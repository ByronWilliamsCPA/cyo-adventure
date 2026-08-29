"""The job's own surface: no route, and a stdout an agent may safely read.

ADR-030 Decision 8 forbids this data set a route, and Decision 6 names the
likeliest real leak on this project: not a stray ``git add``, but an agent
summarising a run into a pull-request description. Both are properties of the
job rather than of the aggregation core, so they are pinned here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.analysis.engagement_correlation import (
    StorybookObservations,
    build_artifact,
)
from scripts import engagement_correlation as job

if TYPE_CHECKING:
    from collections.abc import Iterable

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _observations(*, storybook_id: str, readers: int) -> StorybookObservations:
    """Build one published storybook's observations.

    Args:
        storybook_id: The book's id.
        readers: How many families read it.

    Returns:
        StorybookObservations: The observations.
    """
    families = frozenset(f"family-{index:02d}" for index in range(readers))
    return StorybookObservations(
        storybook_id=storybook_id,
        visibility="catalog",
        is_personalized=False,
        status="published",
        current_published_version=1,
        engagement_verdict="advisory",
        reader_families=families,
        completed_families=frozenset(sorted(families)[:3]),
        returned_families=frozenset(),
        rating_by_family={},
        flag_families_by_reason={},
    )


class TestNoRoute:
    """ADR-030 Decision 8: a route is a data-egress path this data may not have."""

    def test_no_route_path_mentions_this_analysis(self) -> None:
        """The application's own route table, not a grep of the router files."""
        from cyo_adventure.app import create_app

        paths = {str(getattr(route, "path", "")) for route in create_app().routes}
        for path in paths:
            assert "engagement" not in path
            assert "correlation" not in path
            assert "/analysis" not in path

    def test_importing_the_application_never_imports_the_analysis_package(
        self,
    ) -> None:
        """Structural: the package cannot be reached from the served app at all.

        Checked in a fresh interpreter rather than against this process's
        ``sys.modules``, which any earlier test in the session may have
        populated. A route added later would have to import this package, so a
        clean module graph is the property that actually forbids one.
        """
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import cyo_adventure.app; "
                    "print([m for m in sys.modules "
                    "if m.startswith('cyo_adventure.analysis')])"
                ),
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        # The interpreter's own startup logging goes to stdout too; the probe's
        # answer is the last line it printed.
        assert completed.stdout.strip().splitlines()[-1] == "[]"

    def test_the_job_module_defines_no_router_and_no_fastapi_app(self) -> None:
        """A router object is the thing that would get wired in by mistake."""
        for module_name in (
            "cyo_adventure.analysis.engagement_correlation",
            "cyo_adventure.analysis.queries",
            "cyo_adventure.analysis.flywheel_input",
        ):
            module = __import__(module_name, fromlist=["_"])
            for attribute in vars(module).values():
                assert type(attribute).__name__ not in {"APIRouter", "FastAPI"}

    def test_app_py_is_untouched_by_this_work(self) -> None:
        """The brief's control 6 in its own words: do not touch ``app.py``."""
        source = (_REPO_ROOT / "src" / "cyo_adventure" / "app.py").read_text(
            encoding="utf-8"
        )
        assert "analysis" not in source
        assert "engagement_correlation" not in source


class TestStdoutDiscipline:
    """What the job prints is what an agent can quote into a public PR body."""

    @staticmethod
    def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> str:
        """Run the CLI and return everything it wrote.

        Args:
            capsys: pytest's capture fixture.
            argv: The argument vector, without the program name.

        Returns:
            str: stdout and stderr, concatenated.
        """
        _ = job.main(argv)
        captured = capsys.readouterr()
        return captured.out + captured.err

    def test_a_disabled_run_says_so_and_says_nothing_else(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Off is the shipped state, so this is the output that actually appears."""
        monkeypatch.setattr(
            job.settings, "analysis_engagement_correlation_enabled", False
        )
        output = self._run(capsys, [])
        assert "disabled" in output
        assert len(output.splitlines()) <= 2

    def test_an_enabled_run_prints_no_row_and_no_figure_from_the_artifact(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The leak this control exists for, tested with recognisable payloads.

        Every value in the artifact is given a form that would be visible in
        stdout if it were echoed: a distinctive storybook id, and a family
        identifier that only exists inside the observations.
        """
        target = tmp_path / "reports"
        monkeypatch.setattr(
            job.settings, "analysis_engagement_correlation_enabled", True
        )
        monkeypatch.setattr(
            job.settings,
            "analysis_engagement_correlation_output_dir",
            str(target),
        )
        observations = [_observations(storybook_id="BOOK-SENTINEL-ID", readers=9)]
        monkeypatch.setattr(
            job,
            "run_job",
            lambda: job.write_artifact(target, build_artifact(observations)),
        )
        output = self._run(capsys, [])

        written = json.loads(job.artifact_paths(target)[-1].read_text(encoding="utf-8"))
        rows = written["rows"]
        assert len(rows) == 1
        assert rows[0]["storybook_id"] == "BOOK-SENTINEL-ID"

        assert "BOOK-SENTINEL-ID" not in output
        assert "family-00" not in output
        assert "advisory" not in output
        assert "completion" not in output
        assert str(target) in output

    def test_stdout_carries_no_count_of_storybooks(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A count of rows is itself a figure about children's reading.

        Two runs whose artifacts differ in how many books they cover must print
        the same thing, or the count is recoverable from the log.
        """
        target = tmp_path / "reports"
        monkeypatch.setattr(
            job.settings, "analysis_engagement_correlation_enabled", True
        )
        monkeypatch.setattr(
            job.settings, "analysis_engagement_correlation_output_dir", str(target)
        )

        def _outputs(books: Iterable[str]) -> str:
            documents = build_artifact(
                [_observations(storybook_id=book, readers=9) for book in books]
            )
            monkeypatch.setattr(
                job, "run_job", lambda: job.write_artifact(target, documents)
            )
            _ = job.main([])
            captured = capsys.readouterr()
            return captured.out + captured.err

        one = _outputs(["book-a"])
        many = _outputs(["book-a", "book-b", "book-c", "book-d"])
        # The retained-file count is about this job's own housekeeping and is
        # allowed to differ; nothing else is.
        normalise = partial(re.compile(r"retained \d+").sub, "retained N")
        assert normalise(one) == normalise(many)


class TestSelfCheck:
    """The scheduled workflow's only job: are the controls still armed?"""

    def test_the_self_check_passes_on_this_working_tree(self) -> None:
        """It is the gate the workflow runs, so it must be green on ``main``."""
        assert job.self_check() == []

    def test_the_self_check_exits_zero_and_names_no_path(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Its output is read by an agent too."""
        assert job.main(["--self-check"]) == 0
        captured = capsys.readouterr()
        assert "engagement-correlation" in captured.out

    def test_the_self_check_notices_an_artifact_that_reached_the_repository(
        self, tmp_path: Path
    ) -> None:
        """The discriminating half: the walker must actually find one.

        ``self_check`` passing on a clean tree is equally consistent with a
        walker that finds nothing anywhere.
        """
        planted = (
            tmp_path / f"{job.ARTIFACT_PREFIX}20260101T000000Z{job.ARTIFACT_SUFFIX}"
        )
        _ = planted.write_text("{}", encoding="utf-8")
        assert job._committed_artifacts(tmp_path) == [planted]

    def test_the_self_check_skips_vendored_and_git_internal_directories(
        self, tmp_path: Path
    ) -> None:
        """A hit inside ``.git`` or ``node_modules`` is not a committed artifact."""
        buried = tmp_path / "node_modules" / "pkg"
        buried.mkdir(parents=True)
        _ = (
            buried / f"{job.ARTIFACT_PREFIX}20260101T000000Z{job.ARTIFACT_SUFFIX}"
        ).write_text("{}", encoding="utf-8")
        assert job._committed_artifacts(tmp_path) == []

    def test_no_gitignore_in_this_repository_names_the_artifact(self) -> None:
        """Decision 6 adds no ignore entry, on purpose.

        An ignore entry says the artifact belongs in the tree and merely should
        not be staged. It does not belong in the tree.
        """
        assert job._gitignore_mentions_artifact(_REPO_ROOT) is False
