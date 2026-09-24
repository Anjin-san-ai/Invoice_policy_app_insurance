"""Data-only record for one evaluation metric."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

# How a metric's value is obtained. Reported alongside every value so a reader can tell a real
# measurement from a capability that does not exist yet.
MEASURED = "measured"
NOT_IMPLEMENTED = "not_implemented"


@dataclass
class MetricResult:
    """One metric, its target, and whether it was met."""

    name: str
    value: float | bool
    target: float | bool
    comparator: str
    passed: bool
    method: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)
