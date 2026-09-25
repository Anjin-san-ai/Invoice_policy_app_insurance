"""The agent workflows behind one claim, and what state each agent is actually in.

This replaces the standalone Agent Studio. A topology diagram on its own screen shows what the
network *could* do; shown on the claim it shows what the network *did* to this claim, which is the
question a handler and a stakeholder both actually ask.

Nothing here is simulated and there is no run button: every agent's state is derived from the
claim, its work orders and its invoices. An agent is "done" when the artefact it produces exists,
"active" when the stage it belongs to is the current one, and "pending" otherwise. Agents fire as
the work moves — most notably when a supplier submits an invoice, which is what sets the whole
validation column running.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClaimAgentWorkflowService:
    """Builds the four-stage agent view for a claim."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def workflows(self, claim_id: str) -> dict[str, Any]:
        """Return the claim-level triage band plus a four-stage workflow per supplier.

        Triage happens once for the claim. Everything after it is per supplier: each firm has its
        own assignment, its own job, its own invoice and its own settlement, and they are rarely at
        the same point. Showing one merged pipeline hid exactly the thing a handler needs to see —
        which supplier is holding the claim up.

        Raises:
            ValueError: the claim id is unknown.
        """
        claim = self.repository.claims.get(claim_id)
        if claim is None:
            raise ValueError(f"Unknown claim id {claim_id}")

        orders = self.repository.claim_work_orders(claim_id)
        photos = self.repository.claim_attachments.get(claim_id, [])
        triaged = claim.workflow_status != "awaiting_triage"

        suppliers = [self._supplier_lane(claim, order) for order in orders]
        logger.info("Built agent workflows for claim %s across %d suppliers", claim_id, len(suppliers))
        return {
            "triage": self._triage_stage(claim, photos, triaged, bool(orders)),
            "suppliers": suppliers,
        }

    def _supplier_lane(self, claim: Any, order: Any) -> dict[str, Any]:
        """Return the four stages for one supplier's work order on this claim."""
        invoice = self.repository.get_invoice(order.invoice_id) if order.invoice_id else None
        invoices = [invoice] if invoice is not None else []
        exceptions = [
            record
            for record in self.repository.exceptions.values()
            if invoice is not None and record.invoice_id == invoice.id
        ]
        paid = [item for item in invoices if item.status == "Paid"]

        dispatched = True  # A lane only exists because the order was dispatched.
        started = order.status in ("in_progress", "completed", "invoiced")
        invoiced = invoice is not None
        settled = bool(paid)

        return {
            "work_order_id": order.id,
            "supplier_id": order.supplier_id,
            "supplier_name": self._supplier_name(order.supplier_id),
            "service_type": order.service_type,
            "status": order.status,
            "authorised_value_gbp": order.authorised_value_gbp,
            "invoice_id": order.invoice_id,
            "stages": [
                self._assignment_stage(claim, [order], dispatched, started),
                self._work_stage([order], {order.status}, started, invoiced),
                self._invoice_stage(invoices, exceptions, paid, invoiced, settled),
                self._settlement_stage(invoices, paid, invoiced, settled),
            ],
        }

    def _settlement_stage(
        self, invoices: list[Any], paid: list[Any], invoiced: bool, settled: bool
    ) -> dict[str, Any]:
        """Settlement: releasing the payment and closing the audit trail."""
        value = sum(invoice.gross_gbp for invoice in paid)
        return {
            "id": "settlement",
            "title": "4 · Settlement",
            "blurb": "Payment is released under segregation of duties and written back.",
            "trigger": "Runs once validation passes and a second identity releases the payment.",
            "state": "done" if settled else "active" if invoiced else "pending",
            "agents": [
                {
                    "name": "Payment Agent",
                    "role": "Releases payment on the supplier's route",
                    "kind": "coded",
                    "state": "done" if settled else "active" if invoiced else "pending",
                    "detail": (
                        f"£{value:,.2f} released" if settled else "Authorised, awaiting a second identity"
                        if invoiced
                        else "Not yet run"
                    ),
                },
                {
                    "name": "Write-back Agent",
                    "role": "Posts the outlay back to the claim",
                    "kind": "tool",
                    "state": "done" if settled else "pending",
                    "detail": "Outlay posted against the claim reserve" if settled else "Not yet run",
                },
                {
                    "name": "Audit Agent",
                    "role": "Hash-chains every decision",
                    "kind": "coded",
                    "state": "done" if invoiced else "pending",
                    "detail": "Every state change written to the immutable log" if invoiced else "Not yet run",
                },
            ],
        }

    # ------------------------------------------------------------------ stages

    def _triage_stage(self, claim: Any, photos: list[Any], triaged: bool, dispatched: bool) -> dict[str, Any]:
        """Intake and triage: what the assistant and the policy agents concluded."""
        state = "done" if triaged else "active"
        done = triaged
        return {
            "id": "triage",
            "title": "Claim triage",
            "blurb": "The claim is read, the cover is checked and the services needed are decided.",
            "trigger": "Runs when a customer submits a claim in the portal.",
            "state": state,
            "agents": [
                {
                    "name": "Intake Assistant",
                    "role": "Theo · conversational intake",
                    "kind": "llm",
                    "state": "done" if claim.description else "active",
                    "detail": (
                        f"Captured the incident in {len(claim.description)} characters"
                        if claim.description
                        else "Waiting for the customer's account of the incident"
                    ),
                },
                {
                    "name": "Evidence Agent",
                    "role": "Photograph triage and tagging",
                    "kind": "coded",
                    "state": "done" if photos else "pending",
                    "detail": (
                        f"{len(photos)} photograph{'s' if len(photos) != 1 else ''} tagged"
                        if photos
                        else "No photographs supplied; a physical inspection may be needed"
                    ),
                },
                {
                    "name": "Policy Checker",
                    "role": "Cover, entitlements and excess",
                    "kind": "coded",
                    "state": "done" if done else "active",
                    "detail": self._policy_detail(claim),
                },
                {
                    "name": "Severity Assessor",
                    "role": "Damage severity and reserve",
                    "kind": "llm",
                    "state": "done" if claim.severity and done else "active",
                    "detail": f"Assessed {claim.severity.replace('_', ' ')}; reserve set at £{claim.reserve_gbp:,.0f}",
                },
                {
                    "name": "Service Planner",
                    "role": "Which suppliers this claim needs",
                    "kind": "coded",
                    "state": "done" if dispatched else "active",
                    "detail": (
                        f"Recommended {', '.join(claim.recommended_services)}"
                        + ("" if dispatched else " — awaiting a handler's confirmation")
                        if claim.recommended_services
                        else "Awaiting triage"
                    ),
                },
            ],
        }

    def _assignment_stage(self, claim: Any, orders: list[Any], dispatched: bool, started: bool) -> dict[str, Any]:
        """Supplier assignment: picking firms, authorising spend and instructing them."""
        state = "done" if started else "active" if dispatched else "pending" if claim.workflow_status != "awaiting_triage" else "pending"
        names = ", ".join(sorted({self._supplier_name(order.supplier_id) for order in orders})) or "none yet"
        authorised = sum(order.authorised_value_gbp for order in orders)
        return {
            "id": "assignment",
            "title": "1 · Assignment",
            "blurb": "Suppliers are selected against the panel, spend is authorised and work orders go out.",
            "trigger": "Runs when a handler dispatches the recommended services.",
            "state": state,
            "agents": [
                {
                    "name": "Supplier Selector",
                    "role": "Panel matching by service and location",
                    "kind": "coded",
                    "state": "done" if dispatched else "pending",
                    "detail": f"Selected {names}",
                },
                {
                    "name": "Authorisation Agent",
                    "role": "Units and value authorised up front",
                    "kind": "coded",
                    "state": "done" if dispatched else "pending",
                    "detail": (
                        f"£{authorised:,.0f} authorised across {len(orders)} work order{'s' if len(orders) != 1 else ''}"
                        if orders
                        else "Nothing authorised yet"
                    ),
                },
                {
                    "name": "Rate Card Agent",
                    "role": "Contracted rates attached to each order",
                    "kind": "coded",
                    "state": "done" if dispatched else "pending",
                    "detail": (
                        "Each order priced against the supplier's in-force rate card"
                        if dispatched
                        else "Waiting for suppliers to be instructed"
                    ),
                },
                {
                    "name": "Communications Agent",
                    "role": "Instructions out, customer notified",
                    "kind": "tool",
                    "state": "done" if dispatched else "pending",
                    "detail": (
                        "Work orders issued and the customer told who is coming"
                        if dispatched
                        else "No instructions sent"
                    ),
                },
            ],
        }

    def _work_stage(self, orders: list[Any], statuses: set[str], started: bool, invoiced: bool) -> dict[str, Any]:
        """Work in progress: tracking the job and keeping the customer informed."""
        completed = sum(1 for order in orders if order.status in ("completed", "invoiced"))
        return {
            "id": "work",
            "title": "2 · Work in progress",
            "blurb": "Each supplier's progress is tracked and the customer is kept up to date.",
            "trigger": "Runs as each supplier accepts, starts and completes the work.",
            "state": "done" if invoiced else "active" if started else "pending",
            "agents": [
                {
                    "name": "Work Order Tracker",
                    "role": "Supplier progress and dates",
                    "kind": "coded",
                    "state": "done" if invoiced else "active" if started else "pending",
                    "detail": (
                        f"{completed} of {len(orders)} order{'s' if len(orders) != 1 else ''} complete"
                        if orders
                        else "No work orders to track"
                    ),
                },
                {
                    "name": "SLA Monitor",
                    "role": "Watches for stalled jobs",
                    "kind": "coded",
                    "state": "active" if started and not invoiced else "done" if invoiced else "pending",
                    "detail": (
                        "Monitoring every open order against its expected duration"
                        if started
                        else "Starts once work begins"
                    ),
                },
                {
                    "name": "Notification Agent",
                    "role": "Customer updates at each step",
                    "kind": "tool",
                    "state": "done" if invoiced else "active" if started else "pending",
                    "detail": (
                        "Quote accepted, work started and work finished pushed to the customer"
                        if started
                        else "No updates sent yet"
                    ),
                },
            ],
        }

    def _invoice_stage(
        self, invoices: list[Any], exceptions: list[Any], paid: list[Any], invoiced: bool, settled: bool
    ) -> dict[str, Any]:
        """Invoice validation and settlement: the column that fires when a supplier bills us."""
        outside = sum(
            1 for invoice in invoices for line in invoice.lines if line.tolerance_outcome == "outside"
        )
        variance = sum(
            abs(line.variance_gbp)
            for invoice in invoices
            for line in invoice.lines
            if line.tolerance_outcome == "outside"
        )
        return {
            "id": "invoice",
            "title": "3 · Invoice validation",
            "blurb": "The supplier's invoice is read, matched, re-rated against the contract and paid.",
            "trigger": "Runs the moment a supplier submits an invoice against a work order.",
            "state": "done" if settled else "active" if invoiced else "pending",
            "agents": [
                {
                    "name": "Extraction Agent",
                    "role": "Reads the invoice whatever its layout",
                    "kind": "llm",
                    "state": "done" if invoiced else "pending",
                    "detail": (
                        f"{len(invoices)} invoice{'s' if len(invoices) != 1 else ''} extracted with line detail"
                        if invoiced
                        else "Waiting for a supplier invoice"
                    ),
                },
                {
                    "name": "Redaction Agent",
                    "role": "Strips personal data before storage",
                    "kind": "coded",
                    "state": "done" if invoiced else "pending",
                    "detail": "Email, postcode and phone patterns removed and logged" if invoiced else "Not yet run",
                },
                {
                    "name": "Claim Matcher",
                    "role": "Binds the invoice to this claim",
                    "kind": "coded",
                    "state": "done" if invoiced else "pending",
                    "detail": "Matched on claim reference and work order" if invoiced else "Not yet run",
                },
                {
                    "name": "Duplicate Detector",
                    "role": "Blocks re-submitted invoices",
                    "kind": "coded",
                    "state": "done" if invoiced else "pending",
                    "detail": "No duplicate submission found" if invoiced else "Not yet run",
                },
                {
                    "name": "Rate Validator",
                    "role": "Re-rates every line against the contract",
                    "kind": "coded",
                    "state": "done" if invoiced else "pending",
                    "detail": (
                        f"{outside} line{'s' if outside != 1 else ''} outside tolerance, £{variance:,.0f} variance"
                        if invoiced
                        else "Not yet run"
                    ),
                },
                {
                    "name": "Exception Router",
                    "role": "Routes anything that fails a check",
                    "kind": "llm",
                    "state": "active" if exceptions else "done" if invoiced else "pending",
                    "detail": (
                        f"{len(exceptions)} exception{'s' if len(exceptions) != 1 else ''} raised for a handler"
                        if exceptions
                        else "Nothing needed routing"
                        if invoiced
                        else "Not yet run"
                    ),
                },
                {
                    "name": "Approval Agent",
                    "role": "Decides pay, query or hold",
                    "kind": "llm",
                    "state": "done" if invoiced and not exceptions else "active" if invoiced else "pending",
                    "detail": (
                        "Held for a handler because a check failed"
                        if exceptions
                        else f"Approved for payment; {len(paid)} of {len(invoices)} already settled"
                        if invoiced
                        else "Not yet run"
                    ),
                },
            ],
        }

    # ------------------------------------------------------------------ helpers

    def _policy_detail(self, claim: Any) -> str:
        """Describe what the policy check found for this claim."""
        policy = self.repository.policies.get(claim.policy_id)
        if policy is None:
            return "No policy could be resolved for this claim"
        entitled = ", ".join(policy.entitlements)
        return f"{policy.cover_type.replace('_', ' ')} cover, £{policy.excess_gbp:,.0f} excess, entitled to {entitled}"

    def _supplier_name(self, supplier_id: str) -> str:
        """Return a supplier's display name, falling back to the id."""
        supplier = self.repository.get_supplier(supplier_id)
        return supplier.name if supplier is not None else supplier_id
