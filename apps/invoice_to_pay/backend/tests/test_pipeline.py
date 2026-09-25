"""Backend tests for invoInvoice-to-pay prototype."""

from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository


class TestInvoicePipeline:
    """Validate mandatory invoInvoice-to-pay behaviours."""

    def test_straight_through_invoice_is_paid_with_trace(self) -> None:
        repository = InvoiceRepository()
        result = InvoicePipelineService(repository).process_invoice("INVREC-000001")
        assert result.get("status") == "Paid"
        assert result.get("decision", {}).get("decision") == "AUTO_APPROVE"
        assert len(result.get("trace", [])) >= 8
        assert repository.audit.verify()

    def test_out_of_tolerance_query_names_specific_lines(self) -> None:
        repository = InvoiceRepository()
        result = InvoicePipelineService(repository).process_invoice("INVREC-000071")
        assert result.get("status") == "Queried"
        affected = result.get("decision", {}).get("affected_lines", [])
        assert affected
        assert all("INVREC-000071-L" in line_id for line_id in affected)

    def test_release_succeeds_for_a_different_identity(self) -> None:
        repository = InvoiceRepository()
        service = InvoicePipelineService(repository)
        service.approve_invoice("INVREC-000071", "alice")
        payment = service.release_payment("PAY-INVREC-000071", "ben")
        assert payment.get("released_by") == "ben"
        assert payment.get("authorised_by") == "alice"
        assert payment.get("invoice_writeback_status") == "confirmed"
        assert repository.audit.verify()

    def test_second_release_is_refused_so_the_supplier_is_not_paid_twice(self) -> None:
        repository = InvoiceRepository()
        service = InvoicePipelineService(repository)
        service.approve_invoice("INVREC-000071", "alice")
        service.release_payment("PAY-INVREC-000071", "ben")
        try:
            service.release_payment("PAY-INVREC-000071", "ben")
        except ValueError as error:
            assert "already released" in str(error)
        else:
            raise AssertionError("Expected a duplicate release to be refused")
        assert repository.audit.verify()

    def test_segregation_of_duties_blocks_same_releaser(self) -> None:
        repository = InvoiceRepository()
        service = InvoicePipelineService(repository)
        service.approve_invoice("INVREC-000071", "alice")
        try:
            service.release_payment("PAY-INVREC-000071", "alice")
        except PermissionError as error:
            assert "Segregation" in str(error)
        else:
            raise AssertionError("Expected segregation of duties failure")
        assert repository.audit.verify()
