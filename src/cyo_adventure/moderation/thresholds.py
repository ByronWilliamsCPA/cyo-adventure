"""Age-band moderation surfacing thresholds (WS-A).

The moderation pipeline records every finding. This module decides which
recorded findings SURFACE on guardian- and kid-facing responses, per
(age_band, category). Admin surfaces never filter.

Policy resolution: an exact (age_band, category) row wins; otherwise the code
default applies. The DB table is a sparse override set, not a full matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cyo_adventure.moderation.report import Verdict

if TYPE_CHECKING:
    from collections.abc import Mapping

# Severity ordering for surfacing decisions. PASS is deliberately absent: a
# pass finding never surfaces regardless of thresholds.
_SEVERITY: dict[Verdict, int] = {
    Verdict.ADVISORY: 1,
    Verdict.FLAG: 2,
    Verdict.BLOCK: 3,
}

# Known category values across pipeline stages, for the admin editor's
# suggestion list ONLY. Categories are open-ended strings (Stage-0 classifier
# payload keys are provider-defined), so this list is advisory, never a gate.
KNOWN_CATEGORIES: tuple[str, ...] = (
    "coherence",
    "engagement",
    "harassment/threatening",
    "hate/threatening",
    "identity_attack",
    "illicit/violent",
    "insult",
    "invalid_story",
    "personal_information",
    "profanity",
    "reading_level",
    "reviewer_independence",
    "safety",
    "self-harm/instructions",
    "self-harm/intent",
    "severe_toxicity",
    "sexual",
    "sexual/minors",
    "sexually_explicit",
    "threat",
    "toxicity",
)


@dataclass(frozen=True, slots=True)
class Threshold:
    """Minimum verdict (and optional score floor) at which a finding surfaces."""

    min_verdict: Verdict
    min_score: float | None


DEFAULT_THRESHOLD = Threshold(min_verdict=Verdict.FLAG, min_score=None)


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    """Resolved surfacing policy: sparse override rows over a code default."""

    rows: Mapping[tuple[str, str], Threshold]
    default: Threshold = field(default=DEFAULT_THRESHOLD)

    def resolve(self, age_band: str, category: str) -> Threshold:
        """Return the threshold for a band and category (row or default)."""
        return self.rows.get((age_band, category), self.default)

    def surfaces(
        self,
        *,
        age_band: str,
        category: str,
        verdict: Verdict | str,
        score: float | None,
    ) -> bool:
        """Return whether a recorded finding surfaces on a filtered response.

        Args:
            age_band: The story's (or requesting child's) age band; an empty
                string resolves to the code default.
            category: The finding's category string.
            verdict: The finding's verdict; serialized strings are coerced.
            score: The finding's classifier score, if any.

        Returns:
            bool: True when the finding meets the resolved threshold.
        """
        # #ASSUME: data-integrity: verdicts arrive from unconstrained JSONB, so
        # an out-of-enum string must degrade to "hidden", never raise.
        # #VERIFY: test_unknown_string_verdict_does_not_surface.
        if not isinstance(verdict, Verdict):
            try:
                verdict = Verdict(verdict)
            except ValueError:
                return False
        severity = _SEVERITY.get(verdict)
        if severity is None:  # Verdict.PASS
            return False
        threshold = self.resolve(age_band, category)
        if severity < _SEVERITY[threshold.min_verdict]:
            return False
        return not (
            threshold.min_score is not None
            and score is not None
            and score < threshold.min_score
        )
