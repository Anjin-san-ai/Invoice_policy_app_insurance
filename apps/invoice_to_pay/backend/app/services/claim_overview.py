"""Claim-centric aggregation for the 360 degree claim view."""

from __future__ import annotations

import logging
from typing import Any

from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository

logger = logging.getLogger(__name__)

# Order the lifecycle stages appear in on the claim timeline, so the UI can lay them out without
# having to know the pipeline's internals.
STAGE_ORDER = ("Received", "Extracted", "Redacted", "Matched", "Validated", "Approved", "Paid")


class ClaimOverviewService:
    """Assemble everything known about one claim across suppliers, invoices and payments."""

    def __init__(self, repository: InvoiceRepository) -> None:
        self.repository = repository

    def list_claims(self, limit: int = 60, search: str | None = None) -> list[dict[str, Any]]:
        """Return claims ranked by invoiced value, with the headline aggregates per claim."""
        invoices_by_claim: dict[str, list[Any]] = {}
        for invoice in self.repository.invoices.values():
            if invoice.claim_id:
                invoices_by_claim.setdefault(invoice.claim_id, []).append(invoice)

        rows: list[dict[str, Any]] = []
        needle = (search or "").strip().lower()
        for claim in self.repository.claims.values():
            if needle and needle not in claim.id.lower() and needle not in claim.ice_claim_ref.lower():
                continue
            invoices = invoices_by_claim.get(claim.id, [])
            if not invoices:
                continue
            rows.append(
                {
                    "claim": claim.to_dict(),
                    "invoice_count": len(invoices),
                    "supplier_count": len({invoice.supplier_id for invoice in invoices}),
                    "invoiced_gbp": round(sum(invoice.gross_gbp for invoice in invoices), 2),
                    "paid_gbp": round(sum(invoice.gross_gbp for invoice in invoices if invoice.status == "Paid"), 2),
                    "open_count": sum(1 for invoice in invoices if invoice.status != "Paid"),
                    "variance_gbp": round(
                        sum(
                            abs(line.variance_gbp)
                            for invoice in invoices
                            for line in invoice.lines
                            if line.tolerance_outcome == "outside"
                        ),
                        2,
                    ),
                }
            )
        rows.sort(key=lambda row: row.get("invoiced_gbp", 0.0), reverse=True)
        return rows[:limit]

    def overview(self, claim_id: str) -> dict[str, Any]:
        """Return the full 360 degree view for one claim.

        Raises:
            ValueError: the claim id is not in the seeded estate.
        """
        claim = self.repository.get_claim(claim_id)
        if claim is None:
            raise ValueError(f"Unknown claim id: {claim_id}")

        invoices = [invoice for invoice in self.repository.invoices.values() if invoice.claim_id == claim_id]
        policy = self.repository.policies.get(claim.policy_id)
        suppliers = self._suppliers(invoices)
        authorisations = self._authorisations(claim_id, invoices)
        payments = [
            payment.to_dict()
            for payment in self.repository.payments.values()
            if payment.invoice_id in {invoice.id for invoice in invoices}
        ]
        logger.info("Claim %s overview: %d invoices, %d suppliers", claim_id, len(invoices), len(suppliers))

        return {
            "claim": claim.to_dict(),
            "policy": policy.to_dict() if policy else None,
            "financials": self._financials(claim, invoices, payments),
            "suppliers": suppliers,
            "authorisations": authorisations,
            "invoices": [self._invoice_card(invoice) for invoice in invoices],
            "service_mix": self._service_mix(invoices),
            "stage_counts": self._stage_counts(invoices),
            "exceptions": [
                record.to_dict()
                for record in self.repository.exceptions.values()
                if record.invoice_id in {invoice.id for invoice in invoices}
            ],
            "disputes": [
                record.to_dict()
                for record in self.repository.disputes.values()
                if record.invoice_id in {invoice.id for invoice in invoices}
            ],
            "payments": payments,
            "timeline": self._timeline(invoices),
        }

    def _financials(self, claim: Any, invoices: list[Any], payments: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the reserve against what has been invoiced, paid and held back."""
        invoiced = round(sum(invoice.gross_gbp for invoice in invoices), 2)
        paid = round(sum(invoice.gross_gbp for invoice in invoices if invoice.status == "Paid"), 2)
        queried = round(sum(invoice.gross_gbp for invoice in invoices if invoice.status != "Paid"), 2)
        prevented = round(
            sum(
                abs(line.variance_gbp)
                for invoice in invoices
                for line in invoice.lines
                if line.tolerance_outcome == "outside"
            ),
            2,
        )
        reserve = float(claim.reserve_gbp)
        return {
            "reserve_gbp": reserve,
            "invoiced_gbp": invoiced,
            "paid_gbp": paid,
            "withheld_gbp": queried,
            "leakage_prevented_gbp": prevented,
            "vat_gbp": round(sum(invoice.vat_gbp for invoice in invoices), 2),
            "reserve_utilisation_pct": round((invoiced / reserve) * 100, 1) if reserve else 0.0,
            "released_count": sum(1 for payment in payments if payment.get("released_by")),
            "payment_count": len(payments),
        }

    def _suppliers(self, invoices: list[Any]) -> list[dict[str, Any]]:
        """Return each supplier working on the claim with their exposure on it."""
        grouped: dict[str, list[Any]] = {}
        for invoice in invoices:
            grouped.setdefault(invoice.supplier_id, []).append(invoice)
        cards: list[dict[str, Any]] = []
        for supplier_id, items in grouped.items():
            supplier = self.repository.get_supplier(supplier_id)
            cards.append(
                {
                    "supplier": supplier.to_dict() if supplier else {"id": supplier_id, "name": supplier_id},
                    "invoice_count": len(items),
                    "invoiced_gbp": round(sum(invoice.gross_gbp for invoice in items), 2),
                    "disputed_count": sum(1 for invoice in items if invoice.status == "Queried"),
                    "variance_gbp": round(
                        sum(
                            abs(line.variance_gbp)
                            for invoice in items
                            for line in invoice.lines
                            if line.tolerance_outcome == "outside"
                        ),
                        2,
                    ),
                }
            )
        cards.sort(key=lambda card: card.get("invoiced_gbp", 0.0), reverse=True)
        return cards

    def _authorisations(self, claim_id: str, invoices: list[Any]) -> list[dict[str, Any]]:
        """Return authorised units and value against what was actually charged."""
        rows: list[dict[str, Any]] = []
        for authorisation in self.repository.authorisations.values():
            if authorisation.claim_id != claim_id:
                continue
            matching_lines = [
                line
                for invoice in invoices
                if invoice.supplier_id == authorisation.supplier_id
                for line in invoice.lines
                if line.service_type == authorisation.service_type
            ]
            charged_units = sum(line.units for line in matching_lines)
            charged_value = round(sum(line.amount_gbp for line in matching_lines), 2)
            rows.append(
                {
                    "authorisation": authorisation.to_dict(),
                    "charged_units": charged_units,
                    "charged_value_gbp": charged_value,
                    "units_over": max(0, charged_units - authorisation.authorised_units),
                    "value_over_gbp": round(max(0.0, charged_value - authorisation.authorised_value_gbp), 2),
                }
            )
        return rows

    def _invoice_card(self, invoice: Any) -> dict[str, Any]:
        """Return the compact invoice summary the 360 view renders as a card."""
        outside = [line for line in invoice.lines if line.tolerance_outcome == "outside"]
        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "supplier_id": invoice.supplier_id,
            "status": invoice.status,
            "channel": invoice.channel,
            "received_at": invoice.received_at,
            "gross_gbp": invoice.gross_gbp,
            "vat_gbp": invoice.vat_gbp,
            "straight_through": invoice.straight_through,
            "exception_reason": invoice.exception_reason,
            "match_confidence": invoice.match_confidence,
            "line_count": len(invoice.lines),
            "outside_line_ids": [line.id for line in outside],
            "variance_gbp": round(sum(abs(line.variance_gbp) for line in outside), 2),
            "decision": invoice.decision.get("decision") if invoice.decision else None,
            "service_types": sorted({line.service_type for line in invoice.lines}),
        }

    @staticmethod
    def _service_mix(invoices: list[Any]) -> dict[str, float]:
        """Return the claim's spend split by service type."""
        mix: dict[str, float] = {}
        for invoice in invoices:
            for line in invoice.lines:
                mix[line.service_type] = round(mix.get(line.service_type, 0.0) + line.amount_gbp, 2)
        return mix

    @staticmethod
    def _stage_counts(invoices: list[Any]) -> dict[str, int]:
        """Return how far each invoice on the claim has progressed.

        Every processed invoice has passed intake, extraction, redaction, matching and validation, so
        those stages count the whole set; the later stages count by current status.
        """
        total = len(invoices)
        approved = sum(1 for invoice in invoices if invoice.status in ("Approved", "Paid"))
        paid = sum(1 for invoice in invoices if invoice.status == "Paid")
        return {
            "Received": total,
            "Extracted": total,
            "Redacted": total,
            "Matched": sum(1 for invoice in invoices if invoice.claim_id),
            "Validated": total,
            "Approved": approved,
            "Paid": paid,
        }

    def _timeline(self, invoices: list[Any]) -> list[dict[str, Any]]:
        """Return the audit events for every entity attached to the claim, in order."""
        invoice_ids = {invoice.id for invoice in invoices}
        events: list[dict[str, Any]] = []
        for event in self.repository.audit.list_events():
            entity_id = event.get("entity_id", "")
            if entity_id in invoice_ids or any(entity_id.endswith(invoice_id) for invoice_id in invoice_ids):
                events.append(
                    {
                        "id": event.get("id"),
                        "entity_type": event.get("entity_type"),
                        "entity_id": entity_id,
                        "event_type": event.get("event_type"),
                        "actor": event.get("actor"),
                        "actor_id": event.get("actor_id"),
                        "occurred_at": event.get("occurred_at"),
                    }
                )
        return events
