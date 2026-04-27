"""
Единый источник конфигурации из .env переменных окружения.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings

_FORBIDDEN_PASSWORDS = {
    "change_me_to_strong_password",
    "password",
    "admin",
    "123456",
}

_FORBIDDEN_PATH_PREFIXES = (
    "/etc", "/proc", "/sys", "/dev", "/var/log", "/var/run",
    "/boot", "/root", "/usr/sbin",
)


class Settings(BaseSettings):
    model_config = {
        "env_file": None,  # Controlled at instantiation: Settings(_env_file=".env")
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    AUTH_USERNAME: str
    AUTH_PASSWORD: SecretStr
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])
    MAX_UPLOAD_SIZE_MB: int = Field(default=50, ge=1, le=200)
    MAX_TOTAL_UPLOAD_MB: int = Field(default=500, ge=1, le=2000)
    MAX_FILES_PER_UPLOAD: int = Field(default=20, ge=1, le=50)
    FILE_TTL_HOURS: int = Field(default=24, ge=1)
    TOKEN_TTL_HOURS: int = Field(default=24, ge=1)
    UPLOAD_DIR: str = "/app/data/uploads"
    PREVIEW_DIR: str = "/app/data/previews"
    RESULT_DIR: str = "/app/data/results"
    PRESETS_PATH: str = "/app/data/presets.json"
    MAX_CONCURRENT_JOBS: int = Field(default=5, ge=1)
    CLEANUP_INTERVAL_HOURS: int = Field(default=6, ge=1)
    PREVIEW_MAX_SIZE: int = Field(default=800, ge=100)
    JOB_TIMEOUT_SECONDS: int = Field(default=600, ge=10, le=3600)
    MAX_IMAGE_PIXELS: int = Field(default=25_000_000, ge=1_000_000, le=100_000_000)

    @field_validator("AUTH_PASSWORD")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        plain = v.get_secret_value()
        if len(plain) < 12:
            raise ValueError("Password must be at least 12 characters")
        if plain.lower() in _FORBIDDEN_PASSWORDS:
            raise ValueError("Template/weak password is not allowed")
        return v

    @model_validator(mode="after")
    def validate_cors_and_paths(self) -> "Settings":
        # CORS wildcard check
        if "*" in self.CORS_ORIGINS:
            raise ValueError("CORS wildcard '*' is not allowed with credentials")

        # Path validation
        for attr_name in ("UPLOAD_DIR", "PREVIEW_DIR", "RESULT_DIR"):
            path_val = getattr(self, attr_name)
            self._validate_safe_path(path_val, attr_name)

        self._validate_safe_path(self.PRESETS_PATH, "PRESETS_PATH")

        return self

    @staticmethod
    def _validate_safe_path(path_str: str, name: str) -> None:
        resolved = Path(path_str).resolve()
        resolved_str = str(resolved)
        # Check forbidden prefixes
        for prefix in _FORBIDDEN_PATH_PREFIXES:
            if resolved_str == prefix or resolved_str.startswith(prefix + "/"):
                raise ValueError(
                    f"{name}={path_str} resolves to forbidden path {resolved_str}"
                )
        # Check if path is absolute and goes outside allowed areas
        # Allow /tmp, /private/tmp (macOS), /app, /home, /data, /Users
        allowed_roots = ("/tmp", "/private/tmp", "/app", "/home", "/data", "/Users")
        if resolved_str.startswith("/"):
            if not any(resolved_str.startswith(r) for r in allowed_roots):
                raise ValueError(
                    f"{name}={path_str} resolves to disallowed location {resolved_str}"
                )
