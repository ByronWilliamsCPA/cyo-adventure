"""Unit tests for scripts/backfill_narrative_person.py.

The script edits committed catalog skeletons in place by textual splice, so
these tests pin every inference branch, the ``--beats-threshold`` boundary that
must match ``check_prose_craft.py``'s enforcement floor, and every path on
which a bad splice must be REJECTED rather than persisted. Nothing here touches
the real ``skeletons/`` tree: each test chdirs into ``tmp_path``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from scripts.backfill_narrative_person import (
    _build_parser,  # pyright: ignore[reportPrivateUsage]
    _infer,  # pyright: ignore[reportPrivateUsage]
    _insert_person,  # pyright: ignore[reportPrivateUsage]
    _replace_person,  # pyright: ignore[reportPrivateUsage]
    _second_person_rate,  # pyright: ignore[reportPrivateUsage]
    main,
)

if TYPE_CHECKING:
    from pathlib import Path

_SECOND_BEAT = "<<FILL beats='you reach the gate and you wait'>>"
_THIRD_BEAT = "<<FILL beats='Mira reaches the gate and waits'>>"


def _skeleton(
    *, beats: list[str] | None = None, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return a minimal skeleton shape carrying the given beats and metadata.

    Args:
        beats: Directive node bodies, one per node.
        metadata: The skeleton's metadata block.

    Returns:
        A parsed-skeleton-shaped dict.
    """
    bodies = beats if beats is not None else []
    return {
        "schema_version": "2.0",
        "id": "sk_test",
        "metadata": metadata if metadata is not None else {"age_band": "8-11"},
        "nodes": [
            {"id": f"n{index}", "body": body} for index, body in enumerate(bodies)
        ],
    }


def _write_fill(tmp_path: Path, slug: str, bodies: list[str]) -> None:
    """Write a committed fill at ``out/<slug>.filled.json`` under ``tmp_path``.

    Args:
        tmp_path: The temporary working directory.
        slug: The skeleton slug the fill belongs to.
        bodies: Node prose bodies for the fill.
    """
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    (out / f"{slug}.filled.json").write_text(
        json.dumps({"nodes": [{"id": "n", "body": body} for body in bodies]}),
        encoding="utf-8",
    )


def _skeleton_file(tmp_path: Path, band: str, slug: str, payload: str) -> Path:
    """Write raw text as ``skeletons/<band>/<slug>.json`` under ``tmp_path``.

    Args:
        tmp_path: The temporary working directory.
        band: The age-band directory name.
        slug: The skeleton file stem.
        payload: The exact file text.

    Returns:
        The path written.
    """
    band_dir = tmp_path / "skeletons" / band
    band_dir.mkdir(parents=True, exist_ok=True)
    path = band_dir / f"{slug}.json"
    path.write_text(payload, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# _second_person_rate
# --------------------------------------------------------------------------


def test_second_person_rate_ignores_blank_texts() -> None:
    """Blank entries are excluded from the denominator, not counted as third."""
    assert _second_person_rate(["you go", "   ", ""]) == pytest.approx(1.0)


def test_second_person_rate_is_zero_when_nothing_measurable() -> None:
    """An all-blank list yields 0.0 rather than dividing by zero."""
    assert _second_person_rate(["", "  "]) == pytest.approx(0.0)


# --------------------------------------------------------------------------
# _infer: the four branches, in precedence order
# --------------------------------------------------------------------------


def test_infer_gamebook_convention_wins_over_third_person_beats() -> None:
    """Rule 1 decides first: gamebook style beats an all-third-person beat set."""
    skeleton = _skeleton(
        beats=[_THIRD_BEAT, _THIRD_BEAT],
        metadata={"narrative_style": "gamebook"},
    )
    person, source = _infer(skeleton, "slug", beats_threshold=0.5)
    assert person == "second"
    assert source == "gamebook convention"


def test_infer_beats_threshold_decides_second_before_committed_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 2 outranks rule 3: beats decide even with a third-person fill on disk."""
    monkeypatch.chdir(tmp_path)
    _write_fill(tmp_path, "slug", ["Mira waits.", "Mira runs."])
    skeleton = _skeleton(beats=[_SECOND_BEAT, _SECOND_BEAT])
    person, source = _infer(skeleton, "slug", beats_threshold=0.5)
    assert person == "second"
    assert source == "beats second-person rate 1.00"


def test_infer_committed_fill_decides_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 3 decides ``second`` at or above 0.5 once the beats fall through."""
    monkeypatch.chdir(tmp_path)
    _write_fill(tmp_path, "slug", ["You wait.", "You run.", "Mira waits."])
    skeleton = _skeleton(beats=[_THIRD_BEAT, _THIRD_BEAT])
    person, source = _infer(skeleton, "slug", beats_threshold=0.5)
    assert person == "second"
    assert source == "committed fill second-person rate 0.67"


def test_infer_committed_fill_decides_third(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 3 decides ``third`` below 0.5, the same boundary rule 2 now uses."""
    monkeypatch.chdir(tmp_path)
    _write_fill(tmp_path, "slug", ["You wait.", "Mira runs.", "Mira waits."])
    skeleton = _skeleton(beats=[_THIRD_BEAT, _THIRD_BEAT])
    person, source = _infer(skeleton, "slug", beats_threshold=0.5)
    assert person == "third"
    assert source == "committed fill second-person rate 0.33"


def test_infer_defaults_to_third_without_beats_or_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 4 is the fallback when no earlier rule fires."""
    monkeypatch.chdir(tmp_path)
    person, source = _infer(_skeleton(beats=[]), "slug", beats_threshold=0.5)
    assert person == "third"
    assert source == "prose default"


def test_infer_corrupt_committed_fill_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed committed fill is treated as absent, not as an abort.

    Pins the ``#ASSUME`` on the swallowed ``json.JSONDecodeError`` in ``_infer``.
    """
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "slug.filled.json").write_text("{ not json", encoding="utf-8")
    person, source = _infer(_skeleton(beats=[_THIRD_BEAT]), "slug", beats_threshold=0.5)
    assert person == "third"
    assert source == "prose default"


# --------------------------------------------------------------------------
# The --beats-threshold boundary: it must match check_prose_craft.py's floor
# --------------------------------------------------------------------------


def test_default_beats_threshold_is_half() -> None:
    """The inference boundary equals check_prose_craft's enforcement floor.

    A lower default is the defect this test guards: it would declare ``second``
    on a beats rate that a faithful fill can never lift above 0.5.
    """
    assert _build_parser().parse_args([]).beats_threshold == pytest.approx(0.5)


def test_infer_beats_exactly_at_threshold_is_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A beats rate of exactly 0.5 clears the threshold."""
    monkeypatch.chdir(tmp_path)
    skeleton = _skeleton(
        beats=[_SECOND_BEAT, _SECOND_BEAT, _THIRD_BEAT, _THIRD_BEAT],
    )
    person, source = _infer(skeleton, "slug", beats_threshold=0.5)
    assert person == "second"
    assert source == "beats second-person rate 0.50"


def test_infer_beats_just_below_threshold_is_not_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A beats rate of 0.4 no longer declares ``second``, unlike the old 0.3."""
    monkeypatch.chdir(tmp_path)
    skeleton = _skeleton(
        beats=[_SECOND_BEAT, _SECOND_BEAT, _THIRD_BEAT, _THIRD_BEAT, _THIRD_BEAT],
    )
    person, source = _infer(skeleton, "slug", beats_threshold=0.5)
    assert person == "third"
    assert source == "prose default"
    # The same skeleton under the retired 0.3 default did declare "second".
    assert _infer(skeleton, "slug", beats_threshold=0.3)[0] == "second"


# --------------------------------------------------------------------------
# _insert_person: indentation shapes and every rejection path
# --------------------------------------------------------------------------


def test_insert_person_one_space_indent(tmp_path: Path) -> None:
    """An indent=1 file gets a one-space-indented key and keeps its shape."""
    path = _skeleton_file(
        tmp_path,
        "10-13",
        "one",
        '{\n "metadata": {\n  "age_band": "10-13"\n },\n "nodes": []\n}\n',
    )
    _insert_person(path, "third")
    raw = path.read_text(encoding="utf-8")
    assert '  "narrative_person": "third",\n' in raw
    assert json.loads(raw)["metadata"]["narrative_person"] == "third"
    assert raw.splitlines()[1] == ' "metadata": {'


def test_insert_person_two_space_indent(tmp_path: Path) -> None:
    """An indent=2 file gets a four-space-indented key inside metadata."""
    path = _skeleton_file(
        tmp_path,
        "16+",
        "two",
        '{\n  "metadata": {\n    "age_band": "16+"\n  },\n  "nodes": []\n}\n',
    )
    _insert_person(path, "second")
    raw = path.read_text(encoding="utf-8")
    assert '    "narrative_person": "second",\n' in raw
    assert json.loads(raw)["metadata"]["narrative_person"] == "second"


def test_insert_person_rejects_single_line_metadata_block(tmp_path: Path) -> None:
    """A single-line ``"metadata": {}`` splices outside metadata and is refused.

    The splice would land the key at top level, where the re-parse check finds
    no ``metadata.narrative_person`` and rejects the edit unwritten.
    """
    payload = '{\n  "metadata": {},\n  "nodes": []\n}\n'
    path = _skeleton_file(tmp_path, "8-11", "flat", payload)
    with pytest.raises(ValueError, match="does not carry narrative_person"):
        _insert_person(path, "third")
    assert path.read_text(encoding="utf-8") == payload


def test_insert_person_rejects_nested_metadata_marker(tmp_path: Path) -> None:
    """A node-level ``"metadata": {`` earlier in the file matches first.

    ``str.find`` takes the first occurrence, not the top-level one; the re-parse
    verification is what catches the mis-located splice.
    """
    payload = (
        "{\n"
        ' "nodes": [\n'
        "  {\n"
        '   "id": "n1",\n'
        '   "metadata": {\n'
        '    "note": "x"\n'
        "   }\n"
        "  }\n"
        " ],\n"
        ' "metadata": {\n'
        '  "age_band": "8-11"\n'
        " }\n"
        "}\n"
    )
    path = _skeleton_file(tmp_path, "8-11", "nested", payload)
    with pytest.raises(ValueError, match="does not carry narrative_person"):
        _insert_person(path, "third")
    assert path.read_text(encoding="utf-8") == payload


def test_insert_person_ignores_escaped_marker_text_in_a_body(tmp_path: Path) -> None:
    """A body quoting the marker cannot hijack the splice.

    A raw ``"`` cannot appear inside a JSON string, so an escaped occurrence
    never matches the marker and the real metadata block is still found.
    """
    payload = (
        "{\n"
        ' "nodes": [\n'
        '  {"id": "n1", "body": "the plaque read \\"metadata\\": { and stopped"}\n'
        " ],\n"
        ' "metadata": {\n'
        '  "age_band": "8-11"\n'
        " }\n"
        "}\n"
    )
    path = _skeleton_file(tmp_path, "8-11", "quoted", payload)
    _insert_person(path, "third")
    assert json.loads(path.read_text(encoding="utf-8"))["metadata"] == {
        "narrative_person": "third",
        "age_band": "8-11",
    }


def test_insert_person_rejects_marker_without_trailing_newline(tmp_path: Path) -> None:
    """A marker on the file's last line raises a path-bearing ValueError.

    Pins the ``#EDGE`` guard replacing the unhandled ``str.index`` failure.
    """
    path = _skeleton_file(tmp_path, "5-8", "truncated", '{\n "metadata": {')
    with pytest.raises(ValueError, match="no newline after the metadata marker"):
        _insert_person(path, "third")


def test_insert_person_rejects_file_without_metadata_block(tmp_path: Path) -> None:
    """A file with no metadata marker at all is refused, not spliced blindly."""
    path = _skeleton_file(tmp_path, "5-8", "bare", '{\n "nodes": []\n}\n')
    with pytest.raises(ValueError, match="no multi-line metadata block"):
        _insert_person(path, "third")


def test_insert_person_preserves_crlf_line_endings(tmp_path: Path) -> None:
    """A CRLF checkout keeps CRLF everywhere; only one line is added."""
    lines = ["{", ' "metadata": {', '  "age_band": "5-8"', " }", "}", ""]
    path = _skeleton_file(tmp_path, "5-8", "crlf", "")
    path.write_bytes("\r\n".join(lines).encode("utf-8"))
    before = path.read_bytes()
    _insert_person(path, "third")
    after = path.read_bytes()
    assert after.count(b"\r\n") == before.count(b"\r\n") + 1
    assert after.replace(b"\r\n", b"").count(b"\n") == 0
    assert json.loads(after.decode("utf-8"))["metadata"]["narrative_person"] == "third"


# --------------------------------------------------------------------------
# _replace_person: the --rederive write path
# --------------------------------------------------------------------------


def test_replace_person_rewrites_declared_value(tmp_path: Path) -> None:
    """Only the declaration's value changes; every other line is untouched."""
    payload = (
        "{\n"
        ' "metadata": {\n'
        '  "narrative_person": "second",\n'
        '  "age_band": "10-13"\n'
        " }\n"
        "}\n"
    )
    path = _skeleton_file(tmp_path, "10-13", "declared", payload)
    _replace_person(path, "third")
    after = path.read_text(encoding="utf-8")
    assert after == payload.replace('"second"', '"third"')


def test_replace_person_rejects_missing_declaration(tmp_path: Path) -> None:
    """Rewriting a file with no declaration raises rather than inventing one."""
    path = _skeleton_file(
        tmp_path, "10-13", "none", '{\n "metadata": {\n  "age_band": "10-13"\n }\n}\n'
    )
    with pytest.raises(ValueError, match="no narrative_person declaration"):
        _replace_person(path, "third")


def test_replace_person_rejects_nested_declaration(tmp_path: Path) -> None:
    """A nested declaration matching first is caught by the re-parse check."""
    payload = (
        "{\n"
        ' "nodes": [\n'
        '  {"id": "n1", "metadata": {"narrative_person": "second"}}\n'
        " ],\n"
        ' "metadata": {\n'
        '  "narrative_person": "second"\n'
        " }\n"
        "}\n"
    )
    path = _skeleton_file(tmp_path, "10-13", "nesteddecl", payload)
    with pytest.raises(ValueError, match="does not carry narrative_person"):
        _replace_person(path, "third")
    assert path.read_text(encoding="utf-8") == payload


# --------------------------------------------------------------------------
# main: dry-run safety, skip-and-continue, exit code
# --------------------------------------------------------------------------


def test_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--dry-run`` reports and leaves every file byte-for-byte untouched.

    A regression here turns a report into a catalog rewrite, so both content
    and modification time are asserted unchanged.
    """
    monkeypatch.chdir(tmp_path)
    payload = '{\n "metadata": {\n  "age_band": "8-11"\n },\n "nodes": []\n}\n'
    first = _skeleton_file(tmp_path, "8-11", "alpha", payload)
    second = _skeleton_file(tmp_path, "10-13", "beta", payload)
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (first, second)
    }

    assert main(["--dry-run"]) == 0

    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
    assert "alpha.json: third" in capsys.readouterr().out


def test_main_backfills_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real run inserts the key; a second run leaves the file alone."""
    monkeypatch.chdir(tmp_path)
    path = _skeleton_file(
        tmp_path,
        "8-11",
        "alpha",
        '{\n "metadata": {\n  "age_band": "8-11"\n },\n "nodes": []\n}\n',
    )
    assert main([]) == 0
    after_first = path.read_bytes()
    assert json.loads(after_first)["metadata"]["narrative_person"] == "third"
    assert main([]) == 0
    assert path.read_bytes() == after_first


def test_main_skips_malformed_file_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unparsable file is reported and stepped over; later files still write.

    The sweep must never abort mid-catalog, which would leave the tree
    half-backfilled, contradicting the documented contract.
    """
    monkeypatch.chdir(tmp_path)
    bad = _skeleton_file(tmp_path, "8-11", "aaa-bad", "{ not json at all")
    good = _skeleton_file(
        tmp_path,
        "8-11",
        "zzz-good",
        '{\n "metadata": {\n  "age_band": "8-11"\n },\n "nodes": []\n}\n',
    )

    assert main([]) == 1

    assert bad.read_text(encoding="utf-8") == "{ not json at all"
    assert (
        json.loads(good.read_text(encoding="utf-8"))["metadata"]["narrative_person"]
        == "third"
    )
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "aaa-bad.json" in out


def test_main_skips_unsplittable_file_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file whose splice fails verification is skipped, not raised through."""
    monkeypatch.chdir(tmp_path)
    flat_payload = '{\n "metadata": {},\n "nodes": []\n}\n'
    flat = _skeleton_file(tmp_path, "8-11", "aaa-flat", flat_payload)
    good = _skeleton_file(
        tmp_path,
        "8-11",
        "zzz-good",
        '{\n "metadata": {\n  "age_band": "8-11"\n },\n "nodes": []\n}\n',
    )

    assert main([]) == 1

    assert flat.read_text(encoding="utf-8") == flat_payload
    assert (
        json.loads(good.read_text(encoding="utf-8"))["metadata"]["narrative_person"]
        == "third"
    )
    assert "SKIPPED" in capsys.readouterr().out


def test_main_leaves_declared_skeletons_alone_without_rederive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotence means a rule change does NOT propagate on a plain re-run."""
    monkeypatch.chdir(tmp_path)
    payload = (
        "{\n"
        ' "metadata": {\n'
        '  "narrative_person": "second",\n'
        '  "age_band": "8-11"\n'
        " },\n"
        ' "nodes": []\n'
        "}\n"
    )
    path = _skeleton_file(tmp_path, "8-11", "stale", payload)
    assert main([]) == 0
    assert path.read_text(encoding="utf-8") == payload


def test_main_rederive_rewrites_stale_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--rederive`` re-infers a declared skeleton and rewrites a stale value."""
    monkeypatch.chdir(tmp_path)
    payload = (
        "{\n"
        ' "metadata": {\n'
        '  "narrative_person": "second",\n'
        '  "age_band": "8-11"\n'
        " },\n"
        ' "nodes": [\n'
        f'  {{"id": "n0", "body": "{_THIRD_BEAT}"}}\n'
        " ]\n"
        "}\n"
    )
    path = _skeleton_file(tmp_path, "8-11", "stale", payload)

    assert main(["--rederive"]) == 0

    assert path.read_text(encoding="utf-8") == payload.replace('"second"', '"third"')
    assert "second -> third" in capsys.readouterr().out


def test_main_rederive_leaves_correct_declaration_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--rederive`` rewrites nothing when the committed value already matches."""
    monkeypatch.chdir(tmp_path)
    payload = (
        "{\n"
        ' "metadata": {\n'
        '  "narrative_person": "third",\n'
        '  "age_band": "8-11"\n'
        " },\n"
        ' "nodes": []\n'
        "}\n"
    )
    path = _skeleton_file(tmp_path, "8-11", "fine", payload)
    assert main(["--rederive"]) == 0
    assert path.read_text(encoding="utf-8") == payload


def test_main_ignores_sidecar_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Theme contracts and lineage records share the glob but are not skeletons."""
    monkeypatch.chdir(tmp_path)
    sidecar = _skeleton_file(tmp_path, "8-11", "alpha.contract", '{"theme": "x"}\n')
    assert main([]) == 0
    assert sidecar.read_text(encoding="utf-8") == '{"theme": "x"}\n'
