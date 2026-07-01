"""Unit tests for the skeleton-diagram generator script core."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.render_skeleton_diagrams as rsd
from scripts.render_skeleton_diagrams import (
    check_outputs,
    generate_puml,
    render_svgs,
    slug_for,
    verify_sha256,
    write_outputs,
)

_HELLO_SHA256 = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def _write_skeleton(root: Path) -> Path:
    # Minimal valid 3-5 skeleton satisfying all gate constraints:
    #   - 8 nodes (band min_nodes=8)
    #   - 2 endings (band min_endings=2)
    #   - 1 decision node with >=2 choices (band min_decisions=1)
    #   - pure branching tree, acyclic, no reconvergence => time_cave topology
    #   - all nodes reachable from n_start
    # Graph: n_start -[left]-> n_a -> n_a1 -> n_a2 -> n_end_a
    #        n_start -[right]-> n_b -> n_b1 -> n_b2 -> n_end_b
    # (8 nodes total; start is the single decision node)
    skel = {
        "schema_version": "2.0",
        "id": "sk_demo_diagram",
        "version": 1,
        "title": "Demo Diagram",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 2,
            "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
            "topology": "time_cave",
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "<<FILL role=setup words=85 beats='start'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_a", "label": "Go left.", "target": "n_a"},
                    {"id": "c_b", "label": "Go right.", "target": "n_b"},
                ],
            },
            {
                "id": "n_a",
                "body": "<<FILL role=rising words=75 beats='left'>>",
                "is_ending": False,
                "choices": [{"id": "c_a1", "label": "Continue.", "target": "n_a1"}],
            },
            {
                "id": "n_a1",
                "body": "<<FILL role=rising words=75 beats='left mid'>>",
                "is_ending": False,
                "choices": [{"id": "c_a2", "label": "Finish.", "target": "n_end_a"}],
            },
            {
                "id": "n_end_a",
                "body": "<<FILL role=completion words=75 beats='done left'>>",
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "End A",
                },
            },
            {
                "id": "n_b",
                "body": "<<FILL role=rising words=75 beats='right'>>",
                "is_ending": False,
                "choices": [{"id": "c_b1", "label": "Continue.", "target": "n_b1"}],
            },
            {
                "id": "n_b1",
                "body": "<<FILL role=rising words=75 beats='right mid'>>",
                "is_ending": False,
                "choices": [{"id": "c_b2", "label": "Continue.", "target": "n_b2"}],
            },
            {
                "id": "n_b2",
                "body": "<<FILL role=choice words=75 beats='right late'>>",
                "is_ending": False,
                "choices": [{"id": "c_bend", "label": "Finish.", "target": "n_end_b"}],
            },
            {
                "id": "n_end_b",
                "body": "<<FILL role=completion words=75 beats='done right'>>",
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End B",
                },
            },
        ],
    }
    band_dir = root / "3-5"
    band_dir.mkdir(parents=True)
    path = band_dir / "demo-diagram.json"
    path.write_text(json.dumps(skel), encoding="utf-8")
    return path


@pytest.mark.unit
def test_slug_for_uses_filename_stem() -> None:
    assert slug_for(Path("skeletons/3-5/the-lost-mitten.json")) == "the-lost-mitten"


@pytest.mark.unit
def test_generate_puml_maps_band_relative_output_paths(tmp_path: Path) -> None:
    skeletons = tmp_path / "skeletons"
    _write_skeleton(skeletons)
    out_root = tmp_path / "out"
    mapping = generate_puml(skeletons, out_root)
    expected = out_root / "3-5" / "demo-diagram.puml"
    assert expected in mapping
    assert mapping[expected].startswith("@startuml")
    assert "[*] --> n_start" in mapping[expected]


@pytest.mark.unit
def test_write_outputs_writes_files(tmp_path: Path) -> None:
    target = tmp_path / "out" / "3-5" / "demo-diagram.puml"
    write_outputs({target: "@startuml x\n@enduml\n"})
    assert target.read_text(encoding="utf-8") == "@startuml x\n@enduml\n"


# ---------------------------------------------------------------------------
# check_outputs unit tests (carry-forward from Task 4 review)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_outputs_missing_file_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "missing.puml"
    stale = check_outputs({path: "@startuml x\n@enduml\n"})
    assert path in stale


@pytest.mark.unit
def test_check_outputs_different_content_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "old.puml"
    path.write_text("@startuml old\n@enduml\n", encoding="utf-8")
    stale = check_outputs({path: "@startuml new\n@enduml\n"})
    assert path in stale


@pytest.mark.unit
def test_check_outputs_matching_content_not_stale(tmp_path: Path) -> None:
    path = tmp_path / "current.puml"
    content = "@startuml x\n@enduml\n"
    path.write_text(content, encoding="utf-8")
    stale = check_outputs({path: content})
    assert path not in stale


# ---------------------------------------------------------------------------
# verify_sha256 and render_svgs tests (Task 5)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_verify_sha256_matches_known_digest(tmp_path: Path) -> None:
    blob = tmp_path / "x.jar"
    blob.write_bytes(b"hello")
    # sha256("hello")
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert verify_sha256(blob, expected) is True


@pytest.mark.unit
def test_verify_sha256_rejects_mismatch(tmp_path: Path) -> None:
    blob = tmp_path / "x.jar"
    blob.write_bytes(b"hello")
    assert verify_sha256(blob, "0" * 64) is False


@pytest.mark.unit
def test_render_svgs_skips_gracefully_without_jar(tmp_path: Path) -> None:
    puml = tmp_path / "a.puml"
    puml.write_text("@startuml a\n@enduml\n", encoding="utf-8")
    # jar=None means "unavailable"; must return [] and not raise.
    assert render_svgs([puml], jar=None) == []


@pytest.mark.unit
def test_check_outputs_returns_only_stale_in_mixed_mapping(tmp_path: Path) -> None:
    fresh_content = "@startuml fresh\n@enduml\n"
    fresh_path = tmp_path / "fresh.puml"
    fresh_path.write_text(fresh_content, encoding="utf-8")

    stale_path = tmp_path / "stale.puml"
    # stale_path does not exist on disk

    mapping = {fresh_path: fresh_content, stale_path: "@startuml stale\n@enduml\n"}
    result = check_outputs(mapping)

    assert stale_path in result
    assert fresh_path not in result


# ---------------------------------------------------------------------------
# resolve_jar tests (follow-up to PR #37 review: no branch had coverage)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_jar_env_var_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLANTUML_JAR", str(tmp_path / "nope.jar"))
    assert rsd.resolve_jar() is None


@pytest.mark.unit
def test_resolve_jar_env_var_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jar = tmp_path / "x.jar"
    jar.write_bytes(b"not the real jar")
    monkeypatch.setenv("PLANTUML_JAR", str(jar))
    assert rsd.resolve_jar() is None
    assert "failed SHA-256 verification" in capsys.readouterr().err


@pytest.mark.unit
def test_resolve_jar_env_var_valid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jar = tmp_path / "x.jar"
    jar.write_bytes(b"hello")
    monkeypatch.setenv("PLANTUML_JAR", str(jar))
    monkeypatch.setattr(rsd, "PLANTUML_SHA256", _HELLO_SHA256)
    assert rsd.resolve_jar() == jar


@pytest.mark.unit
def test_resolve_jar_uses_valid_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PLANTUML_JAR", raising=False)
    cache = tmp_path / "cache.jar"
    cache.write_bytes(b"hello")
    monkeypatch.setattr(rsd, "JAR_CACHE", cache)
    monkeypatch.setattr(rsd, "PLANTUML_SHA256", _HELLO_SHA256)
    assert rsd.resolve_jar() == cache


@pytest.mark.unit
def test_resolve_jar_corrupted_cache_falls_through_to_redownload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PLANTUML_JAR", raising=False)
    cache = tmp_path / "cache.jar"
    cache.write_bytes(b"corrupted")
    monkeypatch.setattr(rsd, "JAR_CACHE", cache)
    monkeypatch.setattr(rsd, "PLANTUML_SHA256", _HELLO_SHA256)

    def fake_urlretrieve(_url: str, dest: Path) -> None:
        Path(dest).write_bytes(b"hello")

    monkeypatch.setattr(rsd.urllib.request, "urlretrieve", fake_urlretrieve)
    assert rsd.resolve_jar() == cache
    assert "attempting a fresh download" in capsys.readouterr().err


@pytest.mark.unit
def test_resolve_jar_download_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PLANTUML_JAR", raising=False)
    monkeypatch.setattr(rsd, "JAR_CACHE", tmp_path / "cache" / "cache.jar")

    def fake_urlretrieve(_url: str, _dest: Path) -> None:
        raise OSError("network down")

    monkeypatch.setattr(rsd.urllib.request, "urlretrieve", fake_urlretrieve)
    assert rsd.resolve_jar() is None
    assert "Could not download" in capsys.readouterr().err


@pytest.mark.unit
def test_resolve_jar_post_download_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PLANTUML_JAR", raising=False)
    monkeypatch.setattr(rsd, "JAR_CACHE", tmp_path / "cache" / "cache.jar")

    def fake_urlretrieve(_url: str, dest: Path) -> None:
        Path(dest).write_bytes(b"wrong content")

    monkeypatch.setattr(rsd.urllib.request, "urlretrieve", fake_urlretrieve)
    assert rsd.resolve_jar() is None
    assert "Downloaded jar failed SHA-256 verification" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# render_svgs exception-handling tests (follow-up to PR #37 review)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_svgs_missing_java_binary_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    puml = tmp_path / "a.puml"
    puml.write_text("@startuml a\n@enduml\n", encoding="utf-8")
    jar = tmp_path / "x.jar"
    jar.write_bytes(b"hello")

    def fake_run(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("java")

    monkeypatch.setattr(rsd.subprocess, "run", fake_run)
    assert render_svgs([puml], jar=jar) == []
    assert "java executable not found" in capsys.readouterr().err


@pytest.mark.unit
def test_render_svgs_render_failure_skips_file_and_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    puml_bad = tmp_path / "bad.puml"
    puml_bad.write_text("@startuml bad\n@enduml\n", encoding="utf-8")
    puml_good = tmp_path / "good.puml"
    puml_good.write_text("@startuml good\n@enduml\n", encoding="utf-8")
    jar = tmp_path / "x.jar"
    jar.write_bytes(b"hello")

    def fake_run(cmd: list[str], **_kwargs: object) -> None:
        target = Path(cmd[-1])
        if target.name == "bad.puml":
            raise subprocess.CalledProcessError(1, cmd, stderr=b"boom")
        target.with_suffix(".svg").write_text("<svg/>", encoding="utf-8")

    monkeypatch.setattr(rsd.subprocess, "run", fake_run)
    result = render_svgs([puml_bad, puml_good], jar=jar)
    assert result == [puml_good.with_suffix(".svg")]
    assert "PlantUML failed to render" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main(--check) drift-guard tests (follow-up to PR #37 review: the
# "cannot silently drift" claim had zero coverage of its failure path)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_main_check_mode_reports_stale_files_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeletons = tmp_path / "skeletons"
    _write_skeleton(skeletons)
    out_root = tmp_path / "out"
    catalog = tmp_path / "catalog.md"
    catalog.write_text("# doc\n", encoding="utf-8")

    exit_code = rsd.main(
        [
            "--check",
            "--skeletons-dir",
            str(skeletons),
            "--out-dir",
            str(out_root),
            "--catalog",
            str(catalog),
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "Stale skeleton diagrams" in err
    assert "demo-diagram.puml" in err


@pytest.mark.unit
def test_main_check_mode_passes_when_up_to_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeletons = tmp_path / "skeletons"
    _write_skeleton(skeletons)
    out_root = tmp_path / "out"
    catalog = tmp_path / "catalog.md"
    catalog.write_text("# doc\n", encoding="utf-8")

    write_exit = rsd.main(
        [
            "--skeletons-dir",
            str(skeletons),
            "--out-dir",
            str(out_root),
            "--catalog",
            str(catalog),
            "--no-svg",
        ]
    )
    assert write_exit == 0

    check_exit = rsd.main(
        [
            "--check",
            "--skeletons-dir",
            str(skeletons),
            "--out-dir",
            str(out_root),
            "--catalog",
            str(catalog),
        ]
    )
    assert check_exit == 0
    assert "up to date" in capsys.readouterr().out
