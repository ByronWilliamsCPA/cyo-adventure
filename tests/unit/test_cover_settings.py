"""Cover-related settings load from env with sane defaults."""

import pytest

from cyo_adventure.core.config import Settings

pytestmark = pytest.mark.unit


def test_defaults() -> None:
    s = Settings()
    assert s.r2_bucket == "covers"
    assert s.cover_model == "gemini-3-pro-image"
    assert s.cover_max_width == 800
    assert s.cover_max_bytes == 256_000
    assert s.covers_backup_dir is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "svc")
    monkeypatch.setenv("R2_BUCKET", "custom-covers")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://images.example.com")
    s = Settings()
    assert s.gemini_api_key == "g"
    assert s.r2_account_id == "acct123"
    assert s.r2_access_key_id == "AKIDEXAMPLE"
    assert s.r2_secret_access_key == "svc"
    assert s.r2_bucket == "custom-covers"
    assert s.r2_public_base_url == "https://images.example.com"
