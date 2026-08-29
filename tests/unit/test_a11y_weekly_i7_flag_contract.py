"""Contract test for I7's `A11Y_EXTENDED` gate (task B3b review, Important 2b).

`frontend/e2e-usersim/walk-a11y.spec.ts:51` skips every test unless
``A11Y_EXTENDED=1`` is set in the environment (see that file's own
``test.skip`` call). That flag is set exactly one place in the fleet: the
``Accessibility scan (usersim I7, axe on newly-reached states)`` step in
``.github/workflows/accessibility-compliance-weekly.yml``. Drop that one
``env:`` block (an easy YAML edit to get wrong, since the sibling step above
it sets the SAME variable for a DIFFERENT Playwright invocation) and the step
still runs, still exits 0, and still reports nothing: Playwright's own JSON
reporter marks a skipped test ``ok: true``, so
``scripts/extract-failing-specs.mjs`` reads a clean report and the weekly
alert never fires. Reviewer proof for exactly this failure mode: running
``npx playwright test --project=usersim-a11y`` with no flag set produces
``3 skipped, EXIT=0``.

This test judges the PROPERTY (does the step that runs the `usersim-a11y`
project set the flag), not a text grep for the literal `A11Y_EXTENDED: '1'`
somewhere in the file: a grep would still pass if the line moved to the
wrong step, or if a second `usersim-a11y` invocation were added elsewhere
without it. The step is located by what it actually runs (`--project=usersim-a11y`
in its `run:` command), matching this repo's other workflow-property tests
(see `test_ci_failure_action_contract.py`, `test_workflow_job_needs_reachability.py`)
rather than by step name, which is free text a rename would silently drift
away from this test's assumptions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "accessibility-compliance-weekly.yml"
)
JOB_ID = "accessibility-compliance"
PROJECT_MARKER = "--project=usersim-a11y"

# The literal `test:e2e:usersim:a11y` npm script (frontend/package.json) has
# the identical vacuous-pass shape as the workflow step above: it runs the
# `usersim-a11y` project with no `A11Y_EXTENDED` set, so `npm run
# test:e2e:usersim:a11y` has always printed "3 skipped" and exited 0,
# regardless of what I7 would have found. A script whose name promises an
# accessibility check but never runs one is worth gating here too.
PACKAGE_JSON_PATH = REPO_ROOT / "frontend" / "package.json"
PACKAGE_JSON_SCRIPT_NAME = "test:e2e:usersim:a11y"


def _load_workflow(path: Path) -> dict[str, Any]:
    """Parse a GitHub Actions workflow file.

    Args:
        path: Workflow YAML file to read.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    yaml = YAML(typ="safe")
    with path.open(encoding="utf-8") as handle:
        loaded: Any = yaml.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _steps_running_usersim_a11y() -> list[dict[str, Any]]:
    """Find every step in the weekly job whose `run:` invokes the I7 project.

    Matched by the actual `--project=usersim-a11y` CLI argument, not by step
    name: a step's `name:` is free text a future rename would silently drift
    away from, while the project flag is the one thing that structurally ties
    a step to walk-a11y.spec.ts's `test.skip` requirement.

    Returns:
        Every matching step's mapping. Normally exactly one; asserted below.
    """
    workflow = _load_workflow(WORKFLOW_PATH)
    jobs: Any = workflow.get("jobs") or {}
    job: Any = jobs.get(JOB_ID) if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        return []
    steps: Any = job.get("steps") or []
    if not isinstance(steps, list):
        return []
    matches: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        run_command = str(step.get("run", ""))
        if PROJECT_MARKER in run_command:
            matches.append(step)
    return matches


class TestTheWeeklyWorkflowStepSetsTheFlag:
    """The I7 Playwright invocation must set `A11Y_EXTENDED=1`."""

    def test_exactly_one_step_runs_the_usersim_a11y_project(self) -> None:
        """A count of zero would make every assertion below vacuously pass.

        Guards against the step being renamed, removed, or split in a way
        that changes which step this test is even inspecting.
        """
        steps = _steps_running_usersim_a11y()
        assert len(steps) == 1, (
            f"expected exactly one step running `{PROJECT_MARKER}` in "
            f"{WORKFLOW_PATH.relative_to(REPO_ROOT)}'s `{JOB_ID}` job, found "
            f"{len(steps)}. If this workflow now runs the usersim-a11y "
            "project from more than one step, update this test to check "
            "each of them."
        )

    def test_the_step_sets_a11y_extended_to_the_exact_string_1(self) -> None:
        """Assert the exact string `'1'`, not mere presence of the key.

        Both `walk-a11y.spec.ts`'s `test.skip` and `axeTags.ts`'s `AXE_TAGS`
        compare against the exact string `'1'` (`process.env.A11Y_EXTENDED
        !== '1'` / `=== '1'`), not any truthy value.
        """
        (step,) = _steps_running_usersim_a11y()
        env: Any = step.get("env") or {}
        assert isinstance(env, dict), (
            f"the step running `{PROJECT_MARKER}` has no `env:` mapping at all, "
            "so A11Y_EXTENDED is unset and every test in walk-a11y.spec.ts "
            "will be skipped (exit 0, nothing reported)."
        )
        assert env.get("A11Y_EXTENDED") == "1", (
            f"the step running `{PROJECT_MARKER}` in {WORKFLOW_PATH.name}'s `{JOB_ID}` job must set "
            "`A11Y_EXTENDED: '1'` in its `env:` block, or "
            "walk-a11y.spec.ts's `test.skip` (task B3b) silently skips all "
            "three personas: `npx playwright test --project=usersim-a11y` "
            "with no flag set is `3 skipped, EXIT=0`, which the JSON "
            "reporter marks `ok: true`, so the weekly alert never fires. "
            f"Found env: {env!r}"
        )


class TestThePackageJsonScriptSetsTheFlagToo:
    """`npm run test:e2e:usersim:a11y` must not be permanently vacuous."""

    def test_the_script_sets_a11y_extended(self) -> None:
        """The script string must both target the I7 project and set the flag.

        A script that runs `--project=usersim-a11y` without setting
        `A11Y_EXTENDED=1` always prints `3 skipped` and exits 0, regardless
        of what I7 would have found, the identical defect shape as the
        workflow step above.
        """
        import json

        package = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
        scripts: dict[str, str] = package.get("scripts", {})
        assert PACKAGE_JSON_SCRIPT_NAME in scripts, (
            f"expected an npm script named {PACKAGE_JSON_SCRIPT_NAME!r} in "
            f"{PACKAGE_JSON_PATH.relative_to(REPO_ROOT)}"
        )
        script = scripts[PACKAGE_JSON_SCRIPT_NAME]
        assert PROJECT_MARKER in script, (
            f"{PACKAGE_JSON_SCRIPT_NAME!r} no longer runs "
            f"`{PROJECT_MARKER}`; update PROJECT_MARKER or this script."
        )
        assert "A11Y_EXTENDED=1" in script, (
            f"npm script {PACKAGE_JSON_SCRIPT_NAME!r} ({script!r}) runs the "
            "usersim-a11y project without setting A11Y_EXTENDED=1, so "
            f"`npm run {PACKAGE_JSON_SCRIPT_NAME}` always prints '3 skipped' "
            "and exits 0 regardless of what I7 would have found."
        )
