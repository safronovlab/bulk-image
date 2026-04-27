"""
Доменные модели данных проекта.
Единый источник истины для типов. Все модели — Pydantic BaseModel с frozen=True.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Optional
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ──────────────────────────────────────────────
# HEX regex pattern
# ──────────────────────────────────────────────
_HEX_PATTERN = r"^#[0-9A-Fa-f]{6}$"


def _validate_hex(v: str) -> str:
    if not re.match(_HEX_PATTERN, v):
        raise ValueError(f"Invalid HEX color: {v}")
    return v


# ──────────────────────────────────────────────
# SSRF validation helper
# ──────────────────────────────────────────────
_PRIVATE_IP_PATTERNS = [
    re.compile(r"^10\."),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."),
    re.compile(r"^192\.168\."),
    re.compile(r"^169\.254\."),
    re.compile(r"^127\."),
]


def _validate_source_image_url(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if len(v) > 2048:
        raise ValueError("URL exceeds maximum length of 2048 characters")
    parsed = urlparse(v)
    if parsed.scheme != "https":
        raise ValueError("Only https:// URLs are allowed")
    hostname = parsed.hostname or ""
    if hostname == "localhost":
        raise ValueError("localhost is not allowed")
    # Check IPv6-mapped addresses
    if hostname.startswith("["):
        raise ValueError("IPv6-mapped addresses are not allowed")
    if "::ffff:" in hostname.lower():
        raise ValueError("IPv6-mapped addresses are not allowed")
    # Check private IP ranges
    for pattern in _PRIVATE_IP_PATTERNS:
        if pattern.match(hostname):
            raise ValueError(f"Private IP address {hostname} is not allowed")
    return v


# ──────────────────────────────────────────────
# Preset name validation helper
# ──────────────────────────────────────────────
def _validate_preset_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty after trimming whitespace")
    if len(v) > 100:
        raise ValueError("Name must be 100 characters or less")
    # Check for control characters (< 0x20), DEL (0x7f), RTL/LTR overrides
    for ch in v:
        code = ord(ch)
        if code < 0x20:
            raise ValueError("Control characters are not allowed in name")
        if code == 0x7F:
            raise ValueError("DEL character is not allowed in name")
        if 0x202A <= code <= 0x202E:
            raise ValueError("RTL/LTR override characters are not allowed in name")
    return v


# ──────────────────────────────────────────────
# 2.22 JobStatusEnum
# ──────────────────────────────────────────────
class JobStatusEnum(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ──────────────────────────────────────────────
# 2.1 ColorRGB
# ──────────────────────────────────────────────
class ColorRGB(BaseModel):
    model_config = ConfigDict(frozen=True)

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


# ──────────────────────────────────────────────
# 2.2 ColorLAB
# ──────────────────────────────────────────────
class ColorLAB(BaseModel):
    model_config = ConfigDict(frozen=True)

    l: float = Field(ge=0.0, le=100.0)
    a: float = Field(ge=-128.0, le=127.0)
    b_channel: float = Field(ge=-128.0, le=127.0)


# ──────────────────────────────────────────────
# 2.3 ColorInfo
# ──────────────────────────────────────────────
class ColorInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    hex: str
    rgb: ColorRGB
    lab: ColorLAB

    @field_validator("hex")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        return _validate_hex(v)


# ──────────────────────────────────────────────
# 2.4 DominantColor
# ──────────────────────────────────────────────
class DominantColor(BaseModel):
    model_config = ConfigDict(frozen=True)

    hex: str
    rgb: ColorRGB
    percentage: float = Field(ge=0.0, le=100.0)

    @field_validator("hex")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        return _validate_hex(v)


# ──────────────────────────────────────────────
# 2.5 ColorMapping
# ──────────────────────────────────────────────
class ColorMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_hex: str
    to_hex: str

    @field_validator("from_hex", "to_hex")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        return _validate_hex(v)


# ──────────────────────────────────────────────
# 2.6 MappingSuggestion
# ──────────────────────────────────────────────
class MappingSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_hex: str
    to_hex: str
    delta_e: float
    confidence: float = Field(ge=0.0, le=1.0)
    from_percentage: float

    @field_validator("from_hex", "to_hex")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        return _validate_hex(v)


# ──────────────────────────────────────────────
# 2.7 Variation
# ──────────────────────────────────────────────
class Variation(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(default="recolored", min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    color_mappings: list[ColorMapping] = Field(min_length=1, max_length=50)
    tolerance: int = Field(default=25, ge=0, le=100)


# ──────────────────────────────────────────────
# 2.8 JobTask
# ──────────────────────────────────────────────
class JobTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_id: str
    variations: list[Variation] = Field(min_length=1, max_length=10)


# ──────────────────────────────────────────────
# 2.9 JobCreateRequestA
# ──────────────────────────────────────────────
class JobCreateRequestA(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tasks: list[JobTask] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_image_ids(self) -> "JobCreateRequestA":
        image_ids = [t.image_id for t in self.tasks]
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("Duplicate image_id found in tasks")
        return self


# ──────────────────────────────────────────────
# 2.10 GlobalMappings
# ──────────────────────────────────────────────
class GlobalMappings(BaseModel):
    model_config = ConfigDict(frozen=True)

    color_mappings: list[ColorMapping] = Field(min_length=1)
    tolerance: int = Field(default=25, ge=0, le=100)
    variation_name: str = Field(default="recolored", min_length=1, max_length=50)


# ──────────────────────────────────────────────
# 2.11 JobCreateRequestB
# ──────────────────────────────────────────────
class JobCreateRequestB(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    global_mappings: GlobalMappings
    image_ids: list[str] = Field(min_length=1, max_length=20)


# ──────────────────────────────────────────────
# 2.12 JobStatus
# ──────────────────────────────────────────────
class JobStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    status: str
    progress: int = Field(ge=0, le=100)
    total_tasks: int
    total_variations: int
    processed_variations: int
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    download_url: Optional[str] = None


# ──────────────────────────────────────────────
# 2.13 ImageMeta
# ──────────────────────────────────────────────
class ImageMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_id: str
    filename: str = Field(max_length=255)
    original_format: str
    width: int
    height: int
    dpi: Optional[int] = None
    size_bytes: int
    uploaded_at: str


# ──────────────────────────────────────────────
# 2.14 PresetCreate
# ──────────────────────────────────────────────
class PresetCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    colors: list[str] = Field(min_length=1, max_length=10)
    source_image_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_preset_name(v)

    @field_validator("colors")
    @classmethod
    def validate_colors(cls, v: list[str]) -> list[str]:
        for c in v:
            _validate_hex(c)
        return v

    @field_validator("source_image_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        return _validate_source_image_url(v)


# ──────────────────────────────────────────────
# 2.15 Preset
# ──────────────────────────────────────────────
class Preset(BaseModel):
    model_config = ConfigDict(frozen=True)

    preset_id: str
    name: str
    colors: list[str]
    source_image_url: Optional[str] = None
    created_at: str


# ──────────────────────────────────────────────
# 2.16 PresetUpdate
# ──────────────────────────────────────────────
class PresetUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    colors: Optional[list[str]] = None
    source_image_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_preset_name(v)

    @field_validator("colors")
    @classmethod
    def validate_colors(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) < 1:
            raise ValueError("At least 1 color required")
        if len(v) > 10:
            raise ValueError("Maximum 10 colors allowed")
        for c in v:
            _validate_hex(c)
        return v

    @field_validator("source_image_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        return _validate_source_image_url(v)


# ──────────────────────────────────────────────
# 2.17 PreviewReplaceRequest
# ──────────────────────────────────────────────
class PreviewReplaceRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    color_mappings: list[ColorMapping] = Field(min_length=1)
    tolerance: int = Field(default=25, ge=0, le=100)


# ──────────────────────────────────────────────
# 2.18 PickColorRequest
# ──────────────────────────────────────────────
class PickColorRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: int = Field(ge=0)
    y: int = Field(ge=0)


# ──────────────────────────────────────────────
# 2.19 SuggestMappingsRequest
# ──────────────────────────────────────────────
class SuggestMappingsRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_palette: list[str] = Field(min_length=1, max_length=10)

    @field_validator("target_palette")
    @classmethod
    def validate_palette(cls, v: list[str]) -> list[str]:
        for c in v:
            _validate_hex(c)
        return v


# ──────────────────────────────────────────────
# 2.20 BatchAnalyzeRequest
# ──────────────────────────────────────────────
class BatchAnalyzeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_ids: list[str] = Field(min_length=1, max_length=20)
    count: int = Field(default=5, ge=1, le=20)


# ──────────────────────────────────────────────
# 2.21 LoginRequest
# ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


# ──────────────────────────────────────────────
# 2.22 TokenResponse
# ──────────────────────────────────────────────
class TokenResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str
    expires_at: str
