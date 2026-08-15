"""Harness-level reading-level repair: measure, re-prompt, re-measure, re-gate.

Why this exists in the harness rather than in the prompt
--------------------------------------------------------
Every stage prompt already states a Flesch-Kincaid target, and stating it does
not work. ``AL-288`` measured six books written to an explicit "FK 4-6" target:
five of the six cleared the band's 7.0 upper edge anyway. The cause is not a
weak instruction, it is that **a language model cannot count syllables**, so it
cannot evaluate the constraint it is being given and cannot tell whether it has
met it.

``AL-292`` is the paired control. Two authors, same prompt, same target: the one
who instrumented reading level in the harness reached whole-book FK 5.12 with
84% of nodes in band, the one who did not reached FK 8.35 with 11%. What closed
the gap was measuring and re-prompting, not asking more firmly.

So this module supplies the loop the model cannot run for itself: it measures
each node with the deterministic checker (``validator.reading_level``), sends
only the out-of-band bodies back for simplification, measures the replies, and
keeps a revision **only when the measurement improved**.

Where it sits
-------------
It is a separate stage that runs after the structural and Stage 1 fidelity loop
in :mod:`cyo_adventure.generation.orchestrator` has converged, with its own
budget. It is deliberately NOT folded into that loop: ``_gate_signature`` there
filters to ERROR findings precisely so that a prose-only edit cannot change the
no-progress signature and defeat the abort, and RL-13 findings are WARNING and
embed the computed score. Widening that filter would break a working control.
This loop gets a stronger abort instead (see ``_accept``): the score has to
actually improve, so it cannot spin.

What it will not do
-------------------
It never blocks. RL-13 stays advisory, because making it blocking is a product
decision with a catalog consequence: measured across the 22 books this
programme has produced, a blocking rule at grade 7.0 would reject 9 of them
(see ``scripts/check_reading_level.py``). This loop lowers the score before the
gate ever sees it, which is the outcome that decision was about anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.prompts import build_reading_level_repair_prompt
from cyo_adventure.storybook.models import NarrativeStyle
from cyo_adventure.storybook.sentinels import find_sentinels
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.policy import node_word_count, words_per_node_profile
from cyo_adventure.validator.reading_level import (
    _UPPER_BOUND_ONLY_BANDS,
    BookReadingLevel,
    measure_book,
    score_body,
)
from cyo_adventure.validator.report import Severity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.generation.guarded import PiiGuardedProvider
    from cyo_adventure.validator.gate import GateResult
    from cyo_adventure.validator.layer1 import Scale

__all__ = [
    "ReadingLevelContext",
    "ReadingLevelResult",
    "run_reading_level_loop",
]

_logger = get_logger(__name__)

# Nodes per provider call. A 101-node book with 85 out-of-band nodes costs 8
# calls per pass at this size rather than 85. Sized to stay well inside output
# limits: 12 bodies at the ~250-word ceiling is roughly 4k output tokens.
_BATCH_SIZE = 12

# Output ceiling for one batch. Bodies come back at roughly their input length,
# so this is sized off _BATCH_SIZE rather than off the whole story.
_MAX_TOKENS_BATCH = 8192

# A revision may drift this far from the original word count. Splitting one long
# sentence into two short ones barely moves the count, so a large move means the
# model rewrote rather than simplified, and the original body was written to a
# word-count target (PL-19 / the FILL directive) that still applies.
_WORD_DRIFT_TOLERANCE = 0.10

# An unfilled authoring directive must never come back from a simplification.
_FILL_MARKER = "<<FILL"


@dataclass(slots=True)
class ReadingLevelContext:
    """Grouped parameters for the reading-level stage.

    Not frozen: ``stage_log`` is mutated in place (appended to). This mirrors
    :class:`~cyo_adventure.generation.orchestrator._RepairContext`, which exists
    for the same reason, to keep the entry point under the argument-count limit.

    Attributes:
        provider (PiiGuardedProvider): The PII-guarded generation provider. The type is not a
            convenience: requiring the guarded wrapper here is what makes PII
            enforcement structural rather than a rule someone has to remember.
        max_passes (int): Maximum repair passes. Each pass is one round of batched
            calls over whatever is still out of band. ``0`` disables the stage.
        stage_log (list[str]): The orchestrator's stage log; entries are appended in place.
        scale (Scale): Story-size profile forwarded to the post-splice gate re-run, so
            L1-7 is re-checked against the same budget as before.
    """

    provider: PiiGuardedProvider
    max_passes: int
    stage_log: list[str]
    scale: Scale = "standard"


@dataclass(frozen=True, slots=True)
class _Bounds:
    """The three limits a revision is accepted against.

    Grouped into one value object because they always travel together and
    because passing them individually pushed :func:`_run_batch` over the
    argument-count limit.

    Attributes:
        target (float): Target Flesch-Kincaid grade.
        tolerance (float): Half-width of the acceptable band.
        per_node_max (int | None): PL-19's absolute words-per-node wall, or
            ``None`` when the band declares no profile.
        upper_bound_only (bool): Whether this band treats only the upper edge
            as a defect. At 3-5 and 5-8 prose too easy for the reader is the
            product working, and FK is extrapolating below zero there, so the
            loop must not drive a node upward to reach a target
            (`AL-389`, `_UPPER_BOUND_ONLY_BANDS`).
    """

    target: float
    tolerance: float
    per_node_max: int | None
    upper_bound_only: bool = False


@dataclass(frozen=True, slots=True)
class ReadingLevelResult:
    """The outcome of the reading-level repair stage.

    Attributes:
        doc (dict[str, object]): The document after repair. Identical to the input document when
            nothing was accepted, or when the spliced result failed the gate
            and the whole pass was discarded.
        gate (GateResult): The gate result for ``doc``. Re-run only when a revision was
            accepted; otherwise the caller's original result, unchanged.
        before (BookReadingLevel | None): The whole-book measurement before repair, or ``None`` when the
            book held too little prose to score.
        after (BookReadingLevel | None): The whole-book measurement after repair. Equal to ``before``
            when nothing was accepted.
        nodes_revised (int): How many node bodies were replaced.
        passes (int): How many repair passes ran (0 when everything was already in
            band, so no provider call was made).
        discarded_for_gate (bool): ``True`` when revisions were accepted per-node, the
            spliced document then failed the gate, and no subset of the pass
            could be salvaged, so everything was rolled back. Rare, but not the
            impossibility this once claimed: the gate reads node bodies as well
            as the graph (PL-19's word wall among them), so a body-only edit can
            block it. Run-6 hit exactly that. Worth an alert.
        nodes_dropped (int): How many accepted revisions the salvage path threw
            away to get the rest past the gate. Non-zero means the book shipped
            with the repair only partly applied, which reads identically to a
            fully repaired book everywhere else in the artifact. Distinct from
            ``discarded_for_gate``, which is the all-or-nothing case; a book can
            be partly degraded without being discarded, and `AL-350` is what it
            costs when neither number leaves this dataclass.
    """

    doc: dict[str, object]
    gate: GateResult
    before: BookReadingLevel | None
    after: BookReadingLevel | None
    nodes_revised: int
    passes: int
    discarded_for_gate: bool
    nodes_dropped: int = 0

    def to_report(self) -> dict[str, object]:
        """Render the measurement for the generation outcome's report dict.

        Returns:
            dict[str, object]: A JSON-serialisable summary. ``None``
                measurements render as ``None`` rather than being omitted, so a
                book that could not be scored is visibly unscored rather than
                silently absent.
        """

        def _level(level: BookReadingLevel | None) -> dict[str, object] | None:
            if level is None:
                return None
            return {
                "grade": round(level.grade, 2),
                "in_band": round(level.in_band, 3),
                "nodes": level.nodes,
                "scored_nodes": level.scored_nodes,
            }

        return {
            "before": _level(self.before),
            "after": _level(self.after),
            "nodes_revised": self.nodes_revised,
            "passes": self.passes,
            "discarded_for_gate": self.discarded_for_gate,
            "nodes_dropped": self.nodes_dropped,
            "degraded": self.degraded,
        }

    @property
    def degraded(self) -> bool:
        """Whether this stage did less than it was asked to.

        One flag for the two ways Stage D can under-deliver, so a consumer that
        wants to exclude or flag affected books has a single field to read
        rather than a rule to reimplement.

        Returns:
            bool: ``True`` when the pass was discarded outright or any accepted
                revision was dropped to get the rest past the gate.
        """
        return self.discarded_for_gate or self.nodes_dropped > 0


def _is_upper_bound_only(doc: dict[str, object]) -> bool:
    """Return whether this story's band treats only the upper edge as a defect.

    Reads the same constant RL-13 reads, rather than repeating the band list,
    so the gate and the loop that feeds it cannot drift apart about which
    direction counts as a defect.

    Args:
        doc: The story document.

    Returns:
        bool: ``True`` at 3-5 and 5-8, ``False`` elsewhere and for a document
        declaring no band, since an unknown band gets the stricter two-sided
        treatment rather than the looser one.
    """
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        return False
    band = cast("dict[str, object]", meta).get("age_band")
    return isinstance(band, str) and band in _UPPER_BOUND_ONLY_BANDS


def _band(doc: dict[str, object]) -> tuple[float, float] | None:
    """Read the target grade and tolerance out of a story document.

    Args:
        doc (dict[str, object]): The raw story JSON.

    Returns:
        tuple[float, float] | None: A ``(target, tolerance)`` pair, or ``None``
            when the document declares no reading level (in which case there is
            no band to repair toward).
    """
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        return None
    level = cast("dict[str, object]", metadata).get("reading_level")
    if not isinstance(level, dict):
        return None
    target = cast("dict[str, object]", level).get("target")
    tolerance = cast("dict[str, object]", level).get("tolerance")
    # bool is a subclass of int; a JSON `true` here is malformed metadata, not
    # a target of 1.0, so it must not silently become one.
    if isinstance(target, bool) or isinstance(tolerance, bool):
        return None
    if not isinstance(target, (int, float)) or not isinstance(tolerance, (int, float)):
        return None
    return float(target), float(tolerance)


def _per_node_cap(doc: dict[str, object]) -> int | None:
    """Read PL-19's absolute words-per-node wall for this story's band.

    The loop's own acceptance rule bounds word drift *relatively* (10 percent
    of the original body), but PL-19 is an *absolute* ceiling. A relative guard
    cannot enforce an absolute bound, so a node already sitting near the wall
    can be pushed over it by a revision that every other acceptance test
    approves, and the whole spliced pass is then rejected by the gate. Reading
    a simplification pass makes this the likely direction rather than a remote
    one: shortening sentences to lower a grade adds words.

    Args:
        doc (dict[str, object]): The raw story JSON.

    Returns:
        int | None: The per-node maximum word count, or ``None`` when the
            document declares no band and style pair the profile table knows.
    """
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        return None
    meta = cast("dict[str, object]", metadata)
    band = meta.get("age_band")
    if not isinstance(band, str):
        return None
    # `narrative_style` is optional in the schema and most documents omit it, so
    # mirroring Storybook's own default is what makes the wall apply to the
    # ordinary book rather than only to the rare one that spells the field out.
    style = meta.get("narrative_style")
    if not isinstance(style, str):
        style = NarrativeStyle.PROSE.value
    profile = words_per_node_profile(band, style)
    if profile is None:
        return None
    return profile[3]


def _bodies(doc: dict[str, object]) -> list[tuple[str, str]]:
    """Extract ``(node_id, body)`` pairs from a story document.

    Args:
        doc (dict[str, object]): The raw story JSON.

    Returns:
        list[tuple[str, str]]: Every node carrying a string id and a string
            body, in document order. Malformed entries are skipped rather than
            raising: this stage is advisory and must never be the thing that
            fails a generation.
    """
    raw_nodes = doc.get("nodes")
    if not isinstance(raw_nodes, list):
        return []
    pairs: list[tuple[str, str]] = []
    for entry in cast("list[object]", raw_nodes):
        if not isinstance(entry, dict):
            continue
        node = cast("dict[str, object]", entry)
        node_id = node.get("id")
        body = node.get("body")
        if isinstance(node_id, str) and isinstance(body, str):
            pairs.append((node_id, body))
    return pairs


def _preserves_contract(original: str, revised: str) -> bool:
    """Check that a revision kept everything the original body promised.

    Each condition is a way a "simplification" can silently damage the book:

    * a returned ``<<FILL`` directive would un-author the node, turning
      finished prose back into an authoring marker;
    * a dropped or altered ``{~SLOT:Word~}`` sentinel breaks personalisation
      downstream, where it surfaces as a corrupt name in a child's book;
    * a large word-count move means the model rewrote rather than simplified,
      and the body was written to a word-count target (PL-19 and its FILL
      directive) that still applies.

    Args:
        original (str): The current node body.
        revised (str): The proposed replacement.

    Returns:
        bool: ``True`` when the revision may be considered on its merits.
    """
    if _FILL_MARKER in revised:
        return False
    if find_sentinels(revised) != find_sentinels(original):
        return False
    original_words = len(original.split())
    if original_words:
        drift = abs(len(revised.split()) - original_words) / original_words
        if drift > _WORD_DRIFT_TOLERANCE:
            return False
    return True


def _accept(original: str, revised: object, *, bounds: _Bounds) -> str | None:
    """Decide whether one revised body may replace its original.

    This is the loop's safety boundary and its convergence rule at once: a
    revision must be well-formed, must preserve what the original promised
    (:func:`_preserves_contract`), must stay inside PL-19's absolute word wall,
    must be scorable, and must land strictly closer to ``target`` than what it
    replaces.

    That last condition is what makes the loop terminate. Because acceptance is
    strictly monotone in ``|grade - target|``, repeated passes cannot oscillate
    and cannot spin on an unchanged reply. It is a stronger abort than the
    structural loop's signature comparison, which stops only on an output that
    is byte-identical AND carries identical findings.

    Args:
        original (str): The current node body.
        revised (object): The model's proposed replacement, untrusted and
            untyped.
        bounds (_Bounds): The target, the PL-19 wall, and whether this band
            treats only the upper edge as a defect. At 3-5 and 5-8 acceptance
            is one-sided: only revisions that LOWER the grade are taken. The
            symmetric rule would happily raise a node to reach its target, and
            with an accurate syllable counter it would, since `AL-389` measured
            the corrected counter reading the corpus 0.27 grades lower. A loop
            chasing an unchanged target would then push young-band prose harder
            than the prose humans have already approved.

    Returns:
        str | None: The revised body when it is a strict improvement, else
            ``None``.
    """
    if not isinstance(revised, str) or not revised.strip():
        return None
    if not _preserves_contract(original, revised):
        return None
    # #CRITICAL: data-integrity: PL-19 is an absolute ceiling and
    # _preserves_contract's drift bound is relative, so the drift check alone
    # cannot keep a near-wall node under the wall. Accepting a revision the
    # gate will reject costs the whole pass, not just this node. Measured on
    # run-6: one node at 147 words against a 155-word wall discarded 50 revised
    # nodes and shipped the book at grade 5.61 with 12 percent of nodes in band.
    # #VERIFY: test_reading_level_rejects_a_revision_that_would_breach_the_word_cap.
    per_node_max = bounds.per_node_max
    if per_node_max is not None and node_word_count(revised) > per_node_max:
        return None
    before = score_body(original)
    after = score_body(revised)
    if before is None or after is None:
        # An unscorable result cannot be shown to be better than what it
        # replaces, so it is not taken.
        return None
    return revised if _is_improvement(before, after, bounds) else None


def _is_improvement(before: float, after: float, bounds: _Bounds) -> bool:
    """Return whether *after* is a strict improvement on *before*.

    Two rules, because the bands disagree about what counts as worse. The
    symmetric rule moves a node toward its target from either side. The
    one-sided rule, used at 3-5 and 5-8, only ever simplifies: at those bands
    reading too easy is not a defect (`AL-389`), so raising a grade to reach a
    target is a regression dressed as convergence.

    Termination holds under both. The symmetric form is strictly monotone in
    the distance to target; the one-sided form is strictly monotone in the
    grade itself, and the selector stops offering a node once it is under the
    ceiling.

    Args:
        before: The original body's grade.
        after: The revision's grade.
        bounds: The band's acceptance rule.

    Returns:
        bool: ``True`` when the revision may be taken.
    """
    if bounds.upper_bound_only:
        return after < before
    return abs(after - bounds.target) < abs(before - bounds.target)


def _parse_revisions(raw: str | None) -> dict[str, object]:
    """Parse the model's ``{node_id: body}`` reply, or return an empty mapping.

    Args:
        raw (str | None): The provider's completion text.

    Returns:
        dict[str, object]: The decoded mapping, or ``{}`` for any reply that is
            not a JSON object.
        An unparseable reply costs this batch and nothing else: the caller
        keeps every original body and the run continues.
    """
    if raw is None:
        return {}
    try:
        parsed: object = json.loads(raw)  # pyright: ignore[reportAny]
    except (json.JSONDecodeError, RecursionError):
        # #EDGE: data-integrity: a deeply nested reply raises RecursionError
        # rather than JSONDecodeError under CPython 3.14, and whether it fires
        # depends on the executing thread's stack budget. Caught here for the
        # same reason orchestrator._run_one_stage catches it.
        # #VERIFY: test_reading_level_unparseable_reply_keeps_originals.
        return {}
    if not isinstance(parsed, dict):
        return {}
    return cast("dict[str, object]", parsed)


async def _run_batch(
    batch: Sequence[tuple[str, str, float]],
    *,
    provider: PiiGuardedProvider,
    bounds: _Bounds,
) -> dict[str, str]:
    """Simplify one batch of nodes and return only the accepted revisions.

    Args:
        batch (Sequence[tuple[str, str, float]]): ``(node_id, body,
            current_grade)`` for the nodes in this batch.
        provider (PiiGuardedProvider): The PII-guarded generation provider.
        bounds (_Bounds): The band and the PL-19 wall this pass accepts against.

    Returns:
        dict[str, str]: A mapping of node id to accepted revised body. Ids the
            model invented, and revisions that failed :func:`_accept`, are
            absent.
    """
    # #CRITICAL: security: the prompt carries node prose descended from an
    # untrusted brief, so it MUST go through the PII guard exactly like every
    # other generation call. The guard is structural: `provider` is already a
    # PiiGuardedProvider, and it screens both blocks before the real backend.
    # #VERIFY: run_reading_level_loop's signature requires PiiGuardedProvider,
    # and test_reading_level_pii_guard_aborts_before_any_egress asserts the guard
    # aborts before any completion when a body would leak a real child name.
    # #CRITICAL: external-resource: this is a network LLM call. A provider
    # outage propagates to the caller for rollback and RQ retry, exactly as in
    # moderation/repair.py; only an unparseable body degrades to "no revisions".
    # #VERIFY: only json.JSONDecodeError/RecursionError are caught, in
    # _parse_revisions; provider errors are not caught here.
    prompt = build_reading_level_repair_prompt(
        batch, target=bounds.target, tolerance=bounds.tolerance
    )
    # Stage D needs no metering code of its own: the caller wraps the provider
    # before handing it in, so these calls are recorded by the same
    # MeteredProvider layer as Stage 1 and land in the run's usage ledger.
    completion = await provider.complete(
        system=prompt.system,
        prompt=prompt.user,
        max_tokens=_MAX_TOKENS_BATCH,
    )
    revisions = _parse_revisions(completion.text)

    sent = {node_id: body for node_id, body, _grade in batch}
    accepted: dict[str, str] = {}
    for node_id, proposed in revisions.items():
        original = sent.get(node_id)
        if original is None:
            # #ASSUME: data-integrity: a node id the batch did not contain is a
            # hallucination or a mis-keyed reply. Splicing it would write prose
            # into an unrelated node, or create one.
            # #VERIFY: test_reading_level_unknown_node_id_is_ignored.
            continue
        good = _accept(original, proposed, bounds=bounds)
        if good is not None:
            accepted[node_id] = good
    return accepted


def _drop_offenders(
    accepted: dict[str, str], gate: GateResult
) -> dict[str, str] | None:
    """Return ``accepted`` without the nodes the blocked gate named.

    Args:
        accepted (dict[str, str]): The revisions the per-node rule took this
            pass.
        gate (GateResult): The blocked gate result for the spliced document.

    Returns:
        dict[str, str] | None: The surviving revisions, or ``None`` when the
            gate named no node in ``accepted`` (a story-level finding, so there
            is nothing to drop) or named all of them (nothing would survive).
    """
    offenders = {
        finding.node_id
        for finding in gate.report.findings
        if finding.severity is Severity.ERROR and finding.node_id in accepted
    }
    if not offenders or len(offenders) == len(accepted):
        return None
    return {
        node_id: body for node_id, body in accepted.items() if node_id not in offenders
    }


def _splice(doc: dict[str, object], revisions: dict[str, str]) -> dict[str, object]:
    """Return a copy of ``doc`` with the given node bodies replaced.

    Only the ``nodes`` list and the revised node dicts are rebuilt; every other
    part of the document is carried over by reference, so the graph cannot
    change. That is not the same as the gate re-run being a formality: several
    blocking rules are computed *from* body text, so a body-only splice can
    still fail it. The re-run is load-bearing.

    Args:
        doc (dict[str, object]): The story document.
        revisions (dict[str, str]): Mapping of node id to its new body.

    Returns:
        dict[str, object]: A new document dict with the revisions applied.
    """
    raw_nodes = doc.get("nodes")
    if not isinstance(raw_nodes, list):
        return doc
    rebuilt: list[object] = []
    for entry in cast("list[object]", raw_nodes):
        if not isinstance(entry, dict):
            rebuilt.append(entry)
            continue
        node = cast("dict[str, object]", entry)
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id in revisions:
            rebuilt.append({**node, "body": revisions[node_id]})
        else:
            rebuilt.append(node)
    return {**doc, "nodes": rebuilt}


async def run_reading_level_loop(
    doc: dict[str, object],
    gate_result: GateResult,
    ctx: ReadingLevelContext,
) -> ReadingLevelResult:
    """Drive the measure, re-prompt, re-measure, re-gate loop over a story.

    Makes no provider call at all when every scorable node already sits inside
    the band, which is the common case for a short story and the reason this
    stage is cheap to leave enabled.

    Args:
        doc (dict[str, object]): The story document to repair, after the
            structural and Stage 1 loops have converged.
        gate_result (GateResult): That document's current gate result.
        ctx (ReadingLevelContext): Grouped provider, budget, scale, and stage
            log.

    Returns:
        ReadingLevelResult: On every failure path it carries the untouched
            input document and the caller's original gate result, because an
            advisory stage must never be able to worsen a generation.
    """
    band = _band(doc)
    pairs = _bodies(doc)
    if ctx.max_passes <= 0 or band is None or not pairs:
        return ReadingLevelResult(
            doc=doc,
            gate=gate_result,
            before=None,
            after=None,
            nodes_revised=0,
            passes=0,
            discarded_for_gate=False,
        )
    target, tolerance = band
    bounds = _Bounds(
        target=target,
        tolerance=tolerance,
        per_node_max=_per_node_cap(doc),
        upper_bound_only=_is_upper_bound_only(doc),
    )
    before = measure_book(
        (body for _id, body in pairs), target=target, tolerance=tolerance
    )

    accepted: dict[str, str] = {}
    current = dict(pairs)
    passes = 0
    for _pass_index in range(ctx.max_passes):
        out_of_band = [
            (node_id, body, grade)
            for node_id, body in current.items()
            if (grade := score_body(body)) is not None
            and (
                grade > target + tolerance
                or (grade < target - tolerance and not bounds.upper_bound_only)
            )
        ]
        if not out_of_band:
            break
        passes += 1
        pass_accepted: dict[str, str] = {}
        for start in range(0, len(out_of_band), _BATCH_SIZE):
            batch = out_of_band[start : start + _BATCH_SIZE]
            pass_accepted.update(
                await _run_batch(batch, provider=ctx.provider, bounds=bounds)
            )
        ctx.stage_log.append(f"reading_level:{passes}:{len(pass_accepted)}")
        if not pass_accepted:
            # No node improved this pass. Because acceptance is strictly
            # monotone, another identical pass cannot do better.
            ctx.stage_log.append("reading_level:no_progress_abort")
            break
        accepted.update(pass_accepted)
        current.update(pass_accepted)

    if not accepted:
        return ReadingLevelResult(
            doc=doc,
            gate=gate_result,
            before=before,
            after=before,
            nodes_revised=0,
            passes=passes,
            discarded_for_gate=False,
        )

    revised_doc = _splice(doc, accepted)
    # #CRITICAL: data-integrity: a repaired document's structure is re-proven,
    # never merely trusted, before it replaces the pre-repair one. This mirrors
    # moderation/pipeline.py, which re-runs run_gate on an adopted repair for
    # the same reason. This branch was once annotated as unfalsifiable, on the
    # reasoning that the model never sees the graph and can only return body
    # strings. That reasoning was wrong and run-6 falsified it: blocking rules
    # including PL-19's word wall are computed FROM body text, so "cannot change
    # the graph" does not imply "cannot fail the gate".
    # #VERIFY: the salvage path is driven through the REAL gate, with no
    # patching, by the one-capped-node test; the unsalvageable path is covered
    # by the whole-pass discard test. Both live in test_reading_level_loop.py.
    revised_gate = run_gate(revised_doc, ctx.scale, context="fill_result")
    if revised_gate.blocked and not gate_result.blocked:
        # The gate names the nodes it objected to, so a single unusable
        # revision need not cost the rest of the pass. Drop the named nodes,
        # re-splice, and let the gate rule on the remainder; the re-run is the
        # authority on whether the salvage worked, so nothing here has to
        # reimplement which rules block.
        salvaged = _drop_offenders(accepted, revised_gate)
        if salvaged:
            salvaged_doc = _splice(doc, salvaged)
            salvaged_gate = run_gate(salvaged_doc, ctx.scale, context="fill_result")
            if not salvaged_gate.blocked:
                _logger.warning(
                    "reading_level_repair_partially_discarded",
                    nodes_revised=len(salvaged),
                    nodes_dropped=len(accepted) - len(salvaged),
                    reason="some revisions failed the structural gate",
                )
                ctx.stage_log.append("reading_level:gate_regression_partial")
                return ReadingLevelResult(
                    doc=salvaged_doc,
                    gate=salvaged_gate,
                    before=before,
                    after=measure_book(
                        (body for _id, body in _bodies(salvaged_doc)),
                        target=target,
                        tolerance=tolerance,
                    ),
                    nodes_revised=len(salvaged),
                    passes=passes,
                    discarded_for_gate=False,
                    nodes_dropped=len(accepted) - len(salvaged),
                )
        _logger.warning(
            "reading_level_repair_discarded",
            nodes_revised=len(accepted),
            reason="spliced document failed the structural gate",
        )
        ctx.stage_log.append("reading_level:gate_regression_discard")
        return ReadingLevelResult(
            doc=doc,
            gate=gate_result,
            before=before,
            after=before,
            nodes_revised=0,
            passes=passes,
            discarded_for_gate=True,
            nodes_dropped=len(accepted),
        )

    after = measure_book(
        (body for _id, body in _bodies(revised_doc)),
        target=target,
        tolerance=tolerance,
    )
    return ReadingLevelResult(
        doc=revised_doc,
        gate=revised_gate,
        before=before,
        after=after,
        nodes_revised=len(accepted),
        passes=passes,
        discarded_for_gate=False,
    )
