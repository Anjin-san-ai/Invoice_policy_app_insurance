"""Swim-lane board for the approvals and payments workflow."""

from __future__ import annotations

import logging
from typing import Any

from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository

logger = logging.getLogger(__name__)

# The lanes an item moves through, left to right. Keys are stable for the UI.
LANES = (
    ("authorise", "Needs authorisation", "Held for a human to authorise before any payment is raised."),
    ("release", "Awaiting release", "Authorised. A different identity must release it."),
    ("released", "Released and written back", "Paid through the supplier's route, with Invoice write-back confirmed."),
    ("blocked", "Blocked", "Stopped before payment and recorded in the audit log."),
)


class PaymentBoardService:
    """Group payment work into the lanes a finance team actually works through.

    The auto-approval engine settles compliant invoices during warm-up, so a plain payments table
    looks empty of anything to do. This board surfaces the real queue instead: high-value invoices
    the specification requires a human to authorise, anything awaiting a second identity to release,
    what has already settled, and what was blocked outright.
    """

    def __init__(self, repository: InvoiceRepository) -> None:
        self.repository = repository

    def board(self, limit_per_lane: int = 40) -> dict[str, Any]:
        """Return every lane with its items and totals."""
        threshold = float(self.repository.settings.get("high_value_threshold_gbp", 5000.0))
        payments_by_invoice = {payment.invoice_id: payment for payment in self.repository.payments.values()}
        high_value_invoices = {
            record.invoice_id for record in self.repository.exceptions.values() if record.reason == "high_value"
        }

        buckets: dict[str, list[dict[str, Any]]] = {key: [] for key, _, _ in LANES}
        for invoice in self.repository.invoices.values():
            payment = payments_by_invoice.get(invoice.id)
            lane = self._lane_for(invoice, payment, high_value_invoices)
            if lane is None:
                continue
            buckets[lane].append(self._item(invoice, payment, threshold, lane, invoice.id in high_value_invoices))

        lanes: list[dict[str, Any]] = []
        for key, title, description in LANES:
            items = buckets.get(key, [])
            # Highest value first: that is the order a finance team triages in.
            items.sort(key=lambda item: item.get("amount_gbp", 0.0), reverse=True)
            lanes.append(
                {
                    "key": key,
                    "title": title,
                    "description": description,
                    "count": len(items),
                    "value_gbp": round(sum(item.get("amount_gbp", 0.0) for item in items), 2),
                    "items": items[:limit_per_lane],
                    "truncated": max(0, len(items) - limit_per_lane),
                }
            )
        logger.info("Payment board lanes: %s", {lane.get("key"): lane.get("count") for lane in lanes})
        return {
            "lanes": lanes,
            "high_value_threshold_gbp": threshold,
            "total_value_gbp": round(sum(lane.get("value_gbp", 0.0) for lane in lanes), 2),
        }

    @staticmethod
    def _lane_for(invoice: Any, payment: Any, high_value_invoices: set[str]) -> str | None:
        """Decide which lane an invoice belongs in, or None when it is not payment work."""
        if invoice.validation_summary.get("is_duplicate"):
            return "blocked"
        if payment is not None:
            return "released" if payment.released_by is not None else "release"
        if invoice.id in high_value_invoices:
            # Specification TC-05: above the threshold, a human authorises regardless of tolerance.
            return "authorise"
        if invoice.status == "Approved":
            return "authorise"
        return None

    def _item(self, invoice: Any, payment: Any, threshold: float, lane: str, is_high_value: bool) -> dict[str, Any]:
        """Return one board card."""
        supplier = self.repository.get_supplier(invoice.supplier_id)
        amount = payment.amount_gbp if payment is not None else invoice.gross_gbp
        return {
            "payment_id": payment.id if payment is not None else None,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "claim_id": invoice.claim_id,
            "supplier_id": invoice.supplier_id,
            "supplier_name": supplier.name if supplier else invoice.supplier_id,
            "amount_gbp": round(amount, 2),
            "vat_gbp": invoice.vat_gbp,
            "path": payment.path if payment is not None else (supplier.payment_path if supplier else "integration"),
            "authorised_by": payment.authorised_by if payment is not None else None,
            "released_by": payment.released_by if payment is not None else None,
            "released_at": payment.released_at if payment is not None else None,
            "invoice_writeback_status": payment.invoice_writeback_status if payment is not None else "not_raised",
            "reference": payment.reference if payment is not None else None,
            "status": invoice.status,
            "above_threshold": amount > threshold,
            "exception_reason": invoice.exception_reason,
            "duplicate_of": invoice.validation_summary.get("duplicate_of"),
            "is_high_value": is_high_value,
            "reason": self._reason(invoice, lane, is_high_value),
        }

    @staticmethod
    def _reason(invoice: Any, lane: str, is_high_value: bool) -> str:
        """Explain in one line why this item sits in this lane."""
        if lane == "blocked":
            original = invoice.validation_summary.get("duplicate_of")
            return f"Duplicate of {original}. Payment blocked so the supplier is not paid twice."
        if lane == "authorise":
            if is_high_value:
                return "Above the value threshold, so a human must authorise it before payment."
            return "Approved by the engine and waiting for a payment to be raised."
        if lane == "release":
            return "Authorised. Segregation of duties requires a different identity to release it."
        return "Settled. Released by a second identity and written back to the Invoice system."
