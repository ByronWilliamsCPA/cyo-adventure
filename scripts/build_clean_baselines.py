#!/usr/bin/env python3
"""Build the checker-repaired clean baselines for the plan reviewer (WP-3.7, D12).

Owner decision (2026-11-22, option 1): "checker-repaired baselines are the clean
sample". D11 lets the plan reviewer see only plans that passed the deterministic
checks, and most of the held-out clean e and f plans are clean as books but carry
checker ERRORs (``AL-884``). The reviewer's clean sample is therefore the
**checker-repaired baseline** of each clean plan: the same mechanical repairs
``repair_baseline`` in ``scripts/build_synthetic_plans.py`` already makes before
it seeds a defect, recorded per plan. This builder reuses that function (it is
loaded by file path, never forked), so a baseline here is byte-identical to the
seed source the synthetic builder uses.

Writes, deterministically and from committed files only (no model call, no
network, no randomness):

* ``docs/planning/evidence/plan-reviewer/clean-baselines/<plan id>.baseline.plan.json``:
  one repaired plan per clean plan (indent 2, ASCII only, trailing newline);
* ``docs/planning/evidence/plan-reviewer/clean-baselines/manifest.json``: schema
  ``clean-baselines/v1``, the items and a ``summary``.

A clean plan here is a ``pass`` plan with a ``strong`` label in either half. The
weak control is excluded, and so are Museum's three minor-only plans
(``PL-the-midnight-museum-postfix``, ``PL-c1``, ``PL-d3``): they are ``pass`` by
ruling (``AL-882``) but their source revision is defective, and the synthetic
builder refuses them as sources too. Every baseline is re-read from the exact
text it will be written as and must raise zero checker ERRORs, or the build fails.

Usage:
    uv run python scripts/build_clean_baselines.py            # write
    uv run python scripts/build_clean_baselines.py --check    # exit 1 on drift
    uv run python scripts/build_clean_baselines.py --summary  # print the counts

Exit codes: 0 ok; 1 drift or a baseline that is not checker-clean; 2 a pinned
revision missing from this checkout.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

if TYPE_CHECKING:
    from types import ModuleType

    from cyo_adventure.validator.report import ValidationReport

REPO: Final = Path(__file__).resolve().parents[1]
_SYNTHETIC_BUILDER: Final = REPO / "scripts/build_synthetic_plans.py"

OUT_REL: Final = "docs/planning/evidence/plan-reviewer/clean-baselines"
OUT_DIR: Final = REPO / OUT_REL
OUT_FILE: Final = OUT_DIR / "manifest.json"
README_LINK: Final = f"{OUT_REL}/README.md"
SCHEMA: Final = "clean-baselines/v1"
SCORED_FOR: Final = "D12"

EXIT_OK: Final = 0
EXIT_FAIL: Final = 1
EXIT_NO_REVISION: Final = 2

TUNING: Final = "tuning"
HELD_OUT: Final = "held_out"

#: The id prefix of the minor-only residuals (owner ruling 2026-11-22, AL-882).
_MINOR_ONLY_PREFIX: Final = "R1121-"

JsonObj = dict[str, object]


class SourceLike(Protocol):
    """The part of ``Source`` in the synthetic builder that this builder reads."""

    item: dict[str, object]

    @property
    def half(self) -> str:
        """Return the source plan's half."""
        ...


class SyntheticBuilder(Protocol):
    """The typed surface of ``scripts/build_synthetic_plans.py`` used here."""

    SeedError: type[Exception]
    MissingRevisionError: type[Exception]

    def load_validation_set(self) -> dict[str, dict[str, object]]:
        """Return the validation set's plan items by id."""
        ...

    def load_source(
        self, plan_id: str, items: dict[str, dict[str, object]]
    ) -> SourceLike:
        """Load and verify one source plan."""
        ...

    def repair_baseline(
        self, source: SourceLike
    ) -> tuple[dict[str, object], list[str]]:
        """Return the source plan with every checker ERROR repaired."""
        ...

    def run_check(
        self, plan: dict[str, object], source: SourceLike
    ) -> ValidationReport:
        """Validate a plan and run ``check_plan`` on it."""
        ...

    def error_rules(self, report: ValidationReport) -> set[str]:
        """Return the rule ids of a report's ERROR findings."""
        ...

    def encode_plan(self, plan: dict[str, object]) -> str:
        """Serialise a plan for its file."""
        ...


def _load_synthetic() -> ModuleType:
    """Load ``scripts/build_synthetic_plans.py`` from its file path.

    ``scripts/`` is not a package, so the synthetic builder is imported by path.
    Its ``repair_baseline``, ``load_source`` and ``run_check`` are reused as they
    are; nothing is copied.

    Returns:
        ModuleType: The synthetic builder module.
    """
    name = "build_synthetic_plans"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SYNTHETIC_BUILDER)
    if spec is None or spec.loader is None:  # pragma: no cover - file is committed
        msg = f"cannot load {_SYNTHETIC_BUILDER}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SYN: Final = cast("SyntheticBuilder", cast("object", _load_synthetic()))


def _obj(value: object) -> JsonObj:
    """Narrow a decoded JSON value to an object.

    Args:
        value: The decoded value.

    Returns:
        JsonObj: The same value, typed.
    """
    if not isinstance(value, dict):
        msg = f"expected a JSON object, got {type(value).__name__}"
        raise TypeError(msg)
    return cast("JsonObj", value)


def _str(value: object) -> str:
    """Narrow a decoded JSON value to a string.

    Args:
        value: The decoded value.

    Returns:
        str: The same value, typed.
    """
    if not isinstance(value, str):
        msg = f"expected a string, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def is_clean_sample(item: JsonObj) -> bool:
    """Return whether a validation-set plan item has a clean baseline.

    Args:
        item: A ``kind: plan`` item.

    Returns:
        bool: True for a strong ``pass`` plan that is not minor-only.
    """
    if item["expected_verdict"] != "pass" or item["label_strength"] != "strong":
        return False
    residuals = cast("list[object]", item["known_residuals"])
    return not any(
        str(_obj(r).get("id")).startswith(_MINOR_ONLY_PREFIX) for r in residuals
    )


def clean_plan_ids(items: dict[str, JsonObj]) -> list[str]:
    """Return the ids that get a baseline, in validation-set order.

    Args:
        items: The validation set's plan items by id.

    Returns:
        list[str]: The clean plan ids.
    """
    return [pid for pid, item in items.items() if is_clean_sample(item)]


def baseline_text(plan: JsonObj) -> str:
    """Serialise a baseline: indent 2, ASCII only, trailing newline.

    Args:
        plan: The repaired plan.

    Returns:
        str: The file text.
    """
    return SYN.encode_plan(plan)


def _build_item(plan_id: str, items: dict[str, JsonObj]) -> tuple[JsonObj, str]:
    """Repair one clean plan, verify it and return its manifest item and text.

    Args:
        plan_id: The validation-set id of the clean plan.
        items: The validation set's plan items by id.

    Returns:
        tuple[JsonObj, str]: The manifest item and the baseline file text.

    Raises:
        SeedError: The repaired plan still raises a checker ERROR.
    """
    source = SYN.load_source(plan_id, items)
    baseline, repairs = SYN.repair_baseline(source)
    text = baseline_text(baseline)
    # #CRITICAL: data-integrity: the manifest claims checker_clean for the file
    # on disk, not for the in-memory dict the repair produced.
    # #VERIFY: re-read the exact text that will be written and fail the build
    # unless it raises zero ERRORs (the same re-read the synthetic builder does).
    report = SYN.run_check(_obj(cast("object", json.loads(text))), source)
    if report.errors:
        fired = sorted(SYN.error_rules(report))
        msg = f"{plan_id}: repaired baseline still raises ERROR rules {fired}"
        raise SYN.SeedError(msg)
    plan_ref = _obj(source.item["plan"])
    item: JsonObj = {
        "id": f"CBL-{plan_id}",
        "kind": "plan",
        "half": source.half,
        "book": copy.deepcopy(_obj(source.item["book"])),
        "source_plan_id": plan_id,
        "source_plan": {"file": plan_ref["file"], "sha256": plan_ref["sha256"]},
        "plan": {
            "file": f"{OUT_REL}/{plan_id}.baseline.plan.json",
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
        "repairs": repairs,
        "repair_count": len(repairs),
        "checker_clean": True,
        "known_residuals": copy.deepcopy(source.item["known_residuals"]),
        "expected_verdict": "pass",
        "scored_for": SCORED_FOR,
        "label_strength": "strong",
        "needed_repair": bool(repairs),
    }
    return item, text


def _summary(items: list[JsonObj]) -> JsonObj:
    """Count the baselines per half and book, and how many needed repair.

    Args:
        items: The manifest items.

    Returns:
        JsonObj: The summary block.
    """

    def block(mine: list[JsonObj]) -> JsonObj:
        return {
            "total": len(mine),
            "needed_repair": sum(1 for i in mine if i["needed_repair"]),
            "no_repair": sum(1 for i in mine if not i["needed_repair"]),
            "repairs": sum(cast("int", i["repair_count"]) for i in mine),
        }

    by_book: JsonObj = {}
    for unit in sorted({_str(_obj(i["book"])["unit"]) for i in items}):
        mine = [i for i in items if _obj(i["book"])["unit"] == unit]
        by_book[unit] = {
            **block(mine),
            "half": _str(mine[0]["half"]),
            "plans": sorted(_str(i["source_plan_id"]) for i in mine),
        }
    return {
        "items": len(items),
        **block(items),
        "by_half": {
            half: block([i for i in items if i["half"] == half])
            for half in (TUNING, HELD_OUT)
        },
        "by_book": by_book,
        "repairs_by_plan": {
            _str(i["source_plan_id"]): i["repair_count"]
            for i in sorted(items, key=lambda x: _str(x["source_plan_id"]))
        },
    }


def build() -> tuple[JsonObj, dict[str, str]]:
    """Build every baseline and the manifest.

    Returns:
        tuple[JsonObj, dict[str, str]]: The manifest document and the baseline
            files (file name to text).

    Raises:
        SeedError: A baseline is not checker-clean.
    """
    plan_items = SYN.load_validation_set()
    built = [_build_item(pid, plan_items) for pid in clean_plan_ids(plan_items)]
    items = [item for item, _text in built]
    doc: JsonObj = {
        "schema": SCHEMA,
        "work_package": "WP-3.7",
        "decision": (
            "D12, owner decision 2026-11-22 (option 1): the reviewer's clean "
            "sample is the checker-repaired baseline of each clean plan"
        ),
        "generator": "scripts/build_clean_baselines.py",
        "repair_function": "scripts/build_synthetic_plans.py::repair_baseline",
        "readme": README_LINK,
        "source_set": "docs/planning/evidence/continuity-reader/validation-set.json",
        "excluded": {
            "minor_only": (
                "PL-the-midnight-museum-postfix, PL-c1 and PL-d3: pass by ruling "
                "(AL-882), source revision defective"
            ),
            "weak_control": "PL-x3 (label_strength weak)",
        },
        "summary": _summary(items),
        "items": items,
    }
    files = {
        f"{_str(i['source_plan_id'])}.baseline.plan.json": text for i, text in built
    }
    return doc, files


def render(doc: JsonObj) -> str:
    """Serialise the manifest deterministically (sorted keys, indent 2).

    Args:
        doc: The manifest document.

    Returns:
        str: The file text.
    """
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def expected_files() -> dict[Path, str]:
    """Build everything and return the text each path must hold.

    Returns:
        dict[Path, str]: Absolute path to text, for the manifest and every plan.
    """
    doc, plans = build()
    files = {OUT_DIR / name: text for name, text in plans.items()}
    files[OUT_FILE] = render(doc)
    return files


def _drift(files: dict[Path, str]) -> list[str]:
    """Compare the expected files with the working tree.

    Args:
        files: Absolute path to expected text.

    Returns:
        list[str]: One line per missing, different or stray file.
    """
    problems: list[str] = []
    for path, text in sorted(files.items()):
        current = path.read_text("utf-8") if path.is_file() else None
        if current != text:
            problems.append(f"drift: {path.relative_to(REPO)}")
    if OUT_DIR.is_dir():
        problems.extend(
            f"stray: {path.relative_to(REPO)}"
            for path in sorted(OUT_DIR.glob("*.plan.json"))
            if path not in files
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run the builder CLI.

    Args:
        argv: Arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: The exit code.
    """
    parser = argparse.ArgumentParser(description="Build the clean-plan baselines.")
    parser.add_argument("--check", action="store_true", help="compare, do not write")
    parser.add_argument("--summary", action="store_true", help="print the counts")
    args = parser.parse_args(argv)
    check = cast("bool", args.check)
    summary = cast("bool", args.summary)
    try:
        files = expected_files()
    except SYN.MissingRevisionError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_NO_REVISION
    except SYN.SeedError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_FAIL
    if summary:
        doc = _obj(cast("object", json.loads(files[OUT_FILE])))
        sys.stdout.write(json.dumps(doc["summary"], indent=2) + "\n")
        return EXIT_OK
    if check:
        problems = _drift(files)
        for problem in problems:
            sys.stderr.write(problem + "; rerun without --check\n")
        return EXIT_FAIL if problems else EXIT_OK
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.plan.json"):
        if stale not in files:
            stale.unlink()
    for path, text in files.items():
        path.write_text(text, "utf-8")
    sys.stdout.write(f"wrote {len(files)} files under {OUT_REL}\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
