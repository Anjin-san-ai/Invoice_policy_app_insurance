"""Tests for the shared invoice-to-pay coded tool and its per-stage views."""

import asyncio
from typing import Any

from coded_tools.invoice_to_pay.invoice_pipeline_tool import InvoicePipelineTool


class TestInvoicePipelineTool:
    """Validate the stage views each of the twelve agents relies on."""

    STRAIGHT_THROUGH_ID = "INVREC-000001"
    OUT_OF_TOLERANCE_ID = "INVREC-000071"
    # The seed generator injects PII into every eleventh invoice.
    PII_INVOICE_ID = "INVREC-000011"

    @staticmethod
    def _invoke(args: dict[str, Any]) -> Any:
        """Run the coded tool's async entry point and return its result."""
        sly_data: dict[str, Any] = {}
        result = asyncio.run(InvoicePipelineTool().async_invoke(args, sly_data))
        return result, sly_data

    def test_full_stage_returns_the_front_man_summary(self) -> None:
        result, sly_data = self._invoke({"invoice_id": self.STRAIGHT_THROUGH_ID})
        assert result.get("status") == "Paid"
        assert result.get("decision", {}).get("decision") == "AUTO_APPROVE"
        assert result.get("audit_replay_available") is True
        # Sensitive full state must travel in sly_data, not the model-visible return value.
        assert "invoice_state" in sly_data

    def test_every_declared_stage_returns_a_scoped_view(self) -> None:
        for stage in InvoicePipelineTool.STAGE_FIELDS:
            result, _ = self._invoke({"invoice_id": self.OUT_OF_TOLERANCE_ID, "stage": stage})
            assert isinstance(result, dict), f"Stage {stage} did not return a mapping"
            assert result.get("stage") == stage
            assert result.get("invoice_id") == self.OUT_OF_TOLERANCE_ID

    def test_tolerance_stage_names_only_the_offending_lines(self) -> None:
        result, _ = self._invoke({"invoice_id": self.OUT_OF_TOLERANCE_ID, "stage": "tolerance"})
        outside = result.get("outside_line_ids", [])
        assert outside, "Expected at least one line outside tolerance"
        assert all(line_id.startswith(self.OUT_OF_TOLERANCE_ID) for line_id in outside)
        assert set(outside).isdisjoint(result.get("within_line_ids", []))

    def test_redaction_stage_reports_what_and_why(self) -> None:
        result, _ = self._invoke({"invoice_id": self.PII_INVOICE_ID, "stage": "redaction"})
        assert result.get("redaction_count", 0) > 0
        for record in result.get("redactions", []):
            assert record.get("rule_id")
            assert record.get("reason")

    def test_unknown_stage_is_reported_not_silently_ignored(self) -> None:
        result, _ = self._invoke({"invoice_id": self.STRAIGHT_THROUGH_ID, "stage": "not_a_stage"})
        assert isinstance(result, str)
        assert "unknown stage" in result.lower()

    def test_unknown_invoice_is_reported(self) -> None:
        result, _ = self._invoke({"invoice_id": "INVREC-999999"})
        assert isinstance(result, str)
        assert "Error" in result
