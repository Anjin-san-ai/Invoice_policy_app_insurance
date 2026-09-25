"""Deterministic synthetic data generator for the invoice-to-pay prototype."""

from __future__ import annotations

import base64
import json
import random
import sys
from dataclasses import asdict
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

# run.md documents running this file directly, which leaves the repository root off sys.path, so it
# is added before the apps.* imports below. Mirrors the same bootstrap in evaluation/harness.py.
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.invoice_to_pay.backend.app.models.domain import Authorisation
from apps.invoice_to_pay.backend.app.models.domain import Claim
from apps.invoice_to_pay.backend.app.models.domain import ClaimAttachment
from apps.invoice_to_pay.backend.app.models.domain import IntakeTurn
from apps.invoice_to_pay.backend.app.models.domain import Invoice
from apps.invoice_to_pay.backend.app.models.domain import InvoiceLine
from apps.invoice_to_pay.backend.app.models.domain import Policy
from apps.invoice_to_pay.backend.app.models.domain import RateCard
from apps.invoice_to_pay.backend.app.models.domain import RateCardLine
from apps.invoice_to_pay.backend.app.models.domain import Supplier
from apps.invoice_to_pay.backend.app.models.domain import WorkOrder

SEED = 2002
SUPPLIER_TYPES = ("repairer", "hire", "storage", "recovery")
SERVICE_BY_SUPPLIER = {
    "repairer": "repair",
    "hire": "hire",
    "storage": "storage",
    "recovery": "recovery",
}
CHANNELS = ("email", "portal", "attachment")

# Validation thresholds. Shared between the settings block written into the seed file and the
# invoice generator, so seeded overcharges are guaranteed to breach the tolerance that is shipped.
HIGH_VALUE_THRESHOLD_GBP = 5000.0
TOLERANCE_PCT = 5.0
TOLERANCE_GBP = 25.0

# Seeded anomaly volumes from specification section 16.
DUPLICATE_COUNT = 40

# Claims are a curated estate rather than one per policy: a demo needs claims rich enough to read
# individually, each with a narrative, a reporter and photographs, and 110 is enough to fill the
# work queue and analytics while staying browsable. The 2,000 monthly invoices from section 16 are
# distributed across them, so a claim carries several supplier invoices as it would in life.
CLAIM_COUNT = 110
PORTAL_CLAIM_COUNT = 3

# Narrative building blocks. Paired by index so an incident type always gets a matching description,
# damage area and the services that incident would actually need.
INCIDENT_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "type": "collision",
        "headline": "Rear-ended in stationary traffic",
        "detail": (
            "The insured was stopped in queuing traffic when the vehicle behind failed to brake in "
            "time. The rear bumper and boot floor are pushed in and the offside rear light cluster "
            "is broken."
        ),
        "impact": "rear",
        "severity": "moderate",
        "drivable": "drivable",
        "services": ["repair"],
    },
    {
        "type": "collision",
        "headline": "Junction collision, front nearside",
        "detail": (
            "A third party pulled out of a side road and struck the front nearside wing. The wing, "
            "headlamp and front bumper are damaged and the wheel alignment is out. Airbags did not "
            "deploy but the vehicle was not safe to drive away."
        ),
        "impact": "front",
        "severity": "major",
        "drivable": "not drivable",
        "services": ["repair", "recovery", "hire"],
    },
    {
        "type": "weather",
        "headline": "Storm damage while parked",
        "detail": (
            "During high winds a branch came down across the bonnet and roof while the car was "
            "parked on the road outside the insured's home. Deep dents to the bonnet and scratching "
            "along the roof and windscreen surround."
        ),
        "impact": "roof",
        "severity": "moderate",
        "drivable": "drivable",
        "services": ["repair"],
    },
    {
        "type": "theft",
        "headline": "Vehicle stolen and recovered",
        "detail": (
            "The vehicle was taken overnight from the insured's driveway and recovered two days "
            "later by police. The steering column and ignition are damaged, the offside window is "
            "smashed and the interior has been stripped."
        ),
        "impact": "side",
        "severity": "major",
        "drivable": "not drivable",
        "services": ["repair", "recovery", "storage", "hire"],
    },
    {
        "type": "vandalism",
        "headline": "Panels keyed in car park",
        "detail": (
            "Both nearside doors and the rear quarter panel were scored deliberately while the car "
            "was in a multi-storey car park. Paint is through to primer along the full length."
        ),
        "impact": "side",
        "severity": "minor",
        "drivable": "drivable",
        "services": ["repair"],
    },
    {
        "type": "glass",
        "headline": "Windscreen cracked by road debris",
        "detail": (
            "A stone thrown up by a lorry on the motorway put a crack across the driver's side of "
            "the windscreen. The crack has spread and now obstructs the driver's view."
        ),
        "impact": "roof",
        "severity": "minor",
        "drivable": "drivable",
        "services": ["repair"],
    },
    {
        "type": "animal",
        "headline": "Deer strike on rural road",
        "detail": (
            "A deer ran into the road at dusk and struck the front of the vehicle. The front "
            "bumper, grille and radiator are damaged and coolant was lost at the scene, so the car "
            "could not continue."
        ),
        "impact": "front",
        "severity": "major",
        "drivable": "not drivable",
        "services": ["repair", "recovery", "hire"],
    },
    {
        "type": "fire",
        "headline": "Engine bay fire",
        "detail": (
            "Smoke was seen from the engine bay and the fire brigade attended. Fire damage to the "
            "wiring loom and engine bay, with heat distortion to the bonnet. The vehicle is "
            "unlikely to be economical to repair."
        ),
        "impact": "front",
        "severity": "total_loss",
        "drivable": "not drivable",
        "services": ["repair", "recovery", "storage"],
    },
)

# Reporter names cycle so every claim shows who logged it and how it reached the back office.
CUSTOMER_NAMES = (
    "Priya Raman", "Tom Whitfield", "Aisha Bello", "Daniel Okoro", "Sofia Marchetti",
    "Callum Fraser", "Nadia Haddad", "Ellis Booth", "Marta Kowalska", "Ravi Chandra",
    "Grace Adeyemi", "Owen Pritchard", "Yusuf Demir", "Helena Novak", "Jonah Clarke",
    "Amara Nwosu", "Felix Braun", "Isla Mackenzie", "Omar Farouk", "Bethan Lloyd",
    "Sean Gallagher", "Leila Hosseini", "Marcus Bright", "Chiara Rossi", "Dev Patel",
)
HANDLER_NAMES = (
    "handler-01", "handler-02", "handler-03", "handler-04", "handler-05", "handler-06",
)
REPORT_CHANNELS = ("customer_portal", "phone", "broker", "mobile_app", "email")
LAYOUTS = ("standard_a", "standard_b", "repair_grid", "hire_schedule", "storage_note", "recovery_ticket", "long_tail_a", "long_tail_b")
OUTCOMES = (
    ("straight_through", 0.70),
    ("out_of_tolerance", 0.12),
    ("failed_claim_matching", 0.06),
    ("missing_or_invalid_identifiers", 0.04),
    ("high_value", 0.04),
    ("policy_or_coverage_ambiguity", 0.04),
)


class SeedDataGenerator:
    """Generate reproducible demo data matching the build specification."""

    def __init__(self, seed: int = SEED) -> None:
        self.random = random.Random(seed)
        self.today = date(2026, 3, 31)

    def generate(self) -> dict[str, Any]:
        """Generate the full seed dataset."""
        suppliers = self._suppliers()
        rate_cards = self._rate_cards(suppliers)
        policies = self._policies()
        claims = self._claims(policies)
        authorisations = self._authorisations(claims, suppliers)
        invoices = self._invoices(suppliers, claims, authorisations, rate_cards)
        # Every claim gets photographs; only the customer-raised ones get an assistant transcript
        # and live work orders, because those are what the portal flow produces.
        # Reserves are set from what the claim actually costs. A severity-only reserve left almost
        # every claim reading as "over reserve" once its supplier invoices landed, which made the
        # dashboard look broken rather than informative.
        self._align_reserves(claims, invoices)
        portal_claims = [claim for claim in claims if claim.origin == "customer_portal"]
        attachments = self._claim_attachments(claims)
        turns = self._intake_turns(portal_claims)
        work_orders, portal_authorisations, portal_invoices = self._portal_work(portal_claims, suppliers, rate_cards)
        authorisations.extend(portal_authorisations)
        invoices.extend(portal_invoices)
        return {
            "metadata": {
                "seed": SEED,
                "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "expected_monthly_volume": 2000,
                "volume_growth_yoy_pct": 10.0,
                "target_fte_saving": 3.0,
            },
            "settings": {
                "high_value_threshold_gbp": HIGH_VALUE_THRESHOLD_GBP,
                "tolerance_pct": TOLERANCE_PCT,
                "tolerance_gbp": TOLERANCE_GBP,
                "min_extraction_confidence": 0.82,
                "min_match_confidence": 0.80,
                "rate_card_stale_days": 365,
                # Single-escaped inside a raw string: r"\\." would put a literal backslash in the
                # pattern and match nothing, which silently disabled redaction entirely.
                "redaction_rules": [
                    {"id": "PII-EMAIL", "pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "reason": "email address"},
                    {"id": "PII-POSTCODE", "pattern": r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b", "reason": "UK postcode"},
                    {"id": "PII-PHONE", "pattern": r"\b(?:\+44|0)7\d{9}\b", "reason": "UK mobile number"},
                ],
            },
            "suppliers": [supplier.to_dict() for supplier in suppliers],
            "rate_cards": [rate_card.to_dict() for rate_card in rate_cards],
            "policies": [policy.to_dict() for policy in policies],
            "claims": [claim.to_dict() for claim in claims],
            "authorisations": [authorisation.to_dict() for authorisation in authorisations],
            "invoices": [invoice.to_dict() for invoice in invoices],
            "duplicates": self._duplicate_pairs(invoices),
            "split_invoice_patterns": [f"split-pattern-{index:03d}" for index in range(1, 26)],
            "value_outliers": [f"INV-{index:06d}" for index in range(1, 31)],
            "claim_attachments": [item.to_dict() for item in attachments],
            "intake_turns": [item.to_dict() for item in turns],
            "work_orders": [item.to_dict() for item in work_orders],
        }

    def _suppliers(self) -> list[Supplier]:
        suppliers: list[Supplier] = []
        for index in range(1, 51):
            supplier_type = SUPPLIER_TYPES[(index - 1) % len(SUPPLIER_TYPES)]
            layout = LAYOUTS[index % len(LAYOUTS)]
            suppliers.append(
                Supplier(
                    id=f"SUP-{index:03d}",
                    name=f"{supplier_type.title()} Partner {index:03d}",
                    type=supplier_type,
                    contact=f"ap{index:03d}@supplier.example",
                    payment_path="integration" if index % 3 else "rpa",
                    template_id=layout if not layout.startswith("long_tail") else "generic",
                )
            )
        return suppliers

    def _rate_cards(self, suppliers: list[Supplier]) -> list[RateCard]:
        cards: list[RateCard] = []
        for index in range(1, 61):
            supplier = suppliers[(index - 1) % len(suppliers)]
            effective_from = self.today - timedelta(days=210 if index % 10 else 560)
            review_due = self.today - timedelta(days=30) if index <= 8 else self.today + timedelta(days=180)
            card_id = f"RC-{index:03d}"
            service_type = SERVICE_BY_SUPPLIER.get(supplier.type, "repair")
            base_rate = {"repair": 120.0, "hire": 48.0, "storage": 18.0, "recovery": 85.0}.get(service_type, 50.0)
            lines = [
                RateCardLine(
                    id=f"RCL-{index:03d}-1",
                    rate_card_id=card_id,
                    service_type=service_type,
                    unit="per_day" if service_type in ("hire", "storage") else "fixed",
                    rate_gbp=round(base_rate * self.random.uniform(0.9, 1.15), 2),
                    max_units=30 if service_type in ("hire", "storage") else 1,
                    conditions=f"{service_type.title()} charges per contracted schedule",
                )
            ]
            cards.append(
                RateCard(
                    id=card_id,
                    supplier_id=supplier.id,
                    version=f"2026.{(index % 4) + 1}",
                    effective_from=effective_from.isoformat(),
                    effective_to=(self.today + timedelta(days=365)).isoformat(),
                    review_due_date=review_due.isoformat(),
                    status="stale" if index <= 8 else "current",
                    lines=lines,
                )
            )
        return cards

    def _policies(self) -> list[Policy]:
        policies: list[Policy] = []
        for index in range(1, 501):
            entitlements = ["repair", "recovery"]
            if index % 3 != 0:
                entitlements.append("hire")
            if index % 5 != 0:
                entitlements.append("storage")
            policies.append(
                Policy(
                    id=f"POL-{index:05d}",
                    cover_type="comprehensive" if index % 4 else "third_party_fire_theft",
                    coverage_limits={"repair": 10000.0, "hire": 1000.0, "storage": 600.0, "recovery": 500.0},
                    entitlements=entitlements,
                    excess_gbp=float(100 + (index % 5) * 50),
                    effective_from="2025-01-01",
                    effective_to="2026-12-31",
                )
            )
        return policies

    def _claims(self, policies: list[Policy]) -> list[Claim]:
        """Return the curated claim estate, every claim carrying a full narrative.

        The first PORTAL_CLAIM_COUNT claims are customer-raised through the self-service portal and
        get a full assistant transcript; the rest arrived through the traditional channels and
        record who logged them instead. One portal claim is deliberately left at awaiting_triage so
        a demo always has a claim a handler can dispatch live.
        """
        claims: list[Claim] = []
        # Portal claims are pointed at the multi-service incidents on purpose: those are the ones
        # that produce a panel of suppliers and therefore a work-order board worth looking at.
        portal_incidents = (1, 3, 6)
        for index in range(1, CLAIM_COUNT + 1):
            if index <= PORTAL_CLAIM_COUNT:
                incident = INCIDENT_LIBRARY[portal_incidents[index - 1]]
            else:
                incident = INCIDENT_LIBRARY[(index - 1) % len(INCIDENT_LIBRARY)]
            policy = policies[(index * 13) % len(policies)]
            customer = CUSTOMER_NAMES[(index - 1) % len(CUSTOMER_NAMES)]
            incident_date = self.today - timedelta(days=self.random.randint(5, 180))
            reported_at = incident_date + timedelta(days=self.random.randint(0, 2))
            is_portal = index <= PORTAL_CLAIM_COUNT
            channel = "customer_portal" if is_portal else REPORT_CHANNELS[index % len(REPORT_CHANNELS)]
            severity = str(incident.get("severity", "moderate"))
            services = list(incident.get("services", ["repair"]))
            photos = 3 if index % 4 == 0 else 2

            if is_portal:
                workflow = ("work_in_progress", "awaiting_triage", "invoicing")[index - 1]
            else:
                workflow = "invoicing"

            claims.append(
                Claim(
                    id=f"CLM-{index:05d}",
                    invoice_claim_ref=f"Invoice-{202600000 + index}",
                    policy_id=policy.id,
                    customer_id=f"CUS-{index:05d}",
                    incident_date=incident_date.isoformat(),
                    status="open" if index % 9 else "closed",
                    reserve_gbp=self._reserve_for(severity),
                    paid_to_date_gbp=round(self.random.uniform(0, 1200), 2),
                    origin="customer_portal" if is_portal else "batch",
                    customer_name=customer,
                    contact_number=f"07{700 + (index % 90):03d}9{index % 10}{(index * 3) % 10}{(index * 7) % 10}{index % 10}",
                    contact_email=f"{customer.lower().replace(' ', '.')}@example.com",
                    address=f"{1 + (index % 89)} {self._street_for(index)}, {self._location_for(index)}",
                    # The insurance number the policyholder quotes; the digits resolve to the policy.
                    insurance_number=f"INS-{int(policy.id.split('-')[-1]):07d}",
                    vehicle_registration=self._registration_for(index),
                    reported_by=customer if channel in ("customer_portal", "mobile_app") else HANDLER_NAMES[index % len(HANDLER_NAMES)],
                    report_channel=channel,
                    incident_type=str(incident.get("type", "collision")),
                    incident_location=self._location_for(index),
                    description=f"{incident.get('headline')}. {incident.get('detail')}",
                    severity=severity,  # type: ignore[arg-type]
                    reported_at=f"{reported_at.isoformat()}T{8 + (index % 9):02d}:{(index * 7) % 60:02d}:00Z",
                    vehicle_drivable=str(incident.get("drivable", "drivable")),
                    triage_summary=(
                        f"{str(incident.get('type', '')).replace('_', ' ').title()} on "
                        f"{incident_date.isoformat()} at {self._location_for(index)}. Vehicle is "
                        f"{incident.get('drivable')}. Severity assessed as {severity.replace('_', ' ')}. "
                        f"{photos} photographs supplied."
                    ),
                    recommended_services=services,
                    workflow_status=workflow,  # type: ignore[arg-type]
                )
            )
        return claims

    def _align_reserves(self, claims: list[Claim], invoices: list[Invoice]) -> None:
        """Set each claim's reserve to what a handler would realistically have reserved.

        A reserve is the insurer's estimate of the claim's total cost, so it has to sit above what
        the claim is actually invoiced, with a minority deliberately breached so the "over reserve"
        exception has something to find. Every tenth claim is left under-reserved on purpose.
        """
        invoiced: dict[str, float] = {}
        for invoice in invoices:
            if invoice.claim_id:
                invoiced[invoice.claim_id] = invoiced.get(invoice.claim_id, 0.0) + invoice.gross_gbp

        for position, claim in enumerate(claims, start=1):
            total = invoiced.get(claim.id, 0.0)
            if total <= 0:
                # No invoices yet, so the severity-based opening reserve is the right answer.
                continue
            # A 10% headroom normally; every tenth claim is under-reserved to seed the exception.
            multiplier = 0.88 if position % 10 == 0 else self.random.uniform(1.08, 1.35)
            floor = self._reserve_for(claim.severity)
            claim.reserve_gbp = round(max(total * multiplier, floor), 2)
            claim.paid_to_date_gbp = round(
                min(claim.paid_to_date_gbp, claim.reserve_gbp * 0.25), 2
            )

    @staticmethod
    def _reserve_for(severity: str) -> float:
        """Return the reserve a claim of this severity is opened with."""
        return {"minor": 900.0, "moderate": 3200.0, "major": 7400.0, "total_loss": 11500.0}.get(severity, 3200.0)

    @staticmethod
    def _street_for(index: int) -> str:
        """Return a deterministic street name for the policyholder's address."""
        streets = (
            "Bridge Street", "Mill Lane", "Station Road", "Victoria Avenue", "Kings Road",
            "Church Walk", "Elm Grove", "Priory Close", "Harbour View", "Camden Terrace",
        )
        return streets[index % len(streets)]

    @staticmethod
    def _registration_for(index: int) -> str:
        """Return a deterministic UK-format vehicle registration."""
        letters = "ABCDEFGHJKLMNOPRSTUVWXY"
        first = letters[index % len(letters)]
        second = letters[(index * 5) % len(letters)]
        year = 17 + (index % 8)
        tail = "".join(letters[(index * offset) % len(letters)] for offset in (3, 7, 11))
        return f"{first}{second}{year:02d} {tail}"

    @staticmethod
    def _location_for(index: int) -> str:
        """Return a deterministic incident location."""
        places = (
            "M1 junction 23", "LS1 4AP", "B3 1JJ", "M60 anticlockwise", "CF10 1EP",
            "EH1 2NG", "A14 near Kettering", "NE1 7RU", "BS1 5TR", "S1 2HH",
            "A1(M) junction 6", "L1 8JQ", "NG1 5FS", "OX1 3QD", "CB2 1TN",
        )
        return places[index % len(places)]

    def _claim_panel(self, claim: Claim, suppliers: list[Supplier]) -> list[tuple[str, Supplier]]:
        """Return the (service, supplier) pairs instructed on one claim.

        A claim's invoices all come from this small panel, so a claim reads coherently: its
        repairer, its hire company and its recovery agent, rather than an arbitrary supplier per
        invoice. Selection is deterministic on the claim id so the estate is reproducible.
        """
        panel: list[tuple[str, Supplier]] = []
        for service in claim.recommended_services:
            supplier = self._supplier_for(service, claim.id, suppliers)
            if supplier is not None:
                panel.append((service, supplier))
        if not panel:
            fallback = self._supplier_for("repair", claim.id, suppliers)
            if fallback is not None:
                panel.append(("repair", fallback))
        return panel

    def _authorisations(self, claims: list[Claim], suppliers: list[Supplier]) -> list[Authorisation]:
        """Return one authorisation per claim and instructed service.

        Every invoice is validated against the authorisation for its claim and supplier, so there
        has to be one for each pair on the panel or authorised-units checks have nothing to test.
        """
        authorisations: list[Authorisation] = []
        counter = 0
        for claim in claims:
            for service, supplier in self._claim_panel(claim, suppliers):
                counter += 1
                units = 10 if service in ("hire", "storage") else 1
                authorisations.append(
                    Authorisation(
                        id=f"AUTH-{counter:05d}",
                        claim_id=claim.id,
                        supplier_id=supplier.id,
                        service_type=service,
                        authorised_units=units,
                        authorised_value_gbp=round(units * 100.0, 2),
                        authorised_by=claim.reported_by or "handler-01",
                        authorised_at=(self.today - timedelta(days=self.random.randint(1, 50))).isoformat(),
                    )
                )
        return authorisations

    def _invoices(
        self,
        suppliers: list[Supplier],
        claims: list[Claim],
        authorisations: list[Authorisation],
        rate_cards: list[RateCard],
    ) -> list[Invoice]:
        invoices: list[Invoice] = []
        weighted_outcomes = [outcome for outcome, weight in OUTCOMES for _ in range(int(weight * 100))]
        effective_rates = self._effective_rates(suppliers, rate_cards)
        # Authorisations are looked up by (claim, supplier) so an invoice is always validated
        # against the authorisation that actually covers it.
        auth_index = {(item.claim_id, item.supplier_id): item for item in authorisations}
        panels = {claim.id: self._claim_panel(claim, suppliers) for claim in claims}
        # Batch invoices are only attached to batch claims. A customer-raised claim earns its
        # invoices by being triaged and dispatched, so seeding historic invoices onto one would
        # have it showing "invoice checked" before a handler had even looked at it.
        billable = [claim for claim in claims if claim.origin == "batch"]
        for index in range(1, 2001):
            claim = billable[(index * 7) % len(billable)]
            panel = panels.get(claim.id) or []
            if not panel:
                continue
            # The supplier comes from this claim's own panel, so every invoice on a claim is from a
            # firm that was actually instructed on it.
            service_type, supplier = panel[index % len(panel)]
            auth = auth_index.get((claim.id, supplier.id))
            if auth is None:
                continue
            outcome = weighted_outcomes[(index - 1) % len(weighted_outcomes)]
            # Out-of-tolerance invoices must have the lines that carry the overcharge, so they never
            # get fewer than three. Otherwise a two-line invoice seeded to dispute has nothing
            # overcharged and silently processes straight through.
            line_count = (3 + (index % 2)) if outcome == "out_of_tolerance" else 2 + (index % 3)
            rate = effective_rates.get(supplier.id, 50.0)
            lines = self._invoice_lines(index, service_type, outcome, auth, line_count, rate)
            net = round(sum(line.amount_gbp for line in lines), 2)
            vat = round(sum(line.vat_gbp for line in lines), 2)
            invoice_number = f"INV-{index:06d}"
            claim_ref = claim.invoice_claim_ref if outcome != "missing_or_invalid_identifiers" else ""
            supplier_ref = f"SREF-{index:06d}" if outcome != "missing_or_invalid_identifiers" else ""
            pii = " Driver: Alex Morgan, M1 1AE, 07123456789, alex.customer@example.com." if index % 11 == 0 else ""
            layout = LAYOUTS[index % len(LAYOUTS)]
            invoices.append(
                Invoice(
                    id=f"INVREC-{index:06d}",
                    invoice_number=invoice_number,
                    supplier_id=supplier.id,
                    claim_id=claim.id if outcome != "failed_claim_matching" else None,
                    channel=CHANNELS[index % len(CHANNELS)],
                    received_at=(self.today - timedelta(days=index % 180)).isoformat(),
                    document_uri=f"local://documents/{invoice_number}.txt",
                    redacted_document_uri=None,
                    status="Received",
                    gross_gbp=round(net + vat, 2),
                    net_gbp=net,
                    vat_gbp=vat,
                    match_confidence=0.99 if outcome not in ("failed_claim_matching", "missing_or_invalid_identifiers") else 0.42,
                    match_method="exact_reference" if outcome == "straight_through" else "probabilistic",
                    straight_through=False,
                    lines=lines,
                    document_text=(
                        f"Invoice {invoice_number} claim {claim_ref} supplier {supplier.name} supplier ref {supplier_ref}."
                        f" Service {service_type}. Net GBP {net}. VAT GBP {vat}.{pii}"
                    ),
                    layout_id=layout,
                    seeded_outcome=outcome,
                )
            )
        return invoices

    @staticmethod
    def _effective_rates(suppliers: list[Supplier], rate_cards: list[RateCard]) -> dict[str, float]:
        """Return the rate each supplier's invoices are charged against.

        This mirrors InvoiceRepository.current_rate_card, which sorts a supplier's cards by
        effective_from descending and takes the first. `max` returns the first maximal element, so
        the two selections agree. Charging against this rate is what keeps a straight-through
        invoice at zero variance instead of accidentally breaching tolerance.
        """
        rates: dict[str, float] = {}
        for supplier in suppliers:
            candidates = [card for card in rate_cards if card.supplier_id == supplier.id and card.lines]
            if not candidates:
                continue
            chosen = max(candidates, key=lambda card: card.effective_from)
            rates[supplier.id] = chosen.lines[0].rate_gbp
        return rates

    def _invoice_lines(
        self,
        invoice_index: int,
        service_type: str,
        outcome: str,
        auth: Authorisation,
        line_count: int,
        rate_gbp: float,
    ) -> list[InvoiceLine]:
        lines: list[InvoiceLine] = []
        for line_no in range(1, line_count + 1):
            units = 1 if service_type in ("repair", "recovery") else max(1, min(14, auth.authorised_units - 1 + line_no))
            # Amounts are charged against the supplier's own effective rate card, so a compliant
            # line has exactly zero variance and the validation engine can be trusted.
            expected = round(units * rate_gbp, 2)
            amount = expected
            if outcome == "out_of_tolerance" and line_no in (3, 4):
                # Overcharge enough to clear both the percentage and the absolute tolerance,
                # whichever binds for this line's size.
                overcharge = max(TOLERANCE_GBP * 1.5, round(expected * 0.25, 2))
                amount = round(expected + overcharge, 2)
            if outcome == "high_value":
                amount = round(expected * 8.0, 2)
            lines.append(
                InvoiceLine(
                    id=f"INVREC-{invoice_index:06d}-L{line_no}",
                    invoice_id=f"INVREC-{invoice_index:06d}",
                    line_no=line_no,
                    service_type=service_type,  # type: ignore[arg-type]
                    service_date_from=(self.today - timedelta(days=30 + line_no)).isoformat(),
                    service_date_to=(self.today - timedelta(days=29)).isoformat(),
                    units=units,
                    unit_rate_gbp=round(amount / units, 2),
                    amount_gbp=amount,
                    vat_gbp=round(amount * 0.2, 2),
                    extracted_confidence=0.72 if outcome == "policy_or_coverage_ambiguity" and line_no == 1 else 0.94,
                )
            )
        return lines

    @staticmethod
    def _duplicate_pairs(invoices: list[Invoice]) -> list[dict[str, str]]:
        """Pair 40 later resubmissions with an earlier invoice from the same supplier.

        Duplicates are drawn only from invoices that are not seeded to flow straight through. A
        duplicate must be blocked (TC-07), so seeding one onto a straight-through invoice would put
        the 40 seeded duplicates in direct conflict with the 70% straight-through target, and one of
        the two mandatory figures in specification section 16 could never be met.

        They are also drawn from the back half of the estate, which is both realistic for a
        resubmission and keeps the low-numbered invoices used in the documented demo flow clean.
        """
        earliest_by_supplier: dict[str, str] = {}
        pairs: list[dict[str, str]] = []
        for position, invoice in enumerate(invoices):
            if invoice.supplier_id not in earliest_by_supplier:
                earliest_by_supplier[invoice.supplier_id] = invoice.invoice_number
            if len(pairs) >= DUPLICATE_COUNT:
                break
            if position < len(invoices) // 2 or invoice.seeded_outcome == "straight_through":
                continue
            original = earliest_by_supplier.get(invoice.supplier_id)
            if original is None or original == invoice.invoice_number:
                continue
            pairs.append({"original": original, "duplicate": invoice.invoice_number})
        return pairs


    def _claim_attachments(self, claims: list[Claim]) -> list[ClaimAttachment]:
        """Return synthetic incident photographs for every claim.

        These are generated SVG scenes rather than photographs: the repository must stay text-only
        and self-contained, so no binary assets are committed. They exist to prove the upload,
        storage and gallery path end to end, and a real deployment would hold real images here.
        """
        views = ("Rear offside damage", "Front nearside damage", "Wide shot at the scene")
        attachments: list[ClaimAttachment] = []
        for position, claim in enumerate(claims, start=1):
            count = 3 if position % 4 == 0 else 2
            for index in range(count):
                label = views[index % len(views)]
                attachments.append(
                    ClaimAttachment(
                        id=f"{claim.id}-IMG-{index + 1:02d}",
                        claim_id=claim.id,
                        label=label,
                        content_type="image/svg+xml",
                        data_uri=self._incident_image(claim, label, index),
                        uploaded_at=claim.reported_at,
                        source="customer",
                        ai_tags=self._photo_tags(claim, label),
                    )
                )
        return attachments

    def _incident_image(self, claim: Claim, label: str, variant: int) -> str:
        """Return a base64 data URI holding a simple generated incident scene."""
        palettes = (("#1f3b73", "#cbd8ef"), ("#3b2a63", "#d9d2ef"), ("#123f4a", "#c9e4e9"))
        ink, sky = palettes[variant % len(palettes)]
        impact = {"collision": "rear", "weather": "roof", "vandalism": "side"}.get(claim.incident_type, "rear")
        # The damage marker moves with the impact area so the three views are visibly different.
        marker = {"rear": (232, 96), "roof": (150, 58), "side": (118, 104)}.get(impact, (232, 96))
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480' viewBox='0 0 640 480'>"
            f"<rect width='640' height='480' fill='{sky}'/>"
            f"<rect y='300' width='640' height='180' fill='{ink}' opacity='0.18'/>"
            f"<rect y='356' width='640' height='8' fill='{ink}' opacity='0.45'/>"
            f"<g transform='translate(150 150) scale(1.15)'>"
            f"<path d='M20 120 L44 62 Q52 46 72 44 L188 44 Q208 46 218 62 L246 120 Z' fill='{ink}'/>"
            f"<rect x='12' y='118' width='244' height='44' rx='14' fill='{ink}'/>"
            f"<path d='M62 58 L96 58 L92 100 L44 100 Z' fill='{sky}' opacity='0.85'/>"
            f"<path d='M112 58 L176 58 L186 100 L108 100 Z' fill='{sky}' opacity='0.85'/>"
            f"<circle cx='62' cy='166' r='23' fill='#1b1b23'/><circle cx='62' cy='166' r='9' fill='{sky}'/>"
            f"<circle cx='206' cy='166' r='23' fill='#1b1b23'/><circle cx='206' cy='166' r='9' fill='{sky}'/>"
            "</g>"
            f"<g transform='translate({marker[0]} {marker[1]})'>"
            "<path d='M0 40 L16 0 L30 34 L48 6 L58 44 L26 58 Z' fill='#d9480f' opacity='0.82'/>"
            "<path d='M10 44 L24 14 L34 40 L46 22' stroke='#fff3bf' stroke-width='3' fill='none'/>"
            "</g>"
            f"<rect x='0' y='428' width='640' height='52' fill='#10131a' opacity='0.72'/>"
            f"<text x='18' y='452' font-family='Inter,Arial,sans-serif' font-size='17' font-weight='700' fill='#ffffff'>{label}</text>"
            f"<text x='18' y='470' font-family='Inter,Arial,sans-serif' font-size='12' fill='#c9d3e6'>"
            f"{claim.id} &#183; {claim.incident_date} &#183; synthetic demo image</text>"
            "</svg>"
        )
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    @staticmethod
    def _photo_tags(claim: Claim, label: str) -> list[str]:
        """Return descriptive tags for one seeded photograph."""
        lowered = label.lower()
        tags = [claim.incident_type]
        for part in ("rear", "front", "nearside", "offside", "roof", "side", "wide"):
            if part in lowered:
                tags.append(part)
        return tags or [claim.incident_type]

    def _intake_turns(self, claims: list[Claim]) -> list[IntakeTurn]:
        """Return the assistant transcript for each portal claim."""
        turns: list[IntakeTurn] = []
        for claim in claims:
            first_sentence = claim.description.split(". ")[0].strip()
            script: list[tuple[str, str, list[str]]] = [
                (
                    "assistant",
                    "Hello, I am Theo, the claims assistant. I can register your claim right now and "
                    "give you a claim reference before you leave this page.\n\nTo start: what happened?",
                    ["Opened a draft claim", "Asked for the incident in the customer's own words"],
                ),
                ("customer", f"{first_sentence}.", []),
                (
                    "assistant",
                    f"Thank you. When did the {claim.incident_type.replace('_', ' ')} happen? "
                    "A date or 'yesterday' is fine.",
                    [f"Extracted incident type: {claim.incident_type}", "Still missing: incident date"],
                ),
                ("customer", f"It was on {claim.incident_date}.", []),
                (
                    "assistant",
                    "Where did it happen? A postcode or the road name is enough.",
                    [f"Extracted incident date: {claim.incident_date}", "Still missing: incident location"],
                ),
                ("customer", f"At {claim.incident_location}.", []),
                (
                    "assistant",
                    "One more thing: can the vehicle still be driven, or does it need recovering?",
                    [f"Extracted incident location: {claim.incident_location}", "Still missing: drivable"],
                ),
                (
                    "customer",
                    "It is still drivable." if claim.vehicle_drivable == "drivable" else "It needs recovering.",
                    [],
                ),
                (
                    "assistant",
                    "Here is what I have:\n\n"
                    f"â€¢ Incident: {claim.incident_type.replace('_', ' ')}\n"
                    f"â€¢ When: {claim.incident_date}\n"
                    f"â€¢ Where: {claim.incident_location}\n"
                    f"â€¢ Assessment: {claim.severity.replace('_', ' ')}\n"
                    f"â€¢ Services I will request: {', '.join(claim.recommended_services)}\n\n"
                    "Add photographs if you have them, then press Submit claim and I will give you "
                    "your reference.",
                    [
                        f"Extracted drivable: {claim.vehicle_drivable}",
                        f"Triaged as {claim.severity}; recommending {', '.join(claim.recommended_services)}",
                    ],
                ),
                (
                    "assistant",
                    f"Your claim is registered as {claim.id}. A handler will review the photographs "
                    "you sent and instruct the suppliers you need.",
                    ["Claim submitted to the back office", "Handler notified for triage"],
                ),
            ]
            for index, (role, text, reasoning) in enumerate(script, start=1):
                turns.append(
                    IntakeTurn(
                        id=f"{claim.id}-T{index:03d}",
                        claim_id=claim.id,
                        role=role,
                        text=text,
                        at=claim.reported_at,
                        reasoning=reasoning,
                    )
                )
        return turns

    def _portal_work(
        self, claims: list[Claim], suppliers: list[Supplier], rate_cards: list[RateCard]
    ) -> tuple[list[WorkOrder], list[Authorisation], list[Invoice]]:
        """Return work orders, their authorisations and any invoices already received.

        How far each work order has progressed is driven by the claim's workflow_status, so the
        seeded claims show the whole lifecycle: dispatched, in progress, and invoice received.
        """
        stage_by_workflow = {
            "awaiting_triage": [],
            "dispatched": ["dispatched"],
            "work_in_progress": ["in_progress", "accepted"],
            "invoicing": ["invoiced", "completed", "in_progress"],
        }
        rate_lookup = self._effective_rates(suppliers, rate_cards)
        orders: list[WorkOrder] = []
        authorisations: list[Authorisation] = []
        invoices: list[Invoice] = []
        counter = 0
        invoice_sequence = 2000

        for claim in claims:
            stages = stage_by_workflow.get(claim.workflow_status, [])
            if not stages:
                continue
            for position, service in enumerate(claim.recommended_services):
                supplier = self._supplier_for(service, claim.id, suppliers)
                if supplier is None:
                    continue
                counter += 1
                status = stages[position % len(stages)]
                units = {"repair": 1, "recovery": 1, "hire": 10, "storage": 7}.get(service, 1)
                rate = rate_lookup.get(supplier.id, 100.0)
                value = round(units * rate, 2)
                order_id = f"WO-{counter:05d}"
                dispatched_at = f"{claim.incident_date}T10:{15 + position * 5:02d}:00Z"
                invoice_id: str | None = None

                if status == "invoiced":
                    invoice_sequence += 1
                    invoice_id = f"INVREC-{invoice_sequence:06d}"
                    invoices.append(
                        self._portal_invoice(invoice_id, invoice_sequence, claim, supplier, service, units, rate)
                    )

                orders.append(
                    WorkOrder(
                        id=order_id,
                        claim_id=claim.id,
                        supplier_id=supplier.id,
                        service_type=service,
                        status=status,  # type: ignore[arg-type]
                        authorised_units=units,
                        authorised_value_gbp=value,
                        dispatched_at=dispatched_at,
                        dispatched_by="handler-07",
                        accepted_at=dispatched_at if status != "dispatched" else None,
                        started_at=dispatched_at if status in ("in_progress", "completed", "invoiced") else None,
                        completed_at=dispatched_at if status in ("completed", "invoiced") else None,
                        invoice_id=invoice_id,
                        notes=f"{service.title()} authorised from claim triage",
                    )
                )
                authorisations.append(
                    Authorisation(
                        id=f"AUTH-{counter:05d}-{service[:3].upper()}",
                        claim_id=claim.id,
                        supplier_id=supplier.id,
                        service_type=service,
                        authorised_units=units,
                        authorised_value_gbp=value,
                        authorised_by="handler-07",
                        authorised_at=dispatched_at,
                    )
                )
        return orders, authorisations, invoices

    def _portal_invoice(
        self,
        invoice_id: str,
        sequence: int,
        claim: Claim,
        supplier: Supplier,
        service: str,
        units: int,
        rate: float,
    ) -> Invoice:
        """Return the invoice a supplier submitted against a completed work order."""
        amount = round(units * rate, 2)
        vat = round(amount * 0.2, 2)
        invoice_number = f"INV-{sequence:06d}"
        line = InvoiceLine(
            id=f"{invoice_id}-L1",
            invoice_id=invoice_id,
            line_no=1,
            service_type=service,  # type: ignore[arg-type]
            service_date_from=claim.incident_date,
            service_date_to=self.today.isoformat(),
            units=units,
            unit_rate_gbp=rate,
            amount_gbp=amount,
            vat_gbp=vat,
            extracted_confidence=0.96,
        )
        return Invoice(
            id=invoice_id,
            invoice_number=invoice_number,
            supplier_id=supplier.id,
            claim_id=claim.id,
            channel="portal",
            received_at=self.today.isoformat(),
            document_uri=f"local://documents/{invoice_number}.txt",
            redacted_document_uri=None,
            status="Received",
            gross_gbp=round(amount + vat, 2),
            net_gbp=amount,
            vat_gbp=vat,
            match_confidence=0.99,
            match_method="exact_reference",
            straight_through=False,
            lines=[line],
            document_text=(
                f"Invoice {invoice_number} claim {claim.invoice_claim_ref} supplier {supplier.name}."
                f" Service {service}. Net GBP {amount}. VAT GBP {vat}."
            ),
            layout_id=supplier.template_id,
            seeded_outcome="straight_through",
        )

    @staticmethod
    def _supplier_for(service: str, claim_id: str, suppliers: list[Supplier]) -> Supplier | None:
        """Return a supplier of the type that fulfils this service, chosen deterministically.

        Mirrors WorkOrderService._pick_supplier so seeded and runtime dispatch agree.
        """
        wanted = {"repair": "repairer", "hire": "hire", "storage": "storage", "recovery": "recovery"}.get(service)
        candidates = sorted([item for item in suppliers if item.type == wanted], key=lambda item: item.id)
        if not candidates:
            return None
        digits = "".join(character for character in claim_id if character.isdigit())
        return candidates[(int(digits) if digits else 0) % len(candidates)]

    @staticmethod
    def write_default(output_path: str) -> None:
        """Write generated data to output_path.

        Written compactly rather than indented. The file is only ever machine-read, the base64
        incident images make it large, and the indentation alone accounted for roughly a third of
        its size — which was enough to fail a push through a proxy with a request-size limit.
        """
        data = SeedDataGenerator().generate()
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    @staticmethod
    def main() -> None:
        """CLI entry point for generating seed data."""
        SeedDataGenerator.write_default("apps/invoice_to_pay/data/seed/invoice_demo_data.json")


if __name__ == "__main__":
    SeedDataGenerator.main()
