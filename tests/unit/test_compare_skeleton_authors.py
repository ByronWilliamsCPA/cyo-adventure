"""Unit tests for the skeleton-authoring comparison harness.

The harness computes register row `S-1`'s primary endpoint, so the logic that
turns provider replies into ``repair_rounds`` / ``strict_pass`` records is the
part that fails as wrong numbers rather than crashes. These tests pin down:
``author_shell``'s repair-loop bookkeeping (attempts, rounds, the
shell-written-before-named invariant, last-written-document scoring),
``permutation_test``'s determinism and degeneracy behavior, and
``_score_shell_mode``'s read-modify-write path, the sole route by which every
subagent and Modal leg's data reaches the summary.

No test makes a network call and none invokes the real checkers: the checker
boundary (``_strict_check`` / ``_run_checker`` / ``_catalog_distances``) is
stubbed at the module seam, exactly as ``--mock`` runs stub the provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import scripts.compare_skeleton_authors as csa
from cyo_adventure.generation.usage import Completion, TokenUsage

VALID_SHELL = json.dumps({"schema_version": "2.0", "title": "t", "nodes": []})


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        usage=TokenUsage(
            provider="mock",
            model="mock",
            input_tokens=1,
            output_tokens=2,
            duration_ms=0,
        ),
        finish_reason="stop",
    )


class _ScriptedProvider:
    """Provider returning a fixed sequence of raw completions."""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls = 0

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Any:
        del system, prompt, max_tokens
        self.calls += 1
        return _completion(self._replies.pop(0))


def _record(**overrides: Any) -> csa.ShellRecord:
    base: dict[str, Any] = {
        "leg": "test-leg",
        "family": "test",
        "cell_id": "A",
        "band": "5-8",
        "length": "short",
        "style": "prose",
        "replicate": 1,
        "premise": "a premise",
    }
    base.update(overrides)
    # A strict pass always names the shell it passed on (ShellRecord's
    # invariant); default one so fixtures need not restate it every time.
    if base.get("strict_pass") and not base.get("shell_file"):
        base["shell_file"] = (
            f"shells/{base['cell_id']}__r{base['replicate']}__{base['leg']}.json"
        )
    return csa.ShellRecord(**base)


@pytest.fixture
def stub_checkers(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the checker boundary; ``verdicts`` scripts _strict_check calls."""
    state: dict[str, Any] = {"verdicts": [], "strict_calls": 0}

    def fake_strict(
        path: Path, band: str, length: str, style: str
    ) -> tuple[bool, str, int]:
        del path, band, length, style
        state["strict_calls"] += 1
        passed = state["verdicts"].pop(0)
        return passed, "" if passed else "L1-2 dangling ref", 0 if passed else 1

    monkeypatch.setattr(csa, "_strict_check", fake_strict)
    monkeypatch.setattr(csa, "_run_checker", lambda *_a, **_k: (0, ""))
    monkeypatch.setattr(
        csa, "_catalog_distances", lambda *_a, **_k: (0.5, 0.6, "vs 2 peers")
    )
    return state


class TestAuthorShell:
    def test_fail_then_pass_bookkeeping(
        self, tmp_path: Path, stub_checkers: dict[str, Any]
    ) -> None:
        stub_checkers["verdicts"] = [False, True]
        provider = _ScriptedProvider([VALID_SHELL, VALID_SHELL])
        record = asyncio.run(
            csa.author_shell(
                provider,
                _record(),
                "brief",
                tmp_path,
                max_repair_rounds=6,
                max_tokens=100,
            )
        )
        assert record.attempts == 2
        assert record.repair_rounds == 1
        assert record.strict_pass is True
        assert record.first_pass_clean is False
        assert record.shell_file
        assert (tmp_path / record.shell_file).exists()
        record_file = tmp_path / "records" / "A__r1__test-leg.json.record.json"
        assert json.loads(record_file.read_text())["strict_pass"] is True

    def test_all_unparseable_names_no_shell_file(
        self, tmp_path: Path, stub_checkers: dict[str, Any]
    ) -> None:
        provider = _ScriptedProvider(["not json", "still not json"])
        record = asyncio.run(
            csa.author_shell(
                provider,
                _record(),
                "brief",
                tmp_path,
                max_repair_rounds=1,
                max_tokens=100,
            )
        )
        assert record.strict_pass is False
        assert record.parse_failures == 2
        assert record.shell_file == ""
        assert not (tmp_path / "shells" / "A__r1__test-leg.json").exists()
        assert record.min_catalog_distance is None
        assert stub_checkers["strict_calls"] == 0

    def test_final_unparseable_round_keeps_written_shell_metrics(
        self, tmp_path: Path, stub_checkers: dict[str, Any]
    ) -> None:
        stub_checkers["verdicts"] = [False]
        provider = _ScriptedProvider([VALID_SHELL, "garbage"])
        record = asyncio.run(
            csa.author_shell(
                provider,
                _record(),
                "brief",
                tmp_path,
                max_repair_rounds=1,
                max_tokens=100,
            )
        )
        assert record.strict_pass is False
        assert record.shell_file
        assert (tmp_path / record.shell_file).exists()
        # metrics come from the last WRITTEN document, not the last round
        assert record.min_catalog_distance == 0.5
        assert record.graph_check_exit == 0


class TestPermutationTest:
    def test_deterministic_and_separating(self) -> None:
        rounds = {"a": [0, 0, 1], "b": [5, 6, 6]}
        stat1, p1 = csa.permutation_test(rounds)
        stat2, p2 = csa.permutation_test(rounds)
        assert (stat1, p1) == (stat2, p2)
        assert stat1 > 0
        assert p1 < 0.2

    def test_constant_vector_is_degenerate(self) -> None:
        stat, p = csa.permutation_test({"a": [0, 0, 0], "b": [0, 0, 0]})
        assert stat == 0.0
        assert p == 1.0


class TestSummarizeDegeneracy:
    def test_constant_rounds_marks_primary_endpoint_void(self, tmp_path: Path) -> None:
        records = [
            _record(
                leg=leg,
                replicate=r,
                strict_pass=True,
                repair_rounds=0,
                shell_file=f"shells/A__r{r}__{leg}.json",
            )
            for leg in ("a", "b")
            for r in (1, 2)
        ]
        csa._summarize(records, tmp_path)  # pyright: ignore[reportPrivateUsage]
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["primary_endpoint"]["degenerate"] is True
        assert "VOID" in (tmp_path / "summary.md").read_text()

    def test_varying_rounds_not_degenerate(self, tmp_path: Path) -> None:
        records = [
            _record(leg="a", replicate=1, strict_pass=True, repair_rounds=0),
            _record(leg="a", replicate=2, strict_pass=True, repair_rounds=1),
            _record(leg="b", replicate=1, strict_pass=True, repair_rounds=3),
            _record(leg="b", replicate=2, strict_pass=True, repair_rounds=4),
        ]
        csa._summarize(records, tmp_path)  # pyright: ignore[reportPrivateUsage]
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["primary_endpoint"]["degenerate"] is False
        assert "VOID" not in (tmp_path / "summary.md").read_text()

    def test_censored_shells_do_not_enter_the_endpoint(self, tmp_path: Path) -> None:
        # Failing-at-cap shells carry no rounds-to-pass observation; varying
        # censored counts must not rescue the endpoint from degeneracy.
        records = [
            _record(leg="a", replicate=1, strict_pass=False, repair_rounds=0),
            _record(leg="b", replicate=1, strict_pass=False, repair_rounds=6),
        ]
        csa._summarize(records, tmp_path)  # pyright: ignore[reportPrivateUsage]
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["primary_endpoint"]["degenerate"] is True

    def test_single_leg_sample_is_degenerate(self, tmp_path: Path) -> None:
        records = [
            _record(leg="a", replicate=1, strict_pass=True, repair_rounds=0),
            _record(leg="a", replicate=2, strict_pass=True, repair_rounds=3),
        ]
        csa._summarize(records, tmp_path)  # pyright: ignore[reportPrivateUsage]
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["primary_endpoint"]["degenerate"] is True


def _score_args(tmp_path: Path, shell: Path, **overrides: Any) -> Any:
    base = {
        "score_shell": str(shell),
        "score_cell": "A",
        "score_replicate": 1,
        "score_leg": "sub-leg",
        "score_family": "anthropic",
        "out_dir": str(tmp_path / "run"),
        "max_repair_rounds": 6,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


_CELLS = [
    {
        "id": "A",
        "band": "5-8",
        "length": "short",
        "style": "prose",
        "premises": ["p1", "p2"],
    }
]


class TestScoreShellMode:
    def test_read_modify_write_accumulates_rounds(
        self, tmp_path: Path, stub_checkers: dict[str, Any]
    ) -> None:
        shell = tmp_path / "attempt.json"
        shell.write_text(VALID_SHELL, encoding="utf-8")

        stub_checkers["verdicts"] = [False]
        assert (
            csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
                _score_args(tmp_path, shell), _CELLS
            )
            == 1
        )

        stub_checkers["verdicts"] = [True]
        assert (
            csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
                _score_args(tmp_path, shell), _CELLS
            )
            == 0
        )

        record_path = tmp_path / "run" / "records" / "A__r1__sub-leg.json.record.json"
        record = json.loads(record_path.read_text())
        assert record["attempts"] == 2
        assert record["repair_rounds"] == 1
        assert record["strict_pass"] is True
        assert record["first_pass_clean"] is False

    def test_empty_leg_rejected_before_paths(self, tmp_path: Path) -> None:
        shell = tmp_path / "attempt.json"
        shell.write_text(VALID_SHELL, encoding="utf-8")
        code = csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
            _score_args(tmp_path, shell, score_leg=""), _CELLS
        )
        assert code == 2
        assert not (tmp_path / "run").exists()

    def test_traversal_leg_rejected_before_paths(self, tmp_path: Path) -> None:
        shell = tmp_path / "attempt.json"
        shell.write_text(VALID_SHELL, encoding="utf-8")
        code = csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
            _score_args(tmp_path, shell, score_leg="x/../../escape"), _CELLS
        )
        assert code == 2
        assert not (tmp_path / "run").exists()

    def test_unknown_family_rejected(self, tmp_path: Path) -> None:
        shell = tmp_path / "attempt.json"
        shell.write_text(VALID_SHELL, encoding="utf-8")
        code = csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
            _score_args(tmp_path, shell, score_family=""), _CELLS
        )
        assert code == 2
        assert not (tmp_path / "run").exists()

    def test_submission_over_round_cap_rejected(
        self, tmp_path: Path, stub_checkers: dict[str, Any]
    ) -> None:
        shell = tmp_path / "attempt.json"
        shell.write_text(VALID_SHELL, encoding="utf-8")
        stub_checkers["verdicts"] = [False, False]
        for _ in range(2):
            csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
                _score_args(tmp_path, shell, max_repair_rounds=1), _CELLS
            )
        # attempts == 2 == 1 + cap: a third submission must be refused
        # without consuming a checker run or touching the record.
        code = csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
            _score_args(tmp_path, shell, max_repair_rounds=1), _CELLS
        )
        assert code == 2
        record_path = tmp_path / "run" / "records" / "A__r1__sub-leg.json.record.json"
        assert json.loads(record_path.read_text())["attempts"] == 2

    def test_checker_timeout_is_not_scored_as_feedback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shell = tmp_path / "attempt.json"
        shell.write_text(VALID_SHELL, encoding="utf-8")
        monkeypatch.setattr(
            csa,
            "_strict_check",
            lambda *_a, **_k: (False, "check_skeleton.py timed out", 124),
        )
        monkeypatch.setattr(csa, "_run_checker", lambda *_a, **_k: (0, ""))
        monkeypatch.setattr(
            csa, "_catalog_distances", lambda *_a, **_k: (None, None, "")
        )
        code = csa._score_shell_mode(  # pyright: ignore[reportPrivateUsage]
            _score_args(tmp_path, shell), _CELLS
        )
        assert code == 2
        record_path = tmp_path / "run" / "records" / "A__r1__sub-leg.json.record.json"
        record = json.loads(record_path.read_text())
        assert "timed out" in record["error"]
        # a timeout is not a validator finding, so it never becomes feedback
        assert record["last_feedback"] == ""
        assert record["findings_lines_per_round"] == []


class TestRecordInvariant:
    def test_strict_pass_requires_a_shell_file(self) -> None:
        # Constructed directly, not via _record: the helper defaults a
        # shell_file for strict passes, which is exactly what this guards.
        with pytest.raises(ValueError, match="shell_file"):
            csa.ShellRecord(
                leg="test-leg",
                family="test",
                cell_id="A",
                band="5-8",
                length="short",
                style="prose",
                replicate=1,
                premise="a premise",
                strict_pass=True,
            )

    def test_strict_pass_with_shell_file_is_accepted(self) -> None:
        assert _record(strict_pass=True, shell_file="shells/x.json").strict_pass


class TestExtractJson:
    def test_leading_worked_example_still_yields_the_skeleton(self) -> None:
        skeleton = {"schema_version": "2.0", "id": "real", "nodes": [1, 2, 3]}
        text = (
            "Here is the shape I will follow:\n"
            '{"id": "<slug>", "nodes": []}\n'
            "And here is the skeleton:\n" + json.dumps(skeleton)
        )
        doc, reason = csa._extract_json(text)  # pyright: ignore[reportPrivateUsage]
        assert reason == ""
        assert doc == skeleton

    def test_plain_object_parses_exactly_as_before(self) -> None:
        doc, reason = csa._extract_json(  # pyright: ignore[reportPrivateUsage]
            "prose before " + VALID_SHELL + " prose after"
        )
        assert reason == ""
        assert doc == json.loads(VALID_SHELL)

    def test_no_object_still_reports_a_reason(self) -> None:
        doc, reason = csa._extract_json("no braces here")  # pyright: ignore[reportPrivateUsage]
        assert doc is None
        assert reason


class TestFilterCells:
    def test_unknown_id_is_rejected_even_when_another_matches(self) -> None:
        selected, error = csa._filter_cells(  # pyright: ignore[reportPrivateUsage]
            _CELLS, "A,Z"
        )
        assert selected == []
        assert "Z" in error

    def test_empty_spec_keeps_every_cell(self) -> None:
        selected, error = csa._filter_cells(  # pyright: ignore[reportPrivateUsage]
            _CELLS, ""
        )
        assert selected == _CELLS
        assert error == ""

    def test_known_id_selects_it(self) -> None:
        selected, error = csa._filter_cells(  # pyright: ignore[reportPrivateUsage]
            _CELLS, "A"
        )
        assert [c["id"] for c in selected] == ["A"]
        assert error == ""

    def test_run_rejects_an_unknown_cell(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`run()` must reject `--cells A,Z`, not silently drop Z."""
        monkeypatch.setattr(csa, "_load_vendors", lambda _p: [])
        monkeypatch.setattr(csa, "_load_premises", lambda _p: _CELLS)
        args = argparse.Namespace(
            vendors="v.json",
            premises="p.json",
            cells="A,Z",
            legs="",
            replicates=1,
            out_dir=str(tmp_path / "run"),
        )
        assert asyncio.run(csa.run(args)) == 1
        assert not (tmp_path / "run").exists()


class TestSummaryLead:
    def _first_paragraph(self, text: str) -> str:
        return next(
            line
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        )

    def test_degenerate_lead_starts_with_the_void_verdict(self, tmp_path: Path) -> None:
        records = [
            _record(
                leg=leg,
                replicate=1,
                strict_pass=True,
                repair_rounds=0,
                shell_file=f"shells/A__r1__{leg}.json",
            )
            for leg in ("a", "b")
        ]
        csa._summarize(records, tmp_path)  # pyright: ignore[reportPrivateUsage]
        body = (tmp_path / "summary.md").read_text()
        assert self._first_paragraph(body).startswith(
            "Primary endpoint (S-1): VOID for this run."
        )
        assert "Everything below is exploratory" not in body
        assert "strict-pass column" in body
        assert "tools-meta.json" in body

    def test_non_degenerate_lead_is_unchanged(self, tmp_path: Path) -> None:
        records = [
            _record(leg="a", replicate=1, strict_pass=True, repair_rounds=0),
            _record(leg="a", replicate=2, strict_pass=True, repair_rounds=1),
            _record(leg="b", replicate=1, strict_pass=True, repair_rounds=3),
            _record(leg="b", replicate=2, strict_pass=True, repair_rounds=4),
        ]
        csa._summarize(records, tmp_path)  # pyright: ignore[reportPrivateUsage]
        body = (tmp_path / "summary.md").read_text()
        first = self._first_paragraph(body)
        assert first.startswith("Primary endpoint (S-1): between-leg statistic ")
        assert first.endswith("Everything below is exploratory.")
        assert "VOID" not in body


class TestModalResumeGuard:
    """R3: a corrupt grid record must not abort the Modal driver's grid."""

    def test_unreadable_record_means_re_author(self, tmp_path: Path) -> None:
        import scripts.modal_kimi_leg as mkl

        record = tmp_path / "A__r1__leg.json.record.json"
        record.write_text('{"strict_pass": tr', encoding="utf-8")
        assert mkl._resume_skip(record) is False  # pyright: ignore[reportPrivateUsage]

    def test_missing_record_means_re_author(self, tmp_path: Path) -> None:
        import scripts.modal_kimi_leg as mkl

        assert (  # pyright: ignore[reportPrivateUsage]
            mkl._resume_skip(tmp_path / "absent.record.json") is False
        )

    def test_passed_record_is_skipped(self, tmp_path: Path) -> None:
        import scripts.modal_kimi_leg as mkl

        record = tmp_path / "A__r1__leg.json.record.json"
        record.write_text('{"strict_pass": true}', encoding="utf-8")
        assert mkl._resume_skip(record) is True  # pyright: ignore[reportPrivateUsage]
