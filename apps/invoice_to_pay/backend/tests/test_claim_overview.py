"""Tests for the 360 degree claim aggregation."""

import pytest

from apps.invoice_to_pay.backend.app.services.claim_overview import ClaimOverviewService
from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository


class TestClaimOverviewService:
    """Validate the claim-centric view the Claim 360 module renders."""

    @staticmethod
    def _processed() -> InvoiceRepository:
        """Return a repository with a slice of the estate already processed."""
        repository = InvoiceRepository()
        pipeline = InvoicePipelineService(repository)
        for invoice_id in list(repository.invoices)[:400]:
            pipeline.process_invoice(invoice_id)
        return repository

    def test_claim_list_is_ranked_by_invoiced_value(self) -> None:
        repository = self._processed()
        rows = ClaimOverviewService(repository).list_claims(limit=20)
        assert rows
        values = [row.get("invoiced_gbp", 0.0) for row in rows]
        assert values == sorted(values, reverse=True)
        for row in rows:
            assert row.get("invoice_count", 0) > 0

    def test_claim_list_search_matches_the_ice_reference(self) -> None:
        repository = self._processed()
        service = ClaimOverviewService(repository)
        first = service.list_claims(limit=1)[0].get("claim", {})
        matched = service.list_claims(limit=10, search=first.get("ice_claim_ref", ""))
        assert [row.get("claim", {}).get("id") for row in matched] == [first.get("id")]

    def test_overview_aggregates_every_related_entity(self) -> None:
        repository = self._processed()
        service = ClaimOverviewService(repository)
        claim_id = service.list_claims(limit=1)[0].get("claim", {}).get("id", "")
        overview = service.overview(claim_id)

        assert overview.get("claim", {}).get("id") == claim_id
        assert overview.get("invoices"), "Expected at least one invoice on the top claim"
        assert overview.get("suppliers"), "Expected at least one supplier on the top claim"
        assert overview.get("timeline"), "Expected audit events for a processed claim"
        assert set(overview.get("stage_counts", {})) == {
            "Received",
            "Extracted",
            "Redacted",
            "Matched",
            "Validated",
            "Approved",
            "Paid",
        }

    def test_financials_reconcile_with_the_invoice_cards(self) -> None:
        repository = self._processed()
        service = ClaimOverviewService(repository)
        claim_id = service.list_claims(limit=1)[0].get("claim", {}).get("id", "")
        overview = service.overview(claim_id)
        financials = overview.get("financials", {})
        card_total = round(sum(card.get("gross_gbp", 0.0) for card in overview.get("invoices", [])), 2)
        assert financials.get("invoiced_gbp") == card_total
        assert financials.get("paid_gbp", 0.0) + financials.get("withheld_gbp", 0.0) == pytest.approx(card_total, abs=0.02)

    def test_authorisations_compare_approved_against_charged(self) -> None:
        repository = self._processed()
        service = ClaimOverviewService(repository)
        for row in service.list_claims(limit=12):
            overview = service.overview(row.get("claim", {}).get("id", ""))
            for entry in overview.get("authorisations", []):
                approved = entry.get("authorisation", {}).get("authorised_units", 0)
                assert entry.get("units_over") == max(0, entry.get("charged_units", 0) - approved)
                assert entry.get("value_over_gbp", 0.0) >= 0.0

    def test_unknown_claim_is_reported(self) -> None:
        repository = InvoiceRepository()
        with pytest.raises(ValueError, match="Unknown claim id"):
            ClaimOverviewService(repository).overview("CLM-NOPE")
