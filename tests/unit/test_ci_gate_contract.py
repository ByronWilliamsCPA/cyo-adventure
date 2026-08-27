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

# Separators accept newlines and the shell's own backslash continuation, not
# just a single space. A stricter pattern stops matching the moment a call is
# reflowed for line length, and "no check_job calls were found" reads exactly
# like "every check_job call agrees with the workflow". The invocation counter
# below exists so that difference is visible;
# test_every_check_job_invocation_was_parsed asserts on it.
CHECK_JOB_RE = re.compile(
    r'^[ \t]*check_job[\s\\]+"(?P<label>[^"]+)"'
    r'[\s\\]+"\$(?P<result_var>[A-Za-z_][A-Za-z0-9_]*)"'
    r'[\s\\]+(?P<skip>false|"\$merge_queue_skip_ok")[ \t]*$',
    re.MULTILINE,
)
# Matches an invocation but not the `check_job() {` definition, whose next
# character is an opening paren rather than whitespace.
CHECK_JOB_CALL_RE = re.compile(r"^[ \t]*check_job[ \t\\]", re.MULTILINE)
NEEDS_RESULT_RE = re.compile(r"needs\.(?P<job>[A-Za-z0-9_-]+)\.result")

MERGE_QUEUE_SKIP_OK = '"$merge_queue_skip_ok"'
NEVER_SKIPS = "false"

# The exact clause that makes a merge_group skip legitimate. Matching the bare
# substring "merge_group" would also accept `github.event_name ==
# 'merge_group'`, which says the opposite of what the allowance assumes, so the
# negation is part of what gets asserted.
MERGE_QUEUE_EXCLUSION = "github.event_name != 'merge_group'"


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


def _checked_jobs() -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Parse the ``check_job`` calls in the gate script.

    Nothing here raises. A parse problem reported at import time surfaces as a
    collection error that takes every test in the module down with it, which
    hides the specific contract that broke behind a stack trace; the two
    return values are asserted on by named tests instead.

    Returns:
        A mapping of job id to ``(display label, skip-allowance argument)``,
        plus the result vars that no ``needs.<job>.result`` expression binds.
    """
    checked: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []
    for match in CHECK_JOB_RE.finditer(GATE_SCRIPT):
        result_var = match.group("result_var")
        job_id = RESULT_VAR_TO_JOB.get(result_var)
        if job_id is None:
            unresolved.append(result_var)
            continue
        checked[job_id] = (match.group("label"), match.group("skip"))
    return checked, unresolved


CHECKED_JOBS, UNRESOLVED_RESULT_VARS = _checked_jobs()
CHECK_JOB_CALL_COUNT = len(CHECK_JOB_CALL_RE.findall(GATE_SCRIPT))

# The release branch's `for entry in "Label:$VAR" ...; do` list, and the
# disclosure text that names the same jobs in prose. Both are derived rather
# than transcribed, because a hand-copied list is what let `format-tree`,
# `rad-citations` and `docstrings` each go unchecked in turn.
RELEASE_LOOP_RE = re.compile(r"for entry in(?P<body>.*?);[ \t]*do", re.DOTALL)
RELEASE_ENTRY_RE = re.compile(r'"(?P<label>[^"$:]+):\$(?P<result_var>[A-Za-z_]\w*)"')
RELEASE_SUMMARY_RE = re.compile(
    r"## CI Gate passed WITHOUT running the suite.*?exit 0", re.DOTALL
)


def _release_checked_jobs() -> set[str]:
    """Resolve the release loop's entries to job ids.

    Nothing raises here for the same reason ``_checked_jobs`` does not: an
    import-time failure would take the whole module down and hide which
    contract broke. An unparseable loop yields an empty set, which fails the
    named tests below with a readable message.

    Returns:
        set[str]: Job ids whose result the release branch evaluates.
    """
    loop = RELEASE_LOOP_RE.search(GATE_SCRIPT)
    if loop is None:
        return set()
    return {
        job_id
        for match in RELEASE_ENTRY_RE.finditer(loop.group("body"))
        if (job_id := RESULT_VAR_TO_JOB.get(match.group("result_var"))) is not None
    }


RELEASE_CHECKED_JOBS = _release_checked_jobs()
_RELEASE_SUMMARY_MATCH = RELEASE_SUMMARY_RE.search(GATE_SCRIPT)
RELEASE_SUMMARY_TEXT = (
    "" if _RELEASE_SUMMARY_MATCH is None else _RELEASE_SUMMARY_MATCH.group(0)
)


class TestGateCoversEveryRequiredJob:
    """Every job the gate depends on is either checked or explicitly exempt.

    One job is exempt: ``detect-release-pr`` supplies the policy the other
    checks are judged against, so it is guarded by its own early exit rather
    than by ``check_job``. That carve-out is asserted here too, so "exempt"
    cannot quietly grow to mean "unchecked".
    """

    def test_every_check_job_invocation_was_parsed(self) -> None:
        """The parse must account for every ``check_job`` call in the script.

        Without this, a call the regex fails to match simply vanishes from
        ``CHECKED_JOBS``, and a test that compares two sets both derived from
        an empty parse still passes. Counting invocations separately from
        parsing them is what makes the drift tests non-vacuous.
        """
        parsed = len(CHECKED_JOBS) + len(UNRESOLVED_RESULT_VARS)

        assert parsed == CHECK_JOB_CALL_COUNT, (
            f"the script makes {CHECK_JOB_CALL_COUNT} check_job calls but "
            f"CHECK_JOB_RE matched {parsed}; the pattern has drifted from the "
            f"script's formatting"
        )

    def test_every_checked_result_var_is_bound_to_a_job(self) -> None:
        """A ``check_job`` reading an unbound var judges an empty string.

        Under ``set -u`` that is a hard error, and without it the var expands
        to empty and falls into the catch-all arm, failing the gate for a
        reason no summary line explains.
        """
        assert UNRESOLVED_RESULT_VARS == [], (
            f"check_job reads {UNRESOLVED_RESULT_VARS}, which no "
            f"needs.<job>.result expression in the step's env: block binds"
        )

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

    def test_the_gate_itself_runs_unconditionally(self) -> None:
        """``ci-gate`` must keep ``if: always()``.

        Without it the gate inherits the default "all needs succeeded"
        condition, so the very runs it exists to catch, the ones where an
        upstream job failed or skipped, would skip the gate instead. A skipped
        required check does not report a failure; it reports nothing, which is
        the same class of defect as the one this gate was rewritten to fix.
        """
        assert GATE_JOB.get("if") == "always()"

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
            excluded_on_merge_queue = MERGE_QUEUE_EXCLUSION in condition

            # A condition that names merge_group in any other shape is not
            # something this rule knows how to classify, and defaulting it to
            # "never skips" would be a guess. Fail loudly and make the next
            # author extend the rule deliberately.
            assert ("merge_group" in condition) == excluded_on_merge_queue, (
                f"{job_id} has if: {condition!r}, which mentions merge_group "
                f"without the exact {MERGE_QUEUE_EXCLUSION!r} clause this "
                f"rule recognises"
            )

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


# Jobs that ci.yml defines but ci-gate deliberately does not depend on. The
# key is the job id; the value is why it is out of scope. A job absent from
# both this mapping and `needs:` is the failure this guard exists to catch:
# `set(CHECKED_JOBS) == set(GATE_NEEDS)` can only see jobs that reached
# `needs:` in the first place, so a job that was never wired in is invisible
# to it while looking, on the checks page, exactly like a gating one.
UNGATED_JOBS: dict[str, str] = {
    "coverage-upload": (
        "reporting only: uploads coverage to Codecov and Qlty and asserts "
        "nothing, so its failure is not a statement about the commit"
    ),
    "detect-api-collection": (
        "a detector whose sole consumer is api-tests' own `if:`; gating on it "
        "would gate on the detection rather than on the tests"
    ),
    "api-tests": (
        "promotion to a required gate is deferred until the job proves stable "
        "across a few merges, per the comment on the job itself"
    ),
    # #ASSUME: data-integrity: this exemption records the current state, not a
    # decision that the state is right. `Diversity Regression Gate` runs real
    # `--check` assertions and is not an individually required context, so
    # today it can fail without blocking anything.
    # #VERIFY: promote `diversity` into ci-gate's `needs:` and move this entry
    # out, or replace this text with the reason it should stay advisory.
    "diversity": (
        "not gated today, and arguably should be: it makes real assertions "
        "but blocks nothing. Recorded rather than omitted, so the gap is "
        "visible in the test that would otherwise imply full coverage"
    ),
}


class TestNoQualityJobEscapesTheGateSilently:
    """Every job in ``jobs:`` is gated, is the gate, or is listed as exempt."""

    def test_every_job_is_gated_or_explicitly_exempt(self) -> None:
        """A new job that nobody wires into ``needs:`` must fail this test.

        This is the blind spot in the ``needs:`` -> ``check_job`` comparison:
        that test proves the gate checks everything it depends on, which says
        nothing about what it was never made to depend on. Adding a job here
        forces a deliberate answer to "does this gate anything?", instead of
        letting the default answer be "no" by omission.
        """
        accounted = set(GATE_NEEDS) | set(UNGATED_JOBS) | {GATE_JOB_ID}

        assert set(JOBS) == accounted, (
            f"jobs neither gated nor listed as exempt: "
            f"{sorted(set(JOBS) - accounted)}; add each to ci-gate's needs: "
            f"or to UNGATED_JOBS with the reason it does not gate"
        )

    def test_the_exempt_list_names_only_real_jobs(self) -> None:
        """A stale exemption silently re-opens the hole it was meant to note.

        If a job is renamed or removed, its entry here stops matching anything
        and the successor job lands back in the "unaccounted" set. Pinning the
        list to reality keeps the failure above pointing at the real name.
        """
        assert set(UNGATED_JOBS) <= set(JOBS)
        assert set(UNGATED_JOBS).isdisjoint(GATE_NEEDS)


class TestTheScriptFailsClosedByConstruction:
    """Static properties that keep the exit status from being incidental."""

    def test_the_script_sets_strict_mode(self) -> None:
        """``set -euo pipefail`` is what makes a failed redirect fatal.

        Without it a summary this gate cannot write is a silent no-op, and the
        exit status becomes whatever the last statement returned.
        """
        assert "set -euo pipefail" in GATE_SCRIPT

    def test_the_script_ends_by_stating_success_explicitly(self) -> None:
        """Success must be stated, not inherited from the final statement.

        Both gates end this way for the same reason: with the last statement
        deciding the verdict, appending any trailing command silently hands a
        required check's result to whatever that command happens to return.
        """
        assert GATE_SCRIPT.rstrip().endswith("exit 0")


# Derived from the gate's own `env:` block rather than hand-listed. The
# script runs under `set -u`, so a result var the gate reads but this dict
# omits aborts it on an unbound variable, which surfaces as every execution
# test in TestGateDecisions failing at once with a message that names bash
# rather than the missing job. Hand-maintaining the list made adding a gated
# job a seven-test breakage whose cause was invisible in the assertion output.
# Deriving it means a new job joins the happy path automatically, and the
# tests that exercise a failure still override the one key they care about.
# RELEASE_PR is not derived: it reads `needs.<job>.outputs.release_pr`, not
# `.result`, so it is deliberately absent from RESULT_VAR_TO_JOB.
ALL_SUCCESS: dict[str, str] = {
    "EVENT_NAME": "pull_request",
    "RELEASE_PR": "false",
    **dict.fromkeys(RESULT_VAR_TO_JOB, "success"),
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


BASH = shutil.which("bash")


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
        # Resolved to an absolute path rather than suppressing S607. A `noqa`
        # here would also have to be `S607` alone: `S603` is already in this
        # tree's per-file-ignores, so naming it as well trips RUF100 and fails
        # the lint it was added to satisfy.
        completed = subprocess.run(
            [str(BASH), "-c", GATE_SCRIPT],
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


# Keyed on whether bash is actually present, and nothing else. The earlier
# `sys.platform == "win32" or ...` form was doubly wrong: the platform check is
# redundant with the which() check on a Windows box without bash, and on one
# *with* bash (Git Bash, WSL, the windows-latest runner) it silently skipped
# most of this module's assertions on a machine that could run every one.
@pytest.mark.skipif(
    BASH is None,
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
        # Asserted on the text, not just the exit code: a gate that fails for
        # an unrelated reason would satisfy `not run.passed` while telling the
        # reader nothing about the job that actually stopped.
        assert "CI (Python 3.14): cancelled" in run.summary

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
        assert "ER Diagram Drift: skipped" in run.summary
        assert "nothing in this run's context explains why" in run.summary
        assert "::error::ER Diagram Drift was skipped unexpectedly" in run.stdout

    def test_a_skip_is_still_rejected_on_a_push_event(self, run_gate) -> None:
        """merge_group is the only event that excuses the frontend jobs.

        Pinned separately from the pull_request case so a future change that
        widens the allowance to "any event that is not a PR" is caught.
        """
        run = run_gate(EVENT_NAME="push", CONTRACT_RESULT="skipped")

        assert not run.passed
        assert "OpenAPI Contract Drift: skipped" in run.summary
        # The annotation names the event, so the reader can tell "skipped on
        # the wrong event" from "skipped for no reason at all".
        assert "skipped unexpectedly on a push event" in run.stdout

    def test_a_release_commit_passes_but_states_what_it_did_not_verify(
        self, run_gate
    ) -> None:
        """The exact scenario from the issue.

        A ``chore(release):`` push skips the quality suite. The gate still
        passes, because the content was tested on the feature PR that produced
        it, but it must not present that as a verification of this commit.

        ``schema-docs`` is set to ``success`` rather than ``skipped`` because
        that is what really happens: it carries no job-level ``if:``, so it
        runs on a release commit like any other. See
        ``test_schema_docs_really_does_run_on_a_release_commit``.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
            SCHEMA_DOCS_RESULT="success",
        )

        assert run.passed
        assert "WITHOUT running the suite" in run.summary
        assert "no verification from this workflow" in run.summary
        # The disclosure has to carve out EVERY job that did run, or it
        # overstates the gap in the other direction. It named only
        # `ER Diagram Drift` while three jobs really ran, so the sentence was
        # wrong by two; `docstrings` later made it four and wrong by three, and
        # `alert-action` made it five.
        # The prose is spot-checked here and enforced generically by
        # TestEveryUnconditionalJobIsReleaseChecked, which derives the job set
        # from the workflow rather than transcribing it. That generic test is
        # why this transcription is a spot-check and not the guard: it names
        # the joining word and the ordering, which the derived test cannot see.
        assert "every quality job except `ER Diagram Drift`," in run.summary
        assert "`Format (tree-wide)`, `RAD Citation Gate`," in run.summary
        assert "`Docstring coverage (interrogate)`" in run.summary
        assert "and `Scheduled-alert action harness` was intentionally" in run.summary
        assert "Those five carry no job-level condition" in run.summary
        assert "::warning::" in run.stdout

    def test_a_release_commit_with_a_failing_er_diagram_check_fails_the_gate(
        self, run_gate
    ) -> None:
        """A real failure must not be absorbed by the release-skip branch.

        ``schema-docs`` is the one job in the gate that genuinely executes on a
        release-automation commit: no ``if:``, no ``needs:``. Before this case
        existed the release branch returned 0 without ever reading its result,
        so an ``ER Diagram Drift`` failure landed on ``main`` reported as a
        pass, with a summary line calling it an intentional skip.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
            SCHEMA_DOCS_RESULT="failure",
        )

        assert not run.passed
        assert "That job runs unconditionally" in run.summary
        assert "::error::ER Diagram Drift reported failure" in run.stdout

    def test_a_release_commit_with_a_skipped_er_diagram_check_fails_the_gate(
        self, run_gate
    ) -> None:
        """``skipped`` is not a pass here either.

        Nothing in a release commit's context excuses this job, so a skip
        means something upstream broke. Pinned separately from the ``failure``
        case because the two arrive by different routes and an implementation
        that special-cased only one would still look correct.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            SCHEMA_DOCS_RESULT="skipped",
        )

        assert not run.passed
        assert "::error::ER Diagram Drift reported skipped" in run.stdout

    def test_a_release_commit_with_a_failing_rad_citation_check_fails_the_gate(
        self, run_gate
    ) -> None:
        """The same hole, one job over.

        ``rad-citations`` carries no ``if:`` and no ``needs:`` either, so it
        really runs on a release-automation commit exactly like
        ``schema-docs``. The release branch read only ``SCHEMA_DOCS_RESULT``
        before exiting 0, so a genuine ``RAD Citation Gate`` failure was
        discarded and reported as an intentional skip. ``format-tree`` sat in
        the same blind spot; the fix generalises the check over all three
        rather than adding a second hand-written special case.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
            RAD_CITATIONS_RESULT="failure",
        )

        assert not run.passed
        assert "That job runs unconditionally" in run.summary
        assert "::error::RAD Citation Gate reported failure" in run.stdout

    def test_a_release_commit_with_a_failing_format_check_fails_the_gate(
        self, run_gate
    ) -> None:
        """The third unconditional job, pinned for the same reason.

        ``format-tree`` had this hole before ``rad-citations`` existed. It is
        asserted here rather than left to the generalised loop's shape,
        because a loop that silently loses an entry looks identical to a loop
        that never had it.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
            FORMAT_TREE_RESULT="failure",
        )

        assert not run.passed
        assert "::error::Format (tree-wide) reported failure" in run.stdout

    def test_schema_docs_really_does_run_on_a_release_commit(self) -> None:
        """The premise the two tests above rest on, asserted directly.

        Their value depends entirely on ``schema-docs`` being unable to skip
        on a release commit. If someone later gives it a job-level ``if:`` or
        a ``needs:``, those tests keep passing while asserting something that
        is no longer true of the workflow, so the premise is pinned here
        rather than left implicit in a comment.
        """
        schema_docs = JOBS["schema-docs"]

        assert "if" not in schema_docs
        assert "needs" not in schema_docs

    def test_the_tree_wide_format_check_runs_in_every_context(self) -> None:
        """``format-tree`` is only a gate while it cannot be skipped.

        It exists because no other job runs the formatter over the whole tree:
        the delegated ``ci`` job scopes its check to the code directories and
        the pre-commit hook sees staged files only. That coverage argument
        collapses the moment the job gains a job-level ``if:`` or a ``needs:``,
        which is exactly why it was not made a step inside ``contract`` (which
        skips on merge_group and on release PRs). Pinned here so narrowing it
        fails loudly instead of quietly shrinking what the gate covers.
        """
        format_tree = JOBS["format-tree"]

        assert "if" not in format_tree
        assert "needs" not in format_tree

    def test_the_rad_citation_gate_runs_in_every_context(self) -> None:
        """``rad-citations`` is the third job that cannot skip, pinned as such.

        Two separate things rest on this premise and neither states it. The
        gate passes ``false`` as this job's skip allowance, so any skip is a
        defect rather than a policy; and the release branch above evaluates
        its result before exiting 0, which is only necessary while the job
        really runs on a release commit. A job-level ``if:`` or a ``needs:``
        added later would leave both of those reading correctly while
        asserting something no longer true of the workflow.
        """
        rad_citations = JOBS["rad-citations"]

        assert "if" not in rad_citations
        assert "needs" not in rad_citations

    def test_a_release_commit_with_a_failing_docstring_check_fails_the_gate(
        self, run_gate
    ) -> None:
        """The fourth unconditional job, which inherited the hole once already.

        ``docstrings`` was added to the gate carrying no ``if:`` and no
        ``needs:``, so it really runs on a release-automation commit, but it
        was not added to the release branch's loop. A failing docstring job
        therefore produced a green required ``CI Gate`` on every release
        commit. The loop's own comment predicted exactly this, which is why
        ``TestEveryUnconditionalJobIsReleaseChecked`` below now derives the set
        from the workflow instead of trusting the next author to remember.
        """
        run = run_gate(
            EVENT_NAME="push",
            RELEASE_PR="true",
            CI_RESULT="skipped",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
            DOCSTRINGS_RESULT="failure",
        )

        assert not run.passed
        assert "That job runs unconditionally" in run.summary
        assert (
            "::error::Docstring coverage (interrogate) reported failure" in run.stdout
        )

    def test_the_docstring_gate_runs_in_every_context(self) -> None:
        """``docstrings`` is the fourth job that cannot skip, pinned as such.

        Same premise as the three above: the gate passes ``false`` as its skip
        allowance and the release branch evaluates its result before exiting 0,
        and both readings only stay true while the job carries no job-level
        ``if:`` and no ``needs:``.
        """
        docstrings = JOBS["docstrings"]

        assert "if" not in docstrings
        assert "needs" not in docstrings

    def test_the_rad_citation_job_keeps_its_no_growth_ratchet(self) -> None:
        """Deleting the ratchet step must not be a silent change.

        ``--assert-no-growth`` is the only thing comparing this pull
        request's baseline against the branch it targets, so it is the only
        defence against a PR grandfathering brand-new stale citations. The
        ``--all`` step cannot notice its absence: a laundered baseline makes
        that step pass. Without this assertion, removing the step leaves
        every test in the suite green.
        """
        steps = JOBS["rad-citations"]["steps"]
        scripts = [str(step.get("run", "")) for step in steps]
        ratchet = [run for run in scripts if "--assert-no-growth" in run]

        assert len(ratchet) == 1, (
            "rad-citations must run scripts/check_rad_citations.py "
            "--assert-no-growth exactly once"
        )
        # The two-step guard, in order. `git cat-file -e REF:PATH` exits 128
        # both when the ref is missing and when only the path is, so a check
        # that tested the path alone would report a broken checkout as an
        # expected first-PR notice and skip the ratchet entirely.
        #
        # Comment lines are stripped before the ordering is read: the step's
        # own rationale comment names `git cat-file -e` while explaining why
        # the resolve has to come first, so an ordering taken over the raw
        # text reports the correct script as backwards.
        commands = "\n".join(
            line
            for line in ratchet[0].splitlines()
            if not line.lstrip().startswith("#")
        )

        assert "git rev-parse --verify" in commands
        assert commands.index("git rev-parse --verify") < commands.index(
            "git cat-file -e"
        )

    def test_a_skipped_format_check_fails_the_gate(self, run_gate) -> None:
        """A skip must not read as "formatted".

        The companion to the premise above: the workflow allows no skip, and
        the gate must reject one if it ever arrives anyway.
        """
        run = run_gate(FORMAT_TREE_RESULT="skipped")

        assert not run.passed
        assert "::error::Format (tree-wide) was skipped unexpectedly" in run.stdout

    def test_a_failure_alongside_expected_skips_is_not_called_green(
        self, run_gate
    ) -> None:
        """The disclosure must not claim greenness in a run that fails.

        On merge_group the frontend skips are legitimate and get disclosed. If
        something else fails in the same run, that disclosure still fires, and
        an annotation reading "CI Gate is green" above a real failure sends a
        reviewer looking in the wrong place. The exit code was always right
        here; the text was not.
        """
        run = run_gate(
            EVENT_NAME="merge_group",
            CI_RESULT="failure",
            FRONTEND_RESULT="skipped",
            FRONTEND_E2E_RESULT="skipped",
            DESIGN_SYSTEM_RESULT="skipped",
            CONTRACT_RESULT="skipped",
        )

        assert not run.passed
        assert "4 required job(s) were not run" in run.summary
        assert "is green" not in run.summary
        assert "is green" not in run.stdout
        assert "failing for a" in run.summary

    def test_several_unexplained_skips_are_each_reported(self, run_gate) -> None:
        """One annotation per skipped job, not just the first.

        A loop that stops at the first defect leaves the reader fixing one job
        at a time across as many CI runs as there are broken jobs.
        """
        run = run_gate(
            EVENT_NAME="pull_request",
            FRONTEND_RESULT="skipped",
            CONTRACT_RESULT="skipped",
        )

        assert not run.passed
        assert "Frontend (Node 22): skipped" in run.summary
        assert "OpenAPI Contract Drift: skipped" in run.summary
        assert run.stdout.count("::error::") >= 2

    def test_an_empty_result_fails_the_gate(self, run_gate) -> None:
        """An unset result is not an absent problem.

        ``needs.<job>.result`` is empty when the expression is misspelled or
        the job is removed from ``needs:`` without the env block following. An
        empty string matches neither ``success`` nor ``skipped``, so it must
        fall through to the catch-all rather than being read as "fine".
        """
        run = run_gate(FRONTEND_RESULT="")

        assert not run.passed
        assert "Frontend (Node 22):" in run.summary

    def test_a_broken_policy_job_fails_the_gate(self, run_gate) -> None:
        """An empty ``release_pr`` output must not be read as "not a release PR".

        If detect-release-pr fails, ``RELEASE_PR`` is empty. Treating that as
        false and then judging skips against it would be guessing.
        """
        run = run_gate(DETECT_RESULT="failure", RELEASE_PR="")

        assert not run.passed
        assert "cannot establish which skips are expected" in run.summary


# The backticks are backslash-escaped in the workflow, because they sit inside
# a double-quoted shell string where a bare backtick would open a command
# substitution. The optional `\\?` is that escape, not decoration.
WORKFLOW_REFERENCE_RE = re.compile(r"\\?`([a-z0-9-]+\.yml)\\?`")
REFERENCED_WORKFLOWS = sorted(set(WORKFLOW_REFERENCE_RE.findall(GATE_SCRIPT)))


def _triggers(workflow_path: Path) -> dict[str, Any]:
    """Read a workflow's ``on:`` mapping.

    YAML 1.1 parsers fold the bare key ``on`` into the boolean ``True``; YAML
    1.2 leaves it a string. Both are looked up so this does not depend on
    which spec version the loader defaults to.

    Args:
        workflow_path: Path to the workflow file.

    Returns:
        The trigger mapping.
    """
    yaml = YAML(typ="safe")
    with workflow_path.open(encoding="utf-8") as handle:
        parsed: dict[Any, Any] = yaml.load(handle)
    triggers = parsed.get("on", parsed.get(True))
    assert isinstance(triggers, dict), f"{workflow_path.name} has no on: mapping"
    return triggers


class TestEveryUnconditionalJobIsReleaseChecked:
    """The release loop must name every job that really runs on a release commit.

    The four per-job tests above each pin one member by hand, which is exactly
    the pattern that failed: ``format-tree`` was missing until someone noticed,
    then ``rad-citations``, then ``docstrings``. A hand-written list cannot
    fail for a job nobody thought to add. This derives the set from the
    workflow instead, so a fifth unconditional job joins the loop or fails
    here, and the loop's comment stops being a promise nothing enforces.
    """

    def test_the_loop_names_every_unconditional_gated_job(self) -> None:
        """Derive the no-``if:``/no-``needs:`` set and require the loop covers it.

        ``detect-release-pr`` is excluded because it supplies the policy the
        branch is gated on and is guarded by its own earlier exit, and jobs
        outside ``ci-gate``'s ``needs:`` are excluded because the gate never
        sees their result at all (``diversity`` is the documented case, tracked
        in ``UNGATED_JOBS``).
        """
        unconditional = {
            job_id
            for job_id in GATE_NEEDS
            if job_id != POLICY_JOB_ID
            and "if" not in JOBS[job_id]
            and "needs" not in JOBS[job_id]
        }

        assert unconditional <= RELEASE_CHECKED_JOBS, (
            f"jobs that really run on a release-automation commit but whose "
            f"result the release branch never evaluates: "
            f"{sorted(unconditional - RELEASE_CHECKED_JOBS)}. Add each to the "
            f"release loop in ci.yml, or give it a job-level `if:` so it "
            f"genuinely does not run there."
        )

    def test_the_loop_names_only_real_unconditional_jobs(self) -> None:
        """A loop entry for a job that CAN skip asserts something untrue.

        The branch's whole claim is "this result is real even though the rest
        of the suite did not run". An entry for a job carrying an ``if:`` or a
        ``needs:`` quietly breaks that claim, and would make the failure
        message above misleading rather than absent.
        """
        for job_id in RELEASE_CHECKED_JOBS:
            assert job_id in JOBS, (
                f"the release loop names {job_id!r}, which is not a job in ci.yml"
            )
            assert "if" not in JOBS[job_id], (
                f"the release loop treats {job_id!r} as unconditional, but it "
                f"carries a job-level `if:` and so can skip"
            )
            assert "needs" not in JOBS[job_id], (
                f"the release loop treats {job_id!r} as unconditional, but it "
                f"carries a `needs:` and so can skip"
            )

    def test_the_release_summary_names_every_job_the_loop_checks(self) -> None:
        """The disclosure text and the loop must not drift apart.

        The summary tells the reader which jobs really ran on a release commit.
        When the loop gained a member and the prose did not, the summary
        under-reported real coverage while the gate over-reported safety; both
        halves have to move together.
        """
        for job_id in RELEASE_CHECKED_JOBS:
            label = str(JOBS[job_id]["name"])
            assert label in RELEASE_SUMMARY_TEXT, (
                f"the release-skip summary does not mention {label!r}, which "
                f"the release loop evaluates"
            )


class TestTheReleaseDisclosurePointsAtRealCoverage:
    """The gate's release summary names its own compensating controls.

    When the gate passes a release commit it tells the reader to look at the
    scheduled scans instead. That sentence is the entire justification for
    passing an unverified commit, so it is a claim the gate makes and not
    decoration: if those workflows stop existing, or stop being scheduled, the
    gate keeps passing while pointing at coverage that is not there.
    """

    def test_the_release_summary_names_at_least_one_workflow(self) -> None:
        """Guards the two tests below against passing on an empty list."""
        assert REFERENCED_WORKFLOWS

    def test_every_named_workflow_exists_and_is_scheduled(self) -> None:
        """A named workflow that runs only on push is not a fallback.

        The whole point of the pointer is coverage whose cadence does not
        depend on what triggered the last push, which is exactly what a
        ``schedule:`` trigger provides and what nothing else does.
        """
        for name in REFERENCED_WORKFLOWS:
            path = REPO_ROOT / ".github" / "workflows" / name

            assert path.is_file(), (
                f"the release summary names {name}, which does not exist"
            )
            assert "schedule" in _triggers(path), (
                f"the release summary offers {name} as coverage independent of "
                f"push activity, but it has no schedule: trigger"
            )

    def test_the_security_scan_is_scheduled_daily(self) -> None:
        """Daily, per issue #594: the exposure window is the cron's period.

        This is the workflow whose cadence bounds how long ``main`` can sit
        unscanned against a newly published advisory, so a silent drift back
        to weekly would restore the gap this PR set out to close.
        """
        schedule = _triggers(
            REPO_ROOT / ".github" / "workflows" / "security-analysis.yml"
        )

        crons = [str(entry["cron"]) for entry in schedule["schedule"]]

        assert len(crons) == 1
        minute, hour, day_of_month, month, day_of_week = crons[0].split()

        assert [day_of_month, month, day_of_week] == ["*", "*", "*"], (
            f"cron {crons[0]!r} restricts which days it runs, so it is not daily"
        )
        # A list, range or step in either field would fire more than once a
        # day, which is not wrong but is not what the rationale comment claims.
        for field in (minute, hour):
            assert field.isdigit(), f"cron {crons[0]!r} does not run exactly once a day"
