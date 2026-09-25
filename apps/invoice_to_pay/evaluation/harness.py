"""Evaluation harness for CMP-UC-002 prototype metrics.

Every metric in specification section 17.1 is measured against an independent oracle rather than
asserted. Where a capability does not exist yet the metric is reported as `not_implemented` with its
real value, so the summary cannot pass by omission.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.invoice_to_pay.backend.app.models.domain import EXCEPTION_REASONS  # noqa: E402
from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService  # noqa: E402
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository  # noqa: E402
from apps.invoice_to_pay.evaluation.extraction_oracle import FIELD_NAMES  # noqa: E402
from apps.invoice_to_pay.evaluation.extraction_oracle import ExtractionOracle  # noqa: E402
from apps.invoice_to_pay.evaluation.metric_result import MEASURED  # noqa: E402
from apps.invoice_to_pay.evaluation.metric_result import NOT_IMPLEMENTED  # noqa: E402
from apps.invoice_to_pay.evaluation.metric_result import MetricResult  # noqa: E402
from apps.invoice_to_pay.evaluation.pii_oracle import PiiOracle  # noqa: E402

logger = logging.getLogger(__name__)

# Invoice service type in the document text maps to the supplier type that issues it, which is what
# the Intake and Classification Agent reports as the document type.
SERVICE_TO_SUPPLIER_TYPE = {"repair": "repairer", "hire": "hire", "storage": "storage", "recovery": "recovery"}

# Seeded outcome label to the exception reason the router is expected to assign.
OUTCOME_TO_REASON = {
    "out_of_tolerance": "disputed_or_out_of_tolerance",
    "failed_claim_matching": "failed_claim_matching",
    "missing_or_invalid_identifiers": "missing_or_invalid_identifiers",
    "high_value": "high_value",
    "policy_or_coverage_ambiguity": "policy_or_coverage_ambiguity",
}

ECE_BIN_COUNT = 10


class EvaluationHarness:
    """Run deterministic offline evaluations against the synthetic labelled set."""

    def __init__(self) -> None:
        self.repository = InvoiceRepository()
        self.pipeline = InvoicePipelineService(self.repository)

    def run(self, sample_size: int | None = None) -> dict[str, Any]:
        """Process a sample of invoices and return every measured metric."""
        invoice_ids = list(self.repository.invoices)
        if sample_size is not None:
            invoice_ids = invoice_ids[:sample_size]
        for invoice_id in invoice_ids:
            self.pipeline.process_invoice(invoice_id)
        invoices = [self.repository.get_invoice(invoice_id) for invoice_id in invoice_ids]
        evaluated = [invoice for invoice in invoices if invoice is not None]
        logger.info("Evaluating %d invoices", len(evaluated))

        metrics = [
            *self._classification_metrics(evaluated),
            *self._extraction_metrics(evaluated),
            *self._redaction_metrics(evaluated),
            *self._matching_metrics(evaluated),
            self._rerating_metric(evaluated),
            self._tolerance_metric(evaluated),
            self._duplicate_metric(evaluated),
            self._exception_reason_metric(evaluated),
            self._explanation_metric(evaluated),
            self._straight_through_metric(evaluated),
            self._audit_metric(),
        ]
        failed = [metric.name for metric in metrics if not metric.passed]
        return {
            "sample_size": len(evaluated),
            "metrics": {metric.name: metric.to_dict() for metric in metrics},
            "failed_metrics": failed,
            "not_implemented": [metric.name for metric in metrics if metric.method == NOT_IMPLEMENTED],
            "passed": not failed,
        }

    @staticmethod
    def _score(
        name: str, value: float | bool, target: float | bool, comparator: str, method: str = MEASURED, note: str = ""
    ) -> MetricResult:
        """Build a metric result, evaluating the value against its target."""
        if comparator == ">=":
            passed = float(value) >= float(target)
        elif comparator == "<=":
            passed = float(value) <= float(target)
        elif comparator == "==":
            passed = value == target
        else:
            raise ValueError(f"Unknown comparator for metric {name}: {comparator}")
        return MetricResult(
            name=name, value=value, target=target, comparator=comparator, passed=passed, method=method, note=note
        )

    def _oracle_for(self, invoice: Any) -> dict[str, Any] | None:
        """Return the parsed document-text ground truth for an invoice."""
        return ExtractionOracle.parse(invoice.document_text)

    def _intake_output(self, invoice: Any) -> dict[str, Any]:
        """Return the Intake and Classification Agent's recorded output for an invoice."""
        for trace in self.repository.traces.get(invoice.id, []):
            if trace.agent_name == "Intake & Classification Agent":
                return trace.output_json
        return {}

    def _classification_metrics(self, invoices: list[Any]) -> list[MetricResult]:
        """Score document classification and supplier identification against the document text."""
        doc_checked = doc_correct = sup_checked = sup_correct = 0
        names_to_id = {supplier.name: supplier.id for supplier in self.repository.suppliers.values()}
        for invoice in invoices:
            oracle = self._oracle_for(invoice)
            if oracle is None:
                continue
            output = self._intake_output(invoice)
            expected_type = SERVICE_TO_SUPPLIER_TYPE.get(oracle.get("service_type", ""))
            if expected_type is not None:
                doc_checked += 1
                if output.get("document_type") == f"{expected_type}_invoice":
                    doc_correct += 1
            expected_supplier = names_to_id.get(oracle.get("supplier_name", ""))
            if expected_supplier is not None:
                sup_checked += 1
                if output.get("supplier_id") == expected_supplier:
                    sup_correct += 1
        return [
            self._score(
                "document_classification_accuracy",
                round(doc_correct / doc_checked, 4) if doc_checked else 0.0,
                0.97,
                ">=",
                note=f"Document type compared against the service type parsed from {doc_checked} documents.",
            ),
            self._score(
                "supplier_identification_accuracy",
                round(sup_correct / sup_checked, 4) if sup_checked else 0.0,
                0.98,
                ">=",
                note=f"Supplier id compared against the supplier name parsed from {sup_checked} documents.",
            ),
        ]

    def _extraction_metrics(self, invoices: list[Any]) -> list[MetricResult]:
        """Score field-level extraction accuracy and confidence calibration."""
        fields_checked = fields_correct = 0
        bins: list[list[tuple[float, bool]]] = [[] for _ in range(ECE_BIN_COUNT)]
        for invoice in invoices:
            oracle = self._oracle_for(invoice)
            if oracle is None:
                continue
            claim = self.repository.get_claim(invoice.claim_id)
            supplier = self.repository.get_supplier(invoice.supplier_id)
            actual = {
                "invoice_number": invoice.invoice_number,
                "claim_ref": claim.invoice_claim_ref if claim else None,
                "supplier_name": supplier.name if supplier else None,
                "service_type": invoice.lines[0].service_type if invoice.lines else None,
                "net_gbp": invoice.net_gbp,
                "vat_gbp": invoice.vat_gbp,
            }
            outcome = ExtractionOracle.compare(oracle, actual)
            fields_checked += len(FIELD_NAMES)
            fields_correct += sum(1 for correct in outcome.values() if correct)
            # Calibration uses each line's own confidence against whether this invoice's fields were
            # all extracted correctly, which is the only correctness label the seed supports.
            all_correct = all(outcome.values())
            for line in invoice.lines:
                confidence = float(line.extracted_confidence)
                index = min(int(confidence * ECE_BIN_COUNT), ECE_BIN_COUNT - 1)
                bins[index].append((confidence, all_correct))

        total_lines = sum(len(bucket) for bucket in bins)
        ece = 0.0
        for bucket in bins:
            if not bucket:
                continue
            mean_confidence = sum(confidence for confidence, _ in bucket) / len(bucket)
            accuracy = sum(1 for _, correct in bucket if correct) / len(bucket)
            ece += (len(bucket) / total_lines) * abs(accuracy - mean_confidence)

        return [
            self._score(
                "field_extraction_accuracy",
                round(fields_correct / fields_checked, 4) if fields_checked else 0.0,
                0.95,
                ">=",
                note=f"{fields_correct} of {fields_checked} fields matched the document text.",
            ),
            self._score(
                "extraction_confidence_ece",
                round(ece, 4),
                0.05,
                "<=",
                note=f"Expected calibration error over {total_lines} lines in {ECE_BIN_COUNT} confidence bins.",
            ),
        ]

    def _redaction_metrics(self, invoices: list[Any]) -> list[MetricResult]:
        """Score PII redaction recall and false positive rate against the independent PII oracle."""
        true_spans_total = matched_spans = 0
        regions_total = regions_false = 0
        for invoice in invoices:
            spans = PiiOracle.spans(invoice.document_text)
            records = self.repository.redactions.get(invoice.id, [])
            regions = [PiiOracle.parse_region(record.field_or_region) for record in records]
            regions = [region for region in regions if region is not None]
            true_spans_total += len(spans)
            regions_total += len(regions)
            for span_start, span_end, _ in spans:
                if any(region[0] < span_end and span_start < region[1] for region in regions):
                    matched_spans += 1
            for region in regions:
                if not PiiOracle.overlaps(region, spans):
                    regions_false += 1
        return [
            self._score(
                "pii_redaction_recall",
                round(matched_spans / true_spans_total, 4) if true_spans_total else 1.0,
                0.99,
                ">=",
                note=f"{matched_spans} of {true_spans_total} true PII spans were redacted.",
            ),
            self._score(
                "pii_redaction_false_positive_rate",
                round(regions_false / regions_total, 4) if regions_total else 0.0,
                0.03,
                "<=",
                note=f"{regions_false} of {regions_total} redacted regions did not overlap real PII.",
            ),
        ]

    def _matching_metrics(self, invoices: list[Any]) -> list[MetricResult]:
        """Score claim matching accuracy and the false match rate on adversarial cases."""
        checked = correct = 0
        adversarial = false_matches = 0
        raised_by_invoice: dict[str, set[str]] = {}
        for record in self.repository.exceptions.values():
            raised_by_invoice.setdefault(record.invoice_id, set()).add(record.reason)
        for invoice in invoices:
            oracle = self._oracle_for(invoice)
            if oracle is None:
                continue
            if invoice.seeded_outcome == "failed_claim_matching":
                adversarial += 1
                if "failed_claim_matching" not in raised_by_invoice.get(invoice.id, set()):
                    false_matches += 1
                continue
            checked += 1
            claim = self.repository.get_claim(invoice.claim_id)
            if claim is not None and claim.invoice_claim_ref == oracle.get("claim_ref"):
                correct += 1
        return [
            self._score(
                "claim_matching_accuracy",
                round(correct / checked, 4) if checked else 0.0,
                0.98,
                ">=",
                note=f"{correct} of {checked} matchable invoices resolved to the claim reference in the document.",
            ),
            self._score(
                "claim_matching_false_match_rate",
                round(false_matches / adversarial, 4) if adversarial else 0.0,
                0.005,
                "<=",
                note=f"{false_matches} of {adversarial} unmatchable invoices were not flagged as failed matches.",
            ),
        ]

    def _rerating_metric(self, invoices: list[Any]) -> MetricResult:
        """Recompute the re-rating arithmetic independently and require an exact match."""
        checked = exact = 0
        for invoice in invoices:
            rate_card = self.repository.current_rate_card(invoice.supplier_id)
            if rate_card is None or not rate_card.lines:
                continue
            rate = rate_card.lines[0]
            for line in invoice.lines:
                checked += 1
                expected = round(line.units * rate.rate_gbp, 2)
                variance = round(line.amount_gbp - expected, 2)
                if abs(line.expected_amount_gbp - expected) < 0.005 and abs(line.variance_gbp - variance) < 0.005:
                    exact += 1
        return self._score(
            "rerating_arithmetic_exact_match",
            round(exact / checked, 4) if checked else 0.0,
            1.0,
            "==",
            note=f"{exact} of {checked} lines matched an independent units times rate recomputation.",
        )

    def _tolerance_metric(self, invoices: list[Any]) -> MetricResult:
        """Score the tolerance decision against a rule-based oracle built from settings."""
        tolerance_pct = float(self.repository.settings.get("tolerance_pct", 5.0))
        tolerance_gbp = float(self.repository.settings.get("tolerance_gbp", 25.0))
        checked = correct = 0
        for invoice in invoices:
            for line in invoice.lines:
                if line.validation_status == "pending":
                    continue
                checked += 1
                is_outside = abs(line.variance_pct) > tolerance_pct and abs(line.variance_gbp) > tolerance_gbp
                if line.tolerance_outcome == ("outside" if is_outside else "within"):
                    correct += 1
        return self._score(
            "tolerance_decision_accuracy",
            round(correct / checked, 4) if checked else 0.0,
            0.99,
            ">=",
            note=f"{correct} of {checked} lines agreed with the {tolerance_pct}% / £{tolerance_gbp} oracle.",
        )

    def _duplicate_metric(self, invoices: list[Any]) -> MetricResult:
        """Score duplicate detection against the seeded duplicate pairs."""
        evaluated_numbers = {invoice.invoice_number for invoice in invoices}
        truth = {
            pair.get("duplicate")
            for pair in self.repository.duplicate_pairs
            if pair.get("duplicate") in evaluated_numbers
        }
        # The pipeline records no duplicate signal anywhere: no exception reason, no validation flag.
        # Anything it did flag would appear in validation_summary, so that is what is inspected.
        predicted = {
            invoice.invoice_number
            for invoice in invoices
            if invoice.validation_summary.get("duplicate_of") or invoice.validation_summary.get("is_duplicate")
        }
        true_positives = len(truth & predicted)
        precision = true_positives / len(predicted) if predicted else 0.0
        recall = true_positives / len(truth) if truth else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        method = MEASURED if predicted else NOT_IMPLEMENTED
        note = (
            f"{true_positives} of {len(truth)} seeded duplicates detected."
            if predicted
            else f"No duplicate detection exists in the pipeline; {len(truth)} seeded duplicates went undetected."
        )
        return self._score("duplicate_detection_f1", round(f1, 4), 0.95, ">=", method=method, note=note)

    def _exception_reason_metric(self, invoices: list[Any]) -> MetricResult:
        """Score exception reason assignment against the seeded outcome labels."""
        raised_by_invoice: dict[str, set[str]] = {}
        for record in self.repository.exceptions.values():
            raised_by_invoice.setdefault(record.invoice_id, set()).add(record.reason)
        checked = correct = 0
        for invoice in invoices:
            expected = OUTCOME_TO_REASON.get(invoice.seeded_outcome)
            if expected not in EXCEPTION_REASONS:
                continue
            checked += 1
            if expected in raised_by_invoice.get(invoice.id, set()):
                correct += 1
        return self._score(
            "exception_reason_assignment_accuracy",
            round(correct / checked, 4) if checked else 1.0,
            0.97,
            ">=",
            note=f"{correct} of {checked} seeded exception invoices received the expected reason.",
        )

    def _explanation_metric(self, invoices: list[Any]) -> MetricResult:
        """Score explanation quality with a deterministic rubric.

        Specification section 17.1 asks for an LLM judge. This harness must run fully offline
        (acceptance criterion 11), so the three rubric dimensions are scored deterministically
        instead. That is a weaker signal than a judge and is labelled as such in the note.
        """
        scores: list[float] = []
        for invoice in invoices:
            decision = invoice.decision
            if not decision:
                continue
            evidence = decision.get("evidence", [])
            points = 0
            if decision.get("reasoning"):
                points += 1
            if evidence:
                points += 1
            if any(item.get("type") == "rate_card" and item.get("ref") for item in evidence):
                points += 1
            affected = decision.get("affected_lines", [])
            if (decision.get("decision") == "QUERY") == bool(affected):
                points += 1
            if decision.get("model_version") and decision.get("prompt_version"):
                points += 1
            scores.append(points)
        return self._score(
            "explanation_quality_rubric_score",
            round(sum(scores) / len(scores), 3) if scores else 0.0,
            4.0,
            ">=",
            note=f"Deterministic five-point rubric over {len(scores)} decisions, not an LLM judge.",
        )

    def _straight_through_metric(self, invoices: list[Any]) -> MetricResult:
        """Score the end-to-end straight-through rate."""
        total = len(invoices)
        straight_through = sum(1 for invoice in invoices if invoice.straight_through)
        statuses = Counter(invoice.status for invoice in invoices)
        return self._score(
            "straight_through_rate",
            round(straight_through / total, 4) if total else 0.0,
            0.70,
            ">=",
            note=f"{straight_through} of {total} invoices required no human touch. Status mix: {dict(statuses)}.",
        )

    def _audit_metric(self) -> MetricResult:
        """Verify the append-only audit hash chain."""
        return self._score(
            "audit_hash_chain_valid",
            self.repository.audit.verify(),
            True,
            "==",
            note=f"Chain verified over {len(self.repository.audit.list_events())} events.",
        )

    @staticmethod
    def main() -> None:
        """CLI entry point."""
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        parser = argparse.ArgumentParser(description="Run the CMP-UC-002 evaluation harness.")
        parser.add_argument(
            "--sample-size",
            type=int,
            default=None,
            help="Number of invoices to evaluate. Defaults to the whole seeded estate.",
        )
        parser.add_argument(
            "--summary", action="store_true", help="Print a one-line-per-metric table instead of JSON."
        )
        args = parser.parse_args()

        report = EvaluationHarness().run(sample_size=args.sample_size)
        target = REPO_ROOT / "apps/invoice_to_pay/evaluation/reports/latest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")

        if args.summary:
            print(f"\nEvaluated {report.get('sample_size')} invoices\n")
            print(f"{'metric':<40} {'value':>9}  {'target':<10} {'result':<8} method")
            print("-" * 96)
            for name, metric in report.get("metrics", {}).items():
                verdict = "PASS" if metric.get("passed") else "FAIL"
                bound = f"{metric.get('comparator')} {metric.get('target')}"
                print(f"{name:<40} {str(metric.get('value')):>9}  {bound:<10} {verdict:<8} {metric.get('method')}")
            print("-" * 96)
            print(f"passed={report.get('passed')}  failed={report.get('failed_metrics')}")
        else:
            print(json.dumps(report, indent=2))


if __name__ == "__main__":
    EvaluationHarness.main()
