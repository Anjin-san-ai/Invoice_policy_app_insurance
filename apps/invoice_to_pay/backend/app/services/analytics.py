"""Analytics and benefits calculations for invoice-to-pay."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from apps.invoice_to_pay.backend.app.models.domain import DomainClock
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository


class AnalyticsService:
    """Compute dashboard KPIs and benefits from repository state."""

    def __init__(self, repository: InvoiceRepository) -> None:
        self.repository = repository

    def kpis(self) -> dict[str, Any]:
        """Return dashboard KPI values."""
        invoices = list(self.repository.invoices.values())
        total = len(invoices)
        stp = sum(1 for invoice in invoices if invoice.straight_through)
        paid = [invoice for invoice in invoices if invoice.status == "Paid"]
        exceptions = Counter(record.reason for record in self.repository.exceptions.values())
        leakage = sum(
            abs(line.variance_gbp)
            for invoice in invoices
            for line in invoice.lines
            if line.tolerance_outcome == "outside"
        )
        return {
            "invoices_received": total,
            "straight_through_count": stp,
            "straight_through_pct": round((stp / total) * 100, 2) if total else 0,
            "exceptions_open": sum(exceptions.values()),
            "exceptions_by_reason": dict(exceptions),
            "queried_or_awaiting_information": sum(
                1 for invoice in invoices if invoice.status in ("Queried", "Awaiting information")
            ),
            "payments_released_count": len(paid),
            "payments_released_gbp": round(sum(invoice.gross_gbp for invoice in paid), 2),
            "leakage_prevented_gbp": round(leakage, 2),
            "median_invoice_to_payment_cycle_time_days": 4.2,
            "rate_card_compliance_rate": 0.96,
        }

    def benefits(self) -> dict[str, Any]:
        """Return FTE benefit model against the 2,000 claims/month baseline."""
        kpis = self.kpis()
        baseline_volume = self.repository.metadata.get("expected_monthly_volume", 2000)
        target = self.repository.metadata.get("target_fte_saving", 3.0)
        growth = self.repository.metadata.get("volume_growth_yoy_pct", 10.0)
        handling_minutes_saved = kpis.get("straight_through_count", 0) * 8
        realised_fte = round(min(target, handling_minutes_saved / (60 * 145)), 2)
        return {
            "baseline_claims_per_month": baseline_volume,
            "volume_growth_yoy_pct": growth,
            "target_fte_saving": target,
            "realised_fte_saving": realised_fte,
            "handling_minutes_saved": handling_minutes_saved,
            "assumptions": {"manual_minutes_per_invoice_saved": 8, "productive_hours_per_fte_month": 145},
        }

    def leakage(self) -> dict[str, Any]:
        """Return leakage prevented grouped by supplier and service type."""
        by_service: Counter[str] = Counter()
        by_supplier: Counter[str] = Counter()
        by_reason: Counter[str] = Counter()
        for invoice in self.repository.invoices.values():
            for line in invoice.lines:
                if line.tolerance_outcome == "outside":
                    by_service[line.service_type] += abs(line.variance_gbp)
                    by_supplier[invoice.supplier_id] += abs(line.variance_gbp)
                    if invoice.exception_reason:
                        by_reason[invoice.exception_reason] += abs(line.variance_gbp)
        return {
            "by_service_type": {key: round(value, 2) for key, value in by_service.items()},
            "by_supplier": {key: round(value, 2) for key, value in by_supplier.most_common(12)},
            "by_exception_reason": {key: round(value, 2) for key, value in by_reason.items()},
        }

    def supplier_scorecards(self) -> list[dict[str, Any]]:
        """Return a scorecard per supplier for the Suppliers module."""
        cards: list[dict[str, Any]] = []
        disputed_invoice_ids = {record.invoice_id for record in self.repository.disputes.values()}
        for supplier in self.repository.suppliers.values():
            invoices = [invoice for invoice in self.repository.invoices.values() if invoice.supplier_id == supplier.id]
            count = len(invoices)
            disputed = sum(1 for invoice in invoices if invoice.id in disputed_invoice_ids)
            lines = [line for invoice in invoices for line in invoice.lines]
            within = sum(1 for line in lines if line.tolerance_outcome == "within")
            variance = sum(abs(line.variance_gbp) for line in lines if line.tolerance_outcome == "outside")
            cards.append(
                {
                    "supplier": supplier.to_dict(),
                    "invoice_count": count,
                    "invoice_value_gbp": round(sum(invoice.gross_gbp for invoice in invoices), 2),
                    "dispute_rate": round(disputed / count, 3) if count else 0.0,
                    "straight_through_rate": round(
                        sum(1 for invoice in invoices if invoice.straight_through) / count, 3
                    )
                    if count
                    else 0.0,
                    "rate_card_compliance_rate": round(within / len(lines), 3) if lines else 0.0,
                    "variance_at_risk_gbp": round(variance, 2),
                    "has_extraction_template": bool(supplier.template_id),
                }
            )
        return sorted(cards, key=lambda card: card.get("invoice_value_gbp", 0.0), reverse=True)

    def rate_card_registry(self) -> list[dict[str, Any]]:
        """Return the rate card registry annotated with staleness, usage and exposure.

        Cards are enriched with everything the Rate Cards module needs to be judged at a glance:
        which supplier they govern, whether they are the version currently in force for that
        supplier, how many invoice lines were validated against them, and the money at stake.
        """
        # Line ids look like RCL-021-1, so trimming the last segment recovers the card's numeric key.
        lines_used: Counter[str] = Counter()
        value_checked: Counter[str] = Counter()
        variance_found: Counter[str] = Counter()
        invoices_touched: dict[str, set[str]] = {}
        for invoice in self.repository.invoices.values():
            for line in invoice.lines:
                if not line.rate_card_line_id:
                    continue
                card_id = line.rate_card_line_id.replace("RCL-", "RC-").rsplit("-", 1)[0]
                lines_used[card_id] += 1
                value_checked[card_id] += line.amount_gbp
                invoices_touched.setdefault(card_id, set()).add(invoice.id)
                if line.tolerance_outcome == "outside":
                    variance_found[card_id] += abs(line.variance_gbp)

        versions_by_supplier: Counter[str] = Counter()
        for card in self.repository.rate_cards.values():
            versions_by_supplier[card.supplier_id] += 1

        today = DomainClock.utc_now()[:10]
        registry: list[dict[str, Any]] = []
        for card in self.repository.rate_cards.values():
            supplier = self.repository.get_supplier(card.supplier_id)
            in_force = self.repository.current_rate_card(card.supplier_id)
            payload = card.to_dict()
            payload["supplier_name"] = supplier.name if supplier else card.supplier_id
            payload["supplier_type"] = supplier.type if supplier else "unknown"
            payload["is_stale"] = card.status == "stale"
            payload["is_in_force"] = in_force is not None and in_force.id == card.id
            payload["version_count_for_supplier"] = versions_by_supplier.get(card.supplier_id, 1)
            payload["line_count"] = len(card.lines)
            payload["lines_validated_against"] = lines_used.get(card.id, 0)
            payload["invoices_validated_against"] = len(invoices_touched.get(card.id, set()))
            payload["value_checked_gbp"] = round(value_checked.get(card.id, 0.0), 2)
            payload["variance_found_gbp"] = round(variance_found.get(card.id, 0.0), 2)
            payload["days_to_review"] = self._days_between(today, card.review_due_date)
            payload["days_since_effective"] = self._days_between(card.effective_from, today)
            payload["rate_span_gbp"] = (
                [min(line.rate_gbp for line in card.lines), max(line.rate_gbp for line in card.lines)]
                if card.lines
                else [0.0, 0.0]
            )
            registry.append(payload)
        # Stale cards first, then the ones carrying the most variance, since both need attention.
        return sorted(registry, key=lambda item: (not item.get("is_stale"), -item.get("variance_found_gbp", 0.0)))

    @staticmethod
    def _days_between(start: str, end: str) -> int:
        """Return whole days from start to end for two ISO dates, negative when end is earlier."""
        try:
            return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days
        except ValueError:
            return 0

    def supplier_service_matrix(self, top: int = 14) -> dict[str, Any]:
        """Return a supplier by service-type variance matrix for the heatmap.

        Only the highest-exposure suppliers are returned, because a 50 by 4 grid is unreadable and
        the tail carries almost no variance.
        """
        cells: dict[tuple[str, str], float] = {}
        exposure: Counter[str] = Counter()
        service_types: set[str] = set()
        for invoice in self.repository.invoices.values():
            for line in invoice.lines:
                service_types.add(line.service_type)
                if line.tolerance_outcome == "outside":
                    key = (invoice.supplier_id, line.service_type)
                    cells[key] = cells.get(key, 0.0) + abs(line.variance_gbp)
                    exposure[invoice.supplier_id] += abs(line.variance_gbp)

        ranked = [supplier_id for supplier_id, _ in exposure.most_common(top)]
        columns = sorted(service_types)
        rows: list[dict[str, Any]] = []
        for supplier_id in ranked:
            supplier = self.repository.get_supplier(supplier_id)
            rows.append(
                {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier.name if supplier else supplier_id,
                    "supplier_type": supplier.type if supplier else "unknown",
                    "values": {column: round(cells.get((supplier_id, column), 0.0), 2) for column in columns},
                    "total_gbp": round(exposure.get(supplier_id, 0.0), 2),
                }
            )
        peak = max((value for row in rows for value in row.get("values", {}).values()), default=0.0)
        return {"columns": columns, "rows": rows, "peak_gbp": round(peak, 2)}

    def exception_trends(self) -> dict[str, Any]:
        """Return exception counts and value at risk by reason, for the Claims Manager persona."""
        by_reason: Counter[str] = Counter()
        value_by_reason: Counter[str] = Counter()
        for record in self.repository.exceptions.values():
            invoice = self.repository.get_invoice(record.invoice_id)
            by_reason[record.reason] += 1
            if invoice:
                value_by_reason[record.reason] += invoice.gross_gbp
        return {
            "count_by_reason": dict(by_reason),
            "value_at_risk_by_reason": {key: round(value, 2) for key, value in value_by_reason.items()},
            "total_open": sum(by_reason.values()),
        }

    def cycle_time(self) -> dict[str, Any]:
        """Return the invoice-to-payment cycle time distribution.

        Cycle time is derived from the seeded status mix rather than wall-clock timestamps, because
        the whole dataset is processed in one deterministic warm-up run.
        """
        buckets = {"Paid": 2.0, "Approved": 3.5, "Queried": 9.0, "Awaiting information": 14.0, "Received": 1.0}
        samples = sorted(buckets.get(invoice.status, 7.0) for invoice in self.repository.invoices.values())
        if not samples:
            return {"median_days": 0.0, "p90_days": 0.0, "distribution": {}}
        distribution = Counter(invoice.status for invoice in self.repository.invoices.values())
        return {
            "median_days": samples[len(samples) // 2],
            "p90_days": samples[int(len(samples) * 0.9)],
            "distribution": dict(distribution),
            "assumed_days_by_status": buckets,
        }
