"""Contract tests for the ``CI Gate`` fan-in job in ``.github/workflows/ci.yml``.

``CI Gate`` is the required status check that stands in for the whole suite, so
whatever it reports is the repository's claim about a commit. Issue #594 recorded
what happens when that claim is wrong: the gate accepted a ``skipped`` result
unconditionally, so a release-automation push that skipped every quality job
reported plain ``success``, and ``main`` looked verified while carrying an
unscanned CVE.

Two failure classes are pinned here, because they fail differently:

* **Decision defects.** The gate's shell script is extracted and *executed*
  against synthetic job results, so "a skip nobody asked for is a failure" is
  asserted by running the gate rather than by reading it. A gate whose logic is
  only inspected is a gate nobody has ever seen fail.
* **Drift defects.** The gate names each job it checks. Adding a job to
  ``needs:`` without also checking its result silently narrows what the gate
  covers while leaving it green, so the static tests below assert the two lists
  agree and that each skip allowance matches the job's own ``if:``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

GATE_JOB_ID = "ci-gate"
GATE_STEP_NAME = "Check CI results"

# detect-release-pr is not checked through check_job: its own result gates
# whether the skip policy is evaluable at all, so it is handled by an explicit
# guard ahead of the per-job checks.
POLICY_JOB_ID = "detect-release-pr"

CHECK_JOB_RE = re.compile(
    r'^\s*check_job "(?P<label>[^"]+)" '
    r'"\$(?P<result_var>[A-Za-z_][A-Za-z0-9_]*)" '
    r'(?P<skip>false|"\$merge_queue_skip_ok")\s*$',
    re.MULTILINE,
)
NEEDS_RESULT_RE = re.compile(r"needs\.(?P<job>[A-Za-z0-9_-]+)\.result")

MERGE_QUEUE_SKIP_OK = '"$merge_queue_skip_ok"'
NEVER_SKIPS = "false"


def _load_workflow() -> dict[str, Any]:
    """Parse ci.yml.

    Returns:
        The parsed workflow mapping.
    """
    yaml = YAML(typ="safe")
    with CI_WORKFLOW.open(encoding="utf-8") as handle:
        return yaml.load(handle)


WORKFLOW = _load_workflow()
JOBS: dict[str, Any] = WORKFLOW["jobs"]
GATE_JOB: dict[str, Any] = JOBS[GATE_JOB_ID]
GATE_NEEDS: list[str] = list(GATE_JOB["needs"])


def _gate_step() -> dict[str, Any]:
    """Locate the gate's decision step.

    Returns:
        The step mapping whose ``name`` is ``Check CI results``.
    """
    for step in GATE_JOB["steps"]:
        if step.get("name") == GATE_STEP_NAME:
            return step
    pytest.fail(f"{GATE_JOB_ID} has no step named {GATE_STEP_NAME!r}")


GATE_STEP = _gate_step()
GATE_SCRIPT: str = GATE_STEP["run"]
GATE_ENV: dict[str, str] = dict(GATE_STEP["env"])


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


def _checked_jobs() -> dict[str, tuple[str, str]]:
    """Parse the ``check_job`` calls in the gate script.

    Returns:
        A mapping of job id to ``(display label, skip-allowance argument)``.
    """
    checked: dict[str, tuple[str, str]] = {}
    for match in CHECK_JOB_RE.finditer(GATE_SCRIPT):
        result_var = match.group("result_var")
        job_id = RESULT_VAR_TO_JOB.get(result_var)
        assert job_id is not None, (
            f"check_job uses ${result_var}, which is not bound to any "
            f"needs.<job>.result in the step's env: block"
        )
        checked[job_id] = (match.group("label"), match.group("skip"))
    return checked


CHECKED_JOBS = _checked_jobs()


class TestGateCoversEveryRequiredJob:
    """The set of jobs checked must equal the set of jobs depended on."""

    def test_every_needed_job_is_checked(self) -> None:
        """A job added to ``needs:`` but never checked silently stops gating.

        This is the drift that makes a fan-in gate stop meaning anything: the
        job runs, the gate ignores its result, and the check stays green.
        """
        expected = set(GATE_NEEDS) - {POLICY_JOB_ID}

        assert set(CHECKED_JOBS) == expected

    def test_the_policy_job_gates_the_whole_evaluation(self) -> None:
        """detect-release-pr's own result must be checked, not just its output.

        Every skip allowance is derived from its ``release_pr`` output. If the
        job failed, that output is empty, and an empty output must not be read
        as "not a release PR" and used to judge skips.
        """
        assert POLICY_JOB_ID in GATE_NEEDS
        assert RESULT_VAR_TO_JOB.get("DETECT_RESULT") == POLICY_JOB_ID
        assert '"$DETECT_RESULT" != "success"' in GATE_SCRIPT

    def test_labels_match_the_job_display_names(self) -> None:
        """Each check_job label must be the job's real ``name:``.

        The label is what the summary and the annotation name, so a stale label
        sends a reader to a job that is not the one that failed.
        """
        for job_id, (label, _skip) in CHECKED_JOBS.items():
            assert label == JOBS[job_id]["name"], (
                f"check_job label {label!r} does not match "
                f"{job_id}'s name {JOBS[job_id]['name']!r}"
            )


class TestSkipAllowanceMatchesJobCondition:
    """A skip may only be tolerated where the job's own ``if:`` produces one."""

    def test_allowance_is_derived_from_the_job_condition(self) -> None:
        """Tolerating a skip for a job that cannot legitimately skip is the #594 bug.

        ``frontend``, ``frontend-e2e``, ``design-system`` and ``contract`` carry
        ``github.event_name != 'merge_group'``, so merge_group is the one event
        that explains their skip. ``ci`` and ``schema-docs`` carry no such
        exclusion on this path, so for them any skip is a defect.
        """
        for job_id, (_label, skip_arg) in CHECKED_JOBS.items():
            condition = str(JOBS[job_id].get("if", ""))
            excluded_on_merge_queue = "merge_group" in condition
            expected = MERGE_QUEUE_SKIP_OK if excluded_on_merge_queue else NEVER_SKIPS

            assert skip_arg == expected, (
                f"{job_id} has if: {condition!r} but its skip allowance is "
                f"{skip_arg}; expected {expected}"
            )

    def test_at_least_one_job_of_each_kind_is_present(self) -> None:
        """Guards the test above against becoming vacuous.

        If every job ended up in one bucket, the assertion above would still
        pass while checking only half the rule.
        """
        allowances = {skip for _label, skip in CHECKED_JOBS.values()}

        assert allowances == {MERGE_QUEUE_SKIP_OK, NEVER_SKIPS}


ALL_SUCCESS: dict[str, str] = {
    "EVENT_NAME": "pull_request",
    "RELEASE_PR": "false",
    "DETECT_RESULT": "success",
    "CI_RESULT": "success",
    "FRONTEND_RESULT": "success",
    "FRONTEND_E2E_RESULT": "success",
    "DESIGN_SYSTEM_RESULT": "success",
    "CONTRACT_RESULT": "success",
    "SCHEMA_DOCS_RESULT": "success",
}


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
    """Execute the real gate script from ci.yml against synthetic job results.

    Extracting and running the script is what makes the gate's decision
    testable at all. Asserting on the YAML alone would leave the branch that
    matters, "a skip that nothing explains", never once exercised.

    Args:
        tmp_path: Destination for the captured step summary.

    Returns:
        A callable taking env overrides and returning a :class:`GateRun`.
    """
    summary_path = tmp_path / "step-summary.md"
    summary_path.touch()

    def _run(**overrides: str) -> GateRun:
        env = {
            **ALL_SUCCESS,
            **overrides,
            "GITHUB_STEP_SUMMARY": str(summary_path),
        }
        completed = subprocess.run(
            ["bash", "-c", GATE_SCRIPT],  # noqa: S607
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        return GateRun(
            completed.returncode,
            completed.stdout + completed.stderr,
            summary_path.read_text(encoding="utf-8"),
        )

    return _run


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the gate script is bash; the workflow itself only ever runs on ubuntu-latest",
)
class TestGateDecisions:
    """Execute the gate and assert on what it decides."""

    def test_all_jobs_passing_passes(self, run_gate) -> None:
        """The baseline: nothing skipped, nothing failed."""
        run = run_gate()

        assert run.passed
        assert "CI Gate passed" in run.summary
        assert "::warning::" not in run.stdout

    def test_a_failing_job_fails_the_gate(self, run_gate) -> None:
        """A plain failure must still block."""
        run = run_gate(CI_RESULT="failure")

        assert not run.passed
        assert "CI (Python 3.14): failure" in run.summary

    def test_a_cancelled_job_fails_the_gate(self, run_gate) -> None:
        """``cancelled`` is not ``success``.

        A ``timeout-minutes`` expiry reports ``cancelled`` rather than
        ``failure``, so a gate that only rejects ``failure`` would pass a job
        that ran out of time.
        """
        run = run_gate(CI_RESULT="cancelled")

        assert not run.passed

    def test_expected_merge_queue_skips_pass_but_are_disclosed(self, run_gate) -> None:
        """On merge_group the frontend jobs skip by design, and the gate says so.

        Passing is correct here. Passing *silently* is what issue #594 is about,
        so the disclosure is as much of the contract as the exit status.
        """
        run = run_gate(
            EVENT_NAME="merge_group",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
        )

        assert run.passed
        assert "NOT verified on this commit" in run.summary
        assert "4 required job(s) were not run" in run.summary
        assert "::warning::" in run.stdout

    def test_an_unexplained_frontend_skip_fails_the_gate(self, run_gate) -> None:
        """The regression test for #594.

        A ``frontend`` skip on a ``pull_request`` event has no legitimate cause:
        the job's ``if:`` only excludes merge_group. The previous gate accepted
        this and reported ``success``.
        """
        run = run_gate(EVENT_NAME="pull_request", FRONTEND_RESULT="skipped")

        assert not run.passed
        assert "nothing in this run's context explains why" in run.summary
        assert "::error::" in run.stdout

    def test_an_unexplained_schema_docs_skip_fails_the_gate(self, run_gate) -> None:
        """The second half of #594.

        ``schema-docs`` carries no job-level ``if:`` at all, so it can only skip
        when something upstream broke. The previous gate tolerated it as
        "defensive symmetry".
        """
        run = run_gate(SCHEMA_DOCS_RESULT="skipped")

        assert not run.passed

    def test_a_skip_is_still_rejected_on_a_push_event(self, run_gate) -> None:
        """merge_group is the only event that excuses the frontend jobs.

        Pinned separately from the pull_request case so a future change that
        widens the allowance to "any event that is not a PR" is caught.
        """
        run = run_gate(EVENT_NAME="push", CONTRACT_RESULT="skipped")

        assert not run.passed

    def test_a_release_commit_passes_but_states_it_verified_nothing(
        self, run_gate
    ) -> None:
        """The exact scenario from the issue.

        A ``chore(release):`` push skips the whole suite. The gate still passes,
        because the content was tested on the feature PR that produced it, but
        it must not present that as a verification of this commit.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
            SCHEMA_DOCS_RESULT="skipped",
        )

        assert run.passed
        assert "WITHOUT running the suite" in run.summary
        assert "carries no verification from this workflow" in run.summary
        assert "::warning::" in run.stdout

    def test_a_broken_policy_job_fails_the_gate(self, run_gate) -> None:
        """An empty ``release_pr`` output must not be read as "not a release PR".

        If detect-release-pr fails, ``RELEASE_PR`` is empty. Treating that as
        false and then judging skips against it would be guessing.
        """
        run = run_gate(DETECT_RESULT="failure", RELEASE_PR="")

        assert not run.passed
        assert "cannot establish which skips are expected" in run.summary
