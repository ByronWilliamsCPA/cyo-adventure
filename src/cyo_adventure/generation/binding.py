"""Contract discovery, LLM theme binding, and bound-skeleton render, WS-2.

This module is the runtime half of the parameterized-catalog framework: given
a skeleton on disk it decides whether the skeleton is parameterized (a
sidecar ``<slug>.contract.json`` exists) and, if so, drives the bind ->
validate -> render sequence that turns a free-text theme brief into a *bound
skeleton* ready for the unchanged :func:`~cyo_adventure.generation.orchestrator.fill_skeleton`
pipeline (``docs/planning/ws2-parameterized-catalog-design.md`` section 4).

The crux this module implements (design section 0): leaf prose is still
generated fresh per node, never filled by lookup. Substitution happens in
exactly one place -- :func:`render_bound_skeleton` -- and touches exactly
three surfaces of a skeleton: the ``beats='...'`` guidance inside
``<<FILL ...>>`` node bodies, ending ``title`` strings, and choice ``label``
strings. Node prose itself is never constructed here.
"""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.prompts import (
    build_bind_prompt,
    build_interpret_bind_prompt,
)
from cyo_adventure.story_requests.interpretation import RawElement
from cyo_adventure.storybook.theme_contract import (
    SLOT_TOKEN_RE,
    ThemeContract,
    slot_ids,
)
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.slots import SlotViolation, validate_slot_bindings

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.provider import GenerationProvider

__all__ = [
    "bind_theme_to_contract",
    "contract_path_for",
    "interpret_and_bind",
    "load_contract_for",
    "render_bound_skeleton",
]

# The interpret-and-bind element decomposition is advisory, not load-bearing:
# it is capped so a malformed or adversarial response can never balloon the
# persisted at-rest surface, and each phrase is length-bounded pre-sanitization
# (design section 5.2). These bounds mirror the echo floor's own word cap
# posture without importing it (the echo floor runs later, in derivation).
_MAX_INTERPRET_ELEMENTS = 12
_MAX_ELEMENT_PHRASE_CHARS = 120

# The production FILL directive parse, reused verbatim from the pilot
# (`out/pilot/_neutralize.py:337`) and matching `fill.md:32-36` and the
# words-target parse in `validator/policy.py:43-44`. DOTALL so a beats segment
# spanning an escaped/embedded quote or newline-free long sentence still
# matches as one group.
_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)

# The bind step emits one small JSON object ({SLOT_ID: value}); no story prose
# is ever produced by this call, so a small ceiling is correct and cheap.
_MAX_TOKENS_BIND = 4096


# ---------------------------------------------------------------------------
# Skeleton walking helpers (shared by contract loading and rendering)
# ---------------------------------------------------------------------------


def _iter_nodes(skeleton: Mapping[str, object]) -> Iterator[dict[str, object]]:
    """Yield every node dict in a raw skeleton mapping.

    Args:
        skeleton: The raw skeleton dict (or a bound copy of one).

    Yields:
        Each node as a ``dict[str, object]``. Non-dict entries in a malformed
        ``nodes`` list are silently skipped; schema validity is the gate's
        job, not this walker's.
    """
    nodes = skeleton.get("nodes")
    if isinstance(nodes, list):
        for raw_node in cast("list[object]", nodes):
            if isinstance(raw_node, dict):
                yield cast("dict[str, object]", raw_node)


def _slotted_surface_tokens(skeleton: Mapping[str, object]) -> frozenset[str]:
    """Return every ``{SLOT}`` token found in the three slotted surfaces.

    The three surfaces are exactly the ones the design fixes as the only
    legal home for a slot token: the ``beats='...'`` segment of a ``<<FILL
    ...>>`` node body, an ending's ``title``, and a choice's ``label``.

    Args:
        skeleton: The raw skeleton dict to scan.

    Returns:
        The set of slot ids referenced anywhere in those three surfaces.
    """
    tokens: set[str] = set()
    for node in _iter_nodes(skeleton):
        body = node.get("body")
        if isinstance(body, str):
            match = _FILL_RE.match(body)
            if match is not None:
                tokens.update(SLOT_TOKEN_RE.findall(match.group(3)))
        ending = node.get("ending")
        if isinstance(ending, dict):
            title = cast("dict[str, object]", ending).get("title")
            if isinstance(title, str):
                tokens.update(SLOT_TOKEN_RE.findall(title))
        choices = node.get("choices")
        if isinstance(choices, list):
            for raw_choice in cast("list[object]", choices):
                if isinstance(raw_choice, dict):
                    label = cast("dict[str, object]", raw_choice).get("label")
                    if isinstance(label, str):
                        tokens.update(SLOT_TOKEN_RE.findall(label))
    return frozenset(tokens)


def _fill_role_words_map(
    skeleton: Mapping[str, object],
) -> dict[str, tuple[str, str] | None]:
    """Map every node id to its FILL directive's ``(role, words)``, or ``None``.

    ``None`` means the node's body is not (or is no longer) a ``<<FILL ...>>``
    directive -- either it was never one (already-filled prose) or a render
    step degraded/removed it. Comparing this map before and after a render is
    the CR-1 safety-bearing invariant check (see :func:`render_bound_skeleton`).

    Args:
        skeleton: The raw skeleton dict to scan.

    Returns:
        A dict from node id to its parsed ``(role, words)`` pair, or ``None``.
    """
    result: dict[str, tuple[str, str] | None] = {}
    for node in _iter_nodes(skeleton):
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        body = node.get("body")
        match = _FILL_RE.match(body) if isinstance(body, str) else None
        result[node_id] = (
            (match.group(1), match.group(2)) if match is not None else None
        )
    return result


# ---------------------------------------------------------------------------
# Contract discovery (dispatch helper, design section 5.1)
# ---------------------------------------------------------------------------


def contract_path_for(skeleton_path: Path) -> Path:
    """Return the sidecar theme-contract path for a skeleton file.

    The sidecar lives next to its skeleton and shares its stem, so it
    inherits whatever containment guarantee the caller already established
    on ``skeleton_path`` (e.g.
    :func:`~cyo_adventure.generation.skeleton_match.resolve_skeleton_path`):
    only the filename suffix changes, never the directory.

    Args:
        skeleton_path: The skeleton's on-disk path.

    Returns:
        ``skeleton_path`` with its filename replaced by
        ``"<stem>.contract.json"``.
    """
    return skeleton_path.with_name(f"{skeleton_path.stem}.contract.json")


def load_contract_for(
    skeleton_path: Path, skeleton: dict[str, object]
) -> ThemeContract | None:
    """Load and cross-check a skeleton's theme contract, or ``None`` for legacy.

    Three outcomes:

    - No sidecar file exists: returns ``None``. The caller takes the WS-1
      free-text fill path unchanged (a legacy, unparameterized skeleton).
    - No sidecar file exists AND the skeleton already carries ``{SLOT}``
      tokens in its three slotted surfaces (a half-migrated skeleton): raises
      :class:`~cyo_adventure.core.exceptions.ValidationError`. A raw token
      reaching a child-facing fill is a content defect the post-generation
      gate cannot see (tokens are valid non-empty strings), so this fails
      closed rather than silently filling raw placeholders.
    - A sidecar exists: it is schema-validated, then cross-checked so the set
      of ``{SLOT}`` tokens found in the skeleton's three slotted surfaces
      equals the contract's declared slot id set exactly. Any drift (a token
      with no matching slot, or a declared slot with no matching token)
      raises :class:`~cyo_adventure.core.exceptions.ValidationError`: this is
      the guard against a skeleton edited without its contract, or vice versa.

    Args:
        skeleton_path: The skeleton's on-disk path (already containment-
            checked by the caller).
        skeleton: The decoded skeleton dict (already loaded and gate-passed
            by :func:`~cyo_adventure.generation.skeleton.load_skeleton`).

    Returns:
        The validated :class:`ThemeContract`, or ``None`` when the skeleton
        is an unmigrated legacy skeleton.

    Raises:
        ValidationError: On a half-migrated skeleton, a sidecar that fails
            schema validation, or a token/declared-slot-set mismatch.
    """
    # #ASSUME: external-resources: this is a filesystem read on a path derived
    # purely from skeleton_path's directory and stem (contract_path_for changes
    # only the filename), so it inherits containment from whatever check the
    # caller already ran on skeleton_path (e.g. resolve_skeleton_path).
    # #VERIFY: test_binding_render.py exercises the sidecar-absent,
    # half-migrated, drift, and sidecar-present branches.
    contract_path = contract_path_for(skeleton_path)

    if not contract_path.is_file():
        residual = _slotted_surface_tokens(skeleton)
        if residual:
            msg = (
                f"skeleton '{skeleton_path}' contains {{SLOT}} token(s) "
                f"{sorted(residual)} in its beats/title/label surfaces but has "
                f"no theme contract sidecar at '{contract_path}'; a "
                f"half-migrated skeleton must fail closed rather than reach a "
                f"child-facing fill with raw placeholders"
            )
            raise ValidationError(msg, field="skeleton_path", value=str(skeleton_path))
        return None

    raw_text = contract_path.read_text(encoding="utf-8")
    try:
        contract = ThemeContract.model_validate_json(raw_text)
    except PydanticValidationError as exc:
        msg = f"theme contract at '{contract_path}' failed schema validation: {exc}"
        raise ValidationError(
            msg, field="contract_path", value=str(contract_path)
        ) from exc

    declared = slot_ids(contract)
    actual = _slotted_surface_tokens(skeleton)
    if declared != actual:
        declared_but_absent = sorted(declared - actual)
        present_but_undeclared = sorted(actual - declared)
        msg = (
            f"theme contract '{contract_path}' slot id set does not match the "
            f"skeleton's {{SLOT}} tokens: declared_but_absent="
            f"{declared_but_absent} present_but_undeclared="
            f"{present_but_undeclared}"
        )
        raise ValidationError(msg, field="contract_path", value=str(contract_path))

    return contract


# ---------------------------------------------------------------------------
# Render (design section 4.3)
# ---------------------------------------------------------------------------


def _substitute_tokens(text: str, bindings: Mapping[str, str]) -> str:
    """Replace every ``{SLOT}`` token in ``text`` with its bound value, literally.

    Args:
        text: The raw slotted text: a beats segment, an ending title, or a
            choice label.
        bindings: The proposed/validated slot-value map.

    Returns:
        ``text`` with every ``{SLOT}`` token that has a matching binding
        replaced by its literal value via plain substring replacement (never
        ``re.sub`` with the value as a replacement pattern), so a value
        containing regex metacharacters (backslashes, group references, and
        the like) is inserted verbatim rather than interpreted. A token with
        no matching binding is left untouched; the render's residual-token
        post-condition then rejects the result.
    """
    result = text
    tokens = cast("list[str]", SLOT_TOKEN_RE.findall(text))
    for token in set(tokens):
        value = bindings.get(token)
        if value is not None:
            result = result.replace("{" + token + "}", value)
    return result


def _substitute_slotted_surfaces(
    bound: dict[str, object], bindings: Mapping[str, str]
) -> None:
    """Substitute bound values into ``bound``'s three slotted surfaces, in place.

    Args:
        bound: A skeleton dict (mutated in place; caller must pass a copy,
            never the original).
        bindings: The proposed/validated slot-value map.
    """
    for node in _iter_nodes(bound):
        body = node.get("body")
        if isinstance(body, str):
            match = _FILL_RE.match(body)
            if match is not None:
                role, words, beats = match.group(1), match.group(2), match.group(3)
                new_beats = _substitute_tokens(beats, bindings)
                node["body"] = f"<<FILL role={role} words={words} beats='{new_beats}'>>"
        ending = node.get("ending")
        if isinstance(ending, dict):
            ending_map = cast("dict[str, object]", ending)
            title = ending_map.get("title")
            if isinstance(title, str):
                ending_map["title"] = _substitute_tokens(title, bindings)
        choices = node.get("choices")
        if isinstance(choices, list):
            for raw_choice in cast("list[object]", choices):
                if isinstance(raw_choice, dict):
                    choice = cast("dict[str, object]", raw_choice)
                    label = choice.get("label")
                    if isinstance(label, str):
                        choice["label"] = _substitute_tokens(label, bindings)


def _assert_no_residual_tokens(bound: Mapping[str, object]) -> None:
    """Raise if any ``{SLOT}`` token remains anywhere in ``bound``.

    Args:
        bound: The rendered skeleton to scan (the whole document, not just
            the three slotted surfaces: a residual token anywhere is a
            failure).

    Raises:
        ValidationError: If any ``{SLOT}``-shaped token remains.
    """
    serialized = json.dumps(bound)
    residual = sorted(set(SLOT_TOKEN_RE.findall(serialized)))
    if residual:
        msg = (
            f"render_bound_skeleton left unresolved slot token(s) {residual}; "
            f"every declared slot must be bound before rendering"
        )
        raise ValidationError(msg, field="bound_skeleton")


def _assert_fingerprint_unchanged(
    skeleton: Mapping[str, object], bound: Mapping[str, object]
) -> None:
    """Raise if the render changed anything but the three leaf surfaces.

    ``structure_fingerprint`` strips exactly the story title, node body,
    ending title, and choice label (``diversity/structure.py::_strip_leaf_content``),
    so equality here proves node ids, choices, targets, conditions, effects,
    ``is_ending``, and ending ``kind``/``valence`` were left untouched.

    Args:
        skeleton: The original, unbound skeleton.
        bound: The rendered skeleton.

    Raises:
        ValidationError: If the fingerprints differ.
    """
    if structure_fingerprint(skeleton) != structure_fingerprint(bound):
        msg = (
            "render_bound_skeleton changed the skeleton's structural "
            "fingerprint; substitution must be confined to beats guidance, "
            "ending titles, and choice labels"
        )
        raise ValidationError(msg, field="bound_skeleton")


def _assert_gate_not_blocked(bound: Mapping[str, object]) -> None:
    """Raise if the rendered skeleton fails the blocking validation gate.

    Args:
        bound: The rendered skeleton.

    Raises:
        ValidationError: If :func:`~cyo_adventure.validator.gate.run_gate`
            reports ``blocked=True``.
    """
    result = run_gate(bound)
    if result.blocked:
        messages = (
            "; ".join(finding.message for finding in result.report.errors)
            or "no error details available"
        )
        msg = (
            f"render_bound_skeleton produced a bound skeleton that fails the "
            f"validation gate: {messages}"
        )
        raise ValidationError(msg, field="bound_skeleton")


def _assert_fill_invariant_preserved(
    before: Mapping[str, tuple[str, str] | None], bound: Mapping[str, object]
) -> None:
    """Raise unless every FILL directive's ``role``/``words`` survived the render.

    CR-1 (design section 13.2, blocking): ``structure_fingerprint`` strips the
    entire node ``body``, so fingerprint equality alone cannot detect a
    ``role=``/``words=`` mangled during substitution, or a FILL directive
    silently degraded to raw prose (or one newly introduced). This checks the
    render's own invariant directly rather than assuming the substitution
    code is correct.

    Args:
        before: The ``{node_id: (role, words) | None}`` map computed from the
            skeleton BEFORE the render.
        bound: The rendered skeleton.

    Raises:
        ValidationError: If the ``{node_id: (role, words) | None}`` map
            computed from ``bound`` differs from ``before`` in any way: a
            changed role/words pair, a FILL directive that no longer parses
            as one, or a new one that was not there before.
    """
    after = _fill_role_words_map(bound)
    if before != after:
        msg = (
            "render_bound_skeleton mutated a FILL directive's role/words, or "
            "changed whether a node body still parses as a FILL directive "
            "(CR-1 invariant); substitution must be confined to the beats "
            "text inside an unchanged 'role=...words=...' directive"
        )
        raise ValidationError(msg, field="bound_skeleton")


def render_bound_skeleton(
    skeleton: dict[str, object], bindings: Mapping[str, str]
) -> dict[str, object]:
    """Substitute validated slot values into the three slotted surfaces only.

    Deep-copies ``skeleton`` and rewrites, on the copy: (a) the ``beats='...'``
    segment of each ``<<FILL ...>>`` node body (``role=`` and ``words=`` are
    reconstructed from the parsed directive, never copied byte-for-byte from
    the input text, so an apostrophe or brace inside the original beats text
    cannot corrupt the directive shape); (b) every ``ending.title``; (c) every
    ``choices[].label``. Node prose is never constructed here: a node body
    that is not a ``<<FILL ...>>`` directive is left completely untouched.

    Four post-conditions are checked, in order, each raising
    :class:`~cyo_adventure.core.exceptions.ValidationError` (fail closed) on
    failure:

    1. Zero ``{SLOT}``-shaped tokens remain anywhere in the rendered document.
    2. ``structure_fingerprint(bound) == structure_fingerprint(skeleton)``.
    3. ``run_gate(bound)`` is not blocked.
    4. **CR-1** (design section 13.2): the ``{node_id: (role, words)}`` map
       parsed from every FILL directive is unchanged, and every node whose
       pre-render body was a FILL directive still parses as one post-render.

    Args:
        skeleton: The raw skeleton dict, FILL directives intact.
        bindings: The proposed slot-value map. Callers should pass a map that
            has already passed
            :func:`~cyo_adventure.validator.slots.validate_slot_bindings`;
            this function does not re-run that check, but its own
            post-conditions independently fail closed on a bad map (e.g. a
            binding missing a declared slot leaves a residual token and is
            rejected by post-condition 1).

    Returns:
        The rendered ("bound") skeleton: a new dict, still full of
        ``<<FILL ...>>`` directives, ready for
        :func:`~cyo_adventure.generation.orchestrator.fill_skeleton`.

    Raises:
        ValidationError: If any post-condition fails.
    """
    # #CRITICAL: data-integrity: substitution is limited to the three leaf
    # surfaces (beats guidance, ending titles, choice labels) AND every FILL
    # directive's role/words is byte-preserved; both are independently
    # verified below rather than assumed from the substitution code alone.
    # #VERIFY: test_binding_render.py.
    before_fill_map = _fill_role_words_map(skeleton)
    bound = copy.deepcopy(skeleton)
    _substitute_slotted_surfaces(bound, bindings)

    _assert_no_residual_tokens(bound)
    _assert_fingerprint_unchanged(skeleton, bound)
    _assert_gate_not_blocked(bound)
    _assert_fill_invariant_preserved(before_fill_map, bound)

    return bound


# ---------------------------------------------------------------------------
# Bind (design section 4.1)
# ---------------------------------------------------------------------------


def _parse_bind_response(raw: str) -> dict[str, str] | None:
    """Parse a bind-step provider response as a flat ``{slot_id: value}`` map.

    Mirrors ``_run_one_stage``'s parse posture in
    :mod:`cyo_adventure.generation.orchestrator`: any non-JSON or non-dict
    output counts as a failed attempt, returned as ``None`` rather than
    raised. A dict whose values are not all strings is likewise treated as a
    failed attempt, since :func:`~cyo_adventure.validator.slots.validate_slot_bindings`
    and :func:`render_bound_skeleton` both assume string values throughout.

    Args:
        raw: The raw provider completion text.

    Returns:
        The parsed ``dict[str, str]``, or ``None`` on any parse/shape failure.
    """
    try:
        parsed: object = json.loads(raw)  # pyright: ignore[reportAny]
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    parsed_map = cast("dict[str, object]", parsed)
    if not all(isinstance(value, str) for value in parsed_map.values()):
        return None
    return cast("dict[str, str]", parsed_map)


async def bind_theme_to_contract(  # noqa: PLR0913
    contract: ThemeContract,
    theme_brief: Mapping[str, object],
    provider: GenerationProvider,
    pii: PiiContext,
    *,
    max_attempts: int = 2,
) -> dict[str, str]:
    """Bind a free-text theme brief to the contract's slots, validated.

    Wraps ``provider`` in :class:`~cyo_adventure.generation.guarded.PiiGuardedProvider`
    exactly as :func:`~cyo_adventure.generation.orchestrator.fill_skeleton` does,
    so no real-child name can egress in the bind prompt.

    Each attempt: build the bind prompt (the contract's slot table plus the
    brief fenced as untrusted input; on a retry, the exact violation list from
    the previous attempt is appended so the binder can correct without
    re-deriving), call the provider for a JSON-only response, parse it, and
    check it with :func:`~cyo_adventure.validator.slots.validate_slot_bindings`.
    Non-JSON or non-``dict[str, str]`` output counts as a failed attempt (it
    mirrors ``_run_one_stage``'s parse posture) rather than raising
    immediately, so a single malformed response still gets its retry.

    Args:
        contract: The theme contract to bind against.
        theme_brief: The free-text (UNTRUSTED) child/guardian story request.
        provider: The generation provider to call for completions.
        pii: The PII context carrying real-child names that must never
            appear in the bind prompt.
        max_attempts: Maximum number of bind attempts (LLM calls). Defaults to
            2 (one bounded retry with violation feedback).

    Returns:
        A slot-value map that has passed
        :func:`~cyo_adventure.validator.slots.validate_slot_bindings`.

    Raises:
        ValidationError: If no attempt produces a conforming binding within
            ``max_attempts`` (fail closed: the caller must not proceed to
            :func:`render_bound_skeleton` or the fill step), or if the
            assembled prompt would leak forbidden real-child PII (raised by
            the PII guard before any provider call).
    """
    # #CRITICAL: security: theme_brief is untrusted free text (OWASP LLM01);
    # the UNTRUSTED_USER_INPUT fence in bind.md plus the JSON-only parse below
    # are the containment. The bind OUTPUT stays untrusted-derived until it
    # passes validate_slot_bindings; only then is it trusted enough to render.
    # #ASSUME: external-resources: bounded provider calls (at most
    # max_attempts), each screened by PiiGuardedProvider before any network
    # call.
    # #VERIFY: test_bind_step.py.
    guarded_provider = PiiGuardedProvider(provider, forbidden=pii)

    violations: list[SlotViolation] = []
    parse_failed = False

    for _attempt in range(max_attempts):
        stage_prompt = build_bind_prompt(
            contract, theme_brief, violations=violations or None
        )
        raw = await guarded_provider.complete(
            system=stage_prompt.system,
            prompt=stage_prompt.user,
            max_tokens=_MAX_TOKENS_BIND,
        )

        parsed = _parse_bind_response(raw)
        if parsed is None:
            parse_failed = True
            violations = []
            continue

        parse_failed = False
        violations = validate_slot_bindings(contract, parsed)
        if not violations:
            return parsed

    if parse_failed and not violations:
        msg = (
            f"unable to bind theme to contract '{contract.skeleton_slug}' "
            f"after {max_attempts} attempt(s): provider output was not "
            f"parseable as a flat JSON object of slot id to string value"
        )
        raise ValidationError(msg, field="theme_brief")

    detail = [
        {
            "slot_id": violation.slot_id,
            "rule": violation.rule,
            "message": violation.message,
        }
        for violation in violations
    ]
    msg = (
        f"unable to bind theme to contract '{contract.skeleton_slug}' after "
        f"{max_attempts} attempt(s): the binding still violates its contract"
    )
    raise ValidationError(msg, field="theme_brief", details={"violations": detail})


# ---------------------------------------------------------------------------
# Interpret-and-bind (WS-7 D4, design section 5.2)
# ---------------------------------------------------------------------------


def _sanitize_elements(
    raw_elements: object, contract: ThemeContract
) -> list[RawElement]:
    """Sanitize the ``elements`` half of an interpret-and-bind response.

    Advisory-only, so this NEVER fails a parse: a malformed or missing value
    degrades to ``[]`` rather than rejecting the attempt (design section 5.2,
    the deliberate asymmetry vs the load-bearing ``bindings`` half). The
    sanitization is structural/bounded only; the echo-safety floor (the PII and
    denylist checks in :func:`cyo_adventure.story_requests.interpretation.sanitize_element`)
    is applied LATER, in D5's ``derive_dispositions``, NOT here. This helper
    therefore passes RAW phrases through, capping the list, dropping malformed
    entries, and mapping unknown slot ids to ``None``.

    Rules (design section 5.2):

    - Not a list: degrade to ``[]``.
    - Cap at :data:`_MAX_INTERPRET_ELEMENTS` entries (drop the extras).
    - Drop any entry that is not an object, whose ``phrase`` is not a non-empty
      ``str``, or whose ``phrase`` exceeds :data:`_MAX_ELEMENT_PHRASE_CHARS`
      characters pre-sanitization.
    - Map any ``slot_id`` not in ``slot_ids(contract)`` (including a non-string)
      to ``None``.

    Args:
        raw_elements: The ``elements`` value straight from the parsed JSON
            (untrusted, any shape).
        contract: The theme contract, for the declared slot id set.

    Returns:
        The sanitized, capped list of :class:`RawElement`; ``[]`` when the value
        is malformed or missing.
    """
    if not isinstance(raw_elements, list):
        return []
    declared = slot_ids(contract)
    sanitized: list[RawElement] = []
    for raw_entry in cast("list[object]", raw_elements):
        if len(sanitized) >= _MAX_INTERPRET_ELEMENTS:
            break
        if not isinstance(raw_entry, dict):
            continue
        entry = cast("dict[str, object]", raw_entry)
        phrase = entry.get("phrase")
        if not isinstance(phrase, str) or not phrase:
            continue
        if len(phrase) > _MAX_ELEMENT_PHRASE_CHARS:
            continue
        raw_slot = entry.get("slot_id")
        slot_id = (
            raw_slot if isinstance(raw_slot, str) and raw_slot in declared else None
        )
        sanitized.append(RawElement(phrase=phrase, slot_id=slot_id))
    return sanitized


def _parse_interpret_bind_response(
    raw: str, contract: ThemeContract
) -> tuple[dict[str, str], list[RawElement]] | None:
    """Parse an interpret-and-bind response into ``(bindings, elements)``.

    Extends :func:`_parse_bind_response` with the asymmetric posture of design
    section 5.2. The ``bindings`` half is LOAD-BEARING and validated exactly as
    today: the whole response must be a JSON object carrying a ``bindings`` key
    whose value is a flat ``dict[str, str]``; any deviation (non-JSON, non-dict,
    missing ``bindings``, non-dict ``bindings``, or a non-string value inside
    it) fails the WHOLE parse and returns ``None`` (a failed attempt, exactly as
    ``_parse_bind_response`` does). The ``elements`` half is ADVISORY: a
    malformed or missing value degrades to ``[]`` via :func:`_sanitize_elements`
    and can NEVER fail the parse.

    Args:
        raw: The raw provider completion text.
        contract: The theme contract, for element slot-id sanitization.

    Returns:
        ``(bindings, sanitized_elements)`` on a parseable ``bindings`` half, or
        ``None`` when the ``bindings`` half fails (a failed attempt).
    """
    try:
        parsed: object = json.loads(raw)  # pyright: ignore[reportAny]
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    parsed_map = cast("dict[str, object]", parsed)

    # `bindings` is load-bearing: same flat dict[str, str] check as
    # _parse_bind_response; any failure here is a failed attempt (None).
    raw_bindings = parsed_map.get("bindings")
    if not isinstance(raw_bindings, dict):
        return None
    bindings_map = cast("dict[str, object]", raw_bindings)
    if not all(isinstance(value, str) for value in bindings_map.values()):
        return None
    bindings = cast("dict[str, str]", bindings_map)

    # `elements` is advisory: never fails the parse; malformed -> [].
    elements = _sanitize_elements(parsed_map.get("elements"), contract)
    return bindings, elements


async def interpret_and_bind(  # noqa: PLR0913
    contract: ThemeContract,
    theme_brief: Mapping[str, object],
    provider: GenerationProvider,
    pii: PiiContext,
    *,
    max_attempts: int = 2,
) -> tuple[dict[str, str], list[RawElement]]:
    """Bind exactly as :func:`bind_theme_to_contract`, plus element decomposition.

    Mirrors :func:`bind_theme_to_contract` byte-for-byte in its safety posture
    (WS-7 D4, design section 5.2): the same ``PiiGuardedProvider`` wrap, the same
    ``_MAX_TOKENS_BIND`` ceiling, the same one bounded retry re-sending the exact
    violation list, and the same fail-closed ``ValidationError`` messages/details
    on exhaustion or unparseable output. The ONLY difference is the output
    contract: the provider returns ``{"bindings": {...}, "elements": [...]}`` and
    this function additionally returns the binder's sanitized element
    decomposition alongside the validated bindings.

    The ``bindings`` half is validated by the UNCHANGED
    :func:`~cyo_adventure.validator.slots.validate_slot_bindings`, so it carries
    the identical fail-closed contract; the ``elements`` half is advisory and
    can NEITHER cause NOR rescue a bind failure (CR-2): it is derived from the
    parsed response, never fed into the bind decision, the render, or the
    violation loop. Only the PASSING attempt's elements are returned; a failed
    attempt's elements are discarded, so the interpretation always describes the
    binding that actually rendered.

    Args:
        contract: The theme contract to bind against.
        theme_brief: The free-text (UNTRUSTED) child/guardian story request.
        provider: The generation provider to call for completions.
        pii: The PII context carrying real-child names that must never appear in
            the interpret-and-bind prompt.
        max_attempts: Maximum number of bind attempts (LLM calls). Defaults to 2
            (one bounded retry with violation feedback).

    Returns:
        ``(validated_bindings, sanitized_elements)`` from the passing attempt:
        a slot-value map that has passed
        :func:`~cyo_adventure.validator.slots.validate_slot_bindings`, and the
        advisory (structurally sanitized, NOT echo-floored) element list.

    Raises:
        ValidationError: If no attempt produces a conforming binding within
            ``max_attempts`` (fail closed, identical to
            :func:`bind_theme_to_contract`), or if the assembled prompt would
            leak forbidden real-child PII (raised by the PII guard before any
            provider call).
    """
    # #CRITICAL: security: theme_brief is untrusted free text (OWASP LLM01); the
    # UNTRUSTED_USER_INPUT fence in interpret_bind.md (byte-identical to bind.md)
    # plus the JSON parse below are the containment. Both response halves stay
    # untrusted-derived: `bindings` is trusted only after validate_slot_bindings,
    # and `elements` is trusted-enough-to-echo only after D5's echo floor; this
    # function runs no provider call outside PiiGuardedProvider (CR-4).
    # #CRITICAL: data-integrity: the `elements` half is advisory and CANNOT
    # affect bind acceptance (CR-2): it is only read AFTER validate_slot_bindings
    # decides, never fed into that check, the retry violations, or the return
    # gate; a failed attempt's elements are discarded, so a malformed/adversarial
    # decomposition can never rescue nor break a binding.
    # #ASSUME: external-resources: bounded provider calls (at most max_attempts),
    # each screened by PiiGuardedProvider before any network call.
    # #VERIFY: test_interpret_bind.py.
    guarded_provider = PiiGuardedProvider(provider, forbidden=pii)

    violations: list[SlotViolation] = []
    parse_failed = False

    for _attempt in range(max_attempts):
        stage_prompt = build_interpret_bind_prompt(
            contract, theme_brief, violations=violations or None
        )
        raw = await guarded_provider.complete(
            system=stage_prompt.system,
            prompt=stage_prompt.user,
            max_tokens=_MAX_TOKENS_BIND,
        )

        parsed = _parse_interpret_bind_response(raw, contract)
        if parsed is None:
            parse_failed = True
            violations = []
            continue

        bindings, elements = parsed
        parse_failed = False
        violations = validate_slot_bindings(contract, bindings)
        if not violations:
            return bindings, elements

    if parse_failed and not violations:
        msg = (
            f"unable to bind theme to contract '{contract.skeleton_slug}' "
            f"after {max_attempts} attempt(s): provider output was not "
            f"parseable as a flat JSON object of slot id to string value"
        )
        raise ValidationError(msg, field="theme_brief")

    detail = [
        {
            "slot_id": violation.slot_id,
            "rule": violation.rule,
            "message": violation.message,
        }
        for violation in violations
    ]
    msg = (
        f"unable to bind theme to contract '{contract.skeleton_slug}' after "
        f"{max_attempts} attempt(s): the binding still violates its contract"
    )
    raise ValidationError(msg, field="theme_brief", details={"violations": detail})
