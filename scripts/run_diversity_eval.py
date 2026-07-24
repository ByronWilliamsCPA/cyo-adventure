"""Run the offline diversity regression gate over the committed panel.

Usage:
    uv run python scripts/run_diversity_eval.py                      # report, exit 0
    uv run python scripts/run_diversity_eval.py --check              # rules R1-R6
    uv run python scripts/run_diversity_eval.py --update-baseline    # rewrite baseline
    uv run python scripts/run_diversity_eval.py --json out.json      # machine-readable dump
    uv run python scripts/run_diversity_eval.py --panel P --baseline B
    uv run python scripts/run_diversity_eval.py --with-judge [--judge-cache PATH]

A thin argparse shell over ``cyo_adventure.diversity.panel`` (WS-0 Phase 2
harness design doc section 4.1): the R1-R6 rule logic lives in
``diversity/panel.py`` (and counts toward the src coverage gate), this
script only wires argv to that module and prints/exits.

Only ``--check`` gates (exit 1 on any finding); the default run and
``--update-baseline`` always exit 0 so panel-growth iteration is not a wall
of red locally. ``--check`` and ``--update-baseline`` are mutually
exclusive so CI (which always runs ``--check``) can never self-bless a
regression. ``--with-judge`` runs the Phase 3 judge-calibration seam
(design doc section 5): it never gates and refuses to run against the
mock/unset provider.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.panel import (
    PanelManifest,
    PanelResult,
    baseline_payload,
    compare_to_baseline,
    load_panel,
    make_noun_swap_variant,
    run_panel,
)
from cyo_adventure.storybook.models import Storybook

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.diversity.panel import RegressionFinding
    from cyo_adventure.generation.provider import GenerationProvider

_DEFAULT_PANEL: Final[str] = "tests/data/diversity_panel/panel.json"
_DEFAULT_BASELINE: Final[str] = "tests/data/diversity_panel/baseline.json"
_DEFAULT_CALIBRATION: Final[str] = "tests/data/diversity_panel/calibration.json"
_DEFAULT_JUDGE_CACHE: Final[str] = "out/diversity/judge-cache.json"

# The judge rubric prompt version (design doc section 5.2). Bump this when
# the rubric wording changes, so old cache entries are never reused across a
# meaningfully different question.
RUBRIC_VERSION: Final[int] = 1

_JUDGE_SYSTEM: Final[str] = (
    "You are helping calibrate a children's choose-your-own-adventure app's "
    "story-diversity metric. Judge how similar two stories would feel to a "
    "child reader, on a strict 0-10 scale."
)

_SCORE_PATTERN: Final[re.Pattern[str]] = re.compile(r"SCORE:\s*(\d+)", re.IGNORECASE)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        argparse.ArgumentParser: The configured parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--panel", default=_DEFAULT_PANEL, help="Path to the panel manifest JSON."
    )
    parser.add_argument(
        "--baseline", default=_DEFAULT_BASELINE, help="Path to the baseline JSON."
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Write the machine-readable computed result to this path.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Evaluate rules R1-R6 against the baseline; exit 1 on any finding.",
    )
    mode.add_argument(
        "--update-baseline",
        action="store_true",
        help="Recompute and rewrite the baseline; print old-vs-new deltas.",
    )
    parser.add_argument(
        "--with-judge",
        action="store_true",
        help=(
            "Run the Phase 3 judge-calibration pass (never gates; refuses a "
            "mock/unset generation provider)."
        ),
    )
    parser.add_argument(
        "--judge-cache",
        default=_DEFAULT_JUDGE_CACHE,
        help="Path to the judge response cache (gitignored).",
    )
    return parser


def _flatten(obj: object, prefix: str = "") -> dict[str, object]:
    """Flatten a JSON-like value into ``{dotted.path: leaf_value}``.

    Args:
        obj: A JSON-like value (dict, list, or scalar).
        prefix: The dotted path accumulated so far.

    Returns:
        dict[str, object]: One entry per leaf value, keyed by its dotted
            path (list indices rendered as ``[i]``).
    """
    flat: dict[str, object] = {}
    if isinstance(obj, dict):
        for key, value in cast("dict[str, object]", obj).items():
            flat.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(obj, list):
        for index, value in enumerate(cast("list[object]", obj)):
            flat.update(_flatten(value, f"{prefix}[{index}]"))
    else:
        flat[prefix] = obj
    return flat


def _print_deltas(old: Mapping[str, object], new: Mapping[str, object]) -> None:
    """Print every leaf value that differs between two baseline payloads.

    Args:
        old: The previous baseline payload (``{}`` if none existed).
        new: The freshly computed baseline payload.
    """
    old_flat = _flatten(dict(old))
    new_flat = _flatten(dict(new))
    changed = False
    for key in sorted(set(old_flat) | set(new_flat)):
        old_value = old_flat.get(key, "<absent>")
        new_value = new_flat.get(key, "<absent>")
        if old_value != new_value:
            changed = True
            sys.stdout.write(f"delta {key}: {old_value} -> {new_value}\n")
    if not changed:
        sys.stdout.write("no baseline deltas (identical to the previous baseline)\n")


def _print_report(result: PanelResult) -> None:
    """Print the human report: verdict table, lexical table, PS matrix, RAR.

    Args:
        result: The freshly computed panel result.
    """
    sys.stdout.write("=== ATG pairs ===\n")
    for key, pair in sorted(result.atg_pairs.items()):
        report = pair.report
        sys.stdout.write(
            f"{key}: {report.verdict.value} median={report.median_distance:.3f} "
            f"p25={report.p25_distance:.3f} mean_d_big={report.mean_bigram_distance:.3f}\n"
        )
    sys.stdout.write("=== Structural (cross-tree) distances ===\n")
    for key, value in sorted(result.struct_pairs.items()):
        sys.stdout.write(f"{key}: {value:.3f}\n")
    sys.stdout.write("=== Lexical guards ===\n")
    for fill_id, metrics in sorted(result.fills.items()):
        lexical = metrics.lexical
        sys.stdout.write(
            f"{fill_id}: distinct_1={lexical.distinct_1:.3f} "
            f"distinct_2={lexical.distinct_2:.3f} "
            f"self_bleu_lite={lexical.self_bleu_lite:.3f}\n"
        )
    sys.stdout.write(
        "=== PS / RAR (trend-only, uncalibrated priors; never gates CI) ===\n"
    )
    for key, score in sorted(result.ps_pairs.items()):
        sys.stdout.write(f"{key}: PS={score.perceived_similarity:.3f}\n")
    sys.stdout.write(f"rar_sequence={result.rar_value:.3f}\n")
    sys.stdout.write("=== Brief pairs (tau-theme) ===\n")
    for outcome in result.brief_pairs:
        sys.stdout.write(
            f"{outcome.key}: similarity={outcome.similarity:.3f} similar={outcome.similar}\n"
        )


def _print_findings(findings: Sequence[RegressionFinding]) -> None:
    """Print every regression finding, one per line.

    Args:
        findings: The findings from :func:`compare_to_baseline`.
    """
    for finding in findings:
        sys.stdout.write(
            f"{finding.rule:3} {finding.subject}: {finding.message} "
            f"(observed={finding.observed}, allowed={finding.allowed})\n"
        )
    sys.stdout.write(f"findings={len(findings)}\n")


def _load_baseline(path: Path) -> dict[str, object]:
    """Load a baseline JSON file, tolerating a missing or malformed one.

    Args:
        path: The baseline file path.

    Returns:
        dict[str, object]: The parsed baseline, or ``{}`` when the file is
            missing, unreadable, not valid JSON, or not a JSON object (an
            empty mapping fails :func:`~cyo_adventure.diversity.panel.
            compare_to_baseline`'s schema_version check by construction,
            which is rule R6's "baseline missing" case).
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return cast("dict[str, object]", raw) if isinstance(raw, dict) else {}


def _canonical_text(story: Storybook) -> str:
    """Return the canonical ``(node_id, body)`` text used for judge hashing/prompts.

    Args:
        story: The story to render.

    Returns:
        str: A deterministic JSON rendering of every node in story order.
    """
    return json.dumps([[node.id, node.body] for node in story.nodes])


def _cache_key(text_a: str, text_b: str) -> str:
    """Return the order-independent judge-cache key for one story pair.

    Args:
        text_a: The first story's canonical text.
        text_b: The second story's canonical text.

    Returns:
        str: ``"{hash_a}:{hash_b}:{RUBRIC_VERSION}"`` with the two hashes
            sorted, so ``(a, b)`` and ``(b, a)`` hit the same cache entry.
    """
    # #ASSUME: security: sha256 (not md5/sha1) for a cache key derived from
    # story content; this is a cache-collision concern, not an authentication
    # boundary, but there is no reason to use a weaker hash here.
    hash_a = hashlib.sha256(text_a.encode("utf-8")).hexdigest()
    hash_b = hashlib.sha256(text_b.encode("utf-8")).hexdigest()
    first, second = sorted((hash_a, hash_b))
    return f"{first}:{second}:{RUBRIC_VERSION}"


def _judge_prompt(a_text: str, b_text: str, band: str) -> str:
    """Build the fixed judge rubric prompt for one story pair.

    Args:
        a_text: Story A's canonical text.
        b_text: Story B's canonical text.
        band: The pair's age band, for prompt context.

    Returns:
        str: The user-role prompt (design doc section 5.2).
    """
    return (
        f"Age band: {band}\n\n"
        f"Story A:\n{a_text}\n\n"
        f"Story B:\n{b_text}\n\n"
        "Would a child who read story A feel story B is the same adventure? "
        "Reply with `SCORE: <0-10>` on the first line (0 = a completely new "
        "adventure, 10 = the same adventure) and one sentence why."
    )


def _parse_judge_score(response: str) -> int | None:
    """Parse a judge model's ``SCORE: <n>`` reply.

    Args:
        response: The raw model completion.

    Returns:
        int | None: The parsed score in ``[0, 10]``, or ``None`` when the
            response has no parseable, in-range score (recorded as a
            warning by the caller; never raises).
    """
    match = _SCORE_PATTERN.search(response)
    if match is None:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 10 else None


async def _judge_pair(
    provider: GenerationProvider, a_text: str, b_text: str, band: str
) -> int | None:
    """Score one story pair's perceived similarity with a judge model.

    Unit-testable in isolation with :class:`~cyo_adventure.generation.
    provider.MockProvider` and zero network (design doc section 5.1).

    Args:
        provider: The (live or mock) generation provider.
        a_text: Story A's canonical text.
        b_text: Story B's canonical text.
        band: The pair's age band, for prompt context.

    Returns:
        int | None: The parsed 0-10 score, or ``None`` for an unparseable
            reply.
    """
    response = await provider.complete(
        system=_JUDGE_SYSTEM,
        prompt=_judge_prompt(a_text, b_text, band),
        max_tokens=200,
    )
    return _parse_judge_score(response)


async def _scored_pair(
    cache: dict[str, object],
    provider: GenerationProvider,
    a_text: str,
    b_text: str,
    band: str,
) -> int | None:
    """Return a judge score for one pair, serving from ``cache`` when possible.

    Args:
        cache: The mutable judge-cache mapping (updated in place).
        provider: The (live or mock) generation provider.
        a_text: Story A's canonical text.
        b_text: Story B's canonical text.
        band: The pair's age band.

    Returns:
        int | None: The (possibly cached) judge score.
    """
    key = _cache_key(a_text, b_text)
    if key in cache:
        cached = cache[key]
        return cached if isinstance(cached, int) else None
    score = await _judge_pair(provider, a_text, b_text, band)
    cache[key] = score
    return score


def _rank(values: Sequence[float]) -> list[float]:
    """Return the average-tie rank of each value (1-indexed).

    Args:
        values: The values to rank.

    Returns:
        list[float]: The rank of each input value, in input order; tied
            values share their average rank.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        tie_end = index
        while (
            tie_end + 1 < len(order)
            and values[order[tie_end + 1]] == values[order[index]]
        ):
            tie_end += 1
        average_rank = (index + tie_end) / 2 + 1
        for position in range(index, tie_end + 1):
            ranks[order[position]] = average_rank
        index = tie_end + 1
    return ranks


def _spearman_rho(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Return the Spearman rank correlation between two equal-length sequences.

    Args:
        xs: The first sequence.
        ys: The second sequence.

    Returns:
        float | None: The rank correlation, or ``None`` when there are
            fewer than two pairs or either sequence has zero rank variance.
    """
    if len(xs) < 2:
        return None
    rank_x, rank_y = _rank(xs), _rank(ys)
    mean_x, mean_y = sum(rank_x) / len(rank_x), sum(rank_y) / len(rank_y)
    covariance = sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(rank_x, rank_y, strict=True)
    )
    variance_x = sum((x - mean_x) ** 2 for x in rank_x)
    variance_y = sum((y - mean_y) ** 2 for y in rank_y)
    denominator = math.sqrt(variance_x * variance_y)
    return covariance / denominator if denominator else None


def _ps_bins(
    ps_values: Sequence[float], judge_scores: Sequence[int]
) -> list[dict[str, object]]:
    """Return the ten 0.1-wide PS-to-judge-score bins (design doc section 5.3).

    Args:
        ps_values: The PS proxy value for each scored pair.
        judge_scores: The judge score for each scored pair, aligned by index.

    Returns:
        list[dict[str, object]]: Ten ``{"lo", "hi", "mean_judge"}`` bins;
            ``mean_judge`` is ``None`` for an empty bin.
    """
    bins: list[dict[str, object]] = []
    for tenth in range(10):
        lo, hi = tenth / 10, (tenth + 1) / 10
        in_bin = [
            score
            for value, score in zip(ps_values, judge_scores, strict=True)
            if (lo <= value < hi) or (hi >= 1.0 and value >= 1.0)
        ]
        bins.append(
            {
                "lo": lo,
                "hi": hi,
                "mean_judge": sum(in_bin) / len(in_bin) if in_bin else None,
            }
        )
    return bins


def _proposed_repeat_threshold(
    ps_values: Sequence[float], judge_scores: Sequence[int]
) -> float | None:
    """Propose a repeat-adventure PS threshold from the judge-scored pairs.

    Args:
        ps_values: The PS proxy value for each scored pair.
        judge_scores: The judge score for each scored pair, aligned by index.

    Returns:
        float | None: The midpoint between the highest PS among
            judge-scored-"different" pairs (``<= 3``) and the lowest PS
            among judge-scored-"same" pairs (``>= 7``); ``None`` when
            either set is empty or the two sets overlap (design doc
            section 5.3).
    """
    low = [
        value
        for value, score in zip(ps_values, judge_scores, strict=True)
        if score <= 3
    ]
    high = [
        value
        for value, score in zip(ps_values, judge_scores, strict=True)
        if score >= 7
    ]
    if not low or not high:
        return None
    max_low, min_high = max(low), min(high)
    return (max_low + min_high) / 2 if max_low < min_high else None


def _proposed_weights(
    components: Sequence[tuple[float, float, float]], judge_scores: Sequence[int]
) -> dict[str, float] | None:
    """Grid-search PS weights maximizing Spearman rho against judge scores.

    A smoke calibration over the panel's small judged-pair count (design doc
    section 5.3): a 0.05-step search over the ``(leaf, struct, theme)``
    simplex.

    Args:
        components: Per-pair ``(leaf_similarity, structural_similarity,
            theme_similarity)`` triples, aligned with ``judge_scores``.
        judge_scores: The judge score for each scored pair.

    Returns:
        dict[str, float] | None: The best ``{"leaf", "struct", "theme"}``
            weights found, or ``None`` when fewer than two pairs are scored.
    """
    if len(components) < 2:
        return None
    step = 0.05
    steps = round(1.0 / step)
    best_weights: tuple[float, float, float] | None = None
    best_rho = float("-inf")
    judge_floats = [float(score) for score in judge_scores]
    for i in range(steps + 1):
        leaf = i * step
        for j in range(steps + 1 - i):
            struct = j * step
            theme = max(1.0 - leaf - struct, 0.0)
            ps_values = [
                leaf * leaf_sim + struct * struct_sim + theme * theme_sim
                for leaf_sim, struct_sim, theme_sim in components
            ]
            rho = _spearman_rho(ps_values, judge_floats)
            if rho is not None and rho > best_rho:
                best_rho, best_weights = rho, (leaf, struct, theme)
    if best_weights is None:
        return None
    return {
        "leaf": round(best_weights[0], 2),
        "struct": round(best_weights[1], 2),
        "theme": round(best_weights[2], 2),
    }


def _load_stories_for_judge(
    manifest: PanelManifest, repo_root: Path
) -> dict[str, Storybook]:
    """Reload every panel fill and synthetic as a Storybook, for judge prompts.

    Args:
        manifest: The panel manifest.
        repo_root: The repository root the manifest's fixture paths are
            relative to.

    Returns:
        dict[str, Storybook]: Every fill and synthetic, keyed by panel id.
    """
    stories: dict[str, Storybook] = {}
    for fill in manifest.fills:
        raw = json.loads((repo_root / fill.path).read_text(encoding="utf-8"))
        stories[fill.id] = Storybook.model_validate(raw)
    for synthetic in manifest.synthetic:
        base = stories[synthetic.base]
        stories[synthetic.id] = (
            make_noun_swap_variant(base, synthetic.swaps)
            if synthetic.kind == "noun_swap"
            else base
        )
    return stories


def _run_judge_pass(
    manifest: PanelManifest,
    result: PanelResult,
    repo_root: Path,
    cache_path: Path,
    calibration_path: Path,
) -> None:
    """Run the Phase 3 judge-calibration pass and write ``calibration.json``.

    Args:
        manifest: The panel manifest.
        result: The freshly computed panel result (for PS proxy values).
        repo_root: The repository root.
        cache_path: Where to read/write the judge response cache.
        calibration_path: Where to write the calibration output.

    Raises:
        ConfigurationError: If the resolved generation provider is
            ``mock`` (never a live provider) or otherwise cannot be built.
    """
    if settings.generation_provider == "mock":
        msg = (
            "--with-judge requires a live GENERATION_PROVIDER (the resolved "
            "provider is 'mock'); set GENERATION_PROVIDER and its "
            "credentials before running the judge pass"
        )
        raise ValidationError(msg, field="generation_provider", value="mock")
    # Imported lazily so the default and --check paths never load the generation
    # provider stack (the anthropic SDK and its optional deps); only the judge
    # pass needs a live provider. Keeps the offline CI gate lightweight.
    from cyo_adventure.generation.provider import build_provider  # noqa: PLC0415

    provider = build_provider(settings)

    cache = _load_baseline(cache_path)  # same tolerant-load shape as a baseline

    stories = _load_stories_for_judge(manifest, repo_root)
    bands = {fill.id: fill.band for fill in manifest.fills}
    for synthetic in manifest.synthetic:
        bands[synthetic.id] = bands.get(synthetic.base, "8-11")

    pairs = [(pair.a, pair.b) for pair in manifest.atg_pairs]
    pairs.extend(manifest.cross_tree_pairs)

    judged: list[dict[str, object]] = []
    for a_id, b_id in pairs:
        first, second = sorted((a_id, b_id))
        key = f"{first}~{second}"
        score = asyncio.run(
            _scored_pair(
                cache,
                provider,
                _canonical_text(stories[a_id]),
                _canonical_text(stories[b_id]),
                bands.get(a_id, "8-11"),
            )
        )
        judged.append(
            {
                "key": key,
                "ps_proxy": round(result.ps_pairs[key].perceived_similarity, 6),
                "judge_score": score,
            }
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    scored = [entry for entry in judged if entry["judge_score"] is not None]
    ps_values = [cast("float", entry["ps_proxy"]) for entry in scored]
    judge_scores = [cast("int", entry["judge_score"]) for entry in scored]
    components = [
        (
            result.ps_pairs[cast("str", entry["key"])].leaf_similarity,
            result.ps_pairs[cast("str", entry["key"])].structural_similarity,
            result.ps_pairs[cast("str", entry["key"])].theme_similarity,
        )
        for entry in scored
    ]

    calibration = {
        "rubric_version": RUBRIC_VERSION,
        "pairs": judged,
        "spearman_rho": _spearman_rho(ps_values, judge_scores),
        "ps_bins": _ps_bins(ps_values, judge_scores),
        "proposed_repeat_threshold": _proposed_repeat_threshold(
            ps_values, judge_scores
        ),
        "proposed_weights": _proposed_weights(components, judge_scores),
    }
    calibration_path.parent.mkdir(parents=True, exist_ok=True)
    calibration_path.write_text(
        json.dumps(calibration, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    sys.stdout.write(
        f"judge pass complete: {len(scored)}/{len(judged)} pairs scored, "
        f"spearman_rho={calibration['spearman_rho']}, "
        f"wrote {calibration_path}\n"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the diversity eval harness.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        int: ``0`` on a clean run/update, ``1`` on any ``--check`` finding
            or an unreadable panel/fixture, ``2`` on an argparse usage
            error (e.g. ``--check`` combined with ``--update-baseline``).
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    # #ASSUME: security: --panel/--baseline/--judge-cache/--json are
    # canonicalized with .resolve() (CWE-23 hardening, Snyk python/PT), but
    # deliberately NOT contained to a fixed base (the
    # generation/import_cli.py::_load_blob idiom):
    # tests/unit/test_diversity_panel.py exercises --baseline against a
    # pytest tmp_path fixture well outside the repo tree with no chdir,
    # proving arbitrary-location paths are legitimate, exercised behavior
    # that containment would reject. The CI invocation (ci.yml) only ever
    # passes --check with no path args, so the repo-relative defaults are
    # the only path this gate needs to keep working there. No privilege
    # boundary is crossed either way: the operator invoking this dev-only
    # harness already has full filesystem access.
    # #VERIFY: any future change adding a fixed base must re-run
    # test_diversity_panel.py first; a rejection there means real behavior
    # broke.
    repo_root = Path.cwd()
    panel_path = Path(args.panel).resolve()
    baseline_path = Path(args.baseline).resolve()

    try:
        manifest = load_panel(panel_path)
        result = run_panel(manifest, repo_root)
    except ValidationError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if args.with_judge:
        try:
            _run_judge_pass(
                manifest,
                result,
                repo_root,
                Path(args.judge_cache).resolve(),
                Path(_DEFAULT_CALIBRATION).resolve(),
            )
        except ValidationError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 1

    if args.json_path:
        Path(args.json_path).resolve().write_text(
            json.dumps(baseline_payload(result), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.update_baseline:
        _print_report(result)
        old_baseline = _load_baseline(baseline_path)
        new_payload = baseline_payload(result)
        _print_deltas(old_baseline, new_payload)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(new_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return 0

    if args.check:
        baseline = _load_baseline(baseline_path)
        findings = compare_to_baseline(result, baseline, manifest)
        _print_findings(findings)
        return 1 if findings else 0

    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
