"""Independent PII oracle for scoring redaction recall and false positives."""

from __future__ import annotations

import re

# Deliberately declared here rather than read from the seed settings, so that a broken rule set in
# settings cannot make the pipeline and the oracle agree with each other and both be wrong.
REFERENCE_PATTERNS = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("postcode", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b")),
    ("phone", re.compile(r"\b(?:\+44|0)7\d{9}\b")),
)

REGION_PATTERN = re.compile(r"chars:(\d+)-(\d+)")


class PiiOracle:
    """Locate the PII spans a compliant redaction agent must find."""

    @staticmethod
    def spans(document_text: str) -> list[tuple[int, int, str]]:
        """Return every true PII span as (start, end, kind)."""
        found: list[tuple[int, int, str]] = []
        for kind, pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(document_text):
                found.append((match.start(), match.end(), kind))
        return sorted(found)

    @staticmethod
    def parse_region(field_or_region: str) -> tuple[int, int] | None:
        """Return the character span a redaction log entry refers to, if it encodes one."""
        match = REGION_PATTERN.search(field_or_region)
        if match is None:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def overlaps(region: tuple[int, int], spans: list[tuple[int, int, str]]) -> bool:
        """Return whether a redacted region overlaps any true PII span."""
        start, end = region
        return any(start < span_end and span_start < end for span_start, span_end, _ in spans)
