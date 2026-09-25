"""Customer-facing claim tracking: the journey, its tickmarks, and the notification feed.

The journey is derived rather than stored. Back-office actions already mutate the claim, its work
orders and its invoices, so computing the customer view from those means the two can never drift
out of step: a handler cannot advance a repair without the customer's tracker moving with it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClaimTrackingService:
    """Builds the customer's view of where their claim has got to."""

    # The customer-facing milestones, in order. Deliberately fewer and plainer than the internal
    # workflow: a policyholder cares about their car, not about tolerance checks.
    #
    # The journey deliberately ends at "Work complete". Invoice validation and paying the supplier
    # are settlement mechanics between us and the supplier: the customer has nothing to do with
    # them and nothing to do about them, so surfacing them only invites questions about money that
    # was never theirs to pay.
    STEPS: tuple[dict[str, str], ...] = (
        {"id": "submitted", "title": "Claim received", "blurb": "We have your claim and your photographs."},
        {"id": "reviewed", "title": "Handler review", "blurb": "A claims handler has assessed the incident and cover."},
        {"id": "instructed", "title": "Suppliers appointed", "blurb": "We have appointed the garages and services you need."},
        {"id": "started", "title": "Work started", "blurb": "Your vehicle is with the supplier and work is under way."},
        {"id": "completed", "title": "Work complete", "blurb": "The work is finished. We settle the supplier directly."},
    )

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def track(self, claim_id: str) -> dict[str, Any]:
        """Return the tracking payload for one claim.

        Raises:
            ValueError: the claim id is unknown or still a draft the customer never submitted.
        """
        claim = self.repository.claims.get(claim_id)
        if claim is None:
            raise ValueError(f"We could not find a claim with reference {claim_id}")
        if claim.workflow_status == "draft":
            raise ValueError(f"Claim {claim_id} has not been submitted yet")

        orders = self.repository.claim_work_orders(claim_id)
        invoices = self.repository.claim_invoices(claim_id)
        reached = self._reached(claim, orders, invoices)

        # The journey is monotonic: a milestone can only be ticked if every milestone before it
        # is. Without this, a claim that happens to carry an invoice but has not been triaged
        # shows "Invoice checked" ticked directly under "Claim received", which reads as nonsense.
        frontier = len(self.STEPS)
        for position, step in enumerate(self.STEPS):
            if not reached.get(str(step.get("id")), False):
                frontier = position
                break

        steps: list[dict[str, Any]] = []
        current_seen = False
        for position, step in enumerate(self.STEPS):
            done = position < frontier
            # The first not-done step is "current"; everything after it is pending.
            is_current = not done and not current_seen
            if is_current:
                current_seen = True
            steps.append(
                {
                    "id": step.get("id"),
                    "title": step.get("title"),
                    "blurb": step.get("blurb"),
                    "state": "done" if done else "current" if is_current else "pending",
                    "at": self._stamp_for(str(step.get("id")), claim, orders, invoices),
                }
            )

        done_count = sum(1 for step in steps if step.get("state") == "done")
        return {
            "claim": claim.to_dict(),
            "steps": steps,
            "completed_steps": done_count,
            "total_steps": len(steps),
            "percent_complete": round(done_count / len(steps) * 100),
            "notifications": [item.to_dict() for item in reversed(self.repository.claim_notification_list(claim_id))],
            "work_orders": [self._work_order_card(order) for order in orders],
            "attachments": [item.to_dict() for item in self.repository.claim_attachments.get(claim_id, [])],
            "excess_gbp": self._excess_for(claim),
        }

    def for_customer(self, customer_name: str) -> list[dict[str, Any]]:
        """Return every submitted claim belonging to one policyholder, newest first.

        Matching is on the name the portal signed in with. There is no authentication in the
        prototype, so this is identity by assertion; a real deployment would resolve the
        policyholder from the session rather than a name string.
        """
        needle = (customer_name or "").strip().lower()
        if not needle:
            return []
        rows: list[dict[str, Any]] = []
        for claim in self.repository.claims.values():
            if claim.workflow_status == "draft":
                continue
            if (claim.customer_name or "").strip().lower() != needle:
                continue
            orders = self.repository.claim_work_orders(claim.id)
            invoices = self.repository.claim_invoices(claim.id)
            reached = self._reached(claim, orders, invoices)
            done = 0
            for step in self.STEPS:
                if not reached.get(str(step.get("id")), False):
                    break
                done += 1
            unread = sum(1 for note in self.repository.claim_notification_list(claim.id) if not note.read)
            rows.append(
                {
                    "claim_id": claim.id,
                    "incident_type": claim.incident_type,
                    "incident_date": claim.incident_date,
                    "incident_location": claim.incident_location,
                    "vehicle_registration": claim.vehicle_registration,
                    "severity": claim.severity,
                    "reported_at": claim.reported_at,
                    "stage_title": self._stage_title(done),
                    "percent_complete": round(done / len(self.STEPS) * 100),
                    "photo_count": len(self.repository.claim_attachments.get(claim.id, [])),
                    "supplier_count": len({order.supplier_id for order in orders}),
                    "update_count": unread,
                }
            )
        rows.sort(key=lambda row: str(row.get("reported_at")), reverse=True)
        return rows

    def _stage_title(self, done: int) -> str:
        """Return the milestone a claim is currently sitting on."""
        if done >= len(self.STEPS):
            return str(self.STEPS[-1].get("title"))
        return str(self.STEPS[done].get("title"))

    def find(self, reference: str, surname: str = "") -> dict[str, Any]:
        """Look a claim up by reference, optionally checked against the policyholder's surname."""
        needle = (reference or "").strip().upper()
        if not needle:
            raise ValueError("Enter your claim reference")
        claim = self.repository.claims.get(needle)
        if claim is None:
            # Be forgiving about the prefix: people read "00111" off an email.
            digits = "".join(character for character in needle if character.isdigit())
            if digits:
                claim = self.repository.claims.get(f"CLM-{int(digits):05d}")
        if claim is None:
            raise ValueError(f"We could not find a claim with reference {reference}")
        if surname.strip() and surname.strip().lower() not in (claim.customer_name or "").lower():
            raise ValueError("That reference and surname do not match our records")
        return self.track(claim.id)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _reached(claim: Any, orders: list[Any], invoices: list[Any]) -> dict[str, bool]:
        """Return which milestones the claim has passed."""
        statuses = {order.status for order in orders}
        return {
            "submitted": True,
            "reviewed": claim.workflow_status != "awaiting_triage",
            "instructed": bool(orders),
            "started": bool(statuses & {"in_progress", "completed", "invoiced"}),
            "completed": bool(orders) and statuses.issubset({"completed", "invoiced"}),
        }

    @staticmethod
    def _stamp_for(step_id: str, claim: Any, orders: list[Any], invoices: list[Any]) -> str | None:
        """Return the timestamp to show against a milestone, where one is known."""
        if step_id == "submitted":
            return claim.reported_at or None
        if step_id == "instructed" and orders:
            return min(order.dispatched_at for order in orders)
        if step_id == "started":
            started = [order.started_at for order in orders if order.started_at]
            return min(started) if started else None
        if step_id == "completed":
            finished = [order.completed_at for order in orders if order.completed_at]
            return max(finished) if finished else None
        return None

    def _work_order_card(self, order: Any) -> dict[str, Any]:
        """Return a customer-safe view of a work order: no rates, no supplier commercials."""
        supplier = self.repository.get_supplier(order.supplier_id)
        return {
            "id": order.id,
            "service_type": order.service_type,
            "supplier_name": supplier.name if supplier is not None else "Appointed supplier",
            "status": order.status,
            "stage_index": order.stage_index(),
            "dispatched_at": order.dispatched_at,
            "completed_at": order.completed_at,
        }

    def _excess_for(self, claim: Any) -> float:
        """Return the policy excess the customer is liable for."""
        policy = self.repository.policies.get(claim.policy_id)
        return float(policy.excess_gbp) if policy is not None else 0.0
