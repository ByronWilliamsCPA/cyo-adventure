# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Contract tests for ``release.yml``'s ``propose`` job.

The "Open release PR" step is the one place in this repo that mutates release
state, and none of it is reachable from a pull request: its job runs on a daily
schedule, so a defect here is invisible until a release silently does not
happen. Two such defects are pinned:

* **Unretried API mutations (#757).** The branch lookup was retried; the
  ``PATCH``/``POST`` that follow it, and every ``gh pr`` call after them, ran
  bare under ``set -e``. One transient 5xx aborted the run at that point. This
  is the same failure mode that deadlocked the pipeline for a week (#752), one
  job over.
* **Orphaned release PRs (#755).** ``propose`` reuses a release PR only when
  the branch name matches exactly, and the branch name carries the computed
  version. A PR that never merged leaves no tag, so the next day recomputes
  from the same base and gets a DIFFERENT version the moment the highest-
  ranking commit type in the window changes. The lookup then misses, a second
  PR opens, and the first sits orphaned with auto-merge still armed, able to
  apply a lower version bump out of order.

These are static assertions about the step's shell source. The step cannot be
executed here (it needs a GitHub API), so what is pinned is the SHAPE that
makes the failure impossible, not the behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
STEP_NAME = "Open release PR"


def _logical_lines(script: str) -> list[str]:
    """Join backslash-continued lines so a call is one string, not four.

    Every `gh` invocation in this step spans several physical lines, so a
    per-physical-line check would see `gh api -X PATCH \\` on its own and miss
    the `retry_api` that introduces it on the line before.
    """
    return re.sub(r"\\\n\s*", " ", script).splitlines()


def _open_release_pr_script() -> str:
    """Return the ``run:`` body of the propose job's "Open release PR" step."""
    yaml = YAML(typ="safe")
    workflow: Any = yaml.load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    steps: Any = workflow["jobs"]["propose"]["steps"]
    step = next(s for s in steps if s.get("name") == STEP_NAME)
    return str(step["run"])


@pytest.fixture(scope="module")
def script() -> str:
    """The step's shell source, parsed once."""
    return _open_release_pr_script()


class TestEveryApiCallIsRetried:
    """#757: a transient 5xx must not abort the release."""

    def test_the_step_defines_a_retry_helper(self, script: str) -> None:
        """The helper is what the assertions below are written against."""
        assert "retry_api()" in script, (
            "the 'Open release PR' step no longer defines retry_api, so the "
            "gh calls below are unprotected again (#757)"
        )
        assert "MAX_ATTEMPTS" in script
        assert "sleep 2" in script

    @pytest.mark.parametrize(
        ("mutation", "why"),
        [
            (
                "-X PATCH",
                "resetting an existing release branch to the new base commit",
            ),
            ("-X POST", "creating the release branch when it does not exist yet"),
        ],
    )
    def test_the_git_ref_mutations_are_retried(
        self, script: str, mutation: str, why: str
    ) -> None:
        """The two ref mutations are the specific gap #757 reported.

        The lookup that precedes them was already careful: it distinguished a
        genuine 404 from a transient failure and re-entered the retry loop for
        the latter. The mutations inherited none of that.
        """
        calls = [
            line
            for line in _logical_lines(script)
            if mutation in line and not line.lstrip().startswith("#")
        ]

        assert calls, f"the step no longer contains a `gh api {mutation}` call"
        for call in calls:
            assert "retry_api" in call, (
                f"`gh api {mutation}` ({why}) is not routed through retry_api, "
                f"so a transient 5xx aborts the release run (#757): "
                f"{call.strip()}"
            )

    def test_no_gh_call_runs_bare(self, script: str) -> None:
        """A bare ``gh`` under ``set -e`` is the defect this closes.

        Two calls are legitimately not wrapped in ``retry_api`` and are
        exempted by name here rather than by a loose pattern: ``gh api
        graphql`` has the surrounding ``expectedHeadOid`` loop, and ``gh pr
        create`` must NOT be blindly retried, because a create whose response
        was lost has still created the PR and a retry would open the duplicate
        that #755 exists to prevent.
        """
        exempt = ("gh api graphql", "gh pr create")
        offenders = [
            line.strip()
            for line in _logical_lines(script)
            if re.search(r"(?<!_)\bgh (api|pr) ", line)
            and not line.lstrip().startswith("#")
            and not any(allowed in line for allowed in exempt)
            and "retry_api" not in line
            # The lookup keeps its own bespoke set +e / status-check, because
            # it must tell a genuine 404 from a transient error.
            and "git/ref/heads/" not in line
        ]

        assert not offenders, (
            "these gh invocations are neither retried nor exempt, so a "
            f"transient failure aborts the release (#757): {offenders}"
        )

    def test_the_unretried_calls_explain_themselves(self, script: str) -> None:
        """An exemption that is not argued for is indistinguishable from a miss."""
        assert "NOT wrapped in retry_api" in script, (
            "`gh pr create` is exempt from the retry but the step no longer "
            "says why; the next reader cannot tell the exemption from an "
            "oversight"
        )


class TestSupersededReleasePrsAreClosed:
    """#755: only the newest computed version is ever correct."""

    def test_the_step_closes_other_open_release_prs(self, script: str) -> None:
        """Without this, a stale armed PR can merge a lower version later."""
        assert "gh pr close" in script, (
            "the 'Open release PR' step no longer closes superseded release "
            "PRs, so a recomputed version orphans yesterday's PR with "
            "auto-merge still armed (#755)"
        )
        assert 'startswith("release/")' in script, (
            "the cleanup no longer selects release branches by prefix, so a "
            "PR whose version differs from today's is invisible to it (#755)"
        )

    def test_the_cleanup_never_closes_todays_own_pr(self, script: str) -> None:
        """The one release PR that must survive is the one being opened."""
        assert '[ "${STALE_BRANCH}" != "${BRANCH}" ] || continue' in script, (
            "the cleanup no longer skips ${BRANCH}, so it would close the "
            "release PR this very run is about to reuse"
        )

    def test_auto_merge_is_disabled_before_the_close(self, script: str) -> None:
        """Ordering is the whole safety property.

        Closing first and disabling second leaves an armed PR behind whenever
        the second call fails, which is the exact state #755 describes.
        """
        disable_at = script.index("--disable-auto")
        close_at = script.index("gh pr close")

        assert disable_at < close_at, (
            "auto-merge is disabled AFTER the close; if the close fails, an "
            "armed superseded PR is what is left behind (#755)"
        )

    def test_a_failed_close_is_a_hard_error(self, script: str) -> None:
        """A swallowed close leaves the out-of-order merge possible."""
        cleanup = script[script.index("gh pr close") :]
        tail = cleanup[: cleanup.index("done <<<")]

        why = (
            "a failed `gh pr close` no longer fails the step, so the "
            "superseded PR survives with auto-merge state intact (#755)"
        )

        assert "::error::" in tail, why
        assert "exit 1" in tail, why

    def test_the_cleanup_precedes_the_clean_tree_early_exit(self, script: str) -> None:
        """A re-run that finds the bump applied still needs the stale PR gone.

        The early exit returns before everything after it, so cleanup placed
        below it would not run on exactly the re-run path where yesterday's
        orphan is most likely to still be open.
        """
        cleanup_at = script.index("gh pr close")
        early_exit_at = script.index("No release changes to commit")

        assert cleanup_at < early_exit_at, (
            "the superseded-PR cleanup sits after the clean-tree early exit, "
            "so an idempotent re-run skips it (#755)"
        )
