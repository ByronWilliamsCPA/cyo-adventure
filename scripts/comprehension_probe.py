"""Two-model comprehension probe: an offline authoring accelerator (C1).

One model reads a passage and writes three comprehension questions about it
("what happened", "why", "what should the reader remember"). A **different**
model then tries to answer those questions from the passage text alone, with
no access to the rest of the story. A question the answer model cannot answer
confidently flags ambiguity, a missing causal link, or an unclear referent in
that passage.

This exists to test whether an LLM-based check can do better than the
project's own prior attempt at this class of problem.
:mod:`cyo_adventure.validator.continuity` built three formulations of a
reference-tracking check, measured **3.48 findings per node** over the
committed corpus at a **1 true positive in 6** rate on the narrowest
formulation, and shipped none of them as a rule. C1 only earns promotion to an
advisory moderation stage on a measured precision materially better than that,
against human-reviewed stories.

**This script cannot compute that precision figure, and does not try to.**
Precision requires a human to label each unanswerable-question finding as a
true or false positive, and no such labelling exists yet. What this script
measures is the *unlabelled* unanswerable-question rate: how often the answer
model says it cannot answer from the text. That number is a real, useful
signal (it is what a human labeller would triage), but it is not precision,
and a report from this script never claims otherwise. Turning it into
precision needs a human to read every recorded finding (see
``ProbeSummary.questions_unanswerable`` for the count) and judge, for each
one, whether the passage really was ambiguous or the answer model simply
missed something stated plainly in the text. Until that labelling happens,
the promote-or-reject decision this feeds stays open.

Offline only: this script reads no database and no request, is never imported
by ``app.py`` or any router, and is not deployed surface. It reads story JSON
files from disk and calls two OpenRouter model legs.

Output goes under a gitignored reports path (default
``tmp/comprehension-probe-reports/``), not a tracked one, so raw model output
never lands in the repository. This is the opposite convention from
``scripts/judge_books.py`` / ``scripts/evaluate_books.py``, which use
``scripts/_paid_output.py``'s ``ensure_persistable`` to *refuse* a gitignored
destination (AL-379: those scripts' results are the measurement, so losing
them loses the finding). Here the plan is explicit that raw model output must
not be committed, so this script reuses only ``_paid_output``'s private
``_is_ignored`` check and inverts the verdict: it refuses to run against a
destination git is *not* configured to ignore, rather than the other way
round. This guard exists because the obvious default, ``out/reports/``,
*looks* gitignored (an empty-seeming subdirectory of a mostly-scratch tree)
but is not: `.gitignore` only ignores specific subtrees under ``out/``
(``out/diversity/``, ``out/mutations/``, ``out/w7/arms/``), and ``out/reports/``
itself already carries tracked content (`.gitkeep`, compliance-report
markdown). A destination that merely looks safe is exactly the failure mode
the cap-that-never-fires trap generalizes to: verify the property, do not
assume it from the name.

Usage::

    uv run python scripts/comprehension_probe.py \\
        --corpus out --pattern '*.filled.json' --age-band 5-8 \\
        --max-passages 60 --budget-usd 5.00 \\
        --out tmp/comprehension-probe-reports
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.core.exceptions import ConfigurationError  # noqa: E402
from cyo_adventure.core.pricing import (  # noqa: E402
    CostEstimate,
    estimate_cost,
    price_for,
)
from cyo_adventure.generation.provider import build_openrouter_leg  # noqa: E402
from cyo_adventure.utils.logging import get_logger  # noqa: E402
from scripts._paid_output import (  # noqa: E402
    _is_ignored,  # pyright: ignore[reportPrivateUsage]
)
from scripts.adversarial_harness import (  # noqa: E402
    _load_env_file,  # pyright: ignore[reportPrivateUsage]
    _resolve_within,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.usage import Completion

logger = get_logger(__name__)

__all__ = [
    "AnswerRecord",
    "BudgetTracker",
    "CorpusStats",
    "NodeResult",
    "Passage",
    "ProbeSummary",
    "collect_passages",
    "probe_passage",
    "run_probe",
    "summarize",
]

# A skeleton node whose body still holds this directive has no prose yet: it
# is a fill instruction, not a passage. AL and the plan's trap list are both
# explicit that silently including these corrupts the aggregate (an empty
# artifact reads as either "obviously answerable" or "obviously not",
# depending on what a model does when handed a template string, and either
# way moves the rate in a direction nobody chose). They are counted and
# excluded, never scored.
_FILL_PREFIX: Final[str] = "<<FILL"

_QUESTIONS_PER_PASSAGE: Final[int] = 3

# #ASSUME: external-resources: the comprehension probe's two-model split
# remains available under the current provider allowlist and budget.
# #VERIFY: confirm both model ids against the provider allowlist before the
# pilot run, and record the model ids and prompt-set version in every report,
# so a precision (or, until human labelling exists, unlabelled-rate) figure is
# attributable to a configuration.
#
# Two different labs, both cheap, both routed through the OpenRouter leg per
# ADR-003 (the direct anthropic leg is excluded from family-lane generation
# and unnecessary here regardless: this script is offline tooling, not a
# family-lane call). Genuinely different models matter more than which two:
# one model both asking and answering measures the model's self-consistency,
# not the passage's clarity.
_QUESTION_MODEL: Final[str] = "google/gemini-2.5-flash"
_ANSWER_MODEL: Final[str] = "deepseek/deepseek-v4-flash"

# Bumped whenever the question or answer prompt text changes materially, so a
# report is attributable to the exact wording that produced it, not just the
# model ids.
_PROMPT_SET_VERSION: Final[str] = "comprehension-probe-v1"

# Sized for headroom over three short questions (or three short answers) plus
# JSON structure, not for the answer alone: AL-323 is what a per-node budget
# equal to the expected product buys you. Both chosen models are non-reasoning
# fast tiers, so the gap between "content" and "budget" should be small; the
# pilot run's actual truncation count is reported, not assumed.
_QUESTION_MAX_TOKENS: Final[int] = 1200
_ANSWER_MAX_TOKENS: Final[int] = 1500

_QUESTION_SYSTEM: Final[str] = (
    "You write comprehension questions for a children's reading assessment. "
    "You are given one passage from a branching story and must write exactly "
    f"{_QUESTIONS_PER_PASSAGE} short questions about it: one asking what "
    "happened, one asking why it happened, and one asking what the reader "
    "should remember going forward. Base every question only on this "
    "passage; do not assume anything about the rest of the story. Return "
    "only the JSON object requested, with no commentary around it."
)

_ANSWER_SYSTEM: Final[str] = (
    "You answer reading-comprehension questions using only the passage you "
    "are given. You have not read any other part of this story and must not "
    "guess at it. If the passage does not contain enough information to "
    "answer a question confidently, set can_answer to false and leave answer "
    "empty rather than inferring from outside knowledge or genre convention. "
    "Return only the JSON object requested, with no commentary around it."
)


@dataclass(frozen=True, slots=True)
class Passage:
    """One node's body, treated as a comprehension-probe passage.

    Attributes:
        story_id: The story's declared ``id``, falling back to the file stem
            when the document carries none.
        story_path: Path to the source file, relative to the repo root, kept
            for the per-story report grouping.
        node_id: The node's ``id`` within the story.
        body: The node's prose. Never a ``<<FILL ...>>`` directive; see
            :data:`_FILL_PREFIX`.
    """

    story_id: str
    story_path: str
    node_id: str
    body: str


@dataclass(frozen=True, slots=True)
class CorpusStats:
    """Counts from walking the corpus, before any model is called.

    Attributes:
        files_scanned: JSON files found under ``--corpus`` matching
            ``--pattern``.
        files_skipped_non_storybook: Files whose top-level ``nodes`` was not a
            list (sidecar contract/lineage/narrative files, or malformed
            JSON), so they were never Storybook documents to begin with.
        files_skipped_age_band: Files excluded by ``--age-band`` filtering.
        nodes_seen: Node dicts encountered across every included file.
        nodes_skipped_fill: Nodes excluded because ``body`` was a
            ``<<FILL ...>>`` directive.
        nodes_skipped_empty: Nodes excluded because ``body`` was missing or
            blank.
        passages_collected: What survived, in the order they will be probed.
    """

    files_scanned: int
    files_skipped_non_storybook: int
    files_skipped_age_band: int
    nodes_seen: int
    nodes_skipped_fill: int
    nodes_skipped_empty: int
    passages_collected: int


class ProbeParseError(ValueError):
    """A completion could not be parsed into the expected JSON shape.

    Attributes:
        kind: ``"truncated"`` when the completion was cut off before a
            complete JSON object was emitted, ``"malformed"`` when a complete
            reply carried invalid or wrongly-shaped JSON. The two need
            opposite fixes (raise the token budget vs. fix the prompt), so
            conflating them misattributes every truncated response as a
            model formatting failure.
    """

    def __init__(self, message: str, *, kind: str) -> None:
        """Record the parse failure and its kind.

        Args:
            message: Human-readable detail, safe to put in a report.
            kind: ``"truncated"`` or ``"malformed"``.
        """
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class AnswerRecord:
    """One question-answer pair from the answer model.

    Attributes:
        question: The question as generated (or as echoed back by the answer
            model, when it does not echo verbatim the two are compared by
            position, not by text).
        can_answer: Whether the answer model reported it could answer this
            question from the passage alone. ``False`` is the raw,
            unlabelled finding this script exists to produce.
        answer: The answer model's answer text, empty when ``can_answer`` is
            ``False``.
        reason: Optional short justification the answer model gave.
    """

    question: str
    can_answer: bool
    answer: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class NodeResult:
    """The outcome of probing one passage, successful or not.

    Attributes:
        story_id: Which story this node belongs to.
        node_id: The node probed.
        questions: The generated questions, or ``None`` if question
            generation failed or the budget was exhausted before this node.
        answers: The answer records, aligned by position with ``questions``,
            or ``None`` if answering failed, was skipped for budget, or
            question generation itself failed.
        error_stage: ``None`` on full success, else one of
            ``"question_generation:<kind>"``, ``"answering:<kind>"``,
            ``"budget"`` (no calls made), or ``"budget_after_questions"``
            (questions generated, answer call skipped).
        error_detail: Human-readable detail for ``error_stage``, or ``""``.
    """

    story_id: str
    node_id: str
    questions: list[str] | None
    answers: list[AnswerRecord] | None
    error_stage: str | None
    error_detail: str = ""


@dataclass
class BudgetTracker:
    """Tracks spend against a hard dollar cap and stops new calls once hit.

    #CRITICAL: concurrency: ``exhausted`` and ``add`` are checked and updated
    from a single sequential loop (:func:`run_probe`), never from concurrent
    tasks. A concurrent caller could read ``exhausted`` as ``False`` on
    several tasks before any of them calls ``add``, overshooting the cap by
    however many calls raced past the check; that is exactly the shape of the
    prior defect this repository already paid for (a clamp that existed and
    never bound). Sequential processing is what makes the cap exact rather
    than best-effort.
    #VERIFY: tests/unit/test_comprehension_probe.py::
    TestBudgetTracker::test_an_absurdly_low_cap_stops_the_run_after_one_passage
    and ::test_the_real_cap_does_not_fire_on_a_realistic_slice.

    Attributes:
        cap_usd: The hard spend limit. Never exceeded by the run stopping new
            calls; a call already in flight when the cap is crossed still
            posts its real cost, so ``spent_usd`` can land at or slightly
            over ``cap_usd``, never further.
        spent_usd: Cumulative cost of every call made so far, summed from
            :func:`~cyo_adventure.core.pricing.estimate_cost`. A lower bound
            when any call's cost was incomplete (see
            ``incomplete_cost_calls``).
        calls: How many provider calls were actually made.
        incomplete_cost_calls: How many of those calls contributed an
            incomplete cost (unpriced model or unreported token counts). A
            positive count here means ``spent_usd`` understates true spend by
            an unknown margin, and the report says so rather than treating
            spend as exact.
    """

    cap_usd: Decimal
    spent_usd: Decimal = field(default_factory=lambda: Decimal(0))
    calls: int = 0
    incomplete_cost_calls: int = 0

    def add(self, estimate: CostEstimate) -> None:
        """Post one call's cost against the running total.

        Args:
            estimate: The call's cost, from
                :func:`~cyo_adventure.core.pricing.estimate_cost`.
        """
        self.calls += 1
        self.spent_usd += estimate.amount_usd
        if not estimate.complete:
            self.incomplete_cost_calls += 1

    @property
    def exhausted(self) -> bool:
        """Whether spend has reached or passed the cap.

        Returns:
            ``True`` once ``spent_usd >= cap_usd``. Checked before every
            provider call in :func:`run_probe`, so once true no further calls
            are made.
        """
        return self.spent_usd >= self.cap_usd


@dataclass(frozen=True, slots=True)
class ProbeSummary:
    """The aggregate report for one probe run.

    Every field a reader needs in order not to mistake this for a precision
    figure lives here: the model ids, the prompt version, and an explicit
    ``unlabelled_unanswerable_rate`` name rather than anything calling itself
    precision.
    """

    generated_at: str
    corpus_description: str
    question_model: str
    answer_model: str
    prompt_set_version: str
    corpus_stats: CorpusStats
    nodes_processed: int
    nodes_skipped_budget: int
    questions_asked: int
    questions_unanswerable: int
    unlabelled_unanswerable_rate: float | None
    avg_unanswerable_findings_per_node: float | None
    nodes_with_any_unanswerable: int
    error_counts: dict[str, int]
    budget_cap_usd: str
    spend_usd: str
    budget_exhausted: bool
    calls_made: int
    incomplete_cost_calls: int
    uniform_verdict_warning: str | None
    note: str = (
        "unlabelled_unanswerable_rate is NOT precision. Turning it into a "
        "precision figure requires a human to read every finding this run "
        "recorded and judge whether the passage was genuinely ambiguous or "
        "the answer model missed something stated plainly in the text. No "
        "promote-or-reject verdict is recorded from this run."
    )


def _cost_of(completion: Completion) -> CostEstimate:
    """Cost one completion from the price table.

    Args:
        completion: A provider response, carrying which provider/model
            answered and what it consumed.

    Returns:
        The call's cost, a lower bound when the pair is unpriced or the
        backend did not report token counts.
    """
    price = price_for(completion.usage.provider, completion.usage.model)
    return estimate_cost(
        price, completion.usage.input_tokens, completion.usage.output_tokens
    )


def _question_prompt(passage_body: str) -> str:
    """Build the question-generation prompt for one passage.

    Args:
        passage_body: The node's prose.

    Returns:
        The user-role prompt.
    """
    return (
        f"Read this passage from a children's story and write exactly "
        f"{_QUESTIONS_PER_PASSAGE} short comprehension questions about it: "
        "one about what happened, one about why it happened, and one about "
        "what the reader should remember. Return exactly this JSON shape "
        'and nothing else: {"questions": ["...", "...", "..."]}\n\n'
        f"PASSAGE\n{passage_body}"
    )


def _answer_prompt(passage_body: str, questions: Sequence[str]) -> str:
    """Build the answering prompt for one passage and its questions.

    Args:
        passage_body: The same node prose the questions were generated from.
        questions: The questions to answer, in order.

    Returns:
        The user-role prompt.
    """
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    return (
        "Below is a passage from a children's story, followed by "
        f"{len(questions)} questions about it. Answer each question using "
        "ONLY the information in the passage below. Do not use outside "
        "knowledge, genre convention, or a guess about how the story might "
        "continue. If the passage does not give you enough information to "
        "answer a question confidently, set can_answer to false and leave "
        "answer empty.\n\n"
        f"PASSAGE\n{passage_body}\n\nQUESTIONS\n{numbered}\n\n"
        "Return exactly this JSON shape and nothing else, with exactly "
        f"{len(questions)} entries in the same order as the questions: "
        '{"answers": [{"question": "...", "can_answer": true, "answer": '
        '"...", "reason": "..."}]}'
    )


def _parse_json_object(completion: Completion) -> dict[str, object]:
    """Extract a JSON object from a completion, classifying failure kind.

    ``finish_reason == "length"`` is the authoritative truncation signal
    (``providers/openrouter.py`` raises only on an *empty* truncation, so a
    partial one arrives here as ordinary, non-empty text with this
    finish_reason). Where a provider does not report ``finish_reason``, the
    same heuristic ``scripts/judge_books.py::_parse`` uses is the fallback:
    a reply that opens a JSON object but never closes it, or that fails
    ``json.loads`` while not ending in ``}``, is presumed cut off rather than
    malformed.

    Args:
        completion: The provider response to parse.

    Returns:
        The decoded JSON object.

    Raises:
        ProbeParseError: With ``kind="truncated"`` or ``kind="malformed"``.
    """
    raw = completion.text
    truncated_signal = completion.finish_reason == "length"
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        if truncated_signal or raw.lstrip().startswith("{"):
            msg = (
                f"reply cut off at {len(raw)} chars before any JSON object "
                f"closed (finish_reason={completion.finish_reason!r}); raise "
                "the completion token budget"
            )
            raise ProbeParseError(msg, kind="truncated")
        msg = f"no JSON object in reply: {raw[:120]!r}"
        raise ProbeParseError(msg, kind="malformed")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        # Same trap as judge_books._parse: the greedy `\{.*\}` closes on the
        # last *inner* brace a cut-off completion managed to emit, so the
        # decode error points at an unbalanced object that reads like a
        # formatting failure. finish_reason is checked first because it is
        # authoritative; the "did it end in a closing brace" heuristic is
        # only the fallback for a backend that reports no finish_reason.
        truncated = truncated_signal or not raw.rstrip().endswith("}")
        kind = "truncated" if truncated else "malformed"
        msg = f"could not parse JSON ({kind}, finish_reason={completion.finish_reason!r}): {exc}"
        raise ProbeParseError(msg, kind=kind) from exc
    if not isinstance(payload, dict):
        msg = f"JSON was not an object: {type(payload).__name__}"
        raise ProbeParseError(msg, kind="malformed")
    return payload


def _extract_questions(payload: dict[str, object]) -> list[str]:
    """Validate and return the ``questions`` list from a parsed payload.

    Args:
        payload: The decoded JSON object from the question model.

    Returns:
        Exactly :data:`_QUESTIONS_PER_PASSAGE` non-empty question strings.

    Raises:
        ProbeParseError: With ``kind="malformed"`` if the shape does not
            match: a complete, valid-JSON reply that simply did not follow
            the requested shape is a model failure, not a truncation.
    """
    questions = payload.get("questions")
    if (
        isinstance(questions, list)
        and len(questions) == _QUESTIONS_PER_PASSAGE
        and all(isinstance(q, str) and q.strip() for q in questions)
    ):
        return [q.strip() for q in questions]
    msg = (
        f"expected {_QUESTIONS_PER_PASSAGE} non-empty question strings under "
        f"'questions', got: {questions!r}"[:200]
    )
    raise ProbeParseError(msg, kind="malformed")


def _extract_answers(
    payload: dict[str, object], *, questions: Sequence[str]
) -> list[AnswerRecord]:
    """Validate and return the ``answers`` list from a parsed payload.

    Args:
        payload: The decoded JSON object from the answer model.
        questions: The questions that were asked, for the expected count.

    Returns:
        One :class:`AnswerRecord` per question, in the order asked.

    Raises:
        ProbeParseError: With ``kind="malformed"`` if the count or shape does
            not match what was asked.
    """
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions):
        msg = f"expected {len(questions)} entries under 'answers', got: {answers!r}"[
            :200
        ]
        raise ProbeParseError(msg, kind="malformed")
    records: list[AnswerRecord] = []
    for question, entry in zip(questions, answers, strict=True):
        if not isinstance(entry, dict) or not isinstance(entry.get("can_answer"), bool):
            msg = f"malformed answer entry for {question!r}: {entry!r}"[:200]
            raise ProbeParseError(msg, kind="malformed")
        records.append(
            AnswerRecord(
                question=question,
                can_answer=entry["can_answer"],
                answer=str(entry.get("answer", "")),
                reason=str(entry.get("reason", "")),
            )
        )
    return records


def _load_storybook_nodes(path: Path) -> list[object] | None:
    """Read one JSON file and return its node list if it is a Storybook doc.

    The element type is deliberately ``object``, not ``dict[str, object]``:
    JSON decoded from an untrusted file can hold a list of anything (a
    string, a number, another list), and the caller still has to check each
    element before treating it as a node dict.

    Args:
        path: The file to read.

    Returns:
        The ``nodes`` list, or ``None`` when the file is not valid JSON, not
        an object, or its top-level ``nodes`` is not a list (skeleton catalog
        sidecar files such as ``*.contract.json`` and ``*.lineage.json`` all
        take this path, which is expected, not an error).
    """
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    nodes = doc.get("nodes")
    return nodes if isinstance(nodes, list) else None


def _story_id_and_band(path: Path) -> tuple[str, str | None]:
    """Return a story's declared id and age band without re-reading nodes.

    Args:
        path: The Storybook file.

    Returns:
        ``(story_id, age_band)``, falling back to the file stem for the id
        when the document carries none, and ``None`` for the band when
        undeclared.
    """
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path.stem, None
    story_id = doc.get("id") if isinstance(doc, dict) else None
    metadata = doc.get("metadata") if isinstance(doc, dict) else None
    band = metadata.get("age_band") if isinstance(metadata, dict) else None
    return (
        story_id if isinstance(story_id, str) and story_id else path.stem,
        band if isinstance(band, str) else None,
    )


def _display_path(path: Path) -> str:
    """Render a path for reports without ever assuming it is repo-rooted.

    Report paths are cosmetic (they only help a human locate a story), so
    a path outside ``_REPO_ROOT`` (as every ``tmp_path``-based unit test
    fixture is) must render as something readable rather than raise. This
    also protects the pilot run itself: a corpus directory passed via
    ``--corpus`` with a symlink or a relative component that resolves
    outside the repo must not crash mid-scan over a purely cosmetic path.

    Args:
        path: The Storybook file path to render.

    Returns:
        The path relative to the repo root when possible, otherwise the
        path as given.
    """
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def collect_passages(
    corpus_dir: Path,
    *,
    pattern: str = "*.json",
    age_band: str | None = None,
    max_passages: int,
) -> tuple[list[Passage], CorpusStats]:
    """Walk a corpus directory and collect passages up to a cap.

    Files are visited in sorted order and nodes in file order, so the same
    corpus and cap always yield the same slice: the point of a stated slice
    is that it is reproducible, not that it is random.

    Args:
        corpus_dir: Directory to scan (non-recursive).
        pattern: Glob pattern within ``corpus_dir``.
        age_band: When given, only files whose ``metadata.age_band`` equals
            this string exactly are included.
        max_passages: Stop once this many passages have been collected.

    Returns:
        The collected passages and the counts describing what was skipped
        and why.
    """
    files = sorted(corpus_dir.glob(pattern))
    passages: list[Passage] = []
    skipped_non_storybook = 0
    skipped_age_band = 0
    nodes_seen = 0
    skipped_fill = 0
    skipped_empty = 0

    for path in files:
        if len(passages) >= max_passages:
            break
        story_id, band = _story_id_and_band(path)
        if age_band is not None and band != age_band:
            skipped_age_band += 1
            continue
        nodes = _load_storybook_nodes(path)
        if nodes is None:
            skipped_non_storybook += 1
            continue
        rel_path = _display_path(path)
        for node in nodes:
            if len(passages) >= max_passages:
                break
            if not isinstance(node, dict):
                continue
            nodes_seen += 1
            node_id = node.get("id")
            body = node.get("body")
            if not isinstance(body, str) or not body.strip():
                skipped_empty += 1
                continue
            if body.strip().startswith(_FILL_PREFIX):
                skipped_fill += 1
                continue
            passages.append(
                Passage(
                    story_id=story_id,
                    story_path=rel_path,
                    node_id=node_id if isinstance(node_id, str) else "?",
                    body=body,
                )
            )

    stats = CorpusStats(
        files_scanned=len(files),
        files_skipped_non_storybook=skipped_non_storybook,
        files_skipped_age_band=skipped_age_band,
        nodes_seen=nodes_seen,
        nodes_skipped_fill=skipped_fill,
        nodes_skipped_empty=skipped_empty,
        passages_collected=len(passages),
    )
    return passages, stats


async def probe_passage(
    passage: Passage,
    *,
    question_provider: GenerationProvider,
    answer_provider: GenerationProvider,
    budget: BudgetTracker,
) -> NodeResult:
    """Ask one passage's questions, then try to answer them from the text.

    Two provider calls at most: question generation, then answering. The
    budget is checked again between them, because a passage whose question
    call happened to be the one that crossed the cap should not also spend on
    an answer call.

    Args:
        passage: The passage to probe.
        question_provider: The leg that generates questions.
        answer_provider: The leg that answers them; must be a different model
            from ``question_provider`` for the measurement to mean anything.
        budget: Shared spend tracker, mutated by this call.

    Returns:
        The outcome, successful or not.
    """
    q_completion = await question_provider.complete(
        system=_QUESTION_SYSTEM,
        prompt=_question_prompt(passage.body),
        max_tokens=_QUESTION_MAX_TOKENS,
    )
    budget.add(_cost_of(q_completion))
    try:
        questions = _extract_questions(_parse_json_object(q_completion))
    except ProbeParseError as exc:
        return NodeResult(
            story_id=passage.story_id,
            node_id=passage.node_id,
            questions=None,
            answers=None,
            error_stage=f"question_generation:{exc.kind}",
            error_detail=str(exc),
        )

    if budget.exhausted:
        return NodeResult(
            story_id=passage.story_id,
            node_id=passage.node_id,
            questions=questions,
            answers=None,
            error_stage="budget_after_questions",
            error_detail=(
                f"budget cap ${budget.cap_usd} reached after generating "
                "questions; no answer call was made for this passage"
            ),
        )

    a_completion = await answer_provider.complete(
        system=_ANSWER_SYSTEM,
        prompt=_answer_prompt(passage.body, questions),
        max_tokens=_ANSWER_MAX_TOKENS,
    )
    budget.add(_cost_of(a_completion))
    try:
        answers = _extract_answers(
            _parse_json_object(a_completion), questions=questions
        )
    except ProbeParseError as exc:
        return NodeResult(
            story_id=passage.story_id,
            node_id=passage.node_id,
            questions=questions,
            answers=None,
            error_stage=f"answering:{exc.kind}",
            error_detail=str(exc),
        )

    return NodeResult(
        story_id=passage.story_id,
        node_id=passage.node_id,
        questions=questions,
        answers=answers,
        error_stage=None,
    )


async def run_probe(
    passages: Sequence[Passage],
    *,
    question_provider: GenerationProvider,
    answer_provider: GenerationProvider,
    budget: BudgetTracker,
) -> list[NodeResult]:
    """Probe every passage in order, stopping new calls once budget is spent.

    Processed strictly sequentially (one ``await`` at a time, no
    ``asyncio.gather``): see the ``#CRITICAL: concurrency`` note on
    :class:`BudgetTracker` for why concurrent calls would make the cap only
    best-effort.

    Args:
        passages: The slice to probe, in order.
        question_provider: The question-generating leg.
        answer_provider: The answering leg.
        budget: Shared spend tracker.

    Returns:
        One :class:`NodeResult` per passage, including the passages skipped
        outright once the budget was already exhausted.
    """
    results: list[NodeResult] = []
    for index, passage in enumerate(passages):
        if budget.exhausted:
            results.append(
                NodeResult(
                    story_id=passage.story_id,
                    node_id=passage.node_id,
                    questions=None,
                    answers=None,
                    error_stage="budget",
                    error_detail=(
                        f"budget cap ${budget.cap_usd} reached before this "
                        f"passage ({index} of {len(passages)} attempted so "
                        "far); no calls made for it"
                    ),
                )
            )
            continue
        results.append(
            await probe_passage(
                passage,
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
    return results


def summarize(
    results: Sequence[NodeResult],
    *,
    budget: BudgetTracker,
    corpus_stats: CorpusStats,
    corpus_description: str,
) -> ProbeSummary:
    """Aggregate probe results into the report.

    Args:
        results: Every node result from :func:`run_probe`.
        budget: The spend tracker, read for the spend/cap figures.
        corpus_stats: Corpus-walk counts from :func:`collect_passages`.
        corpus_description: Human-readable description of the slice, for the
            report header.

    Returns:
        The aggregate summary. ``uniform_verdict_warning`` is set when every
        processed question landed on the same side (all answerable or all
        unanswerable), which is the signature of an environment fault, not a
        finding, per the trap this repository has already paid for once.
    """
    processed = [r for r in results if r.answers is not None]
    questions_asked = sum(len(r.answers or []) for r in processed)
    unanswerable = sum(
        1 for r in processed for a in (r.answers or []) if not a.can_answer
    )
    nodes_with_any = sum(
        1 for r in processed if any(not a.can_answer for a in (r.answers or []))
    )
    error_counts: dict[str, int] = {}
    for r in results:
        if r.error_stage:
            error_counts[r.error_stage] = error_counts.get(r.error_stage, 0) + 1

    rate = unanswerable / questions_asked if questions_asked else None
    avg_per_node = unanswerable / len(processed) if processed else None

    warning: str | None = None
    if processed and questions_asked:
        if unanswerable == 0:
            warning = (
                "every processed question was answerable (rate 0.0 across "
                f"{questions_asked} questions); a uniform verdict is the "
                "signature of an environment fault, not a finding -- verify "
                "the answer model actually saw the passage before trusting "
                "this as zero ambiguity."
            )
        elif unanswerable == questions_asked:
            warning = (
                "every processed question was UNanswerable (rate 1.0 across "
                f"{questions_asked} questions); a uniform verdict is the "
                "signature of an environment fault, not a finding -- verify "
                "the answer model actually received the passage text and "
                "that can_answer is not defaulting to false on parse."
            )

    return ProbeSummary(
        generated_at=datetime.now(UTC).isoformat(),
        corpus_description=corpus_description,
        question_model=_QUESTION_MODEL,
        answer_model=_ANSWER_MODEL,
        prompt_set_version=_PROMPT_SET_VERSION,
        corpus_stats=corpus_stats,
        nodes_processed=len(processed),
        nodes_skipped_budget=sum(
            1 for r in results if r.error_stage in {"budget", "budget_after_questions"}
        ),
        questions_asked=questions_asked,
        questions_unanswerable=unanswerable,
        unlabelled_unanswerable_rate=rate,
        avg_unanswerable_findings_per_node=avg_per_node,
        nodes_with_any_unanswerable=nodes_with_any,
        error_counts=error_counts,
        budget_cap_usd=str(budget.cap_usd),
        spend_usd=str(budget.spent_usd),
        budget_exhausted=budget.exhausted,
        calls_made=budget.calls,
        incomplete_cost_calls=budget.incomplete_cost_calls,
        uniform_verdict_warning=warning,
    )


def _node_result_to_dict(result: NodeResult) -> dict[str, object]:
    """Serialize one :class:`NodeResult` for the per-story JSON report."""
    return {
        "node_id": result.node_id,
        "questions": result.questions,
        "answers": (
            [dataclasses.asdict(a) for a in result.answers]
            if result.answers is not None
            else None
        ),
        "error_stage": result.error_stage,
        "error_detail": result.error_detail,
    }


def write_report(
    out_dir: Path,
    *,
    passages: Sequence[Passage],
    results: Sequence[NodeResult],
    summary: ProbeSummary,
) -> Path:
    """Write the per-story JSON reports and the aggregate summary.

    Args:
        out_dir: Destination directory (created if absent). Must already be
            verified gitignored by the caller (:func:`main` does this via
            ``_ensure_gitignored_destination`` before any spend); this
            function does not check again.
        passages: The passages probed, aligned by position with ``results``,
            for grouping results back into their source stories.
        results: Every node result.
        summary: The aggregate summary.

    Returns:
        The run's directory (a timestamped subdirectory of ``out_dir``).
    """
    run_dir = out_dir / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stories_dir = run_dir / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)

    by_story: dict[str, list[dict[str, object]]] = {}
    for passage, result in zip(passages, results, strict=True):
        by_story.setdefault(passage.story_id, []).append(_node_result_to_dict(result))

    for story_id, nodes in by_story.items():
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", story_id) or "story"
        (stories_dir / f"{safe_name}.json").write_text(
            json.dumps({"story_id": story_id, "nodes": nodes}, indent=2),
            encoding="utf-8",
        )

    summary_payload = dataclasses.asdict(summary)
    (run_dir / "summary.json").write_text(
        json.dumps(summary_payload, indent=2), encoding="utf-8"
    )
    return run_dir


def _print_summary(summary: ProbeSummary) -> None:
    """Print the human-readable summary to stdout."""
    print("=" * 64)
    print("Comprehension Probe (C1) -- unlabelled pilot, not a precision figure")
    print("=" * 64)
    print(f"Question model: {summary.question_model}")
    print(f"Answer model:   {summary.answer_model}")
    print(f"Prompt set:     {summary.prompt_set_version}")
    print(f"Corpus:         {summary.corpus_description}")
    stats = summary.corpus_stats
    print(
        f"Files scanned: {stats.files_scanned} "
        f"(skipped non-storybook: {stats.files_skipped_non_storybook}, "
        f"skipped age-band: {stats.files_skipped_age_band})"
    )
    print(
        f"Nodes seen: {stats.nodes_seen} "
        f"(skipped FILL: {stats.nodes_skipped_fill}, "
        f"skipped empty: {stats.nodes_skipped_empty}, "
        f"passages collected: {stats.passages_collected})"
    )
    print(f"Nodes processed: {summary.nodes_processed}")
    print(f"Nodes skipped for budget: {summary.nodes_skipped_budget}")
    print(f"Questions asked: {summary.questions_asked}")
    print(f"Questions unanswerable: {summary.questions_unanswerable}")
    print(f"Unlabelled unanswerable rate: {summary.unlabelled_unanswerable_rate}")
    print(
        f"Avg unanswerable findings per node: "
        f"{summary.avg_unanswerable_findings_per_node}"
    )
    print(
        f"Nodes with any unanswerable question: {summary.nodes_with_any_unanswerable}"
    )
    print(f"Error counts: {summary.error_counts}")
    print(
        f"Spend: ${summary.spend_usd} of ${summary.budget_cap_usd} cap "
        f"(exhausted={summary.budget_exhausted}, calls={summary.calls_made}, "
        f"incomplete-cost calls={summary.incomplete_cost_calls})"
    )
    if summary.uniform_verdict_warning:
        print(f"WARNING: {summary.uniform_verdict_warning}")
    print(summary.note)


def _ensure_gitignored_destination(out_dir: Path) -> None:
    """Refuse to run unless git is actually configured to ignore ``out_dir``.

    This is the mirror image of ``scripts/_paid_output.py``'s
    ``ensure_persistable``: that guard exists because a paid measurement run's
    output must survive in git, so it refuses a destination git ignores. This
    script's plan is the opposite (raw model output must never be committed),
    so it refuses a destination git does *not* ignore.

    Checking is not optional here: ``out/reports/`` looks safe (an
    unassuming subdirectory of a mostly-scratch tree) and is not. Only
    specific subtrees under ``out/`` carry an ignore rule
    (``out/diversity/``, ``out/mutations/``, ``out/w7/arms/``), and
    ``out/reports/`` itself already holds tracked content. A default that
    merely looks gitignored is exactly the shape of cap-that-never-fires
    trap this repository has already paid for once; the fix is to verify
    the property being relied on, not to assume it from the path's name.

    Args:
        out_dir: The resolved ``--out`` destination.

    Raises:
        SystemExit: When git does not consider ``out_dir`` ignored.
    """
    if _is_ignored(out_dir):
        return
    message = (
        f"refusing to start: '{out_dir}' is NOT gitignored, so any raw model "
        "output this run writes could end up committed to this PUBLIC "
        "repository. Pass --out with a path under an already-ignored "
        "directory (for example tmp/, which is gitignored repo-wide), or add "
        "a specific ignore rule for the path you want first. This check "
        "exists because out/reports/ (an earlier default here) LOOKS "
        "gitignored and is not: only out/diversity/, out/mutations/, and "
        "out/w7/arms/ carry ignore rules under out/, and out/reports/ itself "
        "already holds tracked content."
    )
    raise SystemExit(message)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, required=True, help="Directory of Storybook JSON files."
    )
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Glob pattern within --corpus (non-recursive). Default: *.json",
    )
    parser.add_argument(
        "--age-band",
        default=None,
        help="Only include documents whose metadata.age_band matches exactly.",
    )
    parser.add_argument("--max-passages", type=int, default=60)
    parser.add_argument("--budget-usd", type=str, default="5.00")
    parser.add_argument(
        "--out", type=Path, default=Path("tmp/comprehension-probe-reports")
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    corpus_dir = _resolve_within(args.corpus, label="--corpus")
    out_dir = _resolve_within(args.out, label="--out")
    env_path = _resolve_within(args.env_file, label="--env-file")

    _ensure_gitignored_destination(out_dir)
    _load_env_file(env_path)

    try:
        cap = Decimal(args.budget_usd)
    except (InvalidOperation, ValueError):
        print(
            f"Error: --budget-usd {args.budget_usd!r} is not a valid amount",
            file=sys.stderr,
        )
        return 2
    if cap <= 0:
        print("Error: --budget-usd must be positive", file=sys.stderr)
        return 2

    try:
        settings = Settings()
        question_provider = build_openrouter_leg(settings, _QUESTION_MODEL)
        answer_provider = build_openrouter_leg(settings, _ANSWER_MODEL)
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    passages, stats = collect_passages(
        corpus_dir,
        pattern=args.pattern,
        age_band=args.age_band,
        max_passages=args.max_passages,
    )
    if not passages:
        print(
            "Error: no passages collected from this corpus slice (every node "
            "was a <<FILL directive, blank, or excluded by --age-band); "
            f"stats={stats}",
            file=sys.stderr,
        )
        return 1

    corpus_description = (
        f"{args.corpus} (pattern={args.pattern!r}"
        + (f", age_band={args.age_band!r}" if args.age_band else "")
        + f", max_passages={args.max_passages})"
    )
    print(
        f"Probing {len(passages)} passages with question model "
        f"{_QUESTION_MODEL} and answer model {_ANSWER_MODEL} "
        f"(cap ${cap})...",
        file=sys.stderr,
    )

    budget = BudgetTracker(cap_usd=cap)
    results = asyncio.run(
        run_probe(
            passages,
            question_provider=question_provider,
            answer_provider=answer_provider,
            budget=budget,
        )
    )
    summary = summarize(
        results,
        budget=budget,
        corpus_stats=stats,
        corpus_description=corpus_description,
    )
    run_dir = write_report(out_dir, passages=passages, results=results, summary=summary)
    _print_summary(summary)
    print(f"\nReport written to {run_dir} (gitignored; not committed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
