"""No scheduled workflow may target the protected ``production`` Environment.

A GitHub Environment does two unrelated jobs: it scopes secrets, and it gates
deployments. ``production`` carries a required-reviewer protection rule, which
is correct for ``supabase-production.yml`` (it applies migrations to the live
database on push, and a human is present for a push) and fatal for anything
that runs on a ``schedule:``. An unattended scheduled run that enters that
environment parks in ``waiting`` for an approver who is not watching, and the
outcome is then decided by the workflow's ``concurrency:`` block rather than by
its steps: with ``cancel-in-progress: true`` the next cron cancels it, with
``cancel-in-progress: false`` it holds the in-progress slot and starves every
run behind it. Either way the schedule executes nothing, and nothing turns red.

This trap has now been walked into three separate times in this repository:

* ``e2e-prod.yml``, from 2026-07-18: fixed by the dedicated ``production-e2e``
  environment, with a ``#CRITICAL: timing`` note on the job's ``environment:``
  key that documents the mechanism in full.
* ``supabase-backup.yml``, before 2026-08-11: fixed by the dedicated ``backups``
  environment, with the same reasoning in its header.
* ``notification-digest.yml`` (26 runs, zero executions since 2026-08-09) and
  ``moderation-report-health.yml`` (run 33364655103 still ``waiting``): fixed
  alongside this test by the dedicated ``production-ops`` environment.

The first two fixes each left a careful comment explaining the trap, and the
third occurrence shipped anyway, because a comment in one file cannot fail a
review of a different file. This test is the check those comments were standing
in for: it walks every workflow in ``.github/workflows/`` that declares a
``schedule:`` trigger and fails if any job in it names ``production`` as its
environment, in either the string form (``environment: production``) or the
mapping form (``environment: {name: production}``).

Scope, stated plainly so the rule is not read as broader than it is:

* Only the literal ``production`` name is protected. A second environment
  acquiring a required-reviewer rule would not be caught here; if that happens,
  add it to ``PROTECTED_ENVIRONMENTS`` and the fleet is re-checked.
* An environment reached through an expression (``${{ matrix.environment }}``
  in ``kws-delivery-health.yml``) is not resolved. A matrix leg naming
  ``production`` would therefore be a known false negative, not a pass.
* ``workflow_dispatch``-only workflows are out of scope on purpose: a manual
  run has a human present to approve it, which is exactly the situation the
  protection rule was designed for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from ruamel.yaml import YAML

# A parsed workflow. The key type admits `bool` because a YAML 1.1 loader reads
# the bare `on:` key as the boolean True rather than the string "on"; ruamel's
# safe loader (YAML 1.2) keeps it a string, and `_triggers` accepts either.
WorkflowMapping = dict[str | bool, Any]

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# The one environment in this repository that carries a required-reviewer
# protection rule. `supabase-production.yml` relies on that rule and must keep
# it; every other consumer of production credentials needs its own unprotected
# environment (`production-e2e`, `production-ops`, `backups`).
#
# #CRITICAL: timing: this test encodes the FACT that `production` is protected,
# which lives in GitHub repository settings and not in any file this test can
# read. If the owner ever removes the rule, this check becomes stricter than
# necessary (a false positive, visible and cheap); if the owner adds the rule to
# another environment, this check becomes silent on it (a false negative, the
# expensive direction).
# #VERIFY: `gh api repos/:owner/:repo/environments --jq
# '.environments[] | {name, rules: [.protection_rules[].type]}'` lists exactly
# the environments in this set as carrying `required_reviewers`; extend the
# set if it lists more.
PROTECTED_ENVIRONMENTS = frozenset({"production"})

E2E_PROD_NOTE = (
    "the `#CRITICAL: timing` note on the `environment:` key of "
    ".github/workflows/e2e-prod.yml"
)


class ProtectedScheduledJob(NamedTuple):
    """One scheduled job that targets a protected environment."""

    workflow: str
    job_id: str
    environment: str

    @property
    def where(self) -> str:
        """Human-readable location.

        Returns:
            ``workflow.yml::job-id``.
        """
        return f"{self.workflow}::{self.job_id}"


def _parse(source: str) -> WorkflowMapping:
    """Parse workflow YAML from a string.

    Split out from :func:`_load` so the fixture-based controls below reach
    the rule through the same parser the fleet scan uses.

    Args:
        source: Workflow YAML text.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    # ruamel, not PyYAML: ruamel is the declared dependency the sibling
    # workflow contract tests use; PyYAML reaches this environment only
    # transitively. ruamel's safe loader speaks YAML 1.2, where `on` is a
    # plain string, so `_triggers` finds it under "on" here and under True
    # only if a 1.1 loader is ever substituted.
    loaded: Any = YAML(typ="safe").load(source)
    return loaded if isinstance(loaded, dict) else {}


def _load(path: Path) -> WorkflowMapping:
    """Parse a workflow file.

    Args:
        path: Workflow to read.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    return _parse(path.read_text(encoding="utf-8"))


def _triggers(workflow: WorkflowMapping) -> frozenset[str]:
    """Extract a workflow's trigger names.

    ``on:`` is parsed as the boolean ``True`` by YAML 1.1 loaders (PyYAML
    included), so both keys have to be tried. Reading only ``"on"`` yields an
    empty set for every file, which would make the schedule filter below
    exclude the whole fleet and the main assertion pass vacuously.

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


def _environment_name(job: dict[str, Any]) -> str | None:
    """Read the environment a job declares, in either GitHub-accepted form.

    GitHub accepts ``environment: <name>`` and ``environment: {name: <name>,
    url: ...}``; the mapping form is how a job attaches a deployment URL, and
    a check that only read the string form would be bypassed by adding one.

    Args:
        job: Parsed job mapping.

    Returns:
        The declared environment name, or ``None`` when the job declares no
        environment or declares it in a shape this cannot read statically.
    """
    declared: Any = job.get("environment")
    if isinstance(declared, str):
        return declared
    if isinstance(declared, dict):
        name: Any = declared.get("name")
        return str(name) if name is not None else None
    return None


def _scan_workflow(
    workflow_name: str, workflow: WorkflowMapping
) -> list[ProtectedScheduledJob]:
    """Apply the rule to every job in one parsed workflow.

    Args:
        workflow_name: File name to attribute findings to.
        workflow: The parsed workflow mapping.

    Returns:
        Every job in a scheduled workflow that names a protected environment;
        empty for a workflow with no ``schedule:`` trigger.
    """
    if "schedule" not in _triggers(workflow):
        return []

    jobs: Any = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        return []

    findings: list[ProtectedScheduledJob] = []
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        environment = _environment_name(job)
        if environment in PROTECTED_ENVIRONMENTS:
            findings.append(
                ProtectedScheduledJob(
                    workflow=workflow_name,
                    job_id=str(job_id),
                    environment=environment,
                )
            )
    return findings


def _find_protected_scheduled_jobs() -> list[ProtectedScheduledJob]:
    """Walk every workflow and apply the rule.

    Returns:
        Every finding, across all workflows, in file order.
    """
    findings: list[ProtectedScheduledJob] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        findings.extend(_scan_workflow(path.name, _load(path)))
    return findings


# ---------------------------------------------------------------------------
# Fixture-based controls for the rule itself.
#
# The fleet assertion's passing state is an empty list, which is also what a
# rule that matches nothing produces. These fixtures give the rule a workflow it
# MUST flag and several it must NOT, so it is observed working rather than
# assumed to. Rendered here and parsed with the production `_parse`; no broken
# job is ever added to a real workflow.
# ---------------------------------------------------------------------------

_FIXTURE_TEMPLATE = """\
name: fixture
on:
{triggers}
jobs:
  work:
    runs-on: ubuntu-latest
{environment}    steps:
      - run: echo work
"""

_SCHEDULED = '  schedule:\n    - cron: "0 9 * * *"\n  workflow_dispatch: {}\n'
_MANUAL_ONLY = "  workflow_dispatch: {}\n"
_PUSH_ONLY = "  push:\n    branches: [main]\n"


def _scan_fixture(*, triggers: str, environment: str) -> list[ProtectedScheduledJob]:
    """Render a synthetic one-job workflow and run the real rule over it.

    Args:
        triggers: The ``on:`` block body, as indented YAML lines.
        environment: The job's ``environment:`` lines, indented four spaces,
            or an empty string for a job that declares none.

    Returns:
        Whatever :func:`_scan_workflow` finds in the rendered workflow.
    """
    source = _FIXTURE_TEMPLATE.format(triggers=triggers, environment=environment)
    return _scan_workflow("fixture.yml", _parse(source))


class TestTheRuleDetectsTheDefectItClaimsTo:
    """Positive and negative controls, so the fleet assertion means something."""

    def test_the_string_form_is_detected(self) -> None:
        """The exact pre-fix shape of both retargeted workflows must be flagged."""
        findings = _scan_fixture(
            triggers=_SCHEDULED, environment="    environment: production\n"
        )
        assert [(f.where, f.environment) for f in findings] == [
            ("fixture.yml::work", "production")
        ]

    def test_the_mapping_form_is_detected(self) -> None:
        """``environment: {name: production, url: ...}`` is the same defect.

        Adding a deployment URL is the usual reason to switch to the mapping
        form, and a check that read only the string form would go quiet on it.
        """
        findings = _scan_fixture(
            triggers=_SCHEDULED,
            environment=(
                "    environment:\n"
                "      name: production\n"
                "      url: https://example.invalid\n"
            ),
        )
        assert [f.where for f in findings] == ["fixture.yml::work"]

    def test_an_unprotected_environment_clears_the_finding(self) -> None:
        """The real fix, applied to the fixture, must silence the rule."""
        assert (
            _scan_fixture(
                triggers=_SCHEDULED, environment="    environment: production-ops\n"
            )
            == []
        )

    def test_a_job_with_no_environment_is_not_flagged(self) -> None:
        """Most scheduled workflows declare no environment at all."""
        assert _scan_fixture(triggers=_SCHEDULED, environment="") == []

    def test_a_manual_only_workflow_may_target_production(self) -> None:
        """A human is present for a ``workflow_dispatch`` run to approve it."""
        assert (
            _scan_fixture(
                triggers=_MANUAL_ONLY, environment="    environment: production\n"
            )
            == []
        )

    def test_a_push_workflow_may_target_production(self) -> None:
        """The ``supabase-production.yml`` shape: the protection rule is wanted."""
        assert (
            _scan_fixture(
                triggers=_PUSH_ONLY, environment="    environment: production\n"
            )
            == []
        )


PROTECTED_SCHEDULED_JOBS: list[ProtectedScheduledJob] = _find_protected_scheduled_jobs()


class TestTheRuleParsesTheFleet:
    """Guards the assertion below against a silently empty parse."""

    def test_scheduled_workflows_are_found(self) -> None:
        """A zero-hit trigger parse would exclude the whole fleet from the rule.

        The floor is deliberately below the current count so retiring a cron
        does not fail this test, and above zero so a drifted ``on:`` key
        lookup or a moved directory does.
        """
        scheduled = [
            path.name
            for path in sorted(WORKFLOWS_DIR.glob("*.yml"))
            if "schedule" in _triggers(_load(path))
        ]
        assert len(scheduled) >= 5, (
            f"found only {len(scheduled)} scheduled workflow(s) ({scheduled}); "
            f"the `on:` lookup or the glob pattern has drifted"
        )

    def test_the_protected_environment_is_seen_where_it_belongs(self) -> None:
        """``supabase-production.yml`` must read as targeting ``production``.

        That workflow is the one legitimate consumer of the protected
        environment, and it runs on push, not on a schedule. If this parser
        cannot see its ``environment:`` key, the main assertion below is
        passing because the rule reads nothing, not because the fleet is
        clean.
        """
        workflow = _load(WORKFLOWS_DIR / "supabase-production.yml")
        jobs: Any = workflow.get("jobs") or {}
        environments = {
            _environment_name(job) for job in jobs.values() if isinstance(job, dict)
        }
        assert "production" in environments
        assert "schedule" not in _triggers(workflow)


class TestNoScheduledWorkflowTargetsAProtectedEnvironment:
    """A scheduled run that waits for a reviewer never runs, and never fails."""

    def test_no_scheduled_job_declares_the_production_environment(self) -> None:
        """Reproduces the notification-digest / moderation-report-health defect.

        Pre-fix, both workflows declared ``environment: production`` on their
        main job. Reverting either to that value is the exact mutation this
        test exists to catch; the fix (``environment: production-ops``, an
        environment with no protection rules) makes it pass again.
        """
        assert PROTECTED_SCHEDULED_JOBS == [], "\n".join(
            [
                "scheduled job(s) targeting a protected GitHub Environment:",
                *(
                    f"  {finding.where}: declares `environment: "
                    f"{finding.environment}` in a workflow with a `schedule:` "
                    f"trigger. That environment carries a required-reviewer "
                    f"protection rule, so an unattended scheduled run parks in "
                    f"`waiting` for an approver who is not watching, and the "
                    f"workflow's `concurrency:` block then either cancels it "
                    f"(cancel-in-progress: true) or lets it starve every later "
                    f"run (cancel-in-progress: false). Nothing executes and "
                    f"nothing turns red. Retarget the job to a dedicated "
                    f"UNPROTECTED environment that holds only the secrets this "
                    f"job reads (`production-ops` for the app DSN, "
                    f"`production-e2e` for the e2e test account, `backups` for "
                    f"the dump credentials), then cancel any run already left "
                    f"in `waiting` by hand. Mechanism and history: "
                    f"{E2E_PROD_NOTE}."
                    for finding in PROTECTED_SCHEDULED_JOBS
                ),
            ]
        )
