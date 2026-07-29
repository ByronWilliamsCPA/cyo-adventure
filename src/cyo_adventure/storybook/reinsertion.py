"""Deterministic sentinel re-insertion: the domain transform (ADR-023 Stage R, Task R2).

Promoted from `cyo_adventure.measurement.reinsertion` (the plan 3.4 offline
prototype) into the storybook domain package, so the production fill path
(Task R3, `generation/worker.py`) can call the same deterministic transform
the offline measurement tooling has been proving out, rather than trusting
the fill LLM to preserve a personalization sentinel
(`cyo_adventure.storybook.sentinels.wrap`) verbatim.

**Strip-all-then-reinsert.** The fill LLM's dominant failure mode is dropping
a sentinel wrapper and writing the bare inner word instead (e.g. writing
plain ``Explorer`` where the pre-fill skeleton declared
``{~HERO:Explorer~}``). Rather than trust the model to preserve a sentinel at
all, this module never trusts one: it deterministically re-inserts every
expected sentinel after the fact by

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
3. Classifying each `(node, token)` pair as ``"not_found"`` (count 0: the
   model paraphrased the word away entirely), ``"ambiguous"`` (the word is
   present, but another slot in the same node is bound to the same generic
   value, so no occurrence can be attributed to this slot), or
   ``"reinsertable"`` (count >= 1 and unambiguously this slot's).
4. Wrapping every matched occurrence with the canonical sentinel (a name
   slot personalizes every mention, not just the first).

**The manifest contract.** `reinsert_storybook` returns a `manifest`: a
JSON-serializable record of the exact per-node, per-surface multiset of
sentinel tokens the transform actually inserted, derived directly by
re-scanning the transform's own output (never from the pre-fill skeleton's
declared expectations). This is the DERIVED at-rest expectation (derive, not
prescribe) a later integrity re-check (Task R3's persisted-blob checks) needs
to verify "does this stored blob still carry the sentinels it was published
with" without re-reading the theme contract. Because the manifest is scanned
straight from the document `reinsert_storybook` also returns, verifying the
returned document against the returned manifest (`verify_manifest`) always
passes by construction; see `MANIFEST_ENDING_TITLE_SUFFIX` for the manifest's
keying scheme.

Pure: every function here is a plain data transform over already-loaded
mappings, with no network, provider, or filesystem calls. The one exception
is `_log_unreinserted`, a single structured warning on the way out, because a
dropped personalization slot is otherwise a completely silent outcome.
`cyo_adventure.measurement.reinsertion` (the offline measurement CLI's
library) and, from Task R3, `generation/worker.py` are the only I/O-adjacent
callers of this module.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from cyo_adventure.storybook.sentinels import (
    SENTINEL_RE,
    find_malformed_sentinel_spans,
    find_sentinels,
    wrap,
)
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = get_logger(__name__)

# The three possible per-(node, token) outcomes of the strip-all-then-reinsert
# algorithm. ``"ambiguous"`` exists because the other two cannot describe a
# value collision honestly: see `_value_owner`.
_TokenStatus = Literal["reinsertable", "not_found", "ambiguous"]

# A single-node expected token, as (slot_id, value); mirrors the private
# `_Token` alias in `cyo_adventure.validator.sentinel_integrity`.
_Token = tuple[str, str]

# A sentence-start position: the very start of the text, the start of a line
# (immediately after a newline), or the whitespace run immediately following
# a sentence-terminating punctuation mark and an optional single closing
# quote character. Captured as a whole group by every caller that builds on
# this fragment (never used as a lookbehind): the punctuation+quote+
# whitespace branch is variable-width (`\s+` can consume more than one
# character), and Python `re` requires a fixed-width lookbehind, so a
# captured leading group whose text is re-emitted verbatim is the only way to
# assert this context without consuming and discarding it. Uses the literal
# Unicode right single/double quotation marks (rather than `\uXXXX` escapes)
# so the character class is unambiguous at a glance; RUF001 flags exactly
# these two characters as visually ambiguous with their ASCII look-alikes,
# which is precisely why they are spelled out literally here instead of left
# for a reader to guess at, so the rule is suppressed on this line only.
_SENTENCE_START_PREFIX = r"(?:\A|\n|[.!?][\"'’”]?\s+)"  # noqa: RUF001

# The manifest's ending-title surface key suffix: a node's body surface is
# keyed by its bare node id (e.g. ``"n1"``); its ending-title surface (only
# present on an ending node) is keyed by the node id plus this suffix (e.g.
# ``"n1::ending_title"``). Two distinct keys per node, rather than one
# combined key, because a node's body and its ending title are two
# independent sentinel surfaces (the same split
# `cyo_adventure.validator.sentinel_integrity` scans separately): a single
# combined key would conflate "the personalized mention is in the
# reader-facing ending headline" with "it is buried in scrollable body
# prose", and make a later at-rest diff describe WHERE a corruption happened
# less precisely than this two-key scheme does. A node id is never legally
# suffixed with this string on its own (node ids come from the skeleton
# author, not from user input), so no real node id can collide with a
# derived ending-title key.
MANIFEST_ENDING_TITLE_SUFFIX = "::ending_title"


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
        status: ``"not_found"`` when `occurrence_count` is zero (the model
            paraphrased the word away); ``"ambiguous"`` when the word IS
            present but another slot in the same node is bound to the same
            generic value and won the tie (see `_value_owner`), so this slot
            contributed no sentinel to `document`; ``"reinsertable"``
            otherwise, and only then is this slot's value actually wrapped.
    """

    node_id: str
    slot_id: str
    value: str
    occurrence_count: int
    status: _TokenStatus


@dataclass(frozen=True, slots=True)
class ReinsertionOutcome:
    """The full strip-all-then-reinsert outcome for one bound skeleton / filled document pair.

    This is the production-facing contract Task R3 persists: `document` is
    the finished, gate-ready content; `manifest` is the derived at-rest
    expectation stored alongside it (e.g. in a JSONB column) so a later
    integrity re-check can verify the stored blob still matches without
    re-reading the theme contract.

    Attributes:
        document: A deep copy of `filled_document` with every model-emitted
            sentinel (well-formed or malformed) stripped to its own inner
            word, and every deterministically reinsertable token's
            occurrences wrapped back into the canonical sentinel form. A
            `TokenOutcome` with `status` ``"not_found"`` contributes nothing
            here (there is nothing to wrap), and neither does one with
            `status` ``"ambiguous"`` (another slot owns the only occurrence).
        manifest: The at-rest sentinel manifest, derived by re-scanning
            `document` itself (see `build_manifest`): the exact per-node,
            per-surface multiset of sentinel tokens actually present. Plain
            dicts, lists, and strings only (safe to pass to `json.dumps`
            unmodified), with deterministic key and entry ordering.

            A manifest entry's VALUE is the text as it appears in the
            document, which for a sentence-start match is the capitalized
            variant of the declared value: a contract declaring
            ``explorer`` yields ``{~HERO:Explorer~}``, and therefore a
            manifest value of ``Explorer``, wherever the mention opens a
            sentence (see `_sentence_start_pattern`). This is deliberate;
            the wrapped fallback word has to read correctly in place. It
            does mean a future manifest READER must not compare these
            values against the theme contract's declared values for
            equality: derive-not-prescribe applies to the value as much as
            to the token multiset. Nothing reads the manifest yet (the
            `storybook_version.sentinel_manifest` column is written only),
            so this is a note for the reader that comes later, not a
            description of an existing comparison.
        token_outcomes: One `TokenOutcome` per `(node, token)` pair the
            pre-fill bound skeleton expected, in a stable order (node id,
            then slot id, then value); sufficient on its own for a caller to
            recompute reinsertion-viability statistics (found/not-found
            counts, occurrence-multiplicity distribution) without
            re-implementing the matcher.
        sentence_start_hits: How many occurrences across the whole document
            were classified `"reinsertable"` only because a sentence-start
            capitalized variant of a lowercase-starting expected value was
            matched (the base, unwidened pattern found nothing at that
            position).
        plural_occurrences: How many `<value>s` occurrences (case-sensitive,
            whole-word) were found across the whole document for expected
            values that are NOT themselves wrapped or counted toward
            `TokenOutcome.occurrence_count`: a plural mention is data,
            never re-inserted.
    """

    document: dict[str, object]
    manifest: dict[str, object]
    token_outcomes: tuple[TokenOutcome, ...]
    sentence_start_hits: int
    plural_occurrences: int


# ---------------------------------------------------------------------------
# Step (a): strip every model-emitted sentinel, well-formed or malformed.
# ---------------------------------------------------------------------------


def _strip_trailing_closer(text: str) -> str:
    """Remove a trailing sentinel closer run (and the whitespace after it).

    Equivalent to substituting a trailing ``[~}]+`` run plus any whitespace
    after it with the empty string, computed in linear time.

    Args:
        text: The candidate inner text of a malformed near-miss span.

    Returns:
        str: `text` with a trailing closer run, plus any whitespace following
            that run, removed. Returned unchanged when the text does not end
            in a closer run followed only by whitespace: the pattern is
            end-anchored, so a closer sitting in the middle of the text
            (``"Explorer~} x"``) is not a trailer and is left alone.
    """
    # #CRITICAL: external-resources: the regex form backtracked quadratically
    # on adversarial model output. The pattern had to be retried at every
    # start offset, and on text whose LAST character is neither a closer nor
    # whitespace ("~~~~...~x") each retry consumed the whole remaining tilde
    # run before failing: measured 1.8 s on a 16k-tilde string against 0.004 ms
    # for this linear form, inside the generation worker's own fill path.
    # Nothing upstream bounds how many tildes a model may emit, so the bound
    # has to be here.
    # #VERIFY: tests/unit/test_storybook_reinsertion.py::
    # test_trailing_closer_strip_is_linear_on_a_long_tilde_run and
    # ::test_trailing_closer_strip_matches_the_regex_it_replaced.
    #
    # The pattern must reach the end of the string, so the only candidate is a
    # closer run ending where trailing whitespace begins. `str.rstrip()` and
    # `\s` agree on what whitespace is (both are Unicode-aware).
    end = len(text.rstrip())
    if end == 0 or text[end - 1] not in "~}":
        return text
    start = end
    while start > 0 and text[start - 1] in "~}":
        start -= 1
    return text[:start]


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
    return _strip_trailing_closer(span[colon_index + 1 :]).strip()


def _strip_malformed_sentinels(text: str) -> str:
    """Replace every malformed sentinel-shaped near-miss in `text` with its inner word.

    One left-to-right pass over the offsets `find_malformed_sentinel_spans`
    reports, which are non-overlapping and strictly increasing. A replacement
    can splice the surrounding remains into a NEW near-miss; converging on
    that is `strip_model_sentinels`' job, since only its loop also re-runs
    the well-formed pass that the same splice can produce.

    # #CRITICAL: data integrity: this rewrites by OFFSET, never by re-locating
    # the returned substring with `str.index`. The scan resolves a span at a
    # specific position; the same characters can occur earlier in the text as
    # a slice of a different span the scan parsed as a whole, and rewriting
    # that earlier occurrence instead leaves sentinel-shaped debris in
    # reader-facing prose. Measured on the nested case
    # ``{~HE{~A:R{~Q:O~}~}:Explorer~}``, which stripped to a literal
    # ``RO:Explorer~}`` in the body.
    # #VERIFY: tests/unit/test_storybook_reinsertion.py::
    # test_nested_near_miss_leaves_no_sentinel_debris.

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
    spans = find_malformed_sentinel_spans(text)
    if not spans:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        pieces.append(_extract_malformed_inner_word(text[start:end]))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def strip_model_sentinels(text: str) -> str:
    """Replace every model-emitted sentinel token in `text` with its inner word.

    A well-formed sentinel (`SENTINEL_RE`) is replaced by its own captured
    inner value; a sentinel-shaped-but-malformed near-miss
    (`find_malformed_sentinel_spans`) is replaced by its best-effort extracted
    inner word (see `_extract_malformed_inner_word`).

    #CRITICAL: data integrity: a model-emitted sentinel must never survive
    this pass; a surviving forged wrapper would let it masquerade as a
    correctly re-inserted one when `reinsert_storybook` later builds
    `manifest` from `document`. A SINGLE pass does not achieve that, which is
    why this runs to a fixed point: `re.sub` never rescans its own
    replacement text, so removing an inner token can splice the surrounding
    remains into a NEW well-formed wrapper that the same pass has already
    walked past. Measured: one pass turns
    ``{~HE{~A:RO~}:Explorer~}`` into the intact sentinel
    ``{~HERO:Explorer~}``, and `_strip_malformed_sentinels` then declines to
    touch it precisely because it is well-formed. The loop terminates because
    every replacement (well-formed or malformed) is strictly shorter than the
    span it replaces, so `len(result)` strictly decreases on every iteration
    that changes anything.
    #VERIFY: tests/unit/test_storybook_reinsertion.py::test_nested_sentinel_is_fully_stripped

    Args:
        text: Text that may contain zero or more sentinel tokens, well-formed
            or malformed, at any nesting depth.

    Returns:
        str: `text` with every sentinel-shaped substring replaced by its
            inner word, and with no sentinel-shaped substring remaining at
            any depth (this function is idempotent on its own output).
    """
    result = text
    while True:
        stripped = _strip_malformed_sentinels(
            SENTINEL_RE.sub(lambda match: match.group(2), result)
        )
        if stripped == result:
            return _drop_orphan_closers(result)
        result = stripped


def _drop_orphan_closers(text: str) -> str:
    """Remove any bare ``~}`` left with no opener to belong to.

    # #CRITICAL: data integrity: the fixed-point loop above guarantees no
    # WHOLE sentinel-shaped span survives, but not that no sentinel SYNTAX
    # does, and the docstring's postcondition claims the stronger thing.
    # Stripping an unterminated opener orphans whatever followed it: the
    # nested case `{~HE{~A:R{~Q:O~}~}:Explorer~}` resolves `{~HE` as an
    # unterminated near-miss, drops it, and leaves the outer token's own tail
    # `:Explorer~}` sitting in reader-facing prose. `find_malformed_sentinels`
    # deliberately does NOT report such an orphan (an unpaired `~}` is
    # ordinary prose there, a rule that protects the at-rest dormancy
    # invariant against brace-bearing story text), so the cleanup has to
    # happen here, on fill output, rather than by widening that detector.
    # Removing `~}` from prose is safe in a way removing `}` would not be: the
    # closer is a two-character sequence with no legitimate use in a
    # children's story, and by this point the text provably contains no
    # well-formed sentinel whose closer this could be.
    # #VERIFY: tests/unit/test_storybook_reinsertion.py::
    # test_nested_sentinel_leaves_no_closer_debris.

    Args:
        text: Already-converged output of the strip loop above, which
            therefore contains no well-formed sentinel and no near-miss.

    Returns:
        str: `text` with every remaining ``~}`` removed.
    """
    return text.replace("~}", "")


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
    builds internally: a personalizable-slot sentinel is only ever legally
    placed in a node's body or its ending title, never a choice label or the
    top-level title. Re-derived locally, rather than importing that module's
    private helper, to keep this module's coupling to a stable public
    boundary (`check_sentinel_integrity` itself, used by `verify_manifest`)
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


def _node_surface_texts(node: dict[str, object]) -> list[str]:
    """Return one node's body and (if present) ending-title strings, in that order.

    Args:
        node: The node dict to read (never mutated).

    Returns:
        list[str]: The node's scannable text surfaces (body, then ending
            title); empty if neither is a string.
    """
    texts: list[str] = []
    body = node.get("body")
    if isinstance(body, str):
        texts.append(body)
    ending = _as_dict(node.get("ending"))
    if ending is not None:
        title = ending.get("title")
        if isinstance(title, str):
            texts.append(title)
    return texts


def _capitalize_first(value: str) -> str:
    """Uppercase only `value`'s first character, leaving the rest untouched.

    Args:
        value: A non-empty string.

    Returns:
        str: `value` with its first character uppercased.
    """
    return value[0].upper() + value[1:]


def _sentence_start_pattern(value: str) -> re.Pattern[str] | None:
    """Build a sentence-start counting pattern for one expected value, or None.

    Applies only to a `value` whose first character is lowercase (the
    sentence-start widening only ever needs to recover a grammatically
    correct capitalization of an otherwise-lowercase generic word; a value
    that already starts uppercase is matched by `_word_boundary_pattern`
    alone, at every position, so no separate variant is needed for it).

    Args:
        value: The expected token's inner generic value.

    Returns:
        re.Pattern[str] | None: A compiled pattern matching
            `_SENTENCE_START_PREFIX` immediately followed by `value` with
            only its first character uppercased, or `None` when `value`
            does not start with a lowercase character.
    """
    if not value[:1].islower():
        return None
    return re.compile(
        _SENTENCE_START_PREFIX + re.escape(_capitalize_first(value)) + r"\b"
    )


def _plural_pattern(value: str) -> re.Pattern[str]:
    """Build a case-sensitive, whole-word regex for `value`'s simple plural.

    Args:
        value: The expected token's inner generic value.

    Returns:
        re.Pattern[str]: A compiled pattern matching `value` with a trailing
            ``s``, at word boundaries (so ``Explorer`` matches ``Explorers``
            here, the exact complement of `_word_boundary_pattern`, which
            never matches inside it).
    """
    return re.compile(r"\b" + re.escape(value) + r"s\b")


def _count_in_node_surfaces(node: dict[str, object], value: str) -> int:
    """Count whole-word occurrences of `value` across one node's body and ending title.

    Includes both the base, case-sensitive whole-word match and, for a
    `value` starting with a lowercase character, its sentence-start
    capitalized variant (see `_sentence_start_pattern`): both are legitimate
    re-insertable occurrences of the same expected token, so both count
    toward `TokenOutcome.occurrence_count` and its ``"reinsertable"`` /
    ``"not_found"`` classification.

    Args:
        node: The node dict to scan (already normalized; no model-emitted
            sentinel syntax remains).
        value: The expected token's inner generic value to search for.

    Returns:
        int: The total occurrence count across the node's body and (if
            present) ending title.
    """
    pattern = _word_boundary_pattern(value)
    sentence_start = _sentence_start_pattern(value)
    total = 0
    for text in _node_surface_texts(node):
        total += len(pattern.findall(text))
        if sentence_start is not None:
            total += len(sentence_start.findall(text))
    return total


def _count_plural_occurrences(node: dict[str, object], value: str) -> int:
    """Count whole-word occurrences of `value`'s simple plural in one node.

    Data collection only: a plural mention is never wrapped, only counted,
    to size a future plural policy.

    Args:
        node: The node dict to scan (already normalized).
        value: The expected token's inner generic value.

    Returns:
        int: The total plural occurrence count across the node's body and
            (if present) ending title.
    """
    pattern = _plural_pattern(value)
    return sum(len(pattern.findall(text)) for text in _node_surface_texts(node))


def _build_node_wrap_pattern(
    reinsertable_tokens: list[_Token],
) -> tuple[re.Pattern[str], dict[str, _Token], dict[str, str]]:
    """Build one node's combined single-pass wrap alternation.

    All of a node's reinsertable tokens are combined into one alternation
    pattern (longest value first, so the regex engine prefers the more
    specific match whenever two expected values could both match at the same
    position, e.g. ``"the pup"`` before ``"pup"``). Combining every token
    into ONE pattern, substituted in a single `re.sub` call per surface, is
    what `_wrap_all_in_node` relies on for its no-double-wrap guarantee:
    `re.sub` never re-enters text it has just inserted, so a single combined
    pass guarantees a shorter token's pattern can never accidentally match
    inside the sentinel wrapper a longer token's own substitution just
    produced, which sequential independent per-token passes over the same
    mutable text would risk.

    For a `value` starting with a lowercase character, the alternation also
    carries a sentence-start branch: `_SENTENCE_START_PREFIX` in its own
    named group (re-emitted verbatim, never consumed by the sentinel wrap),
    immediately followed by `value` with only its first character
    uppercased. Folding this into the SAME alternation (rather than a
    second, separate pattern) is what keeps a mid-sentence and a
    sentence-start match mutually exclusive at any one position, and what
    guarantees a token can never be double-wrapped by both branches.

    Args:
        reinsertable_tokens: The `(slot_id, value)` pairs to wrap, already
            filtered to one node's reinsertable tokens. Values are distinct:
            `reinsert_storybook` resolves same-value collisions via
            `_value_owner` before calling this, so at most one slot per
            distinct value ever reaches here.

    Returns:
        tuple[re.Pattern[str], dict[str, _Token], dict[str, str]]: The
            compiled alternation pattern; a map from every content group
            name (both the plain `v{i}` groups and the sentence-start `p{i}`
            groups) to the token it belongs to; and a map from a
            sentence-start content group's name to its own leading prefix
            group's name (absent for a plain group).
    """
    ordered = sorted(reinsertable_tokens, key=lambda token: -len(token[1]))
    # Defense in depth behind `_value_owner`'s upstream de-duplication: a
    # duplicate value would add a second, permanently unreachable alternation
    # branch (the earlier branch always matches first), which is how the
    # losing slot used to end up reporting "reinsertable" with zero sentinels
    # inserted. Dropping it here is now a no-op on well-formed input; the
    # STATUS decision it used to make silently lives in `_value_owner`.
    seen_values: set[str] = set()
    pattern_parts: list[str] = []
    token_by_group: dict[str, _Token] = {}
    prefix_group_by_content_group: dict[str, str] = {}
    group_index = 0

    for slot_id, value in ordered:
        if value in seen_values:
            continue
        seen_values.add(value)

        content_group = f"v{group_index}"
        token_by_group[content_group] = (slot_id, value)
        pattern_parts.append(rf"(?P<{content_group}>\b{re.escape(value)}\b)")
        group_index += 1

        if not value[:1].islower():
            continue
        cap_value = _capitalize_first(value)
        prefix_group = f"pre{group_index}"
        start_group = f"p{group_index}"
        token_by_group[start_group] = (slot_id, value)
        prefix_group_by_content_group[start_group] = prefix_group
        prefix_part = rf"(?P<{prefix_group}>{_SENTENCE_START_PREFIX})"
        value_part = rf"(?P<{start_group}>{re.escape(cap_value)}\b)"
        pattern_parts.append(prefix_part + value_part)
        group_index += 1

    return (
        re.compile("|".join(pattern_parts)),
        token_by_group,
        prefix_group_by_content_group,
    )


def _wrap_all_in_node(
    node: dict[str, object], reinsertable_tokens: list[_Token]
) -> int:
    """Wrap every reinsertable token's occurrences in one node, in a single pass per surface.

    See `_build_node_wrap_pattern` for how the single combined alternation
    (plain plus, where applicable, sentence-start branches) is built.

    Args:
        node: The node dict to mutate in place (its `body` and, if present,
            `ending.title` strings).
        reinsertable_tokens: The `(slot_id, value)` pairs to wrap, already
            filtered to this node's reinsertable (count >= 1) tokens.

    Returns:
        int: The total count of matches that only fired via the
            sentence-start branch.
    """
    if not reinsertable_tokens:
        return 0

    pattern, token_by_group, prefix_group_by_content_group = _build_node_wrap_pattern(
        reinsertable_tokens
    )

    sentence_start_hits = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal sentence_start_hits
        for group_name, token in token_by_group.items():
            text = match.group(group_name)
            if text is None:
                continue
            prefix_group = prefix_group_by_content_group.get(group_name)
            if prefix_group is None:
                return wrap(token[0], text)
            sentence_start_hits += 1
            return match.group(prefix_group) + wrap(token[0], text)
        # Unreachable: `pattern` only ever matches one of the alternatives
        # enumerated in `token_by_group`.
        return match.group(0)

    body = node.get("body")
    if isinstance(body, str):
        node["body"] = pattern.sub(_replace, body)
    ending = _as_dict(node.get("ending"))
    if ending is not None:
        title = ending.get("title")
        if isinstance(title, str):
            ending["title"] = pattern.sub(_replace, title)

    return sentence_start_hits


def _value_owner(tokens: list[_Token]) -> dict[str, str]:
    """Pick the one slot id allowed to wrap each distinct expected value in a node.

    Two slots in the SAME node bound to the same generic value (e.g. both
    ``HERO`` and ``SIDEKICK`` bound to ``"Explorer"``) is a binding defect,
    not a fill defect: one text occurrence of ``Explorer`` cannot be
    attributed to one slot rather than the other, so no deterministic
    re-insertion is possible for the loser. The wrap pass has always resolved
    this by wrapping each distinct value once, for whichever slot sorted
    first; what it did not do was say so, leaving the losing slot reporting
    ``"reinsertable"`` while contributing zero sentinels to the document and
    zero entries to the manifest.

    #ASSUME: data integrity: the winner is the alphabetically-first slot id,
    chosen for determinism only. There is no domain reason to prefer either
    slot; the point is that the OTHER slot is then classified
    ``"ambiguous"`` rather than mislabeled ``"reinsertable"``, so a caller
    computing coverage sees the collision instead of a false 100%.
    #VERIFY: tests/unit/test_storybook_reinsertion.py::test_two_slots_sharing_one_value_report_ambiguous

    Args:
        tokens: One node's full `(slot_id, value)` expectation list.

    Returns:
        dict[str, str]: Each distinct value mapped to its owning slot id.
    """
    owner: dict[str, str] = {}
    for slot_id, value in sorted(tokens):
        owner.setdefault(value, slot_id)
    return owner


def _classify_token(count: int, *, owns_value: bool) -> _TokenStatus:
    """Classify one `(node, token)` pair from its occurrence count and value ownership.

    Args:
        count: Whole-word occurrences of the token's value in the node.
        owns_value: Whether this slot won its value per `_value_owner`.

    Returns:
        _TokenStatus: The outcome status; see `TokenOutcome.status`.
    """
    if count < 1:
        return "not_found"
    if not owns_value:
        return "ambiguous"
    return "reinsertable"


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
# The manifest: derived directly from the transform's own output.
# ---------------------------------------------------------------------------


def _manifest_key(node_id: str, *, ending_title: bool) -> str:
    """Build one node/surface's manifest key per `MANIFEST_ENDING_TITLE_SUFFIX`'s scheme."""
    if ending_title:
        return f"{node_id}{MANIFEST_ENDING_TITLE_SUFFIX}"
    return node_id


def _tally_sentinels(text: str) -> dict[_Token, int]:
    """Count occurrences of each distinct well-formed sentinel token in `text`."""
    tally: dict[_Token, int] = {}
    for token in find_sentinels(text):
        tally[token] = tally.get(token, 0) + 1
    return tally


def _manifest_entries(tally: dict[_Token, int]) -> list[dict[str, object]]:
    """Render one surface's tally as a deterministically ordered, JSON-safe entry list.

    Sorted by `(slot_id, value)`, so the same document always yields
    byte-identical manifest JSON regardless of dict-iteration history.
    """
    return [
        {"slot_id": slot_id, "value": value, "count": count}
        for (slot_id, value), count in sorted(tally.items())
    ]


def build_manifest(document: Mapping[str, object]) -> dict[str, object]:
    """Derive the at-rest sentinel manifest directly from a document's actual content.

    Scans `document` itself (never a pre-fill skeleton or theme contract)
    for every well-formed sentinel, tallying occurrences per node and
    surface. Because this reads straight off the same document
    `reinsert_storybook` returns, `verify_manifest(document, manifest)`
    always accepts a manifest built this way from that same document: the
    round-trip property holds by construction, not by a separate proof step.

    **Keying scheme.** The returned mapping's ``"tokens"`` entry is a flat
    dict from a manifest key to that surface's token-entry list:

    - A node's body surface is keyed by its bare node id (e.g. ``"n1"``).
    - A node's ending-title surface (only present on an ending node) is
      keyed by the node id plus `MANIFEST_ENDING_TITLE_SUFFIX` (e.g.
      ``"n1::ending_title"``).

    A node/surface with zero sentinels present contributes no key at all
    (an empty entry list would be redundant with simple key absence). Keys
    are emitted in sorted order, so `json.dumps` on the result (even without
    ``sort_keys=True``) is deterministic.

    Args:
        document: The raw story mapping to scan (never mutated).

    Returns:
        dict[str, object]: ``{"tokens": {<manifest key>: [{"slot_id": ...,
            "value": ..., "count": ...}, ...], ...}}``, JSON-serializable
            (plain dicts, lists, strings, and ints only).
    """
    surfaces: dict[str, list[dict[str, object]]] = {}
    nodes = _as_list(document.get("nodes"))
    if nodes is not None:
        for raw_node in nodes:
            node = _as_dict(raw_node)
            if node is None:
                continue
            node_id = node.get("id")
            if not isinstance(node_id, str):
                continue

            body = node.get("body")
            if isinstance(body, str):
                body_tally = _tally_sentinels(body)
                if body_tally:
                    key = _manifest_key(node_id, ending_title=False)
                    surfaces[key] = _manifest_entries(body_tally)

            ending = _as_dict(node.get("ending"))
            if ending is not None:
                title = ending.get("title")
                if isinstance(title, str):
                    title_tally = _tally_sentinels(title)
                    if title_tally:
                        key = _manifest_key(node_id, ending_title=True)
                        surfaces[key] = _manifest_entries(title_tally)

    return {"tokens": {key: surfaces[key] for key in sorted(surfaces)}}


def _reference_document_from_manifest(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Rebuild a minimal, `check_sentinel_integrity`-shaped reference from a manifest.

    Every manifest entry is rendered back into a wrapped sentinel token
    (`wrap`), concatenated per surface; `check_sentinel_integrity` only ever
    needs the DISTINCT token set per node (it scores set equality, not
    occurrence counts), so a single rendering of each distinct token per
    surface is sufficient regardless of the manifest's recorded count.

    Args:
        manifest: A `build_manifest`-shaped mapping; a malformed or
            unrecognized entry is skipped rather than raising, since a
            corrupted manifest should surface as a `verify_manifest`
            mismatch, not a crash.

    Returns:
        dict[str, object]: A ``{"nodes": [...]}`` mapping with one node per
            distinct node id referenced in `manifest`, each carrying a
            `body` string and, when the manifest declared an ending-title
            surface for that node id, an `ending.title` string.
    """
    tokens_obj = manifest.get("tokens")
    body_by_node: dict[str, str] = {}
    title_by_node: dict[str, str] = {}
    if isinstance(tokens_obj, dict):
        for key, entries in cast("dict[object, object]", tokens_obj).items():
            if not isinstance(key, str) or not isinstance(entries, list):
                continue
            is_ending = key.endswith(MANIFEST_ENDING_TITLE_SUFFIX)
            node_id = key[: -len(MANIFEST_ENDING_TITLE_SUFFIX)] if is_ending else key
            parts: list[str] = []
            for entry in cast("list[object]", entries):
                if not isinstance(entry, dict):
                    continue
                record = cast("dict[object, object]", entry)
                slot_id = record.get("slot_id")
                value = record.get("value")
                if isinstance(slot_id, str) and isinstance(value, str):
                    parts.append(wrap(slot_id, value))
            text = "".join(parts)
            if is_ending:
                title_by_node[node_id] = text
            else:
                body_by_node[node_id] = text

    node_ids = sorted(set(body_by_node) | set(title_by_node))
    nodes: list[dict[str, object]] = []
    for node_id in node_ids:
        node: dict[str, object] = {"id": node_id, "body": body_by_node.get(node_id, "")}
        if node_id in title_by_node:
            node["ending"] = {"title": title_by_node[node_id]}
        nodes.append(node)
    return {"nodes": nodes}


def _manifest_entry_token(entry: object) -> tuple[_Token, int] | None:
    """Validate one manifest entry and return its `(token, count)`, or None if malformed.

    Args:
        entry: One element of a manifest surface's entry list.

    Returns:
        tuple[_Token, int] | None: The `(slot_id, value)` token and its
            count, or None when `entry` does not match `build_manifest`'s
            entry schema exactly.
    """
    if not isinstance(entry, dict):
        return None
    record = cast("dict[object, object]", entry)
    slot_id = record.get("slot_id")
    value = record.get("value")
    count = record.get("count")
    # `isinstance(count, bool)` is not redundant: `bool` subclasses `int`, so
    # a JSON `true` would otherwise sail through as a count of 1.
    if (
        not isinstance(slot_id, str)
        or not isinstance(value, str)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
    ):
        return None
    return (slot_id, value), count


def _surface_tally(entries: list[object]) -> dict[_Token, int] | None:
    """Normalize one manifest surface's entry list into a token-to-count map.

    Args:
        entries: The surface's raw entry list.

    Returns:
        dict[_Token, int] | None: The token-to-count map, or None when any
            entry is malformed, a token is repeated (which `build_manifest`
            never emits, since it tallies before rendering), or the list is
            empty (`build_manifest` omits an empty surface's key entirely).
    """
    surface: dict[_Token, int] = {}
    for entry in entries:
        parsed = _manifest_entry_token(entry)
        if parsed is None:
            return None
        token, count = parsed
        if token in surface:
            return None
        surface[token] = count
    return surface or None


def _manifest_tally(
    manifest: Mapping[str, object],
) -> dict[str, dict[_Token, int]] | None:
    """Normalize a manifest into per-surface token multisets for exact comparison.

    Rejects (rather than skips) anything that does not match
    `build_manifest`'s schema exactly, so a corrupted manifest can never
    compare equal to a well-formed one by having its bad entries quietly
    dropped from both sides.

    Args:
        manifest: A `build_manifest`-shaped mapping.

    Returns:
        dict[str, dict[_Token, int]] | None: Manifest key to that surface's
            token-to-count map, or None when `manifest` is malformed.
    """
    tokens_obj = manifest.get("tokens")
    if not isinstance(tokens_obj, dict):
        return None
    tally: dict[str, dict[_Token, int]] = {}
    for key, entries in cast("dict[object, object]", tokens_obj).items():
        if not isinstance(key, str) or not isinstance(entries, list):
            return None
        surface = _surface_tally(cast("list[object]", entries))
        if surface is None:
            return None
        tally[key] = surface
    return tally


def verify_manifest(
    document: Mapping[str, object], manifest: Mapping[str, object]
) -> bool:
    """Verify that `document`'s actual sentinel content still matches `manifest`.

    Two independent checks, both of which must pass.

    1. **Exact manifest equality.** `build_manifest` is re-run against
       `document` and its result compared to `manifest` surface by surface,
       token by token, count included. This is the check that gives the
       manifest its at-rest meaning.
    2. **Whole-document surface sweep.** A minimal reference document is
       rebuilt from `manifest` (`_reference_document_from_manifest`) and
       passed to `check_sentinel_integrity`, the same validator the fill
       pipeline already trusts. This adds coverage the manifest itself does
       not record: a stray sentinel introduced later in a choice label or
       the story title, and any malformed near-miss anywhere.

    #CRITICAL: data integrity: check 1 is not redundant with check 2, and
    delegating alone was measurably insufficient. `check_sentinel_integrity`
    compares the DISTINCT token set per node and merges a node's body and
    ending-title surfaces into one set, so on its own it accepts three
    corruptions this function must reject: a `count` edited from 3 to 99, two
    of three at-rest occurrences stripped, and a sentinel relocated from
    `ending.title` into the body. All three leave the per-node distinct token
    set untouched and all three change what the reader sees.
    #VERIFY: tests/unit/test_storybook_reinsertion.py::test_verify_manifest_rejects_a_count_only_edit

    Args:
        document: The document to check (e.g. a published blob re-read from
            storage).
        manifest: The manifest to check it against (e.g. the same blob's
            stored manifest column). A manifest that does not match
            `build_manifest`'s schema is a verification failure, not a crash.

    Returns:
        bool: True only when `document`'s sentinel content matches
            `manifest` exactly, per-surface and per-count, with no malformed
            near-miss, choice-label, or title violation anywhere in
            `document`.
    """
    declared = _manifest_tally(manifest)
    if declared is None or declared != _manifest_tally(build_manifest(document)):
        return False
    reference = _reference_document_from_manifest(manifest)
    return check_sentinel_integrity(reference, document).ok


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _log_unreinserted(outcomes: list[TokenOutcome]) -> None:
    """Emit one structured warning when any expected token was not re-inserted.

    #CRITICAL: data integrity: a dropped personalization slot is a SILENT
    outcome of this transform by design (a `"not_found"` token simply
    contributes nothing to the document), and the caller is free to persist
    the result anyway. Without this line there is no record anywhere that a
    slot the skeleton declared never made it into the published prose, so a
    systematic fill regression would show up only as readers noticing their
    names had stopped appearing.
    #VERIFY: tests/unit/test_storybook_reinsertion.py::test_unreinserted_tokens_are_logged

    Args:
        outcomes: Every `(node, token)` outcome from one transform run.
    """
    unreinserted = [outcome for outcome in outcomes if outcome.status != "reinsertable"]
    if not unreinserted:
        return
    # Slot ids and node ids only. The VALUE is the child's own personalization
    # data (a real name, a sibling's name, a pet's name); it must never reach
    # a log line, which is why this reports counts and ids rather than the
    # text that failed to match.
    logger.warning(
        "reinsertion.tokens_not_reinserted",
        total_expected=len(outcomes),
        not_found=sum(1 for o in unreinserted if o.status == "not_found"),
        ambiguous=sum(1 for o in unreinserted if o.status == "ambiguous"),
        slot_ids=sorted({o.slot_id for o in unreinserted}),
        node_ids=sorted({o.node_id for o in unreinserted}),
    )


def reinsert_storybook(
    bound_skeleton: Mapping[str, object], filled_document: Mapping[str, object]
) -> ReinsertionOutcome:
    """Run the full strip-all-then-reinsert algorithm for one fill result.

    Args:
        bound_skeleton: The pre-fill bound skeleton the fill was given, used
            only to derive the expected per-node token set; never mutated.
        filled_document: The fill's output document, never mutated (every
            transform works on deep copies).

    Returns:
        ReinsertionOutcome: The finished document, its derived at-rest
            manifest, every `(node, token)` outcome, and the widening
            diagnostics (`sentence_start_hits`, `plural_occurrences`).
    """
    expected = _expected_tokens_by_node(bound_skeleton)
    # `_normalize_document` already deep-copies its input and returns an
    # object nobody else holds a reference to, so copying it again here
    # bought nothing but a second full traversal of the blob. Do not
    # reintroduce the copy to "protect" `filled_document`: that protection
    # lives one call up, inside `_normalize_document`, which is where the
    # never-mutate-the-caller's-document contract is actually enforced.
    reinserted = _normalize_document(filled_document)
    nodes_by_id = _index_nodes(reinserted)

    outcomes: list[TokenOutcome] = []
    sentence_start_hits = 0
    plural_occurrences = 0
    for node_id in sorted(expected):
        node = nodes_by_id.get(node_id)
        node_tokens = sorted(expected[node_id])
        owner_by_value = _value_owner(node_tokens)
        reinsertable_tokens: list[_Token] = []
        for slot_id, value in node_tokens:
            if node is None:
                count = 0
            else:
                count = _count_in_node_surfaces(node, value)
                plural_occurrences += _count_plural_occurrences(node, value)
            status = _classify_token(count, owns_value=owner_by_value[value] == slot_id)
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
            sentence_start_hits += _wrap_all_in_node(node, reinsertable_tokens)

    manifest = build_manifest(reinserted)
    _log_unreinserted(outcomes)

    return ReinsertionOutcome(
        document=reinserted,
        manifest=manifest,
        token_outcomes=tuple(outcomes),
        sentence_start_hits=sentence_start_hits,
        plural_occurrences=plural_occurrences,
    )
