"""In-memory repository backed by deterministic seed data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.invoice_to_pay.backend.app.audit.audit_log import AuditLog
from apps.invoice_to_pay.backend.app.models.domain import Authorisation
from apps.invoice_to_pay.backend.app.models.domain import Claim
from apps.invoice_to_pay.backend.app.models.domain import DisputeQuery
from apps.invoice_to_pay.backend.app.models.domain import ExceptionRecord
from apps.invoice_to_pay.backend.app.models.domain import Invoice
from apps.invoice_to_pay.backend.app.models.domain import InvoiceLine
from apps.invoice_to_pay.backend.app.models.domain import Notification
from apps.invoice_to_pay.backend.app.models.domain import Payment
from apps.invoice_to_pay.backend.app.models.domain import Policy
from apps.invoice_to_pay.backend.app.models.domain import RateCard
from apps.invoice_to_pay.backend.app.models.domain import RateCardLine
from apps.invoice_to_pay.backend.app.models.domain import RedactionLog
from apps.invoice_to_pay.backend.app.models.domain import Supplier
from apps.invoice_to_pay.data.generator.generate_seed import SeedDataGenerator

DEFAULT_DATA_PATH = Path("apps/invoice_to_pay/data/seed/invoice_demo_data.json")


class InvoiceRepository:
    """Simple in-memory repository for the prototype API and coded tools."""

    def __init__(self, data_path: Path = DEFAULT_DATA_PATH) -> None:
        if not data_path.exists():
            SeedDataGenerator.write_default(str(data_path))
        data = json.loads(data_path.read_text(encoding="utf-8"))
        self.metadata = data.get("metadata", {})
        self.settings = data.get("settings", {})
        self.suppliers = {item.get("id"): Supplier(**item) for item in data.get("suppliers", [])}
        self.rate_cards = {item.get("id"): self._rate_card_from_dict(item) for item in data.get("rate_cards", [])}
        self.policies = {item.get("id"): Policy(**item) for item in data.get("policies", [])}
        self.claims = {item.get("id"): Claim(**item) for item in data.get("claims", [])}
        self.authorisations = {item.get("id"): Authorisation(**item) for item in data.get("authorisations", [])}
        self.invoices = {item.get("id"): self._invoice_from_dict(item) for item in data.get("invoices", [])}
        self.exceptions: dict[str, ExceptionRecord] = {}
        self.disputes: dict[str, DisputeQuery] = {}
        self.redactions: dict[str, list[RedactionLog]] = {}
        self.traces: dict[str, list[Any]] = {}
        self.payments: dict[str, Payment] = {}
        self.notifications: dict[str, list[Notification]] = {}
        # Seeded anomaly sets live at the top level of the seed file, not under metadata.
        self.duplicate_pairs: list[dict[str, str]] = data.get("duplicates", [])
        self.split_invoice_patterns: list[str] = data.get("split_invoice_patterns", [])
        self.value_outlier_numbers: list[str] = data.get("value_outliers", [])
        self._duplicate_originals = {pair.get("duplicate"): pair.get("original") for pair in self.duplicate_pairs}
        self.audit = AuditLog()

    def duplicate_of(self, invoice_number: str) -> str | None:
        """Return the original invoice number when this invoice number is a seeded duplicate."""
        return self._duplicate_originals.get(invoice_number)

    def is_value_outlier(self, invoice_number: str) -> bool:
        """Return whether this invoice number is a seeded value outlier."""
        return invoice_number in self.value_outlier_numbers

    @staticmethod
    def _rate_card_from_dict(item: dict[str, Any]) -> RateCard:
        """Create a RateCard from a dictionary."""
        lines = [RateCardLine(**line) for line in item.get("lines", [])]
        payload = dict(item)
        payload["lines"] = lines
        return RateCard(**payload)

    @staticmethod
    def _invoice_from_dict(item: dict[str, Any]) -> Invoice:
        """Create an Invoice from a dictionary."""
        lines = [InvoiceLine(**line) for line in item.get("lines", [])]
        payload = dict(item)
        payload["lines"] = lines
        return Invoice(**payload)

    def list_invoices(
        self, status: str | None = None, supplier_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return invoices filtered for work queues."""
        invoices = list(self.invoices.values())
        if status:
            invoices = [invoice for invoice in invoices if invoice.status == status]
        if supplier_id:
            invoices = [invoice for invoice in invoices if invoice.supplier_id == supplier_id]
        return [invoice.to_dict() for invoice in invoices[:limit]]

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        """Return one invoice by id."""
        return self.invoices.get(invoice_id)

    def get_supplier(self, supplier_id: str) -> Supplier | None:
        """Return one supplier by id."""
        return self.suppliers.get(supplier_id)

    def get_claim(self, claim_id: str | None) -> Claim | None:
        """Return one claim by id."""
        if claim_id is None:
            return None
        return self.claims.get(claim_id)

    def current_rate_card(self, supplier_id: str) -> RateCard | None:
        """Return the first available rate card for a supplier."""
        candidates = [card for card in self.rate_cards.values() if card.supplier_id == supplier_id]
        return sorted(candidates, key=lambda card: card.effective_from, reverse=True)[0] if candidates else None

    def claim_authorisations(self, claim_id: str | None, supplier_id: str) -> list[Authorisation]:
        """Return authorisations for a claim and supplier."""
        if claim_id is None:
            return []
        return [
            auth
            for auth in self.authorisations.values()
            if auth.claim_id == claim_id and auth.supplier_id == supplier_id
        ]

    def update_invoice(self, invoice: Invoice, actor_id: str, event_type: str) -> None:
        """Persist an invoice mutation with audit."""
        before = self.invoices.get(invoice.id).to_dict() if self.invoices.get(invoice.id) else {}
        self.invoices[invoice.id] = invoice
        self.audit.append("invoice", invoice.id, event_type, "agent", actor_id, before, invoice.to_dict())

    def add_exception(self, record: ExceptionRecord) -> None:
        """Persist an exception with audit."""
        self.exceptions[record.id] = record
        self.audit.append(
            "exception", record.id, "exception_opened", "agent", "exception_router", {}, record.to_dict()
        )

    def add_dispute(self, record: DisputeQuery) -> None:
        """Persist a dispute query with audit."""
        self.disputes[record.id] = record
        self.audit.append(
            "dispute_query", record.id, "dispute_created", "agent", "settlement_dispute", {}, record.to_dict()
        )

    def add_redaction(self, invoice_id: str, record: RedactionLog) -> None:
        """Persist a redaction event with audit."""
        self.redactions.setdefault(invoice_id, []).append(record)
        self.audit.append("redaction_log", record.id, "pii_redacted", "agent", "redaction", {}, record.to_dict())

    def add_trace(self, invoice_id: str, trace: Any) -> None:
        """Persist an agent trace event."""
        self.traces.setdefault(invoice_id, []).append(trace)

    def add_notification(self, invoice_id: str, notification: Notification) -> None:
        """Persist a notification."""
        self.notifications.setdefault(invoice_id, []).append(notification)
        self.audit.append(
            "notification", notification.id, "notification_sent", "agent", "communications", {}, notification.to_dict()
        )
