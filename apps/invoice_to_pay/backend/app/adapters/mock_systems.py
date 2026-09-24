"""Mock external adapters for ICE, payment, email and supplier portal integrations."""

from __future__ import annotations

import time
from abc import ABC
from abc import abstractmethod
from typing import Any


class PaymentAdapter(ABC):
    """Interface for payment workflow adapters."""

    @abstractmethod
    def release(self, invoice_id: str, amount_gbp: float) -> dict[str, Any]:
        """Release payment and return adapter response."""


class IntegrationAdapter(PaymentAdapter):
    """Mock direct finance integration adapter."""

    def release(self, invoice_id: str, amount_gbp: float) -> dict[str, Any]:
        """Simulate direct integration payment release."""
        return {"status": "released", "path": "integration", "reference": f"PAY-INT-{invoice_id}", "amount_gbp": amount_gbp}


class RpaAdapter(PaymentAdapter):
    """Mock RPA adapter for suppliers without direct integration."""

    def release(self, invoice_id: str, amount_gbp: float) -> dict[str, Any]:
        """Simulate RPA payment release."""
        time.sleep(0.01)
        return {"status": "released", "path": "rpa", "reference": f"PAY-RPA-{invoice_id}", "amount_gbp": amount_gbp}


class MockIceAdapter:
    """Mock ICE write-back adapter."""

    def write_invoice_status(self, invoice_id: str, status: str, reference: str | None = None) -> dict[str, Any]:
        """Write an invoice status to mock ICE."""
        return {"invoice_id": invoice_id, "status": status, "reference": reference, "ice_writeback_status": "confirmed"}


class NotificationAdapter:
    """Mock outbound communication adapter."""

    def send(self, invoice_id: str, audience: str, status: str, content: str) -> dict[str, Any]:
        """Send a mock notification."""
        return {"invoice_id": invoice_id, "audience": audience, "status": status, "content": content, "sent": True}


class PaymentAdapterFactory:
    """Factory for selecting supplier-specific payment adapter paths."""

    @staticmethod
    def create(path: str) -> PaymentAdapter:
        """Return the adapter for a configured path."""
        if path == "rpa":
            return RpaAdapter()
        return IntegrationAdapter()
