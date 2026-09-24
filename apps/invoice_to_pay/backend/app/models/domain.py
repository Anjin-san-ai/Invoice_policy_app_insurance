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
    """ICE claim record."""

    id: str
    ice_claim_ref: str
    policy_id: str
    customer_id: str
    incident_date: str
    status: str
    reserve_gbp: float
    paid_to_date_gbp: float

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
    ice_writeback_status: str = "pending"
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


class DomainClock:
    """Clock helper kept as a class to conform to repository style."""

    @staticmethod
    def utc_now() -> str:
        """Return the current UTC time in ISO-8601 format."""
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
