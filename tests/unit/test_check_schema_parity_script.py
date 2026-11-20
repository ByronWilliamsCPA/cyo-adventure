"""Unit tests for scripts/check_schema_parity.py (no database).

The script is loaded from its file path (scripts/ is not a package). The
database read is patched; tests/integration/test_schema_parity_check.py runs
the script against a real migrated Postgres for each verdict.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cyo_adventure.core.schema_parity import SchemaComparison

_SPEC = importlib.util.spec_from_file_location(
    "check_schema_parity",
    Path(__file__).resolve().parents[2] / "scripts" / "check_schema_parity.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = script
_SPEC.loader.exec_module(script)

pytestmark = pytest.mark.unit

_SECRET_URL = (
    "postgresql://cyo_ro:hunter2-very-secret@db.internal.example:5432/postgres"
)


def _repo(*versions: str) -> list[object]:
    return [script.RepoMigration(v, f"{v}_m") for v in versions]


class TestLoadRepoMigrations:
    def test_sorted_by_version_and_non_matching_files_skipped(
        self, tmp_path: Path
    ) -> None:
        for name in ("20260102_b.sql", "20260101_a.sql", "README.sql", "x.txt"):
            (tmp_path / name).write_text("select 1;")
        found = script.load_repo_migrations(tmp_path)
        assert [m.version for m in found] == ["20260101", "20260102"]
        assert found[0].filename == "20260101_a"


class TestCompareHistory:
    def test_pending_unknown_and_out_of_order(self) -> None:
        history = script.compare_history(_repo("1", "2", "3", "5"), ["1", "3", "4"])
        assert [m.version for m in history.pending] == ["2", "5"]
        assert [m.version for m in history.pending_before_head] == ["2"]
        assert history.unknown_applied == ["4"]
        assert history.applied_head == "4"
        assert history.repo_head == "5"

    def test_everything_applied(self) -> None:
        history = script.compare_history(_repo("1", "2"), ["2", "1"])
        assert history.pending == []
        assert history.unknown_applied == []


class TestDecide:
    _ok = SchemaComparison(orm_tables=1, orm_columns=1)
    _behind = SchemaComparison(
        orm_tables=1, orm_columns=1, missing_columns=(("t", "c"),)
    )
    _ahead = SchemaComparison(orm_tables=1, orm_columns=1, extra_tables=("x",))

    def _history(self, applied: list[str]) -> object:
        return script.compare_history(_repo("1", "2"), applied)

    def test_parity(self) -> None:
        assert script.decide(
            self._ok, self._history(["1", "2"]), fail_on_ahead=False
        ) == (
            "IN PARITY",
            0,
        )

    def test_missing_column_is_behind(self) -> None:
        assert (
            script.decide(self._behind, self._history(["1", "2"]), fail_on_ahead=False)[
                1
            ]
            == 1
        )

    def test_pending_migration_alone_is_behind(self) -> None:
        assert script.decide(self._ok, self._history(["1"]), fail_on_ahead=False) == (
            "DATABASE BEHIND",
            1,
        )

    def test_behind_wins_over_ahead(self) -> None:
        verdict, code = script.decide(
            self._ahead, self._history(["1", "9"]), fail_on_ahead=True
        )
        assert (verdict, code) == ("DATABASE BEHIND", 1)

    def test_ahead_exit_zero_unless_strict(self) -> None:
        history = self._history(["1", "2", "9"])
        assert script.decide(self._ok, history, fail_on_ahead=False) == (
            "DATABASE AHEAD",
            0,
        )
        assert script.decide(self._ahead, None, fail_on_ahead=True) == (
            "DATABASE AHEAD",
            4,
        )

    def test_unreadable_history_is_incomplete(self) -> None:
        history = script.HistoryHalf(available=False, unavailable_reason="nope")
        assert script.decide(self._ok, history, fail_on_ahead=False) == (
            "INCOMPLETE",
            3,
        )

    def test_schema_only_parity(self) -> None:
        assert script.decide(self._ok, None, fail_on_ahead=False) == ("IN PARITY", 0)


class TestAsyncpgDsn:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("postgresql+asyncpg://u@h/d", "postgresql://u@h/d"),
            ("postgres://u@h/d", "postgres://u@h/d"),
            (
                "postgresql://u@h/d?sslmode=require",
                "postgresql://u@h/d?sslmode=require",
            ),
        ],
    )
    def test_driver_suffix_is_dropped(self, given: str, expected: str) -> None:
        assert script.asyncpg_dsn(given) == expected


class TestMain:
    def test_missing_url_env_is_an_error_naming_the_variable(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.dict("os.environ", {}, clear=True):
            code = script.main([])
        assert code == 2
        assert "SCHEMA_PARITY_DATABASE_URL" in capsys.readouterr().err

    def test_url_is_not_accepted_as_an_argument(self) -> None:
        with pytest.raises(SystemExit):
            script.main([_SECRET_URL])

    def test_connection_failure_never_echoes_the_url(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        failing = AsyncMock(side_effect=OSError(f"could not connect to {_SECRET_URL}"))
        with (
            patch.dict("os.environ", {"SCHEMA_PARITY_DATABASE_URL": _SECRET_URL}),
            patch.object(script, "read_database", failing),
        ):
            code = script.main(["--json"])
        captured = capsys.readouterr()
        assert code == 2
        assert (
            json.loads(captured.out)["error"]
            == "could not query the database (OSError)"
        )
        for leaked in ("hunter2", "db.internal", "cyo_ro"):
            assert leaked not in captured.out + captured.err

    def test_behind_report_lists_names_but_no_connection_detail(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        (tmp_path / "20260101000000_first.sql").write_text("select 1;")
        (tmp_path / "20260102000000_second.sql").write_text("select 1;")
        read = script.DatabaseRead(
            catalog_rows=[], applied=["20260101000000"], history_reason=None
        )
        with (
            patch.dict("os.environ", {"CUSTOM_URL": _SECRET_URL}, clear=True),
            patch.object(script, "read_database", AsyncMock(return_value=read)),
        ):
            code = script.main(
                ["--url-env", "CUSTOM_URL", "--migrations-dir", str(tmp_path)]
            )
        out = capsys.readouterr().out
        assert code == 1
        assert out.startswith("VERDICT: DATABASE BEHIND")
        assert "20260102000000_second" in out
        # An empty catalog means every ORM table is missing.
        assert "missing tables (app would fail): 0" not in out
        assert "hunter2" not in out
        assert "db.internal" not in out
