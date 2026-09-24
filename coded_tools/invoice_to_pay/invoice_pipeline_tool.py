"""Neuro SAN coded tool wrapper for the invoice-to-pay pipeline."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository

logger = logging.getLogger(__name__)

DEFAULT_INVOICE_ID = "INVREC-000001"


class InvoicePipelineTool(CodedTool):
    """Run the deterministic invoice-to-pay pipeline from a Neuro SAN agent.

    Each of the twelve agents in registries/apps/invoice_to_pay.hocon calls this one tool and asks
    for its own stage view, so the deterministic arithmetic stays out of the LLM while every agent
    still reports something specific to its stage.
    """

    # Which keys of the full pipeline result each stage agent is allowed to see. Keeping the views
    # narrow means a stage agent cannot accidentally summarise another stage's output as its own.
    STAGE_FIELDS: dict[str, tuple[str, ...]] = {
        "intake": (
            "invoice_id",
            "invoice_number",
            "channel",
            "supplier",
            "document_type",
            "identifiers_valid",
            "status",
        ),
        "extraction": (
            "invoice_id",
            "layout_id",
            "generic_extractor_used",
            "schema_version",
            "line_count",
            "min_field_confidence",
            "low_confidence_lines",
            "lines",
        ),
        "redaction": ("invoice_id", "redaction_count", "redactions", "redacted_document_uri"),
        "matching": ("invoice_id", "claim_id", "claim", "match_method", "match_confidence", "candidate_claims"),
        "rate_card": (
            "invoice_id",
            "rate_card_id",
            "rate_card_version",
            "rate_card_stale",
            "lines",
            "validation_summary",
        ),
        "entitlement": ("invoice_id", "claim", "policy", "authorisations", "validation_summary"),
        "tolerance": ("invoice_id", "outside_line_ids", "within_line_ids", "anomaly_flags", "high_value", "lines"),
        "settlement": ("invoice_id", "status", "decision"),
        "exception": ("invoice_id", "exception_reason", "exceptions"),
        "communications": ("invoice_id", "status", "notifications"),
        "payment": ("invoice_id", "status", "payment", "payment_path"),
    }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Process one invoice id, keeping sensitive payloads out of model-visible text."""
        return await asyncio.to_thread(self._process, args, sly_data)

    def _process(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Blocking processing implementation executed in a worker thread."""
        invoice_id = args.get("invoice_id") or sly_data.get("invoice_id") or DEFAULT_INVOICE_ID
        if not isinstance(invoice_id, str):
            return "Error: invoice_id must be a string."
        stage = args.get("stage") or "full"
        if not isinstance(stage, str):
            return "Error: stage must be a string."
        stage = stage.lower()
        if stage != "full" and stage not in self.STAGE_FIELDS:
            known = ", ".join(sorted(self.STAGE_FIELDS)) + ", full"
            return f"Error: unknown stage '{stage}'. Known stages: {known}."

        repository = InvoiceRepository()
        try:
            result = InvoicePipelineService(repository).process_invoice(invoice_id, actor_id="neuro-san-agent")
        except ValueError as exc:
            logger.warning("Invoice pipeline rejected invoice_id %s: %s", invoice_id, exc)
            return f"Error: {exc}"

        # The full state, including anything PII-bearing, travels in sly_data rather than in the
        # model-visible return value. See spec section 11.3.
        sly_data["invoice_state"] = result
        enriched = self._enrich(result, repository, invoice_id)
        if stage == "full":
            return self._summary(enriched)
        fields = self.STAGE_FIELDS.get(stage, ())
        view = {key: enriched.get(key) for key in fields if enriched.get(key) is not None}
        view["stage"] = stage
        logger.info("Invoice %s stage %s returned %d fields", invoice_id, stage, len(view))
        return view

    @staticmethod
    def _enrich(result: dict[str, Any], repository: InvoiceRepository, invoice_id: str) -> dict[str, Any]:
        """Add the derived, stage-oriented fields the agents report on."""
        enriched = dict(result)
        enriched["invoice_id"] = invoice_id
        lines = result.get("lines") or []
        supplier = result.get("supplier") or {}
        claim = result.get("claim") or {}
        confidences = [line.get("extracted_confidence", 1.0) for line in lines]
        threshold = float(repository.settings.get("min_extraction_confidence", 0.82))
        rate_card = repository.current_rate_card(result.get("supplier_id", ""))
        payment = next(
            (item.to_dict() for item in repository.payments.values() if item.invoice_id == invoice_id), None
        )
        validation = result.get("validation_summary") or {}
        outside = validation.get("outside_line_ids") or []
        layout_id = result.get("layout_id") or ""

        enriched["document_type"] = f"{supplier.get('type', 'unknown')}_invoice"
        enriched["identifiers_valid"] = result.get("seeded_outcome") != "missing_or_invalid_identifiers"
        enriched["generic_extractor_used"] = layout_id.startswith("long_tail")
        enriched["schema_version"] = "invoice-extraction-v1"
        enriched["line_count"] = len(lines)
        enriched["min_field_confidence"] = round(min(confidences), 3) if confidences else None
        enriched["low_confidence_lines"] = [
            line.get("id") for line in lines if line.get("extracted_confidence", 1.0) < threshold
        ]
        enriched["redaction_count"] = len(result.get("redactions") or [])
        enriched["candidate_claims"] = [
            candidate
            for record in result.get("exceptions") or []
            for candidate in (record.get("next_action") or {}).get("candidates", [])
        ]
        policy_id = claim.get("policy_id")
        policy = repository.policies.get(policy_id) if policy_id else None
        enriched["policy"] = policy.to_dict() if policy else None
        enriched["authorisations"] = [
            item.to_dict()
            for item in repository.claim_authorisations(result.get("claim_id"), result.get("supplier_id", ""))
        ]
        enriched["rate_card_id"] = rate_card.id if rate_card else None
        enriched["rate_card_version"] = rate_card.version if rate_card else None
        enriched["rate_card_stale"] = rate_card.status == "stale" if rate_card else None
        enriched["outside_line_ids"] = outside
        enriched["within_line_ids"] = [line.get("id") for line in lines if line.get("id") not in outside]
        enriched["anomaly_flags"] = InvoicePipelineTool._anomaly_flags(repository, result)
        enriched["high_value"] = result.get("gross_gbp", 0.0) > float(
            repository.settings.get("high_value_threshold_gbp", 5000.0)
        )
        enriched["payment"] = payment
        enriched["payment_path"] = (payment or {}).get("path") or supplier.get("payment_path")
        return enriched

    @staticmethod
    def _anomaly_flags(repository: InvoiceRepository, result: dict[str, Any]) -> dict[str, Any]:
        """Return the seeded duplicate and value-outlier flags for this invoice.

        The seed file's split-invoice patterns are not linked to individual invoice numbers, so no
        per-invoice split flag is claimed here rather than inventing one.
        """
        invoice_number = result.get("invoice_number") or ""
        duplicate_of = repository.duplicate_of(invoice_number)
        return {
            "duplicate_invoice": duplicate_of is not None,
            "duplicate_of_invoice_number": duplicate_of,
            "value_outlier": repository.is_value_outlier(invoice_number),
        }

    @staticmethod
    def _summary(enriched: dict[str, Any]) -> dict[str, Any]:
        """Return the compact whole-pipeline view used by the front man."""
        return {
            "invoice_id": enriched.get("invoice_id"),
            "status": enriched.get("status"),
            "decision": enriched.get("decision"),
            "exception_reason": enriched.get("exception_reason"),
            "affected_line_items": enriched.get("outside_line_ids"),
            "payment_path": enriched.get("payment_path"),
            "trace_count": len(enriched.get("trace") or []),
            "audit_replay_available": True,
        }
