"""Contract test for per-project Playwright `outputDir` isolation.

Task B3b second review, F2. Playwright deletes a project's entire configured
`outputDir` at the START of every invocation that includes that project,
unconditionally (`frontend/playwright.config.ts`'s own header comment on
`JSON_REPORT_PATH` explains this in full). A job that invokes
`frontend/playwright.config.ts` more than once in sequence (separate
workflow steps, not a single `dependencies: [...]` chain) is therefore at
risk of a later step silently wiping an earlier step's failure evidence,
UNLESS every project actually invoked as its own step in that job resolves
to a distinct `outputDir` that does not nest inside another's.

`chromium` had no `outputDir` (Playwright's bare default, `test-results/`)
until this fix: since every other isolated project's dir
(`test-results/usersim-a11y`, etc.) is a subdirectory of that bare default,
`chromium` running was really "clear the parent of everything else's
evidence", and the only thing standing between that and a real defect was a
comment asserting `chromium` always runs first in
`accessibility-compliance-weekly.yml`'s job. That invariant lived only in
prose; this test makes it a property of the config plus the workflow files
that actually invoke it, instead.

Judged against the ACTUAL steps each relevant job runs (parsed from the
workflow YAML, resolving an `npm run <script>` step back to the Playwright
project it invokes via `frontend/package.json`'s own script text), not
against a hardcoded guess of which projects "should" collide: a project
added to `playwright.config.ts` without ever being wired into one of these
jobs is correctly invisible to this check, and a workflow step added later
that reuses an existing project is correctly picked up without this file
needing an update.

That dynamism is scoped to the steps INSIDE a job already named below,
though: which jobs get inspected at all is the hardcoded
`MULTI_INVOCATION_JOBS` list, not something derived from the workflow tree.
A third job that started invoking this shared config more than once would be
invisible to every check above until that list is updated by hand.
`test_multi_invocation_jobs_list_is_complete` closes that gap: it re-derives
the full set of multi-invocation jobs from every workflow file under
`.github/workflows/` and fails the moment the hardcoded list falls behind it.

`real-backend-setup` is deliberately never a member of any job's step list
here even though `real-backend`/`real-backend-pipeline`/`usersim-real` all
declare it as a `dependencies: [...]` target: Playwright always runs a
dependency INSIDE its dependent's own single invocation, never as a separate
workflow step of its own, so it never gets the chance to wipe a sibling's
evidence the way a separately-invoked project could (task B3b second review
confirmed this directly: it is the one project left on the bare default
`outputDir` and is not itself at risk). Building each job's project list
from the workflows' `run:` commands, rather than from `playwright.config.ts`
alone, is what keeps a dependency-only project out of this check without an
explicit allowlist.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
CONFIG_PATH = FRONTEND_DIR / "playwright.config.ts"
PACKAGE_JSON_PATH = FRONTEND_DIR / "package.json"

# Playwright's own default `outputDir` for a project that declares none.
DEFAULT_OUTPUT_DIR = "test-results"

# (workflow file relative to repo root, job id). Both are named directly in
# playwright.config.ts's own header comment as the jobs that invoke this
# shared config more than once in sequence within one job. This list is
# hardcoded, not derived: test_multi_invocation_jobs_list_is_complete below
# is what keeps it honest, by failing if a workflow file gains a third job
# that qualifies.
MULTI_INVOCATION_JOBS: list[tuple[str, str]] = [
    (
        ".github/workflows/accessibility-compliance-weekly.yml",
        "accessibility-compliance",
    ),
    (".github/workflows/e2e-real-nightly.yml", "e2e-real"),
]

PROJECT_FLAG_RE = re.compile(r"--project[= ](\S+)")


def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a plain mapping.

    Args:
        path: File to read.

    Returns:
        The parsed mapping, or an empty mapping for an unparseable file.
    """
    yaml = YAML(typ="safe")
    with path.open(encoding="utf-8") as handle:
        loaded: Any = yaml.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _split_top_level_objects(body: str) -> list[str]:
    """Split a TS array body into its top-level `{ ... }` object entries.

    Splits by brace depth so a project's own nested objects/arrays (`use: {
    ...devices[...] }`, `dependencies: [...]`) cannot be mistaken for entry
    boundaries.

    Args:
        body: The text strictly between an array's outer `[` and `]`.

    Returns:
        One string per top-level `{ ... }` entry, braces included.
    """
    entries: list[str] = []
    depth = 0
    start: int | None = None
    for i, char in enumerate(body):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                entries.append(body[start : i + 1])
                start = None
    return entries


def _parse_playwright_projects() -> dict[str, str]:
    """Parse `playwright.config.ts`'s `projects` array.

    Returns:
        Mapping of project name to its effective `outputDir`: the declared
        value, or Playwright's own default when a project declares none.
    """
    text = CONFIG_PATH.read_text(encoding="utf-8")
    marker = "projects: ["
    marker_index = text.index(marker)
    array_start = marker_index + len(marker) - 1  # index of the '['
    depth = 0
    array_end: int | None = None
    for i in range(array_start, len(text)):
        char = text[i]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_end = i
                break
    assert array_end is not None, (
        "could not find the closing bracket of playwright.config.ts's "
        "`projects` array; the parser above needs updating to match a "
        "structural change to that file"
    )
    body = text[array_start + 1 : array_end]

    projects: dict[str, str] = {}
    for entry in _split_top_level_objects(body):
        name_match = re.search(r"name:\s*'([^']+)'", entry)
        if name_match is None:
            continue
        output_match = re.search(r"outputDir:\s*'([^']+)'", entry)
        projects[name_match.group(1)] = (
            output_match.group(1) if output_match is not None else DEFAULT_OUTPUT_DIR
        )
    return projects


def _parse_npm_scripts() -> dict[str, str]:
    """Read `frontend/package.json`'s `scripts` mapping.

    Returns:
        The scripts mapping (script name to its shell command string).
    """
    import json

    data = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    scripts = data.get("scripts")
    return scripts if isinstance(scripts, dict) else {}


def _project_for_run_command(
    run_command: str, npm_scripts: dict[str, str]
) -> str | None:
    """Resolve a workflow step's `run:` command to the Playwright project it invokes.

    Handles both a direct `npx playwright test --project=X` invocation and an
    `npm run <script>` indirection, resolved through `frontend/package.json`'s
    own script text (e.g. `test:e2e:real` -> `playwright test
    --project=real-backend --workers=1`).

    Args:
        run_command: The step's `run:` field.
        npm_scripts: `frontend/package.json`'s `scripts` mapping.

    Returns:
        The project name, or ``None`` if this command does not invoke
        Playwright at all (most steps in these jobs do not).
    """
    direct = PROJECT_FLAG_RE.search(run_command)
    if direct is not None:
        return direct.group(1)

    npm_run_match = re.search(r"npm run ([\w:.-]+)", run_command)
    if npm_run_match is not None:
        script = npm_scripts.get(npm_run_match.group(1), "")
        script_match = PROJECT_FLAG_RE.search(script)
        if script_match is not None:
            return script_match.group(1)
    return None


def _ordered_projects_for_job(
    workflow_path: Path, job_id: str, npm_scripts: dict[str, str]
) -> list[tuple[str, str]]:
    """List the Playwright projects a job invokes, in step order.

    Args:
        workflow_path: The workflow file to read.
        job_id: The job within it to inspect.
        npm_scripts: `frontend/package.json`'s `scripts` mapping, for
            resolving `npm run` indirection.

    Returns:
        `(step_name, project_name)` pairs, in the order the steps appear.
    """
    workflow = _load_yaml(workflow_path)
    jobs: Any = workflow.get("jobs") or {}
    job: Any = jobs.get(job_id) if isinstance(jobs, dict) else None
    assert isinstance(job, dict), f"job `{job_id}` not found in {workflow_path}"
    steps: Any = job.get("steps") or []
    assert isinstance(steps, list), (
        f"job `{job_id}` in {workflow_path} has no steps list"
    )

    ordered: list[tuple[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        run_command = step.get("run")
        if not isinstance(run_command, str):
            continue
        project = _project_for_run_command(run_command, npm_scripts)
        if project is not None:
            ordered.append((step.get("name", "<unnamed step>"), project))
    return ordered


def _discover_multi_invocation_jobs(
    npm_scripts: dict[str, str],
) -> set[tuple[str, str]]:
    """Re-derive every job that invokes this shared config more than once.

    Independent of `MULTI_INVOCATION_JOBS`: this walks every workflow file
    under `.github/workflows/` and every job inside it, so the hardcoded list
    can be checked against an actual count instead of trusted on its own.

    Args:
        npm_scripts: `frontend/package.json`'s `scripts` mapping, for
            resolving `npm run` indirection.

    Returns:
        set[tuple[str, str]]: `(workflow relative path, job id)` pairs whose
        step list invokes two or more distinct Playwright project steps.
    """
    discovered: set[tuple[str, str]] = set()
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    for workflow_path in sorted(workflows_dir.glob("*.yml")):
        workflow = _load_yaml(workflow_path)
        jobs: Any = workflow.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job_id in jobs:
            ordered = _ordered_projects_for_job(workflow_path, job_id, npm_scripts)
            if len(ordered) >= 2:
                rel_path = str(workflow_path.relative_to(REPO_ROOT))
                discovered.add((rel_path, job_id))
    return discovered


def _dirs_collide(dir_a: str, dir_b: str) -> bool:
    """Whether two `outputDir` values are identical or one nests inside the other.

    Args:
        dir_a: First effective `outputDir`, forward-slash-separated.
        dir_b: Second effective `outputDir`.

    Returns:
        True if clearing one at the start of an invocation could delete
        anything the other has written.
    """
    if dir_a == dir_b:
        return True
    return dir_a.startswith(dir_b + "/") or dir_b.startswith(dir_a + "/")


class TestPlaywrightOutputDirIsolation:
    """Every project a multi-invocation job runs as its own step must have a non-colliding `outputDir`."""

    def test_config_declares_at_least_the_expected_isolated_projects(self) -> None:
        """Sanity check the parser itself before trusting it below."""
        projects = _parse_playwright_projects()
        for expected in (
            "chromium",
            "real-backend",
            "real-backend-pipeline",
            "usersim-real",
            "usersim-a11y",
            "real-backend-setup",
        ):
            assert expected in projects, (
                f"expected project `{expected}` not found by the parser; "
                "either playwright.config.ts changed structurally or the "
                "parser in this test needs updating"
            )
        # real-backend-setup is the one project this suite expects to keep
        # sharing the bare default: see this module's own docstring for why
        # that is safe (a dependency, never a separately-invoked step).
        assert projects["real-backend-setup"] == DEFAULT_OUTPUT_DIR

    def test_no_project_shares_or_nests_output_dir_within_a_multi_invocation_job(
        self,
    ) -> None:
        """The property this test exists for: no step in a shared job can wipe another's evidence."""
        projects = _parse_playwright_projects()
        npm_scripts = _parse_npm_scripts()

        for workflow_rel_path, job_id in MULTI_INVOCATION_JOBS:
            workflow_path = REPO_ROOT / workflow_rel_path
            ordered = _ordered_projects_for_job(workflow_path, job_id, npm_scripts)
            assert len(ordered) >= 2, (
                f"expected `{job_id}` in {workflow_rel_path} to invoke this "
                f"shared playwright.config.ts at least twice (that is the "
                f"whole point of this job being in MULTI_INVOCATION_JOBS); "
                f"found only {ordered}. Either the job changed shape or the "
                f"run-command parsing above needs updating."
            )

            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    step_a, project_a = ordered[i]
                    step_b, project_b = ordered[j]
                    dir_a = projects.get(project_a)
                    dir_b = projects.get(project_b)
                    assert dir_a is not None, (
                        f"unknown project `{project_a}` (step `{step_a}` in {workflow_rel_path})"
                    )
                    assert dir_b is not None, (
                        f"unknown project `{project_b}` (step `{step_b}` in {workflow_rel_path})"
                    )
                    assert not _dirs_collide(dir_a, dir_b), (
                        f"{workflow_rel_path}::{job_id}: step `{step_a}` (project "
                        f"`{project_a}`, outputDir `{dir_a}`) runs before step "
                        f"`{step_b}` (project `{project_b}`, outputDir `{dir_b}`) "
                        "and their effective outputDir values collide or nest. "
                        "Playwright clears an outputDir wholesale at the start "
                        "of every invocation, so whichever step runs later would "
                        "silently wipe the earlier step's failure evidence "
                        "before any 'upload on failure' step reads it. Give "
                        "each project its own outputDir in playwright.config.ts."
                    )

    def test_multi_invocation_jobs_list_is_complete(self) -> None:
        """`MULTI_INVOCATION_JOBS` is hardcoded; this is what keeps it honest.

        The per-job step parsing above is dynamic (a new step that reuses an
        existing project inside an already-listed job needs no update here),
        but WHICH JOBS get inspected at all is this fixed two-entry list. A
        third job that started invoking `playwright.config.ts` more than once
        would otherwise be invisible to every check in this file. This
        re-derives the full set from every workflow file under
        `.github/workflows/` and fails the moment the hardcoded list falls
        behind it, rather than describing that as automatic without actually
        enforcing it.
        """
        npm_scripts = _parse_npm_scripts()
        discovered = _discover_multi_invocation_jobs(npm_scripts)
        assert discovered == set(MULTI_INVOCATION_JOBS), (
            "a job that invokes playwright.config.ts more than once was "
            "added to or removed from the workflow tree without updating "
            f"MULTI_INVOCATION_JOBS: discovered {discovered}, list declares "
            f"{set(MULTI_INVOCATION_JOBS)}"
        )


class TestDirsCollide:
    """Positive control: `_dirs_collide` must detect what it claims to.

    Without this, mutating `_dirs_collide` to always return `False` leaves
    the whole suite green, since every assertion in
    `TestPlaywrightOutputDirIsolation` above is `assert not _dirs_collide(...)`
    and a predicate that never fires satisfies all of them trivially.
    """

    @pytest.mark.parametrize(
        ("dir_a", "dir_b"),
        [
            ("test-results", "test-results"),
            ("test-results", "test-results/usersim-a11y"),
            ("test-results/usersim-a11y", "test-results"),
            ("a/b/c", "a/b"),
        ],
        ids=["identical", "a-nests-in-b", "b-nests-in-a", "deep-nesting"],
    )
    def test_detects_a_genuine_collision(self, dir_a: str, dir_b: str) -> None:
        """Identical dirs and either direction of nesting must collide."""
        assert _dirs_collide(dir_a, dir_b)

    @pytest.mark.parametrize(
        ("dir_a", "dir_b"),
        [
            ("test-results/usersim-a11y", "test-results/usersim-real"),
            ("test-results", "test-results-other"),
            ("test-results-other", "test-results"),
        ],
        ids=["siblings", "lexical-prefix-not-a-path-segment", "reversed-prefix"],
    )
    def test_returns_false_for_a_genuine_non_collision(
        self, dir_a: str, dir_b: str
    ) -> None:
        """Sibling dirs, and a lexical prefix that isn't a real path segment.

        The last two cases pin the `+ "/"` boundary in `_dirs_collide`: a
        naive `str.startswith` without it would wrongly flag
        `test-results-other` as nested inside `test-results`.
        """
        assert not _dirs_collide(dir_a, dir_b)
