"""Tests for `politicoresto_mcp.config`."""

from __future__ import annotations

import pytest

from politicoresto_mcp.config import (
    PROD_OVERRIDE_VALUE,
    PROD_PROJECT_REF,
    STAGING_PROJECT_REF,
    ConfigError,
    Settings,
    _extract_project_ref,
    load_settings,
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "SUPABASE_PROJECT_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "POLITICORESTO_ALLOW_PROD",
    ):
        monkeypatch.delenv(k, raising=False)


class TestExtractProjectRef:
    def test_staging_url(self) -> None:
        assert (
            _extract_project_ref(f"https://{STAGING_PROJECT_REF}.supabase.co")
            == STAGING_PROJECT_REF
        )

    def test_prod_url(self) -> None:
        assert _extract_project_ref(f"https://{PROD_PROJECT_REF}.supabase.co") == PROD_PROJECT_REF

    def test_trailing_path_is_ignored(self) -> None:
        assert _extract_project_ref("https://abc123.supabase.co/anything") == "abc123"

    def test_non_supabase_host_rejected(self) -> None:
        with pytest.raises(ConfigError, match="Invalid Supabase URL"):
            _extract_project_ref("https://example.com")

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(ConfigError):
            _extract_project_ref("")


class TestLoadSettings:
    def test_happy_staging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_PROJECT_URL", f"https://{STAGING_PROJECT_REF}.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk_test")
        settings = load_settings(load_dotenv_file=False)
        assert isinstance(settings, Settings)
        assert settings.project_ref == STAGING_PROJECT_REF
        assert settings.is_staging is True
        assert settings.is_prod is False
        assert settings.rest_url.endswith("/rest/v1")

    def test_missing_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk_test")
        with pytest.raises(ConfigError, match="SUPABASE_PROJECT_URL is required"):
            load_settings(load_dotenv_file=False)

    def test_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_PROJECT_URL", f"https://{STAGING_PROJECT_REF}.supabase.co")
        with pytest.raises(ConfigError, match="SUPABASE_SERVICE_ROLE_KEY is required"):
            load_settings(load_dotenv_file=False)

    def test_invalid_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_PROJECT_URL", "https://notsupabase.com")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk_test")
        with pytest.raises(ConfigError, match="Invalid Supabase URL"):
            load_settings(load_dotenv_file=False)

    def test_prod_without_override_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_PROJECT_URL", f"https://{PROD_PROJECT_REF}.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk_test")
        with pytest.raises(ConfigError, match="Refusing to start"):
            load_settings(load_dotenv_file=False)

    def test_prod_with_override_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_PROJECT_URL", f"https://{PROD_PROJECT_REF}.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk_test")
        monkeypatch.setenv("POLITICORESTO_ALLOW_PROD", PROD_OVERRIDE_VALUE)
        settings = load_settings(load_dotenv_file=False)
        assert settings.is_prod is True
        assert settings.is_staging is False

    def test_prod_with_wrong_override_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("SUPABASE_PROJECT_URL", f"https://{PROD_PROJECT_REF}.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk_test")
        monkeypatch.setenv("POLITICORESTO_ALLOW_PROD", "yes")  # wrong value
        with pytest.raises(ConfigError):
            load_settings(load_dotenv_file=False)

    def test_strips_whitespace_and_trailing_slash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv(
            "SUPABASE_PROJECT_URL",
            f"  https://{STAGING_PROJECT_REF}.supabase.co/  ",
        )
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "  sk_test  ")
        settings = load_settings(load_dotenv_file=False)
        assert settings.supabase_url.endswith(".supabase.co")
        assert not settings.supabase_url.endswith("/")
        assert settings.service_role_key == "sk_test"
