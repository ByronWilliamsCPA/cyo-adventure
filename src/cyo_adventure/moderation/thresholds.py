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

    from sqlalchemy.ext.asyncio import AsyncSession

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


async def load_threshold_policy(
    session: AsyncSession,
) -> ThresholdPolicy:
    """Load all threshold override rows into an immutable policy.

    The table is admin-curated and small; a whole-table read per filtered
    request is deliberate (no cache invalidation machinery).

    Args:
        session: The request-scoped async session.

    Returns:
        ThresholdPolicy: Override rows over the code default.
    """
    # #ASSUME: external-resources: one small SELECT per filtered request; if
    # this table ever grows past a few hundred rows, add request-scope caching.
    # #VERIFY: tests/integration/test_threshold_policy_loader.py.
    from sqlalchemy import select  # noqa: PLC0415

    from cyo_adventure.db.models import ModerationThreshold  # noqa: PLC0415

    rows: dict[tuple[str, str], Threshold] = {}
    for row in await session.scalars(select(ModerationThreshold)):
        try:
            verdict = Verdict(row.min_verdict)
        except ValueError:
            continue  # CHECK constraint should prevent this; skip defensively.
        rows[(row.age_band, row.category)] = Threshold(
            min_verdict=verdict, min_score=row.min_score
        )
    return ThresholdPolicy(rows=rows)


# The moderation_setting row key for the admin noise floor. This is the single
# runtime source of truth for the key string; the migration's seed INSERT uses
# its own frozen literal (migrations must not import live app constants) and
# must be kept in sync with this value by hand.
ADMIN_NOISE_FLOOR_KEY = "admin_noise_floor"

# The code default for the admin noise floor, mirrored in the seed row inserted
# by migrations/versions/20260707_1700_add_moderation_setting.py
# ("admin_noise_floor" = 0.05). Used when the moderation_setting row is absent
# (e.g. a test schema built from ORM metadata rather than migrated).
ADMIN_NOISE_FLOOR_DEFAULT = 0.05


def admin_surfaces(
    verdict: Verdict | str,
    score: float | None,
    *,
    noise_floor: float,
) -> bool:
    """Return whether a finding surfaces on the ADMIN review view specifically.

    This denoises the admin view only; it is unrelated to ``ThresholdPolicy``
    which gates guardian/kid-facing surfaces. It never hides a FLAG or BLOCK
    finding (including a bright-line BLOCK carrying score ``0.0``) and never
    hides an unscored finding. It hides only an ADVISORY finding whose score
    is present and below ``noise_floor``.

    Args:
        verdict: The finding's verdict; serialized strings are coerced.
        score: The finding's classifier score, if any.
        noise_floor: The admin-configured global noise floor in [0.0, 1.0].

    Returns:
        bool: True when the finding should surface on the admin review view.
    """
    # #ASSUME: data-integrity: verdicts arrive from unconstrained JSONB, so an
    # out-of-enum string must degrade to "hidden", never raise.
    # #VERIFY: tests/unit/test_admin_noise_floor.py::
    # test_unknown_string_verdict_does_not_surface.
    if not isinstance(verdict, Verdict):
        try:
            verdict = Verdict(verdict)
        except ValueError:
            return False
    if verdict is Verdict.PASS:
        return False
    return not (
        verdict is Verdict.ADVISORY and score is not None and score < noise_floor
    )


async def load_admin_noise_floor(session: AsyncSession) -> float:
    """Load the admin noise floor scalar, falling back to the code default.

    Args:
        session: The request-scoped async session.

    Returns:
        float: The stored ``admin_noise_floor`` value, or
        ``ADMIN_NOISE_FLOOR_DEFAULT`` when the row is absent (a test schema
        built from ORM metadata with no seed migration applied, or a
        not-yet-migrated deployment).
    """
    # #ASSUME: external-resources: one small primary-key lookup per admin
    # review request; this is a single scalar row, so no request-scope
    # caching is added.
    # #VERIFY: tests/integration covering load_admin_noise_floor.
    from cyo_adventure.db.models import ModerationSetting  # noqa: PLC0415

    row = await session.get(ModerationSetting, ADMIN_NOISE_FLOOR_KEY)
    if row is None:
        return ADMIN_NOISE_FLOOR_DEFAULT
    return row.value
