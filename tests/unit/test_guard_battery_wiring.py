"""The guard battery must have an invoker, and the invoker must be able to fail.

`UW-C453` / `AL-726`: ``scripts/run_guard_battery.py`` registers several guards
``gating=True`` and was invoked by no workflow, no pre-commit hook and no nox
session, so every "gating" guard gated nothing. ``tests/unit/test_guard_gating.py``
asserts what the battery registers and with which flags, which is exactly why
the gap survived a green suite: deregistering a guard failed a test, deleting the
runner failed none. This module is the assertion that was missing. It pins:

* that at least one workflow under ``.github/workflows/`` runs the script, and
  that the invocation passes ``--corpus`` (so it covers the committed corpus
  rather than a hand-picked book) and ``--check`` (so a gating failure can
  fail the step; without the flag the script exits 0 unconditionally, the
  AL-293 "a guard that cannot fail" shape at the level of the whole battery);
* that ``noxfile.py`` names the script, so the local parity path exists;
* the corpus enumeration itself: every committed ``out/*.filled.json`` resolves
  to exactly one shell, deterministically, and a shell with no narrative
  contract has its two contract-scoped guards reported as SKIPPED and
  non-gating, never as passed;
* that the concurrent corpus driver attributes every book's rows to the right
  slug, which is the property the ``--jobs`` thread pool relies on.

``scripts/`` is not an importable package (no ``__init__.py``, by design; see
the INP per-file-ignore in pyproject.toml), so the module is loaded from its
file path via importlib, mirroring ``test_guard_gating.py``.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_SCRIPT = "scripts/run_guard_battery.py"

_SPEC = importlib.util.spec_from_file_location(
    "run_guard_battery_wiring", _REPO_ROOT / _SCRIPT
)
assert _SPEC is not None
assert _SPEC.loader is not None
battery_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = battery_module
_SPEC.loader.exec_module(battery_module)


def _run_steps_naming_the_script() -> list[tuple[str, str, str]]:
    """Collect every ``run:`` step in every workflow that mentions the script.

    Returns:
        ``(workflow file name, job id, run script)`` for each such step.
    """
    yaml = YAML(typ="safe")
    found: list[tuple[str, str, str]] = []
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        with path.open(encoding="utf-8") as handle:
            doc: Any = yaml.load(handle)
        jobs: dict[str, Any] = doc.get("jobs", {}) if isinstance(doc, dict) else {}
        for job_id, job in jobs.items():
            for step in job.get("steps", []) or []:
                run = step.get("run")
                if isinstance(run, str) and _SCRIPT in run:
                    found.append((path.name, str(job_id), run))
    return found


# --------------------------------------------------------------------------
# The battery is named by a workflow and by nox
# --------------------------------------------------------------------------


def test_a_workflow_runs_the_guard_battery() -> None:
    """Deleting the runner job must fail the suite, not just the checks page.

    Comments do not count: only a ``run:`` step's script is scanned, so a
    workflow that merely describes the battery in a header comment does not
    satisfy this test.
    """
    assert _run_steps_naming_the_script(), (
        f"no workflow under {_WORKFLOWS} runs {_SCRIPT}; every gating guard it "
        "registers gates nothing (UW-C453)"
    )


def test_the_workflow_invocation_covers_the_corpus_and_can_fail() -> None:
    """Every workflow invocation passes ``--corpus`` and ``--check``.

    ``--corpus`` is what ties the run to the committed fills rather than to a
    book someone happened to name. ``--check`` is what lets the exit status be
    non-zero; without it the battery prints FAIL rows and exits 0, so a step
    that omitted it could show green over a corpus that is entirely red.
    """
    for workflow, job_id, run in _run_steps_naming_the_script():
        # Shell continuations are joined so a wrapped command is one token list.
        tokens = shlex.split(run.replace("\\\n", " "), comments=True)
        assert "--corpus" in tokens, (
            f"{workflow}:{job_id} runs {_SCRIPT} without --corpus"
        )
        assert "--check" in tokens, (
            f"{workflow}:{job_id} runs {_SCRIPT} without --check"
        )


def test_the_ci_job_is_accounted_for_by_the_gate_contract() -> None:
    """The ci.yml job is either gated or explicitly listed as advisory.

    ``test_ci_gate_contract.py`` enforces this for every ci.yml job already;
    this restates it for the battery specifically so a reader of THIS file
    learns where the gating decision lives, and so moving the job to another
    workflow without a replacement in ci.yml is a visible change here.
    """
    jobs = {
        job_id
        for workflow, job_id, _ in _run_steps_naming_the_script()
        if workflow == "ci.yml"
    }
    assert jobs, f"ci.yml has no job running {_SCRIPT}"

    yaml = YAML(typ="safe")
    with (_WORKFLOWS / "ci.yml").open(encoding="utf-8") as handle:
        ci: Any = yaml.load(handle)
    gate_needs = set(ci["jobs"]["ci-gate"]["needs"])
    contract_test = (
        _REPO_ROOT / "tests" / "unit" / "test_ci_gate_contract.py"
    ).read_text(encoding="utf-8")
    for job_id in jobs:
        assert job_id in gate_needs or f'"{job_id}":' in contract_test, (
            f"{job_id} is neither in ci-gate's needs: nor in UNGATED_JOBS"
        )


def test_noxfile_names_the_guard_battery() -> None:
    """A local parity session exists, so CI is not the only way to run it."""
    noxfile = (_REPO_ROOT / "noxfile.py").read_text(encoding="utf-8")

    assert _SCRIPT in noxfile
    assert "--corpus" in noxfile


# --------------------------------------------------------------------------
# Corpus enumeration
# --------------------------------------------------------------------------


def test_committed_corpus_enumerates_every_fill_to_exactly_one_shell() -> None:
    """Every ``out/*.filled.json`` resolves; the count matches the glob.

    A fill whose slug matches no shell would make the battery run against
    nothing for that book, so enumeration raises rather than skipping. This
    runs against the real tree, so it also documents the corpus size the
    advisory job's runtime estimate is based on.
    """
    books = battery_module.corpus_books(_REPO_ROOT)
    fills = sorted((_REPO_ROOT / "out").glob("*.filled.json"))

    assert len(books) == len(fills)
    assert [b.filled for b in books] == fills, (
        "enumeration order must be the sorted glob"
    )
    for book in books:
        assert book.skeleton.is_file()
        assert book.skeleton.parent.parent == _REPO_ROOT / "skeletons"
        assert book.skeleton.name == f"{book.slug}.json"
        if book.contract is not None:
            assert book.contract.name == f"{book.slug}.narrative.json"
            assert book.contract.parent == book.skeleton.parent


def test_enumeration_never_substitutes_the_theme_contract(tmp_path: Path) -> None:
    """A ``.contract.json`` sidecar is not a narrative contract.

    Handing the theme contract to ``check_device_vocabulary`` produces a DV-0
    "no world_recipe.requires mapping" error on every book, which is how the
    first corpus sweep read as 28 vocabulary failures that were really one
    input-shape mistake. Only ``.narrative.json`` may fill the contract slot.
    """
    (tmp_path / "out").mkdir()
    (tmp_path / "skeletons" / "5-8").mkdir(parents=True)
    (tmp_path / "out" / "a-book.filled.json").write_text("{}", encoding="utf-8")
    (tmp_path / "skeletons" / "5-8" / "a-book.json").write_text("{}", encoding="utf-8")
    (tmp_path / "skeletons" / "5-8" / "a-book.contract.json").write_text(
        "{}", encoding="utf-8"
    )

    [book] = battery_module.corpus_books(tmp_path)

    assert book.contract is None


def test_enumeration_fails_closed_on_an_empty_or_ambiguous_corpus(
    tmp_path: Path,
) -> None:
    """No fills, an orphan fill, and a slug in two bands each raise."""
    (tmp_path / "out").mkdir()
    (tmp_path / "skeletons" / "3-5").mkdir(parents=True)
    (tmp_path / "skeletons" / "5-8").mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        battery_module.corpus_books(tmp_path)

    (tmp_path / "out" / "orphan.filled.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        battery_module.corpus_books(tmp_path)

    (tmp_path / "skeletons" / "3-5" / "orphan.json").write_text("{}", encoding="utf-8")
    (tmp_path / "skeletons" / "5-8" / "orphan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="resolves to 2 shells"):
        battery_module.corpus_books(tmp_path)


# --------------------------------------------------------------------------
# A missing narrative contract is disclosed, not passed
# --------------------------------------------------------------------------


def _stubbed_battery(contract: str | None) -> tuple[list[str], list[Any]]:
    calls: list[str] = []

    def _fake_run(script: str, *args: str) -> tuple[int, str]:
        calls.append(script)
        return 0, "ok"

    with patch.object(battery_module, "_run", _fake_run):
        results = battery_module.battery("skeleton.json", contract, ["book.json"], [])
    return calls, results


def test_missing_contract_skips_the_contract_guards_as_non_gating() -> None:
    """Without a contract the two contract-scoped guards are skipped rows.

    They must be ``ok=True, gating=False`` with a detail starting ``skipped``,
    which is the exact shape ``main()``'s summary counts and names, so the
    "N skipped" line discloses them. Marking them ``ok`` and ``gating=True``
    would count a check that never ran toward the gating denominator.
    """
    calls, results = _stubbed_battery(None)

    assert "check_promise_discharge.py" not in calls
    assert "check_device_vocabulary.py" not in calls
    contract_rows = {
        r.guard: r
        for r in results
        if r.guard in {"check_promise_discharge", "check_device_vocabulary"}
    }
    assert set(contract_rows) == {"check_promise_discharge", "check_device_vocabulary"}
    for row in contract_rows.values():
        assert row.ok is True
        assert row.gating is False
        assert row.detail.lower().startswith("skipped")
    # The per-book guards still run in full: a missing contract narrows the
    # battery to what it can check, it does not excuse the book.
    assert "check_fill_integrity.py" in calls
    assert "run_story_gate.py" in calls


def test_present_contract_still_gates_the_contract_guards() -> None:
    """The companion: with a contract, both guards run and gate as before."""
    calls, results = _stubbed_battery("contract.json")

    assert "check_promise_discharge.py" in calls
    assert "check_device_vocabulary.py" in calls
    for guard in ("check_promise_discharge", "check_device_vocabulary"):
        [row] = [r for r in results if r.guard == guard]
        assert row.gating is True


# --------------------------------------------------------------------------
# The concurrent corpus driver
# --------------------------------------------------------------------------


def test_corpus_battery_attributes_every_book_under_concurrency(tmp_path: Path) -> None:
    """Three books, three workers: every slug gets its own complete row set.

    The stub records which filled path each guard was invoked on, so a
    mis-zipped result (book A's rows filed under slug B) is caught rather than
    hidden by identical stub output.
    """
    books = [
        battery_module.Book(
            slug,
            tmp_path / f"{slug}.json",
            (tmp_path / f"{slug}.narrative.json") if slug == "b" else None,
            tmp_path / f"{slug}.filled.json",
        )
        for slug in ("a", "b", "c")
    ]

    def _fake_run(script: str, *args: str) -> tuple[int, str]:
        filled = next((a for a in args if a.endswith(".filled.json")), "")
        return 0, f"ok {script} {Path(filled).stem}"

    with patch.object(battery_module, "_run", _fake_run):
        per_book = battery_module.corpus_battery(books, jobs=3)

    assert list(per_book) == ["a", "b", "c"]
    for slug, rows in per_book.items():
        per_book_rows = [r for r in rows if r.scope == f"{slug}.filled"]
        assert len(per_book_rows) == 6, f"{slug}: expected the six per-book guards"
        for row in per_book_rows:
            assert row.detail.endswith(f" {slug}.filled"), (slug, row)
    # Only "b" carried a contract, so only "b" has gating contract rows.
    contract_gating = {
        slug: any(r.guard == "check_device_vocabulary" and r.gating for r in rows)
        for slug, rows in per_book.items()
    }
    assert contract_gating == {"a": False, "b": True, "c": False}


def test_corpus_mode_exit_status_follows_check(tmp_path: Path) -> None:
    """``--corpus --check`` exits 1 on a gating failure and 0 without --check.

    Exercised through ``main()`` against a one-book tree with ``_run`` stubbed
    to fail one gating guard, so the CI step's ability to go red is asserted
    end to end rather than inferred from the flag's presence.
    """
    (tmp_path / "out").mkdir()
    (tmp_path / "skeletons" / "3-5").mkdir(parents=True)
    (tmp_path / "out" / "solo.filled.json").write_text(json.dumps({}), encoding="utf-8")
    (tmp_path / "skeletons" / "3-5" / "solo.json").write_text("{}", encoding="utf-8")

    def _fake_run(script: str, *args: str) -> tuple[int, str]:
        if script == "check_fill_integrity.py":
            return 1, "FAIL structure"
        return 0, "ok"

    with (
        patch.object(battery_module, "_run", _fake_run),
        patch.object(battery_module, "_REPO_ROOT", tmp_path),
    ):
        assert battery_module.main(["--corpus", "--check", "--jobs", "1"]) == 1
        assert battery_module.main(["--corpus", "--jobs", "1"]) == 0
        # --corpus enumerates the tree itself; explicit paths are a usage error.
        assert battery_module.main(["--corpus", "x.json", "y.json", "z.json"]) == 2
