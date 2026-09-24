"""Append-only audit log with hash-chain verification."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.invoice_to_pay.backend.app.models.domain import AuditEvent
from apps.invoice_to_pay.backend.app.models.domain import DomainClock


class AuditLog:
    """In-memory append-only audit log with deterministic hash chaining."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor: str,
        actor_id: str,
        before_json: dict[str, Any] | None,
        after_json: dict[str, Any] | None,
    ) -> AuditEvent:
        """Append an audit event and return it."""
        previous_hash = self._events[-1].hash if self._events else "GENESIS"
        event_id = f"AUD-{len(self._events) + 1:08d}"
        occurred_at = DomainClock.utc_now()
        payload = {
            "id": event_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "actor": actor,
            "actor_id": actor_id,
            "before_json": before_json or {},
            "after_json": after_json or {},
            "occurred_at": occurred_at,
            "previous_hash": previous_hash,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        event = AuditEvent(hash=digest, **payload)
        self._events.append(event)
        return event

    def list_events(self, entity_id: str | None = None, entity_type: str | None = None) -> list[dict[str, Any]]:
        """List audit events, optionally filtered by entity."""
        events = self._events
        if entity_id is not None:
            events = [event for event in events if event.entity_id == entity_id]
        if entity_type is not None:
            events = [event for event in events if event.entity_type == entity_type]
        return [event.to_dict() for event in events]

    def verify(self) -> bool:
        """Verify the hash chain for all stored events."""
        previous_hash = "GENESIS"
        for event in self._events:
            payload = event.to_dict()
            expected_hash = payload.pop("hash")
            if payload.get("previous_hash") != previous_hash:
                return False
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
            if digest != expected_hash:
                return False
            previous_hash = expected_hash
        return True
