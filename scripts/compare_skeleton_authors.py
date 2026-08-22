"""Cross-vendor skeleton-authoring comparison harness (register row `S-1`, plan E1).

Asks each vendor leg to author a complete Storybook *skeleton* (a story graph
whose node bodies are ``<<FILL ...>>`` directives) for a production cell, from
the cell's machine-generated drafting brief plus one curated premise, then
scores every shell deterministically. This is the skeleton-stage sibling of
``compare_vendors.py``, which varies the model only on the *fill* stage; the
two harnesses share the vendor-spec format, the leg construction path, and the
preflight, and differ in what the leg is asked to produce.

Design constraints carried in from the plan
(`docs/planning/skeleton-sourcing-test-plan-2026-08-21.md`) and register row
`S-1` (`docs/planning/diversity-test-register.md` section F):

- **Shared repair-loop contract.** Q-3d established that the repair loop
  belongs in the harness, so every leg gets the identical loop: same author
  system prompt, same validator-feedback format (the raw ``check_skeleton
  --strict`` output, truncated identically), same round cap, same
  stateless-repair prompt shape. A per-leg repair harness would be the
  treatment.
- **One pre-registered primary endpoint**: repair rounds to strict pass,
  pooled across cells, permutation test over leg assignment (implemented in
  :func:`permutation_test`). Everything else this harness records (one-pass
  yield, findings counts, walk output, catalog distances, tokens, latency) is
  exploratory and decision-inert.
- **Premises are allocated, never invented.** Replicate ``r`` of a cell uses
  that cell's ``premises[r-1]`` from the frozen S-0 materials file for every
  leg, so the premise axis cancels within a replicate.
- **Briefs are generated, never hand-copied** (AL-149): the cell brief comes
  from ``generate_drafting_brief.build_brief`` at run time.
- **No cascade**: each leg is a single pinned backend via
  ``compare_vendors._build_provider``; a fallback would attribute one
  vendor's shell to another.

``--mock`` exercises the whole loop (prompting, JSON extraction, strict
check, scoring, persistence, analysis) with a deterministic built-in shell
that deliberately does NOT pass the strict bar; a mock run validates the
plumbing, not the passing path. ``--preflight-only`` proves every pin callable
and exits before any authoring spend.

Usage:
    uv run python scripts/compare_skeleton_authors.py --preflight-only
    uv run python scripts/compare_skeleton_authors.py --mock \
        --replicates 1 --max-repair-rounds 1
    uv run python scripts/compare_skeleton_authors.py \
        --cells A --replicates 1 --out-dir <dir>   # smoke
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess  # offline harness drives the repo's own checkers
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from compare_vendors import (  # noqa: E402
    _build_provider,
    _load_env_file,
    _load_vendors,
    _report_preflight,
    preflight,
)
from generate_drafting_brief import _render_markdown, build_brief  # noqa: E402

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.diversity.structure import structural_distance  # noqa: E402
from cyo_adventure.generation.usage import Completion, TokenUsage  # noqa: E402

_EVIDENCE_DIR = _REPO_ROOT / "docs" / "planning" / "evidence"
_DEFAULT_VENDORS = _EVIDENCE_DIR / "skeleton-author-vendors" / "vendors.json"
_DEFAULT_PREMISES = _EVIDENCE_DIR / "sourcing-materials" / "premises.json"
_DEFAULT_OUT_ROOT = _EVIDENCE_DIR / "skeleton-author-vendors" / "runs"
_SIDECAR_SUFFIXES = (".contract.json", ".lineage.json", ".narrative.json")

# Identical for every leg: part of the shared repair-loop contract. Longer
# feedback would favour long-context legs; shorter would starve the repair.
_FEEDBACK_MAX_LINES = 120
_CHECK_TIMEOUT_S = 300
_PERMUTATIONS = 10_000
_PERMUTATION_SEED = 20_260_821

_AUTHOR_SYSTEM = """\
You are authoring a SKELETON for a children's branching storybook: the full
story graph with every node body written as a single fill directive, not as
prose. Output MUST be one JSON object and nothing else: no markdown fences,
no commentary before or after.

Top-level shape (all keys required):
{
  "schema_version": "2.0",
  "id": "<kebab-case-slug>",
  "version": 1,
  "title": "<story title>",
  "metadata": {
    "age_band": "<band>", "length": "<length>", "narrative_style": "prose",
    "topology": "<one of: time_cave, branch_and_bottleneck, gauntlet>",
    "tier": 1, "production_eligible": false,
    "reading_level": {"scheme": "flesch_kincaid", "target": <number>,
                      "tolerance": 1.5},
    "themes": ["<3-5 themes>"], "estimated_minutes": <number>,
    "ending_count": <number of ending nodes>,
    "content_flags": {"violence": "none", "scariness": "none|mild",
                      "peril": "none|mild"}
  },
  "variables": [],
  "start_node": "<id of the opening node>",
  "nodes": [ <node objects> ]
}

Every node: {"id": "<unique id>", "body": "<fill directive>",
"is_ending": false, "choices": [{"id": "<unique id>", "label": "<child-visible
choice text>", "target": "<node id>"}]}.
An ending node instead has "is_ending": true, "choices": [], and an extra key
"ending": {"id": "<unique id>", "valence": "positive|neutral|negative",
"kind": "success|setback|death|capture|completion|discovery",
"title": "<child-visible ending title>"}.

Every non-ending body is EXACTLY one directive of this form (single quotes
around beats, no newline inside):
<<FILL role=<setup|explore|decision|transition|climax|ending> words=<target>
beats='<concrete, story-specific beats for this node; no placeholders>'>>
written as one line. Ending bodies use role=ending. Beats must be concrete to
THIS story (names, objects, places), never template slots like {HERO}.

Follow every constraint in the drafting brief you are given: node budget,
ending count and mix, branching, depth, first-decision window, choice-label
grammar, reading-level target. Choice labels and ending titles are
child-visible text and must obey the brief's label rules.
"""

_REPAIR_PROMPT = """\
Your previous skeleton did not pass the validator. The validator output is
below. Fix every finding and return the COMPLETE corrected JSON object
(the whole skeleton, not a diff). Output JSON only.

--- your previous skeleton ---
{previous}

--- validator output ---
{feedback}
"""


@dataclass(slots=True)
class ShellRecord:
    """Everything measured about one authored shell.

    The primary endpoint for `S-1` is ``repair_rounds`` on shells with
    ``strict_pass``; every other field is exploratory.
    """

    leg: str
    family: str
    cell_id: str
    band: str
    length: str
    style: str
    replicate: int
    premise: str
    attempts: int = 0
    repair_rounds: int = 0
    strict_pass: bool = False
    first_pass_clean: bool = False
    parse_failures: int = 0
    findings_lines_per_round: list[int] = field(default_factory=list)
    graph_check_exit: int | None = None
    latency_s: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    finish_reasons: list[str] = field(default_factory=list)
    min_catalog_distance: float | None = None
    mean_catalog_distance: float | None = None
    catalog_distance_note: str = ""
    last_feedback: str = ""
    shell_file: str = ""
    error: str = ""


def _load_premises(path: Path) -> list[dict[str, Any]]:
    """Load the frozen S-0 premises file.

    Args:
        path: ``premises.json`` from the sourcing-materials evidence dir.

    Returns:
        The ``cells`` array: each entry carries ``id``, ``band``, ``length``,
        ``style``, and a ``premises`` list.

    Raises:
        SystemExit: On a malformed file, since running with improvised
            premises would void the S-0 allocation rule.
    """
    # #CRITICAL: data integrity: premises are pre-registered materials; a
    # harness that silently tolerates a malformed file would let a run drift
    # from the registered allocation.
    # #VERIFY: hard-exit on any shape violation below.
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: cannot read premises {path}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    cells = parsed.get("cells") if isinstance(parsed, dict) else None
    if not isinstance(cells, list) or not cells:
        print(f"Error: {path} has no 'cells' array.", file=sys.stderr)
        raise SystemExit(1)
    for entry in cells:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict) or not entry.get("premises"):
            print(f"Error: malformed cell entry in {path}.", file=sys.stderr)
            raise SystemExit(1)
    return cells  # pyright: ignore[reportUnknownVariableType]


def _author_prompt(brief_markdown: str, premise: str) -> str:
    """Compose the per-shell user prompt from the brief and its premise."""
    return (
        "Author one skeleton for the following production cell.\n\n"
        f"PREMISE (write THIS story, concretely):\n{premise}\n\n"
        f"DRAFTING BRIEF (every constraint is enforced):\n{brief_markdown}\n"
    )


def _extract_json(text: str) -> tuple[dict[str, Any] | None, str]:
    """Pull the first JSON object out of a completion.

    Args:
        text: The leg's raw completion text (fences already stripped by the
            provider adapter, but tolerated here anyway).

    Returns:
        ``(doc, "")`` on success, ``(None, reason)`` on failure. The reason is
        fed back through the shared repair prompt.
    """
    # #ASSUME: data integrity: legs sometimes wrap JSON in prose or fences
    # despite instructions; slicing brace-to-brace recovers the common cases.
    # #VERIFY: parse failure is recorded and costs the leg a repair round
    # rather than crashing the run.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None, "no JSON object found in the output"
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"output was not valid JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "top-level JSON value must be an object"
    return parsed, ""


def _run_checker(script: str, args: list[str]) -> tuple[int, str]:
    """Run one repo checker script on a shell file.

    Args:
        script: Filename under ``scripts/``.
        args: Arguments, typically the shell path plus flags.

    Returns:
        ``(exit_code, output)`` with stdout+stderr merged and truncated to
        ``_FEEDBACK_MAX_LINES`` so every leg sees identically-shaped feedback.
    """
    # #ASSUME: external resources: the checker scripts are deterministic and
    # offline; a hang would stall the run, so a timeout converts it to a
    # failed round instead.
    # #VERIFY: timeout below; timeout output is fed back like any finding.
    cmd = [sys.executable, str(_SCRIPTS_DIR / script), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CHECK_TIMEOUT_S,
            check=False,
            cwd=str(_REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        return 124, f"{script} timed out after {_CHECK_TIMEOUT_S}s"
    output = (proc.stdout or "") + (proc.stderr or "")
    lines = output.splitlines()
    if len(lines) > _FEEDBACK_MAX_LINES:
        dropped = len(lines) - _FEEDBACK_MAX_LINES
        lines = [*lines[:_FEEDBACK_MAX_LINES], f"... ({dropped} more lines)"]
    return proc.returncode, "\n".join(lines)


def _strict_check(
    shell_path: Path, band: str, length: str, style: str
) -> tuple[bool, str]:
    """Run ``check_skeleton.py --strict`` pinned to the cell.

    ``--allow-mvp`` is required, not optional: an authored shell correctly
    declares ``production_eligible: false`` (promotion is a reviewed human
    decision, never an authoring-time claim), and cell mode without the flag
    fails exactly that declaration, making the pass bar unreachable for every
    leg. The 2026-08-21 smoke run hit this: all four completing legs repaired
    down to 1-2 real findings and could never pass.

    Returns:
        ``(passed, feedback)``.
    """
    code, output = _run_checker(
        "check_skeleton.py",
        [
            str(shell_path),
            "--strict",
            "--allow-mvp",
            "--band",
            band,
            "--length",
            length,
            "--style",
            style,
        ],
    )
    return code == 0, output


def _catalog_cell_paths(band: str, length: str, style: str) -> list[Path]:
    """List committed catalog skeletons for one cell (sidecars excluded)."""
    band_dir = _REPO_ROOT / "skeletons" / band
    if not band_dir.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(band_dir.glob("*.json")):
        if path.name.endswith(_SIDECAR_SUFFIXES):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meta = doc.get("metadata")
        if not isinstance(meta, dict):
            continue
        if meta.get("length") == length and meta.get("narrative_style") == style:
            out.append(path)
    return out


def _catalog_distances(
    doc: dict[str, Any], band: str, length: str, style: str
) -> tuple[float | None, float | None, str]:
    """Score a shell's structural distance against its in-cell catalog.

    Exploratory (Tier 2): the register requires the topology-flag component
    of ``structural_distance`` be reported separately wherever legs declare
    their own topology; that split is carried in the note field here because
    the metric exposes only the combined value, and the declared topology is
    persisted with every shell so the component is recoverable.

    Returns:
        ``(min, mean, note)``; ``(None, None, reason)`` when unscorable.
    """
    paths = _catalog_cell_paths(band, length, style)
    if not paths:
        return None, None, f"no committed catalog skeletons for {band}/{length}/{style}"
    distances: list[float] = []
    failures = 0
    for path in paths:
        try:
            other = json.loads(path.read_text(encoding="utf-8"))
            distances.append(structural_distance(doc, other))
        except Exception:  # any coercion failure = unscorable pair
            failures += 1
    if not distances:
        return None, None, f"shell not coercible against any of {len(paths)} peers"
    note = f"vs {len(distances)} in-cell peers" + (
        f"; {failures} pairs unscorable" if failures else ""
    )
    return min(distances), statistics.fmean(distances), note


_MOCK_SHELL_NODES = 6


def _mock_shell(band: str, length: str, premise: str, replicate: int) -> str:
    """Return a deterministic, parseable, strict-FAILING mini shell.

    Exists so ``--mock`` exercises extraction, checking, scoring and
    persistence without a provider. It is far below every cell's node budget
    by design; a mock run validates plumbing, never the passing path.
    """
    seed = f"{band}-{length}-r{replicate}"
    nodes: list[dict[str, Any]] = [
        {
            "id": f"n_{i}",
            "body": (
                f"<<FILL role={'setup' if i == 0 else 'explore'} words=40 "
                f"beats='mock beat {seed} node {i}: {premise[:40]}'>>"
            ),
            "is_ending": False,
            "choices": [
                {"id": f"c_{i}a", "label": "Go on.", "target": f"n_{i + 1}"},
                {"id": f"c_{i}b", "label": "Stop here.", "target": "e_stop"},
            ],
        }
        for i in range(_MOCK_SHELL_NODES - 2)
    ]
    nodes[-1]["choices"] = [{"id": "c_last", "label": "Finish.", "target": "e_done"}]
    for end_id, valence, kind in (
        ("e_done", "positive", "success"),
        ("e_stop", "neutral", "setback"),
    ):
        nodes.append(
            {
                "id": end_id,
                "body": f"<<FILL role=ending words=50 beats='mock end {end_id}'>>",
                "is_ending": True,
                "choices": [],
                "ending": {
                    "id": f"end_{end_id}",
                    "valence": valence,
                    "kind": kind,
                    "title": f"The {end_id} ending",
                },
            }
        )
    doc = {
        "schema_version": "2.0",
        "id": f"mock-shell-{seed}",
        "version": 1,
        "title": f"Mock shell {seed}",
        "metadata": {
            "age_band": band,
            "length": length,
            "narrative_style": "prose",
            "topology": "gauntlet",
            "tier": 1,
            "production_eligible": False,
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 2.5,
                "tolerance": 1.5,
            },
            "themes": ["mock"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_0",
        "nodes": nodes,
    }
    return json.dumps(doc)


class _MockAuthor:
    """Deterministic stand-in provider for ``--mock`` runs."""

    def __init__(self, band: str, length: str, premise: str, replicate: int):
        self._payload = _mock_shell(band, length, premise, replicate)

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Any:
        """Return the canned shell wrapped in a Completion-shaped object."""
        del system, prompt, max_tokens
        return Completion(
            text=self._payload,
            usage=TokenUsage(
                provider="mock",
                model="mock",
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
            ),
            finish_reason="stop",
        )


async def author_shell(
    provider: Any,
    record: ShellRecord,
    brief_markdown: str,
    out_dir: Path,
    *,
    max_repair_rounds: int,
    max_tokens: int,
) -> ShellRecord:
    """Run the shared authoring-and-repair loop for one (cell, replicate, leg).

    The loop is the S-1 contract: identical prompts, feedback shape, and round
    cap for every leg. Each call is stateless (the provider surface has no
    chat history), so a repair round re-sends the previous JSON plus the
    validator output.

    Args:
        provider: The leg's pinned provider (or mock).
        record: The record to fill in; mutated and returned.
        brief_markdown: The cell's generated drafting brief.
        out_dir: Run directory; the shell and its record are persisted here
            as the run goes, so a crashed run keeps its paid artifacts.
        max_repair_rounds: Repair calls allowed after the first attempt.
        max_tokens: Completion cap per call, recorded as a run condition.

    Returns:
        The completed record.
    """
    base_prompt = _author_prompt(brief_markdown, record.premise)
    shell_name = f"{record.cell_id}__r{record.replicate}__{record.leg}.json"
    shell_path = out_dir / "shells" / shell_name
    shell_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = base_prompt
    doc: dict[str, Any] | None = None
    # shell_file is set only after a successful write, so a record never names
    # a file that does not exist; last_written survives a final unparseable
    # round so the post-loop scoring reflects the shell actually on disk.
    last_written: dict[str, Any] | None = None
    started = time.monotonic()
    # #CRITICAL: external resources: every iteration is a paid provider call;
    # the cap below is the only bound on spend for a leg that never converges.
    # #VERIFY: attempts <= 1 + max_repair_rounds, asserted by the range.
    for attempt in range(1 + max_repair_rounds):
        try:
            completion = await provider.complete(
                system=_AUTHOR_SYSTEM, prompt=prompt, max_tokens=max_tokens
            )
        except Exception as exc:  # leg-fatal, recorded not raised
            record.error = f"{type(exc).__name__}: {exc}"[:500]
            break
        record.attempts = attempt + 1
        usage = completion.usage
        if usage.input_tokens is not None:
            record.input_tokens = (record.input_tokens or 0) + usage.input_tokens
        if usage.output_tokens is not None:
            record.output_tokens = (record.output_tokens or 0) + usage.output_tokens
        if usage.reasoning_tokens is not None:
            record.reasoning_tokens = (
                record.reasoning_tokens or 0
            ) + usage.reasoning_tokens
        record.finish_reasons.append(completion.finish_reason or "?")

        doc, parse_reason = _extract_json(completion.text)
        if doc is None:
            record.parse_failures += 1
            feedback = f"(no skeleton to check) {parse_reason}"
            record.findings_lines_per_round.append(1)
        else:
            shell_path.write_text(
                json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            last_written = doc
            record.shell_file = str(shell_path.relative_to(out_dir))
            passed, feedback = _strict_check(
                shell_path, record.band, record.length, record.style
            )
            record.findings_lines_per_round.append(len(feedback.splitlines()))
            if passed:
                record.strict_pass = True
                record.first_pass_clean = attempt == 0
                record.repair_rounds = attempt
                record.last_feedback = ""
                break
        record.last_feedback = feedback[:4000]
        previous = completion.text if doc is None else json.dumps(doc)
        prompt = (
            base_prompt
            + "\n\n"
            + _REPAIR_PROMPT.format(previous=previous[:60_000], feedback=feedback)
        )
    record.latency_s = round(time.monotonic() - started, 2)
    if not record.strict_pass:
        record.repair_rounds = max(record.attempts - 1, 0)

    if last_written is not None:
        code, _ = _run_checker("check_graph_structure.py", [str(shell_path)])
        record.graph_check_exit = code
        (
            record.min_catalog_distance,
            record.mean_catalog_distance,
            record.catalog_distance_note,
        ) = _catalog_distances(last_written, record.band, record.length, record.style)

    record_path = out_dir / "records" / (shell_name + ".record.json")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(asdict(record), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return record


def permutation_test(
    rounds_by_leg: dict[str, list[int]],
    *,
    permutations: int = _PERMUTATIONS,
    seed: int = _PERMUTATION_SEED,
) -> tuple[float, float]:
    """Permutation test on the S-1 primary endpoint (repair rounds).

    Statistic: weighted between-leg variance of mean repair rounds,
    ``sum_l n_l * (mean_l - grand_mean)^2``. Labels are permuted over the
    pooled observations; the p-value is the fraction of permuted statistics
    at or above the observed one (with the +1 correction).

    Args:
        rounds_by_leg: Observed repair-round counts per leg label.
        permutations: Number of label shuffles.
        seed: RNG seed, fixed so the registered analysis is reproducible.

    Returns:
        ``(observed_statistic, p_value)``. With fewer than two legs or fewer
        than two total observations the p-value is 1.0.
    """
    labels = [leg for leg, values in rounds_by_leg.items() for _ in values]
    pooled = [v for values in rounds_by_leg.values() for v in values]
    if len(rounds_by_leg) < 2 or len(pooled) < 2:
        return 0.0, 1.0

    def statistic(assign: list[str], values: list[int]) -> float:
        by: dict[str, list[int]] = {}
        for leg, value in zip(assign, values, strict=True):
            by.setdefault(leg, []).append(value)
        grand = statistics.fmean(values)
        return sum(
            len(vals) * (statistics.fmean(vals) - grand) ** 2 for vals in by.values()
        )

    observed = statistic(labels, pooled)
    rng = Random(seed)
    at_or_above = 0
    shuffled = list(labels)
    for _ in range(permutations):
        rng.shuffle(shuffled)
        if statistic(shuffled, pooled) >= observed - 1e-12:
            at_or_above += 1
    p_value = (at_or_above + 1) / (permutations + 1)
    return observed, p_value


def _summarize(records: list[ShellRecord], out_dir: Path) -> None:
    """Write ``summary.json`` and a readable ``summary.md`` for the run."""
    rounds_by_leg: dict[str, list[int]] = {}
    for rec in records:
        if not rec.error:
            rounds_by_leg.setdefault(rec.leg, []).append(rec.repair_rounds)
    observed, p_value = permutation_test(rounds_by_leg)

    by_leg: dict[str, dict[str, Any]] = {}
    for rec in records:
        row = by_leg.setdefault(
            rec.leg,
            {
                "shells": 0,
                "errors": 0,
                "strict_pass": 0,
                "first_pass_clean": 0,
                "repair_rounds": [],
                "output_tokens": 0,
                "min_catalog_distance": [],
            },
        )
        row["shells"] += 1
        if rec.error:
            row["errors"] += 1
            continue
        row["strict_pass"] += int(rec.strict_pass)
        row["first_pass_clean"] += int(rec.first_pass_clean)
        row["repair_rounds"].append(rec.repair_rounds)
        row["output_tokens"] += rec.output_tokens or 0
        if rec.min_catalog_distance is not None:
            row["min_catalog_distance"].append(rec.min_catalog_distance)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "primary_endpoint": {
            "name": "repair rounds to strict pass, pooled across cells",
            "statistic": observed,
            "p_value": p_value,
            "permutations": _PERMUTATIONS,
            "seed": _PERMUTATION_SEED,
            "note": (
                "every other field in this summary is exploratory and "
                "decision-inert per register row S-1"
            ),
        },
        "legs": by_leg,
        "records": [asdict(r) for r in records],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# Skeleton-author comparison summary",
        "",
        (
            f"Primary endpoint (S-1): between-leg statistic {observed:.3f}, "
            f"p = {p_value:.4f} ({_PERMUTATIONS} permutations, seed "
            f"{_PERMUTATION_SEED}). Everything below is exploratory."
        ),
        "",
        (
            "| leg | shells | errors | strict pass | first-pass clean "
            "| mean repair rounds | output tokens | min catalog distance |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for leg, row in sorted(by_leg.items()):
        rr = row["repair_rounds"]
        dmin = row["min_catalog_distance"]
        mean_rounds = f"{statistics.fmean(rr):.2f}" if rr else "-"
        min_dist = f"{min(dmin):.3f}" if dmin else "-"
        lines.append(
            f"| {leg} | {row['shells']} | {row['errors']} "
            f"| {row['strict_pass']} | {row['first_pass_clean']} "
            f"| {mean_rounds} | {row['output_tokens']} | {min_dist} |"
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _emit_prompts_mode(args: argparse.Namespace, cells: list[dict[str, Any]]) -> int:
    """Write the shared system prompt and one author prompt per grid point.

    The input side of a subagent leg (plan section 10): an external driver
    hands these files verbatim to a model-tier subagent, so the subagent leg
    authors under byte-identical instructions to the provider legs.
    """
    prompt_dir = Path(args.emit_prompts)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "system.md").write_text(_AUTHOR_SYSTEM, encoding="utf-8")
    count = 0
    for cell in cells:
        brief_md = _render_markdown(
            build_brief(cell["band"], cell["length"], cell["style"])
        )
        premises = list(cell["premises"])[: args.replicates]
        for replicate, premise in enumerate(premises, start=1):
            name = f"{cell['id']}__r{replicate}.prompt.md"
            (prompt_dir / name).write_text(
                _author_prompt(brief_md, premise), encoding="utf-8"
            )
            count += 1
    print(f"emitted system.md and {count} author prompts -> {prompt_dir}")
    return 0


def _score_shell_mode(args: argparse.Namespace, cells: list[dict[str, Any]]) -> int:
    """Score one externally authored shell and accumulate its grid record.

    This is the harness half of a subagent leg (plan section 10): an external
    driver authors a shell at some model tier, then calls this mode once per
    authored round. The mode applies the identical strict check the provider
    legs get, prints the validator feedback (the driver relays it verbatim
    into the stateless repair prompt), and read-modify-writes the same record
    file the provider path writes, so ``--resume`` and the summary treat
    subagent shells uniformly.

    Returns:
        0 when the shell passes the strict bar, 1 otherwise (including an
        unparseable shell, which costs the leg a round exactly as it does on
        the provider path).
    """
    cell = next((c for c in cells if c["id"] == args.score_cell), None)
    if cell is None:
        print(f"Error: unknown cell '{args.score_cell}'", file=sys.stderr)
        return 2
    premises = list(cell["premises"])
    if not 1 <= args.score_replicate <= len(premises):
        print(f"Error: replicate out of range for cell {cell['id']}", file=sys.stderr)
        return 2
    if not args.out_dir:
        print("Error: --score-shell requires --out-dir", file=sys.stderr)
        return 2
    if not args.score_leg:
        print("Error: --score-shell requires --score-leg", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    shell_name = f"{cell['id']}__r{args.score_replicate}__{args.score_leg}.json"
    record_path = out_dir / "records" / (shell_name + ".record.json")
    record_path.parent.mkdir(parents=True, exist_ok=True)

    if record_path.exists():
        data = json.loads(record_path.read_text(encoding="utf-8"))
        known = {f.name for f in ShellRecord.__dataclass_fields__.values()}
        record = ShellRecord(**{k: v for k, v in data.items() if k in known})
    else:
        record = ShellRecord(
            leg=args.score_leg,
            family=args.score_family,
            cell_id=str(cell["id"]),
            band=str(cell["band"]),
            length=str(cell["length"]),
            style=str(cell["style"]),
            replicate=args.score_replicate,
            premise=premises[args.score_replicate - 1],
        )
    if record.strict_pass:
        print("already passed; not rescoring")
        return 0

    record.attempts += 1
    raw = Path(args.score_shell).read_text(encoding="utf-8")
    doc, parse_reason = _extract_json(raw)
    if doc is None:
        record.parse_failures += 1
        feedback = f"(no skeleton to check) {parse_reason}"
        record.findings_lines_per_round.append(1)
        passed = False
    else:
        shell_path = out_dir / "shells" / shell_name
        shell_path.parent.mkdir(parents=True, exist_ok=True)
        shell_path.write_text(
            json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        record.shell_file = str(shell_path.relative_to(out_dir))
        passed, feedback = _strict_check(
            shell_path, record.band, record.length, record.style
        )
        record.findings_lines_per_round.append(len(feedback.splitlines()))
        code, _ = _run_checker("check_graph_structure.py", [str(shell_path)])
        record.graph_check_exit = code
        (
            record.min_catalog_distance,
            record.mean_catalog_distance,
            record.catalog_distance_note,
        ) = _catalog_distances(doc, record.band, record.length, record.style)
    record.repair_rounds = record.attempts - 1
    if passed:
        record.strict_pass = True
        record.first_pass_clean = record.attempts == 1
        record.last_feedback = ""
    else:
        record.last_feedback = feedback[:4000]
    record_path.write_text(
        json.dumps(asdict(record), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(feedback)
    print(f"score: {'PASS' if passed else 'FAIL'} attempts={record.attempts}")
    return 0 if passed else 1


async def run(args: argparse.Namespace) -> int:
    """Execute the harness per the parsed arguments."""
    vendors = _load_vendors(Path(args.vendors))
    if args.legs:
        wanted = set(args.legs.split(","))
        vendors = [v for v in vendors if v.label in wanted]
        missing = wanted - {v.label for v in vendors}
        if missing:
            print(f"Error: unknown legs {sorted(missing)}", file=sys.stderr)
            return 1
    cells = _load_premises(Path(args.premises))
    if args.cells:
        wanted = set(args.cells.split(","))
        cells = [c for c in cells if c["id"] in wanted]
        if not cells:
            print(f"Error: no cells match {sorted(wanted)}", file=sys.stderr)
            return 1

    _load_env_file(_REPO_ROOT / ".env")
    settings = Settings()

    if args.preflight_only:
        results = await preflight(vendors, settings)
        return 0 if _report_preflight(results) else 1

    if not args.mock:
        results = await preflight(vendors, settings)
        if not _report_preflight(results):
            print("Preflight failed; nothing was spent.", file=sys.stderr)
            return 1

    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else (_DEFAULT_OUT_ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run.json").write_text(
        json.dumps(
            {
                "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "resumed": bool(args.resume),
                "mock": args.mock,
                "vendors": [v.label for v in vendors],
                "cells": [c["id"] for c in cells],
                "replicates": args.replicates,
                "max_repair_rounds": args.max_repair_rounds,
                "max_tokens": args.max_tokens,
                "premises_file": str(args.premises),
                "vendors_file": str(args.vendors),
            },
            indent=1,
        ),
        encoding="utf-8",
    )

    briefs: dict[str, str] = {}
    for cell in cells:
        brief = build_brief(cell["band"], cell["length"], cell["style"])
        briefs[cell["id"]] = _render_markdown(brief)

    # #ASSUME: external resources: a paid run can die mid-grid (the
    # 2026-08-21 registered run hit HTTP 402 when the OpenRouter account ran
    # out of credits, 4 shells in). --resume keeps every cleanly completed
    # shell and re-runs only errored or missing ones, so paid artifacts are
    # never re-bought.
    # #VERIFY: a resumed shell is identified by its (cell, replicate, leg)
    # record having an empty error field; conditions are re-recorded in
    # run.json (the `resumed` flag marks a resumed invocation).
    kept: list[ShellRecord] = []
    done_keys: set[tuple[str, int, str]] = set()
    if args.resume:
        record_dir = out_dir / "records"
        known = {f.name for f in ShellRecord.__dataclass_fields__.values()}
        for record_file in sorted(record_dir.glob("*.record.json")):
            try:
                data = json.loads(record_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("error"):
                continue
            fields_only = {k: v for k, v in data.items() if k in known}
            prior = ShellRecord(**fields_only)
            kept.append(prior)
            done_keys.add((prior.cell_id, prior.replicate, prior.leg))
        print(f"resume: keeping {len(kept)} completed shells")

    semaphore = asyncio.Semaphore(args.concurrency)
    tasks: list[asyncio.Task[ShellRecord]] = []

    async def _bounded(
        record: ShellRecord, provider: Any, brief_md: str
    ) -> ShellRecord:
        # #ASSUME: concurrency: legs share nothing but the semaphore; each
        # task owns its record and its output paths (leg+cell+replicate are
        # unique per task by construction of the loops below).
        # #VERIFY: shell filenames embed cell, replicate, and leg.
        async with semaphore:
            # #CRITICAL: data integrity: a checker/JSON/filesystem error in one
            # grid point must not abort the gather and discard the paid run's
            # aggregate output; author_shell only catches provider errors.
            # #VERIFY: the exception lands in record.error and the record is
            # still persisted and summarized.
            try:
                return await author_shell(
                    provider,
                    record,
                    brief_md,
                    out_dir,
                    max_repair_rounds=args.max_repair_rounds,
                    max_tokens=args.max_tokens,
                )
            except Exception as exc:
                record.error = f"{type(exc).__name__}: {exc}"[:500]
                record_path = (
                    out_dir
                    / "records"
                    / (
                        f"{record.cell_id}__r{record.replicate}__"
                        f"{record.leg}.json.record.json"
                    )
                )
                record_path.parent.mkdir(parents=True, exist_ok=True)
                record_path.write_text(
                    json.dumps(asdict(record), indent=1, ensure_ascii=False),
                    encoding="utf-8",
                )
                return record

    for cell in cells:
        premises = list(cell["premises"])[: args.replicates]
        for replicate, premise in enumerate(premises, start=1):
            for vendor in vendors:
                if (str(cell["id"]), replicate, vendor.label) in done_keys:
                    continue
                record = ShellRecord(
                    leg=vendor.label,
                    family=vendor.lineage(),
                    cell_id=str(cell["id"]),
                    band=str(cell["band"]),
                    length=str(cell["length"]),
                    style=str(cell["style"]),
                    replicate=replicate,
                    premise=premise,
                )
                provider: Any
                if args.mock:
                    provider = _MockAuthor(
                        record.band, record.length, premise, replicate
                    )
                else:
                    provider = _build_provider(vendor, settings, mock=False)
                tasks.append(
                    asyncio.ensure_future(
                        _bounded(record, provider, briefs[record.cell_id])
                    )
                )

    records = [*kept, *(await asyncio.gather(*tasks))]
    _summarize(records, out_dir)
    passes = sum(r.strict_pass for r in records)
    errors = sum(bool(r.error) for r in records)
    print(
        f"done: {len(records)} shells, {passes} strict passes, "
        f"{errors} leg errors -> {out_dir}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Build and run the argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vendors", default=str(_DEFAULT_VENDORS))
    parser.add_argument("--premises", default=str(_DEFAULT_PREMISES))
    parser.add_argument(
        "--cells", default="", help="Comma-separated cell ids (default: all)."
    )
    parser.add_argument(
        "--legs", default="", help="Comma-separated leg labels (default: all)."
    )
    parser.add_argument("--replicates", type=int, default=4)
    parser.add_argument("--max-repair-rounds", type=int, default=4)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=65_536,
        help=(
            "Completion cap per call; a run condition, recorded in run.json. "
            "Default raised from 32768 after the 2026-08-21 smoke: v4 Flash "
            "spent the whole 32k cap on hidden reasoning and returned no "
            "content, and Sonnet 5 truncated twice (the AL-328 shape)."
        ),
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument(
        "--emit-prompts",
        default="",
        help=(
            "Write system.md plus one author prompt per cell x replicate to "
            "this directory and exit; the input side of a subagent leg."
        ),
    )
    parser.add_argument(
        "--score-shell",
        default="",
        help=(
            "Score one externally authored shell file and accumulate its "
            "record in --out-dir; the output side of a subagent leg. "
            "Requires --score-cell, --score-replicate, --score-leg."
        ),
    )
    parser.add_argument("--score-cell", default="")
    parser.add_argument("--score-replicate", type=int, default=0)
    parser.add_argument("--score-leg", default="")
    parser.add_argument("--score-family", default="anthropic")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Keep cleanly completed shells already in --out-dir and author "
            "only the errored or missing grid points."
        ),
    )
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = _parse_args(argv)
    if args.emit_prompts or args.score_shell:
        cells = _load_premises(Path(args.premises))
        if args.cells:
            wanted = set(args.cells.split(","))
            known = {c["id"] for c in cells}
            missing = wanted - known
            if missing:
                print(f"Error: unknown cells {sorted(missing)}", file=sys.stderr)
                return 2
            cells = [c for c in cells if c["id"] in wanted]
        if args.emit_prompts:
            return _emit_prompts_mode(args, cells)
        return _score_shell_mode(args, cells)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
