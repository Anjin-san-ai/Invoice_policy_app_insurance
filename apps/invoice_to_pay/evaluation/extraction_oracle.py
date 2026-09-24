"""Golden extraction oracle: recovers expected field values from the raw document text."""

from __future__ import annotations

import re
from typing import Any

# The invoice document text is the only independent source of truth for extraction. Parsing it here
# with a deliberately separate expression means the harness is not simply reading back the same
# structured fields the pipeline populated.
DOCUMENT_PATTERN = re.compile(
    r"Invoice (?P<invoice_number>\S+) "
    r"claim (?P<claim_ref>\S+) "
    r"supplier (?P<supplier_name>.+?) "
    r"supplier ref (?P<supplier_ref>[^.]+)\. "
    r"Service (?P<service_type>\w+)\. "
    r"Net GBP (?P<net_gbp>[\d.]+)\. "
    r"VAT GBP (?P<vat_gbp>[\d.]+)\."
)

FIELD_NAMES = ("invoice_number", "claim_ref", "supplier_name", "service_type", "net_gbp", "vat_gbp")


class ExtractionOracle:
    """Parse the document text into the fields the Extraction Agent is expected to produce."""

    @staticmethod
    def parse(document_text: str) -> dict[str, Any] | None:
        """Return the expected field values, or None when the document does not parse at all."""
        match = DOCUMENT_PATTERN.search(document_text)
        if match is None:
            return None
        return {
            "invoice_number": match.group("invoice_number"),
            "claim_ref": match.group("claim_ref"),
            "supplier_name": match.group("supplier_name"),
            "supplier_ref": match.group("supplier_ref"),
            "service_type": match.group("service_type"),
            "net_gbp": float(match.group("net_gbp")),
            "vat_gbp": float(match.group("vat_gbp")),
        }

    @staticmethod
    def compare(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, bool]:
        """Return per-field correctness for the fields both sides carry."""
        outcome: dict[str, bool] = {}
        for field in FIELD_NAMES:
            expected_value = expected.get(field)
            actual_value = actual.get(field)
            if isinstance(expected_value, float) and isinstance(actual_value, (int, float)):
                outcome[field] = abs(expected_value - float(actual_value)) < 0.01
            else:
                outcome[field] = expected_value == actual_value
        return outcome
