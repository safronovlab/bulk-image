"""
TDD-тесты для core/models.py
Спецификация: core/models_spec.md

Покрытие:
- Валидация HEX regex
- Валидация tolerance 0-100
- Валидация Variation name regex
- Валидация PresetCreate/PresetUpdate
- Frozen (immutable) модели
- SSRF-валидация source_image_url
- Уникальность image_id в JobCreateRequestA
- ConfigDict(extra='forbid') для Job requests
- Лимиты max/min для списков
- LoginRequest max_length защита от DoS
"""

import pytest
from pydantic import ValidationError


# ──────────────────────────────────────────────
# 2.1 ColorRGB
# ──────────────────────────────────────────────
class TestColorRGB:
    def test_valid_rgb(self):
        from app.core.models import ColorRGB
        c = ColorRGB(r=0, g=128, b=255)
        assert c.r == 0
        assert c.g == 128
        assert c.b == 255

    def test_rgb_lower_bound(self):
        from app.core.models import ColorRGB
        c = ColorRGB(r=0, g=0, b=0)
        assert c.r == 0

    def test_rgb_upper_bound(self):
        from app.core.models import ColorRGB
        c = ColorRGB(r=255, g=255, b=255)
        assert c.r == 255

    def test_rgb_negative_rejected(self):
        from app.core.models import ColorRGB
        with pytest.raises(ValidationError):
            ColorRGB(r=-1, g=0, b=0)

    def test_rgb_over_255_rejected(self):
        from app.core.models import ColorRGB
        with pytest.raises(ValidationError):
            ColorRGB(r=256, g=0, b=0)

    def test_rgb_is_frozen(self):
        from app.core.models import ColorRGB
        c = ColorRGB(r=10, g=20, b=30)
        with pytest.raises(Exception):
            c.r = 100


# ──────────────────────────────────────────────
# 2.2 ColorLAB
# ──────────────────────────────────────────────
class TestColorLAB:
    def test_valid_lab(self):
        from app.core.models import ColorLAB
        c = ColorLAB(l=50.0, a=0.0, b_channel=0.0)
        assert c.l == 50.0

    def test_lab_l_lower_bound(self):
        from app.core.models import ColorLAB
        c = ColorLAB(l=0.0, a=-128.0, b_channel=-128.0)
        assert c.l == 0.0

    def test_lab_l_upper_bound(self):
        from app.core.models import ColorLAB
        c = ColorLAB(l=100.0, a=127.0, b_channel=127.0)
        assert c.l == 100.0

    def test_lab_l_over_100_rejected(self):
        from app.core.models import ColorLAB
        with pytest.raises(ValidationError):
            ColorLAB(l=101.0, a=0.0, b_channel=0.0)

    def test_lab_is_frozen(self):
        from app.core.models import ColorLAB
        c = ColorLAB(l=50.0, a=0.0, b_channel=0.0)
        with pytest.raises(Exception):
            c.l = 99.0


# ──────────────────────────────────────────────
# 2.3 ColorInfo
# ──────────────────────────────────────────────
class TestColorInfo:
    def test_valid_hex(self):
        from app.core.models import ColorInfo, ColorRGB, ColorLAB
        ci = ColorInfo(
            hex="#FF00AA",
            rgb=ColorRGB(r=255, g=0, b=170),
            lab=ColorLAB(l=50.0, a=80.0, b_channel=-10.0),
        )
        assert ci.hex == "#FF00AA"

    def test_hex_lowercase_accepted(self):
        from app.core.models import ColorInfo, ColorRGB, ColorLAB
        ci = ColorInfo(
            hex="#ff00aa",
            rgb=ColorRGB(r=255, g=0, b=170),
            lab=ColorLAB(l=50.0, a=80.0, b_channel=-10.0),
        )
        assert ci.hex == "#ff00aa"

    def test_invalid_hex_no_hash(self):
        from app.core.models import ColorInfo, ColorRGB, ColorLAB
        with pytest.raises(ValidationError):
            ColorInfo(
                hex="FF00AA",
                rgb=ColorRGB(r=255, g=0, b=170),
                lab=ColorLAB(l=50.0, a=80.0, b_channel=-10.0),
            )

    def test_invalid_hex_short(self):
        from app.core.models import ColorInfo, ColorRGB, ColorLAB
        with pytest.raises(ValidationError):
            ColorInfo(
                hex="#FFF",
                rgb=ColorRGB(r=255, g=0, b=170),
                lab=ColorLAB(l=50.0, a=80.0, b_channel=-10.0),
            )

    def test_invalid_hex_non_hex_chars(self):
        from app.core.models import ColorInfo, ColorRGB, ColorLAB
        with pytest.raises(ValidationError):
            ColorInfo(
                hex="#GGHHII",
                rgb=ColorRGB(r=255, g=0, b=170),
                lab=ColorLAB(l=50.0, a=80.0, b_channel=-10.0),
            )

    def test_is_frozen(self):
        from app.core.models import ColorInfo, ColorRGB, ColorLAB
        ci = ColorInfo(
            hex="#FF00AA",
            rgb=ColorRGB(r=255, g=0, b=170),
            lab=ColorLAB(l=50.0, a=80.0, b_channel=-10.0),
        )
        with pytest.raises(Exception):
            ci.hex = "#000000"


# ──────────────────────────────────────────────
# 2.4 DominantColor
# ──────────────────────────────────────────────
class TestDominantColor:
    def test_valid_dominant_color(self):
        from app.core.models import DominantColor, ColorRGB
        dc = DominantColor(
            hex="#FF0000",
            rgb=ColorRGB(r=255, g=0, b=0),
            percentage=45.5,
        )
        assert dc.percentage == 45.5

    def test_percentage_zero(self):
        from app.core.models import DominantColor, ColorRGB
        dc = DominantColor(
            hex="#000000",
            rgb=ColorRGB(r=0, g=0, b=0),
            percentage=0.0,
        )
        assert dc.percentage == 0.0

    def test_percentage_100(self):
        from app.core.models import DominantColor, ColorRGB
        dc = DominantColor(
            hex="#FFFFFF",
            rgb=ColorRGB(r=255, g=255, b=255),
            percentage=100.0,
        )
        assert dc.percentage == 100.0


# ──────────────────────────────────────────────
# 2.5 ColorMapping
# ──────────────────────────────────────────────
class TestColorMapping:
    def test_valid_mapping(self):
        from app.core.models import ColorMapping
        m = ColorMapping(from_hex="#FF0000", to_hex="#0000FF")
        assert m.from_hex == "#FF0000"
        assert m.to_hex == "#0000FF"

    def test_invalid_from_hex(self):
        from app.core.models import ColorMapping
        with pytest.raises(ValidationError):
            ColorMapping(from_hex="red", to_hex="#0000FF")

    def test_invalid_to_hex(self):
        from app.core.models import ColorMapping
        with pytest.raises(ValidationError):
            ColorMapping(from_hex="#FF0000", to_hex="blue")


# ──────────────────────────────────────────────
# 2.6 MappingSuggestion
# ──────────────────────────────────────────────
class TestMappingSuggestion:
    def test_valid_suggestion(self):
        from app.core.models import MappingSuggestion
        ms = MappingSuggestion(
            from_hex="#FF0000",
            to_hex="#00FF00",
            delta_e=12.5,
            confidence=0.75,
            from_percentage=35.0,
        )
        assert ms.confidence == 0.75

    def test_confidence_bounds(self):
        from app.core.models import MappingSuggestion
        ms = MappingSuggestion(
            from_hex="#FF0000",
            to_hex="#00FF00",
            delta_e=0.0,
            confidence=1.0,
            from_percentage=100.0,
        )
        assert ms.confidence == 1.0

    def test_confidence_zero(self):
        from app.core.models import MappingSuggestion
        ms = MappingSuggestion(
            from_hex="#FF0000",
            to_hex="#00FF00",
            delta_e=50.0,
            confidence=0.0,
            from_percentage=0.0,
        )
        assert ms.confidence == 0.0


# ──────────────────────────────────────────────
# 2.7 Variation
# ──────────────────────────────────────────────
class TestVariation:
    def test_valid_variation(self):
        from app.core.models import Variation, ColorMapping
        v = Variation(
            name="Jordan_Blue",
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            tolerance=25,
        )
        assert v.name == "Jordan_Blue"

    def test_default_name(self):
        from app.core.models import Variation, ColorMapping
        v = Variation(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
        )
        assert v.name == "recolored"

    def test_default_tolerance(self):
        from app.core.models import Variation, ColorMapping
        v = Variation(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
        )
        assert v.tolerance == 25

    def test_name_regex_valid_alphanumeric_dash_underscore(self):
        from app.core.models import Variation, ColorMapping
        v = Variation(
            name="My_Color-v2",
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
        )
        assert v.name == "My_Color-v2"

    def test_name_regex_invalid_spaces(self):
        from app.core.models import Variation, ColorMapping
        with pytest.raises(ValidationError):
            Variation(
                name="Has Space",
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            )

    def test_name_regex_invalid_special_chars(self):
        from app.core.models import Variation, ColorMapping
        with pytest.raises(ValidationError):
            Variation(
                name="hello@world",
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            )

    def test_name_too_long_rejected(self):
        from app.core.models import Variation, ColorMapping
        with pytest.raises(ValidationError):
            Variation(
                name="a" * 51,
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            )

    def test_name_empty_rejected(self):
        from app.core.models import Variation, ColorMapping
        with pytest.raises(ValidationError):
            Variation(
                name="",
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            )

    def test_tolerance_zero(self):
        from app.core.models import Variation, ColorMapping
        v = Variation(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            tolerance=0,
        )
        assert v.tolerance == 0

    def test_tolerance_100(self):
        from app.core.models import Variation, ColorMapping
        v = Variation(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            tolerance=100,
        )
        assert v.tolerance == 100

    def test_tolerance_over_100_rejected(self):
        from app.core.models import Variation, ColorMapping
        with pytest.raises(ValidationError):
            Variation(
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                tolerance=101,
            )

    def test_tolerance_negative_rejected(self):
        from app.core.models import Variation, ColorMapping
        with pytest.raises(ValidationError):
            Variation(
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                tolerance=-1,
            )

    def test_empty_color_mappings_rejected(self):
        """Минимум 1 color_mapping обязателен."""
        from app.core.models import Variation
        with pytest.raises(ValidationError):
            Variation(name="test", color_mappings=[], tolerance=25)

    def test_max_50_color_mappings(self):
        """[SRE_MARKER] Защита от CPU-DoS: макс 50 маппингов."""
        from app.core.models import Variation, ColorMapping
        mappings = [
            ColorMapping(from_hex=f"#{i:02x}{i:02x}{i:02x}", to_hex="#000000")
            for i in range(51)
        ]
        with pytest.raises(ValidationError):
            Variation(name="test", color_mappings=mappings, tolerance=25)


# ──────────────────────────────────────────────
# 2.8 JobTask
# ──────────────────────────────────────────────
class TestJobTask:
    def test_valid_job_task(self):
        from app.core.models import JobTask, Variation, ColorMapping
        jt = JobTask(
            image_id="abc123",
            variations=[
                Variation(
                    color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                )
            ],
        )
        assert jt.image_id == "abc123"

    def test_empty_variations_rejected(self):
        from app.core.models import JobTask
        with pytest.raises(ValidationError):
            JobTask(image_id="abc123", variations=[])

    def test_max_10_variations(self):
        """[SRE_MARKER] Защита от CPU-взрыва: макс 10 вариаций."""
        from app.core.models import JobTask, Variation, ColorMapping
        variations = [
            Variation(
                name=f"v{i}",
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            )
            for i in range(11)
        ]
        with pytest.raises(ValidationError):
            JobTask(image_id="abc", variations=variations)


# ──────────────────────────────────────────────
# 2.9 JobCreateRequestA
# ──────────────────────────────────────────────
class TestJobCreateRequestA:
    def test_valid_request_a(self):
        from app.core.models import JobCreateRequestA, JobTask, Variation, ColorMapping
        req = JobCreateRequestA(
            tasks=[
                JobTask(
                    image_id="img1",
                    variations=[
                        Variation(
                            color_mappings=[
                                ColorMapping(from_hex="#FF0000", to_hex="#0000FF")
                            ],
                        )
                    ],
                )
            ]
        )
        assert len(req.tasks) == 1

    def test_empty_tasks_rejected(self):
        from app.core.models import JobCreateRequestA
        with pytest.raises(ValidationError):
            JobCreateRequestA(tasks=[])

    def test_max_20_tasks(self):
        """[SRE_MARKER] Защита от CPU-DoS: макс 20 tasks."""
        from app.core.models import JobCreateRequestA, JobTask, Variation, ColorMapping
        tasks = [
            JobTask(
                image_id=f"img{i}",
                variations=[
                    Variation(
                        color_mappings=[
                            ColorMapping(from_hex="#FF0000", to_hex="#0000FF")
                        ],
                    )
                ],
            )
            for i in range(21)
        ]
        with pytest.raises(ValidationError):
            JobCreateRequestA(tasks=tasks)

    def test_duplicate_image_ids_rejected(self):
        """[SRE_MARKER] model_validator: уникальность image_id."""
        from app.core.models import JobCreateRequestA, JobTask, Variation, ColorMapping
        task = JobTask(
            image_id="same_id",
            variations=[
                Variation(
                    color_mappings=[
                        ColorMapping(from_hex="#FF0000", to_hex="#0000FF")
                    ],
                )
            ],
        )
        with pytest.raises(ValidationError):
            JobCreateRequestA(tasks=[task, task])

    def test_extra_fields_forbidden(self):
        """[SRE_MARKER] ConfigDict(extra='forbid')."""
        from app.core.models import JobCreateRequestA, JobTask, Variation, ColorMapping
        with pytest.raises(ValidationError):
            JobCreateRequestA(
                tasks=[
                    JobTask(
                        image_id="img1",
                        variations=[
                            Variation(
                                color_mappings=[
                                    ColorMapping(from_hex="#FF0000", to_hex="#0000FF")
                                ],
                            )
                        ],
                    )
                ],
                evil_field="injected",
            )


# ──────────────────────────────────────────────
# 2.11 JobCreateRequestB
# ──────────────────────────────────────────────
class TestJobCreateRequestB:
    def test_valid_request_b(self):
        from app.core.models import (
            JobCreateRequestB,
            GlobalMappings,
            ColorMapping,
        )
        req = JobCreateRequestB(
            global_mappings=GlobalMappings(
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                tolerance=30,
            ),
            image_ids=["img1", "img2"],
        )
        assert len(req.image_ids) == 2

    def test_empty_image_ids_rejected(self):
        from app.core.models import (
            JobCreateRequestB,
            GlobalMappings,
            ColorMapping,
        )
        with pytest.raises(ValidationError):
            JobCreateRequestB(
                global_mappings=GlobalMappings(
                    color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                ),
                image_ids=[],
            )

    def test_max_20_image_ids(self):
        """[SRE_MARKER] Защита от CPU-взрыва: макс 20 image_ids."""
        from app.core.models import (
            JobCreateRequestB,
            GlobalMappings,
            ColorMapping,
        )
        with pytest.raises(ValidationError):
            JobCreateRequestB(
                global_mappings=GlobalMappings(
                    color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                ),
                image_ids=[f"img{i}" for i in range(21)],
            )

    def test_extra_fields_forbidden(self):
        """[SRE_MARKER] ConfigDict(extra='forbid')."""
        from app.core.models import (
            JobCreateRequestB,
            GlobalMappings,
            ColorMapping,
        )
        with pytest.raises(ValidationError):
            JobCreateRequestB(
                global_mappings=GlobalMappings(
                    color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                ),
                image_ids=["img1"],
                evil_field="injected",
            )


# ──────────────────────────────────────────────
# 2.13 ImageMeta
# ──────────────────────────────────────────────
class TestImageMeta:
    def test_valid_image_meta(self):
        from app.core.models import ImageMeta
        im = ImageMeta(
            image_id="abc123",
            filename="skull_tee.png",
            original_format="png",
            width=4000,
            height=3000,
            dpi=300,
            size_bytes=5_000_000,
            uploaded_at="2026-04-27T10:00:00Z",
        )
        assert im.image_id == "abc123"

    def test_filename_max_255(self):
        from app.core.models import ImageMeta
        im = ImageMeta(
            image_id="abc",
            filename="a" * 255,
            original_format="png",
            width=100,
            height=100,
            dpi=None,
            size_bytes=1000,
            uploaded_at="2026-04-27T10:00:00Z",
        )
        assert len(im.filename) == 255

    def test_dpi_nullable(self):
        from app.core.models import ImageMeta
        im = ImageMeta(
            image_id="abc",
            filename="test.png",
            original_format="jpeg",
            width=100,
            height=100,
            dpi=None,
            size_bytes=1000,
            uploaded_at="2026-04-27T10:00:00Z",
        )
        assert im.dpi is None


# ──────────────────────────────────────────────
# 2.14 PresetCreate — с SSRF-валидацией
# ──────────────────────────────────────────────
class TestPresetCreate:
    def test_valid_preset(self):
        from app.core.models import PresetCreate
        p = PresetCreate(
            name="Jordan Retro",
            colors=["#FF0000", "#00FF00", "#0000FF"],
        )
        assert p.name == "Jordan Retro"

    def test_name_trim_whitespace(self):
        from app.core.models import PresetCreate
        p = PresetCreate(name="  trimmed  ", colors=["#FF0000"])
        assert p.name == "trimmed"

    def test_name_empty_after_trim_rejected(self):
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="   ", colors=["#FF0000"])

    def test_name_max_100(self):
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="a" * 101, colors=["#FF0000"])

    def test_colors_min_1(self):
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="test", colors=[])

    def test_colors_max_10(self):
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=[f"#{i:02x}{i:02x}{i:02x}" for i in range(11)],
            )

    def test_invalid_hex_in_colors(self):
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="test", colors=["not-a-hex"])

    def test_source_image_url_https_accepted(self):
        from app.core.models import PresetCreate
        p = PresetCreate(
            name="test",
            colors=["#FF0000"],
            source_image_url="https://example.com/img.jpg",
        )
        assert p.source_image_url == "https://example.com/img.jpg"

    def test_source_image_url_http_rejected(self):
        """[SRE_MARKER] SSRF: только https."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="http://example.com/img.jpg",
            )

    def test_source_image_url_localhost_rejected(self):
        """[SRE_MARKER] SSRF: localhost запрещён."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://localhost/img.jpg",
            )

    def test_source_image_url_private_ip_10_rejected(self):
        """[SRE_MARKER] SSRF: приватный IP 10.x.x.x."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://10.0.0.1/img.jpg",
            )

    def test_source_image_url_private_ip_172_rejected(self):
        """[SRE_MARKER] SSRF: приватный IP 172.16.x.x."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://172.16.0.1/img.jpg",
            )

    def test_source_image_url_private_ip_192_rejected(self):
        """[SRE_MARKER] SSRF: приватный IP 192.168.x.x."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://192.168.1.1/img.jpg",
            )

    def test_source_image_url_link_local_rejected(self):
        """[SRE_MARKER] SSRF: link-local 169.254.x.x."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://169.254.169.254/latest/meta-data/",
            )

    def test_source_image_url_127_rejected(self):
        """[SRE_MARKER] SSRF: loopback 127.x.x.x."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://127.0.0.1/img.jpg",
            )

    def test_source_image_url_too_long_rejected(self):
        """[SRE_MARKER] SSRF: макс 2048 символов."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://example.com/" + "a" * 2048,
            )

    def test_source_image_url_null_accepted(self):
        from app.core.models import PresetCreate
        p = PresetCreate(name="test", colors=["#FF0000"], source_image_url=None)
        assert p.source_image_url is None

    def test_control_chars_in_name_rejected(self):
        """[SRE_MARKER] JSON-инъекция: control chars."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="test\x00evil", colors=["#FF0000"])

    def test_rtl_override_in_name_rejected(self):
        """[SRE_MARKER] JSON-инъекция: RTL override chars."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="test\u202ename", colors=["#FF0000"])


# ──────────────────────────────────────────────
# 2.16 PresetUpdate
# ──────────────────────────────────────────────
class TestPresetUpdate:
    def test_all_fields_optional(self):
        from app.core.models import PresetUpdate
        pu = PresetUpdate()
        assert pu.name is None
        assert pu.colors is None
        assert pu.source_image_url is None

    def test_partial_update_name_only(self):
        from app.core.models import PresetUpdate
        pu = PresetUpdate(name="new_name")
        assert pu.name == "new_name"
        assert pu.colors is None

    def test_partial_update_colors_only(self):
        from app.core.models import PresetUpdate
        pu = PresetUpdate(colors=["#FF0000"])
        assert pu.name is None
        assert len(pu.colors) == 1

    def test_ssrf_validation_same_as_create(self):
        """[SRE_MARKER] SSRF-валидация в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://127.0.0.1/evil")

    def test_is_frozen(self):
        from app.core.models import PresetUpdate
        pu = PresetUpdate(name="test")
        with pytest.raises(Exception):
            pu.name = "changed"


# ──────────────────────────────────────────────
# 2.17 PreviewReplaceRequest
# ──────────────────────────────────────────────
class TestPreviewReplaceRequest:
    def test_valid_request(self):
        from app.core.models import PreviewReplaceRequest, ColorMapping
        r = PreviewReplaceRequest(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            tolerance=25,
        )
        assert r.tolerance == 25

    def test_default_tolerance_25(self):
        from app.core.models import PreviewReplaceRequest, ColorMapping
        r = PreviewReplaceRequest(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
        )
        assert r.tolerance == 25

    def test_empty_mappings_rejected(self):
        from app.core.models import PreviewReplaceRequest
        with pytest.raises(ValidationError):
            PreviewReplaceRequest(color_mappings=[], tolerance=25)


# ──────────────────────────────────────────────
# 2.18 PickColorRequest
# ──────────────────────────────────────────────
class TestPickColorRequest:
    def test_valid_coords(self):
        from app.core.models import PickColorRequest
        r = PickColorRequest(x=100, y=200)
        assert r.x == 100

    def test_zero_coords(self):
        from app.core.models import PickColorRequest
        r = PickColorRequest(x=0, y=0)
        assert r.x == 0

    def test_negative_x_rejected(self):
        from app.core.models import PickColorRequest
        with pytest.raises(ValidationError):
            PickColorRequest(x=-1, y=0)

    def test_negative_y_rejected(self):
        from app.core.models import PickColorRequest
        with pytest.raises(ValidationError):
            PickColorRequest(x=0, y=-1)


# ──────────────────────────────────────────────
# 2.19 SuggestMappingsRequest
# ──────────────────────────────────────────────
class TestSuggestMappingsRequest:
    def test_valid_request(self):
        from app.core.models import SuggestMappingsRequest
        r = SuggestMappingsRequest(target_palette=["#FF0000", "#00FF00"])
        assert len(r.target_palette) == 2

    def test_empty_palette_rejected(self):
        from app.core.models import SuggestMappingsRequest
        with pytest.raises(ValidationError):
            SuggestMappingsRequest(target_palette=[])

    def test_max_10_palette(self):
        from app.core.models import SuggestMappingsRequest
        with pytest.raises(ValidationError):
            SuggestMappingsRequest(
                target_palette=[f"#{i:02x}{i:02x}{i:02x}" for i in range(11)]
            )


# ──────────────────────────────────────────────
# 2.20 BatchAnalyzeRequest
# ──────────────────────────────────────────────
class TestBatchAnalyzeRequest:
    def test_valid_request(self):
        from app.core.models import BatchAnalyzeRequest
        r = BatchAnalyzeRequest(image_ids=["img1", "img2"], count=5)
        assert r.count == 5

    def test_default_count_5(self):
        from app.core.models import BatchAnalyzeRequest
        r = BatchAnalyzeRequest(image_ids=["img1"])
        assert r.count == 5

    def test_empty_image_ids_rejected(self):
        from app.core.models import BatchAnalyzeRequest
        with pytest.raises(ValidationError):
            BatchAnalyzeRequest(image_ids=[])

    def test_max_20_image_ids(self):
        """[SRE_MARKER] DoS защита: макс 20 image_ids (KMeans CPU-bound)."""
        from app.core.models import BatchAnalyzeRequest
        with pytest.raises(ValidationError):
            BatchAnalyzeRequest(image_ids=[f"img{i}" for i in range(21)])

    def test_count_range_1_20(self):
        from app.core.models import BatchAnalyzeRequest
        with pytest.raises(ValidationError):
            BatchAnalyzeRequest(image_ids=["img1"], count=0)
        with pytest.raises(ValidationError):
            BatchAnalyzeRequest(image_ids=["img1"], count=21)


# ──────────────────────────────────────────────
# 2.21 LoginRequest
# ──────────────────────────────────────────────
class TestLoginRequest:
    def test_valid_login(self):
        from app.core.models import LoginRequest
        lr = LoginRequest(username="admin", password="secret")
        assert lr.username == "admin"

    def test_empty_username_rejected(self):
        from app.core.models import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="secret")

    def test_empty_password_rejected(self):
        from app.core.models import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(username="admin", password="")

    def test_username_max_256(self):
        """[SRE_MARKER] Защита от DoS: макс 256 символов для hmac.compare_digest."""
        from app.core.models import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(username="a" * 257, password="secret")

    def test_password_max_256(self):
        """[SRE_MARKER] Защита от CPU/RAM DoS."""
        from app.core.models import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(username="admin", password="p" * 257)


# ──────────────────────────────────────────────
# 2.22 TokenResponse
# ──────────────────────────────────────────────
class TestTokenResponse:
    def test_valid_response(self):
        from app.core.models import TokenResponse
        tr = TokenResponse(
            token="abc123def456", expires_at="2026-04-28T10:00:00Z"
        )
        assert tr.token == "abc123def456"


# ──────────────────────────────────────────────
# 2.10 GlobalMappings
# ──────────────────────────────────────────────
class TestGlobalMappings:
    def test_valid_global_mappings(self):
        from app.core.models import GlobalMappings, ColorMapping
        gm = GlobalMappings(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
            tolerance=30,
        )
        assert gm.tolerance == 30

    def test_default_tolerance_25(self):
        from app.core.models import GlobalMappings, ColorMapping
        gm = GlobalMappings(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
        )
        assert gm.tolerance == 25

    def test_default_variation_name(self):
        from app.core.models import GlobalMappings, ColorMapping
        gm = GlobalMappings(
            color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
        )
        assert gm.variation_name == "recolored"

    def test_empty_mappings_rejected(self):
        from app.core.models import GlobalMappings
        with pytest.raises(ValidationError):
            GlobalMappings(color_mappings=[])

    def test_tolerance_over_100_rejected(self):
        from app.core.models import GlobalMappings, ColorMapping
        with pytest.raises(ValidationError):
            GlobalMappings(
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                tolerance=101,
            )

    def test_tolerance_negative_rejected(self):
        from app.core.models import GlobalMappings, ColorMapping
        with pytest.raises(ValidationError):
            GlobalMappings(
                color_mappings=[ColorMapping(from_hex="#FF0000", to_hex="#0000FF")],
                tolerance=-1,
            )


# ──────────────────────────────────────────────
# 2.12 JobStatus
# ──────────────────────────────────────────────
class TestJobStatus:
    def test_valid_job_status_pending(self):
        from app.core.models import JobStatus
        js = JobStatus(
            job_id="abc123",
            status="pending",
            progress=0,
            total_tasks=3,
            total_variations=6,
            processed_variations=0,
            created_at="2026-04-27T10:00:00Z",
            completed_at=None,
            error=None,
            download_url=None,
        )
        assert js.status == "pending"
        assert js.progress == 0

    def test_valid_job_status_completed(self):
        from app.core.models import JobStatus
        js = JobStatus(
            job_id="abc123",
            status="completed",
            progress=100,
            total_tasks=3,
            total_variations=6,
            processed_variations=6,
            created_at="2026-04-27T10:00:00Z",
            completed_at="2026-04-27T11:00:00Z",
            error=None,
            download_url="/api/jobs/abc123/download",
        )
        assert js.status == "completed"
        assert js.download_url is not None

    def test_job_status_nullable_fields(self):
        from app.core.models import JobStatus
        js = JobStatus(
            job_id="abc",
            status="failed",
            progress=50,
            total_tasks=1,
            total_variations=2,
            processed_variations=1,
            created_at="2026-04-27T10:00:00Z",
            completed_at="2026-04-27T10:30:00Z",
            error="Something failed",
            download_url=None,
        )
        assert js.error == "Something failed"
        assert js.download_url is None


# ──────────────────────────────────────────────
# 2.15 Preset
# ──────────────────────────────────────────────
class TestPreset:
    def test_valid_preset(self):
        from app.core.models import Preset
        p = Preset(
            preset_id="abc123",
            name="Jordan Retro High OG Royal",
            colors=["#0C56A0", "#000000", "#FFFFFF"],
            source_image_url="https://example.com/sneaker.jpg",
            created_at="2026-04-27T10:00:00Z",
        )
        assert p.preset_id == "abc123"
        assert len(p.colors) == 3

    def test_preset_nullable_source_url(self):
        from app.core.models import Preset
        p = Preset(
            preset_id="abc",
            name="Test",
            colors=["#FF0000"],
            source_image_url=None,
            created_at="2026-04-27T10:00:00Z",
        )
        assert p.source_image_url is None

    def test_preset_is_frozen(self):
        from app.core.models import Preset
        p = Preset(
            preset_id="abc",
            name="Test",
            colors=["#FF0000"],
            source_image_url=None,
            created_at="2026-04-27T10:00:00Z",
        )
        with pytest.raises(Exception):
            p.name = "Changed"


# ──────────────────────────────────────────────
# PresetCreate — дополнительные SRE-тесты
# ──────────────────────────────────────────────
class TestPresetCreateAdditionalSRE:
    def test_ipv6_mapped_address_rejected(self):
        """[SRE_MARKER] SSRF: IPv6-mapped адрес ::ffff:127.0.0.1."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(
                name="test",
                colors=["#FF0000"],
                source_image_url="https://[::ffff:127.0.0.1]/evil",
            )

    def test_del_char_in_name_rejected(self):
        """[SRE_MARKER] JSON-инъекция: DEL char (0x7f)."""
        from app.core.models import PresetCreate
        with pytest.raises(ValidationError):
            PresetCreate(name="test\x7fevil", colors=["#FF0000"])


# ──────────────────────────────────────────────
# PresetUpdate — дополнительные SSRF-тесты
# ──────────────────────────────────────────────
class TestPresetUpdateSSRF:
    def test_http_rejected(self):
        """[SRE_MARKER] SSRF: http:// отклоняется в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="http://example.com/img.jpg")

    def test_localhost_rejected(self):
        """[SRE_MARKER] SSRF: localhost отклоняется в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://localhost/evil")

    def test_private_ip_10_rejected(self):
        """[SRE_MARKER] SSRF: 10.x.x.x отклоняется в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://10.0.0.1/evil")

    def test_private_ip_192_rejected(self):
        """[SRE_MARKER] SSRF: 192.168.x.x отклоняется в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://192.168.1.1/evil")

    def test_private_ip_172_rejected(self):
        """[SRE_MARKER] SSRF: 172.16.x.x отклоняется в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://172.16.0.1/evil")

    def test_link_local_rejected(self):
        """[SRE_MARKER] SSRF: 169.254.x.x отклоняется в PresetUpdate."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://169.254.169.254/latest/meta-data/")

    def test_too_long_url_rejected(self):
        """[SRE_MARKER] SSRF: URL > 2048 символов."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://example.com/" + "a" * 2048)

    def test_ipv6_mapped_rejected(self):
        """[SRE_MARKER] SSRF: IPv6-mapped ::ffff:127.0.0.1."""
        from app.core.models import PresetUpdate
        with pytest.raises(ValidationError):
            PresetUpdate(source_image_url="https://[::ffff:127.0.0.1]/evil")

    def test_valid_https_accepted(self):
        from app.core.models import PresetUpdate
        pu = PresetUpdate(source_image_url="https://example.com/img.jpg")
        assert pu.source_image_url == "https://example.com/img.jpg"


# ──────────────────────────────────────────────
# JobStatusEnum
# ──────────────────────────────────────────────
class TestJobStatusEnum:
    def test_enum_values(self):
        from app.core.models import JobStatusEnum
        assert JobStatusEnum.PENDING == "pending"
        assert JobStatusEnum.PROCESSING == "processing"
        assert JobStatusEnum.COMPLETED == "completed"
        assert JobStatusEnum.FAILED == "failed"
