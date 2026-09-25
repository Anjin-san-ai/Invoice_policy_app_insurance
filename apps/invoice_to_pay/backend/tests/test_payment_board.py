"""Tests for the approvals and payments swim-lane board."""

from apps.invoice_to_pay.backend.app.services.payment_board import LANES, PaymentBoardService
from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository


class TestPaymentBoardService:
    """Validate the lanes a finance team works through."""

    @staticmethod
    def _warm() -> InvoiceRepository:
        """Return a repository with the whole estate processed, as the API does at startup."""
        repository = InvoiceRepository()
        pipeline = InvoicePipelineService(repository)
        for invoice_id in list(repository.invoices):
            pipeline.process_invoice(invoice_id)
        return repository

    def test_board_returns_every_lane_in_order(self) -> None:
        board = PaymentBoardService(self._warm()).board()
        assert [lane.get("key") for lane in board.get("lanes", [])] == [key for key, _, _ in LANES]

    def test_authorisation_lane_is_populated_after_warm_up(self) -> None:
        """The screen used to look empty because auto-pay settles everything; it must not."""
        board = PaymentBoardService(self._warm()).board()
        lanes = {lane.get("key"): lane for lane in board.get("lanes", [])}
        assert lanes.get("authorise", {}).get("count", 0) > 0
        assert lanes.get("released", {}).get("count", 0) > 0
        assert lanes.get("blocked", {}).get("count", 0) > 0

    def test_blocked_lane_holds_only_duplicates_and_names_the_original(self) -> None:
        board = PaymentBoardService(self._warm()).board()
        blocked = next(lane for lane in board.get("lanes", []) if lane.get("key") == "blocked")
        assert blocked.get("items")
        for item in blocked.get("items", []):
            assert item.get("duplicate_of")
            assert item.get("duplicate_of") in item.get("reason", "")
            assert item.get("payment_id") is None

    def test_released_items_carry_both_identities(self) -> None:
        board = PaymentBoardService(self._warm()).board()
        released = next(lane for lane in board.get("lanes", []) if lane.get("key") == "released")
        for item in released.get("items", []):
            assert item.get("released_by")
            assert item.get("invoice_writeback_status") == "confirmed"

    def test_authorising_moves_an_item_into_the_release_lane(self) -> None:
        repository = self._warm()
        service = PaymentBoardService(repository)
        lanes = {lane.get("key"): lane for lane in service.board().get("lanes", [])}
        candidate = lanes.get("authorise", {}).get("items", [])[0]
        before = lanes.get("release", {}).get("count", 0)

        InvoicePipelineService(repository).approve_invoice(candidate.get("invoice_id", ""), "analyst-alice")

        after_lanes = {lane.get("key"): lane for lane in service.board().get("lanes", [])}
        assert after_lanes.get("release", {}).get("count", 0) == before + 1
        moved = [item for item in after_lanes.get("release", {}).get("items", []) if item.get("invoice_id") == candidate.get("invoice_id")]
        assert moved and moved[0].get("authorised_by") == "analyst-alice"
        assert moved[0].get("released_by") is None

    def test_lane_values_sum_to_the_reported_total(self) -> None:
        board = PaymentBoardService(self._warm()).board()
        lane_total = round(sum(lane.get("value_gbp", 0.0) for lane in board.get("lanes", [])), 2)
        assert board.get("total_value_gbp") == lane_total

    def test_high_value_items_explain_why_they_need_a_human(self) -> None:
        board = PaymentBoardService(self._warm()).board()
        authorise = next(lane for lane in board.get("lanes", []) if lane.get("key") == "authorise")
        high_value = [item for item in authorise.get("items", []) if item.get("is_high_value")]
        assert high_value
        for item in high_value:
            assert "threshold" in item.get("reason", "")
