"""Cover-related settings load from env with sane defaults."""

import pytest

from cyo_adventure.core.config import Settings

pytestmark = pytest.mark.unit


def test_defaults() -> None:
    s = Settings()
    assert s.covers_bucket == "covers"
    assert s.cover_model == "gemini-3-pro-image"
    assert s.cover_max_width == 800
    assert s.cover_max_bytes == 256_000
    assert s.covers_backup_dir is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    monkeypatch.setenv("SUPABASE_URL", "https://p.supabase.co")
    s = Settings()
    assert s.gemini_api_key == "g"
    assert s.supabase_service_key == "svc"
    assert s.supabase_url == "https://p.supabase.co"
