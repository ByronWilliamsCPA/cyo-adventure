"""Unit tests for scripts/check_env_boots.py (no network, no database).

Each test writes an env file and runs the preflight against it in isolation,
so the developer's own shell never leaks in. The secrets below are planted in
failing settings on purpose: the output must name every broken rule and never
any value.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_env_boots",
    Path(__file__).resolve().parents[2] / "scripts" / "check_env_boots.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = script
_SPEC.loader.exec_module(script)

pytestmark = pytest.mark.unit

_DB_PASSWORD = "Sup3rS3cretDbPw"
_KWS_KEY = "kws-api-key-planted-secret"
_KWS_CLIENT = "kws-client-planted-id"

# Mirrors the 2026-08-12 outage shape plus three more independent breaks: a
# pooler DSN without the cache flag, OIDC half-set, and a partial KWS set.
_BROKEN_ENV = f"""
ENVIRONMENT=production
CYO_ADVENTURE_DATABASE_URL=postgresql+asyncpg://cyo:{_DB_PASSWORD}@pooler.example:6543/postgres
OIDC_ISSUER=https://issuer.example/auth/v1
KWS_CLIENT_ID={_KWS_CLIENT}
KWS_API_KEY={_KWS_KEY}
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "test.env"
    path.write_text(body)
    return path


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = script.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


class TestEnvFile:
    def test_reports_every_broken_rule_in_one_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(capsys, str(_write(tmp_path, _BROKEN_ENV)), "--json")
        report = json.loads(out)
        rules = {f["rule"] for f in report["failures"]}

        assert code == 1
        assert report["boots"] is False
        assert {
            "_require_prepared_cache_disabled_for_pooler_dsn",
            "_require_oidc_config_outside_local",
            "_require_kws_credentials_together",
            "_require_child_session_secret_outside_local",
        } <= rules
        assert report["cross_check_problem"] is None

    def test_names_settings_and_never_prints_a_value(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = _write(tmp_path, _BROKEN_ENV)
        _, text = _run(capsys, str(env), "--integrations")
        _, as_json = _run(capsys, str(env), "--json", "--integrations")

        for out in (text, as_json):
            for secret in (_DB_PASSWORD, _KWS_KEY, _KWS_CLIENT, "pooler.example"):
                assert secret not in out
        kws = next(
            f
            for f in json.loads(as_json)["failures"]
            if f["rule"] == "_require_kws_credentials_together"
        )
        assert "KWS_API_ORIGIN" in kws["settings"]

    def test_field_errors_are_named_without_input(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = _write(tmp_path, "ENVIRONMENT=prod-typo-secretish\nLOG_LEVEL=LOUD\n")
        code, out = _run(capsys, str(env), "--json")
        report = json.loads(out)
        settings = {s for f in report["failures"] for s in f["settings"]}

        assert code == 1
        assert {f["kind"] for f in report["failures"]} == {"field"}
        assert "ENVIRONMENT" in settings
        assert "prod-typo-secretish" not in out
        assert "LOUD" not in out

    def test_empty_file_boots_as_local_and_lists_integrations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(capsys, str(_write(tmp_path, "")), "--json", "--integrations")
        report = json.loads(out)
        assert code == 0
        assert report["boots"] is True
        names = {i["name"]: i["configured"] for i in report["integrations"]}
        assert names["Modal generation leg"] is False
        assert names["Supabase service-role key (auth identity erasure)"] is False

    def test_integrations_are_listed_even_when_a_rule_refuses_the_boot(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = _BROKEN_ENV + "SUPABASE_SERVICE_ROLE_KEY=service-role-secret\n"
        _, out = _run(capsys, str(_write(tmp_path, body)), "--json", "--integrations")
        report = json.loads(out)
        names = {i["name"]: i["configured"] for i in report["integrations"]}
        assert names["Supabase service-role key (auth identity erasure)"] is True
        assert "service-role-secret" not in out

    def test_unparseable_dsn_is_a_boot_failure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = f"CYO_ADVENTURE_DATABASE_URL=notadsn://x:{_DB_PASSWORD}@h/d\n"
        code, out = _run(capsys, str(_write(tmp_path, body)), "--json")
        report = json.loads(out)
        assert code == 1
        assert [f["rule"] for f in report["failures"]] == ["engine_construction"]
        assert _DB_PASSWORD not in out

    def test_file_is_evaluated_in_isolation_from_the_shell(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A broken variable in the caller's shell must not leak into a file run."""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            code, _ = _run(capsys, str(_write(tmp_path, "")))
        assert code == 0

    def test_missing_file_is_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(capsys, str(tmp_path / "nope.env"))
        assert code == 2
        assert "not found" in out


class TestCurrentEnvironment:
    def test_current_environment_is_used_without_a_file(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=True):
            code, out = _run(capsys)
        assert code == 1
        assert "_require_oidc_config_outside_local" in out


class TestScrubber:
    def test_longest_secret_is_replaced_first_and_vocabulary_is_kept(self) -> None:
        scrub = script.make_scrubber(["abcd", "abcdef", "production", "true", "8000"])
        assert scrub("x abcdef y abcd z") == "x <redacted> y <redacted> z"
        assert scrub("environment is 'production', debug true, port 8000") == (
            "environment is 'production', debug true, port 8000"
        )


class TestCrossCheck:
    def test_disagreement_with_full_settings_is_reported_and_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """If the one-by-one model misses a rule Settings() enforces, say so."""
        settings_cls = script._load_settings_class()

        class _StricterSettings(settings_cls):
            def __init__(self, **kwargs: object) -> None:
                if type(self) is _StricterSettings:
                    msg = "hidden rule"
                    raise ValueError(msg)
                super().__init__(**kwargs)

        with patch.object(
            script, "_load_settings_class", return_value=_StricterSettings
        ):
            code, out = _run(capsys, str(_write(tmp_path, "")), "--json")
        report = json.loads(out)
        assert code == 1
        assert report["boots"] is False
        assert "cannot attribute" in report["cross_check_problem"]
