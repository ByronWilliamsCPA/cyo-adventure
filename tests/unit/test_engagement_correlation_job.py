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

    def test_gitignore_mentions_artifact_detects_a_real_mention(
        self, tmp_path: Path
    ) -> None:
        """The discriminating half of the check above.

        A helper that always returns ``False`` passes the negative test on this
        real repository too; only a planted positive tells them apart.
        """
        _ = (tmp_path / ".gitignore").write_text(
            f"{job.ARTIFACT_PREFIX.rstrip('-')}\n", encoding="utf-8"
        )
        assert job._gitignore_mentions_artifact(tmp_path) is True


class TestSelfCheckBranches:
    """Each of ``self_check``'s seven conditions, forced and checked in isolation.

    ``test_the_self_check_passes_on_this_working_tree`` above proves the
    all-clear case on the real tree, but that alone cannot tell a genuine
    per-condition implementation apart from one that always returns ``[]``, or
    one where a single ``if`` has quietly been deleted: both look identical on
    a tree where every condition already happens to hold. Every test here
    forces exactly one condition into its failing state while holding the rest
    at their passing state, and asserts the *exact* resulting list, not merely
    that it is non-empty, so a check that starts reporting the wrong failure
    string is also caught.
    """

    @staticmethod
    def _hold_repo_checks_clear(monkeypatch: pytest.MonkeyPatch) -> None:
        """Pin the two repo-walking conditions to their passing state.

        Without this, a branch test that forces one condition could pass for
        the wrong reason if this working tree (shared with concurrent
        sessions per this repo's own operating notes) happened to carry a
        stray artifact or a stray ``.gitignore`` mention at the moment the
        test runs.

        Args:
            monkeypatch: pytest's monkeypatch fixture.
        """
        monkeypatch.setattr(job, "_committed_artifacts", lambda root: [])
        monkeypatch.setattr(job, "_gitignore_mentions_artifact", lambda root: False)

    def test_all_clear_only_when_every_condition_genuinely_holds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The all-clear case, with the repo-walking half held explicit.

        Complements the plain ``self_check() == []`` test: this one does not
        rely on the ambient state of the real tree for two of the seven
        conditions, so it stays meaningful even if this shared working tree is
        mid-edit by another session.
        """
        self._hold_repo_checks_clear(monkeypatch)
        assert job.self_check() == []

    def test_flags_a_kill_switch_default_that_flips_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cyo_adventure.core.config import Settings

        self._hold_repo_checks_clear(monkeypatch)
        field = Settings.model_fields["analysis_engagement_correlation_enabled"]
        monkeypatch.setattr(field, "default", True)
        assert job.self_check() == ["the kill switch does not default to off"]

    def test_flags_an_empty_output_path_that_is_not_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._hold_repo_checks_clear(monkeypatch)
        real_refuses = job._refuses

        def fake_refuses(*, output_dir: str) -> bool:
            if output_dir == "":
                return False
            return real_refuses(output_dir=output_dir)

        monkeypatch.setattr(job, "_refuses", fake_refuses)
        assert job.self_check() == ["an empty output path is not refused"]

    def test_flags_an_in_repository_output_path_that_is_not_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._hold_repo_checks_clear(monkeypatch)
        real_refuses = job._refuses
        in_repo = str(job._REPO_ROOT / "out")

        def fake_refuses(*, output_dir: str) -> bool:
            if output_dir == in_repo:
                return False
            return real_refuses(output_dir=output_dir)

        monkeypatch.setattr(job, "_refuses", fake_refuses)
        assert job.self_check() == [
            "an output path inside this repository is not refused"
        ]

    def test_flags_a_path_outside_any_worktree_that_is_wrongly_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The acceptance check: a legitimate path must not be refused.

        ``self_check`` builds its own scratch temp directory internally, so
        this cannot match on an exact path; it matches on the fixed basename
        ``self_check`` gives the candidate for this specific condition, which
        is distinct from the basename used for the worktree condition below.
        """
        self._hold_repo_checks_clear(monkeypatch)
        real_refuses = job._refuses

        def fake_refuses(*, output_dir: str) -> bool:
            if Path(output_dir).name == "artifacts":
                return True
            return real_refuses(output_dir=output_dir)

        monkeypatch.setattr(job, "_refuses", fake_refuses)
        assert job.self_check() == ["a path outside any working tree is refused"]

    def test_flags_a_dot_git_file_worktree_that_is_not_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._hold_repo_checks_clear(monkeypatch)
        real_refuses = job._refuses

        def fake_refuses(*, output_dir: str) -> bool:
            if Path(output_dir).name == "reports":
                return False
            return real_refuses(output_dir=output_dir)

        monkeypatch.setattr(job, "_refuses", fake_refuses)
        assert job.self_check() == ["a worktree marked by a .git FILE is not refused"]

    def test_flags_committed_artifacts_found_in_the_tree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._hold_repo_checks_clear(monkeypatch)
        planted = [Path("/fake/a.json"), Path("/fake/b.json")]
        monkeypatch.setattr(job, "_committed_artifacts", lambda root: planted)
        assert job.self_check() == [
            (
                "2 engagement-correlation artifact file(s) are in the repository "
                "tree and must be removed"
            )
        ]

    def test_flags_a_gitignore_entry_naming_the_artifact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._hold_repo_checks_clear(monkeypatch)
        monkeypatch.setattr(job, "_gitignore_mentions_artifact", lambda root: True)
        assert job.self_check() == [
            (
                "a .gitignore entry names this artifact; Decision 6 adds none, "
                "because an ignore entry says the artifact belongs in the tree"
            )
        ]


class _StubResult:
    """A minimal stand-in for a SQLAlchemy result."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        """Store the rows this result yields.

        Args:
            rows: The rows, in the statement's own column order.
        """
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        """Return every row.

        Returns:
            list[tuple[object, ...]]: The rows.
        """
        return self._rows


class _StubSession:
    """Answers each of the job's six statements by recognising its SQL.

    Keyed on the compiled SQL rather than on call order, so the fixture cannot
    quietly answer the wrong statement if the reader is reordered, and so a
    statement the job stops issuing shows up as an unconsumed fixture.
    """

    def __init__(self, answers: dict[str, list[tuple[object, ...]]]) -> None:
        """Store the answers, keyed by a distinguishing SQL fragment.

        Args:
            answers: Rows keyed by a fragment of the statement's SQL.
        """
        self.answers = answers
        self.consumed: set[str] = set()

    async def execute(self, statement: object) -> _StubResult:
        """Return the rows for the statement whose SQL matches one key.

        Args:
            statement: The statement the job issued.

        Returns:
            _StubResult: The matching rows.

        Raises:
            AssertionError: when the statement matches no key or several.
        """
        sql = str(statement)
        matched = [key for key in self.answers if key in sql]
        assert len(matched) == 1, f"{matched} keys matched: {sql}"
        self.consumed.add(matched[0])
        return _StubResult(self.answers[matched[0]])


class TestLoadObservationsAndReport:
    """The reducer between the allowlisted reads and the gating core.

    This is where the job turns rows into family-grain observations, and it is
    the only part of the read path that a fixture can exercise without a
    database. The test ends by writing a real artifact file, so the whole chain
    from statement results to a report on disk is covered.
    """

    @staticmethod
    def _answers() -> dict[str, list[tuple[object, ...]]]:
        """Return canned rows for all six statements.

        Returns:
            dict: Rows keyed by a distinguishing SQL fragment.
        """
        readers = [("book-open", 2, f"fam-{i}") for i in range(6)]
        completions = [
            ("book-open", 2, "fam-0", "2026-01-01"),
            ("book-open", 2, "fam-0", "2026-01-08"),
            ("book-open", 2, "fam-1", "2026-01-02"),
        ]
        return {
            "storybook.personalization_subject_profile_id": [
                ("book-open", "catalog", "published", 2, None),
                ("book-family", "family", "published", 1, None),
                ("book-personal", "catalog", "published", 1, "profile-9"),
                ("book-quiet", "catalog", "published", 1, None),
            ],
            "storybook_version.moderation_report": [
                (
                    "book-open",
                    2,
                    {"findings": [{"stage": 4, "verdict": "advisory", "message": "x"}]},
                )
            ],
            "FROM reading_state": readers
            + [("book-family", 1, f"fam-{i}") for i in range(9)]
            + [("book-personal", 1, f"fam-{i}") for i in range(9)]
            + [("book-quiet", 1, "fam-0")],
            "FROM completion": completions,
            "FROM rating": [("book-open", 5, f"fam-{i}") for i in range(6)],
            "FROM kid_flag": [("book-open", "scared_me", "fam-0")],
        }

    @pytest.mark.asyncio
    async def test_the_job_reduces_rows_to_family_grain_and_writes_a_report(
        self, tmp_path: Path
    ) -> None:
        """End to end from statement results to an artifact on disk.

        Asserts the outcome that matters: the two categorically excluded books
        and the one below the floor produce no row despite having readers, and
        the surviving book's figures are the ones the reads imply.
        """
        answers = self._answers()
        session = _StubSession(answers)
        observations = await job.load_observations(session)  # pyright: ignore[reportArgumentType]
        assert session.consumed == set(answers)

        path = job.write_artifact(tmp_path / "reports", build_artifact(observations))
        document = json.loads(path.read_text(encoding="utf-8"))
        rows = document["rows"]
        assert [row["storybook_id"] for row in rows] == ["book-open"]

        row = rows[0]
        assert row["engagement_verdict"] == "advisory"
        # Two of six reader families completed it; one of those came back on a
        # later calendar day.
        assert row["completion_rate"] == pytest.approx(0.35)
        assert row["return_read_rate"] == pytest.approx(0.15)
        assert row["reader_family_band"] == "5-9"
        # Six families rated it 5, so the mean publishes; one family flagged it,
        # so the flag cell does not.
        assert row["rating_mean"] == pytest.approx(5.0)
        assert row["flag_counts"] == "<5"

    @pytest.mark.asyncio
    async def test_the_reducer_never_carries_a_version_across_a_republish(
        self, tmp_path: Path
    ) -> None:
        """Version-scoped signals must read the current published version only.

        The same book's earlier version has readers and completions; none of
        them may count toward the published version's figures.
        """
        answers = self._answers()
        answers["FROM reading_state"] = [
            *answers["FROM reading_state"],
            *[("book-open", 1, f"stale-{i}") for i in range(40)],
        ]
        session = _StubSession(answers)
        observations = await job.load_observations(session)  # pyright: ignore[reportArgumentType]
        opened = next(o for o in observations if o.storybook_id == "book-open")
        assert len(opened.reader_families) == 6
        assert not any(f.startswith("stale-") for f in opened.reader_families)
