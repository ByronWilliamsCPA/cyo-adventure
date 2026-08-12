"""Score filled books on prose quality with a blind, cross-lab judge panel.

``scripts/evaluate_books.py`` measures everything deterministic code can prove:
whether a book was finished, whether it hit its reading band, whether each node
matched the word count and beats its directive asked for. None of that can say
whether a story is any good. A book can hit every target and still be lifeless,
and the compliance axis will call it perfect.

So this is the other axis, and it is a model's opinion by necessity. Three
design constraints make that opinion worth something:

**Blind.** The judge never learns which model wrote what. Books are presented as
anonymous text, so a judge cannot reward a house style it recognises.

**Cross-lab.** A model asked to rank prose reliably favours its own family's
output. One judge would bake that bias into the headline, so the panel spans
three labs and every score is reported per judge as well as pooled. When a
judge's own family is under test, that row is the one to read sceptically, and
``self_family`` marks it so nobody has to remember which lab built which model.

**Normalised.** Judges differ in how freely they spend the top of a scale; one
may never award a 5. Pooling raw means would rank the legs a lenient judge
happened to see. Scores are z-scored within each judge before pooling, so the
pooled number reflects agreement about *ordering*, which is the thing three
independent judges can actually establish.

Only books that reached full fill completeness are judged. Scoring a book that
is three-quarters unwritten produces a number that looks like a quality verdict
and is really a delivery failure; the compliance axis already reports that, and
mixing the two is exactly the conflation this split exists to prevent.

Usage::

    uv run python scripts/judge_books.py \\
        --run out/vendor-comparison/run-1 \\
        --skeletons skeletons/5-8 \\
        --out out/vendor-comparison/evaluation \\
        --env-file .env
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.generation.provider import build_openrouter_leg  # noqa: E402
from scripts.evaluate_books import evaluate_book  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.generation.provider import GenerationProvider


@dataclass(frozen=True, slots=True)
class Judge:
    """One member of the panel.

    Attributes:
        label: Short name used in the report.
        model: OpenRouter model slug.
        provider_order: Backend pin, so a judge's scores are attributable to one
            serving stack for the same reason the generating legs are.
        family: The judge's lineage, compared against each book's family to flag
            self-scoring.
    """

    label: str
    model: str
    provider_order: tuple[str, ...]
    family: str


# Three labs, none of them Anthropic-only, so no single lineage can carry the
# pooled verdict. Kept deliberately small: a fourth judge multiplies cost across
# every book for a smaller marginal gain than a fourth generating leg would give.
_PANEL: Final[tuple[Judge, ...]] = (
    Judge("judge-gpt-5.6", "openai/gpt-5.6-sol", ("azure",), "openai"),
    Judge(
        "judge-gemini-3.1",
        "google/gemini-3.1-pro-preview",
        ("google-vertex/global",),
        "google",
    ),
    Judge("judge-grok-4.6", "x-ai/grok-4.6", ("xai/zdr",), "xai"),
)

# Each criterion names what a 1 and a 5 look like, because an unanchored 1-to-5
# scale measures a judge's mood. The anchors are written for this product: a
# story a 5-to-8-year-old reads alone, in a branching format where the choices
# are the point.
_CRITERIA: Final[dict[str, str]] = {
    "age_fit": (
        "Suitability for a 5-to-8-year-old reading alone. 1 = vocabulary or "
        "sentence structure a 7-year-old would stall on, or themes too adult. "
        "5 = consistently readable at that age with no talking down."
    ),
    "imagery": (
        "Concreteness of sensory detail. 1 = abstract or generic description "
        "that could belong to any story. 5 = specific, physical detail a child "
        "can picture."
    ),
    "voice": (
        "Distinctness and consistency of the main character. 1 = interchangeable "
        "narrator with no personality. 5 = a character who reacts in a "
        "recognisable, consistent way throughout."
    ),
    "dialogue": (
        "Naturalness of spoken lines. 1 = stilted, expository, or absent where "
        "it is clearly needed. 5 = lines that sound like people talking. Score 3 "
        "if the story is legitimately narration-led with little dialogue."
    ),
    "choice_quality": (
        "Whether the branch points feel like real decisions. 1 = options that "
        "are cosmetic restatements of each other. 5 = options that promise "
        "genuinely different experiences and deliver on that promise."
    ),
    "ending_quality": (
        "Satisfaction of the endings reached. 1 = abrupt stops or flat morals. "
        "5 = endings that resolve what the story set up and feel earned."
    ),
    "engagement": (
        "Whether a child would want to read on. 1 = a chore. 5 = genuinely compelling."
    ),
}

_SYSTEM: Final[str] = (
    "You are an experienced children's-book editor evaluating a branching "
    "story written for children aged 5 to 8. You are strict and calibrated: "
    "most competent-but-unremarkable writing is a 3, and a 5 is reserved for "
    "work you would publish as-is. Judge only the writing in front of you. You "
    "do not know who or what wrote it, and you must not speculate. Return only "
    "the JSON object requested, with no commentary around it."
)

# Enough for seven scores plus one short justification each, with room for a
# reasoning judge's hidden tokens on top.
# Completion budget per scoring. Sized to clear reasoning overhead plus the
# answer, not the answer alone: a reasoning judge spends hidden tokens before it
# emits anything, and whatever is left has to carry seven criteria with their
# notes. Measured 2026-08-12 against one 3,000-word book at an 8,000-token cap,
# the three panel judges returned 1,351, 1,530 and 1,360 characters of content
# (roughly 340 to 385 tokens), so the content is small and the overhead is what
# the budget must absorb. At 2,000 this truncated every Gemini 3.1 Pro reply
# mid-note, which surfaced as a JSONDecodeError and read as a malformed answer;
# see _parse for why that misreads. This is AL-308 recurring: size a budget by
# what the model spends before it can answer, not by the answer.
_JUDGE_MAX_TOKENS: Final[int] = 8000

__all__ = ["Judge", "Verdict", "judge_book", "pool_scores"]


@dataclass(frozen=True, slots=True)
class Verdict:
    """One judge's scoring of one book.

    Attributes:
        book: Identifier of the book scored, ``"<leg>#<brief>"``.
        leg: The generating leg's label.
        family: The generating leg's lineage.
        judge: The scoring judge's label.
        self_family: Whether judge and book share a lineage, which is the case
            to read sceptically.
        scores: Criterion name to 1-to-5 score.
        notes: The judge's one-line justification per criterion.
        error: Why scoring failed, or ``None``.
    """

    book: str
    leg: str
    family: str
    judge: str
    self_family: bool
    scores: dict[str, float]
    notes: dict[str, str]
    error: str | None


def _story_text(doc: dict[str, object]) -> str:
    """Render a book as readable text with its branch structure intact.

    A judge cannot assess choice quality from prose alone; it needs to see which
    options each node offered and where they led. Node ids are kept so the judge
    can follow a branch rather than reading the nodes as a flat sequence.

    Args:
        doc: The filled story document.

    Returns:
        The rendered story.
    """
    lines: list[str] = [f"TITLE: {doc.get('title', 'untitled')}", ""]
    nodes = doc.get("nodes")
    if not isinstance(nodes, list):
        return "\n".join(lines)
    for node in nodes:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        marker = " [ENDING]" if node.get("is_ending") else ""
        lines.append(f"--- {node.get('id')}{marker} ---")
        lines.append(str(node.get("body", "")))
        choices = node.get("choices")  # pyright: ignore[reportUnknownMemberType]
        if isinstance(choices, list):
            lines.extend(
                f'  -> "{choice.get("label")}" leads to {choice.get("target")}'
                for choice in choices  # pyright: ignore[reportUnknownVariableType]
                if isinstance(choice, dict)
            )
        lines.append("")
    return "\n".join(lines)


def _prompt(story: str) -> str:
    """Build the judging prompt for one book.

    Args:
        story: The rendered story text.

    Returns:
        The user-role prompt.
    """
    rubric = "\n".join(f"- {name}: {desc}" for name, desc in _CRITERIA.items())
    shape = ", ".join(f'"{name}": {{"score": N, "note": "..."}}' for name in _CRITERIA)
    return (
        f"Score this branching children's story on each criterion from 1 to 5.\n\n"
        f"CRITERIA\n{rubric}\n\n"
        f"Return exactly this JSON shape and nothing else:\n"
        f"{{{shape}}}\n\n"
        f"Each note must be one sentence citing something specific in the text.\n\n"
        f"STORY\n{story}"
    )


def _parse(raw: str) -> tuple[dict[str, float], dict[str, str]]:
    """Extract scores and notes from a judge's reply.

    Args:
        raw: The judge's raw completion.

    Returns:
        Scores and notes, keyed by criterion.

    Raises:
        ValueError: If the reply was truncated, carries no JSON object, or
            parsed without yielding a single criterion.
    """
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        # Cut off before even the first inner brace closed. Same cause as the
        # decode failure below, different symptom, so give the same guidance.
        if raw.lstrip().startswith("{"):
            msg = (
                f"the judge's reply was cut off at {len(raw)} chars before any "
                f"JSON object closed; raise _JUDGE_MAX_TOKENS above "
                f"{_JUDGE_MAX_TOKENS}"
            )
            raise ValueError(msg)
        msg = f"no JSON object in reply: {raw[:120]!r}"
        raise ValueError(msg)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        # A truncated reply still matches the regex above, because the greedy
        # `\{.*\}` closes on the last *inner* brace the completion managed to
        # emit. The result is an unbalanced object whose decode error points at
        # that inner brace, which reads as a malformed answer from a judge that
        # cannot follow a schema. It is not: the schema was followed and the
        # budget ran out. The two need opposite fixes, so name the difference.
        truncated = not raw.rstrip().endswith("}")
        cause = (
            f"the completion was cut off at {len(raw)} chars, so raise "
            f"_JUDGE_MAX_TOKENS above {_JUDGE_MAX_TOKENS}"
            if truncated
            else "the judge emitted a complete but invalid object"
        )
        msg = f"could not parse the judge's JSON ({cause}): {exc}"
        raise ValueError(msg) from exc
    scores: dict[str, float] = {}
    notes: dict[str, str] = {}
    for name in _CRITERIA:
        entry = payload.get(name)
        if isinstance(entry, dict) and isinstance(entry.get("score"), (int, float)):
            scores[name] = float(entry["score"])
            notes[name] = str(entry.get("note", ""))
        elif isinstance(entry, (int, float)):
            scores[name] = float(entry)
            notes[name] = ""
    if not scores:
        msg = f"reply carried no recognised criterion: {raw[:120]!r}"
        raise ValueError(msg)
    return scores, notes


async def judge_book(
    provider: GenerationProvider,
    judge: Judge,
    doc: dict[str, object],
    *,
    leg: str,
    family: str,
    brief_index: int,
) -> Verdict:
    """Have one judge score one book.

    Args:
        provider: The judge's provider leg.
        judge: The judge being asked.
        doc: The filled story document.
        leg: The generating leg's label.
        family: The generating leg's lineage.
        brief_index: Which brief the book was written from.

    Returns:
        The verdict, carrying ``error`` when scoring failed.
    """
    book = f"{leg}#{brief_index}"
    blank = Verdict(
        book=book,
        leg=leg,
        family=family,
        judge=judge.label,
        self_family=judge.family == family,
        scores={},
        notes={},
        error=None,
    )
    try:
        raw = await provider.complete(
            system=_SYSTEM,
            prompt=_prompt(_story_text(doc)),
            max_tokens=_JUDGE_MAX_TOKENS,
        )
        scores, notes = _parse(raw)
    except Exception as exc:
        # Deliberately broad: one judge failing on one book must not abandon the
        # other hundred-odd scorings. The failure is recorded per book, and
        # pool_scores drops it rather than treating a missing score as a zero.
        return dataclasses.replace(blank, error=f"{type(exc).__name__}: {exc}")
    return dataclasses.replace(blank, scores=scores, notes=notes)


def _z_scores(verdicts: Sequence[Verdict]) -> dict[tuple[str, str], float]:
    """Normalise each judge's overall scores to its own mean and spread.

    Args:
        verdicts: Every successful verdict.

    Returns:
        ``(judge, book)`` to z-scored overall rating.
    """
    by_judge: dict[str, list[tuple[str, float]]] = {}
    for v in verdicts:
        if v.scores:
            by_judge.setdefault(v.judge, []).append(
                (v.book, statistics.fmean(v.scores.values()))
            )
    out: dict[tuple[str, str], float] = {}
    for judge, rows in by_judge.items():
        values = [value for _, value in rows]
        mean = statistics.fmean(values)
        # A judge who gave every book the same score carries no ordering
        # information; spreading by zero would be a divide-by-zero, and calling
        # every book average is the honest reading.
        spread = statistics.stdev(values) if len(values) > 1 else 0.0
        for book, value in rows:
            out[judge, book] = 0.0 if spread == 0 else (value - mean) / spread
    return out


def pool_scores(verdicts: Sequence[Verdict]) -> dict[str, dict[str, float | int]]:
    """Aggregate verdicts per generating leg.

    Args:
        verdicts: Every verdict, successful or not.

    Returns:
        Per-leg pooled figures: raw mean, judge-normalised mean, per-criterion
        means, and how many scorings succeeded.
    """
    good = [v for v in verdicts if v.scores and v.error is None]
    z = _z_scores(good)
    by_leg: dict[str, list[Verdict]] = {}
    for v in good:
        by_leg.setdefault(v.leg, []).append(v)

    pooled: dict[str, dict[str, float | int]] = {}
    for leg, rows in by_leg.items():
        entry: dict[str, float | int] = {
            "scorings": len(rows),
            "raw_mean": statistics.fmean(
                [statistics.fmean(v.scores.values()) for v in rows]
            ),
            "normalised_mean": statistics.fmean(
                [z[v.judge, v.book] for v in rows if (v.judge, v.book) in z]
            ),
        }
        for name in _CRITERIA:
            values = [v.scores[name] for v in rows if name in v.scores]
            if values:
                entry[name] = statistics.fmean(values)
        pooled[leg] = entry
    return pooled


def _complete_books(
    run_dirs: Sequence[Path], skeleton_dir: Path
) -> list[dict[str, object]]:
    """Collect every fully filled book across the given runs.

    Args:
        run_dirs: Directories holding ``report.json`` and ``books/``.
        skeleton_dir: Where the runs' skeletons live.

    Returns:
        One entry per complete book, carrying its document and provenance.
    """
    out: list[dict[str, object]] = []
    for run_dir in run_dirs:
        payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        names: list[str] = list(payload["skeletons"])
        skeletons = [
            json.loads((skeleton_dir / n).read_text(encoding="utf-8")) for n in names
        ]
        for row in payload["books"]:
            if row.get("file") is None:
                continue
            doc = json.loads((run_dir / row["file"]).read_text(encoding="utf-8"))
            index = int(row["brief_index"])
            score = evaluate_book(
                doc,
                skeletons[index if len(skeletons) > 1 else 0],
                leg=row["vendor"],
                family=row["family"],
                brief_index=index,
            )
            if score.fill_completeness < 1.0:
                print(
                    f"  skipping {row['vendor']}#{index}: only "
                    f"{score.fill_completeness:.0%} of nodes were filled",
                    file=sys.stderr,
                )
                continue
            out.append(
                {
                    "doc": doc,
                    "leg": row["vendor"],
                    "family": row["family"],
                    "brief_index": index,
                }
            )
    return out


async def _run_panel(
    books: Sequence[dict[str, object]], settings: Settings
) -> list[Verdict]:
    """Score every book with every judge.

    Args:
        books: Complete books with provenance.
        settings: Settings supplying the credential.

    Returns:
        Every verdict.
    """
    verdicts: list[Verdict] = []
    for judge in _PANEL:
        provider = build_openrouter_leg(
            settings, model=judge.model, provider_order=judge.provider_order
        )
        for entry in books:
            verdict = await judge_book(
                provider,
                judge,
                entry["doc"],  # pyright: ignore[reportArgumentType]
                leg=str(entry["leg"]),
                family=str(entry["family"]),
                brief_index=int(entry["brief_index"]),  # pyright: ignore[reportArgumentType]
            )
            flag = " [SELF-FAMILY]" if verdict.self_family else ""
            detail = verdict.error or (
                f"{statistics.fmean(verdict.scores.values()):.2f}"
                if verdict.scores
                else "no scores"
            )
            print(f"  {judge.label} -> {verdict.book}{flag}: {detail}", file=sys.stderr)
            verdicts.append(verdict)
    return verdicts


def _print_table(pooled: dict[str, dict[str, float | int]]) -> None:
    """Print the pooled quality scorecard.

    Args:
        pooled: Output of :func:`pool_scores`.
    """
    if not pooled:
        print("\nNo book was scored.")
        return
    rows = sorted(pooled.items(), key=lambda kv: -float(kv[1]["normalised_mean"]))
    width = max(len(leg) for leg in pooled)
    names = list(_CRITERIA)
    header = f"  {'leg':<{width}}  {'norm':>6} {'raw':>5} {'n':>3}  " + " ".join(
        f"{name[:6]:>6}" for name in names
    )
    print("\nQUALITY  (blind cross-lab panel; normalised within judge)")
    print(header)
    for leg, entry in rows:
        cells = " ".join(
            f"{float(entry[name]):>6.2f}" if name in entry else f"{'-':>6}"
            for name in names
        )
        print(
            f"  {leg:<{width}}  {float(entry['normalised_mean']):>+6.2f} "
            f"{float(entry['raw_mean']):>5.2f} {int(entry['scorings']):>3}  {cells}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Judge every complete book and write the panel's verdicts.

    Args:
        argv: Command-line arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, action="append", type=Path, dest="runs")
    parser.add_argument("--skeletons", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    if args.env_file.exists():
        for line in args.env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = (
                    line.split("=", 1)[1].strip().strip("'\"")
                )

    books = _complete_books(args.runs, args.skeletons)
    if not books:
        print("Error: no complete books to judge.", file=sys.stderr)
        return 1
    print(
        f"Judging {len(books)} complete books with {len(_PANEL)} judges "
        f"({len(books) * len(_PANEL)} scorings).",
        file=sys.stderr,
    )

    verdicts = asyncio.run(_run_panel(books, Settings()))
    pooled = pool_scores(verdicts)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "judgements.json").write_text(
        json.dumps(
            {
                "panel": [dataclasses.asdict(j) for j in _PANEL],
                "criteria": _CRITERIA,
                "verdicts": [dataclasses.asdict(v) for v in verdicts],
                "pooled": pooled,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _print_table(pooled)
    failed = sum(1 for v in verdicts if v.error is not None)
    if failed:
        print(f"\n{failed} of {len(verdicts)} scorings failed; see judgements.json")
    print(f"Wrote {args.out / 'judgements.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
