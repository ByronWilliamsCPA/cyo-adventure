# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Contract tests for ``release.yml``'s ``propose`` job.

The "Open release PR" step is the one place in this repo that mutates release
state, and none of it is reachable from a pull request: its job runs on a daily
schedule, so a defect here is invisible until a release silently does not
happen. Four such defects are pinned:

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
* **A forced dispatch closing a correct, higher-version PR (#774).** The
  #755 cleanup assumed "only the newest computed version is ever correct",
  which is false for a ``workflow_dispatch`` run passing ``force_level``:
  python-semantic-release computes a forced bump from the latest TAG, not
  from the accumulated commits, so it can be numerically LOWER than an
  already-open, still-correct release PR. A branch-name-only cleanup would
  close that PR and ship the lower version, silently dropping whatever bump
  the open PR carried.
* **A non-idempotent branch-create POST retried blindly.** ``POST
  .../git/refs`` is not idempotent: a lost response after a successful
  server-side create makes a blind retry come back HTTP 422 "Reference
  already exists" and hard-fail a branch that in fact now exists. Recovery
  has to be the idempotent GET re-lookup, the same discipline ``gh pr
  create`` below is already exempted from ``retry_api`` for.

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

    def test_the_reset_mutation_is_retried(self, script: str) -> None:
        """`-X PATCH` resets an EXISTING branch, so retrying it is always safe.

        Setting a ref to the same sha twice has the same end state either
        time, unlike the `-X POST` create below, which is deliberately NOT
        retried this way (see ``TestTheBranchCreatePostIsNotBlindlyRetried``).
        """
        calls = [
            line
            for line in _logical_lines(script)
            if "-X PATCH" in line and not line.lstrip().startswith("#")
        ]

        assert calls, "the step no longer contains a `gh api -X PATCH` call"
        for call in calls:
            assert "retry_api" in call, (
                "`gh api -X PATCH` (resetting an existing release branch) is "
                "not routed through retry_api, so a transient 5xx aborts the "
                f"release run (#757): {call.strip()}"
            )

    def test_no_gh_call_runs_bare(self, script: str) -> None:
        """A bare ``gh`` under ``set -e`` is the defect this closes.

        Three calls are legitimately not wrapped in ``retry_api`` and are
        exempted by name here rather than by a loose pattern: ``gh api
        graphql`` has the surrounding ``expectedHeadOid`` loop, ``gh pr
        create`` must NOT be blindly retried, because a create whose response
        was lost has still created the PR and a retry would open the duplicate
        that #755 exists to prevent, and the branch-create ``-X POST`` is the
        same non-idempotent-mutation trap: see
        ``TestTheBranchCreatePostIsNotBlindlyRetried``.
        """
        exempt = (
            "gh api graphql",
            "gh pr create",
            '-X POST "repos/${GITHUB_REPOSITORY}/git/refs"',
        )
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


class TestForcedRunsDoNotCloseAHigherVersionPr:
    """#774: a forced dispatch can compute a version LOWER than an open PR.

    ``version_from_forced_level`` bumps the latest TAG, not the accumulated
    commits, so "only the newest computed version is ever correct" (the
    invariant #755's cleanup relied on) is false for a ``force_level``
    dispatch. The cleanup must compare versions, not just branch identity.
    """

    def test_the_step_extracts_a_comparable_version_from_the_stale_branch(
        self, script: str
    ) -> None:
        """Without this, there is nothing to compare ${NEXT} against."""
        assert 'STALE_VERSION="${STALE_BRANCH#release/v}"' in script, (
            "the cleanup no longer extracts a version from the stale branch "
            "name, so it has nothing to compare against ${NEXT} and falls "
            "back to closing on branch identity alone (#774)"
        )

    def test_the_version_comparison_is_numeric_via_sort_v_not_lexical(
        self, script: str
    ) -> None:
        """A lexical comparison ranks '0.9.0' above '0.10.0'; sort -V does not."""
        assert "version_gt() {" in script, (
            "the step no longer defines a version_gt helper, so the cleanup "
            "has no numeric way to compare the stale PR's version against "
            "${NEXT} (#774)"
        )
        assert "sort -V" in script, (
            "version_gt no longer uses `sort -V` for the comparison; a plain "
            "string comparison would rank '0.9.0' above '0.10.0' and could "
            "wrongly treat a higher stale version as lower (#774)"
        )

    def test_a_higher_version_stale_pr_is_skipped_before_the_close(
        self, script: str
    ) -> None:
        """The specific guard: reverting or inverting it must fail this test."""
        helper_at = script.index("version_gt() {")
        guard_at = script.index(
            'if version_gt "${STALE_VERSION}" "${NEXT}"; then', helper_at
        )
        warning_at = script.index("::warning::", guard_at)
        continue_at = script.index("continue", warning_at)
        close_at = script.index("gh pr close", continue_at)

        assert helper_at < guard_at < warning_at < continue_at < close_at, (
            "a stale release PR whose version is higher than ${NEXT} is no "
            "longer skipped ahead of the close, so a force_level dispatch "
            "can close a still-correct, higher-version release PR and ship "
            "a lower one in its place (#774)"
        )

    def test_the_skip_warns_with_both_versions(self, script: str) -> None:
        """A silent skip is as bad as a wrong close: the operator must see why."""
        guard_at = script.index('if version_gt "${STALE_VERSION}" "${NEXT}"; then')
        warning_block = script[guard_at : script.index("continue", guard_at)]

        why = (
            "the higher-version skip no longer names both versions in its "
            "::warning::, so an operator who dispatched force_level cannot "
            "tell why their run did not supersede the open PR (#774)"
        )
        assert "STALE_VERSION" in warning_block, why
        assert "NEXT" in warning_block, why


class TestTheBranchCreatePostIsNotBlindlyRetried:
    """The branch-create POST is not idempotent, unlike the reset PATCH above.

    A lost response after a successful server-side create must not be
    retried blindly: a blind retry re-POSTs and gets back HTTP 422
    "Reference already exists," hard-failing a branch that in fact now
    exists. Recovery is the same idempotent-lookup discipline ``gh pr
    create`` below is already exempted from ``retry_api`` for.
    """

    def test_the_create_post_is_not_wrapped_in_retry_api(self, script: str) -> None:
        """Reverting to a blind `retry_api` wrap is the exact regression."""
        calls = [
            line
            for line in _logical_lines(script)
            if "-X POST" in line
            and "git/refs" in line
            and not line.lstrip().startswith("#")
        ]

        assert calls, "the step no longer contains the branch-create POST"
        for call in calls:
            assert "retry_api" not in call, (
                "the branch-create POST is wrapped in retry_api again; a "
                "lost response is now blindly re-POSTed and hard-fails with "
                f"HTTP 422 'Reference already exists': {call.strip()}"
            )

    def test_a_failed_create_re_checks_via_the_idempotent_lookup(
        self, script: str
    ) -> None:
        """Recovery asks GitHub what happened instead of assuming failure."""
        post_at = script.index('-X POST "repos/${GITHUB_REPOSITORY}/git/refs"')
        status_check_at = script.index('if [ "${POST_STATUS}" -ne 0 ]; then', post_at)
        recheck_at = script.index(
            'gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/${BRANCH}"',
            status_check_at,
        )

        assert post_at < status_check_at < recheck_at, (
            "the failed-create recovery no longer re-runs the branch lookup "
            "after the POST reports a failure, so a lost response has no "
            "path back to success"
        )

    def test_a_ref_matching_the_expected_sha_is_treated_as_success(
        self, script: str
    ) -> None:
        """The specific comparison that tells a lost response from a real conflict."""
        assert 'CREATED_SHA="${RETRY_OUT}"' in script, (
            "the step no longer reads the re-lookup's sha into CREATED_SHA, "
            "so it has nothing to compare against BASE_SHA"
        )
        assert 'if [ "${CREATED_SHA}" != "${BASE_SHA}" ]; then' in script, (
            "the step no longer compares the re-looked-up sha against "
            "BASE_SHA, so it cannot tell a lost-response false failure from "
            "a genuine ref conflict"
        )

    def test_a_mismatched_sha_is_still_a_hard_error(self, script: str) -> None:
        """A ref that exists but points elsewhere is a real conflict, not a lost response."""
        mismatch_at = script.index('if [ "${CREATED_SHA}" != "${BASE_SHA}" ]; then')
        tail = script[mismatch_at : mismatch_at + 400]

        assert "::error::" in tail, (
            "a mismatched CREATED_SHA no longer emits ::error::, so a "
            "genuine ref conflict would be silently treated as success"
        )
        assert "exit 1" in tail, (
            "a mismatched CREATED_SHA no longer hard-fails the step, so a "
            "genuine ref conflict would be silently treated as success"
        )
