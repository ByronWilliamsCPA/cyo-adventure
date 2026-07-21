"""WS-8 re-guidance drafting and the deterministic reguide floor (design 5.3-5.4).

Behind OQ-1's ratified HYBRID decision: an agent *drafts* each re-guidance
resolution, a deterministic floor *screens* it, and a human *approves* each item
in the promotion PR (D4). This module owns the drafting orchestration
(:func:`draft_resolutions`) and the floor (:func:`screen_draft`); it never marks
anything resolved by itself, it only refuses drafts. A refused draft leaves its
item unresolved, which leaves the candidate held, so no drafting code path can
promote an item the floor did not pass.

Safety posture (design 5.3 ``#CRITICAL``; plan safety invariant 4, OWASP LLM01):

- The drafting provider call consumes **catalog content only**: the parent's
  story-opening tone context, the emitted item's ``current_text`` (its
  pre-mutation surface), its ``reason``, the mutant contract's slot meanings, and
  the mutant's cell enums. No brief, theme, premise, family, or child artifact is
  an input, transitively. No function here accepts such a parameter, and this
  module imports nothing from ``story_requests``.
- The drafted output is untrusted-derived: it is floor-screened before it becomes
  a :class:`~cyo_adventure.mutation.reguide.ResolvedReguide`, it faces the full
  UNCHANGED acceptance re-run (via ``run_chain_acceptance`` with
  ``resolved_reguide_ids``, wired by the caller), and it is attributed
  ``author="agent:<model-id>"`` so the promotion PR reviewer sees, and must
  approve, every agent-drafted seam.

The floor (:func:`screen_draft`) is pure, total, and I/O-free. The drafting
orchestration performs exactly one LLM touchpoint per item through the injected
:class:`~cyo_adventure.generation.provider.GenerationProvider`, so unit tests pass
a deterministic fake and no real network is touched. Ships with a ``--no-draft``
manual path (the CLI simply omits drafting and uses :data:`NO_DRAFT_RESOLUTIONS`),
so the hand-authoring flow survives untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.mutation.ops import ReguideTarget
from cyo_adventure.mutation.reguide import ReguideResolutions, ResolvedReguide
from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE, slot_ids
from cyo_adventure.validator.slots import (
    band_mandatory_bundles,
    denylisted_bundles,
    structural_value_violations,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.mutation.ops import ReguideItem
    from cyo_adventure.storybook.models import AgeBand
    from cyo_adventure.storybook.theme_contract import ThemeContract
    from cyo_adventure.validator.slots import SlotViolation

# The FILL directive parse. Identical to ``generation.binding._FILL_RE`` and
# ``scripts/parameterize_skeleton.py`` (which reuses it verbatim); no public
# parser is exported by either module, so this single-source pattern is
# re-declared here with the same attribution the pilot used, rather than reaching
# into a private module member.
_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)

# The FILL directive attribute assignment tokens. A NODE beats resolution is
# prose guidance for the *inside* of ``beats='...'``; it must never carry these,
# which is how a draft would try to restructure the directive (rule 1 drift).
_FILL_ATTR_TOKENS: tuple[str, ...] = ("role=", "words=", "beats=")

# Length caps (design 5.3 rule 3). A node's beats guidance is longer-form than a
# single-line label or title.
_MAX_BEATS_CHARS = 600
_MAX_LABEL_CHARS = 120

# The banned en dash (U+2013). The em dash (U+2014) is already blocked by the
# reused ``structural_value_violations`` charset check; the en dash is not, so it
# is added here (design 5.3 rule 3: "no U+2014 and no U+2013").
_EN_DASH = "\u2013"

# Floor rule ids, stable so a caller / test can attribute a failure to a rule.
_RULE_SURFACE_PARITY = "surface_parity"
_RULE_SLOT_DISCIPLINE = "slot_discipline"
_RULE_STRUCTURAL = "structural"
_RULE_BAND_VOCAB = "band_vocab"

# Template plumbing (mirrors ``generation.prompts``: load a bundled template and
# substitute with explicit ``.replace()`` so literal braces in catalog content
# never trigger ``str.format`` interpretation).
_TEMPLATES = files("cyo_adventure.generation.templates")
_USER_MARKER = "<!-- @user -->"
_TEMPLATE_NAME = "reguide_draft.md"
_DRAFT_MAX_TOKENS = 512

# The empty resolution set for the ``--no-draft`` manual path (design 5.2 (b) /
# section 12 "ships with a --no-draft mode"). A module constant so no call
# appears in a parameter default.
NO_DRAFT_RESOLUTIONS: ReguideResolutions = ReguideResolutions(resolutions=[])


@dataclass(frozen=True, slots=True)
class FloorViolation:
    """One deterministic reason a drafted resolution was refused.

    Attributes:
        rule: The floor rule that failed (one of the ``_RULE_*`` ids): surface
            parity, slot-token discipline, structural injection block, or band
            vocabulary floor.
        message: A human-readable explanation. Safe to surface to a reviewer: it
            names rules, ids, counts, and bundles only, never re-emits the
            candidate story text.
    """

    rule: str
    message: str


@dataclass(frozen=True, slots=True)
class FloorResult:
    """The outcome of screening one drafted resolution through the floor.

    Attributes:
        passed: True only when every floor rule holds; then, and only then, the
            caller may persist the draft as a resolution.
        violations: Every rule the draft failed, in rule order; empty when
            ``passed``.
        human_check_required: True for a CHOICE / ENDING target, whose deeper
            action-semantic obligation is not mechanically verifiable and is
            flagged for the human PR reviewer (design 5.3 rule 1, 5.4).
    """

    passed: bool
    violations: tuple[FloorViolation, ...]
    human_check_required: bool


def _is_overridden_structural(violation: SlotViolation) -> bool:
    """Return whether a reused structural finding is handled elsewhere here.

    ``structural_value_violations`` is built for slot *values*, which never carry
    ``{SLOT}`` tokens and cap at 120 characters. A drafted resolution legitimately
    may reuse declared ``{SLOT}`` tokens (screened by rule 2) and a NODE beats
    draft may run to 600 characters (rule 3's own cap), so those two findings are
    dropped from the reused block and re-imposed with the correct semantics.

    Failing open here is safe: if the upstream message text ever changes so a
    finding stops being dropped, the floor only over-refuses a draft (leaving the
    item unresolved), never admits an unsafe one.

    Args:
        violation: One finding from :func:`structural_value_violations`.

    Returns:
        bool: True when this finding is superseded by rule 2 or rule 3's own cap.
    """
    if violation.rule != "charset":
        return False
    return (
        "'{' or '}'" in violation.message or "120-character limit" in violation.message
    )


def _surface_parity_violations(
    item: ReguideItem, drafted_text: str, parent_node_fill: str
) -> list[FloorViolation]:
    """Rule 1: surface parity (design 5.3 rule 1).

    NODE target: substituting the drafted beats into the pre-mutation FILL body
    must still parse under the FILL grammar with ``role=`` / ``words=``
    byte-identical, and the beats must round-trip exactly. A NODE beats draft must
    also carry no FILL attribute assignment token, since that is how a draft would
    try to alter ``role=`` / ``words=``. When the pre-mutation body is not a FILL
    directive there is no envelope to preserve, so the obligation is vacuous.

    CHOICE / ENDING target: the label / title must be a single line; the deeper
    action-semantic obligation is not mechanically verifiable and is left to the
    human PR review (surfaced via :attr:`FloorResult.human_check_required`).

    Args:
        item: The emitted re-guidance item being resolved.
        drafted_text: The agent's drafted resolution text.
        parent_node_fill: The pre-mutation node body (a FILL directive for a
            skeleton node); used only for a NODE target.

    Returns:
        list[FloorViolation]: The rule-1 violations (empty when parity holds).
    """
    if item.target is not ReguideTarget.NODE:
        # CHOICE / ENDING: single line only (the action-semantic obligation is a
        # human check, flagged separately on the FloorResult).
        if "\n" in drafted_text or "\r" in drafted_text:
            return [
                FloorViolation(
                    _RULE_SURFACE_PARITY,
                    "a choice label / ending title resolution must be a single line",
                )
            ]
        return []

    match = _FILL_RE.match(parent_node_fill)
    if match is None:
        # No pre-mutation FILL envelope (a prosed / contract-less node body, or an
        # operator that supplied no current_text): nothing to preserve.
        return []
    role, words = match.group(1), match.group(2)

    for token in _FILL_ATTR_TOKENS:
        if token in drafted_text:
            return [
                FloorViolation(
                    _RULE_SURFACE_PARITY,
                    (
                        f"node beats must not contain the FILL attribute token "
                        f"'{token}' (would alter role=/words=)"
                    ),
                )
            ]

    reconstructed = f"<<FILL role={role} words={words} beats='{drafted_text}'>>"
    reparsed = _FILL_RE.match(reconstructed)
    if (
        reparsed is None
        or reparsed.group(1) != role
        or reparsed.group(2) != words
        or reparsed.group(3) != drafted_text
    ):
        return [
            FloorViolation(
                _RULE_SURFACE_PARITY,
                (
                    "substituting the drafted beats would not preserve the FILL "
                    "directive's role=/words="
                ),
            )
        ]
    return []


def _slot_token_violations(
    drafted_text: str, contract: ThemeContract | None
) -> list[FloorViolation]:
    """Rule 2: slot-token discipline (design 5.3 rule 2).

    With a contract, every ``{SLOT}`` token in the draft must be a subset of the
    mutant contract's declared slot ids (no invented slots), and no stray or
    malformed brace may appear. Without a contract, no ``{`` / ``}`` character is
    permitted at all.

    Args:
        drafted_text: The agent's drafted resolution text.
        contract: The mutant's theme contract, or None for a contract-less mutant.

    Returns:
        list[FloorViolation]: The rule-2 violations (empty when discipline holds).
    """
    if contract is None:
        if "{" in drafted_text or "}" in drafted_text:
            return [
                FloorViolation(
                    _RULE_SLOT_DISCIPLINE,
                    (
                        "a contract-less mutant permits no slot tokens: remove all "
                        "'{' and '}' characters"
                    ),
                )
            ]
        return []

    violations: list[FloorViolation] = []
    declared = slot_ids(contract)
    used = frozenset(SLOT_TOKEN_RE.findall(drafted_text))
    invented = sorted(used - declared)
    if invented:
        violations.append(
            FloorViolation(
                _RULE_SLOT_DISCIPLINE,
                f"drafted text uses undeclared slot token(s): {invented}",
            )
        )
    # Any brace character not part of a well-formed, declared token is a stray or
    # malformed group (e.g. '{}', '{lower}', an unmatched brace).
    residue = SLOT_TOKEN_RE.sub("", drafted_text)
    if "{" in residue or "}" in residue:
        violations.append(
            FloorViolation(
                _RULE_SLOT_DISCIPLINE,
                "drafted text contains a stray or malformed brace group",
            )
        )
    return violations


def _structural_violations(
    drafted_text: str, target: ReguideTarget
) -> list[FloorViolation]:
    """Rule 3: structural injection block (design 5.3 rule 3).

    Reuses ``validator.slots.structural_value_violations`` for the shared block
    (no ``<<`` / ``>>``, no fence markers, no control characters, printable
    charset, no em dash, non-empty), dropping its slot-token and 120-character
    findings (owned by rule 2 and this rule's own target-specific cap), then adds
    the en dash ban and the target-specific length cap.

    Args:
        drafted_text: The agent's drafted resolution text.
        target: The surface kind, selecting the length cap (NODE beats vs a
            single-line label / title).

    Returns:
        list[FloorViolation]: The rule-3 violations (empty when the draft is
            structurally clean).
    """
    violations: list[FloorViolation] = [
        FloorViolation(_RULE_STRUCTURAL, finding.message)
        for finding in structural_value_violations(drafted_text)
        if not _is_overridden_structural(finding)
    ]
    if _EN_DASH in drafted_text:
        violations.append(
            FloorViolation(_RULE_STRUCTURAL, "value must not contain an en dash")
        )
    cap = _MAX_BEATS_CHARS if target is ReguideTarget.NODE else _MAX_LABEL_CHARS
    if len(drafted_text) > cap:
        violations.append(
            FloorViolation(
                _RULE_STRUCTURAL,
                f"value exceeds the {cap}-character limit (length {len(drafted_text)})",
            )
        )
    return violations


def _band_vocab_violations(
    drafted_text: str, age_band: AgeBand
) -> list[FloorViolation]:
    """Rule 4: band vocabulary floor (design 5.3 rule 4).

    Stem-matches the band-mandatory denylist bundles against the drafted text with
    the same word-boundary matcher the slot gate uses; any hit fails the draft.
    Deliberately stricter than strictly necessary (the gate and moderation
    re-check downstream): drafted guidance should never need the downstream net.

    Args:
        drafted_text: The agent's drafted resolution text.
        age_band: The mutant's reading age band.

    Returns:
        list[FloorViolation]: A single rule-4 violation naming the tripped
            bundles, or an empty list.
    """
    hits = denylisted_bundles(drafted_text, band_mandatory_bundles(age_band))
    if hits:
        return [
            FloorViolation(
                _RULE_BAND_VOCAB,
                f"drafted text trips band-mandatory denylist bundle(s): {sorted(hits)}",
            )
        ]
    return []


def screen_draft(  # noqa: PLR0913 -- one cohesive floor entry point
    item: ReguideItem,
    drafted_text: str,
    *,
    contract: ThemeContract | None,
    age_band: AgeBand,
    parent_node_fill: str | None = None,
) -> FloorResult:
    """Screen one drafted resolution through the deterministic reguide floor.

    Runs all four floor rules (design 5.3): surface parity, slot-token discipline,
    the structural injection block, and the band vocabulary floor. A draft
    ``passes`` only when every rule holds; the floor never marks anything resolved
    by itself, it only refuses drafts. Determinism of acceptance (rule 5) is the
    caller's obligation: only a ``promotable`` full acceptance re-run proceeds.

    Args:
        item: The emitted re-guidance item being resolved (its target kind and,
            for a NODE, its pre-mutation ``current_text`` drive the parity check).
        drafted_text: The agent's drafted resolution text (already stripped).
        contract: The mutant's theme contract, or None for a contract-less mutant.
        age_band: The mutant's reading age band, for the band vocabulary floor.
        parent_node_fill: The pre-mutation node body for a NODE target; defaults
            to the item's ``current_text`` when omitted.

    Returns:
        FloorResult: Whether the draft passed, every violation, and whether a
            human action-semantic check is still required (CHOICE / ENDING).
    """
    node_fill = parent_node_fill if parent_node_fill is not None else item.current_text
    violations: list[FloorViolation] = []
    violations.extend(_surface_parity_violations(item, drafted_text, node_fill))
    violations.extend(_slot_token_violations(drafted_text, contract))
    violations.extend(_structural_violations(drafted_text, item.target))
    violations.extend(_band_vocab_violations(drafted_text, age_band))
    return FloorResult(
        passed=not violations,
        violations=tuple(violations),
        human_check_required=item.target
        in (ReguideTarget.CHOICE, ReguideTarget.ENDING),
    )


def _load_template() -> str:
    """Return the bundled ``reguide_draft.md`` template text.

    Returns:
        str: The full template text.
    """
    # #ASSUME: data-integrity: importlib.resources finds the template in the
    # installed or src-layout package tree (same posture as generation.prompts).
    # #VERIFY: a template test loads and renders it, asserting the data fence.
    return _TEMPLATES.joinpath(_TEMPLATE_NAME).read_text(encoding="utf-8")


def _story_context(parent: Mapping[str, object]) -> str:
    """Return the parent's start-node body as tone context, truncated.

    Catalog content only (a story opening), used to give the drafter tone. Never a
    brief, theme, or request. Truncated so a long node body cannot bloat the
    prompt.

    Args:
        parent: The raw parent story document.

    Returns:
        str: The start node's body text (truncated), or an empty string.
    """
    start = parent.get("start_node")
    if not isinstance(start, str):
        return ""
    raw_nodes = parent.get("nodes")
    if not isinstance(raw_nodes, list):
        return ""
    for raw_node in cast("list[object]", raw_nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        if node.get("id") != start:
            continue
        body = node.get("body")
        if isinstance(body, str):
            return body[:600]
    return ""


def _catalog_content_block(  # noqa: PLR0913 -- one cohesive prompt data block
    item: ReguideItem,
    *,
    contract: ThemeContract | None,
    age_band: AgeBand,
    length: str,
    style: str,
    story_context: str,
) -> str:
    """Assemble the fenced catalog-content data block for the drafting prompt.

    Catalog content and cell enums only (design 5.3 ``#CRITICAL``): the item's
    reason and pre-mutation text, the cell coordinate, the contract's slot
    meanings, and a story-opening tone snippet. No request-derived input.

    Args:
        item: The emitted re-guidance item being resolved.
        contract: The mutant's theme contract, or None.
        age_band: The mutant's reading age band.
        length: The cell length tier (enum value).
        style: The cell narrative style (enum value).
        story_context: The parent's story-opening tone snippet.

    Returns:
        str: The assembled data block (goes inside the template's data fence).
    """
    lines = [
        f"reason re-guidance is needed: {item.reason}",
        f"cell: age band {age_band.value}; length {length}; style {style}",
        f"target id: {item.target_id}",
        "pre-mutation text (the surface, before the mutation):",
        item.current_text or "(none supplied)",
    ]
    if contract is not None:
        lines.append("declared slot tokens you may reuse (only these, verbatim):")
        lines.extend(f"  {{{slot.id}}}: {slot.meaning}" for slot in contract.slots)
    else:
        lines.append("this skeleton is contract-less: use no {SLOT} tokens.")
    if story_context:
        lines.append("story opening for tone (do not copy verbatim):")
        lines.append(story_context)
    return "\n".join(lines)


def render_draft_prompt(  # noqa: PLR0913 -- one cohesive prompt renderer
    item: ReguideItem,
    *,
    contract: ThemeContract | None,
    age_band: AgeBand,
    length: str,
    style: str,
    story_context: str = "",
) -> tuple[str, str]:
    """Render the drafting prompt for one re-guidance item (system, user).

    Loads ``reguide_draft.md``, substitutes the target kind and the fenced
    catalog-content data block with explicit ``.replace()`` (never ``str.format``,
    so literal braces in catalog content are safe), and splits on the single
    ``<!-- @user -->`` marker into a static system block and a volatile user block.

    Args:
        item: The emitted re-guidance item being resolved.
        contract: The mutant's theme contract, or None for a contract-less mutant.
        age_band: The mutant's reading age band.
        length: The cell length tier (enum value).
        style: The cell narrative style (enum value).
        story_context: The parent's story-opening tone snippet (optional).

    Returns:
        tuple[str, str]: The ``(system, user)`` prompt pair.

    Raises:
        BusinessLogicError: If the template lacks exactly one ``<!-- @user -->``
            marker (a template-authoring error).
    """
    catalog_content = _catalog_content_block(
        item,
        contract=contract,
        age_band=age_band,
        length=length,
        style=style,
        story_context=story_context,
    )
    text = (
        _load_template()
        .replace("{target_kind}", item.target.value)
        .replace("{catalog_content}", catalog_content)
    )
    parts = text.split(_USER_MARKER)
    if len(parts) != 2:
        msg = (
            f"template must contain exactly one '{_USER_MARKER}' marker; "
            f"found {len(parts) - 1}"
        )
        raise BusinessLogicError(msg, rule="reguide_draft_marker")
    system, user = parts
    return system.strip(), user.strip()


def _draft_note(result: FloorResult) -> str:
    """Return the audit note recorded alongside a passing drafted resolution.

    Args:
        result: The passing floor result.

    Returns:
        str: A note flagging the human action-semantic check for a CHOICE /
            ENDING draft, else an empty string.
    """
    if result.human_check_required:
        return (
            "agent-drafted; action-semantic obligation is human-checked in the "
            "promotion PR"
        )
    return "agent-drafted; floor-screened; human-reviewed in the promotion PR"


async def draft_resolutions(  # noqa: PLR0913 -- one cohesive drafting orchestration
    emitted: Sequence[ReguideItem],
    *,
    provider: GenerationProvider,
    model_id: str,
    contract: ThemeContract | None,
    age_band: AgeBand,
    length: str,
    style: str,
    parent: Mapping[str, object],
) -> ReguideResolutions:
    """Draft, floor-screen, and attribute a resolution for each emitted item.

    For every outstanding re-guidance item this renders the catalog-content-only
    drafting prompt, calls the injected provider once, screens the completion
    through :func:`screen_draft`, and, ONLY on a pass, emits a
    :class:`~cyo_adventure.mutation.reguide.ResolvedReguide` attributed
    ``author="agent:<model-id>"``. A floor failure leaves the item unresolved (it
    is simply not in the returned set), which leaves the candidate held. The
    caller re-runs the UNCHANGED acceptance harness with ``resolved_ids(...)`` and
    only a ``promotable`` result proceeds (design 5.3 rule 5).

    Args:
        emitted: The outstanding re-guidance items (a chain's surviving items).
        provider: The injected LLM completion backend (a deterministic fake in
            tests; the one LLM touchpoint WS-8 adds).
        model_id: The drafting model id, recorded as ``agent:<model_id>``.
        contract: The mutant's theme contract, or None for a contract-less mutant.
        age_band: The mutant's reading age band.
        length: The cell length tier (enum value).
        style: The cell narrative style (enum value).
        parent: The raw parent story document (for story-opening tone context;
            catalog content only).

    Returns:
        ReguideResolutions: The floor-passing, agent-attributed resolutions (a
            subset of ``emitted``; empty when none passed).
    """
    # #CRITICAL: security: this is the one WS-8 provider call. Its inputs are
    # catalog content and cell enums only (rendered by render_draft_prompt); no
    # request text, brief, theme, family, or child artifact reaches it,
    # transitively (design 5.3 #CRITICAL, plan safety invariant 4, OWASP LLM01).
    # The output is untrusted-derived: it is floor-screened below before it can
    # become a resolution, and faces the full acceptance re-run plus human PR
    # review before it can touch skeletons/ on main.
    # #VERIFY: tests inject a MockProvider (no network); a signature/AST test
    # pins that no brief/theme/premise/request parameter exists and that this
    # package imports nothing from story_requests; a floor-failing completion
    # yields no resolution.
    story_context = _story_context(parent)
    resolutions: list[ResolvedReguide] = []
    for item in emitted:
        system, user = render_draft_prompt(
            item,
            contract=contract,
            age_band=age_band,
            length=length,
            style=style,
            story_context=story_context,
        )
        completion = await provider.complete(
            system=system, prompt=user, max_tokens=_DRAFT_MAX_TOKENS
        )
        drafted_text = completion.strip()
        result = screen_draft(item, drafted_text, contract=contract, age_band=age_band)
        if not result.passed:
            continue
        resolutions.append(
            ResolvedReguide(
                target=item.target,
                target_id=item.target_id,
                resolved_text=drafted_text,
                author=f"agent:{model_id}",
                note=_draft_note(result),
            )
        )
    return ReguideResolutions(resolutions=resolutions)
