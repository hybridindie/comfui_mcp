"""Tests for configuration loading."""

import pytest
import yaml

from comfyui_mcp.config import (
    SecuritySettings,
    Settings,
    load_settings,
)


class TestSettingsDefaults:
    def test_default_comfyui_url(self):
        s = Settings()
        assert s.comfyui.url == "http://127.0.0.1:8188"

    def test_default_security_mode(self):
        s = Settings()
        assert s.security.mode == "audit"

    def test_default_rate_limits(self):
        s = Settings()
        assert s.rate_limits.workflow == 10
        assert s.rate_limits.read_only == 60

    def test_default_transport_sse_disabled(self):
        s = Settings()
        assert s.transport.sse.enabled is False

    def test_dangerous_nodes_default(self):
        s = Settings()
        assert len(s.security.dangerous_nodes) > 0

    def test_allowed_extensions_default(self):
        s = Settings()
        assert ".png" in s.security.allowed_extensions


class TestSettingsFromYAML:
    def test_load_from_yaml(self, tmp_path):
        config = {
            "comfyui": {
                "url": "https://gpu-server:8188",
            },
            "security": {"mode": "enforce"},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config))

        settings = load_settings(config_path=config_file)
        assert settings.comfyui.url == "https://gpu-server:8188"
        assert settings.security.mode == "enforce"

    def test_missing_yaml_uses_defaults(self, tmp_path):
        settings = load_settings(config_path=tmp_path / "nonexistent.yaml")
        assert settings.comfyui.url == "http://127.0.0.1:8188"


class TestSettingsEnvOverrides:
    def test_env_overrides_url(self, monkeypatch):
        monkeypatch.setenv("COMFYUI_URL", "https://env-server:8188")
        settings = load_settings()
        assert settings.comfyui.url == "https://env-server:8188"

    def test_env_overrides_security_mode(self, monkeypatch):
        monkeypatch.setenv("COMFYUI_SECURITY_MODE", "enforce")
        settings = load_settings()
        assert settings.security.mode == "enforce"


class TestSecurityModeValidation:
    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError):
            SecuritySettings(mode="invalid")

    def test_enforce_mode_accepted(self):
        s = SecuritySettings(mode="enforce")
        assert s.mode == "enforce"
