"""Domain constants and dataclasses for automated invoice and outlay validation."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any
from typing import Literal

InvoiceStatus = Literal["Received", "Queried", "Approved", "Paid", "Awaiting information"]
SupplierType = Literal["repairer", "hire", "storage", "recovery"]
PaymentPath = Literal["integration", "rpa"]
# A claim either arrived in the nightly batch or was raised by a customer in the self-service portal.
ClaimOrigin = Literal["batch", "customer_portal"]
ClaimSeverity = Literal["minor", "moderate", "major", "total_loss"]
# Lifecycle of the back-office side of a claim, from triage through to the supplier invoices landing.
WorkflowStatus = Literal["draft", "awaiting_triage", "dispatched", "work_in_progress", "invoicing", "settled"]
WorkOrderStatus = Literal["dispatched", "accepted", "in_progress", "completed", "invoiced"]
WORK_ORDER_SEQUENCE: tuple[str, ...] = ("dispatched", "accepted", "in_progress", "completed", "invoiced")
# Services the triage agent can recommend, mapped to the supplier type that fulfils each one.
SERVICE_TO_SUPPLIER_TYPE: dict[str, str] = {
    "repair": "repairer",
    "hire": "hire",
    "storage": "storage",
    "recovery": "recovery",
}
ExceptionReason = Literal[
    "missing_or_invalid_identifiers",
    "failed_claim_matching",
    "disputed_or_out_of_tolerance",
    "high_value",
    "policy_or_coverage_ambiguity",
]
ServiceType = Literal["repair", "hire", "storage", "recovery"]

CANONICAL_STATUSES: tuple[str, ...] = ("Received", "Queried", "Approved", "Paid", "Awaiting information")
EXCEPTION_REASONS: tuple[str, ...] = (
    "missing_or_invalid_identifiers",
    "failed_claim_matching",
    "disputed_or_out_of_tolerance",
    "high_value",
    "policy_or_coverage_ambiguity",
)


@dataclass
class Supplier:
    """Supplier master-data record."""

    id: str
    name: str
    type: SupplierType
    contact: str
    payment_path: PaymentPath
    template_id: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class RateCardLine:
    """A line in an effective-dated supplier rate card."""

    id: str
    rate_card_id: str
    service_type: ServiceType
    unit: str
    rate_gbp: float
    max_units: int
    conditions: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class RateCard:
    """Effective-dated supplier rate card."""

    id: str
    supplier_id: str
    version: str
    effective_from: str
    effective_to: str
    review_due_date: str
    status: str
    lines: list[RateCardLine]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        payload = asdict(self)
        payload["lines"] = [line.to_dict() for line in self.lines]
        return payload


@dataclass
class Policy:
    """Insurance policy record."""

    id: str
    cover_type: str
    coverage_limits: dict[str, float]
    entitlements: list[str]
    excess_gbp: float
    effective_from: str
    effective_to: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Claim:
    """Invoice claim record."""

    id: str
    invoice_claim_ref: str
    policy_id: str
    customer_id: str
    incident_date: str
    status: str
    reserve_gbp: float
    paid_to_date_gbp: float
    # Everything below is additive with a default, so seed files and payloads written before the
    # customer intake feature still load through Claim(**item) without a migration.
    origin: ClaimOrigin = "batch"
    customer_name: str = ""
    # Policyholder identity, captured at portal sign-in rather than asked for by the assistant.
    contact_number: str = ""
    contact_email: str = ""
    address: str = ""
    insurance_number: str = ""
    vehicle_registration: str = ""
    # Who logged the claim and through which channel, for the back-office provenance panel.
    reported_by: str = ""
    report_channel: str = ""
    # Intake bookkeeping: which slot the assistant last asked for, and how many times it has had
    # to re-ask. Kept on the claim so the conversation survives a process restart.
    pending_slot: str = ""
    ask_attempts: int = 0
    incident_type: str = "collision"
    incident_location: str = ""
    description: str = ""
    severity: ClaimSeverity = "moderate"
    reported_at: str = ""
    # "", "drivable" or "not drivable"; drives whether recovery and storage are recommended.
    vehicle_drivable: str = ""
    # "yes" when the vehicle is at the policyholder's address, "no" when it is elsewhere. When it
    # is elsewhere the recovery agent needs incident_location, so the agent asks for it.
    vehicle_at_home: str = ""
    # "added" or "declined". Photographs are optional, so the assistant needs to know the customer
    # has been asked and answered, rather than waiting for an upload that is never coming.
    photos_decision: str = ""
    triage_summary: str = ""
    recommended_services: list[str] = field(default_factory=list)
    workflow_status: WorkflowStatus = "awaiting_triage"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Authorisation:
    """Prior authorisation for a supplier service on a claim."""

    id: str
    claim_id: str
    supplier_id: str
    service_type: ServiceType
    authorised_units: int
    authorised_value_gbp: float
    authorised_by: str
    authorised_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class InvoiceLine:
    """Line-level invoice charge and validation data."""

    id: str
    invoice_id: str
    line_no: int
    service_type: ServiceType
    service_date_from: str
    service_date_to: str
    units: int
    unit_rate_gbp: float
    amount_gbp: float
    vat_gbp: float
    extracted_confidence: float
    rate_card_line_id: str | None = None
    expected_amount_gbp: float = 0.0
    variance_gbp: float = 0.0
    variance_pct: float = 0.0
    tolerance_outcome: str = "within"
    validation_status: str = "pending"
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class ExceptionRecord:
    """Exception work-queue item."""

    id: str
    invoice_id: str
    reason: ExceptionReason
    explanation: str
    next_action: dict[str, Any]
    assigned_to: str
    priority: int
    opened_at: str
    resolved_at: str | None = None
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class DisputeQuery:
    """Line-specific supplier dispute query."""

    id: str
    invoice_id: str
    line_ids: list[str]
    query_text: str
    basis: str
    sent_at: str | None = None
    response_received_at: str | None = None
    outcome: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class RedactionLog:
    """What-and-why record for PII/GDPR redaction."""

    id: str
    invoice_id: str
    field_or_region: str
    rule_id: str
    reason: str
    redacted_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class AgentTrace:
    """Persisted agent decision replay event."""

    id: str
    invoice_id: str
    agent_name: str
    sequence: int
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    confidence: float
    prompt_version: str
    model_version: str
    started_at: str
    completed_at: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class AuditEvent:
    """Append-only hash-chained audit event."""

    id: str
    entity_type: str
    entity_id: str
    event_type: str
    actor: str
    actor_id: str
    before_json: dict[str, Any]
    after_json: dict[str, Any]
    occurred_at: str
    previous_hash: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Payment:
    """Payment workflow record."""

    id: str
    invoice_id: str
    amount_gbp: float
    path: PaymentPath
    authorised_by: str | None = None
    released_by: str | None = None
    released_at: str | None = None
    invoice_writeback_status: str = "pending"
    reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Notification:
    """Outbound notification record."""

    id: str
    invoice_id: str
    audience: str
    status_trigger: InvoiceStatus
    channel: str
    content: str
    sent_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Invoice:
    """Invoice aggregate."""

    id: str
    invoice_number: str
    supplier_id: str
    claim_id: str | None
    channel: str
    received_at: str
    document_uri: str
    redacted_document_uri: str | None
    status: InvoiceStatus
    gross_gbp: float
    net_gbp: float
    vat_gbp: float
    match_confidence: float
    match_method: str
    straight_through: bool
    lines: list[InvoiceLine]
    document_text: str
    layout_id: str
    seeded_outcome: str
    exception_reason: str | None = None
    redaction_summary: list[dict[str, Any]] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        payload = asdict(self)
        payload["lines"] = [line.to_dict() for line in self.lines]
        return payload


@dataclass
class ClaimAttachment:
    """A photograph or document attached to a claim.

    Images are held as data URIs rather than binary blobs: the prototype has no object store, and a
    data URI survives the in-memory repository and renders directly in the back-office gallery.
    """

    id: str
    claim_id: str
    label: str
    content_type: str
    data_uri: str
    uploaded_at: str
    source: str = "customer"
    ai_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class IntakeTurn:
    """One exchange in the customer intake conversation.

    The reasoning list is what the assistant decided on this turn. It is surfaced in the portal and
    in the back-office transcript so a handler can see why the agent asked what it asked.
    """

    id: str
    claim_id: str
    role: str
    text: str
    at: str
    reasoning: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class ClaimNotification:
    """A message pushed to the customer when something moves on their claim."""

    id: str
    claim_id: str
    title: str
    body: str
    kind: str
    at: str
    read: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class WorkOrder:
    """Instruction to a supplier to carry out one authorised service on a claim.

    The invoice that eventually arrives from the supplier is linked back through invoice_id, which
    is what joins the customer-raised claim to the existing invoice-to-pay validation pipeline.
    """

    id: str
    claim_id: str
    supplier_id: str
    service_type: str
    status: WorkOrderStatus
    authorised_units: int
    authorised_value_gbp: float
    dispatched_at: str
    dispatched_by: str
    accepted_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    invoice_id: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)

    def stage_index(self) -> int:
        """Return how far this work order has progressed through the status sequence."""
        return WORK_ORDER_SEQUENCE.index(self.status) if self.status in WORK_ORDER_SEQUENCE else 0


class DomainClock:
    """Clock helper kept as a class to conform to repository style."""

    @staticmethod
    def utc_now() -> str:
        """Return the current UTC time in ISO-8601 format."""
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
