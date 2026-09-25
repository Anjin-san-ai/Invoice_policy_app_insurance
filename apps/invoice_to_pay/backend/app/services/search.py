"""Cross-module search so one bar on every screen can find any entity."""

import logging
from typing import Any

from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository

logger = logging.getLogger(__name__)


class SearchService:
    """Substring search across every entity a finance user can navigate to.

    The estate is small and held in memory, so a linear scan is cheaper than an index and
    always reflects the current pipeline state. Results carry the route the UI should open.
    """

    GROUP_LIMIT = 6

    def __init__(self, repository: InvoiceRepository) -> None:
        self.repository = repository

    def search(self, query: str, limit: int = 40) -> dict[str, Any]:
        """Return grouped hits for a free-text query, best group order first."""
        needle = (query or "").strip().lower()
        if len(needle) < 2:
            return {"query": query, "total": 0, "groups": []}

        groups = [
            {"key": "invoices", "title": "Invoices", "hits": self._invoices(needle)},
            {"key": "claims", "title": "Claims", "hits": self._claims(needle)},
            {"key": "suppliers", "title": "Suppliers", "hits": self._suppliers(needle)},
            {"key": "rate_cards", "title": "Rate cards", "hits": self._rate_cards(needle)},
            {"key": "exceptions", "title": "Exceptions", "hits": self._exceptions(needle)},
            {"key": "modules", "title": "Modules", "hits": self._modules(needle)},
        ]

        total = sum(len(group.get("hits", [])) for group in groups)
        trimmed = []
        remaining = limit
        for group in groups:
            hits = group.get("hits", [])
            if not hits:
                continue
            shown = hits[: min(self.GROUP_LIMIT, max(remaining, 0))]
            remaining -= len(shown)
            trimmed.append(
                {
                    "key": group.get("key"),
                    "title": group.get("title"),
                    "count": len(hits),
                    "hits": shown,
                }
            )
        logger.debug("Search for %r matched %s entities", query, total)
        return {"query": query, "total": total, "groups": trimmed}

    @staticmethod
    def _hit(route: str, title: str, subtitle: str, badge: str) -> dict[str, str]:
        """Build one result row; `route` is the hash route the shell navigates to."""
        return {"route": route, "title": title, "subtitle": subtitle, "badge": badge}

    def _invoices(self, needle: str) -> list[dict[str, str]]:
        hits = []
        for invoice in self.repository.invoices.values():
            supplier = self.repository.suppliers.get(invoice.supplier_id)
            supplier_name = supplier.name if supplier is not None else invoice.supplier_id
            haystack = " ".join(
                [
                    invoice.id,
                    invoice.invoice_number,
                    invoice.supplier_id,
                    supplier_name,
                    invoice.claim_id or "",
                    invoice.status,
                    invoice.exception_reason or "",
                ]
            ).lower()
            if needle in haystack:
                hits.append(
                    self._hit(
                        f"/invoice/{invoice.id}",
                        f"{invoice.invoice_number} · £{invoice.gross_gbp:,.2f}",
                        f"{supplier_name} · {invoice.claim_id or 'unmatched'}",
                        invoice.status,
                    )
                )
        return sorted(hits, key=lambda hit: hit.get("title", ""))

    def _claims(self, needle: str) -> list[dict[str, str]]:
        hits = []
        for claim in self.repository.claims.values():
            haystack = f"{claim.id} {claim.invoice_claim_ref} {claim.policy_id} {claim.customer_id} {claim.status}".lower()
            if needle in haystack:
                hits.append(
                    self._hit(
                        f"/claim/{claim.id}",
                        f"{claim.id} · {claim.invoice_claim_ref}",
                        f"Reserve £{claim.reserve_gbp:,.0f} · paid £{claim.paid_to_date_gbp:,.0f}",
                        claim.status,
                    )
                )
        return sorted(hits, key=lambda hit: hit.get("title", ""))

    def _suppliers(self, needle: str) -> list[dict[str, str]]:
        hits = []
        for supplier in self.repository.suppliers.values():
            haystack = (
                f"{supplier.id} {supplier.name} {supplier.type} {supplier.contact} {supplier.payment_path}".lower()
            )
            if needle in haystack:
                hits.append(
                    self._hit(
                        f"/suppliers?supplier={supplier.id}",
                        supplier.name,
                        f"{supplier.type} · {supplier.payment_path}",
                        supplier.id,
                    )
                )
        return sorted(hits, key=lambda hit: hit.get("title", ""))

    def _rate_cards(self, needle: str) -> list[dict[str, str]]:
        hits = []
        for card in self.repository.rate_cards.values():
            supplier = self.repository.suppliers.get(card.supplier_id)
            supplier_name = supplier.name if supplier is not None else card.supplier_id
            haystack = f"{card.id} {card.version} {card.supplier_id} {supplier_name} {card.status}".lower()
            if needle in haystack:
                hits.append(
                    self._hit(
                        f"/rate-cards?q={card.id}",
                        f"{card.id} · {card.version}",
                        f"{supplier_name} · effective {card.effective_from}",
                        card.status,
                    )
                )
        return sorted(hits, key=lambda hit: hit.get("title", ""))

    def _exceptions(self, needle: str) -> list[dict[str, str]]:
        hits = []
        for item in self.repository.exceptions.values():
            haystack = f"{item.id} {item.invoice_id} {item.reason} {item.explanation} {item.assigned_to}".lower()
            if needle in haystack:
                hits.append(
                    self._hit(
                        f"/invoice/{item.invoice_id}",
                        f"{item.reason.replace('_', ' ')} · {item.invoice_id}",
                        item.explanation[:110],
                        f"P{item.priority}",
                    )
                )
        return sorted(hits, key=lambda hit: hit.get("title", ""))

    # Module titles, kept here so search also works as a jump-to-page palette.
    MODULES = (
        ("/dashboard", "Dashboard", "Portfolio KPIs and straight-through rate"),
        ("/queue", "Invoice Work Queue", "Every invoice with stage, status and variance"),
        ("/claims", "Claim 360", "One claim, every supplier, invoice and payment"),
        ("/exceptions", "Exceptions", "The fixed five-value taxonomy with next actions"),
        ("/disputes", "Disputes", "Supplier queries raised and their outcomes"),
        ("/approvals", "Approvals & Payments", "Swim-lane board from authorisation to release"),
        ("/suppliers", "Suppliers", "Scorecards, dispute rate and compliance"),
        ("/rate-cards", "Rate Cards", "Contracted rates, versions and stale reviews"),
        ("/analytics", "Analytics", "Leakage, cycle time and exception trends"),
        ("/benefits", "Benefits Tracker", "FTE saving against the business case"),
        ("/audit", "Audit Trail", "Hash-chained append-only events"),
        ("/agent-studio", "Agent Studio", "The interactive Neuro SAN agent network"),
        ("/settings", "Settings", "Thresholds, tolerances and redaction rules"),
    )

    def _modules(self, needle: str) -> list[dict[str, str]]:
        return [
            self._hit(route, label, description, "page")
            for route, label, description in self.MODULES
            if needle in f"{label} {description}".lower()
        ]
