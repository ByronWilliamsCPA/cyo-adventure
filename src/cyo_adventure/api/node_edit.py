"""The lightweight passage editor with re-review (register G6, Phase 4b).

``PATCH /storybooks/{storybook_id}/versions/{version}/nodes/{node_id}`` edits
ONE node's prose (its body text, and/or the label text of its existing
choices) and nothing else: ids, choice targets, conditions, effects, and the
graph shape are structurally untouchable through this endpoint, because the
handler only ever writes ``node["body"]`` and an existing choice's
``["label"]`` on a deep copy of the stored blob.

Allowed only while the storybook is ``in_review`` or ``needs_revision`` (never
``draft``, ``published``, or ``archived``); role admin, or guardian for their
own family's story (approval itself stays admin-only regardless -- this
endpoint never calls ``publishing.service.approve``).

Re-review mechanics
--------------------
Every edit re-runs the deterministic gate (``validator.gate.run_fill_gate``) over
the FULL edited blob, since a prose change can still blow a length or
reading-level budget (L1-7 / RL-13) or, if a choice label was cleared to
empty, ... (rejected earlier by the schema's ``min_length=1``, but a body
edit alone can still trip L1-7). A gate ERROR rejects the whole edit with a
422 carrying the failing findings; the stored blob is untouched (the mutation
happens on a local copy that is discarded on any rejection).

If the gate passes, the edited node's text is re-screened by the same two
HARD-gating moderation checks ``moderation.pipeline.run_moderation_pipeline``
runs at generation time -- Stage 0 classifiers (``moderation.classifiers.
run_classifiers``) and Stage 1 safety (``moderation.stages.run_safety_stage``)
-- scoped to just this node, via the same ``build_review_provider`` +
``PiiGuardedProvider`` seam the pipeline uses, so unit tests double the same
boundary (MockProvider / httpx.MockTransport). Stage 3-4 (coherence/
engagement) are NOT re-run here: they are whole-story checks a single node's
re-review cannot honestly stand in for. (Stage 2, per-node LLM readability,
is no longer a stage at all: it was retired in favour of the gate's
deterministic RL-13, which this endpoint already re-runs.) Re-running the
full pipeline synchronously inside an HTTP request
would also break this codebase's established pattern of doing all LLM
generation work in the background RQ worker (generation/worker.py), never
inline in a request handler. This is the documented "smallest honest
version" scope decision for register G6.

A moderation finding -- including a fresh hard BLOCK -- does NOT reject the
write. Mirroring ADR-005 (the human reviewer is the final gate), moderation
findings are surfaced on the refreshed review surface for a human to weigh,
exactly like the generation-time report; only the deterministic gate blocks
the write outright. The refreshed findings for this node id replace its prior
per-node Stage-0/Stage-1 findings; every other node's findings, and the
whole-story Stage 3-4 findings, are carried over unchanged.

No forced state transition. This endpoint never changes ``storybook.status``.
Because ``publishing.service.approve`` is the SOLE publish path, always reads
the version's CURRENT blob at call time, and requires ``status == in_review``
(``publishing/state_machine.py``), there is no "approved but not yet
published" resting state a stale edit could invalidate: an edit to an
in_review story simply changes what a subsequent approve() will publish. The
re-review guarantee is structural, not a status flip: the refreshed report
this handler persists is what the review surface (and the queue's screened
flag) show the next time anyone -- including the approving admin -- loads it.
# #EDGE: timing dependencies: an admin with a stale review page open from
# before the edit could still click "Confirm approve" without reloading;
# approve() would then publish the freshly edited (correct) content, just
# without that admin having re-read it on screen. This is a UX staleness risk,
# not a data-integrity one (the published content is exactly the current row),
# and closing it would need an optimistic-concurrency token on approve() that
# is out of scope for this endpoint.
# #VERIFY: none yet; a future ETag/If-Match on approve() would close this.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, cast

import httpx
from anyio.to_thread import run_sync
from fastapi import APIRouter
from sqlalchemy import func, select

from cyo_adventure.api.deps import Context, authorize_family
from cyo_adventure.api.gate_limits import gate_limiter
from cyo_adventure.api.review_surface import build_review_surface
from cyo_adventure.api.schemas import NodeEditBody, ReviewSurfaceView
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, Storybook, StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.personalizable_slots import (
    PersonalizableSlots,
    PersonalizableSlotsUnrecoverable,
    personalizable_slot_ids_for_story,
)
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.review_provider import (
    build_review_provider,
    resolve_review_settings,
)
from cyo_adventure.moderation.stages import run_safety_stage
from cyo_adventure.moderation.thresholds import load_admin_noise_floor
from cyo_adventure.publishing.state_machine import Status
from cyo_adventure.storybook.reinsertion import (
    build_manifest,
    manifest_carries_tokens,
)
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_fill_gate
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity_at_rest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["node-edit"])

_logger = get_logger(__name__)

# Editable-state allowlist: a prose edit may land on a version awaiting review
# (fresh from generation/import) or one already sent back; never a draft (not
# yet screened at all -- editing ahead of the first moderation pass would let
# unscreened prose skip straight to a re-review that assumes a baseline
# exists), and never published/archived (immutable once released, ADR-005).
_EDITABLE_STATUSES = frozenset({Status.IN_REVIEW, Status.NEEDS_REVISION})

# Mirrors moderation/pipeline.py's _MAX_REVIEW_TOKENS: the review prompt asks
# for one short JSON verdict, not prose generation.
_MAX_REVIEW_TOKENS = 1024

# Sources whose per-node findings this endpoint fully refreshes for the edited
# node (Stage 0 classifiers + Stage 1 safety, both hard-gating and per-node).
# Stage 3-4 sources are never in this set: their findings for OTHER nodes (or
# the whole story) must survive an edit untouched. Neither is the retired
# Stage 2's Source.LLM_READABILITY, which no stage produces anymore but which
# old persisted reports still carry and must keep carrying (stages.py's
# additive-safe contract, design doc 2.1). Source.PERSPECTIVE is a second
# retired source (ratified sunset; run_classifiers no longer calls
# Perspective), kept here so a stale historical Perspective finding on the
# edited node is still superseded by this refresh rather than fossilized.
_REFRESHED_SOURCES = frozenset({Source.OPENAI, Source.PERSPECTIVE, Source.LLM_SAFETY})


async def _load_edit_target(ctx: Context, storybook_id: str) -> Storybook:
    """Load a storybook for a passage edit, enforcing the role + ownership gate.

    Args:
        ctx: The request context (principal and session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: The locked storybook row.

    Raises:
        AuthorizationError: If the caller is neither admin nor guardian
            (-> 403), or a guardian's family does not own the story (-> 403).
        ResourceNotFoundError: If the story does not exist (-> 404).
    """
    # #CRITICAL: security: role gate before any row is read, mirroring every
    # other guardian-or-admin endpoint in this codebase (e.g.
    # story_requests.py, device_grants.py): admin is the global safety
    # operator, guardian is scoped to their own family below via
    # authorize_family. Neither a child nor a device token may edit prose.
    # #VERIFY: tests/unit/test_node_edit.py::test_child_role_rejected,
    # ::test_device_role_rejected.
    if not (ctx.principal.is_admin or ctx.principal.is_guardian):
        msg = "admin or guardian role required"
        raise AuthorizationError(msg, required_permission="admin_or_guardian")
    # #CRITICAL: concurrency: locks the storybook row for the duration of this
    # edit, matching every other mutating publishing-adjacent handler
    # (api/approval.py::_load_admin_story, moderation/pipeline.py). Without
    # it, a concurrent approve() on the same story could publish mid-edit; the
    # lock makes the two transactions serialize instead of interleaving.
    # #VERIFY: tests/unit/test_node_edit.py::test_load_edit_target_locks_row_for_update.
    stmt = select(Storybook).where(Storybook.id == storybook_id).with_for_update()
    book = (await ctx.session.execute(stmt)).scalar_one_or_none()
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not ctx.principal.is_admin:
        # #CRITICAL: security: a guardian may edit only their own family's
        # story; admin authority is global and skips this check (mirrors
        # api/approval.py's admin-is-cross-family stance).
        # #VERIFY: tests/integration/test_authz_matrix.py cross-family
        # guardian case; tests/unit/test_node_edit.py::
        # test_guardian_other_family_rejected.
        authorize_family(ctx.principal, book.family_id)
    return book


async def _latest_version_number(session: AsyncSession, storybook_id: str) -> int:
    """Return the highest version number for a storybook.

    Args:
        session: The request session.
        storybook_id: The story id.

    Returns:
        int: The latest version number.

    Raises:
        ResourceNotFoundError: If the story has no versions.
    """
    latest = await session.scalar(
        select(func.max(StorybookVersion.version)).where(
            StorybookVersion.storybook_id == storybook_id
        )
    )
    if latest is None:
        msg = f"storybook '{storybook_id}' has no versions"
        raise ResourceNotFoundError(msg)
    return latest


def _find_node(
    blob: dict[str, object], node_id: str, *, storybook_id: str, version: int
) -> dict[str, object]:
    """Return the mutable node dict with ``id == node_id`` from a blob copy.

    Args:
        blob: The (already-copied) story blob.
        node_id: The node id from the path.
        storybook_id: The story id, for the not-found message.
        version: The version number, for the not-found message.

    Returns:
        dict[str, object]: The node dict, safe to mutate in place.

    Raises:
        ResourceNotFoundError: If no node in the blob carries this id.
    """
    nodes = blob.get("nodes")
    if isinstance(nodes, list):
        # #ASSUME: data-integrity: "list[object]"/"dict[str, object]" repeat
        # across this module's cast() calls (Sonar S1192); hoisting either to
        # a module-level constant breaks basedpyright's cast() overload
        # (it only narrows a type from a literal string in the source, not a
        # variable, so the result silently becomes Unknown), and dropping the
        # quotes to a bare `cast(dict[str, object], ...)` trips this
        # project's own ruff TC006 (quote type expressions in typing.cast()).
        # Kept as repeated literals; both other options regress an enforced
        # gate.
        # #VERIFY: uv run basedpyright + uv run ruff check on this file.
        for entry in cast("list[object]", nodes):  # NOSONAR
            if isinstance(entry, dict):
                typed_entry = cast("dict[str, object]", entry)  # NOSONAR
                if typed_entry.get("id") == node_id:
                    return typed_entry
    msg = f"node '{node_id}' not found in storybook '{storybook_id}' v{version}"
    raise ResourceNotFoundError(msg)


def _apply_choice_labels(node: dict[str, object], labels: dict[str, str]) -> None:
    """Rewrite the label text of EXISTING choices on ``node``, in place.

    Args:
        node: The mutable node dict.
        labels: choice_id -> new label text. Every id must already exist on
            this node's ``choices``; no choice is added, removed, or
            retargeted here.

    Raises:
        ValidationError: If any id in ``labels`` is not one of the node's
            existing choice ids (structural tampering attempt: this endpoint
            is prose-only).
    """
    choices = node.get("choices")
    choice_list = cast("list[object]", choices) if isinstance(choices, list) else []
    by_id: dict[object, dict[str, object]] = {}
    for entry in choice_list:
        if isinstance(entry, dict):
            typed_choice = cast("dict[str, object]", entry)
            by_id[typed_choice.get("id")] = typed_choice
    unknown = sorted(set(labels) - {cid for cid in by_id if isinstance(cid, str)})
    if unknown:
        msg = "choice_labels names a choice id this node does not have"
        raise ValidationError(msg, field="choice_labels", value=unknown)
    for choice_id, text in labels.items():
        by_id[choice_id]["label"] = text


def _node_text(node: dict[str, object]) -> str:
    """Return a node's body as ``str``, defaulting to empty for a bad shape."""
    body = node.get("body")
    return body if isinstance(body, str) else ""


def _age_band(blob: dict[str, object]) -> str:
    """Return the blob's ``metadata.age_band``, defaulting to an empty string."""
    metadata = blob.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    band = cast("dict[str, object]", metadata).get("age_band")
    return band if isinstance(band, str) else ""


async def _family_child_names(
    session: AsyncSession, family_id: object
) -> frozenset[str]:
    """Return the real display names of a family's child profiles.

    Args:
        session: The request session.
        family_id: The owning family's id (the story's family, not
            necessarily the caller's, for the admin cross-family case).

    Returns:
        frozenset[str]: Every child display name in the family, for the PII
        egress guard on the re-review prompt.
    """
    rows = await session.scalars(
        select(ChildProfile.display_name).where(ChildProfile.family_id == family_id)
    )
    return frozenset(rows.all())


def _without_edited_node(
    finding: dict[str, object], node_id: str
) -> dict[str, object] | None:
    """Return the stored finding with the edited node's coverage withdrawn.

    The edited node has just been re-reviewed from scratch, so any stored
    finding from a refreshed source no longer speaks for it. Three outcomes:

    * The finding does not cover the edited node (or comes from a source this
      endpoint does not refresh): returned unchanged.
    * Its ONLY coverage is the edited node: returned as ``None`` (dropped),
      superseded by the fresh re-review.
    * It is a merged finding (design doc 2.2) covering the edited node
      ALONGSIDE others: returned narrowed, with the edited node removed from
      ``node_ids`` and ``node_id`` re-pointed at the first survivor.

    # #CRITICAL: data integrity: narrowing is only sound because the merge
    # stage is lossless: ``moderation/synthesis.py`` groups on the full tuple
    # of fields a merged finding carries, so every node in ``node_ids`` shares
    # one verdict, severity, and message. Dropping one node therefore leaves a
    # finding that is still exactly true of the survivors. Were the merge to
    # widen its key again so a group could mix verdicts or messages, this
    # function would have to split the finding instead.
    # #VERIFY: tests/unit/test_node_edit.py::
    # test_multi_node_merged_finding_narrows_to_the_unedited_nodes,
    # ::test_single_node_merged_finding_dropped_as_stale,
    # ::test_merged_finding_covering_an_untouched_node_set_is_left_alone.

    Args:
        finding: One stored finding dict (any shape: pre- or post-Stage-B).
        node_id: The edited node's id.

    Returns:
        dict[str, object] | None: The finding to keep, or ``None`` to drop it.
    """
    if finding.get("source") not in {s.value for s in _REFRESHED_SOURCES}:
        return finding
    node_ids = finding.get("node_ids")
    if not isinstance(node_ids, list):
        return None if finding.get("node_id") == node_id else finding
    typed_ids = [n for n in cast("list[object]", node_ids) if isinstance(n, str)]
    if node_id not in typed_ids:
        return finding
    remaining = [n for n in typed_ids if n != node_id]
    if not remaining:
        return None
    return {**finding, "node_ids": remaining, "node_id": remaining[0]}


def _merge_moderation_report(
    stored: dict[str, object] | None,
    node_id: str,
    fresh_findings: list[Finding],
    *,
    independent: bool,
) -> dict[str, object]:
    """Replace one node's refreshed-source findings, keeping everything else.

    Args:
        stored: The version's previously persisted moderation report, or
            ``None`` if the version was never moderated.
        node_id: The edited node's id.
        fresh_findings: The newly computed Stage 0 + Stage 1 findings for
            this node. May include PASS verdicts (a clean classifier or
            safety-stage result); these are filtered out before persisting,
            matching design doc 2.1's PASS-is-never-persisted rule.
        independent: Whether THIS re-review's provider is independent of the
            generator; ANDed with the stored report's own flag so the report
            only claims full independence when every contributing review was.

    Returns:
        dict[str, object]: A new ``ModerationReport.to_dict()``-shaped
        mapping: this node's stale findings are withdrawn (see
        ``_without_edited_node``, which drops a finding scoped to this node
        alone and narrows a merged finding that also covers others), every
        other finding (other nodes' per-node findings, whole-story Stage 3-4
        findings) is carried over verbatim, and the fresh non-PASS findings
        are appended. The stored report's ``aggregate`` block, if present, is
        carried over verbatim (never recomputed here) and omitted entirely
        when the stored report predates it.
    """
    old_findings_raw = stored.get("findings") if isinstance(stored, dict) else None
    old_findings: list[object] = (
        cast("list[object]", old_findings_raw)
        if isinstance(old_findings_raw, list)
        else []
    )
    kept: list[dict[str, object]] = []
    for entry in old_findings:
        if not isinstance(entry, dict):
            continue
        retained = _without_edited_node(cast("dict[str, object]", entry), node_id)
        if retained is not None:
            kept.append(retained)
    # #ASSUME: data integrity: design doc 2.1: PASS is never persisted. A
    # fresh single-node re-review can still emit PASS (a clean classifier or
    # safety-stage result); filter it here so this write path matches
    # moderation/pipeline.py::_persist_report's PASS-aggregation rule
    # instead of reintroducing the persisted-PASS-row shape Stage B removed.
    # #VERIFY: tests/unit/test_node_edit.py::test_fresh_pass_findings_not_persisted.
    fresh_non_pass = [f for f in fresh_findings if f.verdict is not Verdict.PASS]
    merged = [*kept, *(f.to_dict() for f in fresh_non_pass)]
    hard_block = any(f.get("verdict") == Verdict.BLOCK.value for f in merged)
    soft_flag = (not hard_block) and any(
        f.get("verdict") == Verdict.FLAG.value for f in merged
    )
    old_summary = stored.get("summary") if isinstance(stored, dict) else None
    old_summary_dict = (
        cast("dict[str, object]", old_summary) if isinstance(old_summary, dict) else {}
    )
    old_repaired = old_summary_dict.get("repaired")
    old_independent = old_summary_dict.get("reviewer_independent")
    result: dict[str, object] = {
        "findings": merged,
        "summary": {
            "count": len(merged),
            "hard_block": hard_block,
            "soft_flag": soft_flag,
            "repaired": bool(old_repaired) if isinstance(old_repaired, bool) else False,
            "reviewer_independent": independent
            and (old_independent if isinstance(old_independent, bool) else True),
        },
    }
    # #ASSUME: data integrity: the stored aggregate block (nodes_reviewed /
    # pass_counts) reflects the LAST FULL pipeline pass, not this single-node
    # re-review; carry it verbatim rather than recomputing, since the old
    # PASS rows it was built from are no longer persisted and cannot be
    # recovered here. This node's fresh PASS evidence (if any) is
    # deliberately NOT folded into pass_counts: a slight undercount is the
    # fail-safe direction, it never overstates how much was reviewed clean.
    # #VERIFY: tests/unit/test_node_edit.py::
    # test_aggregate_carried_verbatim_when_present,
    # ::test_aggregate_omitted_when_absent.
    if isinstance(stored, dict) and "aggregate" in stored:
        result["aggregate"] = stored["aggregate"]
    return result


def _personalization_eligible(
    personalizable_slots: PersonalizableSlots, blob: dict[str, object]
) -> bool:
    """Decide the persisted ``personalization_eligible`` flag for an edited blob.

    # #CRITICAL: data integrity: this reads the UNCOLLAPSED tri-state, not the
    # empty-set collapse `edit_node` performs for the at-rest integrity check.
    # That collapse is authorized for exactly one decision ("reject any
    # sentinel this edit leaves behind"), where "no slot is declared" and
    # "which slots are declared cannot be proven" genuinely coincide. They do
    # NOT coincide here: an unrecoverable contract is not evidence that the
    # story declares no personalizable slot, and this column is a persisted
    # claim that `api/library.py` reads verbatim. So the marker is answered on
    # its own terms below rather than inherited from a value computed for a
    # different question.
    # #VERIFY: tests/unit/test_node_edit.py::
    # test_unrecoverable_contract_drives_eligibility_from_the_tri_state and
    # ::test_personalization_eligible_is_false_for_an_unrecoverable_contract.

    Args:
        personalizable_slots: The story's resolved personalizable-slot
            tri-state (see ``moderation/personalizable_slots.py``).
        blob: The blob about to be stored, i.e. the EDITED document, so the
            flag describes what is being persisted rather than what was read.

    Returns:
        bool: ``True`` only when the story provably declares at least one
        personalizable slot AND the blob still carries a sentinel token.
        ``False`` for an unrecoverable contract: the column gates an
        affordance, so the fail-closed answer is to withhold it. The cost of
        being wrong that way is a genuinely personalizable book briefly
        offered as plain prose; the cost the other way is advertising a
        personalization the story's declared-slot set cannot be shown to
        support.
    """
    if isinstance(personalizable_slots, PersonalizableSlotsUnrecoverable):
        return False
    # Narrowed to the frozenset arm first, which is what makes this truthiness
    # test legitimate rather than the falsy-collapse the marker type exists to
    # prevent.
    return bool(personalizable_slots) and manifest_carries_tokens(build_manifest(blob))


@router.patch("/storybooks/{storybook_id}/versions/{version}/nodes/{node_id}")
async def edit_node(
    storybook_id: str,
    version: int,
    node_id: str,
    body: NodeEditBody,
    *,
    ctx: Context,
) -> ReviewSurfaceView:
    """Apply a prose-only edit to one node, re-running the gate and moderation.

    Args:
        storybook_id: The story id from the path.
        version: The version number from the path; must be the story's
            latest version.
        node_id: The node id from the path.
        body: The edit: new body text and/or new choice label text, prose only.
        ctx: The request context (principal and session).

    Returns:
        ReviewSurfaceView: The refreshed review surface (the same shape
            ``GET .../review`` returns), reflecting the newly persisted blob
            and reports.

    Raises:
        AuthorizationError: Neither admin nor guardian (-> 403); a guardian
            outside the story's family (-> 403).
        ResourceNotFoundError: Unknown story/version/node (-> 404).
        StateTransitionError: The story is not ``in_review`` or
            ``needs_revision`` (-> 409), or ``version`` is not the latest
            version (-> 409).
        ValidationError: ``choice_labels`` names an id the node does not
            have (-> 422), or the edited blob fails the deterministic gate
            (-> 422; the stored blob is left unchanged).
    """
    book = await _load_edit_target(ctx, storybook_id)
    # #CRITICAL: data integrity: the ORM status string is coerced through the
    # closed Status enum at this boundary (mirrors publishing/service.py),
    # so an unmodeled DB status raises rather than silently permitting an
    # edit.
    # #VERIFY: tests/unit/test_node_edit.py::test_draft_rejected,
    # ::test_published_rejected, ::test_archived_rejected.
    status = Status(book.status)
    if status not in _EDITABLE_STATUSES:
        msg = "cannot edit a passage unless the story is in_review or needs_revision"
        raise StateTransitionError(
            msg, rule="node_edit_wrong_state", context={"status": book.status}
        )
    latest = await _latest_version_number(ctx.session, storybook_id)
    if version != latest:
        msg = "only the latest version of a story can be edited"
        raise StateTransitionError(
            msg,
            rule="node_edit_not_latest_version",
            context={"requested": version, "latest": latest},
        )
    version_row = await ctx.session.get(StorybookVersion, (storybook_id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)

    # #CRITICAL: data integrity: mutate a deep copy, never the ORM-tracked
    # dict in place, so a gate rejection below leaves version_row.blob (and
    # thus what a concurrent reader sees before this transaction commits)
    # byte-for-byte unchanged -- the "leave the stored blob unchanged" cap.
    # #VERIFY: tests/unit/test_node_edit.py::test_gate_failure_leaves_blob_unchanged.
    new_blob = copy.deepcopy(version_row.blob)
    node = _find_node(new_blob, node_id, storybook_id=storybook_id, version=version)
    if body.body is not None:
        node["body"] = body.body
    if body.choice_labels:
        _apply_choice_labels(node, body.choice_labels)

    # #CRITICAL: data integrity: a prose edit alone can still blow the L1-7
    # node/word budget or (advisory) the RL-13 reading-level band; the FULL
    # edited blob is re-validated, not just the touched node, because L1/L2
    # are graph-wide checks.
    # #VERIFY: tests/unit/test_node_edit.py::test_gate_failing_edit_rejected_422.
    # #CRITICAL: timing: run_gate is pure synchronous CPU, and a character
    # envelope multiplies its cost by roughly the envelope's entry-state
    # count, because the CH-3a/CH-3b/CH-4 rules re-walk the story once per
    # entry state. Re-measured 2026-08-06 against real catalog skeletons:
    # the largest book (skeletons/16+/the-longwinter-station.json, 248 nodes,
    # 51,241 base configurations) runs in 0.8s with no envelope and 49.6s
    # with the canonical 27-state accepts_character envelope, a 64x
    # multiplier. The figure this marker used to quote, 3.7s on a 746-node
    # story, is a no-envelope measurement and is no longer the worst case:
    # budget against tens of seconds. A book an ERROR-severity CH rule
    # rejects is cheap again (0.98s on the same book) because
    # validator/character.py skips the walk block once any CH ERROR is in
    # the report, but that only covers the rejected path.
    # Calling this inline in an async handler would stall the whole event
    # loop for that window, blocking every other in-flight request including
    # a child mid-read (AL-035); anyio.to_thread keeps the loop responsive.
    # UW-A47: the hold is now bounded to gate_limiter()'s N concurrent calls
    # (default 4, see core/config.py::gate_max_concurrency), shared with
    # api/generation.py's validate_version call site via
    # api/gate_limits.py::gate_limiter(). That bounds how many callers may
    # occupy an AnyIO worker thread for the gate at once; it does not shorten
    # the 49.58s per-call worst case above, so a queued request still holds
    # its HTTP connection and may time out. Latent today only because no
    # catalog book declares accepts_character.
    # #VERIFY: the handler's existing tests still pass; the gate is pure and
    # holds no session, so running it off-loop is safe.
    # tests/unit/test_gate_capacity_limiter.py pins the shared-limiter and
    # smaller-than-the-default-pool properties. Re-measure the worst case
    # before the first character-enabled book ships, by timing run_gate over
    # the longwinter-station skeleton with a might/wits/nerve 0-2 envelope.
    # #CRITICAL: data integrity: run_fill_gate, not run_gate. The blob being
    # re-gated here is a FILLED book, and the bare run_gate call this replaced
    # defaulted to the catalog-time "skeleton" posture, under which a retained
    # `<<FILL ...>>` directive is expected input rather than a defect. PL-27 is
    # the only deterministic floor between an unwritten node and a human
    # reviewer (validator/policy.py::check_fill_directives), so under the wrong
    # posture an edit could replace prose with a directive, be accepted, and be
    # recorded clean in the validation_report the review surface displays.
    # #VERIFY: tests/unit/test_node_edit.py::
    # test_edit_writing_a_fill_directive_is_rejected reproduces the acceptance
    # this fixes.
    gate_result = await run_sync(run_fill_gate, new_blob, limiter=gate_limiter())
    if gate_result.blocked:
        msg = "edited passage failed the validation gate"
        raise ValidationError(
            msg,
            details={"findings": [f.to_dict() for f in gate_result.report.errors]},
        )

    # #CRITICAL: security: an admin/guardian edit can drop, forge, or
    # relocate a personalization sentinel on an already-approved story
    # undetected (register G6 originally only re-ran the sentinel-blind
    # deterministic gate above). Re-resolve the story's declared
    # personalizable-slot set (Task 6a; the SAME resolver the moderation
    # pipeline's entry backstop and repair gate reuse) and re-check the
    # EDITED blob at rest. A non-ok result fails closed, exactly like the
    # gate-block cap above: the edit is rejected before anything is
    # persisted, and the mutation happened on a local copy (`new_blob`) that
    # is simply discarded.
    #
    # An UNRECOVERABLE contract (`PERSONALIZABLE_SLOTS_UNRECOVERABLE`)
    # degrades to an empty declared-slot set rather than a hard block. That
    # collapse is deliberate for THIS check and nowhere else, which is why the
    # collapsed value is named for its single authorized use: for an editor,
    # "no slot is declared" and "we cannot prove which slots are declared"
    # both mean "reject any sentinel this edit leaves behind", so the two arms
    # genuinely coincide. The persisted `personalization_eligible` flag below
    # is a DIFFERENT decision, where they do not coincide, so it reads the
    # uncollapsed tri-state instead (see `_personalization_eligible`).
    # The `isinstance` spells the collapse out rather than letting a
    # truthiness test perform it silently. `check_sentinel_integrity_at_rest` with
    # no declared slots still fails closed on any sentinel actually present
    # in the edited blob (every well-formed sentinel becomes `unknown_slot`,
    # every near-miss `malformed`), so a forged or leftover sentinel is
    # still caught. But a sentinel-free edit, which is every edit to the
    # entire existing (dormant) catalog, is no longer permanently 422'd by
    # an unrelated contract-recovery failure. This preserves the security
    # invariant for the only blobs that carry sentinel risk while removing
    # the lockout for blobs that carry none.
    # #VERIFY: tests/unit/test_node_edit.py::
    # test_edit_injecting_forged_sentinel_rejected_and_blob_unchanged,
    # ::test_edit_leaving_sentinel_in_choice_label_rejected,
    # ::test_edit_contract_unrecoverable_with_sentinel_rejected,
    # ::test_edit_contract_unrecoverable_sentinel_free_succeeds,
    # ::test_edit_sentinel_free_still_succeeds (dormancy).
    personalizable_slots = await personalizable_slot_ids_for_story(
        ctx.session, storybook_id
    )
    slots_for_integrity_check: frozenset[str]
    if isinstance(personalizable_slots, PersonalizableSlotsUnrecoverable):
        # The resolver logs its own event naming the slug and band that failed
        # to load; this line records the CONSEQUENCE at the decision point:
        # this edit is being integrity-checked against an empty declared set.
        # INFO, not WARNING: the underlying fault is already on the log at
        # WARNING from the resolver, and the collapse itself is a designed,
        # still-fail-closed degrade (a sentinel-bearing edit is rejected
        # below), so re-alarming here would double-count one fault.
        # #VERIFY: tests/unit/test_node_edit.py::
        # test_unrecoverable_contract_is_logged_at_the_edit_site.
        _logger.info(
            "node_edit.slot_contract_unrecoverable_empty_declared_set",
            storybook_id=storybook_id,
            version=version,
            node_id=node_id,
        )
        slots_for_integrity_check = frozenset()
    else:
        slots_for_integrity_check = personalizable_slots
    integrity_result = check_sentinel_integrity_at_rest(
        new_blob, slots_for_integrity_check
    )
    if not integrity_result.ok:
        msg = "edited passage introduced a sentinel-integrity violation"
        raise ValidationError(
            msg,
            details={
                # #ASSUME: security: the raw sentinel token is redacted from
                # the 422 response body as defense-in-depth. node_id + kind let
                # the admin locate and classify the violation; the token holds
                # only a generic default server-side, never child data.
                # #VERIFY: keep sentinel tokens out of every log/response sink.
                "violations": [
                    {"node_id": v.node_id, "kind": v.kind}
                    for v in integrity_result.violations
                ]
            },
        )

    # #CRITICAL: external-resources: the review call is network I/O to the
    # configured classifier/LLM review backend; both degrade gracefully (no
    # configured key skips a classifier; MockProvider is the dev/test
    # default), matching moderation/pipeline.py's own posture.
    # #VERIFY: tests/unit/test_node_edit.py patches build_review_provider /
    # run_classifiers exactly like tests/unit/test_moderation_pipeline.py.
    child_names = await _family_child_names(ctx.session, book.family_id)
    pii = PiiContext(child_names=child_names)
    review_settings = resolve_review_settings(settings, None)
    review_provider, independent = build_review_provider(
        review_settings,
        generator_provider=version_row.provider,
        generator_model=version_row.model,
    )
    guarded_review = PiiGuardedProvider(review_provider, forbidden=pii)
    node_text = _node_text(node)
    # #CRITICAL: security: the classifier call below is a distinct egress path
    # from the LLM safety stage (which is protected structurally by
    # PiiGuardedProvider via guarded_review). Screen the edited node text here
    # so OpenAI Moderation gets the same guard the generation-time moderation
    # pipeline applies (moderation/pipeline.py), instead of receiving an
    # admin/guardian's raw edited prose unconditionally.
    # #VERIFY: tests/unit/test_node_edit.py::test_classifier_call_blocked_on_pii_in_edited_text.
    assert_prompt_pii_safe(node_text, forbidden=pii)
    fresh_findings: list[Finding] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        fresh_findings.extend(
            await run_classifiers(
                nodes=[(node_id, node_text)],
                openai_key=settings.openai_api_key,
                client=client,
            )
        )
    # Short-circuit exactly like moderation/pipeline.py: a Stage-0 bright-line
    # block skips the LLM safety call.
    if not any(f.verdict is Verdict.BLOCK for f in fresh_findings):
        fresh_findings.extend(
            await run_safety_stage(
                provider=guarded_review,
                nodes=[(node_id, node_text)],
                age_band=_age_band(new_blob),
                max_tokens=_MAX_REVIEW_TOKENS,
            )
        )

    # #CRITICAL: security: a moderation hard block does NOT reject the write.
    # ADR-005: the human reviewer is the final gate. Only the deterministic
    # gate above blocks the edit outright; a fresh block here is persisted
    # and surfaced on the review surface for a human to weigh, exactly like
    # the generation-time report (approve() does not itself check
    # has_hard_block either -- it only requires SOME moderation_report to
    # exist).
    # #VERIFY: tests/unit/test_node_edit.py::test_moderation_block_persists_not_rejects.
    refreshed_report = _merge_moderation_report(
        version_row.moderation_report, node_id, fresh_findings, independent=independent
    )

    # Serialized once and reused by the response projection below, so the
    # persisted column and the returned surface cannot drift apart.
    validation_report = gate_result.report.to_dict()

    version_row.blob = new_blob
    version_row.validation_report = validation_report
    version_row.moderation_report = refreshed_report
    # #CRITICAL: data integrity: the blob just changed under a flag derived
    # from the PREVIOUS blob. `personalization_eligible` is written once at
    # persist time (generation/persistence.py) and read verbatim by
    # api/library.py, so an edit that deletes the story's last sentinel would
    # otherwise leave the column advertising a personalization affordance the
    # blob can no longer honor. `check_sentinel_integrity_at_rest` above does
    # not close this: it rejects a FORGED or mutated sentinel, and deleting
    # one is a legitimate edit. Re-derive from the blob actually being stored.
    # `sentinel_manifest` is deliberately NOT refreshed here; that is the open
    # half of Task R3 recorded on the column itself in db/models.py.
    # Derived from `personalizable_slots` (the tri-state), NOT from
    # `slots_for_integrity_check` (the collapse authorized only for the at-rest
    # check above); see `_personalization_eligible` for why the two decisions
    # must not share one value.
    # #VERIFY: tests/unit/test_node_edit.py::
    # test_edit_removing_last_sentinel_clears_personalization_eligible and
    # ::test_unrecoverable_contract_drives_eligibility_from_the_tri_state.
    version_row.personalization_eligible = _personalization_eligible(
        personalizable_slots, new_blob
    )

    # #CRITICAL: data integrity: the append-only audit record of this edit;
    # payload is the node id ONLY, never the edited prose (spec D3). Flushed
    # by record_event in the same pending transaction as the blob/report
    # writes above, so the event and the mutation are atomic.
    # #VERIFY: tests/unit/test_node_edit.py::test_edit_records_event_without_prose.
    await record_event(
        ctx.session,
        Actor.from_principal(
            ctx.principal, acting_role=str(ctx.principal.acting_role(book.family_id))
        ),
        entity_type="storybook_version",
        entity_id=f"{storybook_id}:{version}",
        event_type=EventType.NODE_EDITED,
        payload={"node_id": node_id},
    )

    floor = (
        await load_admin_noise_floor(ctx.session) if ctx.principal.is_admin else None
    )
    return build_review_surface(
        status=book.status,
        storybook_id=storybook_id,
        version=version,
        blob=new_blob,
        moderation_report=refreshed_report,
        admin_noise_floor=floor,
        # The gate re-ran above (`gate_result`) and the SAME serialized report
        # was assigned to `version_row.validation_report` a few lines up; reuse
        # that exact object so the refreshed surface's validator findings
        # reflect this edit immediately, not the pre-edit stored value, and so
        # the response can never disagree with what was just persisted.
        validation_report=validation_report,
    )
