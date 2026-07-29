"""Deterministic sentinel re-insertion: strip-all-then-reinsert (plan 3.4 fallback).

Plan section 3.4 measured that the fill LLM preserves a personalization
sentinel (`cyo_adventure.storybook.sentinels.wrap`) on only a small fraction
of stories, and that the dominant failure mode is the model dropping the
wrapper and writing the bare inner word instead (e.g. writing plain
``Explorer`` where the pre-fill skeleton declared ``{~HERO:Explorer~}``). The
new design direction this module measures: never trust the LLM to preserve a
sentinel at all. Instead, deterministically re-insert one after the fact by:

1. Stripping every model-emitted sentinel, well-formed or malformed, out of
   the filled document, replacing each with its own best-effort inner word.
   A model-emitted sentinel is never trusted, so it is never counted as a
   match for anything; this closes the "forged token" hole a naive
   find-and-keep approach would fall into.
2. For each node and each token the pre-fill bound skeleton expected there
   (the same body/ending-title expectation model
   `cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity`
   scores against), counting case-sensitive, whole-word occurrences of that
   token's inner generic value in the now-stripped node prose.
3. Classifying each `(node, token)` pair as ``"reinsertable"`` (count >= 1)
   or ``"not_found"`` (the model paraphrased the word away entirely; no
   deterministic re-insertion is possible for that node).
4. Wrapping every matched occurrence with the canonical sentinel (a name
   slot personalizes every mention, not just the first), then proving the
   result via the SAME integrity check the fill pipeline already trusts
   (`round_trip_ok`).

Pure: every function here is a plain data transform over already-loaded
mappings, with no I/O and no network or provider calls. The measurement CLI
(`scripts/prototype_sentinel_reinsertion.py`) is the only I/O boundary that
uses this module.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from cyo_adventure.storybook.sentinels import (
    SENTINEL_RE,
    find_malformed_sentinels,
    find_sentinels,
    wrap,
)
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# The two possible per-(node, token) outcomes of the strip-all-then-reinsert
# algorithm.
_TokenStatus = Literal["reinsertable", "not_found"]

# A single-node expected token, as (slot_id, value); mirrors the private
# `_Token` alias in `cyo_adventure.validator.sentinel_integrity`.
_Token = tuple[str, str]

# A malformed near-miss span's closer, stripped from its extracted inner word
# (see `_extract_malformed_inner_word`): a trailing `~}`, a bare `}`, a
# dangling `~`, or any run of those, plus surrounding whitespace.
_MALFORMED_TRAILER_RE = re.compile(r"[~}]+\s*$")

# The occurrence-multiplicity buckets `_multiplicity_bucket` sorts a
# reinsertable token's count into (plan 3.4 prototype: high multiplicity is a
# proxy for mis-target risk, since a common generic word used in more than a
# handful of unrelated senses is more likely to also collect a false-positive
# wrap somewhere in the same node).
_MULTIPLICITY_SINGLE = "1"
_MULTIPLICITY_FEW = "2-3"
_MULTIPLICITY_MANY = "4+"


@dataclass(frozen=True, slots=True)
class TokenOutcome:
    """The strip-all-then-reinsert outcome for one expected `(node, token)` pair.

    Attributes:
        node_id: The owning node's id.
        slot_id: The expected token's slot id.
        value: The expected token's inner generic value.
        occurrence_count: How many case-sensitive, whole-word occurrences of
            `value` were found in the node's normalized (model-sentinel-
            stripped) body and ending-title text combined. Zero exactly when
            `status` is ``"not_found"``.
        status: ``"reinsertable"`` when `occurrence_count` is at least 1,
            ``"not_found"`` otherwise (the model paraphrased the word away).
    """

    node_id: str
    slot_id: str
    value: str
    occurrence_count: int
    status: _TokenStatus


@dataclass(frozen=True, slots=True)
class ReinsertionResult:
    """The full strip-all-then-reinsert outcome for one bound skeleton / filled blob pair.

    Attributes:
        normalized_document: A deep copy of the filled blob with every
            model-emitted sentinel (well-formed or malformed) replaced by its
            own inner word; no sentinel-shaped syntax from the model survives
            here, by construction.
        reinserted_document: A further deep copy of `normalized_document`
            with every reinsertable token's occurrences wrapped back into the
            canonical sentinel form. A `not_found` token contributes nothing
            here (there is nothing to wrap).
        token_outcomes: One `TokenOutcome` per `(node, token)` pair the
            pre-fill bound skeleton expected, in a stable order (node id,
            then slot id, then value).
        reinsertion_clean: True only when `token_outcomes` is non-empty and
            every entry is `"reinsertable"`. An empty `token_outcomes` (a
            bound skeleton with no expected tokens at all) is deliberately
            NOT clean: there is nothing to prove re-insertion viable on, so
            treating it as a vacuous pass would silently inflate the
            clean-rate with non-data-points.
        round_trip_ok: Whether `check_sentinel_integrity(bound_skeleton,
            reinserted_document).ok` is True: the same integrity gate the
            fill pipeline already trusts, run against this module's own
            output, to prove the transform restores the exact expected token
            multiset whenever it claims success.
    """

    normalized_document: dict[str, object]
    reinserted_document: dict[str, object]
    token_outcomes: tuple[TokenOutcome, ...]
    reinsertion_clean: bool
    round_trip_ok: bool


@dataclass(frozen=True, slots=True)
class ReinsertionTrial:
    """One `reinsert_sentinels` result, tagged with which specimen/provider produced it.

    Mirrors `cyo_adventure.measurement.report.TrialRecord`'s shape for the
    sentinel-survival report, so the two CLIs read alike.

    Attributes:
        specimen_slug: The source skeleton slug the fill was run against.
        provider: The provider name the fill was produced by.
        result: The classified re-insertion outcome.
    """

    specimen_slug: str
    provider: str
    result: ReinsertionResult


@dataclass(frozen=True, slots=True)
class ReinsertionProviderStats:
    """Reinsertion-clean statistics for one provider.

    Attributes:
        provider: The provider name.
        total: Total trials aggregated for this provider.
        clean: Trials with `ReinsertionResult.reinsertion_clean` True.
        clean_rate: ``clean / total``.
    """

    provider: str
    total: int
    clean: int
    clean_rate: float


@dataclass(frozen=True, slots=True)
class ReinsertionAggregate:
    """The full aggregated re-insertion-viability report.

    Attributes:
        total_trials: Total trials aggregated.
        clean_trials: Trials with `reinsertion_clean` True.
        reinsertion_clean_rate: ``clean_trials / total_trials``.
        round_trip_ok_trials: Trials with `round_trip_ok` True.
        round_trip_ok_rate: ``round_trip_ok_trials / total_trials``.
        per_provider: Per-provider reinsertion-clean stats, sorted by
            provider name.
        outcome_histogram: Counts of every `(node, token)` pair's `status`
            across every trial, keyed by ``"reinsertable"`` /
            ``"not_found"``. Deliberately NOT keyed by the literal node id or
            token value: those are only unique within one specimen's own
            skeleton (two different stories both have a node called "n1"),
            so grouping by literal identity across trials would conflate
            unrelated nodes rather than measure the outcome distribution.
        multiplicity_histogram: Counts of every reinsertable token's
            `occurrence_count`, bucketed into ``"1"``, ``"2-3"``, ``"4+"``
            (a `not_found` token, count 0, is never bucketed here; it is
            already captured in `outcome_histogram`).
    """

    total_trials: int
    clean_trials: int
    reinsertion_clean_rate: float
    round_trip_ok_trials: int
    round_trip_ok_rate: float
    per_provider: tuple[ReinsertionProviderStats, ...]
    outcome_histogram: dict[str, int]
    multiplicity_histogram: dict[str, int]


# ---------------------------------------------------------------------------
# Step (a): strip every model-emitted sentinel, well-formed or malformed.
# ---------------------------------------------------------------------------


def _extract_malformed_inner_word(span: str) -> str:
    """Best-effort inner-word extraction from one malformed sentinel span.

    Looks for the canonical wrapper's ``:`` separator and takes everything
    after it, trimmed of a trailing closer (``~}``, a bare ``}``, or a
    dangling ``~``) and surrounding whitespace. This recovers the intended
    word from common near-misses: a truncated wrapper (``{~HERO:Explorer``),
    a lowercase or malformed slot id (``{~hero:Explorer~}``), or stray
    whitespace around the separators (``{~HERO : Explorer~}``).

    A malformed span with no colon at all (e.g. a bare unterminated
    ``{~HERO``) carries no recoverable inner word and yields the empty
    string, which strips the near-miss out of the prose entirely rather than
    leaving any forged sentinel-shaped syntax behind. This is the "where
    feasible" clause: extraction is attempted, never guaranteed.

    Args:
        span: One malformed near-miss substring, as returned by
            `cyo_adventure.storybook.sentinels.find_malformed_sentinels`.

    Returns:
        str: The best-effort recovered inner word, or the empty string when
            none could be recovered.
    """
    colon_index = span.find(":")
    if colon_index == -1:
        return ""
    inner = span[colon_index + 1 :]
    inner = _MALFORMED_TRAILER_RE.sub("", inner)
    return inner.strip()


def _strip_malformed_sentinels(text: str) -> str:
    """Replace every malformed sentinel-shaped near-miss in `text` with its inner word.

    Iterates `find_malformed_sentinels` to convergence: each replacement is
    strictly shorter than the span it replaces (the wrapper syntax is always
    at least the two-character ``{~`` opener), so the remaining text strictly
    shrinks on every iteration and the loop is guaranteed to terminate.

    Args:
        text: Text that may contain zero or more malformed near-misses. Must
            already have every WELL-FORMED sentinel replaced (see
            `strip_model_sentinels`), so this function only ever encounters
            genuine near-misses, never a well-formed token's own syntax.

    Returns:
        str: `text` with every malformed near-miss replaced by its
            best-effort extracted inner word (or removed, when none could be
            extracted).
    """
    result = text
    cursor = 0
    while True:
        spans = find_malformed_sentinels(result[cursor:])
        if not spans:
            break
        span = spans[0]
        index = result.index(span, cursor)
        inner = _extract_malformed_inner_word(span)
        result = result[:index] + inner + result[index + len(span) :]
        cursor = index + len(inner)
    return result


def strip_model_sentinels(text: str) -> str:
    """Replace every model-emitted sentinel token in `text` with its inner word.

    A well-formed sentinel (`SENTINEL_RE`) is replaced by its own captured
    inner value; a sentinel-shaped-but-malformed near-miss
    (`find_malformed_sentinels`) is replaced by its best-effort extracted
    inner word (see `_extract_malformed_inner_word`). Every replacement value
    is text the MODEL produced, never re-parsed as a sentinel itself: a
    well-formed token's inner value cannot contain ``{ } < > ' ~``
    (`cyo_adventure.storybook.sentinels.wrap`'s own forbidden-character
    guard), so this pass can never manufacture a new sentinel-shaped
    substring for the malformed pass to (mis)detect.

    #CRITICAL: data integrity: a model-emitted sentinel must never survive
    this pass; a surviving forged wrapper would let it masquerade as a
    correctly re-inserted one when `reinsert_sentinels` later runs
    `check_sentinel_integrity` against the output.
    #VERIFY: tests/unit/test_measurement_reinsertion.py::test_forged_sentinel_is_stripped_before_matching

    Args:
        text: Text that may contain zero or more sentinel tokens, well-formed
            or malformed.

    Returns:
        str: `text` with every sentinel-shaped substring replaced by its
            inner word.
    """
    stripped = SENTINEL_RE.sub(lambda match: match.group(2), text)
    return _strip_malformed_sentinels(stripped)


def _as_dict(value: object) -> dict[str, object] | None:
    """Narrow `value` to `dict[str, object]`, or `None` when it is not a dict."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _as_list(value: object) -> list[object] | None:
    """Narrow `value` to `list[object]`, or `None` when it is not a list."""
    return cast("list[object]", value) if isinstance(value, list) else None


def _normalize_ending(ending: dict[str, object]) -> None:
    """Normalize one ending dict's `title` in place, if it is a string."""
    title = ending.get("title")
    if isinstance(title, str):
        ending["title"] = strip_model_sentinels(title)


def _normalize_choices(choices: list[object]) -> None:
    """Normalize every choice dict's `label` in `choices` in place."""
    for raw_choice in choices:
        choice = _as_dict(raw_choice)
        if choice is None:
            continue
        label = choice.get("label")
        if isinstance(label, str):
            choice["label"] = strip_model_sentinels(label)


def _normalize_node(node: dict[str, object]) -> None:
    """Normalize one node's body, ending title, and choice labels in place."""
    body = node.get("body")
    if isinstance(body, str):
        node["body"] = strip_model_sentinels(body)
    ending = _as_dict(node.get("ending"))
    if ending is not None:
        _normalize_ending(ending)
    choices = _as_list(node.get("choices"))
    if choices is not None:
        _normalize_choices(choices)


def _normalize_document(document: Mapping[str, object]) -> dict[str, object]:
    """Return a deep copy of `document` with every model-emitted sentinel stripped.

    Every surface `cyo_adventure.validator.sentinel_integrity` scans (the
    top-level title, every node body, ending title, and choice label) is
    normalized, not only the body/ending-title surfaces this module later
    re-inserts into: the whole point of "never trust the LLM to preserve
    tokens" is that a model-emitted sentinel is never counted as a match,
    wherever in the document it landed.

    Args:
        document: The raw filled-blob mapping (or any raw story mapping).

    Returns:
        dict[str, object]: An independent deep copy with every string
            surface normalized via `strip_model_sentinels`.
    """
    doc = cast("dict[str, object]", copy.deepcopy(document))

    title = doc.get("title")
    if isinstance(title, str):
        doc["title"] = strip_model_sentinels(title)

    nodes = _as_list(doc.get("nodes"))
    if nodes is None:
        return doc
    for raw_node in nodes:
        node = _as_dict(raw_node)
        if node is not None:
            _normalize_node(node)
    return doc


# ---------------------------------------------------------------------------
# Step (b)/(c): expected tokens, occurrence counting, and classification.
# ---------------------------------------------------------------------------


def _expected_tokens_by_node(
    bound_skeleton: Mapping[str, object],
) -> dict[str, frozenset[_Token]]:
    """Return each node's expected sentinel token set (body + ending title).

    Mirrors the expectation model
    `cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity`
    builds internally (the same one
    `cyo_adventure.measurement.taxonomy.classify_fill` is scored against): a
    personalizable-slot sentinel is only ever legally placed in a node's body
    or its ending title, never a choice label or the top-level title.
    Re-derived locally, rather than importing that module's private helper,
    to keep this module's coupling to a stable public boundary
    (`check_sentinel_integrity` itself, used later for the round-trip proof)
    rather than another module's private surface.

    Args:
        bound_skeleton: The pre-fill bound skeleton (FILL directives intact;
            sentinels live inside the ``beats='...'`` guidance text, which
            this function scans as plain text, same as the checker does).

    Returns:
        dict[str, frozenset[_Token]]: Node id to its distinct `(slot_id,
            value)` expected tokens. A node with no expected tokens is
            simply absent from the mapping.
    """
    tokens_by_node: dict[str, set[_Token]] = {}
    nodes = _as_list(bound_skeleton.get("nodes"))
    if nodes is None:
        return {}
    for raw_node in nodes:
        node = _as_dict(raw_node)
        if node is None:
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        texts: list[str] = []
        body = node.get("body")
        if isinstance(body, str):
            texts.append(body)
        ending = _as_dict(node.get("ending"))
        if ending is not None:
            ending_title = ending.get("title")
            if isinstance(ending_title, str):
                texts.append(ending_title)
        for text in texts:
            tokens_by_node.setdefault(node_id, set()).update(find_sentinels(text))
    return {node_id: frozenset(tokens) for node_id, tokens in tokens_by_node.items()}


def _word_boundary_pattern(value: str) -> re.Pattern[str]:
    r"""Build a case-sensitive, whole-word regex for one expected inner value.

    Uses ``\b`` at each end of the escaped literal, so a match only counts
    when `value` appears as a whole word (or, for a multi-word value, a whole
    phrase) rather than as a substring of a longer word. This is a
    deliberate scoping decision: ``\bExplorer\b`` does NOT match inside
    ``Explorers``, since there is no boundary between the shared ``r`` and
    the trailing ``s`` (both are word characters). The strip-all-then-
    reinsert algorithm exists to avoid corrupting prose the fill LLM wrote
    for unrelated purposes, and wrapping a partial word inside a longer,
    unrelated one would do exactly that.

    Args:
        value: The expected token's inner generic value.

    Returns:
        re.Pattern[str]: A compiled, case-sensitive whole-word pattern.
    """
    return re.compile(r"\b" + re.escape(value) + r"\b")


def _count_in_node_surfaces(node: dict[str, object], value: str) -> int:
    """Count whole-word occurrences of `value` across one node's body and ending title.

    Args:
        node: The node dict to scan (already normalized; no model-emitted
            sentinel syntax remains).
        value: The expected token's inner generic value to search for.

    Returns:
        int: The total occurrence count across the node's body and (if
            present) ending title.
    """
    pattern = _word_boundary_pattern(value)
    total = 0
    body = node.get("body")
    if isinstance(body, str):
        total += len(pattern.findall(body))
    ending = _as_dict(node.get("ending"))
    if ending is not None:
        title = ending.get("title")
        if isinstance(title, str):
            total += len(pattern.findall(title))
    return total


def _wrap_all_in_node(
    node: dict[str, object], reinsertable_tokens: list[_Token]
) -> None:
    """Wrap every reinsertable token's occurrences in one node, in a single pass per surface.

    All of a node's reinsertable tokens are combined into one alternation
    pattern (longest value first, so the regex engine prefers the more
    specific match whenever two expected values could both match at the same
    position, e.g. ``"the pup"`` before ``"pup"``) and substituted in one
    `re.sub` call per surface. This matters because `re.sub` never re-enters
    text it has just inserted: a single combined pass guarantees a shorter
    token's pattern can never accidentally match inside the sentinel wrapper
    a longer token's own substitution just produced, which sequential
    independent per-token passes over the same mutable text would risk.

    Args:
        node: The node dict to mutate in place (its `body` and, if present,
            `ending.title` strings).
        reinsertable_tokens: The `(slot_id, value)` pairs to wrap, already
            filtered to this node's reinsertable (count >= 1) tokens.
    """
    if not reinsertable_tokens:
        return
    ordered = sorted(reinsertable_tokens, key=lambda token: -len(token[1]))
    replacement_by_value: dict[str, str] = {}
    pattern_parts: list[str] = []
    for slot_id, value in ordered:
        if value in replacement_by_value:
            continue
        replacement_by_value[value] = wrap(slot_id, value)
        pattern_parts.append(re.escape(value))
    pattern = re.compile(r"\b(" + "|".join(pattern_parts) + r")\b")

    def _replace(match: re.Match[str]) -> str:
        return replacement_by_value[match.group(1)]

    body = node.get("body")
    if isinstance(body, str):
        node["body"] = pattern.sub(_replace, body)
    ending = _as_dict(node.get("ending"))
    if ending is not None:
        title = ending.get("title")
        if isinstance(title, str):
            ending["title"] = pattern.sub(_replace, title)


def _index_nodes(document: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return a node-id-to-node-dict index over `document`'s `nodes` list.

    Args:
        document: A raw story mapping (mutable; the returned dicts are the
            SAME objects held in `document["nodes"]`, not copies).

    Returns:
        dict[str, dict[str, object]]: Node id to its node dict, for every
            node with a string id. A node with no string id is silently
            excluded (schema validity is the validation gate's job, not
            this module's).
    """
    nodes = _as_list(document.get("nodes"))
    if nodes is None:
        return {}
    indexed: dict[str, dict[str, object]] = {}
    for raw_node in nodes:
        node = _as_dict(raw_node)
        if node is None:
            continue
        node_id = node.get("id")
        if isinstance(node_id, str):
            indexed[node_id] = node
    return indexed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def reinsert_sentinels(
    bound_skeleton: Mapping[str, object], filled_blob: Mapping[str, object]
) -> ReinsertionResult:
    """Run the full strip-all-then-reinsert algorithm for one fill result.

    Args:
        bound_skeleton: The pre-fill bound skeleton the fill was given (a
            `cyo_adventure.measurement.fixtures.Specimen`'s
            `bound_skeleton`), used only to derive the expected per-node
            token set; never mutated.
        filled_blob: The fill's output document
            (`cyo_adventure.generation.orchestrator.GenerationOutcome.storybook`),
            never mutated (every transform works on deep copies).

    Returns:
        ReinsertionResult: The normalized document, the fully re-inserted
            document, every `(node, token)` outcome, and the story-level
            `reinsertion_clean` / `round_trip_ok` verdicts.
    """
    expected = _expected_tokens_by_node(bound_skeleton)
    normalized = _normalize_document(filled_blob)
    reinserted = copy.deepcopy(normalized)
    nodes_by_id = _index_nodes(reinserted)

    outcomes: list[TokenOutcome] = []
    for node_id in sorted(expected):
        node = nodes_by_id.get(node_id)
        reinsertable_tokens: list[_Token] = []
        for slot_id, value in sorted(expected[node_id]):
            count = _count_in_node_surfaces(node, value) if node is not None else 0
            status: _TokenStatus = "reinsertable" if count >= 1 else "not_found"
            outcomes.append(
                TokenOutcome(
                    node_id=node_id,
                    slot_id=slot_id,
                    value=value,
                    occurrence_count=count,
                    status=status,
                )
            )
            if status == "reinsertable":
                reinsertable_tokens.append((slot_id, value))
        if node is not None:
            _wrap_all_in_node(node, reinsertable_tokens)

    reinsertion_clean = bool(outcomes) and all(
        outcome.status == "reinsertable" for outcome in outcomes
    )
    round_trip_ok = check_sentinel_integrity(bound_skeleton, reinserted).ok

    return ReinsertionResult(
        normalized_document=normalized,
        reinserted_document=reinserted,
        token_outcomes=tuple(outcomes),
        reinsertion_clean=reinsertion_clean,
        round_trip_ok=round_trip_ok,
    )


# ---------------------------------------------------------------------------
# Aggregation across many trials
# ---------------------------------------------------------------------------


def _multiplicity_bucket(count: int) -> str:
    """Sort one reinsertable token's occurrence count into a multiplicity bucket.

    Args:
        count: A reinsertable token's `occurrence_count` (always >= 1; a
            `not_found` token, count 0, is never passed here).

    Returns:
        str: `_MULTIPLICITY_SINGLE` for exactly 1, `_MULTIPLICITY_FEW` for 2
            or 3, `_MULTIPLICITY_MANY` for 4 or more.

    Raises:
        ValueError: If `count` is not positive; a non-positive count has no
            defined bucket (it belongs in `outcome_histogram` as
            ``"not_found"`` instead).
    """
    if count < 1:
        msg = f"multiplicity bucket undefined for non-positive count: {count}"
        raise ValueError(msg)
    if count == 1:
        return _MULTIPLICITY_SINGLE
    if count <= 3:
        return _MULTIPLICITY_FEW
    return _MULTIPLICITY_MANY


def aggregate_reinsertion(trials: Sequence[ReinsertionTrial]) -> ReinsertionAggregate:
    """Aggregate a flat sequence of re-insertion trials into a full report.

    Args:
        trials: Every trial run, across every specimen and provider.

    Returns:
        ReinsertionAggregate: The aggregated clean rates, per-provider split,
            outcome histogram, and occurrence-multiplicity distribution.

    Raises:
        ValueError: If `trials` is empty; there is nothing to report on.
    """
    if not trials:
        msg = "cannot aggregate an empty reinsertion trial sequence"
        raise ValueError(msg)

    total_trials = len(trials)
    clean_trials = sum(1 for trial in trials if trial.result.reinsertion_clean)
    round_trip_ok_trials = sum(1 for trial in trials if trial.result.round_trip_ok)

    per_provider_totals: dict[str, int] = {}
    per_provider_clean: dict[str, int] = {}
    outcome_histogram: dict[str, int] = {}
    multiplicity_histogram: dict[str, int] = {}

    for trial in trials:
        per_provider_totals[trial.provider] = (
            per_provider_totals.get(trial.provider, 0) + 1
        )
        if trial.result.reinsertion_clean:
            per_provider_clean[trial.provider] = (
                per_provider_clean.get(trial.provider, 0) + 1
            )
        for outcome in trial.result.token_outcomes:
            outcome_histogram[outcome.status] = (
                outcome_histogram.get(outcome.status, 0) + 1
            )
            if outcome.status == "reinsertable":
                bucket = _multiplicity_bucket(outcome.occurrence_count)
                multiplicity_histogram[bucket] = (
                    multiplicity_histogram.get(bucket, 0) + 1
                )

    per_provider = tuple(
        ReinsertionProviderStats(
            provider=provider,
            total=total,
            clean=per_provider_clean.get(provider, 0),
            clean_rate=per_provider_clean.get(provider, 0) / total,
        )
        for provider, total in sorted(per_provider_totals.items())
    )

    return ReinsertionAggregate(
        total_trials=total_trials,
        clean_trials=clean_trials,
        reinsertion_clean_rate=clean_trials / total_trials,
        round_trip_ok_trials=round_trip_ok_trials,
        round_trip_ok_rate=round_trip_ok_trials / total_trials,
        per_provider=per_provider,
        outcome_histogram=outcome_histogram,
        multiplicity_histogram=multiplicity_histogram,
    )


# ---------------------------------------------------------------------------
# Report rendering (mirrors cyo_adventure.measurement.report's style)
# ---------------------------------------------------------------------------


def render_json(data: ReinsertionAggregate) -> dict[str, object]:
    """Render a re-insertion report as a machine-readable JSON-serializable mapping.

    Args:
        data: The aggregated report.

    Returns:
        dict[str, object]: A plain-data mapping safe to pass to ``json.dumps``.
    """
    return {
        "total_trials": data.total_trials,
        "clean_trials": data.clean_trials,
        "reinsertion_clean_rate": data.reinsertion_clean_rate,
        "round_trip_ok_trials": data.round_trip_ok_trials,
        "round_trip_ok_rate": data.round_trip_ok_rate,
        "per_provider": [
            {
                "provider": stats.provider,
                "total": stats.total,
                "clean": stats.clean,
                "clean_rate": stats.clean_rate,
            }
            for stats in data.per_provider
        ],
        "outcome_histogram": dict(data.outcome_histogram),
        "multiplicity_histogram": dict(data.multiplicity_histogram),
    }


def render_markdown(data: ReinsertionAggregate) -> str:
    """Render a re-insertion report as a human-readable markdown summary.

    Args:
        data: The aggregated report.

    Returns:
        str: A markdown document stating the reinsertion-clean rate, the
            round-trip-ok rate, per-provider variance, the per-(node, token)
            outcome histogram, and the occurrence-multiplicity distribution.
    """
    lines: list[str] = ["# Sentinel re-insertion prototype report", ""]
    lines.append(
        " ".join(
            [
                "Strip-all-then-reinsert clean rate:",
                f"**{data.reinsertion_clean_rate:.1%}**",
                f"({data.clean_trials}/{data.total_trials})",
            ]
        )
    )
    lines.append("")
    lines.append(
        " ".join(
            [
                "Round-trip integrity-check pass rate (proves a clean",
                "reinsertion restores the exact expected token multiset):",
                f"**{data.round_trip_ok_rate:.1%}**",
                f"({data.round_trip_ok_trials}/{data.total_trials})",
            ]
        )
    )
    lines.append("")

    lines.append("## Per-provider variance")
    lines.append("")
    lines.append("| Provider | Clean | Total | Clean rate |")
    lines.append("| --- | --- | --- | --- |")
    lines.extend(
        f"| {stats.provider} | {stats.clean} | {stats.total} | {stats.clean_rate:.1%} |"
        for stats in data.per_provider
    )
    lines.append("")

    lines.append("## Per-(node, token) outcome histogram")
    lines.append("")
    lines.append("| Outcome | Count |")
    lines.append("| --- | --- |")
    lines.extend(
        f"| {status} | {data.outcome_histogram[status]} |"
        for status in sorted(data.outcome_histogram)
    )
    if not data.outcome_histogram:
        lines.append("| (none) | 0 |")
    lines.append("")

    lines.append("## Occurrence-multiplicity distribution (reinsertable tokens only)")
    lines.append("")
    lines.append("| Occurrences | Count |")
    lines.append("| --- | --- |")
    lines.extend(
        f"| {bucket} | {data.multiplicity_histogram.get(bucket, 0)} |"
        for bucket in (_MULTIPLICITY_SINGLE, _MULTIPLICITY_FEW, _MULTIPLICITY_MANY)
    )
    lines.append("")

    return "\n".join(lines)
