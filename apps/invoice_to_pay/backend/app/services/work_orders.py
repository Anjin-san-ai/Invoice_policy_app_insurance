"""Supplier work orders: the bridge from a triaged claim to the invoice-to-pay pipeline.

A handler dispatches one work order per authorised service. When a supplier reports the work
finished, this service raises the invoice they would have sent and hands it to the existing
InvoicePipelineService, so a customer-raised claim ends up in the same work queue, tolerance
checks, exception routing and payment board as every batch invoice.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.invoice_to_pay.backend.app.models.domain import SERVICE_TO_SUPPLIER_TYPE
from apps.invoice_to_pay.backend.app.models.domain import WORK_ORDER_SEQUENCE
from apps.invoice_to_pay.backend.app.models.domain import Authorisation
from apps.invoice_to_pay.backend.app.models.domain import Claim
from apps.invoice_to_pay.backend.app.models.domain import DomainClock
from apps.invoice_to_pay.backend.app.models.domain import Invoice
from apps.invoice_to_pay.backend.app.models.domain import InvoiceLine
from apps.invoice_to_pay.backend.app.models.domain import WorkOrder

logger = logging.getLogger(__name__)

# Units authorised per service when a handler dispatches without overriding them.
DEFAULT_UNITS: dict[str, int] = {"repair": 1, "recovery": 1, "hire": 10, "storage": 7}


class WorkOrderService:
    """Dispatches work to suppliers and turns completed work into invoices."""

    def __init__(self, repository: Any, pipeline: Any) -> None:
        self.repository = repository
        self.pipeline = pipeline

    def dispatch(self, claim_id: str, services: list[str], actor_id: str) -> dict[str, Any]:
        """Instruct one supplier per requested service and authorise the spend."""
        claim = self._require_claim(claim_id)
        requested = [service for service in services if service in SERVICE_TO_SUPPLIER_TYPE]
        if not requested:
            raise ValueError(f"No dispatchable services in {services}")

        already = {order.service_type for order in self.repository.claim_work_orders(claim_id)}
        duplicates = [service for service in requested if service in already]
        if duplicates:
            raise ValueError(f"Already dispatched for {', '.join(duplicates)} on {claim_id}")

        created: list[dict[str, Any]] = []
        for service in requested:
            supplier = self._pick_supplier(service, claim_id)
            if supplier is None:
                logger.warning("No supplier of type %s available for %s", service, claim_id)
                continue
            units = DEFAULT_UNITS.get(service, 1)
            rate = self._rate_for(supplier.id, service)
            order_id = self.repository.next_work_order_id()
            order = WorkOrder(
                id=order_id,
                claim_id=claim_id,
                supplier_id=supplier.id,
                service_type=service,
                status="dispatched",
                authorised_units=units,
                authorised_value_gbp=round(units * rate, 2),
                dispatched_at=DomainClock.utc_now(),
                dispatched_by=actor_id,
                notes=f"{service.title()} authorised from claim triage",
            )
            self.repository.add_work_order(order)
            # The authorisation is what the invoice will later be validated against, so it is
            # written at dispatch time rather than invented when the invoice arrives.
            self.repository.add_authorisation(
                Authorisation(
                    id=f"AUTH-{order_id.split('-')[-1]}-{service[:3].upper()}",
                    claim_id=claim_id,
                    supplier_id=supplier.id,
                    service_type=service,
                    authorised_units=units,
                    authorised_value_gbp=order.authorised_value_gbp,
                    authorised_by=actor_id,
                    authorised_at=order.dispatched_at,
                )
            )
            created.append(order.to_dict())

        if not created:
            raise ValueError(f"No supplier could be instructed for {claim_id}")

        before = claim.to_dict()
        claim.workflow_status = "dispatched"
        self.repository.audit.append(
            "claim", claim_id, "work_dispatched", "user", actor_id, before, claim.to_dict()
        )
        names = ", ".join(
            f"{item.get('service_type')} ({self._supplier_name(str(item.get('supplier_id')))})" for item in created
        )
        self.repository.add_claim_notification(
            claim_id,
            "Suppliers appointed",
            f"We have instructed {names}. They will contact you to arrange things.",
            "progress",
        )
        self.repository.persist()
        logger.info("Dispatched %d work orders for %s", len(created), claim_id)
        return {"claim_id": claim_id, "dispatched": created, "claim": claim.to_dict()}

    def advance(self, work_order_id: str, actor_id: str) -> dict[str, Any]:
        """Move a work order to the next status, raising the invoice on completion."""
        order = self.repository.work_orders.get(work_order_id)
        if order is None:
            raise ValueError(f"Unknown work order id {work_order_id}")
        if order.status == "invoiced":
            raise ValueError(f"{work_order_id} has already produced an invoice")

        position = WORK_ORDER_SEQUENCE.index(order.status)
        next_status = WORK_ORDER_SEQUENCE[position + 1]
        before = order.to_dict()
        order.status = next_status  # type: ignore[assignment]
        stamp = DomainClock.utc_now()
        if next_status == "accepted":
            order.accepted_at = stamp
        elif next_status == "in_progress":
            order.started_at = stamp
        elif next_status == "completed":
            order.completed_at = stamp

        invoice_payload: dict[str, Any] | None = None
        if next_status == "invoiced":
            invoice_payload = self._raise_invoice(order)

        self.repository.audit.append(
            "work_order", order.id, f"work_order_{next_status}", "user", actor_id, before, order.to_dict()
        )
        self._notify_progress(order, next_status)
        self._sync_claim_status(order.claim_id, actor_id)
        self.repository.persist()
        return {"work_order": order.to_dict(), "invoice": invoice_payload}

    def _notify_progress(self, order: WorkOrder, status: str) -> None:
        """Tell the customer what just changed, in their language rather than ours."""
        supplier = self._supplier_name(order.supplier_id)
        service = order.service_type.replace("_", " ")
        messages = {
            "accepted": (
                "Quote accepted",
                f"{supplier} has accepted the {service} instruction and quoted for the work.",
                "progress",
            ),
            "in_progress": (
                "Work started",
                f"{supplier} has started the {service} on your vehicle.",
                "progress",
            ),
            "completed": (
                "Work finished",
                f"{supplier} has finished the {service}. We are now checking their invoice.",
                "progress",
            ),
            # Nothing is sent to the customer for "invoiced": receiving and validating a supplier
            # invoice, and paying it, are settlement mechanics between us and the supplier. The
            # customer has no action and no liability there beyond their excess, so telling them
            # only raises questions about money that was never theirs.
        }
        entry = messages.get(status)
        if entry is not None:
            self.repository.add_claim_notification(order.claim_id, entry[0], entry[1], entry[2])

    def _supplier_name(self, supplier_id: str) -> str:
        """Return a supplier's display name, falling back to the id."""
        supplier = self.repository.get_supplier(supplier_id)
        return supplier.name if supplier is not None else supplier_id

    def board(self, claim_id: str) -> list[dict[str, Any]]:
        """Return the work orders on one claim, with the supplier name resolved for display."""
        rows: list[dict[str, Any]] = []
        for order in self.repository.claim_work_orders(claim_id):
            supplier = self.repository.get_supplier(order.supplier_id)
            payload = order.to_dict()
            payload["supplier_name"] = supplier.name if supplier is not None else order.supplier_id
            payload["stage_index"] = order.stage_index()
            payload["stages"] = list(WORK_ORDER_SEQUENCE)
            rows.append(payload)
        return rows

    # ------------------------------------------------------------------ internals

    def _require_claim(self, claim_id: str) -> Claim:
        """Return the claim or raise for an unknown id."""
        claim = self.repository.claims.get(claim_id)
        if claim is None:
            raise ValueError(f"Unknown claim id {claim_id}")
        return claim

    def _pick_supplier(self, service: str, claim_id: str) -> Any:
        """Return a supplier of the type that fulfils this service.

        Selection is deterministic on the claim id so the same claim always routes to the same
        supplier, which keeps a demo reproducible.
        """
        wanted = SERVICE_TO_SUPPLIER_TYPE.get(service)
        candidates = sorted(
            [supplier for supplier in self.repository.suppliers.values() if supplier.type == wanted],
            key=lambda supplier: supplier.id,
        )
        if not candidates:
            return None
        digits = "".join(character for character in claim_id if character.isdigit())
        offset = int(digits) if digits else 0
        return candidates[offset % len(candidates)]

    def _rate_for(self, supplier_id: str, service: str) -> float:
        """Return the contracted rate for this supplier and service."""
        card = self.repository.current_rate_card(supplier_id)
        if card is None:
            return 100.0
        for line in card.lines:
            if line.service_type == service:
                return line.rate_gbp
        return card.lines[0].rate_gbp if card.lines else 100.0

    def _raise_invoice(self, order: WorkOrder) -> dict[str, Any]:
        """Create the invoice the supplier would have sent and run it through the pipeline."""
        supplier = self.repository.get_supplier(order.supplier_id)
        invoice_id, invoice_number = self.repository.next_invoice_identifiers()
        rate = self._rate_for(order.supplier_id, order.service_type)
        units = order.authorised_units
        amount = round(units * rate, 2)
        line = InvoiceLine(
            id=f"{invoice_id}-L1",
            invoice_id=invoice_id,
            line_no=1,
            service_type=order.service_type,  # type: ignore[arg-type]
            service_date_from=order.started_at or order.dispatched_at,
            service_date_to=order.completed_at or DomainClock.utc_now(),
            units=units,
            unit_rate_gbp=rate,
            amount_gbp=amount,
            vat_gbp=round(amount * 0.2, 2),
            extracted_confidence=0.96,
        )
        claim = self.repository.claims.get(order.claim_id)
        claim_ref = claim.invoice_claim_ref if claim is not None else ""
        invoice = Invoice(
            id=invoice_id,
            invoice_number=invoice_number,
            supplier_id=order.supplier_id,
            claim_id=order.claim_id,
            channel="portal",
            received_at=DomainClock.utc_now(),
            document_uri=f"local://documents/{invoice_number}.txt",
            redacted_document_uri=None,
            status="Received",
            gross_gbp=round(amount + line.vat_gbp, 2),
            net_gbp=amount,
            vat_gbp=line.vat_gbp,
            match_confidence=0.99,
            match_method="exact_reference",
            straight_through=False,
            lines=[line],
            document_text=(
                f"Invoice {invoice_number} claim {claim_ref} supplier "
                f"{supplier.name if supplier is not None else order.supplier_id} work order {order.id}."
                f" Service {order.service_type}. Net GBP {amount}. VAT GBP {line.vat_gbp}."
            ),
            layout_id=supplier.template_id if supplier is not None else "generic",
            seeded_outcome="straight_through",
        )
        self.repository.add_invoice(invoice, actor_id=order.supplier_id, event_type="invoice_received_from_supplier")
        order.invoice_id = invoice_id

        # Validate it immediately so the handler sees the outcome rather than a Received row.
        try:
            processed = self.pipeline.process_invoice(invoice_id)
        except ValueError as exc:
            logger.warning("Raised invoice %s could not be processed: %s", invoice_id, exc)
            return invoice.to_dict()
        logger.info("Work order %s produced invoice %s", order.id, invoice_id)
        return processed

    def _sync_claim_status(self, claim_id: str, actor_id: str) -> None:
        """Roll the claim's workflow status up from the state of its work orders."""
        claim = self.repository.claims.get(claim_id)
        if claim is None:
            return
        orders = self.repository.claim_work_orders(claim_id)
        if not orders:
            return
        statuses = {order.status for order in orders}
        if statuses == {"invoiced"}:
            target = "invoicing"
        elif "completed" in statuses or "invoiced" in statuses:
            target = "invoicing"
        elif "in_progress" in statuses or "accepted" in statuses:
            target = "work_in_progress"
        else:
            target = "dispatched"
        if target == claim.workflow_status:
            return
        before = claim.to_dict()
        claim.workflow_status = target  # type: ignore[assignment]
        self.repository.audit.append(
            "claim", claim_id, f"claim_{target}", "agent", actor_id, before, claim.to_dict()
        )
