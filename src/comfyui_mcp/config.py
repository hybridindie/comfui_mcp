"""Configuration management with YAML file + environment variable overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, field_validator

_DEFAULT_CONFIG_PATH = Path.home() / ".comfyui-mcp" / "config.yaml"

_DEFAULT_DANGEROUS_NODES = [
    "ExecuteAnything",
    "EvalNode",
    "ExecNode",
    "PythonExec",
    "RunPython",
    "ShellNode",
    "CommandExecutor",
    "PythonCode",
    "PythonScript",
    "ExecPython",
    "ExecutePython",
    "PythonRunner",
    "AdvancedPython",
    "PythonFunction",
    "SimplePython",
    "FN_pyeval",
    "PyFunctional",
    "PyTorchLayer",
    "TensorFlowOp",
]

_DEFAULT_ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".json"]


class ComfyUISettings(BaseModel):
    url: str = "http://127.0.0.1:8188"
    tls_verify: bool = True
    timeout_connect: int = 30
    timeout_read: int = 300
    max_workflow_size_mb: int = 10
    max_prompt_length: int = 10000

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must use http or https")
        if not parsed.netloc:
            raise ValueError("URL must have a valid host")
        return v


class SecuritySettings(BaseModel):
    mode: Literal["audit", "enforce"] = "audit"
    allowed_nodes: list[str] = []
    dangerous_nodes: list[str] = list(_DEFAULT_DANGEROUS_NODES)
    max_upload_size_mb: int = 50
    allowed_extensions: list[str] = list(_DEFAULT_ALLOWED_EXTENSIONS)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("audit", "enforce"):
            raise ValueError(
                f"Invalid security mode: {v!r}. Must be 'audit' or 'enforce'."
            )
        return v

    @field_validator("max_upload_size_mb")
    @classmethod
    def validate_max_upload_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_upload_size_mb must be at least 1")
        if v > 500:
            raise ValueError("max_upload_size_mb must not exceed 500")
        return v


class RateLimitSettings(BaseModel):
    workflow: int = 10
    generation: int = 10
    file_ops: int = 30
    read_only: int = 60


class LoggingSettings(BaseModel):
    level: str = "INFO"
    audit_file: str = "~/.comfyui-mcp/audit.log"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Level must be one of {valid_levels}")
        return v.upper()


class SSESettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8080


class TransportSettings(BaseModel):
    stdio: bool = True
    sse: SSESettings = SSESettings()


class Settings(BaseModel):
    comfyui: ComfyUISettings = ComfyUISettings()
    security: SecuritySettings = SecuritySettings()
    rate_limits: RateLimitSettings = RateLimitSettings()
    logging: LoggingSettings = LoggingSettings()
    transport: TransportSettings = TransportSettings()


def _apply_env_overrides(data: dict) -> dict:
    """Apply environment variable overrides."""
    env_map = {
        "COMFYUI_URL": ("comfyui", "url"),
        "COMFYUI_TLS_VERIFY": ("comfyui", "tls_verify"),
        "COMFYUI_TIMEOUT_CONNECT": ("comfyui", "timeout_connect"),
        "COMFYUI_TIMEOUT_READ": ("comfyui", "timeout_read"),
        "COMFYUI_SECURITY_MODE": ("security", "mode"),
        "COMFYUI_LOG_LEVEL": ("logging", "level"),
        "COMFYUI_AUDIT_FILE": ("logging", "audit_file"),
    }
    for env_var, path in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            section, key = path
            if section not in data:
                data[section] = {}
            if key in ("timeout_connect", "timeout_read"):
                data[section][key] = int(value)
            elif key == "tls_verify":
                data[section][key] = value.lower() in ("true", "1", "yes")
            else:
                data[section][key] = value
    return data


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML file with environment variable overrides."""
    path = config_path or _DEFAULT_CONFIG_PATH
    data: dict = {}

    if path.exists():
        with open(path) as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                data = loaded

    data = _apply_env_overrides(data)
    return Settings(**data)
