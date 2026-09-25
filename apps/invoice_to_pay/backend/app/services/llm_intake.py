"""Optional Azure OpenAI layer over the deterministic claim intake agent.

Why it is optional: the booth demo has to work with no key, no network and no latency budget, so
the deterministic slot reader in ClaimIntakeService stays the source of truth. When Azure OpenAI
credentials are present this class is consulted *first* for two jobs it is genuinely better at:

  1. reading a rambling, out-of-order human answer into structured slots, and
  2. wording the next question so it never sounds like a form.

Anything the model fails to return is filled by the deterministic reader, and any error at all —
missing key, timeout, rate limit, malformed JSON — is logged and falls back silently. The customer
never sees a broken conversation because the model was unavailable.

Configure with environment variables:
    AZURE_OPENAI_API_KEY        required to enable the layer at all
    AZURE_OPENAI_ENDPOINT       e.g. https://<resource>.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT     the chat deployment name, e.g. gpt-5.5
    AZURE_OPENAI_API_VERSION    defaults to 2025-03-01-preview
    CLAIM_INTAKE_LLM            set to "off" to force the deterministic agent even with a key
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 12
MAX_OUTPUT_TOKENS = 500

SYSTEM_PROMPT = """You are Theo, a UK motor insurance claims intake assistant.

You are filling a fixed set of slots by conversation. Read the customer's latest message in the
context of the question that was just asked, then reply with ONE short question for the next
missing slot.

Rules:
- Interpret answers in context. If the pending slot is incident_location and the customer says
  "Leeds", that IS the location.
- Never ask for a slot that already has a value. Never repeat a question word for word.
- Be warm, brief and British. One question per reply, no bullet lists, no preamble.
- Do not invent values. Only report what the customer actually said.
- Dates: return ISO yyyy-mm-dd when you can work it out, otherwise the customer's own words.
- drivable must be exactly "drivable" or "not drivable".
- vehicle_at_home must be exactly "yes" (the car is at the policyholder's own address) or "no".
  Only ask for incident_location when vehicle_at_home is "no"; if it is "yes" the address covers it.
- The policyholder is already signed in. NEVER ask for their name, address, contact number or
  insurance number, and never return those as slots.

Reply with JSON only, in this shape:
{"extracted": {"<slot>": "<value>", ...}, "reply": "<your next question>"}
Include in "extracted" only slots you learned from THIS message."""


class LlmClaimAssistant:
    """Azure OpenAI-backed slot extraction and reply wording, with graceful degradation."""

    # The policyholder's identity comes from portal sign-in, so the model is never asked to read
    # or invent a name, address, contact number or insurance number.
    SLOTS = (
        "vehicle_registration",
        "incident_type",
        "incident_date",
        "vehicle_at_home",
        "incident_location",
        "description",
        "drivable",
    )

    def __init__(self) -> None:
        self.api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        self.endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        self.deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
        self.api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-03-01-preview").strip()
        self.disabled = os.environ.get("CLAIM_INTAKE_LLM", "").strip().lower() in ("off", "0", "false")
        # Once a call fails the layer stays off for the rest of the process: a booth demo must not
        # pay the timeout on every turn because the endpoint is unreachable.
        self._broken = False

    @property
    def enabled(self) -> bool:
        """Return whether the layer is configured and still healthy."""
        return bool(self.api_key and self.endpoint and self.deployment) and not self.disabled and not self._broken

    def describe(self) -> dict[str, Any]:
        """Return the layer's status, for the settings screen and the health endpoint."""
        return {
            "configured": bool(self.api_key and self.endpoint and self.deployment),
            "enabled": self.enabled,
            "disabled_by_config": self.disabled,
            "unhealthy": self._broken,
            "deployment": self.deployment or None,
            "api_version": self.api_version,
        }

    def interpret(
        self, message: str, pending_slot: str, collected: dict[str, str], missing: list[str]
    ) -> dict[str, Any] | None:
        """Return {"extracted": {...}, "reply": "..."} or None when the layer cannot answer."""
        if not self.enabled:
            return None
        payload = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "pending_slot": pending_slot,
                            "already_collected": {key: value for key, value in collected.items() if value},
                            "still_missing": missing,
                            "customer_message": message,
                        }
                    ),
                },
            ],
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
        }
        raw = self._call(payload)
        if raw is None:
            return None
        return self._parse(raw)

    # ------------------------------------------------------------------ internals

    def _call(self, payload: dict[str, Any]) -> str | None:
        """POST to the Azure OpenAI chat completions endpoint, returning the message content."""
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            logger.error("Azure OpenAI returned HTTP %s: %s", exc.code, detail)
            # Auth and deployment mistakes will not fix themselves; stop retrying.
            if exc.code in (401, 403, 404):
                self._broken = True
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.error("Azure OpenAI call failed, falling back to the deterministic agent: %s", exc)
            self._broken = True
            return None
        except json.JSONDecodeError as exc:
            logger.error("Azure OpenAI returned a non-JSON envelope: %s", exc)
            return None

        choices = body.get("choices") or []
        if not choices:
            logger.error("Azure OpenAI returned no choices: %s", str(body)[:300])
            return None
        return str(choices[0].get("message", {}).get("content", "")) or None

    def _parse(self, raw: str) -> dict[str, Any] | None:
        """Validate the model's JSON, dropping anything that is not a known slot."""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Azure OpenAI reply was not valid JSON: %s", exc)
            return None
        if not isinstance(parsed, dict):
            logger.error("Azure OpenAI reply was not a JSON object")
            return None

        candidate = parsed.get("extracted")
        extracted: dict[str, str] = {}
        if isinstance(candidate, dict):
            for slot, value in candidate.items():
                if slot in self.SLOTS and isinstance(value, (str, int, float)) and str(value).strip():
                    extracted[slot] = str(value).strip()
        # A model-invented drivable value would break the triage rules downstream.
        if extracted.get("drivable") not in (None, "drivable", "not drivable"):
            extracted.pop("drivable", None)

        reply = parsed.get("reply")
        return {
            "extracted": extracted,
            "reply": str(reply).strip() if isinstance(reply, str) and reply.strip() else "",
        }
