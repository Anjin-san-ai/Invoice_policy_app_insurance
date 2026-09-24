"""Tests for duplicate invoice detection, covering TC-07."""

from apps.invoice_to_pay.backend.app.models.domain import EXCEPTION_REASONS
from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository


class TestDuplicateDetection:
    """A resubmitted invoice must be blocked, flagged, and reference the original."""

    @staticmethod
    def _first_duplicate(repository: InvoiceRepository) -> tuple[str, str]:
        """Return the invoice id and original invoice number of the first seeded duplicate."""
        pair = repository.duplicate_pairs[0]
        duplicate_number = pair.get("duplicate")
        for invoice in repository.invoices.values():
            if invoice.invoice_number == duplicate_number:
                return invoice.id, pair.get("original", "")
        raise AssertionError(f"Seeded duplicate {duplicate_number} is not in the invoice set")

    def test_seed_provides_forty_duplicate_pairs(self) -> None:
        repository = InvoiceRepository()
        assert len(repository.duplicate_pairs) == 40

    def test_duplicates_are_never_seeded_onto_straight_through_invoices(self) -> None:
        """Otherwise the 40 seeded duplicates would fight the 70% straight-through target."""
        repository = InvoiceRepository()
        by_number = {invoice.invoice_number: invoice for invoice in repository.invoices.values()}
        for pair in repository.duplicate_pairs:
            invoice = by_number.get(pair.get("duplicate", ""))
            assert invoice is not None
            assert invoice.seeded_outcome != "straight_through"

    def test_duplicate_is_blocked_and_references_the_original(self) -> None:
        repository = InvoiceRepository()
        invoice_id, original = self._first_duplicate(repository)
        result = InvoicePipelineService(repository).process_invoice(invoice_id)

        assert result.get("validation_summary", {}).get("is_duplicate") is True
        assert result.get("validation_summary", {}).get("duplicate_of") == original
        assert result.get("status") == "Awaiting information"
        assert result.get("decision", {}).get("decision") == "ROUTE_TO_HANDLER"
        assert original in result.get("decision", {}).get("reasoning", "")
        assert any(item.get("type") == "duplicate" for item in result.get("decision", {}).get("evidence", []))
        # Blocked, so no payment may exist for it.
        assert not [payment for payment in repository.payments.values() if payment.invoice_id == invoice_id]
        assert repository.audit.verify()

    def test_duplicate_block_does_not_invent_a_sixth_exception_reason(self) -> None:
        """Section 3.7 fixes the taxonomy at five values; none of them means duplicate."""
        repository = InvoiceRepository()
        invoice_id, _ = self._first_duplicate(repository)
        InvoicePipelineService(repository).process_invoice(invoice_id)
        for record in repository.exceptions.values():
            assert record.reason in EXCEPTION_REASONS

    def test_duplicate_block_is_audited(self) -> None:
        repository = InvoiceRepository()
        invoice_id, original = self._first_duplicate(repository)
        InvoicePipelineService(repository).process_invoice(invoice_id)
        events = [
            event
            for event in repository.audit.list_events(entity_id=invoice_id)
            if event.get("event_type") == "duplicate_blocked"
        ]
        assert len(events) == 1
        assert events[0].get("after_json", {}).get("duplicate_of") == original
        assert events[0].get("after_json", {}).get("payment_blocked") is True

    def test_a_clean_invoice_is_not_flagged_as_duplicate(self) -> None:
        repository = InvoiceRepository()
        result = InvoicePipelineService(repository).process_invoice("INVREC-000001")
        assert result.get("validation_summary", {}).get("is_duplicate") is False
        assert result.get("status") == "Paid"
