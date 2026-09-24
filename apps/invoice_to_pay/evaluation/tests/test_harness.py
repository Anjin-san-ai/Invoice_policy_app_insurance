"""Tests that the evaluation harness measures rather than asserts its metrics."""

from apps.invoice_to_pay.evaluation.extraction_oracle import ExtractionOracle
from apps.invoice_to_pay.evaluation.harness import EvaluationHarness
from apps.invoice_to_pay.evaluation.metric_result import MEASURED
from apps.invoice_to_pay.evaluation.pii_oracle import PiiOracle

# Every metric named in specification section 17.1 must appear in the report.
EXPECTED_METRICS = {
    "document_classification_accuracy",
    "supplier_identification_accuracy",
    "field_extraction_accuracy",
    "extraction_confidence_ece",
    "pii_redaction_recall",
    "pii_redaction_false_positive_rate",
    "claim_matching_accuracy",
    "claim_matching_false_match_rate",
    "rerating_arithmetic_exact_match",
    "tolerance_decision_accuracy",
    "duplicate_detection_f1",
    "exception_reason_assignment_accuracy",
    "explanation_quality_rubric_score",
    "straight_through_rate",
    "audit_hash_chain_valid",
}


class TestEvaluationHarness:
    """Validate the harness reports real measurements against the specification targets."""

    SAMPLE = 300

    def test_report_covers_every_specification_metric(self) -> None:
        report = EvaluationHarness().run(sample_size=self.SAMPLE)
        assert set(report.get("metrics", {})) == EXPECTED_METRICS

    def test_every_metric_carries_a_target_and_a_method(self) -> None:
        report = EvaluationHarness().run(sample_size=self.SAMPLE)
        for name, metric in report.get("metrics", {}).items():
            assert metric.get("comparator") in (">=", "<=", "=="), name
            assert metric.get("target") is not None, name
            assert metric.get("method"), name
            assert metric.get("note"), name

    def test_no_metric_is_a_hardcoded_literal(self) -> None:
        """Guards the regression this harness was rewritten to fix.

        The previous version returned 12 of 15 metrics as constants, so the report passed without
        measuring anything. Running two different sample sizes must move at least one value.
        """
        small = EvaluationHarness().run(sample_size=120).get("metrics", {})
        large = EvaluationHarness().run(sample_size=600).get("metrics", {})
        differences = [
            name for name in EXPECTED_METRICS if small.get(name, {}).get("value") != large.get(name, {}).get("value")
        ]
        assert differences, "No metric changed with sample size, which suggests hardcoded values"

    def test_pass_flag_agrees_with_the_failed_metric_list(self) -> None:
        report = EvaluationHarness().run(sample_size=self.SAMPLE)
        failed = report.get("failed_metrics", [])
        assert report.get("passed") == (not failed)
        for name in failed:
            assert report.get("metrics", {}).get(name, {}).get("passed") is False

    def test_full_estate_meets_every_target(self) -> None:
        report = EvaluationHarness().run()
        assert report.get("passed") is True, f"Failing metrics: {report.get('failed_metrics')}"
        assert report.get("not_implemented") == []
        for name, metric in report.get("metrics", {}).items():
            assert metric.get("method") == MEASURED, name


class TestOracles:
    """Validate the independent oracles the harness measures against."""

    def test_extraction_oracle_parses_a_document(self) -> None:
        text = (
            "Invoice INV-000001 claim ICE-202600008 supplier Repairer Partner 001 "
            "supplier ref SREF-000001. Service repair. Net GBP 360.0. VAT GBP 72.0."
        )
        parsed = ExtractionOracle.parse(text)
        assert parsed is not None
        assert parsed.get("invoice_number") == "INV-000001"
        assert parsed.get("claim_ref") == "ICE-202600008"
        assert parsed.get("supplier_name") == "Repairer Partner 001"
        assert parsed.get("service_type") == "repair"
        assert parsed.get("net_gbp") == 360.0
        assert parsed.get("vat_gbp") == 72.0

    def test_extraction_oracle_reports_an_unparseable_document(self) -> None:
        assert ExtractionOracle.parse("not an invoice at all") is None

    def test_pii_oracle_finds_all_three_pii_kinds(self) -> None:
        text = "Driver: Alex Morgan, M1 1AE, 07123456789, alex.customer@example.com."
        kinds = {kind for _, _, kind in PiiOracle.spans(text)}
        assert kinds == {"email", "postcode", "phone"}

    def test_pii_oracle_finds_nothing_in_a_clean_document(self) -> None:
        assert PiiOracle.spans("Invoice INV-000001 claim ICE-202600008. Net GBP 360.0.") == []
