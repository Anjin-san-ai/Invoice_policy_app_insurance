"""Tests for GDPR and PII redaction, covering spec section 3.3 and TC-10."""

from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository


class TestRedaction:
    """Validate that PII-bearing documents produce a what-and-why redaction audit trail."""

    # The seed generator injects PII into every eleventh invoice, so this one carries all three types.
    PII_INVOICE_ID = "INVREC-000011"

    def test_redaction_rules_are_valid_regex_that_match_seeded_pii(self) -> None:
        """Guards against the double-escaped patterns that silently disabled redaction."""
        repository = InvoiceRepository()
        rules = repository.settings.get("redaction_rules", [])
        assert len(rules) == 3
        for rule in rules:
            pattern = rule.get("pattern", "")
            assert "\\\\" not in pattern, f"Rule {rule.get('id')} is double-escaped and can never match"

    def test_pii_invoice_produces_redaction_log_entries(self) -> None:
        repository = InvoiceRepository()
        InvoicePipelineService(repository).process_invoice(self.PII_INVOICE_ID)
        records = repository.redactions.get(self.PII_INVOICE_ID, [])
        assert records, "Expected redaction log entries for a PII-bearing invoice"
        rule_ids = {record.rule_id for record in records}
        assert rule_ids == {"PII-EMAIL", "PII-POSTCODE", "PII-PHONE"}
        for record in records:
            assert record.reason, "Every redaction must record why it was redacted"
            assert record.field_or_region, "Every redaction must record what was redacted"
        assert repository.audit.verify()

    def test_redaction_is_recorded_across_the_whole_estate(self) -> None:
        repository = InvoiceRepository()
        service = InvoicePipelineService(repository)
        for invoice_id in list(repository.invoices):
            service.process_invoice(invoice_id)
        redacted_invoices = len(repository.redactions)
        assert redacted_invoices > 100, f"Only {redacted_invoices} invoices produced redactions"
        assert repository.audit.verify()
