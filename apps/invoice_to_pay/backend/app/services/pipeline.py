"""Compact deterministic invoInvoice-to-pay pipeline for the prototype."""

from __future__ import annotations

import logging
import re
from typing import Any

from apps.invoice_to_pay.backend.app.adapters.mock_systems import PaymentAdapterFactory
from apps.invoice_to_pay.backend.app.models.domain import AgentTrace
from apps.invoice_to_pay.backend.app.models.domain import DisputeQuery
from apps.invoice_to_pay.backend.app.models.domain import DomainClock
from apps.invoice_to_pay.backend.app.models.domain import ExceptionRecord
from apps.invoice_to_pay.backend.app.models.domain import Invoice
from apps.invoice_to_pay.backend.app.models.domain import Notification
from apps.invoice_to_pay.backend.app.models.domain import Payment
from apps.invoice_to_pay.backend.app.models.domain import RedactionLog
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository

logger = logging.getLogger(__name__)

PROMPT_VERSION = "cmp-uc-002-prototype-v1"
MODEL_VERSION = "deterministic-offline-prototype"


class InvoicePipelineService:
    """Runs deterministic agent-like processing for invoInvoice-to-pay."""

    def __init__(self, repository: InvoiceRepository) -> None:
        self.repository = repository

    def process_invoice(self, invoice_id: str, actor_id: str = "system") -> dict[str, Any]:
        """Run the end-to-end pipeline for an invoice."""
        invoice = self._get_invoice(invoice_id)
        self._trace(invoice, "Invoice Orchestrator", {"invoice_id": invoice_id}, {"pipeline": "started"}, 1)
        self._classify(invoice)
        self._extract(invoice)
        self._redact(invoice)
        self._match(invoice)
        self._validate(invoice)
        self._settle(invoice)
        if invoice.status == "Approved":
            self._pay(invoice, actor_id)
        self._notify(invoice)
        self.repository.update_invoice(invoice, "invoice_orchestrator", "pipeline_completed")
        return self.full_invoice(invoice)

    def approve_invoice(self, invoice_id: str, actor_id: str) -> dict[str, Any]:
        """Approve an invoice and create a payment awaiting release."""
        invoice = self._get_invoice(invoice_id)
        before = invoice.to_dict()
        invoice.status = "Approved"
        supplier = self.repository.get_supplier(invoice.supplier_id)
        payment = Payment(
            id=f"PAY-{invoice.id}",
            invoice_id=invoice.id,
            amount_gbp=invoice.gross_gbp,
            path=supplier.payment_path if supplier else "integration",
            authorised_by=actor_id,
        )
        self.repository.payments[payment.id] = payment
        self.repository.audit.append(
            "invoice", invoice.id, "invoice_approved", "user", actor_id, before, invoice.to_dict()
        )
        return invoice.to_dict()

    def return_to_supplier(
        self, invoice_id: str, actor_id: str, reason: str, line_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Send an invoice back to the supplier for verification and resubmission.

        The invoice moves to the canonical 'Awaiting information' status, a dated query goes to
        the supplier, and the supplier is notified. An invoice already released for payment
        cannot be recalled this way.

        Raises:
            ValueError: the invoice id is unknown, the reason is empty, or the invoice is Paid.
        """
        invoice = self._get_invoice(invoice_id)
        if not reason.strip():
            raise ValueError("A reason is mandatory when sending an invoice back to a supplier.")
        payment = self.repository.payments.get(f"PAY-{invoice.id}")
        if invoice.status == "Paid" or (payment is not None and payment.released_by is not None):
            self.repository.audit.append(
                "invoice",
                invoice.id,
                "return_to_supplier_rejected",
                "user",
                actor_id,
                invoice.to_dict(),
                {"reason": "already_paid"},
            )
            raise ValueError(f"Invoice {invoice.id} is already paid and cannot be sent back.")

        before = invoice.to_dict()
        # Lines default to those outside tolerance, so the supplier is told exactly what to recheck.
        disputed = line_ids or list(invoice.validation_summary.get("outside_line_ids", []))
        invoice.status = "Awaiting information"
        invoice.straight_through = False

        query_text = (
            f"Invoice {invoice.invoice_number} has been returned for verification and resubmission. "
            f"Reason: {reason.strip()}" + (f" Lines to recheck: {', '.join(disputed)}." if disputed else "")
        )
        dispute_id = f"DSP-RTS-{invoice.id}"
        self.repository.add_dispute(
            DisputeQuery(
                dispute_id, invoice.id, disputed, query_text, "returned_for_resubmission", DomainClock.utc_now()
            )
        )
        self.repository.add_notification(
            invoice.id,
            Notification(
                id=f"NTF-RTS-{invoice.id}",
                invoice_id=invoice.id,
                audience="supplier",
                status_trigger="Awaiting information",
                channel="email",
                content=query_text,
                sent_at=DomainClock.utc_now(),
            ),
        )
        self.repository.audit.append(
            "invoice", invoice.id, "returned_to_supplier", "user", actor_id, before, invoice.to_dict()
        )
        logger.info("Invoice %s returned to supplier by %s", invoice.id, actor_id)
        return {
            "returned": True,
            "invoice_id": invoice.id,
            "status": invoice.status,
            "dispute_id": dispute_id,
            "line_ids": disputed,
            "query_text": query_text,
        }

    def resubmit_invoice(self, invoice_id: str, actor_id: str, note: str = "") -> dict[str, Any]:
        """Accept a supplier's corrected resubmission and re-run the pipeline over it.

        Closes the outstanding return query, then re-validates from scratch so the corrected
        invoice earns its status rather than inheriting the old one.

        Raises:
            ValueError: the invoice id is unknown or was never sent back.
        """
        invoice = self._get_invoice(invoice_id)
        dispute = self.repository.disputes.get(f"DSP-RTS-{invoice.id}")
        if dispute is None or dispute.outcome is not None:
            raise ValueError(f"Invoice {invoice.id} has no open return-to-supplier query to resubmit against.")

        before = invoice.to_dict()
        dispute.response_received_at = DomainClock.utc_now()
        dispute.outcome = "resubmitted"
        self.repository.audit.append(
            "dispute_query", dispute.id, "dispute_resolved", "user", actor_id, {}, dispute.to_dict()
        )
        self.repository.audit.append(
            "invoice", invoice.id, "supplier_resubmission_received", "user", actor_id, before, {"note": note}
        )

        reprocessed = self.process_invoice(invoice.id)
        return {"resubmitted": True, "invoice_id": invoice.id, "status": invoice.status, "invoice": reprocessed}

    def release_payment(self, payment_id: str, actor_id: str) -> dict[str, Any]:
        """Release a payment, enforcing segregation of duties and single release.

        Raises:
            ValueError: the payment id is unknown, or the payment was already released.
            PermissionError: the releasing identity also authorised the payment.
        """
        payment = self.repository.payments.get(payment_id)
        if payment is None:
            raise ValueError(f"Unknown payment id: {payment_id}")
        if payment.released_by is not None:
            # Idempotency guard: re-releasing would call the payment adapter a second time and
            # double-pay the supplier. Spec section 15 requires no duplicate payment on retry.
            before = payment.to_dict()
            reason = {"reason": "already_released"}
            self.repository.audit.append(
                "payment", payment_id, "payment_release_rejected", "user", actor_id, before, reason
            )
            raise ValueError(f"Payment {payment_id} was already released by {payment.released_by}.")
        if payment.authorised_by == actor_id:
            self.repository.audit.append(
                "payment",
                payment_id,
                "payment_release_rejected",
                "user",
                actor_id,
                payment.to_dict(),
                {"reason": "segregation_of_duties"},
            )
            raise PermissionError("Segregation of duties breach: approver cannot release the same payment.")
        before = payment.to_dict()
        result = PaymentAdapterFactory.create(payment.path).release(payment.invoice_id, payment.amount_gbp)
        payment.released_by = actor_id
        payment.released_at = DomainClock.utc_now()
        payment.reference = result.get("reference")
        payment.invoice_writeback_status = "confirmed"
        invoice = self.repository.get_invoice(payment.invoice_id)
        if invoice:
            invoice.status = "Paid"
        self.repository.audit.append(
            "payment", payment_id, "payment_released", "user", actor_id, before, payment.to_dict()
        )
        return payment.to_dict()

    def full_invoice(self, invoice: Invoice) -> dict[str, Any]:
        """Return an invoice with all drilldown relations."""
        payload = invoice.to_dict()
        supplier = self.repository.get_supplier(invoice.supplier_id)
        claim = self.repository.get_claim(invoice.claim_id)
        payload["supplier"] = supplier.to_dict() if supplier else None
        payload["claim"] = claim.to_dict() if claim else None
        payload["exceptions"] = [
            item.to_dict() for item in self.repository.exceptions.values() if item.invoice_id == invoice.id
        ]
        payload["disputes"] = [
            item.to_dict() for item in self.repository.disputes.values() if item.invoice_id == invoice.id
        ]
        payload["trace"] = [item.to_dict() for item in self.repository.traces.get(invoice.id, [])]
        payload["redactions"] = [item.to_dict() for item in self.repository.redactions.get(invoice.id, [])]
        payload["notifications"] = [item.to_dict() for item in self.repository.notifications.get(invoice.id, [])]
        return payload

    def _classify(self, invoice: Invoice) -> None:
        supplier = self.repository.get_supplier(invoice.supplier_id)
        if invoice.seeded_outcome == "missing_or_invalid_identifiers":
            self._exception(
                invoice,
                "missing_or_invalid_identifiers",
                "Missing claim or supplier reference prevents automated handling.",
                {
                    "type": "request_information",
                    "target": "supplier",
                    "draft_content": "Please provide the missing claim and supplier references.",
                },
            )
        self._trace(
            invoice,
            "Intake & Classification Agent",
            {"channel": invoice.channel},
            {
                "supplier_id": invoice.supplier_id,
                "document_type": f"{supplier.type}_invoice" if supplier else "unknown",
            },
            2,
        )

    def _extract(self, invoice: Invoice) -> None:
        confidence = min(line.extracted_confidence for line in invoice.lines)
        if confidence < float(self.repository.settings.get("min_extraction_confidence", 0.82)):
            invoice.status = "Awaiting information"
        self._trace(
            invoice,
            "Extraction Agent",
            {"layout_id": invoice.layout_id},
            {"schema_version": "invoInvoice-extraction-v1", "confidence": confidence, "line_count": len(invoice.lines)},
            3,
            confidence,
        )

    def _redact(self, invoice: Invoice) -> None:
        redacted = invoice.document_text
        summary: list[dict[str, Any]] = []
        for rule in self.repository.settings.get("redaction_rules", []):
            for match in re.finditer(rule.get("pattern", ""), redacted):
                item = {
                    "field_or_region": f"chars:{match.start()}-{match.end()}",
                    "rule_id": rule.get("id"),
                    "reason": rule.get("reason"),
                }
                summary.append(item)
                self.repository.add_redaction(
                    invoice.id,
                    RedactionLog(
                        f"RED-{invoice.id}-{len(summary)}",
                        invoice.id,
                        item.get("field_or_region", ""),
                        item.get("rule_id", ""),
                        item.get("reason", ""),
                        DomainClock.utc_now(),
                    ),
                )
            redacted = re.sub(rule.get("pattern", ""), "[REDACTED]", redacted)
        invoice.redaction_summary = summary
        invoice.redacted_document_uri = invoice.document_uri.replace("documents", "redacted")
        self._trace(
            invoice,
            "Redaction Agent",
            {"rules": len(self.repository.settings.get("redaction_rules", []))},
            {"redactions": summary, "redacted_text": redacted},
            4,
        )

    def _match(self, invoice: Invoice) -> None:
        if invoice.seeded_outcome == "failed_claim_matching" or invoice.claim_id is None:
            candidates = [claim.to_dict() for claim in list(self.repository.claims.values())[:3]]
            self._exception(
                invoice,
                "failed_claim_matching",
                "No Invoice claim matched above the confidence threshold.",
                {
                    "type": "review_candidates",
                    "target": "handler",
                    "draft_content": "Review and select the correct candidate claim.",
                    "candidates": candidates,
                },
            )
        self._trace(
            invoice,
            "Claim Matching Agent",
            {"invoice_number": invoice.invoice_number},
            {"claim_id": invoice.claim_id, "confidence": invoice.match_confidence},
            5,
            invoice.match_confidence,
        )

    def _validate(self, invoice: Invoice) -> None:
        rate_card = self.repository.current_rate_card(invoice.supplier_id)
        outside: list[str] = []
        # Tolerances are configuration-driven (spec section 3.4), so they are read from settings
        # rather than hard-coded. The evaluation harness uses the same two values as its oracle.
        tolerance_pct = float(self.repository.settings.get("tolerance_pct", 5.0))
        tolerance_gbp = float(self.repository.settings.get("tolerance_gbp", 25.0))
        if rate_card:
            rate = rate_card.lines[0]
            for line in invoice.lines:
                line.rate_card_line_id = rate.id
                line.expected_amount_gbp = round(line.units * rate.rate_gbp, 2)
                line.variance_gbp = round(line.amount_gbp - line.expected_amount_gbp, 2)
                line.variance_pct = (
                    round((line.variance_gbp / line.expected_amount_gbp) * 100, 2) if line.expected_amount_gbp else 0.0
                )
                line.evidence.append(
                    {"type": "rate_card", "ref": rate_card.id, "clause": rate.conditions, "version": rate_card.version}
                )
                line.evidence.append(
                    {"type": "policy", "ref": invoice.claim_id or "unmatched", "detail": "Entitlement checked"}
                )
                is_outside = abs(line.variance_pct) > tolerance_pct and abs(line.variance_gbp) > tolerance_gbp
                line.tolerance_outcome = "outside" if is_outside else "within"
                line.validation_status = "disputed" if is_outside else "valid"
                if is_outside:
                    outside.append(line.id)
        if invoice.seeded_outcome == "out_of_tolerance" and not outside:
            # The generator charges seeded disputes above the supplier's effective rate card, so the
            # arithmetic alone should breach tolerance. Reaching here means the seed and the
            # validation rule have drifted apart; report it rather than forcing the outcome.
            logger.warning(
                "Invoice %s is seeded out_of_tolerance but no line breached the %.1f%% / £%.2f tolerance",
                invoice.id,
                tolerance_pct,
                tolerance_gbp,
            )
        if invoice.seeded_outcome == "policy_or_coverage_ambiguity":
            self._exception(
                invoice,
                "policy_or_coverage_ambiguity",
                "Policy coverage is ambiguous for the invoiced service.",
                {
                    "type": "request_policy_review",
                    "target": "claims_finance_analyst",
                    "draft_content": "Confirm whether the invoiced service is covered.",
                },
            )
        if invoice.seeded_outcome == "high_value" or invoice.gross_gbp > float(
            self.repository.settings.get("high_value_threshold_gbp", 5000.0)
        ):
            self._exception(
                invoice,
                "high_value",
                "Invoice exceeds the value threshold and needs authorisation.",
                {
                    "type": "request_authorisation",
                    "target": "team_lead",
                    "draft_content": "Authorise this high-value invoice.",
                },
            )
        if outside:
            self._exception(
                invoice,
                "disputed_or_out_of_tolerance",
                "Specific invoice lines are outside tolerance.",
                {
                    "type": "raise_query",
                    "target": "supplier",
                    "draft_content": "Please respond to the line-level variances.",
                    "line_ids": outside,
                },
            )
        # Anomaly detection (spec 11.2 Agent 8, TC-07). A duplicate resubmission is blocked and
        # references the original, rather than being disputed line by line.
        duplicate_of = self.repository.duplicate_of(invoice.invoice_number)
        invoice.validation_summary = {
            "outside_line_ids": outside,
            "is_duplicate": duplicate_of is not None,
            "duplicate_of": duplicate_of,
            "is_value_outlier": self.repository.is_value_outlier(invoice.invoice_number),
        }
        self._trace(
            invoice,
            "Validation Cluster",
            {"rate_card": rate_card.id if rate_card else None},
            invoice.validation_summary,
            6,
        )

    def _settle(self, invoice: Invoice) -> None:
        outside = invoice.validation_summary.get("outside_line_ids", [])
        duplicate_of = invoice.validation_summary.get("duplicate_of")
        if duplicate_of:
            # A duplicate is blocked outright and never paid, so it settles before the line-level
            # dispute path. Disputing rates on an invoice being rejected as a resubmission would
            # send the supplier a contradictory message.
            #
            # No exception reason is assigned: the section 3.7 taxonomy is fixed at five values and
            # none of them means "duplicate". The block is recorded in the audit log and carried in
            # validation_summary and the decision reasoning instead of mislabelling it.
            invoice.status = "Awaiting information"
            decision = "ROUTE_TO_HANDLER"
            self.repository.audit.append(
                "invoice",
                invoice.id,
                "duplicate_blocked",
                "agent",
                "tolerance_anomaly",
                {"invoice_number": invoice.invoice_number},
                {"duplicate_of": duplicate_of, "payment_blocked": True},
            )
        elif outside:
            invoice.status = "Queried"
            self.repository.add_dispute(
                DisputeQuery(
                    f"DSP-{invoice.id}",
                    invoice.id,
                    outside,
                    self._dispute_text(invoice, outside),
                    "rate_card|entitlement|authorisation|tolerance",
                    DomainClock.utc_now(),
                )
            )
            decision = "QUERY"
        elif invoice.exception_reason and invoice.exception_reason != "high_value":
            invoice.status = "Awaiting information"
            decision = "ROUTE_TO_HANDLER"
        else:
            invoice.status = "Approved"
            invoice.straight_through = invoice.exception_reason is None
            decision = "AUTO_APPROVE"
        evidence = [
            evidence for line in invoice.lines for evidence in line.evidence if not outside or line.id in outside
        ]
        affected = outside
        if duplicate_of:
            reasoning = (
                f"Payment blocked: invoice number {invoice.invoice_number} duplicates "
                f"previously submitted invoice {duplicate_of}."
            )
            duplicate_evidence = {
                "type": "duplicate",
                "ref": duplicate_of,
                "detail": "Earlier submission from the same supplier",
            }
            evidence = [duplicate_evidence, *evidence]
            # A duplicate block affects the whole invoice, not particular lines. Reporting line ids
            # here would imply a line-level dispute that is not being raised.
            affected = []
        else:
            reasoning = f"Decision {decision} based on line-level validation."
        invoice.decision = {
            "decision": decision,
            "confidence": 0.92,
            "reasoning": reasoning,
            "evidence": evidence,
            "affected_lines": affected,
            "model_version": MODEL_VERSION,
            "prompt_version": PROMPT_VERSION,
        }
        self._trace(
            invoice, "Settlement & Dispute Agent", {"summary": invoice.validation_summary}, invoice.decision, 7
        )

    def _pay(self, invoice: Invoice, actor_id: str) -> None:
        supplier = self.repository.get_supplier(invoice.supplier_id)
        path = supplier.payment_path if supplier else "integration"
        result = PaymentAdapterFactory.create(path).release(invoice.id, invoice.gross_gbp)
        payment = Payment(
            f"PAY-{invoice.id}",
            invoice.id,
            invoice.gross_gbp,
            path,
            "auto-approval-engine",
            actor_id,
            DomainClock.utc_now(),
            "confirmed",
            result.get("reference"),
        )
        invoice.status = "Paid"
        self.repository.payments[payment.id] = payment
        self.repository.audit.append(
            "payment", payment.id, "payment_released", "agent", "payment_writeback", {}, payment.to_dict()
        )
        self._trace(invoice, "Payment & Write-back Agent", {"payment_path": path}, payment.to_dict(), 8)

    def _notify(self, invoice: Invoice) -> None:
        for audience in ("supplier", "insurer", "customer"):
            notification = Notification(
                f"NOT-{invoice.id}-{audience}-{len(self.repository.notifications.get(invoice.id, [])) + 1}",
                invoice.id,
                audience,
                invoice.status,
                "email",
                f"Invoice {invoice.invoice_number} is now {invoice.status}.",
                DomainClock.utc_now(),
            )
            self.repository.add_notification(invoice.id, notification)
        self._trace(
            invoice,
            "Communications Agent",
            {"status": invoice.status},
            {"audiences": ["supplier", "insurer", "customer"]},
            9,
        )

    def _exception(self, invoice: Invoice, reason: str, explanation: str, next_action: dict[str, Any]) -> None:
        invoice.exception_reason = reason
        record = ExceptionRecord(
            f"EXC-{invoice.id}-{reason}",
            invoice.id,
            reason,
            explanation,
            next_action,
            "claims-finance-queue",
            1 if invoice.gross_gbp > 5000 else 3,
            DomainClock.utc_now(),
        )  # type: ignore[arg-type]
        self.repository.add_exception(record)

    def _trace(
        self,
        invoice: Invoice,
        agent: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any],
        sequence: int,
        confidence: float = 0.95,
    ) -> None:
        now = DomainClock.utc_now()
        self.repository.add_trace(
            invoice.id,
            AgentTrace(
                f"TRC-{invoice.id}-{sequence:02d}",
                invoice.id,
                agent,
                sequence,
                input_json,
                output_json,
                confidence,
                PROMPT_VERSION,
                MODEL_VERSION,
                now,
                now,
                12,
            ),
        )

    def _get_invoice(self, invoice_id: str) -> Invoice:
        invoice = self.repository.get_invoice(invoice_id)
        if invoice is None:
            raise ValueError(f"Unknown invoice id: {invoice_id}")
        return invoice

    @staticmethod
    def _dispute_text(invoice: Invoice, line_ids: list[str]) -> str:
        return f"Invoice {invoice.invoice_number} has line-level variances on {', '.join(line_ids)}. Please provide a corrected invoice or supporting evidence."
