"""Story validation gate.

Layer 1 (graph rules L1-1..L1-7) runs on every story and is implemented here.
Layer 2 (state-space rules, Tier-2 only) lands in Phase 2.
"""

from __future__ import annotations

from cyo_adventure.validator.layer1 import validate_layer1
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

__all__ = [
    "Severity",
    "ValidationFinding",
    "ValidationReport",
    "validate_layer1",
]
