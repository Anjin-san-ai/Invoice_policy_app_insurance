"""FastAPI application for the CMP-UC-002 invoice-to-pay prototype."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from apps.invoice_to_pay.backend.app.services.analytics import AnalyticsService
from apps.invoice_to_pay.backend.app.services.assistant import BackOfficeAssistant
from apps.invoice_to_pay.backend.app.services.claim_agents import ClaimAgentWorkflowService
from apps.invoice_to_pay.backend.app.services.claim_intake import ClaimIntakeService
from apps.invoice_to_pay.backend.app.services.claim_overview import ClaimOverviewService
from apps.invoice_to_pay.backend.app.services.payment_board import PaymentBoardService
from apps.invoice_to_pay.backend.app.services.pipeline import InvoicePipelineService
from apps.invoice_to_pay.backend.app.services.repository import InvoiceRepository
from apps.invoice_to_pay.backend.app.services.search import SearchService
from apps.invoice_to_pay.backend.app.services.tracking import ClaimTrackingService
from apps.invoice_to_pay.backend.app.services.work_orders import WorkOrderService

logger = logging.getLogger(__name__)


class ActorRequest(BaseModel):
    """Request body carrying a user or system actor id."""

    actor_id: str = "demo-user"


class AppContainer:
    """Dependency container for the prototype."""

    def __init__(self) -> None:
        self.repository = InvoiceRepository()
        self.pipeline = InvoicePipelineService(self.repository)
        self.analytics = AnalyticsService(self.repository)
        self.claims = ClaimOverviewService(self.repository)
        self.board = PaymentBoardService(self.repository)
        self.search = SearchService(self.repository)
        self.intake = ClaimIntakeService(self.repository)
        self.work_orders = WorkOrderService(self.repository, self.pipeline)
        self.tracking = ClaimTrackingService(self.repository)
        self.claim_agents = ClaimAgentWorkflowService(self.repository)
        self.assistant = BackOfficeAssistant(
            self.repository, self.analytics, self.claims, self.board, self.search
        )

    def warm_up(self) -> int:
        """Process the whole seeded dataset so every screen has data on first load.

        The deterministic pipeline runs the full 2,000-invoice set in roughly seven seconds, so this
        is done eagerly at startup rather than leaving the exception, dispute, payment and audit
        views empty until someone clicks a row.
        """
        processed = 0
        for invoice_id in list(self.repository.invoices):
            try:
                self.pipeline.process_invoice(invoice_id)
            except ValueError as exc:
                logger.warning("Skipped invoice %s during warm-up: %s", invoice_id, exc)
                continue
            processed += 1
        logger.info("Warm-up processed %d invoices; audit chain valid=%s", processed, self.repository.audit.verify())
        return processed


class InvoiceToPayApp:
    """Factory for the FastAPI app."""

    @staticmethod
    def create() -> FastAPI:
        """Create and configure the FastAPI application."""
        container = AppContainer()
        container.warm_up()
        app = FastAPI(title="CMP-UC-002 Invoice-to-Pay Prototype", version="0.1.0")
        app.add_middleware(
            CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
        )
        InvoiceToPayApp._routes(app, container)
        return app

    @staticmethod
    def _routes(app: FastAPI, container: AppContainer) -> None:
        """Register routes on the FastAPI app."""

        @app.get("/api/health")
        async def health() -> dict[str, Any]:
            return {
                "status": "ok",
                "audit_hash_chain_valid": container.repository.audit.verify(),
                "claim_assistant": container.intake.assistant.describe(),
            }

        @app.post("/api/invoices/ingest")
        async def ingest(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            invoice_id = (payload or {}).get("invoice_id", "INVREC-000001")
            try:
                return container.pipeline.process_invoice(invoice_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.get("/api/invoices")
        async def invoices(
            status: str | None = None, supplier_id: str | None = None, limit: int = 100
        ) -> list[dict[str, Any]]:
            return container.repository.list_invoices(status=status, supplier_id=supplier_id, limit=limit)

        @app.get("/api/invoices/{invoice_id}")
        async def invoice(invoice_id: str) -> dict[str, Any]:
            item = container.repository.get_invoice(invoice_id)
            if item is None:
                raise HTTPException(status_code=404, detail="Invoice not found")
            return container.pipeline.full_invoice(item)

        @app.post("/api/invoices/{invoice_id}/reprocess")
        async def reprocess(invoice_id: str) -> dict[str, Any]:
            try:
                return container.pipeline.process_invoice(invoice_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.get("/api/invoices/{invoice_id}/trace")
        async def trace(invoice_id: str) -> list[dict[str, Any]]:
            return [item.to_dict() for item in container.repository.traces.get(invoice_id, [])]

        @app.get("/api/invoices/{invoice_id}/audit")
        async def audit(invoice_id: str) -> list[dict[str, Any]]:
            return container.repository.audit.list_events(entity_id=invoice_id)

        @app.get("/api/invoices/{invoice_id}/evidence-pack")
        async def evidence_pack(invoice_id: str) -> dict[str, Any]:
            item = container.repository.get_invoice(invoice_id)
            if item is None:
                raise HTTPException(status_code=404, detail="Invoice not found")
            return {
                "format": "json",
                "pdf_status": "mocked",
                "invoice": container.pipeline.full_invoice(item),
                "audit": container.repository.audit.list_events(entity_id=invoice_id),
            }

        @app.get("/api/exceptions")
        async def exceptions() -> list[dict[str, Any]]:
            return sorted(
                [item.to_dict() for item in container.repository.exceptions.values()],
                key=lambda item: (item.get("priority"), item.get("opened_at")),
            )

        @app.post("/api/exceptions/{exception_id}/execute-action")
        async def execute_action(exception_id: str) -> dict[str, Any]:
            item = container.repository.exceptions.get(exception_id)
            if item is None:
                raise HTTPException(status_code=404, detail="Exception not found")
            # The next action runs once: a second click must not re-send the query or re-write the event.
            if item.resolved_at is not None:
                raise HTTPException(status_code=409, detail=f"Next action was already executed for {exception_id}")
            before = item.to_dict()
            item.resolved_at = "now"
            item.resolution = f"Next action executed: {item.next_action.get('type', 'action')}"
            container.repository.audit.append(
                "exception", exception_id, "next_action_executed", "user", "demo-user", before, item.to_dict()
            )
            return {"executed": True, "action": item.next_action, "exception": item.to_dict()}

        @app.post("/api/exceptions/{exception_id}/override")
        async def override(exception_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            reason = payload.get("reason")
            if not reason:
                raise HTTPException(status_code=400, detail="Override reason is mandatory")
            item = container.repository.exceptions.get(exception_id)
            if item is None:
                raise HTTPException(status_code=404, detail="Exception not found")
            before = item.to_dict()
            item.resolution = reason
            item.resolved_at = "now"
            container.repository.audit.append(
                "exception",
                exception_id,
                "human_override",
                "user",
                payload.get("actor_id", "demo-user"),
                before,
                item.to_dict(),
            )
            return item.to_dict()

        @app.post("/api/invoices/{invoice_id}/approve")
        async def approve(invoice_id: str, payload: ActorRequest) -> dict[str, Any]:
            try:
                return container.pipeline.approve_invoice(invoice_id, payload.actor_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.post("/api/invoices/{invoice_id}/return-to-supplier")
        async def return_to_supplier(invoice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Send an invoice back to the supplier for verification and resubmission."""
            reason = payload.get("reason", "")
            if not str(reason).strip():
                raise HTTPException(status_code=400, detail="A reason is mandatory")
            try:
                return container.pipeline.return_to_supplier(
                    invoice_id, str(payload.get("actor_id", "demo-user")), str(reason), payload.get("line_ids")
                )
            except ValueError as exc:
                status = 409 if "already paid" in str(exc).lower() else 404
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        @app.post("/api/invoices/{invoice_id}/resubmit")
        async def resubmit(invoice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Record a supplier resubmission and re-run validation over the corrected invoice."""
            try:
                return container.pipeline.resubmit_invoice(
                    invoice_id, str(payload.get("actor_id", "demo-user")), str(payload.get("note", ""))
                )
            except ValueError as exc:
                status = 409 if "no open" in str(exc).lower() else 404
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        @app.post("/api/payments/{payment_id}/release")
        async def release(payment_id: str, payload: ActorRequest) -> dict[str, Any]:
            try:
                return container.pipeline.release_payment(payment_id, payload.actor_id)
            except ValueError as exc:
                # An unknown payment is a 404; an already-released one is a conflict, not a
                # missing resource, so the UI can tell the two apart.
                status_code = 404 if "Unknown payment id" in str(exc) else 409
                raise HTTPException(status_code=status_code, detail=str(exc)) from exc
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc

        @app.get("/api/suppliers")
        async def suppliers() -> list[dict[str, Any]]:
            return container.analytics.supplier_scorecards()

        @app.get("/api/rate-cards")
        async def rate_cards() -> list[dict[str, Any]]:
            return container.analytics.rate_card_registry()

        @app.get("/api/disputes")
        async def disputes() -> list[dict[str, Any]]:
            """Return dispute queries for the Disputes workspace."""
            return [item.to_dict() for item in container.repository.disputes.values()]

        @app.get("/api/search")
        async def search(q: str = "", limit: int = 40) -> dict[str, Any]:
            """Cross-module search backing the global search bar on every screen."""
            return container.search.search(q, limit=limit)

        @app.get("/api/payments/board")
        async def payment_board(limit_per_lane: int = 40) -> dict[str, Any]:
            """Return the approvals and payments swim-lane board."""
            return container.board.board(limit_per_lane=limit_per_lane)

        @app.get("/api/payments")
        async def payments() -> list[dict[str, Any]]:
            """Return payments for the Approvals and Payments module."""
            return [item.to_dict() for item in container.repository.payments.values()]

        @app.get("/api/notifications")
        async def notifications(limit: int = 200) -> list[dict[str, Any]]:
            """Return recent outbound notifications for the notification matrix view."""
            flattened = [item.to_dict() for items in container.repository.notifications.values() for item in items]
            return flattened[:limit]

        @app.get("/api/redactions")
        async def redactions(limit: int = 200) -> list[dict[str, Any]]:
            """Return the GDPR and PII redaction log for the Audit Trail module."""
            flattened = [item.to_dict() for items in container.repository.redactions.values() for item in items]
            return flattened[:limit]

        @app.get("/api/audit")
        async def audit_all(entity_type: str | None = None, limit: int = 300) -> dict[str, Any]:
            """Return the immutable audit log with its hash chain verification status."""
            events = container.repository.audit.list_events(entity_type=entity_type)
            return {
                "hash_chain_valid": container.repository.audit.verify(),
                "total": len(events),
                "events": events[-limit:],
            }

        @app.get("/api/settings")
        async def settings() -> dict[str, Any]:
            """Return the configuration-driven thresholds and redaction rules."""
            return {"settings": container.repository.settings, "metadata": container.repository.metadata}

        @app.get("/api/claims")
        async def claims(limit: int = 60, search: str | None = None) -> list[dict[str, Any]]:
            """Return claims with their invoice, supplier and value aggregates."""
            return container.claims.list_claims(limit=limit, search=search)

        @app.get("/api/assistant/suggestions")
        async def assistant_suggestions() -> list[str]:
            """Return the prompts Theo offers a handler on an empty screen."""
            return list(BackOfficeAssistant.SUGGESTIONS)

        @app.post("/api/assistant/ask")
        async def assistant_ask(payload: dict[str, Any]) -> dict[str, Any]:
            """Answer a back-office question with figures from the live estate."""
            try:
                return container.assistant.ask(str(payload.get("question", "")))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        @app.get("/api/claims/{claim_id}/agent-workflows")
        async def claim_agent_workflows(claim_id: str) -> dict[str, Any]:
            """Return claim triage plus a four-stage agent workflow per supplier."""
            try:
                return container.claim_agents.workflows(claim_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.get("/api/claims/statistics")
        async def claim_statistics() -> dict[str, Any]:
            """Return claim-side headline numbers and breakdowns for the dashboard."""
            return container.claims.statistics()

        @app.get("/api/claims/{claim_id}/overview")
        async def claim_overview(claim_id: str) -> dict[str, Any]:
            """Return the 360 degree view of one claim."""
            try:
                return container.claims.overview(claim_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.get("/api/analytics/supplier-matrix")
        async def supplier_matrix(top: int = 14) -> dict[str, Any]:
            """Return the supplier by service-type variance matrix for the heatmap."""
            return container.analytics.supplier_service_matrix(top=top)

        @app.get("/api/analytics/exception-trends")
        async def exception_trends() -> dict[str, Any]:
            return container.analytics.exception_trends()

        @app.get("/api/analytics/cycle-time")
        async def cycle_time() -> dict[str, Any]:
            return container.analytics.cycle_time()

        @app.post("/api/rate-cards")
        async def upload_rate_card(payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "accepted": True,
                "mode": "mock",
                "impact_preview": {"open_invoices_impacted": 0},
                "payload": payload,
            }

        @app.get("/api/analytics/kpis")
        async def kpis() -> dict[str, Any]:
            return container.analytics.kpis()

        @app.get("/api/analytics/leakage")
        async def leakage() -> dict[str, Any]:
            return container.analytics.leakage()

        @app.get("/api/analytics/benefits")
        async def benefits() -> dict[str, Any]:
            return container.analytics.benefits()

        # ---------------------------------------------------------- customer portal intake

        @app.post("/api/portal/claims")
        async def portal_start(payload: dict[str, Any] | None = None) -> dict[str, Any]:
            """Open a draft claim for a signed-in policyholder and return the opening turn."""
            body = payload or {}
            return container.intake.start(
                {
                    "customer_name": str(body.get("customer_name", "")),
                    "contact_number": str(body.get("contact_number", "")),
                    "contact_email": str(body.get("contact_email", "")),
                    "address": str(body.get("address", "")),
                    "insurance_number": str(body.get("insurance_number", "")),
                }
            )

        @app.get("/api/portal/claims/{claim_id}")
        async def portal_state(claim_id: str) -> dict[str, Any]:
            """Return the live intake conversation state."""
            try:
                return container.intake.state(claim_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.post("/api/portal/claims/{claim_id}/messages")
        async def portal_message(claim_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Send one customer message to the claims assistant."""
            try:
                return container.intake.reply(claim_id, str(payload.get("text", "")))
            except ValueError as exc:
                status = 404 if "Unknown claim" in str(exc) else 400
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        @app.post("/api/portal/claims/{claim_id}/attachments")
        async def portal_attach(claim_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Attach one photograph, supplied as a data URI."""
            try:
                return container.intake.attach(
                    claim_id,
                    str(payload.get("label", "")),
                    str(payload.get("content_type", "")),
                    str(payload.get("data_uri", "")),
                )
            except ValueError as exc:
                status = 404 if "Unknown claim" in str(exc) else 400
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        @app.post("/api/portal/claims/{claim_id}/submit")
        async def portal_submit(claim_id: str) -> dict[str, Any]:
            """Confirm the claim and hand it to the back office."""
            try:
                return container.intake.submit(claim_id)
            except ValueError as exc:
                status = 404 if "Unknown claim" in str(exc) else 409
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        # ---------------------------------------------------------- customer claim tracking

        @app.get("/api/portal/my-claims")
        async def portal_my_claims(customer_name: str = "") -> list[dict[str, Any]]:
            """Return every submitted claim belonging to the signed-in policyholder."""
            return container.tracking.for_customer(customer_name)

        @app.get("/api/portal/track/{reference}")
        async def portal_track(reference: str, surname: str = "") -> dict[str, Any]:
            """Return the customer's journey, tickmarks and notifications for a claim."""
            try:
                return container.tracking.find(reference, surname)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @app.get("/api/portal/claims/{claim_id}/notifications")
        async def portal_notifications(claim_id: str) -> list[dict[str, Any]]:
            """Return the notification feed for one claim, newest first."""
            return [item.to_dict() for item in reversed(container.repository.claim_notification_list(claim_id))]

        # ---------------------------------------------------------- supplier work orders

        @app.get("/api/claims/{claim_id}/work-orders")
        async def claim_work_orders(claim_id: str) -> list[dict[str, Any]]:
            """Return the supplier work orders raised against one claim."""
            return container.work_orders.board(claim_id)

        @app.post("/api/claims/{claim_id}/dispatch")
        async def dispatch_work(claim_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            """Instruct suppliers for the services a handler has selected."""
            services = payload.get("services")
            if not isinstance(services, list) or not services:
                raise HTTPException(status_code=400, detail="At least one service must be selected")
            try:
                return container.work_orders.dispatch(
                    claim_id, [str(item) for item in services], str(payload.get("actor_id", "demo-user"))
                )
            except ValueError as exc:
                status = 404 if "Unknown claim" in str(exc) else 409
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        @app.post("/api/work-orders/{work_order_id}/advance")
        async def advance_work_order(work_order_id: str, payload: ActorRequest) -> dict[str, Any]:
            """Move a work order to its next status; completion raises the supplier invoice."""
            try:
                return container.work_orders.advance(work_order_id, payload.actor_id)
            except ValueError as exc:
                status = 404 if "Unknown work order" in str(exc) else 409
                raise HTTPException(status_code=status, detail=str(exc)) from exc

        @app.websocket("/ws/invoice-stream")
        async def invoice_stream(websocket: WebSocket) -> None:
            await websocket.accept()
            for invoice in list(container.repository.invoices.values())[:25]:
                await websocket.send_text(
                    json.dumps({"invoice_id": invoice.id, "status": invoice.status, "gross_gbp": invoice.gross_gbp})
                )
            await websocket.close()


app = InvoiceToPayApp.create()
