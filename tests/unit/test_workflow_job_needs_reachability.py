"""Detects jobs whose ``needs:`` shape makes their ``if:`` unreachable.

GitHub Actions checks that every job named in ``needs:`` completed
successfully BEFORE it evaluates that job's own ``if:`` at all, unless the
``if:`` expression itself calls one of the four status check functions
(``success()``, ``failure()``, ``cancelled()``, ``always()``), which
replaces that implicit gate. A skipped job does not count as a success for
that check. So a job whose ``if:`` reads
``needs.publish.result == 'success'`` while its ``needs:`` also lists
``propose``, a job that is skipped whenever ``publish`` runs, never gets far
enough for GitHub to look at that ``if:`` at all: the job reads as gated on
``publish``, but it is actually gated on ``publish`` AND ``propose``, and
``propose`` is never both present and successful on the same run as
``publish``.

This is exactly the ``.github/workflows/release.yml::resolve`` defect fixed
alongside this test (see the job's own comment for the incident: a fully
successful v0.84.0 release, run 33140125879, still reported ``resolve`` as
skipped). A job that cannot run looks identical in the Actions UI to a job
that ran and found nothing to do, so nothing short of running the fleet
through this rule would have caught it, and nothing did until now.

Scope, stated plainly because a rule that overclaims its coverage is the same
defect this file exists to catch:

* This only inspects a job's own job-level ``if:`` field. A step-level
  ``if:`` gated the same way is not covered; none of this repository's
  ``needs.<x>.result`` step-level references gate a whole job's execution,
  they only feed a later step's environment, so this scope was chosen to
  match the actual shape of the defect rather than to inflate coverage.
* Only the literal ``needs.<x>.result`` pattern is matched. A job gated on
  ``needs.<x>.outputs.<y>`` has the identical implicit-success problem (the
  same implicit gate applies to any custom ``if:``) but is not detected here.
  This is a known false negative, not an assumption that the pattern is the
  only source of the defect.
* "Can be skipped" is approximated as "the job declares its own job-level
  ``if:``". A job with no ``if:`` at all is treated as unconditional, even
  though it could still be skipped transitively if one of ITS OWN ``needs:``
  is itself conditional. Walking the full transitive graph would catch more,
  but a rule this file's author cannot state in one sentence is a rule the
  next author will not trust enough to keep passing. This is the deliberate
  conservative choice the task asked for, and it is a known false negative:
  a chain of two or more unconditional jobs behind a conditional root is not
  currently traced.
* An earlier revision of this file accepted only ``always(`` and
  ``!cancelled(`` as escapes, and asserted in this docstring that a bare
  ``success()`` or ``failure()`` does not lift the implicit gate. That was
  wrong, and the code was wrong the same way. GitHub adds the implicit
  ``success()`` gate only to an ``if:`` that calls NONE of the four status
  check functions; ANY of ``success()``, ``failure()``, ``cancelled()`` or
  ``always()`` replaces it. ``.github/workflows/release.yml``'s own
  ``resolve`` comment states this correctly, and its ``alert`` job relies
  on it: ``alert`` declares ``needs: [propose, publish]`` with
  ``if: failure() || cancelled()`` and runs fine with one of the two
  skipped. Under the old rule an ``alert`` phrased
  ``failure() && needs.publish.result == 'failure'`` would have been
  flagged as unreachable while being perfectly correct, which is a check
  failing on working code: the precise failure mode this file exists to
  prevent, pointed the other way.

Run across every workflow in ``.github/workflows/``, not only
``release.yml``: the defect is a property of a job's ``needs:`` shape, and
nothing about it is specific to the release pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Matches `needs.<job-id>.result` inside an `if:` expression, with or
# without the `${{ }}` wrapper (GitHub allows a bare `if:` without it).
NEEDS_RESULT_PATTERN = re.compile(r"needs\.([A-Za-z0-9_-]+)\.result")

# GitHub adds its implicit "every job in `needs:` must have succeeded" gate
# to a job-level `if:` ONLY when that expression calls none of the four
# status check functions. Naming any one of them replaces the implicit gate,
# so the job's `if:` is evaluated even when a job in `needs:` was skipped.
# `cancelled(` covers `!cancelled(` as a substring, and `failure(` covers
# `!failure(`.
#
# #ASSUME external-resource: GitHub treats an explicit bare `success()` the
# same as the other three, that is, as replacing the implicit gate rather
# than restating it, so a job whose `if:` is `success() && ...` runs with a
# skipped sibling in `needs:`. This follows GitHub's own definition
# (`success()` is true when nothing previous failed or was cancelled, and a
# skipped job is neither) and the rule written into release.yml's `resolve`
# comment. If it is wrong, this member is a false negative, never a false
# positive, so the failure mode is a missed finding rather than a red build
# on correct code.
# #VERIFY before relying on a bare `success()` as an escape in a real
# workflow, confirm on one run that the job is not reported as skipped.
SKIP_IMMUNE_MARKERS = ("always(", "cancelled(", "failure(", "success(")


def _parse(source: str) -> dict[str, Any]:
    """Parse workflow YAML from a string.

    Split out from :func:`_load` so the fixture-based controls below reach
    the rule through the same parser the fleet scan uses, rather than
    hand-building the dicts the parser would have produced.

    Args:
        source: Workflow YAML text.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    yaml = YAML(typ="safe")
    loaded: Any = yaml.load(source)
    return loaded if isinstance(loaded, dict) else {}


def _load(path: Path) -> dict[str, Any]:
    """Parse a workflow file.

    Args:
        path: Workflow to read.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    return _parse(path.read_text(encoding="utf-8"))


def _needs_list(job: dict[str, Any]) -> list[str]:
    """Normalise a job's ``needs:`` into a list of job ids.

    Args:
        job: Parsed job mapping.

    Returns:
        The job ids named in ``needs:``, in declaration order.
    """
    needs: Any = job.get("needs")
    if needs is None:
        return []
    if isinstance(needs, str):
        return [needs]
    if isinstance(needs, list):
        return [str(item) for item in needs]
    return []


def _job_can_be_skipped(job: dict[str, Any]) -> bool:
    """Conservative "can this job be skipped" rule.

    A job is treated as skippable exactly when it declares its own
    job-level ``if:``. Absence of ``if:`` is treated as unconditional, which
    is a known simplification: a job can still be skipped transitively
    through its own ``needs:`` chain. See the module docstring's false
    negatives.

    Args:
        job: Parsed job mapping.

    Returns:
        Whether the job declares a job-level ``if:``.
    """
    return job.get("if") is not None


class UnreachableJob(NamedTuple):
    """One job whose ``needs:`` shape makes its ``if:`` unreachable."""

    workflow: str
    job_id: str
    referenced: str
    skippable_sibling: str
    condition: str

    @property
    def where(self) -> str:
        """Human-readable location.

        Returns:
            ``workflow.yml::job-id``.
        """
        return f"{self.workflow}::{self.job_id}"


def _skippable_siblings(
    needs_list: list[str], referenced_in_needs: set[str], jobs: dict[str, Any]
) -> list[str]:
    """Find sibling jobs in ``needs:`` that are not checked but can skip.

    Args:
        needs_list: The job's full ``needs:`` list, in declaration order.
        referenced_in_needs: The subset of ``needs_list`` the ``if:`` checks.
        jobs: All jobs in the same workflow, keyed by job id.

    Returns:
        The ids of sibling jobs, outside ``referenced_in_needs``, that
        declare their own job-level ``if:`` and so can be skipped.
    """
    siblings: list[str] = []
    for sibling_id in needs_list:
        if sibling_id in referenced_in_needs:
            continue
        sibling: Any = jobs.get(sibling_id)
        if isinstance(sibling, dict) and _job_can_be_skipped(sibling):
            siblings.append(sibling_id)
    return siblings


def _check_job(
    workflow_name: str, job_id: str, job: dict[str, Any], jobs: dict[str, Any]
) -> list[UnreachableJob]:
    """Apply the detection rule to a single job.

    A job is flagged when all three hold:

    1. Its job-level ``if:`` matches ``needs.<x>.result`` for some ``x`` that
       is also named in its own ``needs:``.
    2. Its ``needs:`` names at least one OTHER job (not ``x``) that can be
       skipped, per :func:`_job_can_be_skipped`.
    3. Its ``if:`` contains none of ``SKIP_IMMUNE_MARKERS``.

    Args:
        workflow_name: File name of the workflow the job lives in.
        job_id: The job's id.
        job: Parsed job mapping.
        jobs: All jobs in the same workflow, keyed by job id.

    Returns:
        One :class:`UnreachableJob` per skippable, unchecked sibling; empty
        if the job does not match the rule.
    """
    if_text: Any = job.get("if")
    if not if_text:
        return []
    if_text = str(if_text)

    referenced = set(NEEDS_RESULT_PATTERN.findall(if_text))
    if not referenced:
        return []
    if any(marker in if_text for marker in SKIP_IMMUNE_MARKERS):
        return []

    needs_list = _needs_list(job)
    referenced_in_needs = referenced & set(needs_list)
    if not referenced_in_needs:
        return []

    return [
        UnreachableJob(
            workflow=workflow_name,
            job_id=job_id,
            referenced=", ".join(sorted(referenced_in_needs)),
            skippable_sibling=sibling_id,
            condition=if_text,
        )
        for sibling_id in _skippable_siblings(needs_list, referenced_in_needs, jobs)
    ]


def _scan_workflow(
    workflow_name: str, workflow: dict[str, Any]
) -> list[UnreachableJob]:
    """Apply the detection rule to every job in one parsed workflow.

    Args:
        workflow_name: File name to attribute findings to.
        workflow: The parsed workflow mapping.

    Returns:
        Every job in this workflow matching the rule.
    """
    findings: list[UnreachableJob] = []
    jobs: Any = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        return findings

    for job_id, job in jobs.items():
        if isinstance(job, dict):
            findings.extend(_check_job(workflow_name, str(job_id), job, jobs))

    return findings


def _find_unreachable_jobs() -> list[UnreachableJob]:
    """Walk every workflow job and apply the detection rule.

    Returns:
        Every job matching the rule, across all workflows.
    """
    findings: list[UnreachableJob] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        findings.extend(_scan_workflow(path.name, _load(path)))
    return findings


# ---------------------------------------------------------------------------
# Fixture-based positive control for the rule itself.
#
# `assert UNREACHABLE_JOBS == []` is the fleet assertion, and its passing
# state is an empty list. That is exactly what a broken detector produces, so
# on its own it cannot distinguish "the fleet is clean" from "the rule matches
# nothing". Inverting `_job_can_be_skipped` to always return False used to
# leave the whole module green. These fixtures give the rule a workflow it
# MUST flag and several it must NOT, so the rule is observed working rather
# than assumed to.
#
# The fixture is built here and parsed with the production `_parse`; no broken
# job is ever added to a real workflow.
# ---------------------------------------------------------------------------

# Two producer jobs that never run on the same event, plus one consumer, which
# is the `release.yml` shape the rule was written for.
_FIXTURE_TEMPLATE = """\
name: fixture
on:
  push:
    branches: [main]
jobs:
  propose:
{propose_if}    runs-on: ubuntu-latest
    steps:
      - run: echo propose
  publish:
    if: startsWith(github.event.head_commit.message, 'chore(release):')
    runs-on: ubuntu-latest
    steps:
      - run: echo publish
  resolve:
    needs: {resolve_needs}
    if: {resolve_if}
    runs-on: ubuntu-latest
    steps:
      - run: echo resolve
"""


def _scan_fixture(
    *, resolve_needs: str, resolve_if: str, propose_conditional: bool = True
) -> list[UnreachableJob]:
    """Render a synthetic workflow and run the real rule over it.

    Args:
        resolve_needs: The consumer job's ``needs:`` value, as YAML.
        resolve_if: The consumer job's ``if:`` value, as a YAML scalar.
        propose_conditional: Whether the unchecked sibling declares its own
            ``if:`` and so counts as skippable.

    Returns:
        Whatever :func:`_scan_workflow` finds in the rendered workflow.
    """
    propose_if = (
        "    if: github.event_name == 'schedule'\n" if propose_conditional else ""
    )
    source = _FIXTURE_TEMPLATE.format(
        propose_if=propose_if,
        resolve_needs=resolve_needs,
        resolve_if=resolve_if,
    )
    return _scan_workflow("fixture.yml", _parse(source))


class TestTheRuleDetectsTheDefectItClaimsTo:
    """Positive and negative controls, so the fleet assertion means something.

    Without these, every assertion in this module holds against a rule that
    can never fire, which is the same class of defect the module exists to
    catch: a check that reviews well and cannot fail when its subject breaks.
    """

    def test_a_needs_on_an_unchecked_skippable_sibling_is_detected(self) -> None:
        """The pre-fix ``release.yml::resolve`` shape must be flagged.

        ``needs: [propose, publish]`` with ``if:`` checking only
        ``publish``: reverting the real fix reproduces exactly this, and the
        rule has to emit the finding, naming the right sibling.
        """
        findings = _scan_fixture(
            resolve_needs="[propose, publish]",
            resolve_if="needs.publish.result == 'success'",
        )
        assert [
            (finding.where, finding.referenced, finding.skippable_sibling)
            for finding in findings
        ] == [("fixture.yml::resolve", "publish", "propose")]

    def test_the_same_defect_wrapped_in_expression_syntax_is_detected(self) -> None:
        """``NEEDS_RESULT_PATTERN``'s "with or without ``${{ }}``" claim.

        The comment on that pattern says the wrapper is optional. No real
        workflow in this repository exercises the wrapped form against this
        rule, so the claim was untested.
        """
        findings = _scan_fixture(
            resolve_needs="[propose, publish]",
            resolve_if="${{ needs.publish.result == 'success' }}",
        )
        assert [finding.skippable_sibling for finding in findings] == ["propose"]

    def test_narrowing_needs_to_the_checked_job_clears_the_finding(self) -> None:
        """The real fix, applied to the fixture, must silence the rule.

        Paired with the test above this is the discrimination proof: the
        rule responds to the ``needs:`` shape, not to the fixture merely
        existing.
        """
        assert (
            _scan_fixture(
                resolve_needs="[publish]",
                resolve_if="needs.publish.result == 'success'",
            )
            == []
        )

    def test_an_unconditional_sibling_is_not_treated_as_skippable(self) -> None:
        """A sibling with no ``if:`` of its own cannot skip, so no finding.

        This is the arm that dies if `_job_can_be_skipped` is stubbed to
        always return True, the mirror of the arm above it.
        """
        assert (
            _scan_fixture(
                resolve_needs="[propose, publish]",
                resolve_if="needs.publish.result == 'success'",
                propose_conditional=False,
            )
            == []
        )

    @pytest.mark.parametrize(
        "guarded_if",
        [
            "always() && needs.publish.result == 'success'",
            "${{ !cancelled() && needs.publish.result == 'success' }}",
            "cancelled() && needs.publish.result == 'cancelled'",
            "failure() && needs.publish.result == 'failure'",
            "success() && needs.publish.result == 'success'",
        ],
        ids=["always", "not-cancelled", "cancelled", "failure", "success"],
    )
    def test_any_status_check_function_lifts_the_implicit_gate(
        self, guarded_if: str
    ) -> None:
        """None of the four status check functions may be flagged.

        Regression test for the rule's own false positive. Before this, only
        ``always(`` and ``!cancelled(`` counted as escapes, so a correct
        ``if: failure() && needs.publish.result == 'failure'`` alongside a
        skippable sibling was reported as unreachable. GitHub adds its
        implicit ``success()`` gate only to an ``if:`` naming none of the
        four, so all five conditions here are reachable and a finding on any
        of them is the rule failing on working code.
        """
        assert (
            _scan_fixture(resolve_needs="[propose, publish]", resolve_if=guarded_if)
            == []
        )


UNREACHABLE_JOBS: list[UnreachableJob] = _find_unreachable_jobs()


class TestTheRuleParsesTheFleet:
    """Guards the assertion below against a silently empty parse."""

    def test_at_least_one_needs_result_gate_exists(self) -> None:
        """A zero-hit parse would make the main test vacuously pass.

        Several workflows in this repository gate a ``resolve`` job on
        exactly one upstream job's ``result``; if none were found, the YAML
        loader or the glob has drifted rather than the fleet having gotten
        cleaner.
        """
        hits = 0
        for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            workflow = _load(path)
            jobs: Any = workflow.get("jobs") or {}
            if not isinstance(jobs, dict):
                continue
            for job in jobs.values():
                if isinstance(job, dict) and NEEDS_RESULT_PATTERN.search(
                    str(job.get("if") or "")
                ):
                    hits += 1

        assert hits >= 5, (
            f"found only {hits} job(s) gated on `needs.<x>.result`; the "
            f"parse or the glob pattern has drifted"
        )


class TestNoJobIsUnreachableByConstruction:
    """A job cannot run at all is a different failure than a job that ran
    clean, and the two must not look identical.
    """

    def test_no_job_needs_a_skippable_sibling_it_never_checks(self) -> None:
        """Reproduces the release.yml::resolve defect and its fix.

        Pre-fix, ``release.yml``'s ``resolve`` job declared
        ``needs: [propose, publish]`` with
        ``if: needs.publish.result == 'success'``. ``propose`` runs only on
        schedule/workflow_dispatch and ``publish`` runs only on push, so the
        two never both run, and GitHub's implicit "every job in `needs:`
        must have succeeded" check saw a skipped ``propose`` and skipped
        ``resolve`` before ever reading its ``if:``. Reverting the fix
        (``needs: [propose, publish]`` restored, ``if:`` left as written) is
        the exact mutation this test exists to catch; the fix
        (``needs: [publish]``) makes this test pass again.
        """
        assert UNREACHABLE_JOBS == [], "\n".join(
            [
                "job(s) unreachable due to a skippable sibling in `needs:`:",
                *(
                    f"  {finding.where}: `if:` checks "
                    f"needs.{finding.referenced}.result, but `needs:` also "
                    f"names {finding.skippable_sibling!r}, which declares "
                    f"its own conditional `if:` and can be skipped. "
                    f"GitHub's implicit success check then requires "
                    f"{finding.skippable_sibling!r} to succeed too, which "
                    f"never happens alongside {finding.referenced!r}, so "
                    f"this job can never run. Narrow `needs:` to the "
                    f"job(s) the `if:` actually checks, or add `always()` "
                    f"or `!cancelled()` to the condition. "
                    f"(condition: {finding.condition!r})"
                    for finding in UNREACHABLE_JOBS
                ),
            ]
        )
