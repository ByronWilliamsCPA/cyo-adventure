"""The diversity eval panel: manifest, runner, and baseline compare.

WS-0 Phase 2 (design doc section 3.3). This is the testable core the
``run_diversity_eval`` script wraps: it loads the committed panel manifest
and fixture files, computes every metric over the panel, and compares the
result to a committed baseline under the CI-fail rules R1-R6 (design doc
section 2.3).

Filesystem-impure (it reads committed fixture files from paths the caller
supplies), but DB-free and network-free: this module never imports ``db``,
``generation``, or ``sqlalchemy``. The judge integration (design doc section
5) lives in the script, not here, so that rule is never at risk of being
violated by an import creeping in.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, JsonValue
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.aggregate import (
    PairScore,
    pair_score,
    repeat_adventure_rate,
)
from cyo_adventure.diversity.leaf import anti_template_verdict, leaf_distance_profile
from cyo_adventure.diversity.lexical import LexicalProfile, lexical_profile
from cyo_adventure.diversity.normalize import (
    coerce_storybook,
    jaccard_similarity,
    theme_signature,
)
from cyo_adventure.diversity.report import AntiTemplateReport, AntiTemplateVerdict
from cyo_adventure.diversity.structure import structural_distance, structure_fingerprint
from cyo_adventure.storybook.models import Storybook

if TYPE_CHECKING:
    from pathlib import Path

# The baseline.json schema version this module reads and writes (WS-0 design
# doc section 2.1). A baseline with a missing or different value is treated
# as untrustworthy (R6): never silently reinterpreted, always forcing a
# deliberate --update-baseline.
_CURRENT_SCHEMA_VERSION: Final[int] = 1

# R2: an expected-PASS pair's median_distance may not drop more than this
# absolute margin below its baseline value (WS-0 design doc section 2.3).
_R2_MEDIAN_MARGIN: Final[float] = 0.05

# R3: a lexical_gated_ids fill's distinct_2 may not drop below this fraction
# of its baseline value (WS-0 design doc section 2.3, a 10% relative floor).
_R3_RELATIVE_FLOOR: Final[float] = 0.90

# R4: the tau-theme boundary a brief pair's computed similarity must clear
# to be judged "similar" (WS-0 design doc section 2.3).
_R4_SIMILARITY_THRESHOLD: Final[float] = 0.35


class PanelFill(BaseModel):
    """One committed fill entry in the panel manifest.

    Attributes:
        id: The panel-local identifier (referenced by pair specs).
        path: Repo-root-relative path to the committed fixture file.
        band: The fill's declared age band (e.g. ``"8-11"``).
        skeleton_slug: The skeleton this fill was authored from.
        brief: The fill's theme brief, if one travelled with it; drives ATG
            masking and PS theme similarity exactly like production.
        provenance: A human-readable note on where and when this fixture
            was copied from (WS-0 design doc section 1.2).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    band: str
    skeleton_slug: str
    brief: dict[str, JsonValue] | None = None
    provenance: str


class SyntheticSpec(BaseModel):
    """A run-time-derived panel entry that is never committed as a story file.

    Attributes:
        id: The panel-local identifier for the derived variant.
        base: The ``PanelFill.id`` (or another synthetic's id) this variant
            is derived from.
        kind: ``"noun_swap"`` applies :func:`make_noun_swap_variant` with
            ``swaps``; ``"identity"`` is the base fill compared against
            itself.
        swaps: The word-swap table for ``kind="noun_swap"``; empty and
            unused for ``kind="identity"``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    base: str
    kind: Literal["noun_swap", "identity"]
    swaps: dict[str, str] = {}


class AtgPairSpec(BaseModel):
    """One anti-template-guard pair the panel gates on (R1, WS-0 section 2.3).

    Attributes:
        a: The first panel id (a fill or synthetic).
        b: The second panel id.
        expected_verdict: The verdict this pair must compute, as curated
            human contract (never overwritten by ``--update-baseline``).
    """

    model_config = ConfigDict(extra="forbid")

    a: str
    b: str
    expected_verdict: AntiTemplateVerdict


class BriefPairSpec(BaseModel):
    """One tau-theme brief pair the panel gates on (R4, WS-0 section 2.3).

    Attributes:
        a: The first brief (a ``ConceptBrief``-shaped mapping).
        b: The second brief.
        expected_similar: Whether the pair's theme similarity must clear
            :data:`_R4_SIMILARITY_THRESHOLD`, as curated human contract.
    """

    model_config = ConfigDict(extra="forbid")

    a: dict[str, JsonValue]
    b: dict[str, JsonValue]
    expected_similar: bool


class PanelManifest(BaseModel):
    """The full committed panel manifest (``tests/data/diversity_panel/panel.json``).

    Attributes:
        schema_version: The manifest schema version (currently ``1``).
        fills: Committed fill fixtures.
        synthetic: Run-time-derived variants (never committed as story
            files).
        atg_pairs: Anti-template-guard pairs, gated by R1.
        cross_tree_pairs: Cross-skeleton pairs; invariant-gated (structural
            distance ``> 0``) by R5, values baseline-tracked but never
            regression-gated.
        rar_sequence: Panel ids treated as one pseudo-family's chronological
            history for the repeat-adventure-rate trend metric.
        brief_pairs: Tau-theme brief pairs, gated by R4.
        lexical_gated_ids: The subset of ``fills`` ids whose ``distinct_2``
            is regression-gated by R3.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    fills: list[PanelFill]
    synthetic: list[SyntheticSpec] = []
    atg_pairs: list[AtgPairSpec]
    cross_tree_pairs: list[tuple[str, str]]
    rar_sequence: list[str]
    brief_pairs: list[BriefPairSpec]
    lexical_gated_ids: list[str]


def load_panel(path: Path) -> PanelManifest:
    """Load and validate a diversity panel manifest from disk.

    Args:
        path: Path to the manifest JSON file.

    Returns:
        PanelManifest: The validated manifest.

    Raises:
        ValidationError: If the file cannot be read, is not valid JSON, or
            fails :class:`PanelManifest` schema validation.
    """
    # #ASSUME: external-resources: reads a committed fixture file from disk;
    # a missing/unreadable/malformed panel manifest is an R6 panel-integrity
    # failure (the fixture was moved, deleted, or hand-edited into an
    # invalid shape), not a code bug, so it is surfaced as ValidationError
    # with the offending path rather than an unguarded OSError/JSONDecodeError.
    # #VERIFY: test_diversity_panel.py exercises a missing manifest path.
    try:
        raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except OSError as exc:
        msg = f"cannot read panel manifest at {path}"
        raise ValidationError(msg, field="path", value=str(path)) from exc
    except json.JSONDecodeError as exc:
        msg = f"panel manifest at {path} is not valid JSON"
        raise ValidationError(msg, field="path", value=str(path)) from exc
    try:
        return PanelManifest.model_validate(raw)
    except PydanticValidationError as exc:
        msg = f"panel manifest at {path} failed schema validation"
        raise ValidationError(msg, field="path", details={"error": str(exc)}) from exc


def make_noun_swap_variant(fill: Storybook, swaps: Mapping[str, str]) -> Storybook:
    """Return a synthetic "dog for cat" noun-swap variant of one fill.

    A word-boundary, case-preserving substitution over node bodies only
    (the canonical anti-template-guard FAIL case, WS-0 design doc section
    6.2): the same structure and sentence rhythm, only the nouns changed.

    Args:
        fill: The fill to derive a variant from.
        swaps: A lowercase-key word-swap table (e.g. ``{"station":
            "burrow"}``); both the lowercase and Capitalized forms of each
            key are matched and replaced, preserving the matched form's
            capitalization.

    Returns:
        Storybook: The swapped variant.

    Raises:
        ValidationError: If the swap unexpectedly changed the source's
            :func:`~cyo_adventure.diversity.structure.structure_fingerprint`
            (bodies are excluded from the fingerprint by construction, so
            this should never happen; it is checked directly rather than
            relied upon, matching the WS-0 Phase 1 convention).
    """
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(word) for word in swaps) + r")\b", re.IGNORECASE
    )

    def _swap_one(match: re.Match[str]) -> str:
        original = match.group(0)
        replacement = swaps[original.lower()]
        return replacement.capitalize() if original[0].isupper() else replacement

    data = fill.model_dump(mode="json")
    nodes = data.get("nodes")
    if isinstance(nodes, list):
        for raw_node in cast("list[object]", nodes):
            if isinstance(raw_node, dict):
                node = cast("dict[str, object]", raw_node)
                body = node.get("body")
                if isinstance(body, str):
                    node["body"] = pattern.sub(_swap_one, body)

    variant = Storybook.model_validate(data)
    if structure_fingerprint(fill) != structure_fingerprint(variant):
        msg = "make_noun_swap_variant must preserve the source structure fingerprint"
        raise ValidationError(msg, field="structure_fingerprint", value=variant.id)
    return variant


def _pair_key(a: str, b: str) -> str:
    """Return the canonical, sorted ``"a~b"`` baseline key for a pair of ids.

    Args:
        a: The first panel id.
        b: The second panel id.

    Returns:
        str: The two ids, lexicographically sorted, joined with ``"~"``.
    """
    first, second = sorted((a, b))
    return f"{first}~{second}"


@dataclass(frozen=True, slots=True)
class FillMetrics:
    """One committed fill's computed structure fingerprint and lexical profile.

    Attributes:
        fingerprint: The fill's :func:`~cyo_adventure.diversity.structure.
            structure_fingerprint`.
        band: The fill's declared age band, carried through from the
            manifest for the baseline record.
        lexical: The fill's :class:`~cyo_adventure.diversity.lexical.
            LexicalProfile`.
    """

    fingerprint: str
    band: str
    lexical: LexicalProfile


@dataclass(frozen=True, slots=True)
class AtgPairResult:
    """One ATG pair's anti-template report plus its invariants and tripwire.

    Attributes:
        report: The full anti-template guard report.
        structural_distance: The pair's structural distance; every genuine
            ATG pair is same-tree by construction, so this must be ``0.0``
            (R5).
        big_over_uni_ratio: ``mean_d_big / mean_d_uni`` (``0.0`` when
            ``mean_d_uni`` is ``0``), the paraphrase-gaming tripwire (WS-0
            design doc section 7.1). Recorded and reported, never gated in
            Phase 2.
    """

    report: AntiTemplateReport
    structural_distance: float
    big_over_uni_ratio: float


@dataclass(frozen=True, slots=True)
class BriefPairOutcome:
    """One brief pair's computed theme-similarity outcome.

    Attributes:
        key: ``"{premise_a}~{premise_b}"``, matching the baseline record's
            join convention.
        similarity: The computed Jaccard theme similarity.
        similar: Whether ``similarity`` clears
            :data:`_R4_SIMILARITY_THRESHOLD`.
    """

    key: str
    similarity: float
    similar: bool


@dataclass(frozen=True, slots=True)
class PanelResult:
    """Everything :func:`run_panel` computes over one manifest.

    Attributes:
        fills: Per-fill fingerprint and lexical profile, keyed by panel id.
            Real fills only; synthetics have no committed file and no
            lexical profile of their own.
        atg_pairs: Per-ATG-pair report and invariants, keyed by the sorted
            ``"a~b"`` pair key (:func:`_pair_key`).
        struct_pairs: Per-cross-tree-pair structural distance, keyed the
            same way.
        ps_pairs: Per-pair :class:`~cyo_adventure.diversity.aggregate.
            PairScore`, covering every ATG pair plus every cross-tree pair.
        rar_value: The repeat-adventure rate over the manifest's
            ``rar_sequence``.
        brief_pairs: Per-brief-pair theme-similarity outcome, in manifest
            order.
    """

    fills: dict[str, FillMetrics]
    atg_pairs: dict[str, AtgPairResult]
    struct_pairs: dict[str, float]
    ps_pairs: dict[str, PairScore]
    rar_value: float
    brief_pairs: tuple[BriefPairOutcome, ...]


def _load_fill_story(repo_root: Path, fill: PanelFill) -> Storybook:
    """Read and validate one committed fill fixture.

    Args:
        repo_root: The repository root the manifest's paths are relative to.
        fill: The manifest entry describing the fixture to load.

    Returns:
        Storybook: The validated fill.

    Raises:
        ValidationError: If the fixture is missing, unreadable, not valid
            JSON, or fails Storybook schema validation.
    """
    # #ASSUME: external-resources: the manifest names a path relative to
    # repo_root; a missing/unreadable fixture means a committed panel file
    # was moved or deleted out from under the gate. This is an R6
    # panel-integrity failure, not a code bug.
    # #VERIFY: test_diversity_panel.py exercises a manifest pointing at a
    # nonexistent fixture path.
    full_path = repo_root / fill.path
    try:
        raw = cast(
            "dict[str, object]", json.loads(full_path.read_text(encoding="utf-8"))
        )
    except OSError as exc:
        msg = f"cannot read panel fixture '{fill.id}' at {full_path}"
        raise ValidationError(msg, field="path", value=str(full_path)) from exc
    except json.JSONDecodeError as exc:
        msg = f"panel fixture '{fill.id}' at {full_path} is not valid JSON"
        raise ValidationError(msg, field="path", value=str(full_path)) from exc
    return coerce_storybook(raw)


def run_panel(manifest: PanelManifest, repo_root: Path) -> PanelResult:
    """Load every fixture, synthesize every variant, and compute all metrics.

    Args:
        manifest: The validated panel manifest.
        repo_root: The repository root the manifest's fixture paths are
            relative to.

    Returns:
        PanelResult: The full computed result.

    Raises:
        ValidationError: If a fixture is missing/unreadable/invalid, or a
            synthetic entry names an unknown ``base`` id (both R6
            panel-integrity failures per WS-0 design doc section 2.3).
    """
    stories: dict[str, Storybook] = {}
    briefs: dict[str, Mapping[str, object] | None] = {}
    fills: dict[str, FillMetrics] = {}

    for fill in manifest.fills:
        story = _load_fill_story(repo_root, fill)
        stories[fill.id] = story
        briefs[fill.id] = fill.brief
        fills[fill.id] = FillMetrics(
            fingerprint=structure_fingerprint(story),
            band=fill.band,
            lexical=lexical_profile(story, fill.brief),
        )

    for synthetic in manifest.synthetic:
        base_story = stories.get(synthetic.base)
        if base_story is None:
            msg = f"synthetic '{synthetic.id}' references unknown base id '{synthetic.base}'"
            raise ValidationError(msg, field="base", value=synthetic.base)
        variant = (
            make_noun_swap_variant(base_story, synthetic.swaps)
            if synthetic.kind == "noun_swap"
            else base_story
        )
        stories[synthetic.id] = variant
        briefs[synthetic.id] = briefs.get(synthetic.base)

    atg_pairs: dict[str, AtgPairResult] = {}
    ps_pairs: dict[str, PairScore] = {}
    for pair in manifest.atg_pairs:
        a_story, b_story = stories[pair.a], stories[pair.b]
        brief_a, brief_b = briefs.get(pair.a), briefs.get(pair.b)
        report = anti_template_verdict(
            a_story, b_story, brief_a=brief_a, brief_b=brief_b
        )
        profile = leaf_distance_profile(a_story, b_story, brief_a, brief_b)
        ratio = profile.mean_d_big / profile.mean_d_uni if profile.mean_d_uni else 0.0
        key = _pair_key(pair.a, pair.b)
        atg_pairs[key] = AtgPairResult(
            report=report,
            structural_distance=structural_distance(a_story, b_story),
            big_over_uni_ratio=ratio,
        )
        ps_pairs[key] = pair_score(a_story, b_story, brief_a=brief_a, brief_b=brief_b)

    struct_pairs: dict[str, float] = {}
    for a_id, b_id in manifest.cross_tree_pairs:
        a_story, b_story = stories[a_id], stories[b_id]
        brief_a, brief_b = briefs.get(a_id), briefs.get(b_id)
        key = _pair_key(a_id, b_id)
        struct_pairs[key] = structural_distance(a_story, b_story)
        ps_pairs[key] = pair_score(a_story, b_story, brief_a=brief_a, brief_b=brief_b)

    rar_stories = [stories[panel_id] for panel_id in manifest.rar_sequence]
    rar_briefs = [briefs.get(panel_id) for panel_id in manifest.rar_sequence]
    rar_value = repeat_adventure_rate(rar_stories, briefs=rar_briefs)

    brief_outcomes = tuple(_brief_pair_outcome(spec) for spec in manifest.brief_pairs)

    return PanelResult(
        fills=fills,
        atg_pairs=atg_pairs,
        struct_pairs=struct_pairs,
        ps_pairs=ps_pairs,
        rar_value=rar_value,
        brief_pairs=brief_outcomes,
    )


def _brief_pair_outcome(spec: BriefPairSpec) -> BriefPairOutcome:
    """Compute one brief pair's theme-similarity outcome.

    Args:
        spec: The manifest's brief-pair specification.

    Returns:
        BriefPairOutcome: The computed similarity and boolean.
    """
    similarity = jaccard_similarity(theme_signature(spec.a), theme_signature(spec.b))
    premise_a = spec.a.get("premise", "")
    premise_b = spec.b.get("premise", "")
    key = f"{premise_a}~{premise_b}"
    return BriefPairOutcome(
        key=key, similarity=similarity, similar=similarity >= _R4_SIMILARITY_THRESHOLD
    )


def baseline_payload(result: PanelResult) -> dict[str, object]:
    """Build the JSON-serializable baseline payload for one computed result.

    Args:
        result: A freshly computed :class:`PanelResult`.

    Returns:
        dict[str, object]: The ``baseline.json`` payload (WS-0 design doc
            section 2.1). Every float is rounded to 6 decimal places. Byte
            stability across identical inputs relies on the caller dumping
            this with ``json.dumps(..., sort_keys=True, indent=2)`` (dict
            key order here does not matter; list order does, and
            ``brief_pairs`` is emitted in fixed manifest order).
    """
    fills_payload = {
        fill_id: {
            "fingerprint": metrics.fingerprint,
            "band": metrics.band,
            "distinct_1": round(metrics.lexical.distinct_1, 6),
            "distinct_2": round(metrics.lexical.distinct_2, 6),
            "self_bleu_lite": round(metrics.lexical.self_bleu_lite, 6),
            "content_token_count": metrics.lexical.content_token_count,
        }
        for fill_id, metrics in result.fills.items()
    }
    atg_payload = {
        key: {
            "verdict": pair.report.verdict.value,
            "median_distance": round(pair.report.median_distance, 6),
            "p25_distance": round(pair.report.p25_distance, 6),
            "p10_distance": round(pair.report.p10_distance, 6),
            "mean_bigram_distance": round(pair.report.mean_bigram_distance, 6),
            "templated_node_count": len(pair.report.templated_nodes),
            "big_over_uni_ratio": round(pair.big_over_uni_ratio, 6),
        }
        for key, pair in result.atg_pairs.items()
    }
    struct_payload = {
        key: round(value, 6) for key, value in result.struct_pairs.items()
    }
    ps_payload = {
        key: {
            "leaf_similarity": round(score.leaf_similarity, 6),
            "structural_similarity": round(score.structural_similarity, 6),
            "theme_similarity": round(score.theme_similarity, 6),
            "perceived_similarity": round(score.perceived_similarity, 6),
            "same_tree": score.same_tree,
        }
        for key, score in result.ps_pairs.items()
    }
    brief_payload = [
        {
            "key": outcome.key,
            "similarity": round(outcome.similarity, 6),
            "similar": outcome.similar,
        }
        for outcome in result.brief_pairs
    ]
    return {
        "schema_version": _CURRENT_SCHEMA_VERSION,
        "fills": fills_payload,
        "atg_pairs": atg_payload,
        "struct_pairs": struct_payload,
        "ps_pairs": ps_payload,
        "rar_sequence": round(result.rar_value, 6),
        "brief_pairs": brief_payload,
    }


@dataclass(frozen=True, slots=True)
class RegressionFinding:
    """One CI-fail rule violation (WS-0 design doc section 2.3).

    Attributes:
        rule: The rule id, ``"R1"`` through ``"R6"``.
        subject: The pair key or fill id the finding is about (or
            ``"baseline"`` for a baseline-level failure).
        message: A human-readable description of the violation.
        observed: The computed value that tripped the rule.
        allowed: The bound the observed value violated.
    """

    rule: str
    subject: str
    message: str
    observed: float | str
    allowed: float | str


def _sub_mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return a nested baseline mapping, or an empty mapping if absent.

    Args:
        source: The parent mapping.
        key: The nested field name.

    Returns:
        Mapping[str, object]: The nested mapping, or ``{}`` when ``key`` is
            missing or not a mapping.
    """
    value = source.get(key)
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else {}


def _entry(source: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    """Return one baseline sub-entry as a mapping, or None if absent/malformed.

    Args:
        source: The parent baseline mapping (e.g. ``baseline["fills"]``).
        key: The entry key (a fill id or pair key).

    Returns:
        Mapping[str, object] | None: The entry, or None when missing or not
            a mapping.
    """
    value = source.get(key)
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else None


def _number_field(source: Mapping[str, object], key: str) -> float | None:
    """Return a numeric baseline field, or None if absent/wrong-typed.

    Args:
        source: The baseline entry.
        key: The numeric field name.

    Returns:
        float | None: The value as a float, or None when missing,
            non-numeric, or a bool (bools are ints in Python but never a
            legitimate baseline metric value).
    """
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _check_verdict_contract(
    result: PanelResult, manifest: PanelManifest
) -> list[RegressionFinding]:
    """R1: every ATG pair's computed verdict must equal its expected verdict."""
    findings: list[RegressionFinding] = []
    for pair in manifest.atg_pairs:
        key = _pair_key(pair.a, pair.b)
        computed = result.atg_pairs[key].report.verdict
        if computed != pair.expected_verdict:
            findings.append(
                RegressionFinding(
                    rule="R1",
                    subject=key,
                    message=(
                        f"expected verdict '{pair.expected_verdict.value}' but "
                        f"computed '{computed.value}'"
                    ),
                    observed=computed.value,
                    allowed=pair.expected_verdict.value,
                )
            )
    return findings


def _check_brief_flip(
    result: PanelResult, manifest: PanelManifest
) -> list[RegressionFinding]:
    """R4: every brief pair's computed boolean must equal ``expected_similar``."""
    findings: list[RegressionFinding] = []
    for spec, outcome in zip(manifest.brief_pairs, result.brief_pairs, strict=True):
        if outcome.similar != spec.expected_similar:
            findings.append(
                RegressionFinding(
                    rule="R4",
                    subject=outcome.key,
                    message="brief-pair similarity boolean flipped",
                    observed=str(outcome.similar),
                    allowed=str(spec.expected_similar),
                )
            )
    return findings


def _check_structural_invariants(
    result: PanelResult, manifest: PanelManifest
) -> list[RegressionFinding]:
    """R5 (invariant half): same-tree pairs are 0.0; cross-tree pairs are > 0.0."""
    findings: list[RegressionFinding] = []
    for pair in manifest.atg_pairs:
        key = _pair_key(pair.a, pair.b)
        distance = result.atg_pairs[key].structural_distance
        if distance != 0.0:
            findings.append(
                RegressionFinding(
                    rule="R5",
                    subject=key,
                    message="same-tree ATG pair has a nonzero structural_distance",
                    observed=distance,
                    allowed=0.0,
                )
            )
    for a_id, b_id in manifest.cross_tree_pairs:
        key = _pair_key(a_id, b_id)
        distance = result.struct_pairs[key]
        if distance <= 0.0:
            findings.append(
                RegressionFinding(
                    rule="R5",
                    subject=key,
                    message="cross-tree pair has a non-positive structural_distance",
                    observed=distance,
                    allowed="> 0.0",
                )
            )
    return findings


def _check_genuine_pair_erosion(
    result: PanelResult, manifest: PanelManifest, baseline_atg: Mapping[str, object]
) -> list[RegressionFinding]:
    """R2 (plus its R6 completeness precondition): expected-PASS median erosion."""
    findings: list[RegressionFinding] = []
    for pair in manifest.atg_pairs:
        if pair.expected_verdict != AntiTemplateVerdict.PASS_:
            continue
        key = _pair_key(pair.a, pair.b)
        entry = _entry(baseline_atg, key)
        baseline_median = _number_field(entry, "median_distance") if entry else None
        if baseline_median is None:
            findings.append(
                RegressionFinding(
                    rule="R6",
                    subject=key,
                    message="no baseline atg_pairs entry; run --update-baseline",
                    observed="missing",
                    allowed="present",
                )
            )
            continue
        floor = baseline_median - _R2_MEDIAN_MARGIN
        observed = result.atg_pairs[key].report.median_distance
        if observed < floor:
            findings.append(
                RegressionFinding(
                    rule="R2",
                    subject=key,
                    message="genuine-pair median_distance eroded past the allowed margin",
                    observed=observed,
                    allowed=floor,
                )
            )
    return findings


def _check_distinct_2_erosion(
    result: PanelResult, manifest: PanelManifest, baseline_fills: Mapping[str, object]
) -> list[RegressionFinding]:
    """R3 (plus its R6 completeness precondition): lexical_gated_ids distinct_2 erosion."""
    findings: list[RegressionFinding] = []
    for fill_id in manifest.lexical_gated_ids:
        metrics = result.fills.get(fill_id)
        if metrics is None:
            continue
        entry = _entry(baseline_fills, fill_id)
        baseline_distinct_2 = _number_field(entry, "distinct_2") if entry else None
        if baseline_distinct_2 is None:
            findings.append(
                RegressionFinding(
                    rule="R6",
                    subject=fill_id,
                    message="no baseline fills entry; run --update-baseline",
                    observed="missing",
                    allowed="present",
                )
            )
            continue
        floor = _R3_RELATIVE_FLOOR * baseline_distinct_2
        observed = metrics.lexical.distinct_2
        if observed < floor:
            findings.append(
                RegressionFinding(
                    rule="R3",
                    subject=fill_id,
                    message="distinct_2 eroded past the allowed relative floor",
                    observed=observed,
                    allowed=floor,
                )
            )
    return findings


def _check_fingerprint_drift(
    result: PanelResult, manifest: PanelManifest, baseline_fills: Mapping[str, object]
) -> list[RegressionFinding]:
    """R5 (fingerprint half, plus its R6 completeness precondition)."""
    findings: list[RegressionFinding] = []
    for fill in manifest.fills:
        metrics = result.fills[fill.id]
        entry = _entry(baseline_fills, fill.id)
        baseline_fingerprint = entry.get("fingerprint") if entry else None
        if not isinstance(baseline_fingerprint, str):
            findings.append(
                RegressionFinding(
                    rule="R6",
                    subject=fill.id,
                    message="no baseline fills entry; run --update-baseline",
                    observed="missing",
                    allowed="present",
                )
            )
            continue
        if metrics.fingerprint != baseline_fingerprint:
            findings.append(
                RegressionFinding(
                    rule="R5",
                    subject=fill.id,
                    message=(
                        "fill's computed structure fingerprint differs from the "
                        "baseline (fixture edited, or fingerprint algorithm changed)"
                    ),
                    observed=metrics.fingerprint,
                    allowed=baseline_fingerprint,
                )
            )
    return findings


def _check_struct_pair_completeness(
    manifest: PanelManifest, baseline_struct: Mapping[str, object]
) -> list[RegressionFinding]:
    """R6: every cross-tree pair must have a baseline struct_pairs entry."""
    findings: list[RegressionFinding] = []
    for a_id, b_id in manifest.cross_tree_pairs:
        key = _pair_key(a_id, b_id)
        value = baseline_struct.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            findings.append(
                RegressionFinding(
                    rule="R6",
                    subject=key,
                    message="no baseline struct_pairs entry; run --update-baseline",
                    observed="missing",
                    allowed="present",
                )
            )
    return findings


def compare_to_baseline(
    result: PanelResult, baseline: Mapping[str, object], manifest: PanelManifest
) -> list[RegressionFinding]:
    """Evaluate the CI-fail rules R1-R6 against a committed baseline.

    Checks are one-sided (WS-0 design doc section 2.2): only erosion trips a
    rule, an improvement never does. Expected verdicts (R1) and expected
    brief-pair booleans (R4) come from ``manifest`` (the human-curated
    contract) and can never be silently blessed by a baseline rewrite; every
    other rule compares a freshly computed value against ``baseline`` (the
    tool-written measurement). See WS-0 design doc section 2.1's authority
    split.

    Args:
        result: The freshly computed panel result.
        baseline: The parsed ``baseline.json`` mapping.
        manifest: The panel manifest.

    Returns:
        list[RegressionFinding]: Empty exactly when the gate passes.
    """
    schema_version = baseline.get("schema_version")
    if schema_version != _CURRENT_SCHEMA_VERSION:
        return [
            RegressionFinding(
                rule="R6",
                subject="baseline",
                message=(
                    "baseline is missing or has an unsupported schema_version; "
                    "run --update-baseline"
                ),
                observed=str(schema_version),
                allowed=str(_CURRENT_SCHEMA_VERSION),
            )
        ]

    baseline_fills = _sub_mapping(baseline, "fills")
    baseline_atg = _sub_mapping(baseline, "atg_pairs")
    baseline_struct = _sub_mapping(baseline, "struct_pairs")

    findings: list[RegressionFinding] = []
    findings.extend(_check_verdict_contract(result, manifest))
    findings.extend(_check_brief_flip(result, manifest))
    findings.extend(_check_structural_invariants(result, manifest))
    findings.extend(_check_genuine_pair_erosion(result, manifest, baseline_atg))
    findings.extend(_check_distinct_2_erosion(result, manifest, baseline_fills))
    findings.extend(_check_fingerprint_drift(result, manifest, baseline_fills))
    findings.extend(_check_struct_pair_completeness(manifest, baseline_struct))
    return findings
