"""Prototype the deterministic strip-all-then-reinsert sentinel fallback (plan 3.4).

``scripts/measure_sentinel_survival.py --save-fills`` persists every trial's
specimen slug, provider, slot bindings, bound skeleton, and filled storybook
under ``<run-dir>/fills/``. This script reads that ``fills/`` directory back,
runs each saved fill through
``cyo_adventure.measurement.reinsertion.reinsert_sentinels`` (the pure,
deterministic re-insertion algorithm: strip every model-emitted sentinel,
then re-wrap whole-word matches of each expected token's inner value), and
writes an aggregated viability report into the SAME run directory
(``reinsertion-report.json`` / ``reinsertion-report.md``), alongside the
original ``report.json`` / ``report.md`` sentinel-SURVIVAL numbers.

This script performs no generation and calls no provider: it is a pure,
offline re-analysis of already-saved fills. It never mutates anything under
``fills/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from cyo_adventure.measurement.reinsertion import (
    ReinsertionTrial,
    aggregate_reinsertion,
    reinsert_sentinels,
    render_json,
    render_markdown,
)


class MalformedFillError(Exception):
    """A saved fill file's JSON parsed but does not have the expected shape.

    Distinct from `json.JSONDecodeError` (the bytes are not JSON at all) and
    from `OSError` (the file could not be read). All three are recoverable
    per-run input errors that `main` turns into a diagnostic plus exit 1;
    they are separated so the message can say which one happened.

    This replaces the `TypeError` these checks used to raise. A fill file with
    a string where an object belongs is bad DATA, not a bad call, and
    `TypeError` is what Python itself raises when the surrounding code has a
    genuine bug. Conflating the two meant `main`'s ``except TypeError`` would
    also have swallowed a real programming error in `reinsert_sentinels` and
    reported it as a malformed input file.
    """


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir",
        help=(
            "A sentinel-survival run directory produced by "
            "measure_sentinel_survival.py --save-fills "
            "(e.g. results/sentinel-survival/<run-slug>); must contain a "
            "fills/ subdirectory of saved trial JSON files."
        ),
    )
    return parser


def _load_fill(path: Path) -> tuple[str, str, dict[str, object], dict[str, object]]:
    """Load one saved fill file written by ``_write_fill``.

    Args:
        path: The saved fill JSON file's path.

    Returns:
        tuple[str, str, dict[str, object], dict[str, object]]: The
            ``(specimen_slug, provider, bound_skeleton, filled_storybook)``
            fields this script needs; ``slot_bindings`` is loaded implicitly
            by the raw parse but not used here (re-insertion recomputes
            expectations from ``bound_skeleton`` alone).

    Raises:
        MalformedFillError: If the file's JSON root is not an object, or any
            required field is missing or the wrong type.
        json.JSONDecodeError: If the file is not valid JSON at all.
        OSError: If the file cannot be read or is not valid UTF-8.
    """
    raw: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(raw, dict):
        msg = f"expected a JSON object in {path}"
        raise MalformedFillError(msg)
    payload = cast("dict[str, object]", raw)

    specimen_slug = payload.get("specimen_slug")
    provider = payload.get("provider")
    bound_skeleton = payload.get("bound_skeleton")
    filled_storybook = payload.get("filled_storybook")
    if not isinstance(specimen_slug, str):
        msg = f"{path}: 'specimen_slug' missing or not a string"
        raise MalformedFillError(msg)
    if not isinstance(provider, str):
        msg = f"{path}: 'provider' missing or not a string"
        raise MalformedFillError(msg)
    if not isinstance(bound_skeleton, dict):
        msg = f"{path}: 'bound_skeleton' missing or not an object"
        raise MalformedFillError(msg)
    if not isinstance(filled_storybook, dict):
        msg = f"{path}: 'filled_storybook' missing or not an object"
        raise MalformedFillError(msg)
    return (
        specimen_slug,
        provider,
        cast("dict[str, object]", bound_skeleton),
        cast("dict[str, object]", filled_storybook),
    )


def _analyze_fills(fills_dir: Path) -> list[ReinsertionTrial]:
    """Load and analyze every saved fill file in ``fills_dir``, in sorted order.

    Args:
        fills_dir: The run directory's ``fills/`` subdirectory.

    Returns:
        list[ReinsertionTrial]: One trial per fill file.

    Raises:
        MalformedFillError: On any fill file that cannot be read, is not valid
            JSON, or whose JSON has the wrong shape. The offending path is
            always part of the message.
    """
    trials: list[ReinsertionTrial] = []
    for path in sorted(fills_dir.glob("*.json")):
        # #CRITICAL: external-resources: `--save-fills` writes one file per
        # trial across a long provider run, so a run killed mid-write leaves a
        # TRUNCATED file (`JSONDecodeError`) and a directory that was moved or
        # made read-only leaves an unreadable one (`OSError`). Both used to
        # escape `main`'s `except TypeError` and exit with a traceback. They
        # are converted here rather than caught in `main` because
        # `JSONDecodeError`'s own message names only a line and column, never
        # the file: re-raising with `path` is the only way the operator learns
        # WHICH of a few hundred fill files is the bad one.
        # #VERIFY: `raise ... from exc` keeps the original as `__cause__`, so
        # the specific parse or I/O failure survives in the traceback.
        try:
            specimen_slug, provider, bound_skeleton, filled_storybook = _load_fill(path)
        except (json.JSONDecodeError, OSError) as exc:
            msg = f"{path}: unreadable or not valid JSON: {exc}"
            raise MalformedFillError(msg) from exc
        result = reinsert_sentinels(bound_skeleton, filled_storybook)
        trials.append(
            ReinsertionTrial(
                specimen_slug=specimen_slug, provider=provider, result=result
            )
        )
    return trials


def main(argv: list[str] | None = None) -> int:
    """Analyze a saved-fills run directory and write the re-insertion report.

    Args:
        argv: Command-line arguments, or ``None`` to use ``sys.argv``.

    Returns:
        int: 0 on success, 1 on any input or fill-file error.
    """
    args = _build_parser().parse_args(argv)
    run_dir = Path(cast("str", args.run_dir))
    fills_dir = run_dir / "fills"

    if not fills_dir.is_dir():
        hint = "re-run measure_sentinel_survival.py with --save-fills first"
        sys.stderr.write(f"error: no fills/ directory under {run_dir}; {hint}\n")
        return 1

    # `_analyze_fills` normalizes every per-file failure (bad shape, bad JSON,
    # unreadable) into `MalformedFillError` with the path attached, so this is
    # the single recoverable-input catch. It is deliberately NOT `ValueError`,
    # which `json.JSONDecodeError` subclasses: a `ValueError` raised by the
    # re-insertion algorithm itself is a bug, and must not be reported to the
    # operator as a bad input file.
    try:
        trials = _analyze_fills(fills_dir)
    except MalformedFillError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if not trials:
        sys.stderr.write(f"error: {fills_dir} contains no saved fill files\n")
        return 1

    try:
        data = aggregate_reinsertion(trials)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    (run_dir / "reinsertion-report.json").write_text(
        json.dumps(render_json(data), indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "reinsertion-report.md").write_text(
        render_markdown(data), encoding="utf-8"
    )

    sys.stdout.write(
        " ".join(
            [
                f"sentinel-reinsertion: {data.clean_trials}/{data.total_trials} clean",
                f"({data.reinsertion_clean_rate:.1%})",
            ]
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
