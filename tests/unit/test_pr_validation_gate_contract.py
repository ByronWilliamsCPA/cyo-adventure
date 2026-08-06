"""Contract tests for ``Dependency & Standards Validation`` in pr-validation.yml.

This is the second of the repository's two fan-in gates, and it is a required
status check in the org baseline ruleset just as ``CI Gate`` is. It was written
separately from ``CI Gate`` and reimplements the same decision, "what does this
job's result entitle the gate to claim about the commit", in its own shell.

That independence is the reason this module exists. Issue #594 is a bug in a
decision, not in a file: a ``skipped`` result read as a pass. Fixing it in
``ci.yml`` and testing it only there leaves an identical gate on an identical
required check with no executing test at all, so the same regression could land
again through the door nobody watches. The tests below extract this gate's
script and run it, exactly as ``test_ci_gate_contract.py`` does for the other.

The two modules deliberately do not share a harness. The point of a second
implementation is that it is a second implementation; a shared abstraction
would encode one gate's structure as the definition of correctness and stop
noticing where the other diverged.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pr-validation.yml"

GATE_JOB_ID = "validate-dependencies"
GATE_STEP_NAME = "Check validation results"

# See test_ci_gate_contract.CHECK_JOB_RE: separators accept newlines and the
# shell's backslash continuation so a reflow does not silently empty the parse.
SUMMARIZE_RE = re.compile(
    r'^[ \t]*summarize[\s\\]+"(?P<label>[^"]+)"'
    r'[\s\\]+"\$(?P<result_var>[A-Za-z_][A-Za-z0-9_]*)"[ \t]*$',
    re.MULTILINE,
)
# Matches an invocation but neither the `summarize() {` definition nor the
# `# summarize <label> <result>` comment above it.
SUMMARIZE_CALL_RE = re.compile(r"^[ \t]*summarize[ \t\\]", re.MULTILINE)
NEEDS_RESULT_RE = re.compile(r"needs\.(?P<job>[A-Za-z0-9_-]+)\.result")

MERGE_QUEUE_EXCLUSION = "github.event_name != 'merge_group'"


def _load_workflow() -> dict[str, Any]:
    """Parse pr-validation.yml.

    Returns:
        The parsed workflow mapping.
    """
    yaml = YAML(typ="safe")
    with WORKFLOW_PATH.open(encoding="utf-8") as handle:
        return yaml.load(handle)


WORKFLOW = _load_workflow()
JOBS: dict[str, Any] = WORKFLOW["jobs"]
GATE_JOB: dict[str, Any] = JOBS[GATE_JOB_ID]
GATE_NEEDS: list[str] = list(GATE_JOB["needs"])

# Unlike ci.yml's gate, the result expressions live on the job rather than on
# the step. Reading them from the step would find nothing and every parsed
# mapping below would come back empty.
GATE_ENV: dict[str, str] = dict(GATE_JOB["env"])


def _gate_step() -> dict[str, Any]:
    """Locate the gate's decision step.

    Returns:
        The step mapping whose ``name`` is ``Check validation results``.
    """
    for step in GATE_JOB["steps"]:
        if step.get("name") == GATE_STEP_NAME:
            return step
    pytest.fail(f"{GATE_JOB_ID} has no step named {GATE_STEP_NAME!r}")


GATE_SCRIPT: str = _gate_step()["run"]


def _result_var_to_job() -> dict[str, str]:
    """Map each ``*_RESULT`` env var to the job id whose result it carries.

    Returns:
        A mapping of env var name to job id.
    """
    mapping: dict[str, str] = {}
    for name, expression in GATE_ENV.items():
        match = NEEDS_RESULT_RE.search(str(expression))
        if match is not None:
            mapping[name] = match.group("job")
    return mapping


RESULT_VAR_TO_JOB = _result_var_to_job()


def _summarized_jobs() -> tuple[dict[str, str], list[str]]:
    """Parse the ``summarize`` calls in the gate script.

    Nothing here raises: a parse failure at import time becomes a collection
    error that hides which contract actually broke.

    Returns:
        A mapping of job id to display label, plus the result vars that no
        ``needs.<job>.result`` expression binds.
    """
    summarized: dict[str, str] = {}
    unresolved: list[str] = []
    for match in SUMMARIZE_RE.finditer(GATE_SCRIPT):
        result_var = match.group("result_var")
        job_id = RESULT_VAR_TO_JOB.get(result_var)
        if job_id is None:
            unresolved.append(result_var)
            continue
        summarized[job_id] = match.group("label")
    return summarized, unresolved


SUMMARIZED_JOBS, UNRESOLVED_RESULT_VARS = _summarized_jobs()
SUMMARIZE_CALL_COUNT = len(SUMMARIZE_CALL_RE.findall(GATE_SCRIPT))


class TestGateCoversEveryRequiredJob:
    """Every job the gate depends on has its result read."""

    def test_every_summarize_invocation_was_parsed(self) -> None:
        """Keeps the drift tests below from passing on an empty parse."""
        parsed = len(SUMMARIZED_JOBS) + len(UNRESOLVED_RESULT_VARS)

        assert parsed == SUMMARIZE_CALL_COUNT, (
            f"the script makes {SUMMARIZE_CALL_COUNT} summarize calls but "
            f"SUMMARIZE_RE matched {parsed}"
        )

    def test_every_needed_job_is_summarized(self) -> None:
        """A job added to ``needs:`` but never read stops gating silently.

        This gate has no policy job to exempt, so unlike ``CI Gate`` the two
        sets are expected to be equal outright.
        """
        assert set(SUMMARIZED_JOBS) == set(GATE_NEEDS)

    def test_every_result_var_is_bound_to_a_job(self) -> None:
        """A ``summarize`` reading an unbound var judges an empty string."""
        assert UNRESOLVED_RESULT_VARS == []

    def test_the_gate_itself_runs_unconditionally(self) -> None:
        """``validate-dependencies`` must keep ``if: always()``.

        Without it the job inherits "all needs succeeded", so the runs it
        exists to catch would skip it. A skipped required check reports
        nothing, which is the same defect class this gate was rewritten for.
        """
        assert GATE_JOB.get("if") == "always()"

    def test_labels_match_the_job_display_names(self) -> None:
        """Each label must be the job's real ``name:``.

        The label is all a reader gets: the summary line and the annotation
        both use it, so a label naming no real job sends them hunting through
        the checks UI for something that does not appear there.
        """
        for job_id, label in SUMMARIZED_JOBS.items():
            assert label == JOBS[job_id]["name"], (
                f"summarize label {label!r} does not match {job_id}'s name "
                f"{JOBS[job_id]['name']!r}"
            )


class TestSkipAllowanceMatchesJobCondition:
    """The single ``skip_expected`` flag is only sound if every job agrees."""

    def test_every_gated_job_is_excluded_on_merge_queue_and_only_there(self) -> None:
        """The gate derives one allowance for all jobs from the event alone.

        ``CI Gate`` can afford a per-job allowance because its jobs differ;
        here a single ``skip_expected`` is computed once and applied to both.
        That is only correct while every gated job carries the same exclusion
        and no other. A job whose ``if:`` gains a second way to skip would
        make the flag say "expected" about a skip nobody expected, which is
        the #594 defect arriving by a different route.
        """
        for job_id in GATE_NEEDS:
            condition = str(JOBS[job_id].get("if", ""))

            assert condition == MERGE_QUEUE_EXCLUSION, (
                f"{job_id} has if: {condition!r}; the gate's single "
                f"skip_expected flag assumes exactly {MERGE_QUEUE_EXCLUSION!r}"
            )


class TestTheScriptFailsClosedByConstruction:
    """Static properties that keep the exit status from being incidental."""

    def test_the_script_sets_strict_mode(self) -> None:
        """``set -euo pipefail`` is what makes a failed redirect fatal.

        Without it the script's status is whatever its last statement
        returned, so an unwritable summary produced a non-zero exit only by
        the accident of the last statement being a redirect to that same
        broken file.
        """
        assert "set -euo pipefail" in GATE_SCRIPT

    def test_the_script_ends_by_stating_success_explicitly(self) -> None:
        """Success must be stated, not inherited from the final statement.

        With the strict-mode fix in place, appending any trailing command
        would otherwise hand this required check's verdict to whatever that
        command happened to return.
        """
        assert GATE_SCRIPT.rstrip().endswith("exit 0")


ALL_SUCCESS: dict[str, str] = {
    "EVENT_NAME": "pull_request",
    "DEAD_CODE_RESULT": "success",
    "LINK_CHECK_RESULT": "success",
}

BASH = shutil.which("bash")


class GateRun:
    """The observable result of executing the gate script once."""

    def __init__(self, returncode: int, stdout: str, summary: str) -> None:
        """Record one run.

        Args:
            returncode: The script's exit status.
            stdout: Everything the script printed, including workflow commands.
            summary: What the script appended to ``$GITHUB_STEP_SUMMARY``.
        """
        self.returncode = returncode
        self.stdout = stdout
        self.summary = summary

    @property
    def passed(self) -> bool:
        """Whether the gate reported a pass.

        Returns:
            True when the script exited zero.
        """
        return self.returncode == 0


@pytest.fixture
def run_gate(tmp_path: Path) -> Callable[..., GateRun]:
    """Execute the real gate script from pr-validation.yml.

    Args:
        tmp_path: Destination for the captured step summary.

    Returns:
        A callable taking env overrides and returning a :class:`GateRun`.
    """
    summary_path = tmp_path / "step-summary.md"
    summary_path.touch()

    def _run(*, summary_target: Path | None = None, **overrides: str) -> GateRun:
        target = summary_target if summary_target is not None else summary_path
        env = {
            **ALL_SUCCESS,
            **overrides,
            "GITHUB_STEP_SUMMARY": str(target),
        }
        completed = subprocess.run(
            [str(BASH), "-c", GATE_SCRIPT],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        written = (
            summary_path.read_text(encoding="utf-8") if target == summary_path else ""
        )
        return GateRun(
            completed.returncode, completed.stdout + completed.stderr, written
        )

    return _run


@pytest.mark.skipif(
    BASH is None,
    reason="the gate script is bash; the workflow itself only ever runs on ubuntu-latest",
)
class TestGateDecisions:
    """Execute the gate and assert on what it decides."""

    def test_all_checks_passing_passes(self, run_gate) -> None:
        """The baseline: nothing skipped, nothing failed."""
        run = run_gate()

        assert run.passed
        assert "All validation checks passed!" in run.summary
        assert "::warning::" not in run.stdout

    def test_a_failing_check_fails_the_gate(self, run_gate) -> None:
        """A plain failure must still block."""
        run = run_gate(DEAD_CODE_RESULT="failure")

        assert not run.passed
        assert "Dead Code Check: failure" in run.summary
        assert "Validation failed" in run.summary

    def test_a_cancelled_check_fails_the_gate(self, run_gate) -> None:
        """``cancelled`` is not ``success``.

        A ``timeout-minutes`` expiry reports ``cancelled``, not ``failure``,
        so a gate that only rejects ``failure`` passes a check that ran out of
        time. The comment above the ``case`` says the catch-all covers this;
        this is the test that makes the comment checkable.
        """
        run = run_gate(LINK_CHECK_RESULT="cancelled")

        assert not run.passed
        assert "Documentation Links: cancelled" in run.summary

    def test_an_empty_result_fails_the_gate(self, run_gate) -> None:
        """An unset result is not an absent problem.

        ``needs.<job>.result`` is empty when the expression is misspelled or
        the job leaves ``needs:`` without the env block following.
        """
        run = run_gate(DEAD_CODE_RESULT="")

        assert not run.passed

    def test_an_unexplained_skip_fails_the_gate(self, run_gate) -> None:
        """The #594 regression, on this gate.

        Both jobs' ``if:`` excludes only merge_group, so a skip on a
        pull_request event has no legitimate cause. The previous version
        accepted it and labelled it "Skipped (merge queue)" regardless of the
        event that was actually running.
        """
        run = run_gate(EVENT_NAME="pull_request", LINK_CHECK_RESULT="skipped")

        assert not run.passed
        assert "a pull_request event does not explain why" in run.summary
        assert "::error::Documentation Links was skipped unexpectedly" in run.stdout

    def test_a_skip_is_still_rejected_on_a_push_event(self, run_gate) -> None:
        """merge_group is the only event that excuses these jobs.

        Pinned separately from the pull_request case so a future change that
        widens the allowance to "any event that is not a PR" is caught.
        """
        run = run_gate(EVENT_NAME="push", DEAD_CODE_RESULT="skipped")

        assert not run.passed

    def test_expected_merge_queue_skips_pass_but_are_disclosed(self, run_gate) -> None:
        """Passing is correct here; passing silently is the bug.

        The gate must not sign off with "All validation checks passed!" on a
        run where a check did not run at all. That sentence is the claim the
        required status check carries into the merge queue.
        """
        run = run_gate(
            EVENT_NAME="merge_group",
            DEAD_CODE_RESULT="skipped",
            LINK_CHECK_RESULT="skipped",
        )

        assert run.passed
        assert "All validation checks passed!" not in run.summary
        assert "2 check(s) were not run on this commit" in run.summary
        assert "not because" in run.summary
        assert "::warning::" in run.stdout

    def test_an_unwritable_summary_fails_the_gate(self, tmp_path, run_gate) -> None:
        """The claim made by the ``#CRITICAL`` comment on this step.

        If ``$GITHUB_STEP_SUMMARY`` cannot be written, the gate has no way to
        report what it decided, and a required check that cannot say why it
        passed must not pass. Before ``set -euo pipefail`` this held only by
        coincidence: every redirect failed silently and the exit status came
        from whichever statement happened to be last, so adding a trailing
        ``echo`` would have turned it into a false green.

        A directory is used as the unwritable target rather than a
        permission-stripped file, because a test run as root can write to a
        read-only file and would then assert nothing.
        """
        unwritable = tmp_path / "not-a-file"
        unwritable.mkdir()

        run = run_gate(summary_target=unwritable)

        assert not run.passed
