"""Deterministic synthetic data generator for the invoice-to-pay prototype."""

from __future__ import annotations

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
from apps.invoice_to_pay.backend.app.models.domain import Invoice
from apps.invoice_to_pay.backend.app.models.domain import InvoiceLine
from apps.invoice_to_pay.backend.app.models.domain import Policy
from apps.invoice_to_pay.backend.app.models.domain import RateCard
from apps.invoice_to_pay.backend.app.models.domain import RateCardLine
from apps.invoice_to_pay.backend.app.models.domain import Supplier

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
        claims: list[Claim] = []
        for index, policy in enumerate(policies, start=1):
            claims.append(
                Claim(
                    id=f"CLM-{index:05d}",
                    ice_claim_ref=f"ICE-{202600000 + index}",
                    policy_id=policy.id,
                    customer_id=f"CUS-{index:05d}",
                    incident_date=(self.today - timedelta(days=self.random.randint(5, 180))).isoformat(),
                    status="open" if index % 9 else "closed",
                    reserve_gbp=round(self.random.uniform(1000, 12000), 2),
                    paid_to_date_gbp=round(self.random.uniform(0, 3000), 2),
                )
            )
        return claims

    def _authorisations(self, claims: list[Claim], suppliers: list[Supplier]) -> list[Authorisation]:
        authorisations: list[Authorisation] = []
        for index, claim in enumerate(claims, start=1):
            supplier = suppliers[index % len(suppliers)]
            service_type = SERVICE_BY_SUPPLIER.get(supplier.type, "repair")
            units = 10 if service_type in ("hire", "storage") else 1
            authorisations.append(
                Authorisation(
                    id=f"AUTH-{index:05d}",
                    claim_id=claim.id,
                    supplier_id=supplier.id,
                    service_type=service_type,
                    authorised_units=units,
                    authorised_value_gbp=round(units * 100.0, 2),
                    authorised_by=f"handler-{index % 12:02d}",
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
        for index in range(1, 2001):
            supplier = suppliers[(index - 1) % len(suppliers)]
            claim = claims[(index * 7) % len(claims)]
            auth = authorisations[(index * 7) % len(authorisations)]
            outcome = weighted_outcomes[(index - 1) % len(weighted_outcomes)]
            service_type = SERVICE_BY_SUPPLIER.get(supplier.type, "repair")
            # Out-of-tolerance invoices must have the lines that carry the overcharge, so they never
            # get fewer than three. Otherwise a two-line invoice seeded to dispute has nothing
            # overcharged and silently processes straight through.
            line_count = (3 + (index % 2)) if outcome == "out_of_tolerance" else 2 + (index % 3)
            rate = effective_rates.get(supplier.id, 50.0)
            lines = self._invoice_lines(index, service_type, outcome, auth, line_count, rate)
            net = round(sum(line.amount_gbp for line in lines), 2)
            vat = round(sum(line.vat_gbp for line in lines), 2)
            invoice_number = f"INV-{index:06d}"
            claim_ref = claim.ice_claim_ref if outcome != "missing_or_invalid_identifiers" else ""
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

    @staticmethod
    def write_default(output_path: str) -> None:
        """Write generated data to output_path."""
        data = SeedDataGenerator().generate()
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def main() -> None:
        """CLI entry point for generating seed data."""
        SeedDataGenerator.write_default("apps/invoice_to_pay/data/seed/invoice_demo_data.json")


if __name__ == "__main__":
    SeedDataGenerator.main()
