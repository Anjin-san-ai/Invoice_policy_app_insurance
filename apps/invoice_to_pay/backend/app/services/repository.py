"""In-memory repository backed by deterministic seed data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from apps.invoice_to_pay.backend.app.audit.audit_log import AuditLog
from apps.invoice_to_pay.backend.app.models.domain import Authorisation
from apps.invoice_to_pay.backend.app.models.domain import Claim
from apps.invoice_to_pay.backend.app.models.domain import ClaimAttachment
from apps.invoice_to_pay.backend.app.models.domain import ClaimNotification
from apps.invoice_to_pay.backend.app.models.domain import DisputeQuery
from apps.invoice_to_pay.backend.app.models.domain import DomainClock
from apps.invoice_to_pay.backend.app.models.domain import IntakeTurn
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
from apps.invoice_to_pay.backend.app.models.domain import WorkOrder
from apps.invoice_to_pay.data.generator.generate_seed import SeedDataGenerator

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = Path("apps/invoice_to_pay/data/seed/invoice_demo_data.json")
# Claims a customer raises at runtime are written here and replayed on the next boot. Without this
# a backend restart loses every claim submitted during a demo, which is exactly when it matters.
DEFAULT_RUNTIME_PATH = Path("apps/invoice_to_pay/data/runtime/portal_state.json")


class InvoiceRepository:
    """Simple in-memory repository for the prototype API and coded tools."""

    def __init__(self, data_path: Path = DEFAULT_DATA_PATH, runtime_path: Path = DEFAULT_RUNTIME_PATH) -> None:
        self.runtime_path = runtime_path
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
        # Customer-portal state. Attachments and transcripts are seeded for the demo claims and then
        # appended to at runtime as customers raise new claims.
        self.claim_attachments: dict[str, list[ClaimAttachment]] = {}
        self.intake_turns: dict[str, list[IntakeTurn]] = {}
        self.work_orders: dict[str, WorkOrder] = {}
        self.claim_notifications: dict[str, list[ClaimNotification]] = {}
        self._load_portal_records(data)
        # Snapshot what came from the seed, so persist() can write only the runtime delta.
        self._seeded_claim_ids = set(self.claims)
        self._seeded_invoice_ids = set(self.invoices)
        self._seeded_authorisation_ids = set(self.authorisations)
        self._seeded_work_order_ids = set(self.work_orders)
        self._load_runtime_state()
        # Seeded anomaly sets live at the top level of the seed file, not under metadata.
        self.duplicate_pairs: list[dict[str, str]] = data.get("duplicates", [])
        self.split_invoice_patterns: list[str] = data.get("split_invoice_patterns", [])
        self.value_outlier_numbers: list[str] = data.get("value_outliers", [])
        self._duplicate_originals = {pair.get("duplicate"): pair.get("original") for pair in self.duplicate_pairs}
        self.audit = AuditLog()

    def _load_portal_records(self, data: dict[str, Any]) -> None:
        """Load the portal-side records out of a seed or runtime payload."""
        for item in data.get("claim_attachments", []):
            record = ClaimAttachment(**item)
            self.claim_attachments.setdefault(record.claim_id, []).append(record)
        for item in data.get("intake_turns", []):
            turn = IntakeTurn(**item)
            self.intake_turns.setdefault(turn.claim_id, []).append(turn)
        for item in data.get("work_orders", []):
            order = WorkOrder(**item)
            self.work_orders[order.id] = order
        for item in data.get("claim_notifications", []):
            note = ClaimNotification(**item)
            self.claim_notifications.setdefault(note.claim_id, []).append(note)

    def _load_runtime_state(self) -> None:
        """Replay claims raised through the portal since the seed was written.

        A corrupt or half-written runtime file must not stop the API from booting, so a parse
        failure is logged loudly and the seeded estate is served on its own.
        """
        if not self.runtime_path.exists():
            return
        try:
            state = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Could not read runtime portal state at %s: %s", self.runtime_path, exc)
            return

        for item in state.get("claims", []):
            claim = Claim(**item)
            self.claims[claim.id] = claim
        for item in state.get("invoices", []):
            invoice = self._invoice_from_dict(item)
            self.invoices[invoice.id] = invoice
        for item in state.get("authorisations", []):
            authorisation = Authorisation(**item)
            self.authorisations[authorisation.id] = authorisation
        self._load_portal_records(state)
        logger.info(
            "Replayed %d portal claims and %d portal invoices from runtime state",
            len(state.get("claims", [])),
            len(state.get("invoices", [])),
        )

    def persist(self) -> None:
        """Write the runtime portal state to disk.

        Only records created after the seed are written: the 6 MB seed file is never rewritten.
        Persistence is best-effort — a read-only filesystem must not break the API.
        """
        runtime_claims = [
            claim.to_dict()
            for claim in self.claims.values()
            if claim.origin == "customer_portal" and claim.id not in self._seeded_claim_ids
        ]
        runtime_claim_ids = {claim.get("id") for claim in runtime_claims}
        payload = {
            "written_at": DomainClock.utc_now(),
            "claims": runtime_claims,
            "invoices": [
                invoice.to_dict()
                for invoice in self.invoices.values()
                if invoice.id not in self._seeded_invoice_ids
            ],
            "authorisations": [
                item.to_dict()
                for item in self.authorisations.values()
                if item.id not in self._seeded_authorisation_ids
            ],
            "claim_attachments": [
                item.to_dict()
                for claim_id, items in self.claim_attachments.items()
                if claim_id in runtime_claim_ids
                for item in items
            ],
            "intake_turns": [
                item.to_dict()
                for claim_id, items in self.intake_turns.items()
                if claim_id in runtime_claim_ids
                for item in items
            ],
            "work_orders": [
                order.to_dict() for order in self.work_orders.values() if order.id not in self._seeded_work_order_ids
            ],
            "claim_notifications": [
                item.to_dict() for items in self.claim_notifications.values() for item in items
            ],
        }
        try:
            self.runtime_path.parent.mkdir(parents=True, exist_ok=True)
            self.runtime_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("Could not persist runtime portal state to %s: %s", self.runtime_path, exc)

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

    # ------------------------------------------------------------------ customer portal

    def next_claim_id(self) -> str:
        """Return the next unused claim identifier."""
        highest = 0
        for claim_id in self.claims:
            tail = str(claim_id).split("-")[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"CLM-{highest + 1:05d}"

    def next_work_order_id(self) -> str:
        """Return the next unused work order identifier."""
        highest = 0
        for order_id in self.work_orders:
            tail = str(order_id).split("-")[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return f"WO-{highest + 1:05d}"

    def next_invoice_identifiers(self) -> tuple[str, str]:
        """Return the next unused (invoice id, invoice number) pair."""
        highest = 0
        for invoice_id in self.invoices:
            tail = str(invoice_id).split("-")[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        sequence = highest + 1
        return f"INVREC-{sequence:06d}", f"INV-{sequence:06d}"

    def policy_for_insurance_number(self, insurance_number: str) -> Policy | None:
        """Resolve the policy behind an insurance number the customer typed at sign-in.

        Seeded insurance numbers are INS-<policy digits>, so the digits are used to find the
        policy. An unrecognised number is not an error in the prototype: the claim still gets
        taken and the handler reconciles the policy later.
        """
        digits = "".join(character for character in (insurance_number or "") if character.isdigit())
        if not digits:
            return None
        return self.policies.get(f"POL-{int(digits):05d}")

    def any_policy(self) -> Policy | None:
        """Return one policy to attach a portal claim to.

        The prototype has no customer authentication, so a portal claim is bound to a seeded policy
        rather than to a verified policyholder.
        """
        for policy in self.policies.values():
            return policy
        return None

    def add_claim(self, claim: Claim, actor_id: str, event_type: str) -> None:
        """Persist a claim with audit."""
        self.claims[claim.id] = claim
        self.audit.append("claim", claim.id, event_type, "user", actor_id, {}, claim.to_dict())

    def add_claim_attachment(self, attachment: ClaimAttachment) -> None:
        """Persist a claim photograph with audit.

        The data URI is deliberately left out of the audit payload: the hash chain should record
        that an image arrived, not carry megabytes of base64 in every event.
        """
        self.claim_attachments.setdefault(attachment.claim_id, []).append(attachment)
        summary = {key: value for key, value in attachment.to_dict().items() if key != "data_uri"}
        self.audit.append("claim_attachment", attachment.id, "photo_uploaded", "user", "customer_portal", {}, summary)

    def add_intake_turn(self, turn: IntakeTurn) -> None:
        """Persist one conversation turn."""
        self.intake_turns.setdefault(turn.claim_id, []).append(turn)

    def add_work_order(self, order: WorkOrder) -> None:
        """Persist a work order with audit."""
        self.work_orders[order.id] = order
        self.audit.append(
            "work_order", order.id, "work_order_dispatched", "user", order.dispatched_by, {}, order.to_dict()
        )

    def add_authorisation(self, authorisation: Authorisation) -> None:
        """Persist an authorisation with audit."""
        self.authorisations[authorisation.id] = authorisation
        self.audit.append(
            "authorisation",
            authorisation.id,
            "authorisation_granted",
            "user",
            authorisation.authorised_by,
            {},
            authorisation.to_dict(),
        )

    def add_invoice(self, invoice: Invoice, actor_id: str, event_type: str) -> None:
        """Persist a newly arrived invoice with audit."""
        self.invoices[invoice.id] = invoice
        self.audit.append("invoice", invoice.id, event_type, "agent", actor_id, {}, invoice.to_dict())

    def add_claim_notification(self, claim_id: str, title: str, body: str, kind: str) -> ClaimNotification:
        """Push a customer-facing notification onto a claim."""
        existing = self.claim_notifications.setdefault(claim_id, [])
        note = ClaimNotification(
            id=f"{claim_id}-N{len(existing) + 1:03d}",
            claim_id=claim_id,
            title=title,
            body=body,
            kind=kind,
            at=DomainClock.utc_now(),
        )
        existing.append(note)
        logger.info("Notified claim %s: %s", claim_id, title)
        return note

    def claim_notification_list(self, claim_id: str) -> list[ClaimNotification]:
        """Return the notifications on one claim, newest last."""
        return list(self.claim_notifications.get(claim_id, []))

    def claim_work_orders(self, claim_id: str) -> list[WorkOrder]:
        """Return the work orders raised against one claim, oldest first."""
        return sorted(
            [order for order in self.work_orders.values() if order.claim_id == claim_id],
            key=lambda order: order.id,
        )

    def claim_invoices(self, claim_id: str) -> list[Invoice]:
        """Return the invoices attached to one claim."""
        return [invoice for invoice in self.invoices.values() if invoice.claim_id == claim_id]
