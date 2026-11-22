"""The plan reviewer's pure core (WP-3.7, owner decisions D11 and D12).

A *plan reviewer* is a model, different from the one that wrote a Story Plan,
that reads the plan and answers ``pass``, ``reject`` or ``unsure`` with reasons
that name plan entries. This module holds everything about that stage that
needs no network and no clock: the verdict model and its defensive parser, the
independence rule, the combination of two runs, the authority of the
deterministic checker over the reviewer, the seeded exception sample, the
suspension rule, the validated-pairing record and its refusal, and the two
renderers that decide what the model is allowed to see (the book graph without
prose, and the plan without its notes). The provider call is
:mod:`cyo_adventure.moderation.plan_reviewer`; the prompt is
``generation/templates/plan_review.md``.

Design rules, each pinned by ``tests/unit/test_plan_review.py``:

* **A parse failure is never a pass.** Bad JSON, a truncated answer (a
  ``length`` finish, AL-823), an unknown verdict, a provider error: all are
  ``unsure`` with a recorded reason code. The reviewer fails closed.
* **Reasons name entries and never quote story text.** A finding carries one
  plan entry id (a node, choice, fact, thread or ending), a defect class, a
  severity and a short reason. A reason is scrubbed on the way in (a long
  quoted span is replaced; control characters and the em dash are removed;
  length is capped). The reasons this module generates itself are machine
  codes built from rule ids and entry ids, never from model output.
* **The checker has authority.** A ``pass`` is allowed only if the
  deterministic checks (SP-0 to SP-9) reported no ERROR. If they did, the
  combined verdict is forced to ``reject`` and marked ``checker_caught``. The
  reviewer never overrides the checker.
* **Two runs, disagreement is ``unsure``.** Identical verdicts keep the
  verdict; any disagreement is ``unsure``; the union of the findings is kept.
* **A different model.** :func:`assert_independent` refuses the same model id
  and the same vendor and family where the project can tell. A family is a
  vendor plus the model name with its version tokens removed
  (``claude-sonnet-5.5`` and ``claude-sonnet-4.6`` share one), which is
  deliberately conservative: a different generation of the same family is not
  treated as independent.

Deviations from the WP-3.7 design, recorded here as the plan asks: the
renderer :func:`plan_for_review` removes ``provenance.approver`` and
``provenance.checks`` as well as ``provenance.notes`` (an earlier verdict or a
check summary would anchor the reviewer), and moves the whole ``request``
object out of the plan body into the fenced untrusted block, so request text
appears once, fenced. Lists that are empty and fields that are unset are
omitted from the rendered plan to save input tokens; the prompt says a missing
list is empty.

This module is pure: no I/O, no network, no clock.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence

    from cyo_adventure.storybook.models import Effect, Storybook

__all__ = [
    "ADVISORY_CLASSES",
    "AUTHORITATIVE_CLASSES",
    "DEFAULT_SAMPLE_SEED",
    "FINDING_CLASSES",
    "MAX_FINDINGS",
    "SAMPLE_WINDOW",
    "SEVERITIES",
    "UNVALIDATED",
    "CheckerSummary",
    "PlanReview",
    "PlanVerdict",
    "ReviewFinding",
    "SampleDraw",
    "SampledPass",
    "SuspensionDecision",
    "ValidatedPairing",
    "apply_checker_authority",
    "assert_independent",
    "assert_reviewer_usable",
    "combine_runs",
    "draw_sample",
    "evaluate_suspension",
    "format_validated_pairing",
    "model_family",
    "parse_plan_verdict",
    "parse_validated_pairing",
    "plan_content_hash",
    "plan_entry_ids",
    "plan_for_review",
    "render_book_graph",
    "reviewer_refusal",
    "scrub_reason",
    "unsure_verdict",
]

Verdict = Literal["pass", "reject", "unsure"]
Severity = Literal["blocker", "should-fix", "minor"]

SEVERITIES: Final[tuple[Severity, ...]] = ("blocker", "should-fix", "minor")
VERDICTS: Final[tuple[Verdict, ...]] = ("pass", "reject", "unsure")
_VERDICT_BY_TEXT: Final[dict[str, Verdict]] = {v: v for v in VERDICTS}

AUTHORITATIVE_CLASSES: Final[tuple[str, ...]] = (
    "label_outcome_mismatch",
    "truth_contradiction",
    "ending_gift_mismatch",
    "payoff_shows_mismatch",
    "state_contradiction",
)
"""Defect classes the reviewer is measured on (the synthetic family B classes
and the answer key's state class). D12 gives authority only to classes with
measured recall."""

ADVISORY_CLASSES: Final[tuple[str, ...]] = (
    "agency_or_cost",
    "request_fidelity",
    "band_suitability",
    "dull_or_generic",
    "other",
)
"""Classes with no measured recall (no labelled data): their findings are
reported and never authoritative (D12, scope of authority)."""

FINDING_CLASSES: Final[tuple[str, ...]] = AUTHORITATIVE_CLASSES + ADVISORY_CLASSES

MAX_FINDINGS: Final = 40
"""Findings kept from one answer; the prompt asks for at most 20."""

_MAX_REASON_CHARS: Final = 400
_MAX_ENTRY_CHARS: Final = 80
_QUOTE_MIN_CHARS: Final = 40
_OK_FINISH_REASONS: Final = frozenset({"stop", "end_turn", "<absent>"})

_EM_DASH: Final = chr(0x2014)
_LONG_QUOTE_RE: Final = re.compile(
    "|".join(
        (
            '"[^"]{' + str(_QUOTE_MIN_CHARS) + ',}"',
            chr(0x201C)
            + "[^"
            + chr(0x201D)
            + "]{"
            + str(_QUOTE_MIN_CHARS)
            + ",}"
            + chr(0x201D),
        )
    )
)
_CONTROL_RE: Final = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACE_RE: Final = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Verdict model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """One finding: a plan entry, a class, a severity and a short reason.

    Attributes:
        entry: One plan entry id (a node, choice, fact, thread or ending id).
        defect_class: One of :data:`FINDING_CLASSES`; an unknown class from the
            model becomes ``"other"``.
        severity: ``blocker``, ``should-fix`` or ``minor``.
        reason: A short reason, scrubbed by :func:`scrub_reason`.
        entry_known: False when the entry id is not in the plan, which the
            parser can only tell when it is given the plan's entry ids.
    """

    entry: str
    defect_class: str
    severity: Severity
    reason: str
    entry_known: bool = True

    @property
    def authoritative(self) -> bool:
        """Whether this finding's class is one the reviewer is measured on.

        Returns:
            bool: True for a member of :data:`AUTHORITATIVE_CLASSES`.
        """
        return self.defect_class in AUTHORITATIVE_CLASSES

    def to_dict(self) -> dict[str, object]:
        """Return the finding as a JSON-ready dict.

        Returns:
            dict[str, object]: The fields, with ``class`` as the key the model
                is asked to use.
        """
        return {
            "entry": self.entry,
            "class": self.defect_class,
            "severity": self.severity,
            "reason": self.reason,
            "entry_known": self.entry_known,
            "authoritative": self.authoritative,
        }


@dataclass(frozen=True, slots=True)
class PlanVerdict:
    """One reviewer answer, parsed.

    Attributes:
        verdict: ``pass``, ``reject`` or ``unsure``.
        confidence: The model's stated confidence in [0, 1], or None.
        findings: The findings, most serious first as the model gave them.
        reasons: Machine reason codes recorded by the parser or the combiner
            (for example ``finish_reason_length``); empty for a clean answer.
    """

    verdict: Verdict
    confidence: float | None
    findings: tuple[ReviewFinding, ...] = ()
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return the verdict as a JSON-ready dict.

        Returns:
            dict[str, object]: The fields.
        """
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "findings": [f.to_dict() for f in self.findings],
            "reasons": list(self.reasons),
        }


def unsure_verdict(*reasons: str) -> PlanVerdict:
    """Return an ``unsure`` verdict carrying reason codes.

    Args:
        *reasons: Machine reason codes (never model output).

    Returns:
        PlanVerdict: ``unsure``, no confidence, no findings.
    """
    return PlanVerdict(verdict="unsure", confidence=None, reasons=tuple(reasons))


def scrub_reason(value: object) -> str:
    """Make a model-written reason safe to store and print.

    The reviewer sees the plan and the graph, never the prose, so a long
    quotation in a reason is something it should not be producing; a quoted
    span of :data:`_QUOTE_MIN_CHARS` or more is replaced rather than kept.
    Control characters and the em dash are removed, whitespace is collapsed
    and the length is capped.

    Args:
        value: The raw ``reason`` value from the model's JSON.

    Returns:
        str: The scrubbed reason, empty when ``value`` is not a string.
    """
    if not isinstance(value, str):
        return ""
    text = _CONTROL_RE.sub(" ", value).replace(_EM_DASH, "-")
    text = _LONG_QUOTE_RE.sub("[quoted text removed]", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text[:_MAX_REASON_CHARS]


def _clean_entry(value: object) -> str | None:
    """Return a plan entry id from the model's ``entry`` value, or None.

    Args:
        value: A string, or a list whose first member is a string.

    Returns:
        str | None: The id, whitespace-collapsed and capped, or None when no
            usable id was given.
    """
    raw: object = value
    if isinstance(value, list):
        members = cast("list[object]", value)
        raw = members[0] if members else None
    if not isinstance(raw, str):
        return None
    entry = _SPACE_RE.sub(" ", _CONTROL_RE.sub(" ", raw)).strip()
    if not entry:
        return None
    return entry[:_MAX_ENTRY_CHARS]


def _coerce_finding(
    raw: object, known_entries: Collection[str] | None
) -> ReviewFinding | None:
    """Turn one entry of the model's ``findings`` list into a finding.

    Args:
        raw: The decoded list member.
        known_entries: The plan's entry ids, or None when not checked.

    Returns:
        ReviewFinding | None: The finding, or None when it names no entry.
    """
    if not isinstance(raw, dict):
        return None
    item = cast("dict[str, object]", raw)
    entry = _clean_entry(item.get("entry", item.get("entries")))
    if entry is None:
        return None
    raw_class = item.get("class", item.get("defect_class"))
    defect_class = (
        raw_class.strip().lower().replace("-", "_").replace(" ", "_")
        if isinstance(raw_class, str)
        else "other"
    )
    if defect_class not in FINDING_CLASSES:
        defect_class = "other"
    raw_severity = item.get("severity")
    severity: Severity = "should-fix"
    if isinstance(raw_severity, str) and raw_severity.strip().lower() in SEVERITIES:
        severity = cast("Severity", raw_severity.strip().lower())
    return ReviewFinding(
        entry=entry,
        defect_class=defect_class,
        severity=severity,
        reason=scrub_reason(item.get("reason", item.get("problem"))),
        entry_known=known_entries is None or entry in known_entries,
    )


def _decode_answer(text: str) -> dict[str, object] | None:
    """Decode the first JSON object in a model answer, or None.

    Args:
        text: The raw completion text, possibly fenced or wrapped in prose.

    Returns:
        dict[str, object] | None: The object, or None when there is none.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        decoded = cast("object", json.loads(text[start : end + 1]))
    except (json.JSONDecodeError, RecursionError):
        return None
    return cast("dict[str, object]", decoded) if isinstance(decoded, dict) else None


def _confidence(value: object) -> float | None:
    """Return a confidence in [0, 1], or None for anything else.

    Args:
        value: The raw ``confidence`` value.

    Returns:
        float | None: The number when it is a real in [0, 1].
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if 0.0 <= number <= 1.0 else None


def parse_plan_verdict(
    text: str | None,
    *,
    finish_reason: str | None,
    known_entries: Collection[str] | None = None,
) -> PlanVerdict:
    """Parse one reviewer answer, failing closed.

    Never raises on model output and never returns ``pass`` for an answer it
    could not fully trust: a finish other than a normal stop (``length`` is the
    AL-823 symptom, so it is never trusted and never retried here), an absent
    or undecodable object, an unknown verdict, or a ``pass`` that carries a
    blocker finding all give ``unsure``.

    Args:
        text: The completion text, or None when the provider returned none.
        finish_reason: The provider's finish reason (``"<absent>"`` or None
            when it reported none).
        known_entries: The plan's entry ids, used to mark findings that name
            an entry the plan does not have.

    Returns:
        PlanVerdict: The parsed answer, or ``unsure`` with a reason code.
    """
    reason = finish_reason if finish_reason is not None else "<absent>"
    if reason not in _OK_FINISH_REASONS:
        return unsure_verdict(f"finish_reason_{reason}")
    if text is None or not text.strip():
        return unsure_verdict("empty_answer")
    decoded = _decode_answer(text)
    if decoded is None:
        return unsure_verdict("unparseable_answer")
    raw_verdict = decoded.get("verdict")
    verdict = raw_verdict.strip().lower() if isinstance(raw_verdict, str) else ""
    if verdict not in VERDICTS:
        return unsure_verdict("unknown_verdict")
    raw_findings = decoded.get("findings", [])
    members = (
        cast("list[object]", raw_findings) if isinstance(raw_findings, list) else []
    )
    coerced = [_coerce_finding(m, known_entries) for m in members[:MAX_FINDINGS]]
    findings = tuple(f for f in coerced if f is not None)
    codes: list[str] = []
    if len(findings) < len(coerced):
        codes.append("finding_without_entry")
    if not isinstance(raw_findings, list):
        codes.append("findings_not_a_list")
    final: Verdict = _VERDICT_BY_TEXT[verdict]
    if final == "pass" and any(f.severity == "blocker" for f in findings):
        final = "unsure"
        codes.append("pass_with_blocker_finding")
    if final == "reject" and not findings:
        codes.append("reject_without_findings")
    return PlanVerdict(
        verdict=final,
        confidence=_confidence(decoded.get("confidence")),
        findings=findings,
        reasons=tuple(codes),
    )


# ---------------------------------------------------------------------------
# Two runs, then the checker's authority
# ---------------------------------------------------------------------------


def combine_runs(runs: Sequence[PlanVerdict]) -> PlanVerdict:
    """Combine the verdicts of two (or more) runs of one plan.

    Identical verdicts keep the verdict; any disagreement is ``unsure``. The
    findings of every run are kept, de-duplicated by entry, class and severity,
    and the confidence is the lowest stated. An empty sequence is ``unsure``.

    Args:
        runs: The parsed verdicts, one per run.

    Returns:
        PlanVerdict: The combined verdict.
    """
    if not runs:
        return unsure_verdict("no_runs")
    kinds = {run.verdict for run in runs}
    agreed = len(kinds) == 1
    seen: set[tuple[str, str, str]] = set()
    merged: list[ReviewFinding] = []
    for run in runs:
        for finding in run.findings:
            key = (finding.entry, finding.defect_class, finding.severity)
            if key not in seen:
                seen.add(key)
                merged.append(finding)
    codes: list[str] = []
    for run in runs:
        codes.extend(c for c in run.reasons if c not in codes)
    if not agreed:
        codes.append("runs_disagree")
    confidences = [r.confidence for r in runs if r.confidence is not None]
    return PlanVerdict(
        verdict=runs[0].verdict if agreed else "unsure",
        confidence=min(confidences) if confidences else None,
        findings=tuple(merged),
        reasons=tuple(codes),
    )


@dataclass(frozen=True, slots=True)
class CheckerSummary:
    """What the deterministic checks (SP-0 to SP-9) reported for a plan.

    Attributes:
        errors: The number of ERROR findings.
        warnings: The number of WARNING findings (SP-D is advisory).
        error_rules: The distinct rule ids of the ERROR findings, sorted.
    """

    errors: int
    warnings: int
    error_rules: tuple[str, ...] = ()

    @classmethod
    def from_rule_ids(
        cls, error_rule_ids: Iterable[str], *, warnings: int = 0
    ) -> CheckerSummary:
        """Build a summary from the rule id of each ERROR finding.

        Args:
            error_rule_ids: One rule id per ERROR finding.
            warnings: The WARNING count.

        Returns:
            CheckerSummary: The summary.
        """
        ids = list(error_rule_ids)
        return cls(
            errors=len(ids), warnings=warnings, error_rules=tuple(sorted(set(ids)))
        )


@dataclass(frozen=True, slots=True)
class PlanReview:
    """The final answer for one plan, after the checker's authority.

    Attributes:
        verdict: The verdict to act on.
        confidence: The combined confidence, or None.
        findings: The union of the findings of every run.
        reasons: Machine reason codes (parser, combiner, checker).
        run_verdicts: Each run's verdict before combination.
        checker_caught: True when the checks reported an ERROR, which forces
            ``reject``.
        reviewer_pass_overridden: True when the reviewer's combined verdict was
            ``pass`` and the checker forced a reject.
        reviewer_ran: False when the checker's ERROR meant no model was called.
    """

    verdict: Verdict
    confidence: float | None
    findings: tuple[ReviewFinding, ...]
    reasons: tuple[str, ...]
    run_verdicts: tuple[Verdict, ...]
    checker_caught: bool = False
    reviewer_pass_overridden: bool = False
    reviewer_ran: bool = True

    @property
    def flagged(self) -> bool:
        """Whether the plan goes to the owner: anything but a clean ``pass``.

        Returns:
            bool: True for ``reject`` and ``unsure``.
        """
        return self.verdict != "pass"

    def to_dict(self) -> dict[str, object]:
        """Return the review as a JSON-ready dict.

        Returns:
            dict[str, object]: The fields.
        """
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "findings": [f.to_dict() for f in self.findings],
            "reasons": list(self.reasons),
            "run_verdicts": list(self.run_verdicts),
            "checker_caught": self.checker_caught,
            "reviewer_pass_overridden": self.reviewer_pass_overridden,
            "reviewer_ran": self.reviewer_ran,
        }


def apply_checker_authority(
    combined: PlanVerdict | None,
    checker: CheckerSummary,
    *,
    run_verdicts: Sequence[Verdict] = (),
) -> PlanReview:
    """Apply the checker's authority to the reviewer's combined verdict.

    A ``pass`` is allowed only when the checks reported no ERROR. With an ERROR
    the verdict is ``reject``, marked ``checker_caught``, whatever the reviewer
    said (and whether or not a reviewer ran); if the reviewer had said
    ``pass`` that is recorded as ``reviewer_pass_overridden``. With a clean
    check the reviewer's combined verdict stands. A clean check and no reviewer
    result is ``unsure``: the reviewer is the only thing that can pass a plan.

    Args:
        combined: The combined verdict of the reviewer's runs, or None when no
            reviewer ran.
        checker: What the deterministic checks reported.
        run_verdicts: Each run's verdict before combination.

    Returns:
        PlanReview: The final answer.
    """
    # #CRITICAL: security: the model may be wrong or manipulated through the
    # request text; the deterministic checker is the one exact component. A
    # reviewer pass over a checker ERROR must never reach the worker.
    # #VERIFY: test_plan_review.py::test_a_pass_over_a_checker_error_is_forced_to_reject.
    if checker.errors > 0:
        codes = tuple(f"checker_error:{rule}" for rule in checker.error_rules)
        return PlanReview(
            verdict="reject",
            confidence=None if combined is None else combined.confidence,
            findings=() if combined is None else combined.findings,
            reasons=codes + (() if combined is None else combined.reasons),
            run_verdicts=tuple(run_verdicts),
            checker_caught=True,
            reviewer_pass_overridden=combined is not None
            and combined.verdict == "pass",
            reviewer_ran=combined is not None,
        )
    if combined is None:
        return PlanReview(
            verdict="unsure",
            confidence=None,
            findings=(),
            reasons=("reviewer_not_run",),
            run_verdicts=(),
            reviewer_ran=False,
        )
    return PlanReview(
        verdict=combined.verdict,
        confidence=combined.confidence,
        findings=combined.findings,
        reasons=combined.reasons,
        run_verdicts=tuple(run_verdicts),
    )


# ---------------------------------------------------------------------------
# What the reviewer may see
# ---------------------------------------------------------------------------

_DROPPED_PROVENANCE: Final = ("notes", "approver", "checks")


def plan_for_review(
    plan: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Split a plan into the body the reviewer reads and the fenced request.

    ``provenance.notes`` is removed because notes can carry continuity
    findings, and ``approver`` and ``checks`` because an earlier verdict or
    check summary would anchor the reviewer. The whole ``request`` object moves
    out of the body: it carries the guardian's or child's own words (OWASP
    LLM01) and is presented separately, inside the untrusted fence.

    Args:
        plan: The plan as a JSON-style mapping (for example
            ``StoryPlan.model_dump(mode="json", exclude_none=True,
            exclude_defaults=True)``). Not mutated.

    Returns:
        tuple[dict[str, object], dict[str, object]]: ``(body, request)``.
    """
    body = {k: v for k, v in plan.items() if k != "request"}
    provenance = body.get("provenance")
    if isinstance(provenance, dict):
        kept = {
            k: v
            for k, v in cast("dict[str, object]", provenance).items()
            if k not in _DROPPED_PROVENANCE
        }
        body["provenance"] = kept
    raw_request = plan.get("request")
    request = (
        dict(cast("dict[str, object]", raw_request))
        if isinstance(raw_request, dict)
        else {}
    )
    return body, request


def plan_entry_ids(plan: Mapping[str, object]) -> frozenset[str]:
    """Return every entry id a finding may name: nodes, choices, facts, threads, endings.

    Args:
        plan: The plan as a JSON-style mapping.

    Returns:
        frozenset[str]: The ids (cast ids included).
    """
    ids: set[str] = set()
    for section in ("nodes", "choices", "facts", "threads", "endings", "cast"):
        value = plan.get(section)
        if isinstance(value, dict):
            ids.update(cast("dict[str, object]", value))
    return frozenset(ids)


def plan_content_hash(plan: Mapping[str, object]) -> str:
    """Return the content hash the exception sample is seeded from.

    The hash ignores ``provenance.approver``, ``provenance.checks`` and
    ``provenance.notes``: the approver is written after the verdict, and a hash
    that moved when it was recorded would let the sample be re-rolled.

    Args:
        plan: The plan as a JSON-style mapping.

    Returns:
        str: ``sha256:<hex>`` of the canonical JSON of the plan without those
            fields.
    """
    body = dict(plan)
    provenance = body.get("provenance")
    if isinstance(provenance, dict):
        body["provenance"] = {
            k: v
            for k, v in cast("dict[str, object]", provenance).items()
            if k not in _DROPPED_PROVENANCE
        }
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return "sha256:" + hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _compact(value: object) -> str:
    """Render a value as compact ASCII JSON.

    Args:
        value: Any JSON-serializable value.

    Returns:
        str: The JSON text.
    """
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def _effect_text(effect: Effect) -> str:
    """Render one effect as a short token.

    Args:
        effect: The effect.

    Returns:
        str: For example ``set has_key=true`` or ``inc courage+1``.
    """
    once = " once" if effect.once else ""
    if effect.op.value == "set":
        value = _compact(effect.value)
        return f"set {effect.var}={value}{once}"
    sign = "+" if effect.op.value == "inc" else "-"
    return f"{effect.op.value} {effect.var}{sign}{effect.value}{once}"


def render_book_graph(book: Storybook) -> str:
    """Render the book's graph with no prose: ids, conditions, effects, endings.

    One line per choice (``node: choice -> target [if <condition>] [sets ...]``),
    one per node entry effect, one per ending (valence and kind). Node bodies,
    choice labels and ending titles are never included.

    Args:
        book: The parsed Storybook.

    Returns:
        str: The graph text.
    """
    lines = [f"start: {book.start_node}"]
    if book.variables:
        declared = [
            {
                "name": v.name,
                "type": v.type.value,
                "initial": v.initial,
                **({"min": v.min} if v.min is not None else {}),
                **({"max": v.max} if v.max is not None else {}),
            }
            for v in book.variables
        ]
        lines.append(f"variables: {_compact(declared)}")
    for node in book.nodes:
        if node.on_enter:
            entered = ", ".join(_effect_text(e) for e in node.on_enter)
            lines.append(f"{node.id}: on enter sets {entered}")
        if node.is_ending and node.ending is not None:
            valence, kind = node.ending.valence.value, node.ending.kind.value
            lines.append(f"{node.id}: ENDING valence={valence} kind={kind}")
        elif node.is_ending:
            lines.append(f"{node.id}: ENDING")
        elif not node.choices:
            lines.append(f"{node.id}: NO CHOICES")
        for choice in node.choices:
            text = f"{node.id}: {choice.id} -> {choice.target}"
            if choice.condition is not None:
                text += f" if {_compact(choice.condition)}"
            if choice.effects:
                text += " sets " + ", ".join(_effect_text(e) for e in choice.effects)
            lines.append(text)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Independence
# ---------------------------------------------------------------------------

_VERSION_TOKEN_RE: Final = re.compile(r"^v?\d+$")
_NOISE_TOKENS: Final = frozenset({"preview", "latest", "beta", "exp", "experimental"})
_VENDOR_BY_PREFIX: Final = (
    ("claude", "anthropic"),
    ("gpt", "openai"),
    ("gemini", "google"),
    ("deepseek", "deepseek"),
    ("grok", "x-ai"),
)


def _strip_route_and_variant(model_id: str) -> str:
    """Remove a route prefix (``openrouter:``) and a variant suffix (``:thinking``).

    Args:
        model_id: The lower-cased id.

    Returns:
        str: The bare ``vendor/model`` or ``model`` text.
    """
    text = model_id.removeprefix("~")
    for _ in range(2):
        if ":" not in text:
            break
        head, _, tail = text.partition(":")
        text = tail if "/" not in head else head
    return text


def model_family(model_id: str) -> tuple[str, str, tuple[str, ...]]:
    """Return ``(vendor, normalized name, family tokens)`` for a model id.

    A family is the model name with version tokens (digits, ``v4``, dates) and
    release-noise words removed, so ``anthropic/claude-sonnet-5.5`` and
    ``claude-sonnet-4-6`` share the family ``("claude", "sonnet")``. The vendor
    is the id's prefix, or inferred from a well-known name prefix for a bare id.

    Args:
        model_id: An OpenRouter-style ``vendor/model`` id or a bare model id.

    Returns:
        tuple[str, str, tuple[str, ...]]: The vendor (``""`` when unknown), the
            normalized name and the family tokens.
    """
    text = _strip_route_and_variant(model_id.strip().lower())
    vendor, _, name = text.rpartition("/")
    name = name.replace("_", "-").replace(".", "-")
    if not vendor:
        vendor = next((v for p, v in _VENDOR_BY_PREFIX if name.startswith(p)), "")
    tokens = tuple(
        t
        for t in name.split("-")
        if t and not _VERSION_TOKEN_RE.match(t) and t not in _NOISE_TOKENS
    )
    return vendor, name, tokens or (name,)


def assert_independent(writer_model: str | None, reviewer_model: str | None) -> None:
    """Refuse a reviewer that is not independent of the plan's writer.

    Refuses: an unknown writer or reviewer (the project cannot tell, so it
    fails closed), the same normalized model id, and the same vendor and model
    family.

    Args:
        writer_model: The model that wrote the plan, or None when unknown.
        reviewer_model: The model that will review it, or None when unset.

    Raises:
        BusinessLogicError: When either model is unknown, or the two are the
            same model or the same vendor and family. The rule is
            ``plan_reviewer_not_independent`` or
            ``plan_reviewer_model_unknown``.
    """
    # #CRITICAL: security: a model reviewing its own output shares its blind
    # spots, so a pass from it is not evidence (D11). The check is on configured
    # ids; it cannot see a router that substitutes one model for another.
    # #VERIFY: test_plan_review.py::TestIndependence, and the harness records
    # the model ids the provider reports on every call.
    if not writer_model or not reviewer_model:
        msg = "the plan reviewer needs both a writer model and a reviewer model"
        raise BusinessLogicError(msg, rule="plan_reviewer_model_unknown")
    w_vendor, w_name, w_family = model_family(writer_model)
    r_vendor, r_name, r_family = model_family(reviewer_model)
    if (w_vendor, w_name) == (r_vendor, r_name):
        msg = (
            f"the plan reviewer must differ from the writer; both are {writer_model!r}"
        )
        raise BusinessLogicError(
            msg,
            rule="plan_reviewer_not_independent",
            context={"writer": writer_model, "reviewer": reviewer_model},
        )
    if w_vendor == r_vendor and w_family == r_family:
        msg = (
            f"the plan reviewer {reviewer_model!r} is the same model family as "
            f"the writer {writer_model!r}"
        )
        raise BusinessLogicError(
            msg,
            rule="plan_reviewer_not_independent",
            context={"writer": writer_model, "reviewer": reviewer_model},
        )


# ---------------------------------------------------------------------------
# Exception sample and suspension
# ---------------------------------------------------------------------------

DEFAULT_SAMPLE_SEED: Final = "plan-review-sample-v1"
SAMPLE_WINDOW: Final = 10
_MIN_SAMPLED: Final = 5
_OVERTURN_NUMERATOR: Final = 1
_OVERTURN_DENOMINATOR: Final = 5
_DRAW_SPACE: Final = 2**32


@dataclass(frozen=True, slots=True)
class SampleDraw:
    """The recorded result of one exception-sample draw.

    Attributes:
        plan_id: What was drawn for (the plan's content hash in production).
        seed: The seed string; recorded so the draw is auditable.
        rate: The configured sample rate in [0, 1].
        draw: The deterministic draw in [0, 1).
        sampled: True when ``draw < rate``: the owner reads this plan.
    """

    plan_id: str
    seed: str
    rate: float
    draw: float
    sampled: bool

    def to_dict(self) -> dict[str, object]:
        """Return the draw as a JSON-ready dict.

        Returns:
            dict[str, object]: The fields.
        """
        return {
            "plan_id": self.plan_id,
            "seed": self.seed,
            "rate": self.rate,
            "draw": self.draw,
            "sampled": self.sampled,
        }


def draw_sample(
    plan_id: str, rate: float, *, seed: str = DEFAULT_SAMPLE_SEED
) -> SampleDraw:
    """Decide whether the owner reads a passing plan, deterministically.

    The draw is the first 32 bits of ``sha256("<seed>:<plan_id>")`` as a
    fraction of 2**32, so it is a pure function of the plan id and the seed: it
    is auditable and cannot be re-rolled. A rate of 0 never samples and a rate
    of 1 always does.

    Args:
        plan_id: The plan's content hash (any stable id in tests).
        rate: The sample rate in [0, 1] (1 in 10 is 0.1; the pilot is 1.0).
        seed: The recorded seed.

    Returns:
        SampleDraw: The recorded draw.

    Raises:
        ConfigurationError: When ``rate`` is not in [0, 1].
    """
    if not 0.0 <= rate <= 1.0:
        msg = f"the plan reviewer sample rate must be in [0, 1], got {rate}"
        raise ConfigurationError(msg)
    digest = hashlib.sha256(f"{seed}:{plan_id}".encode()).digest()
    draw = int.from_bytes(digest[:4], "big") / _DRAW_SPACE
    return SampleDraw(
        plan_id=plan_id, seed=seed, rate=rate, draw=draw, sampled=draw < rate
    )


@dataclass(frozen=True, slots=True)
class SampledPass:
    """One reviewer pass the owner read, for the suspension rule.

    Attributes:
        plan_id: The plan.
        owner_overturned: True when the owner judged the plan defective.
        blocker_class: True when the defect the owner found was a blocker.
    """

    plan_id: str
    owner_overturned: bool
    blocker_class: bool = False


@dataclass(frozen=True, slots=True)
class SuspensionDecision:
    """Whether the reviewer is suspended, and why.

    Attributes:
        suspended: True when the rule fires.
        reason: ``blocker_overturned``, ``overturn_rate`` or None.
        considered: How many sampled passes the rate was taken over.
        overturned: How many of those the owner overturned.
    """

    suspended: bool
    reason: str | None
    considered: int
    overturned: int

    def to_dict(self) -> dict[str, object]:
        """Return the decision as a JSON-ready dict, for the audit record.

        Returns:
            dict[str, object]: The fields.
        """
        return {
            "suspended": self.suspended,
            "reason": self.reason,
            "considered": self.considered,
            "overturned": self.overturned,
        }


def evaluate_suspension(history: Sequence[SampledPass]) -> SuspensionDecision:
    """Apply the D12 suspension rule to the sampled passes since validation.

    Suspended when the owner overturned any blocker-class pass, or when more
    than 1 in 5 of the last 10 sampled passes were overturned and at least 5
    were sampled. "More than 1 in 5" is strict: exactly 1 of 5 or 2 of 10 does
    not suspend; 2 of 5 or 3 of 10 does.

    Args:
        history: The sampled passes, oldest first, since the last validation.

    Returns:
        SuspensionDecision: The decision and the figures behind it.
    """
    window = list(history[-SAMPLE_WINDOW:])
    overturned = sum(1 for s in window if s.owner_overturned)
    if any(s.owner_overturned and s.blocker_class for s in history):
        return SuspensionDecision(
            suspended=True,
            reason="blocker_overturned",
            considered=len(window),
            overturned=overturned,
        )
    if (
        len(window) >= _MIN_SAMPLED
        and overturned * _OVERTURN_DENOMINATOR > len(window) * _OVERTURN_NUMERATOR
    ):
        return SuspensionDecision(
            suspended=True,
            reason="overturn_rate",
            considered=len(window),
            overturned=overturned,
        )
    return SuspensionDecision(
        suspended=False, reason=None, considered=len(window), overturned=overturned
    )


# ---------------------------------------------------------------------------
# The validated pairing
# ---------------------------------------------------------------------------

UNVALIDATED: Final = "unvalidated"
_PAIRING_PARTS: Final = 3


@dataclass(frozen=True, slots=True)
class ValidatedPairing:
    """The writer, reviewer and prompt a held-out validation passed for.

    Attributes:
        writer_model: The plan writer's model id.
        reviewer_model: The reviewer's model id.
        prompt_hash: The reviewer prompt's hash
            (``generation.prompts.plan_review_prompt_hash``).
    """

    writer_model: str
    reviewer_model: str
    prompt_hash: str


def format_validated_pairing(pairing: ValidatedPairing) -> str:
    """Render a pairing as the setting value ``writer|reviewer|prompt_hash``.

    Args:
        pairing: The pairing.

    Returns:
        str: The value for ``story_plan_reviewer_validated_pairing``.
    """
    return f"{pairing.writer_model}|{pairing.reviewer_model}|{pairing.prompt_hash}"


def parse_validated_pairing(value: str) -> ValidatedPairing | None:
    """Parse the ``story_plan_reviewer_validated_pairing`` setting.

    Args:
        value: ``"unvalidated"`` or ``"writer|reviewer|prompt_hash"``.

    Returns:
        ValidatedPairing | None: None for ``"unvalidated"``.

    Raises:
        ConfigurationError: When the value is neither form.
    """
    text = value.strip()
    if text == UNVALIDATED:
        return None
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != _PAIRING_PARTS or not all(parts):
        msg = (
            "story_plan_reviewer_validated_pairing must be 'unvalidated' or "
            "'<writer model>|<reviewer model>|<prompt hash>'"
        )
        raise ConfigurationError(msg)
    return ValidatedPairing(parts[0], parts[1], parts[2])


def reviewer_refusal(  # noqa: PLR0911, PLR0913 - one return per refusal code; six independent settings
    *,
    enabled: bool,
    suspended: bool,
    writer_model: str | None,
    reviewer_model: str | None,
    prompt_hash: str,
    validated_pairing: str,
) -> str | None:
    """Return why the reviewer must not be used for this pairing, or None.

    The worker (WP-2.4) calls this before every plan and routes the job to
    ``needs_review`` for any non-None answer: it fails closed. In order:
    ``disabled``, ``suspended``, ``not_independent`` (or ``model_unknown``),
    ``unvalidated``, ``pairing_malformed``, ``pairing_mismatch`` (a change of
    writer, reviewer or prompt voids the validation).

    Args:
        enabled: ``story_plan_reviewer_enabled``.
        suspended: ``story_plan_reviewer_suspended``.
        writer_model: The model that wrote the plan.
        reviewer_model: The configured reviewer.
        prompt_hash: The current reviewer prompt's hash.
        validated_pairing: ``story_plan_reviewer_validated_pairing``.

    Returns:
        str | None: A reason code, or None when the reviewer may be used.
    """
    # #CRITICAL: external-resources: a reviewer that was validated for another
    # writer, model or prompt has no measured behaviour here; using it would be
    # approval without evidence.
    # #VERIFY: test_plan_review.py::TestReviewerRefusal.
    if not enabled:
        return "disabled"
    if suspended:
        return "suspended"
    try:
        assert_independent(writer_model, reviewer_model)
    except BusinessLogicError as exc:
        return (
            "model_unknown"
            if exc.details.get("rule") == "plan_reviewer_model_unknown"
            else "not_independent"
        )
    try:
        pairing = parse_validated_pairing(validated_pairing)
    except ConfigurationError:
        return "pairing_malformed"
    if pairing is None:
        return UNVALIDATED
    if pairing != ValidatedPairing(
        cast("str", writer_model), cast("str", reviewer_model), prompt_hash
    ):
        return "pairing_mismatch"
    return None


def assert_reviewer_usable(  # noqa: PLR0913 - mirrors reviewer_refusal
    *,
    enabled: bool,
    suspended: bool,
    writer_model: str | None,
    reviewer_model: str | None,
    prompt_hash: str,
    validated_pairing: str,
) -> None:
    """Raise unless the reviewer may be used for this pairing.

    Args:
        enabled: ``story_plan_reviewer_enabled``.
        suspended: ``story_plan_reviewer_suspended``.
        writer_model: The model that wrote the plan.
        reviewer_model: The configured reviewer.
        prompt_hash: The current reviewer prompt's hash.
        validated_pairing: ``story_plan_reviewer_validated_pairing``.

    Raises:
        BusinessLogicError: With rule ``plan_reviewer_unusable`` and the reason
            code from :func:`reviewer_refusal` in its context.
    """
    reason = reviewer_refusal(
        enabled=enabled,
        suspended=suspended,
        writer_model=writer_model,
        reviewer_model=reviewer_model,
        prompt_hash=prompt_hash,
        validated_pairing=validated_pairing,
    )
    if reason is not None:
        msg = f"the plan reviewer cannot be used: {reason}"
        raise BusinessLogicError(
            msg, rule="plan_reviewer_unusable", context={"reason": reason}
        )
