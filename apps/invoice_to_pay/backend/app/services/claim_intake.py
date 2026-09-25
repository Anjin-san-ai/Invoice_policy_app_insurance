"""Conversational claim intake for the customer self-service portal.

The assistant is a deterministic slot-filling agent rather than an LLM call. That is a demo
decision, not a limitation of the design: the prototype has to answer instantly, run without an
Azure OpenAI key, and produce the same transcript every time so the back-office screens can be
demonstrated repeatably. Swapping this class for an LLM-backed one later only changes how slots
get filled.

Answers are interpreted **in the context of the question just asked**, which is what stops the
agent looping. A bare "Leeds" is not a location to a context-free parser, but it obviously is when
the question was "where did it happen?". Every slot therefore has a directed reader that is tried
first, and only then the opportunistic readers that scan any message for anything recognisable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from apps.invoice_to_pay.backend.app.models.domain import SERVICE_TO_SUPPLIER_TYPE
from apps.invoice_to_pay.backend.app.models.domain import Claim
from apps.invoice_to_pay.backend.app.models.domain import ClaimAttachment
from apps.invoice_to_pay.backend.app.models.domain import DomainClock
from apps.invoice_to_pay.backend.app.models.domain import IntakeTurn
from apps.invoice_to_pay.backend.app.services.llm_intake import LlmClaimAssistant

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 6 * 1024 * 1024
MAX_ATTACHMENTS = 8
ACCEPTED_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml")

# Words that mean "I do not know" or "skip", for the slots where that is acceptable.
SKIP_WORDS = ("skip", "not sure", "dont know", "don't know", "no idea", "unknown", "prefer not")


class ClaimIntakeService:
    """Drives the customer-facing claim conversation and turns it into a real claim record."""

    # Who the policyholder is arrives from the portal sign-in, so the assistant never asks for the
    # name, address, contact number or insurance number. It only asks what it cannot already know:
    # the vehicle and the incident.
    REQUIRED_SLOTS = (
        "vehicle_registration",
        "incident_type",
        "incident_date",
        "vehicle_at_home",
        # Only asked when the vehicle is not at the policyholder's address; see _missing_slots.
        "incident_location",
        "description",
        "drivable",
        # Asked last, and optional: the customer can decline and still submit.
        "photos",
    )

    # Slots a customer is allowed to decline; the claim is still actionable without them.
    SKIPPABLE_SLOTS = ()

    # After this many failed attempts at one slot the agent stops asking, records that a handler
    # must confirm it, and moves on. Looping on one question is what makes a bot feel broken.
    MAX_ASK_ATTEMPTS = 3

    # Words that are never a person's name, so a mistimed answer is not recorded as one.
    NON_NAME_WORDS = frozenset(
        {
            "yes", "no", "yeah", "nope", "today", "yesterday", "tomorrow", "morning", "afternoon",
            "evening", "night", "week", "month", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "crash", "crashed", "accident", "collision", "stolen",
            "theft", "fire", "flood", "storm", "damage", "damaged", "dented", "skip", "none",
            "car", "van", "vehicle", "drivable", "driveable", "help", "hello", "hi", "thanks",
        }
    )

    INCIDENT_KEYWORDS: dict[str, tuple[str, ...]] = {
        "collision": ("collision", "crash", "crashed", "collided", "rear-end", "rear ended", "rear-ended",
                      "bump", "shunt", "hit me", "hit my", "ran into", "accident"),
        "theft": ("theft", "stolen", "stole", "broke in", "break-in", "burglary", "taken"),
        "vandalism": ("vandal", "keyed", "scratched", "smashed window", "damaged deliberately"),
        "weather": ("flood", "flooded", "storm", "hail", "wind", "branch", "tree fell", "fell on"),
        "fire": ("fire", "burnt", "burned", "smoke", "flames"),
        "glass": ("windscreen", "windshield", "chipped", "cracked screen", "stone chip"),
        "animal": ("deer", "dog ran", "animal", "badger", "fox"),
    }

    SEVERITY_KEYWORDS: dict[str, tuple[str, ...]] = {
        "total_loss": ("written off", "write-off", "total loss", "beyond repair", "burnt out"),
        "major": ("airbag", "undrivable", "not drivable", "cannot drive", "can't drive", "major",
                  "severe", "wheel came", "towed", "steering"),
        "minor": ("scratch", "scuff", "small dent", "minor", "chip", "scrape"),
    }

    def __init__(self, repository: Any, assistant: Any | None = None) -> None:
        self.repository = repository
        # When Azure OpenAI is configured this reads the customer's answers first; the
        # deterministic readers below stay as the fallback and the safety net.
        self.assistant = assistant if assistant is not None else LlmClaimAssistant()

    # ------------------------------------------------------------------ conversation

    def start(self, profile: dict[str, str] | None = None) -> dict[str, Any]:
        """Open a draft claim against a signed-in policyholder and return the first turn."""
        details = profile or {}
        claim = self._new_draft(details)
        first = (claim.customer_name or "").split(" ")[0]
        greeting = (
            f"Hi{' ' + first if first else ''}, I'm Theo. I already have your policy details, so I "
            "just need a few things about the vehicle and what happened.\n\n"
            "What's the vehicle registration?"
        )
        claim.pending_slot = "vehicle_registration"
        self._say(
            claim.id,
            "assistant",
            greeting,
            [
                f"Opened a draft claim for {claim.customer_name or 'the policyholder'}",
                f"Policy details taken from sign-in ({claim.insurance_number or 'no insurance number'})",
                "Asked for the vehicle registration",
            ],
        )
        self.repository.persist()
        return self.state(claim.id)

    def reply(self, claim_id: str, text: str) -> dict[str, Any]:
        """Record a customer message, interpret it against the pending question, and answer."""
        claim = self._require(claim_id)
        message = (text or "").strip()
        if not message:
            raise ValueError("An empty message cannot be processed")
        self._say(claim_id, "customer", message, [])

        asked = claim.pending_slot
        reasoning: list[str] = []

        # 0. Let the language model read the answer first, when one is configured. Whatever it
        #    cannot fill still goes through the deterministic readers below.
        llm_reply = ""
        answered = False
        outcome = self.assistant.interpret(message, asked, self._collected(claim), self._missing_slots(claim))
        if outcome is not None:
            applied = self._apply_llm_slots(claim, outcome.get("extracted", {}))
            if applied:
                reasoning.append("Azure OpenAI read: " + ", ".join(f"{k.replace('_', ' ')}={v}" for k, v in applied.items()))
            answered = asked in applied
            llm_reply = str(outcome.get("reply", ""))

        # 1. Read the answer as an answer to the question that was actually asked.
        if asked and not answered:
            answered = self._read_for_slot(claim, asked, message)
            if answered:
                reasoning.append(f"Read \"{self._shorten(message)}\" as {asked.replace('_', ' ')}")

        # 2. Then pick up anything else the message happens to contain.
        for key, value in self._read_opportunistically(claim, message, skip=asked).items():
            reasoning.append(f"Also noted {key.replace('_', ' ')}: {value}")

        missing = self._missing_slots(claim)
        if missing:
            nxt = missing[0]
            if nxt == asked and not answered:
                claim.ask_attempts += 1
                if claim.ask_attempts >= self.MAX_ASK_ATTEMPTS:
                    # Give up on this slot rather than loop. The claim is still worth taking; the
                    # handler picks the detail up on their follow-up call.
                    self._defer(claim, nxt)
                    reasoning.append(f"Gave up on {nxt.replace('_', ' ')} after {claim.ask_attempts} attempts")
                    remaining = self._missing_slots(claim)
                    claim.ask_attempts = 0
                    claim.pending_slot = remaining[0] if remaining else ""
                    handover = (
                        f"No problem — I'll flag {self._slot_label(nxt)} for your handler to confirm when they call.\n\n"
                        + (self._question_for(claim.pending_slot, claim) if claim.pending_slot else "")
                    ).strip()
                    self._say(claim_id, "assistant", handover, reasoning)
                    self.repository.persist()
                    return self.state(claim_id)
                # Re-ask, but differently and with an example: never the same words twice.
                reasoning.append(f"Could not read that as {nxt.replace('_', ' ')}; clarifying")
                question = self._clarify(nxt, claim.ask_attempts)
            else:
                claim.ask_attempts = 0
                # Prefer the model's wording when it asked for the slot we actually need next.
                question = llm_reply or self._question_for(nxt, claim)
            claim.pending_slot = nxt
            self._say(claim_id, "assistant", question, reasoning)
            self.repository.persist()
            return self.state(claim_id)

        self._triage(claim)
        claim.pending_slot = ""
        claim.ask_attempts = 0
        reasoning.append(f"Triaged as {claim.severity}; will request {', '.join(claim.recommended_services)}")
        self._say(claim_id, "assistant", self._summary_for(claim), reasoning)
        self.repository.persist()
        return self.state(claim_id)

    def attach(self, claim_id: str, label: str, content_type: str, data_uri: str) -> dict[str, Any]:
        """Attach one photograph to the claim."""
        claim = self._require(claim_id)
        existing = self.repository.claim_attachments.get(claim.id, [])
        if len(existing) >= MAX_ATTACHMENTS:
            raise ValueError(f"A claim accepts at most {MAX_ATTACHMENTS} photographs")
        if content_type not in ACCEPTED_IMAGE_TYPES:
            raise ValueError(f"Unsupported image type {content_type}")
        if len(data_uri.encode("utf-8")) > MAX_ATTACHMENT_BYTES:
            raise ValueError("That photograph is too large; please upload one under 6 MB")

        index = len(existing) + 1
        attachment = ClaimAttachment(
            id=f"{claim.id}-IMG-{index:02d}",
            claim_id=claim.id,
            label=label or f"Photograph {index}",
            content_type=content_type,
            data_uri=data_uri,
            uploaded_at=DomainClock.utc_now(),
            source="customer",
            ai_tags=self._tag_photo(label, claim),
        )
        self.repository.add_claim_attachment(attachment)
        # An upload answers the photographs question, so the conversation can move to the summary.
        claim.photos_decision = "added"
        if claim.pending_slot == "photos":
            claim.pending_slot = ""
        remaining = self._missing_slots(claim)
        if remaining:
            message = f"Got it — {index} photograph{'s' if index > 1 else ''} saved. Add more if you have them."
        else:
            self._triage(claim)
            message = (
                f"Got it — {index} photograph{'s' if index > 1 else ''} saved. "
                "Add more if you like, or press Submit claim and I'll give you your reference."
            )
        self._say(
            claim.id,
            "assistant",
            message,
            [f"Stored {attachment.id}", f"Auto-tagged as {', '.join(attachment.ai_tags)}"],
        )
        self.repository.persist()
        return self.state(claim.id)

    def submit(self, claim_id: str) -> dict[str, Any]:
        """Confirm the claim, move it into the back-office queue and return the claim reference."""
        claim = self._require(claim_id)
        missing = self._missing_slots(claim)
        if missing:
            raise ValueError(f"The claim is not complete; still needed: {', '.join(missing)}")

        self._triage(claim)
        before = claim.to_dict()
        claim.workflow_status = "awaiting_triage"
        claim.status = "open"
        claim.pending_slot = ""
        self.repository.audit.append(
            "claim", claim.id, "claim_submitted_by_customer", "user", claim.customer_id, before, claim.to_dict()
        )
        photos = len(self.repository.claim_attachments.get(claim.id, []))
        self._say(
            claim.id,
            "assistant",
            f"All done. Your claim reference is {claim.id}.\n\n"
            f"A handler will review the {photos} photograph{'s' if photos != 1 else ''} you sent and "
            "instruct the suppliers you need. You can track it any time from the Track a claim tab.",
            ["Claim submitted to the back office", "Handler notified for triage"],
        )
        self.repository.add_claim_notification(
            claim.id,
            "Claim received",
            f"Thanks {claim.customer_name or 'there'} — we have your claim and a handler is reviewing it now.",
            "info",
        )
        self.repository.persist()
        logger.info("Customer claim %s submitted with %d photographs", claim.id, photos)
        return self.state(claim.id)

    def state(self, claim_id: str) -> dict[str, Any]:
        """Return the whole conversation state the portal needs to render."""
        claim = self._require(claim_id)
        missing = self._missing_slots(claim)
        return {
            "claim": claim.to_dict(),
            "turns": [turn.to_dict() for turn in self.repository.intake_turns.get(claim.id, [])],
            "attachments": [item.to_dict() for item in self.repository.claim_attachments.get(claim.id, [])],
            "missing_slots": missing,
            "pending_slot": claim.pending_slot,
            "collected": self._collected(claim),
            "ready_to_submit": not missing,
            "submitted": claim.workflow_status != "draft",
            "quick_replies": self._quick_replies(claim.pending_slot or (missing[0] if missing else "")),
        }

    # ------------------------------------------------------------------ slot reading

    def _read_for_slot(self, claim: Claim, slot: str, message: str) -> bool:
        """Interpret the message as the answer to `slot`. Returns whether it filled the slot."""
        lowered = message.lower()
        if slot in self.SKIPPABLE_SLOTS and any(word in lowered for word in SKIP_WORDS):
            setattr(claim, slot, "not supplied")
            return True

        if slot == "vehicle_registration":
            reg = self._find_registration(message)
            if reg:
                claim.vehicle_registration = reg
                return True
            return False

        if slot == "incident_type":
            found = self._classify_incident(lowered)
            if found:
                claim.incident_type = found
            if len(message) >= 8:
                claim.description = self._append(claim.description, message)
                return True
            return False

        if slot == "incident_date":
            when = self._find_date(message)
            if when:
                claim.incident_date = when
                return True
            return False

        if slot == "vehicle_at_home":
            at_home = self._find_at_home(lowered)
            if at_home:
                claim.vehicle_at_home = at_home
                if at_home == "yes":
                    # No point asking where it is when the customer just told us it is at the
                    # address they already gave.
                    claim.incident_location = claim.address or "At the policyholder's address"
                return True
            return False

        if slot == "incident_location":
            where = self._find_location(message) or self._as_place(message)
            if where:
                claim.incident_location = where
                return True
            return False

        if slot == "description":
            if len(message) >= 10:
                claim.description = self._append(claim.description, message)
                return True
            return False

        if slot == "drivable":
            state = self._find_drivable(lowered)
            if state:
                claim.vehicle_drivable = state
                return True
            return False

        if slot == "photos":
            # Photographs are optional, so declining is a complete answer. An upload arrives
            # through attach() instead, which marks the slot answered from there.
            if self._declines_photos(lowered):
                claim.photos_decision = "declined"
                return True
            return False

        return False

    @staticmethod
    def _declines_photos(lowered: str) -> bool:
        """Return whether the customer is turning down the offer to add photographs."""
        stripped = lowered.strip(" .!")
        if stripped in ("no", "nope", "skip", "none", "no thanks", "not now"):
            return True
        phrases = ("skip", "no photo", "no pictures", "haven't", "have not", "dont have", "don't have",
                   "not got", "no thanks", "later", "move on", "carry on", "that's all", "thats all")
        return any(phrase in lowered for phrase in phrases)

    def _apply_llm_slots(self, claim: Claim, extracted: dict[str, str]) -> dict[str, str]:
        """Write the model's extracted slots onto the claim, without overwriting known values.

        The model is trusted to read language, not to be authoritative: a value it returns for a
        slot that is already filled is ignored, and free-text fields still go through the same
        accumulation rules as the deterministic path.
        """
        applied: dict[str, str] = {}
        for slot, value in extracted.items():
            if slot == "vehicle_registration" and not claim.vehicle_registration:
                claim.vehicle_registration = value.upper()
            elif slot == "incident_type":
                claim.incident_type = value
            elif slot == "incident_date" and not claim.incident_date:
                claim.incident_date = value
            elif slot == "incident_location" and not claim.incident_location:
                claim.incident_location = value
            elif slot == "description":
                claim.description = self._append(claim.description, value)
            elif slot == "drivable" and not claim.vehicle_drivable:
                claim.vehicle_drivable = value
            else:
                continue
            applied[slot] = value
        # incident_type on its own does not satisfy the narrative slot, so mirror the free text in.
        if "incident_type" in applied and "description" not in applied and len(claim.description) < 8:
            claim.description = self._append(claim.description, f"Reported as {applied['incident_type']}.")
        return applied

    def _read_opportunistically(self, claim: Claim, message: str, skip: str) -> dict[str, str]:
        """Fill any other empty slot this message clearly contains."""
        found: dict[str, str] = {}
        lowered = message.lower()

        if skip != "vehicle_registration" and not claim.vehicle_registration:
            reg = self._find_registration(message)
            if reg:
                claim.vehicle_registration = reg
                found["vehicle_registration"] = reg

        if skip != "incident_date" and not claim.incident_date:
            when = self._find_date(message)
            if when:
                claim.incident_date = when
                found["incident_date"] = when

        # The vehicle's whereabouts is only read opportunistically once the customer has said it is
        # NOT at home. Otherwise the postcode inside their home address gets recorded as the
        # incident location, and the agent then skips asking where the car actually is.
        if skip != "incident_location" and not claim.incident_location and claim.vehicle_at_home == "no":
            where = self._find_location(message)
            if where:
                claim.incident_location = where
                found["incident_location"] = where

        if skip != "drivable" and not claim.vehicle_drivable:
            state = self._find_drivable(lowered)
            if state:
                claim.vehicle_drivable = state
                found["drivable"] = state

        # Incident classification is free to improve at any point in the conversation.
        if claim.incident_type in ("", "collision"):
            classified = self._classify_incident(lowered)
            if classified and classified != claim.incident_type:
                claim.incident_type = classified
                found["incident_type"] = classified

        return found

    def _missing_slots(self, claim: Claim) -> list[str]:
        """Return the required slots still unfilled, in the order the agent asks for them.

        incident_location is conditional: it is only asked when the vehicle is somewhere other
        than the policyholder's address, because otherwise the address already answers it.
        """
        filled = {
            "vehicle_registration": bool(claim.vehicle_registration),
            "incident_type": len(claim.description) >= 8,
            "incident_date": bool(claim.incident_date),
            "vehicle_at_home": bool(claim.vehicle_at_home),
            "incident_location": claim.vehicle_at_home == "yes" or bool(claim.incident_location),
            "description": len(claim.description) >= 20,
            "drivable": bool(claim.vehicle_drivable),
            "photos": bool(claim.photos_decision) or bool(self.repository.claim_attachments.get(claim.id)),
        }
        return [slot for slot in self.REQUIRED_SLOTS if not filled.get(slot)]

    @staticmethod
    def _find_at_home(lowered: str) -> str:
        """Return "yes" when the vehicle is at the policyholder's address, "no" when elsewhere."""
        elsewhere = ("somewhere else", "elsewhere", "not at home", "not home", "at work", "garage",
                     "car park", "roadside", "street", "compound", "pound", "recovered to",
                     "still there", "at the scene", "work")
        home = ("at home", "home", "my house", "the house", "my drive", "driveway", "outside my",
                "on my drive", "at my address", "yes")
        if any(phrase in lowered for phrase in elsewhere):
            return "no"
        if any(phrase in lowered for phrase in home):
            return "yes"
        stripped = lowered.strip(" .!")
        if stripped in ("no", "nope"):
            return "no"
        return ""

    @staticmethod
    def _slot_label(slot: str) -> str:
        """Return the customer-facing name of a slot."""
        return {
            "vehicle_registration": "the registration",
            "incident_type": "what happened",
            "incident_date": "the date",
            "vehicle_at_home": "where the vehicle is",
            "incident_location": "the location",
            "description": "the damage",
            "drivable": "whether it is drivable",
        }.get(slot, slot.replace("_", " "))

    def _defer(self, claim: Claim, slot: str) -> None:
        """Record a slot as needing handler confirmation so the conversation can move on."""
        placeholder = "to be confirmed by handler"
        fields = {
            "vehicle_registration": "vehicle_registration",
            "incident_date": "incident_date",
            "incident_location": "incident_location",
            "vehicle_at_home": "vehicle_at_home",
            "drivable": "vehicle_drivable",
        }
        field_name = fields.get(slot)
        if field_name is not None:
            setattr(claim, field_name, placeholder)
            if slot == "customer_name":
                claim.reported_by = placeholder
        elif slot in ("incident_type", "description"):
            claim.description = self._append(claim.description, "Damage detail to be confirmed by the handler.")
        logger.info("Deferred slot %s on claim %s to the handler", slot, claim.id)

    def _collected(self, claim: Claim) -> dict[str, str]:
        """Return the slot values gathered so far, for the portal's live summary card."""
        return {
            "vehicle_registration": claim.vehicle_registration,
            "incident_type": claim.incident_type if claim.description else "",
            "incident_date": claim.incident_date,
            "vehicle_at_home": claim.vehicle_at_home,
            "incident_location": claim.incident_location,
            "description": claim.description,
            "drivable": claim.vehicle_drivable,
        }

    # ------------------------------------------------------------------ readers

    @staticmethod
    def _append(existing: str, addition: str) -> str:
        """Accumulate narrative across turns without repeating the same sentence."""
        if addition in existing:
            return existing
        return f"{existing} {addition}".strip() if existing else addition

    @staticmethod
    def _shorten(message: str) -> str:
        """Return a short echo of the customer's words for the reasoning trail."""
        return message if len(message) <= 42 else f"{message[:39]}..."

    @classmethod
    def _classify_incident(cls, lowered: str) -> str:
        """Return the incident type whose keywords appear in the message, if any."""
        for incident_type, keywords in cls.INCIDENT_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return incident_type
        return ""

    @staticmethod
    def _find_name(message: str) -> str:
        """Return a self-reported name when the message introduces one."""
        match = re.search(
            r"\b(?:my name is|my name's|i am|i'm|this is|it's|its)\s+"
            # Each part is a word or a single initial, so middle names and initials are captured.
            r"([A-Za-z][A-Za-z'-]*\.?(?:\s+[A-Za-z][A-Za-z'-]*\.?){0,4})",
            message,
            re.IGNORECASE,
        )
        if not match:
            return ""
        parts = match.group(1).replace(".", " ").split()
        return " ".join(part.title() if len(part) > 1 else part.upper() for part in parts)

    @classmethod
    def _as_name(cls, message: str) -> str:
        """Accept a bare "Priya Raman" as the name when that is what was asked for.

        A permissive "any short alphabetic string is a name" rule reads "yesterday" as a surname,
        so anything that parses as another slot's answer, or is a known filler word, is rejected
        and the agent asks again instead of recording nonsense.
        """
        if cls._find_date(message) or cls._find_phone(message) or cls._find_registration(message):
            return ""
        if cls._find_drivable(message.lower()):
            return ""
        # Full stops are kept out of the character filter but initials are preserved, so
        # "John M. Smith" and "J.M. Patel" both survive as names.
        cleaned = re.sub(r"[^A-Za-z\s.'-]", "", message).replace(".", " ").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        words = cleaned.split()
        # Up to five parts covers a first name, one or two middle names and a double-barrelled
        # surname. A single-character part is a middle initial, which is legitimate.
        if not 1 <= len(words) <= 5 or len(cleaned) > 64:
            return ""
        if any(word.lower() in cls.NON_NAME_WORDS for word in words):
            return ""
        return " ".join(word.title() if len(word) > 1 else word.upper() for word in words)

    @staticmethod
    def _find_phone(message: str) -> str:
        """Return a UK mobile or landline number found in the message."""
        digits = re.sub(r"[^\d+]", "", message)
        match = re.search(r"(?:\+44|0)\d{9,10}", digits)
        if match:
            return match.group(0)
        # Accept a bare run of 10-11 digits, which is what people usually type.
        bare = re.search(r"\d{10,11}", digits)
        return bare.group(0) if bare else ""

    @staticmethod
    def _find_registration(message: str) -> str:
        """Return a UK vehicle registration from the message."""
        upper = message.upper()
        current = re.search(r"\b[A-Z]{2}\d{2}\s?[A-Z]{3}\b", upper)
        if current:
            return re.sub(r"\s+", " ", current.group(0)).strip()
        older = re.search(r"\b[A-Z]\d{1,3}\s?[A-Z]{3}\b", upper)
        if older:
            return older.group(0)
        prefixless = re.search(r"\b[A-Z]{3}\s?\d{1,4}\b", upper)
        return prefixless.group(0) if prefixless else ""

    @staticmethod
    def _find_date(message: str) -> str:
        """Return an ISO date, a recognised relative day, or an empty string."""
        iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", message)
        if iso:
            return iso.group(0)
        slashed = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", message)
        if slashed:
            day, month, year = slashed.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        lowered = message.lower()
        for phrase in ("this morning", "this afternoon", "this evening", "today", "yesterday",
                       "last night", "this week", "last week", "last month"):
            if phrase in lowered:
                return phrase
        spelled = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\b",
            lowered,
        )
        if spelled:
            return f"{spelled.group(1)} {spelled.group(2).title()}"
        weekday = re.search(r"\b(?:last\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lowered)
        return weekday.group(0) if weekday else ""

    @staticmethod
    def _find_location(message: str) -> str:
        """Return a UK postcode, a named road, or a prepositional place phrase."""
        postcode = re.search(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b", message.upper())
        if postcode:
            return postcode.group(0)
        road = re.search(r"\b([AM]\d{1,4})\b", message.upper())
        if road:
            return f"the {road.group(1)}"
        place = re.search(r"\b(?:in|at|near|on|outside)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})", message)
        if place:
            return place.group(1)
        return ""

    @staticmethod
    def _as_place(message: str) -> str:
        """Accept a bare "Leeds" or "the multi-storey car park" as the location.

        This is the specific gap that made the agent loop: a context-free parser rejects a
        one-word answer, so the same question came back forever.
        """
        cleaned = message.strip().rstrip(".")
        if 2 <= len(cleaned) <= 80:
            return cleaned
        return ""

    @staticmethod
    def _find_drivable(lowered: str) -> str:
        """Return whether the vehicle can be driven, when the message says so."""
        immobile = ("not drivable", "undrivable", "cannot be driven", "can't be driven", "cannot drive",
                    "can't drive", "cant drive", "won't start", "wont start", "towed", "recovered",
                    "needs recovering", "not driveable", "no it", "immobile")
        mobile = ("still drivable", "drivable", "driveable", "drove it", "drove home", "can drive",
                  "can be driven", "yes it", "it drives", "fine to drive")
        if any(phrase in lowered for phrase in immobile):
            return "not drivable"
        if any(phrase in lowered for phrase in mobile):
            return "drivable"
        # Bare yes/no, which is what a one-word reply to this question looks like.
        stripped = lowered.strip(" .!")
        if stripped in ("no", "nope", "negative"):
            return "not drivable"
        if stripped in ("yes", "yeah", "yep", "aye"):
            return "drivable"
        return ""

    # ------------------------------------------------------------------ triage and wording

    def _triage(self, claim: Claim) -> None:
        """Set severity, the recommended services and a handler-facing summary."""
        haystack = f"{claim.description} {claim.vehicle_drivable}".lower()
        claim.severity = "moderate"
        for severity, keywords in self.SEVERITY_KEYWORDS.items():
            if any(keyword in haystack for keyword in keywords):
                claim.severity = severity  # type: ignore[assignment]
                break

        immobile = claim.vehicle_drivable == "not drivable"
        services = ["repair"]
        if immobile:
            services.append("recovery")
        if immobile or claim.severity in ("major", "total_loss"):
            services.append("hire")
        if immobile and claim.severity in ("major", "total_loss"):
            services.append("storage")
        claim.recommended_services = [service for service in services if service in SERVICE_TO_SUPPLIER_TYPE]

        photos = len(self.repository.claim_attachments.get(claim.id, []))
        claim.triage_summary = (
            f"{claim.incident_type.replace('_', ' ').title()} on {claim.incident_date or 'an unstated date'} "
            f"at {claim.incident_location or 'an unstated location'}. Vehicle "
            f"{claim.vehicle_registration or 'registration not supplied'} is "
            f"{'not drivable' if immobile else 'drivable'}. Severity assessed as "
            f"{claim.severity.replace('_', ' ')}. {photos} photograph{'s' if photos != 1 else ''} supplied."
        )
        if claim.reserve_gbp == 0.0:
            claim.reserve_gbp = {"minor": 900.0, "moderate": 3200.0, "major": 7400.0, "total_loss": 11500.0}.get(
                claim.severity, 3200.0
            )

    @staticmethod
    def _question_for(slot: str, claim: Claim) -> str:
        """Return the next question, phrased around what the agent already knows."""
        known = claim.incident_type.replace("_", " ")
        questions = {
            "vehicle_registration": "What's the vehicle registration?",
            "incident_type": "Now the incident — tell me in your own words what happened.",
            "incident_date": f"When did the {known or 'incident'} happen?",
            "vehicle_at_home": "Where is the vehicle right now — at home, or somewhere else?",
            "incident_location": "Whereabouts is it? A postcode, a road or the name of the place is fine.",
            "description": "Which parts of the vehicle are damaged?",
            "drivable": "Can the vehicle still be driven, or does it need recovering?",
            "photos": (
                "Last thing — do you have any photographs of the damage? Tap the camera to add them, "
                "or say skip and your handler will arrange an inspection."
            ),
        }
        return questions.get(slot, "Could you tell me a little more?")

    @staticmethod
    def _clarify(slot: str, attempt: int) -> str:
        """Return a re-ask that is worded differently and gives an example.

        The agent must never repeat itself verbatim: an unchanged question reads as a broken bot.
        """
        ladders = {
            "vehicle_registration": [
                "That didn't look like a registration. It's on the number plate, for example AB12 CDE.",
                "I need the number plate — two letters, two numbers, three letters, like LS19 XYZ.",
            ],
            "incident_type": [
                "Tell me a bit more about what happened — even one sentence helps.",
                "In your own words: what happened to the vehicle?",
            ],
            "incident_date": [
                "I couldn't read a date there. You can say \"yesterday\", \"last Tuesday\", or 24/03/2026.",
                "Roughly when was it? A day of the week or a date is fine.",
            ],
            "vehicle_at_home": [
                "Sorry — is the car at your home address, or somewhere else? \"Home\" or \"somewhere else\" is fine.",
                "Just so we know where to collect it: is it at home, yes or no?",
            ],
            "incident_location": [
                "Where is it? A town, a postcode or a road number all work.",
                "Just the place is fine — for example \"Leeds\", \"LS1 4AP\" or \"the M1\".",
            ],
            "description": [
                "Which panels or parts took the damage? For example \"rear bumper and boot\".",
                "A short description of the damage is all I need.",
            ],
            "drivable": [
                "Sorry — can you still drive it? Reply \"it drives\" or \"it needs recovering\".",
                "Just so I get the right help out: is the vehicle driveable, yes or no?",
            ],
        }
        options = ladders.get(slot, ["Could you rephrase that for me?"])
        return options[min(attempt - 1, len(options) - 1)]

    @staticmethod
    def _summary_for(claim: Claim) -> str:
        """Return the pre-submission summary the customer confirms."""
        return (
            "That's everything I need. Here's what I have:\n\n"
            f"• Vehicle: {claim.vehicle_registration}\n"
            f"• Incident: {claim.incident_type.replace('_', ' ')} on {claim.incident_date}\n"
            f"• Where: {claim.incident_location}\n"
            f"• Assessment: {claim.severity.replace('_', ' ')}\n"
            f"• I'll request: {', '.join(claim.recommended_services)}\n\n"
            "Press Submit claim and I'll give you your reference."
        )

    @staticmethod
    def _quick_replies(slot: str) -> list[str]:
        """Return tappable suggestions for the slot currently being asked about."""
        if not slot:
            return ["That all looks right", "I have more photos to add"]
        options = {
            "incident_type": ["Someone rear-ended me", "My car was stolen", "Storm damage", "Cracked windscreen"],
            "incident_date": ["Today", "Yesterday", "Last week"],
            "vehicle_at_home": ["It's at home", "It's somewhere else"],
            "incident_location": ["In a car park", "At the roadside", "At a garage"],
            "description": ["Rear bumper and boot", "Front wing and headlight", "Nearside doors"],
            "drivable": ["It still drives", "It needs recovering"],
            "photos": ["Skip photos"],
        }
        return options.get(slot, [])

    @staticmethod
    def _tag_photo(label: str, claim: Claim) -> list[str]:
        """Return descriptive tags for an uploaded photograph.

        Tagging is derived from the label and the claim context rather than from pixels; a real
        deployment would call a vision model here.
        """
        lowered = (label or "").lower()
        tags = [claim.incident_type]
        for part in ("front", "rear", "nearside", "offside", "bumper", "door", "wing", "windscreen", "wheel", "roof"):
            if part in lowered:
                tags.append(part)
        if len(tags) == 1:
            tags.append("damage overview")
        return tags

    # ------------------------------------------------------------------ internals

    def _new_draft(self, profile: dict[str, str]) -> Claim:
        """Create and register a draft claim against the signed-in policyholder."""
        claim_id = self.repository.next_claim_id()
        sequence = int(claim_id.split("-")[-1])
        name = str(profile.get("customer_name", "")).strip()
        insurance_number = str(profile.get("insurance_number", "")).strip().upper()
        # The insurance number is the policy reference the customer holds, so use it to bind the
        # claim to a real seeded policy where it resolves, and fall back to any policy otherwise.
        policy = self.repository.policy_for_insurance_number(insurance_number) or self.repository.any_policy()
        claim = Claim(
            id=claim_id,
            invoice_claim_ref=f"Invoice-{202600000 + sequence}",
            policy_id=policy.id if policy is not None else "POL-00001",
            customer_id=f"CUS-{sequence:05d}",
            incident_date="",
            status="draft",
            reserve_gbp=0.0,
            paid_to_date_gbp=0.0,
            origin="customer_portal",
            customer_name=name,
            contact_number=str(profile.get("contact_number", "")).strip(),
            contact_email=str(profile.get("contact_email", "")).strip(),
            address=str(profile.get("address", "")).strip(),
            insurance_number=insurance_number,
            reported_by=name,
            report_channel="customer_portal",
            reported_at=DomainClock.utc_now(),
            workflow_status="draft",
        )
        self.repository.add_claim(claim, actor_id="customer_portal", event_type="claim_draft_opened")
        return claim

    def _require(self, claim_id: str) -> Claim:
        """Return the claim or raise for an unknown id."""
        claim = self.repository.claims.get(claim_id)
        if claim is None:
            raise ValueError(f"Unknown claim id {claim_id}")
        return claim

    def _say(self, claim_id: str, role: str, text: str, reasoning: list[str]) -> None:
        """Append one turn to the transcript."""
        turns = self.repository.intake_turns.get(claim_id, [])
        turn = IntakeTurn(
            id=f"{claim_id}-T{len(turns) + 1:03d}",
            claim_id=claim_id,
            role=role,
            text=text,
            at=DomainClock.utc_now(),
            reasoning=reasoning,
        )
        self.repository.add_intake_turn(turn)
