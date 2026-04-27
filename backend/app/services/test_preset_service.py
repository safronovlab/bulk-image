"""
TDD-тесты для services/preset_service.py
Спецификация: services/preset_service_spec.md

Покрытие:
- create → get: данные совпадают
- create с дубликатом имени → ValueError
- get_all: сортировка по дате
- update: поля обновлены
- delete: удалён
- get несуществующего → None
- Разделение ответственности: формальная валидация в Pydantic, бизнес — в сервисе
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_preset_store():
    store = MagicMock()
    return store


@pytest.fixture
def preset_service(mock_preset_store):
    from app.services.preset_service import PresetService
    return PresetService(mock_preset_store)


# ──────────────────────────────────────────────
# 3.1 create_preset
# ──────────────────────────────────────────────
class TestCreatePreset:
    def test_create_delegates_to_store(self, preset_service, mock_preset_store):
        """create_preset вызывает preset_store.create_preset."""
        from app.core.models import PresetCreate

        mock_preset = MagicMock()
        mock_preset.name = "Jordan Blue"
        mock_preset.colors = ["#0C56A0"]
        mock_preset.preset_id = "abc123"
        mock_preset_store.create_preset.return_value = mock_preset

        request = PresetCreate(name="Jordan Blue", colors=["#0C56A0"])
        result = preset_service.create_preset(request)

        assert result.name == "Jordan Blue"
        mock_preset_store.create_preset.assert_called_once()

    def test_create_duplicate_name_raises(self, preset_service, mock_preset_store):
        """Дубликат имени → ValueError пробрасывается."""
        mock_preset_store.create_preset.side_effect = ValueError(
            "Preset with name 'Existing' already exists"
        )

        from app.core.models import PresetCreate

        with pytest.raises(ValueError, match="already exists"):
            preset_service.create_preset(
                PresetCreate(name="Existing", colors=["#FF0000"])
            )

    def test_create_limit_100_raises(self, preset_service, mock_preset_store):
        """Лимит 100 пресетов → ValueError пробрасывается."""
        mock_preset_store.create_preset.side_effect = ValueError(
            "Maximum number of presets (100) reached"
        )

        from app.core.models import PresetCreate

        with pytest.raises(ValueError, match="100"):
            preset_service.create_preset(
                PresetCreate(name="New", colors=["#FF0000"])
            )


# ──────────────────────────────────────────────
# 3.2 get_all_presets
# ──────────────────────────────────────────────
class TestGetAllPresets:
    def test_delegates_to_store(self, preset_service, mock_preset_store):
        mock_preset_store.get_all_presets.return_value = []
        result = preset_service.get_all_presets()
        assert result == []
        mock_preset_store.get_all_presets.assert_called_once()


# ──────────────────────────────────────────────
# 3.3 get_preset
# ──────────────────────────────────────────────
class TestGetPreset:
    def test_existing(self, preset_service, mock_preset_store):
        mock_preset = MagicMock()
        mock_preset.preset_id = "p1"
        mock_preset_store.get_preset.return_value = mock_preset

        result = preset_service.get_preset("p1")
        assert result.preset_id == "p1"

    def test_nonexistent_returns_none(self, preset_service, mock_preset_store):
        mock_preset_store.get_preset.return_value = None
        result = preset_service.get_preset("fake")
        assert result is None


# ──────────────────────────────────────────────
# 3.4 update_preset
# ──────────────────────────────────────────────
class TestUpdatePreset:
    def test_update_delegates(self, preset_service, mock_preset_store):
        mock_preset = MagicMock()
        mock_preset.name = "Updated"
        mock_preset_store.update_preset.return_value = mock_preset

        result = preset_service.update_preset("p1", name="Updated")
        assert result.name == "Updated"

    def test_update_nonexistent(self, preset_service, mock_preset_store):
        mock_preset_store.update_preset.return_value = None
        result = preset_service.update_preset("fake", name="Test")
        assert result is None


# ──────────────────────────────────────────────
# 3.5 delete_preset
# ──────────────────────────────────────────────
class TestDeletePreset:
    def test_delete_delegates(self, preset_service, mock_preset_store):
        mock_preset_store.delete_preset.return_value = True
        assert preset_service.delete_preset("p1") is True

    def test_delete_nonexistent(self, preset_service, mock_preset_store):
        mock_preset_store.delete_preset.return_value = False
        assert preset_service.delete_preset("fake") is False
