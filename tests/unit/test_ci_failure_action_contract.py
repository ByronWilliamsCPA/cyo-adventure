"""Contract tests for ``.github/actions/ci-failure-issue`` and its call sites.

Fourteen scheduled workflows delegate their only notification channel to one
composite action. A scheduled workflow fails invisibly by construction: no pull
request turns red, so a defect in the alerting path is not a broken build, it is
nobody being told. Issue #667 is what that costs: sixteen consecutive nightly
backups were cancelled at the concurrency gate and the silence read as health.

Three classes of defect are pinned here, and the script's own behaviour is NOT
one of them:

* **Fleet invariants.** Markers must stay mutually non-prefixing and unique, or
  two workflows share a tracking issue and one workflow's recovery closes the
  other's live alert. That is a property of the fourteen call sites together, so
  no single workflow's review can see it.
* **Call-site preconditions.** The action's header states two conditions its
  correctness depends on: every call site sits in a workflow with a
  ``concurrency:`` group, and a resolve leg cannot be reached by a manual run.
  Both were prose asking a future author to remember.
* **Gate liveness.** The Node harness is the only thing executing the script,
  and ``node --test`` exits 0 when it discovers no tests. The CI leg therefore
  asserts a count floor, and this file asserts the floor is still asserted.

The script's *behaviour* is covered by
``.github/actions/ci-failure-issue/test/reconcile.test.mjs``, which runs the real
extracted script against Octokit doubles. Duplicating that here in Python would
mean reimplementing the script to test it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ACTION_DIR = REPO_ROOT / ".github" / "actions" / "ci-failure-issue"
ACTION_YML = ACTION_DIR / "action.yml"
HARNESS = ACTION_DIR / "test" / "reconcile.test.mjs"
# Added alongside the generalised `extractScript()` (fix/testing-ladder-trust):
# covers `scheduled-health-rollup.yml`'s `findTrackingIssue` extraction. The
# `alert-action` CI job runs this file in the same invocation as HARNESS, so
# both must be counted together or the floor and the runtime count diverge.
HEALTH_ROLLUP_HARNESS = WORKFLOWS_DIR / "test" / "health-rollup.test.mjs"
# Added by the task A7-i review fix pass (Important 2): covers
# `frontend/scripts/extract-failing-specs.mjs`, the sole producer of every
# scheduled e2e alert's substantive content. Not extracted from workflow YAML
# (it is a plain, directly-invokable script), but the `alert-action` CI job
# runs it in the same `node --test` invocation as HARNESS and
# HEALTH_ROLLUP_HARNESS, so all three must be counted together or the floor
# and the runtime count diverge, same reasoning as HEALTH_ROLLUP_HARNESS above.
EXTRACT_FAILING_SPECS_HARNESS = (
    REPO_ROOT / "frontend" / "scripts" / "test" / "extract-failing-specs.test.mjs"
)
CI_WORKFLOW = WORKFLOWS_DIR / "ci.yml"

ACTION_REF = "./.github/actions/ci-failure-issue"
HARNESS_JOB_ID = "alert-action"

# The two labels the fleet uses. A third would not be wrong, but it would be a
# decision, and an unreviewed typo in a `label:` input is indistinguishable from
# one: the lookup silently scopes to a label no issue carries, so the action
# files a fresh issue on every single run instead of finding the open one.
KNOWN_LABELS = frozenset({"ci-failure", "e2e-alert"})


class CallSite(NamedTuple):
    """One ``uses: ./.github/actions/ci-failure-issue`` step."""

    workflow: str
    job_id: str
    mode: str
    marker: str
    label: str
    condition: str
    triggers: frozenset[str]
    matrix_legs: int

    @property
    def where(self) -> str:
        """Human-readable location.

        Returns:
            ``workflow.yml::job-id (mode)``.
        """
        return f"{self.workflow}::{self.job_id} ({self.mode})"


def _load(path: Path) -> dict[str, Any]:
    """Parse a workflow file.

    Args:
        path: Workflow to read.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    yaml = YAML(typ="safe")
    with path.open(encoding="utf-8") as handle:
        loaded: Any = yaml.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _triggers(workflow: dict[str, Any]) -> frozenset[str]:
    """Extract a workflow's trigger names.

    ``on:`` is parsed as the boolean ``True`` by YAML 1.1 loaders, so both keys
    have to be tried. Reading only ``"on"`` yields an empty set for every file,
    which would make the manual-run rule below vacuous rather than failing.

    Args:
        workflow: Parsed workflow mapping.

    Returns:
        The set of trigger names.
    """
    raw: Any = workflow.get("on", workflow.get(True))
    if isinstance(raw, dict):
        return frozenset(str(key) for key in raw)
    if isinstance(raw, list):
        return frozenset(str(item) for item in raw)
    return frozenset({str(raw)}) if raw is not None else frozenset()


def _matrix_legs(job: dict[str, Any]) -> int:
    """Count how many legs a job's matrix expands to.

    Fail-closed on any shape this cannot count statically (a matrix built from
    an expression, a non-mapping matrix): an uncountable matrix is exactly the
    case a human needs to look at, so it returns a leg count that trips the
    assertion rather than one that passes quietly.

    Args:
        job: Parsed job mapping.

    Returns:
        The number of matrix legs; 1 for a job with no matrix.
    """
    strategy: Any = job.get("strategy")
    if strategy is None:
        return 1
    if not isinstance(strategy, dict):
        return 2
    matrix: Any = strategy.get("matrix")
    if matrix is None:
        return 1
    if not isinstance(matrix, dict):
        return 2

    axes = {k: v for k, v in matrix.items() if k not in {"include", "exclude"}}
    if not axes:
        includes: Any = matrix.get("include")
        return len(includes) if isinstance(includes, list) else 2

    legs = 1
    for value in axes.values():
        if not isinstance(value, list):
            return 2
        legs *= max(len(value), 1)
    includes = matrix.get("include")
    if isinstance(includes, list):
        legs += sum(1 for entry in includes if isinstance(entry, dict))
    return legs


def _call_sites() -> Iterator[CallSite]:
    """Find every call site by walking the workflows.

    Derived rather than listed: a hand-maintained roster cannot fail for a call
    site nobody added it to, which is the exact failure mode that let fourteen
    copies of this logic drift apart in the first place.

    Yields:
        One CallSite per matching step.
    """
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = _load(path)
        triggers = _triggers(workflow)
        jobs: Any = workflow.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if ACTION_REF not in str(step.get("uses", "")):
                    continue
                with_block: Any = step.get("with") or {}
                yield CallSite(
                    workflow=path.name,
                    job_id=str(job_id),
                    mode=str(with_block.get("mode", "open")),
                    marker=str(with_block.get("marker", "")),
                    label=str(with_block.get("label", "ci-failure")),
                    condition=f"{job.get('if', '')} || {step.get('if', '')}",
                    triggers=triggers,
                    matrix_legs=_matrix_legs(job),
                )


CALL_SITES: list[CallSite] = list(_call_sites())
RESOLVE_SITES: list[CallSite] = [s for s in CALL_SITES if s.mode == "resolve"]
ACTION_TEXT = ACTION_YML.read_text(encoding="utf-8")
HARNESS_TEXT = HARNESS.read_text(encoding="utf-8")

# Resolve legs that cannot be reached by a manual run WITHOUT naming
# `github.event_name == 'schedule'`, and why. The key is `workflow::job`; a
# resolve leg absent from both this mapping and the schedule guard is the
# failure this exemption exists to make visible rather than to hide.
#
# Same shape as UNGATED_JOBS in test_ci_gate_contract.py, and for the same
# reason: an implicit carve-out is one nobody re-examines.
MANUAL_RUN_EXEMPT: dict[str, str] = {
    "release.yml::resolve": (
        "gated on `needs.publish.result == 'success'`, and `publish` runs only "
        "on push (its own guard reads `head_commit.message`, which no other "
        "event carries). A schedule guard here would make the leg permanently "
        "dead rather than safer, because a scheduled run never produces a "
        "successful publish"
    ),
}


# Resolve legs whose green result is NOT self-evidently a measurement, and the
# expression that must gate them. A workflow can exit 0 having probed nothing;
# where that is true, "the job passed" is not evidence the tracked outage
# recovered, and closing the issue on it launders a live incident.
#
# The gate being COMPUTED is not the same as the gate being HONOURED: deleting
# the `if:` from the closing step leaves the computation in place, every job
# green, and the protection gone. That deletion is what this mapping catches.
MEASUREMENT_GATED_RESOLVES: dict[str, str] = {
    "kws-delivery-health.yml::resolve": "steps.measured.outputs.measured",
}


def _harness_floor() -> int:
    """Read the MIN_TESTS floor off the CI step.

    Returns:
        The declared floor.
    """
    jobs: Any = _load(CI_WORKFLOW).get("jobs") or {}
    steps: Any = jobs[HARNESS_JOB_ID]["steps"]
    harness_step = next(
        step for step in steps if "reconcile.test.mjs" in str(step.get("run", ""))
    )
    return int(str((harness_step.get("env") or {})["MIN_TESTS"]))


def _run_harness_and_count() -> int:
    """Execute the Node harness(es) and return how many tests passed.

    Shelling out rather than reasoning about the source, for the same reason
    ``test_ci_gate_contract.py`` executes the gate's shell script: a count
    derived by reading the file is a second implementation of the test runner,
    and it was wrong the first time it was tried here.

    Runs all three files the CI step runs, in one ``node --test`` invocation,
    so the reported count matches what the gate actually measures rather than
    just HARNESS's own total.

    Returns:
        The number of passing tests the harness reported.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH; the CI leg asserts this floor there")
    completed = subprocess.run(
        [
            node,
            "--test",
            "--test-reporter=tap",
            str(HARNESS),
            str(HEALTH_ROLLUP_HARNESS),
            str(EXTRACT_FAILING_SPECS_HARNESS),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, (
        f"the harness itself failed, so no floor can be judged:\n"
        f"{completed.stdout[-4000:]}"
    )
    match = re.search(r"^# pass (\d+)$", completed.stdout, re.MULTILINE)
    assert match is not None, (
        f"the harness produced no TAP `# pass` summary; the CI leg's own "
        f"parser reads the same line, so this is a real break:\n"
        f"{completed.stdout[-2000:]}"
    )
    return int(match.group(1))


class TestTheCallSitesWereActuallyFound:
    """Guards every derived test below against a silently empty parse."""

    def test_the_fleet_is_present(self) -> None:
        """An empty roster would make every assertion here vacuous.

        The floor is deliberately below the current count so adding a workflow
        does not fail this test, and deliberately above zero so a broken parse
        or a moved directory does.
        """
        assert len(CALL_SITES) >= 20, (
            f"found only {len(CALL_SITES)} call sites; the parse or the "
            f"action path {ACTION_REF!r} has drifted"
        )

    def test_both_modes_are_represented(self) -> None:
        """A roster of only one mode would silently skip half the rules."""
        assert {site.mode for site in CALL_SITES} == {"open", "resolve"}


class TestMarkersCannotCollide:
    """Two workflows sharing a tracking issue is a cross-workflow outage."""

    def test_no_marker_is_a_prefix_of_another(self) -> None:
        """Matching is by ``startsWith``, so a prefix is a collision.

        If ``[e2e]`` and ``[e2e-prod]`` both existed, the ``[e2e]`` workflow
        would match the ``[e2e-prod]`` issue and comment on it, and its own
        green run would CLOSE it: one workflow's recovery silently retires
        another's live alert. Uniqueness alone does not catch this, which is
        why prefixing is asserted separately.
        """
        markers = sorted({site.marker for site in CALL_SITES})
        collisions = [
            (shorter, longer)
            for shorter in markers
            for longer in markers
            if shorter != longer and longer.startswith(shorter)
        ]

        assert collisions == [], (
            f"marker prefix collisions: {collisions}. Matching is by prefix, "
            f"so the shorter marker matches the longer one's issue"
        )

    def test_every_marker_is_non_empty_and_bracketed(self) -> None:
        """The bracket is what makes prefixing safe in practice.

        ``[release]`` cannot be a prefix of ``[release-notes]`` by accident the
        way a bare ``release`` can, because the closing bracket terminates it.
        """
        for site in CALL_SITES:
            assert re.fullmatch(r"\[[a-z0-9-]+\]", site.marker), (
                f"{site.where} has marker {site.marker!r}; expected a "
                f"lowercase bracketed slug"
            )

    def test_each_workflow_uses_one_marker(self) -> None:
        """A workflow's open and resolve legs must address the same issue.

        Disagreeing markers give a workflow an issue it files but never closes,
        which is the stale-backlog condition the resolve mode was added to end.
        """
        per_workflow: dict[str, set[str]] = {}
        for site in CALL_SITES:
            per_workflow.setdefault(site.workflow, set()).add(site.marker)

        drifted = {name: sorted(m) for name, m in per_workflow.items() if len(m) > 1}

        assert drifted == {}, f"workflows whose legs use different markers: {drifted}"

    def test_no_two_workflows_share_a_marker(self) -> None:
        """One marker per workflow, or a recovery closes someone else's alert."""
        owners: dict[str, set[str]] = {}
        for site in CALL_SITES:
            owners.setdefault(site.marker, set()).add(site.workflow)

        shared = {marker: sorted(w) for marker, w in owners.items() if len(w) > 1}

        assert shared == {}, f"markers claimed by more than one workflow: {shared}"


class TestLabelsStayOnTheKnownSet:
    """A mistyped label scopes the lookup to nothing and files a duplicate every run."""

    def test_every_label_is_known(self) -> None:
        """An unrecognised label is a typo until someone decides otherwise."""
        for site in CALL_SITES:
            assert site.label in KNOWN_LABELS, (
                f"{site.where} passes label {site.label!r}; known labels are "
                f"{sorted(KNOWN_LABELS)}. Adding a third is a decision: widen "
                f"KNOWN_LABELS deliberately rather than by typo"
            )

    def test_each_workflow_uses_one_label(self) -> None:
        """The lookup only ever sees one label, so the legs must agree.

        An open leg on ``ci-failure`` and a resolve leg on ``e2e-alert`` cannot
        see each other's issue, so the workflow files alerts it can never close.
        """
        per_workflow: dict[str, set[str]] = {}
        for site in CALL_SITES:
            per_workflow.setdefault(site.workflow, set()).add(site.label)

        drifted = {name: sorted(v) for name, v in per_workflow.items() if len(v) > 1}

        assert drifted == {}, f"workflows whose legs use different labels: {drifted}"

    def test_both_labels_are_in_use(self) -> None:
        """Keeps the check above from passing against a one-label fleet.

        The ``e2e-alert`` group exists because three workflows carried their own
        copies of this logic with the same pagination and pull-request defects.
        If they ever revert to inline scripts this test fails rather than the
        label check quietly narrowing to a single value.
        """
        assert {site.label for site in CALL_SITES} == KNOWN_LABELS


class TestTheActionsOwnPreconditionsHold:
    """The header states two conditions its correctness depends on."""

    def test_every_call_site_workflow_has_a_concurrency_group(self) -> None:
        """This is the ``#EDGE concurrency`` marker's ``#VERIFY``.

        The find-then-create sequence is not atomic, so two simultaneous runs
        of the same workflow could both miss the issue and file two. Nothing in
        the action prevents that; the call site's ``concurrency:`` group is what
        bounds it. The header says so and then asks a future author to
        remember, which is what this test replaces.
        """
        missing = sorted(
            {
                site.workflow
                for site in CALL_SITES
                if not _load(WORKFLOWS_DIR / site.workflow).get("concurrency")
            }
        )

        assert missing == [], (
            f"workflows calling ci-failure-issue with no `concurrency:` group: "
            f"{missing}. Without one, two overlapping runs can both miss the "
            f"open issue and file a duplicate"
        )

    def test_no_workflow_re_inlines_the_lookup(self) -> None:
        """ "Do not re-inline this logic into a workflow" is otherwise unenforced.

        A fresh copy of the ~40 lines is how the fleet got here: eight copies
        matched by prefix and six by equality, seven never paginated, and only
        one filtered pull requests. A re-inlined copy also escapes the harness
        entirely, so it is untested by construction.
        """
        offenders = sorted(
            path.name
            for path in WORKFLOWS_DIR.glob("*.yml")
            if "issues.listForRepo" in path.read_text(encoding="utf-8")
        )

        assert offenders == [], (
            f"workflows calling issues.listForRepo directly: {offenders}. Use "
            f"{ACTION_REF} instead; an inline copy is covered by no test"
        )

    def test_no_call_site_sits_in_a_multi_leg_matrix_job(self) -> None:
        """A ``concurrency:`` group does not serialize legs within one run.

        The action's find-then-create is not atomic. A ``concurrency:`` group
        bounds two overlapping RUNS, which is what the test above checks, and
        that is the whole of what it bounds: legs of a single run start
        together, so two failing legs calling the action on the same marker can
        both miss the issue and file two.

        ``cifuzzy.yml`` is the live instance, and it passes only because
        ``sanitizer: [address]`` has one leg. Adding a second sanitizer is a
        one-line change that would silently make the race real, which is
        precisely why this is an assertion and not a comment.
        """
        offenders = sorted(
            f"{site.where} in a {site.matrix_legs}-leg matrix"
            for site in CALL_SITES
            if site.matrix_legs > 1
        )

        assert offenders == [], (
            f"call sites inside a multi-leg matrix job: {offenders}. Legs of "
            f"one run are not serialized by a `concurrency:` group, so these "
            f"can file duplicate issues. Route the alerting through a single "
            f"downstream job (see kws-delivery-health.yml's probe + alert)"
        )

    def test_the_kws_tier_count_matches_its_matrix(self) -> None:
        """``EXPECTED_TIERS`` is a hardcoded count of a matrix elsewhere.

        ``kws-delivery-health.yml``'s resolve leg refuses to close its issue
        unless every tier reported a genuinely-measured state, because two of
        the probe's branches record an outcome and exit 0 having measured
        nothing. That check compares against a literal ``EXPECTED_TIERS``, so
        adding a third tier to the probe matrix without touching the literal
        would let the new tier go unmeasured and still close the issue: the
        drift restores the exact defect the gate exists to prevent, and does it
        with every job green.
        """
        workflow = _load(WORKFLOWS_DIR / "kws-delivery-health.yml")
        jobs: Any = workflow.get("jobs") or {}
        probe: Any = jobs.get("probe") or {}
        matrix: Any = ((probe.get("strategy") or {}).get("matrix")) or {}

        # The matrix names its tiers through `include:` (each entry pairs a tier
        # with its GitHub environment) rather than a bare `tier:` axis, so both
        # shapes are read. Reading only the axis returns None and would compare
        # nothing, which is how this test would pass while checking nothing.
        axis: Any = matrix.get("tier")
        tiers: list[str] = (
            [str(v) for v in axis]
            if isinstance(axis, list)
            else [
                str(entry["tier"])
                for entry in (matrix.get("include") or [])
                if isinstance(entry, dict) and "tier" in entry
            ]
        )

        assert tiers, (
            "could not read the probe matrix's tiers from either a `tier:` axis "
            "or `include:`; if the matrix moved, this test is now vacuous and "
            "must be repointed"
        )

        resolve: Any = jobs.get("resolve") or {}
        declared: str | None = None
        for step in resolve.get("steps") or []:
            if isinstance(step, dict) and "EXPECTED_TIERS" in (step.get("env") or {}):
                declared = str((step.get("env") or {})["EXPECTED_TIERS"])

        assert declared is not None, (
            "kws-delivery-health.yml's resolve job declares no EXPECTED_TIERS. "
            "Without it a tier that never reported cannot be distinguished from "
            "one that reported healthy"
        )
        assert declared == str(len(tiers)), (
            f"EXPECTED_TIERS is {declared} but the probe matrix has "
            f"{len(tiers)} tiers ({tiers}). A tier the gate does not expect can "
            f"go unmeasured and still close the tracking issue"
        )


class TestAResolveLegCannotBeReachedByAManualRun:
    """A green manual run must not close an issue the schedule is still failing."""

    def test_every_resolve_leg_is_guarded_or_exempt(self) -> None:
        """The 2026-08-11 backup outage is the shape this prevents.

        A scheduled run cancelled at the concurrency gate dispatches zero jobs,
        so the workflow reports nothing at all. If a human then triggers the
        same workflow manually and it passes, an unguarded resolve leg closes
        the tracking issue while the schedule is still dead: the alert is
        retired by a run that proved nothing about the thing being monitored.
        """
        unguarded = [
            site.where
            for site in RESOLVE_SITES
            if "github.event_name == 'schedule'" not in site.condition
            and f"{site.workflow}::{site.job_id}" not in MANUAL_RUN_EXEMPT
            and site.triggers != frozenset({"schedule"})
        ]

        assert unguarded == [], (
            f"resolve legs a manual run can reach: {unguarded}. Add "
            f"`github.event_name == 'schedule'` to the job's `if:`, or add an "
            f"entry to MANUAL_RUN_EXEMPT stating why a manual run cannot "
            f"reach it"
        )

    def test_the_exemption_names_only_real_resolve_legs(self) -> None:
        """A stale exemption silently re-opens the hole it recorded.

        If a job is renamed, its entry stops matching anything and the
        successor lands back in the unguarded set with no exemption. Pinning
        the mapping to reality keeps the failure above pointing at a real name.
        """
        real = {f"{site.workflow}::{site.job_id}" for site in RESOLVE_SITES}

        assert set(MANUAL_RUN_EXEMPT) <= real, (
            f"MANUAL_RUN_EXEMPT names legs that are not resolve call sites: "
            f"{sorted(set(MANUAL_RUN_EXEMPT) - real)}"
        )

    def test_a_measurement_gated_resolve_actually_honours_its_gate(self) -> None:
        """Computing the gate and honouring it are different things.

        ``kws-delivery-health.yml``'s probe records an outcome and exits 0 on
        two branches that measured nothing: an absent base URL, and an absent
        readiness check inside the production grace. The resolve job therefore
        computes whether every tier was really measured, and must not close the
        issue when it was not.

        Removing the ``if:`` from the closing step is a one-line change that
        keeps the computation, keeps every job green, and restores the original
        defect in full. Nothing else in this file notices it, which is the
        reason this test exists.
        """
        by_where = {f"{s.workflow}::{s.job_id}": s for s in RESOLVE_SITES}
        missing: list[str] = []
        for where, guard in MEASUREMENT_GATED_RESOLVES.items():
            site = by_where.get(where)
            if site is None:
                missing.append(f"{where}: no such resolve leg")
            elif guard not in site.condition:
                missing.append(
                    f"{where}: closes without checking `{guard}`, so a run that "
                    f"measured nothing can close the issue "
                    f"(condition: {site.condition!r})"
                )

        assert missing == [], f"measurement gate declared but not honoured: {missing}"

    def test_the_exemption_is_not_the_common_case(self) -> None:
        """Most legs must carry the real guard, or the rule is a formality.

        An exemption mapping large enough to cover the fleet would satisfy the
        test above while asserting nothing, so the balance is asserted too.
        """
        guarded = [
            site
            for site in RESOLVE_SITES
            if "github.event_name == 'schedule'" in site.condition
        ]

        assert len(guarded) > len(MANUAL_RUN_EXEMPT) * 3


class TestTheHarnessIsWiredIntoARealGate:
    """An unexecuted harness is indistinguishable from a passing one."""

    def test_the_harness_file_exists_and_targets_the_live_action(self) -> None:
        """A harness reading a copied fixture cannot fail for a drifted action."""
        assert HARNESS.is_file()
        assert "extractScript()" in HARNESS_TEXT
        assert "action.yml" in (ACTION_DIR / "test" / "harness.mjs").read_text(
            encoding="utf-8"
        )

    def test_the_ci_job_exists_and_runs_the_harness(self) -> None:
        """The gate has to actually invoke it, not merely check it in."""
        jobs: Any = _load(CI_WORKFLOW).get("jobs") or {}

        assert HARNESS_JOB_ID in jobs, (
            f"ci.yml has no {HARNESS_JOB_ID!r} job, so the harness is checked "
            f"in but never executed"
        )
        run_steps = " ".join(
            str(step.get("run", "")) for step in jobs[HARNESS_JOB_ID]["steps"]
        )
        assert "node --test" in run_steps
        assert "reconcile.test.mjs" in run_steps
        assert "health-rollup.test.mjs" in run_steps, (
            "ci.yml no longer runs health-rollup.test.mjs, so a workflow's "
            "generalised findTrackingIssue extraction is checked in but "
            "never executed"
        )
        assert "extract-failing-specs.test.mjs" in run_steps, (
            "ci.yml no longer runs extract-failing-specs.test.mjs, so the "
            "sole producer of every scheduled e2e alert's substantive "
            "content is checked in but never executed"
        )

    def test_the_ci_job_asserts_a_test_count_floor(self) -> None:
        """``node --test`` exits 0 when it discovers no tests.

        A moved or renamed harness file therefore turns a required leg green
        while executing nothing, which reads exactly like a passing suite. The
        floor check is the only thing separating those two states, so deleting
        it must fail a test rather than pass CI. Cited by the ``#VERIFY`` on
        that step.
        """
        jobs: Any = _load(CI_WORKFLOW).get("jobs") or {}
        steps: Any = jobs[HARNESS_JOB_ID]["steps"]
        harness_step = next(
            step for step in steps if "reconcile.test.mjs" in str(step.get("run", ""))
        )

        assert "MIN_TESTS" in (harness_step.get("env") or {}), (
            "the harness step declares no MIN_TESTS floor, so a suite that "
            "discovered nothing would report success"
        )
        assert "-lt" in str(harness_step["run"]), (
            "MIN_TESTS is declared but never compared, which is the same as "
            "having no floor"
        )

    def test_the_floor_is_reachable_and_tight(self) -> None:
        """The floor must sit at or just below what the suite really reports.

        A static count of ``test(`` occurrences is NOT sufficient here, and
        finding that out is why this runs the suite: five of the cases come
        from one parametrised loop, so the source declares 38 ``test(`` calls
        and the runtime reports 42. A proxy that undercounts by four would
        have rejected a correct floor and, worse, accepted one four cases too
        low.

        Tightness matters as much as reachability. A floor far below the real
        count still passes CI after the suite silently loses a third of its
        cases, which is the state this whole file exists to make impossible.
        """
        floor = _harness_floor()
        reported = _run_harness_and_count()

        assert floor <= reported, (
            f"MIN_TESTS is {floor} but the harness reports {reported} passing "
            f"tests, so the CI leg fails on a correct suite"
        )
        assert floor >= reported - 5, (
            f"MIN_TESTS is {floor} against {reported} real tests; a floor that "
            f"slack lets the suite lose cases without failing CI. Raise it in "
            f"step with the suite"
        )


class TestTheActionKeepsItsInjectionSafeShape:
    """The ``#CRITICAL security`` note's ``#VERIFY``, in static form."""

    @pytest.mark.parametrize(
        "input_name",
        ["marker", "label", "mode", "summary", "body", "comment-body", "assignee"],
    )
    def test_every_interpolated_input_reaches_the_script_through_env(
        self, input_name: str
    ) -> None:
        """A ``${{ }}`` expansion inside a ``script:`` block executes as code.

        Every value here carries interpolated run data, so the env path is what
        keeps a body containing a backtick from changing the script's
        behaviour. The harness asserts the runtime half of this; the static
        half is that no input is ever spliced into the script source.
        """
        script_start = ACTION_TEXT.index("script: |")
        script = ACTION_TEXT[script_start:]

        assert f"inputs.{input_name}" not in script, (
            f"inputs.{input_name} is interpolated inside the script body; pass "
            f"it through the step's env: block instead"
        )
        assert f"${{{{ inputs.{input_name} }}}}" in ACTION_TEXT[:script_start], (
            f"inputs.{input_name} is not bound in the env: block"
        )
