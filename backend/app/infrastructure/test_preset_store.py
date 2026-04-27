"""
TDD-тесты для infrastructure/preset_store.py
Спецификация: infrastructure/preset_store_spec.md

Покрытие:
- create_preset → get_preset: roundtrip
- get_all_presets: сортировка по дате
- update_preset: поля обновлены, остальные сохранены
- delete_preset: удалён, get → None
- Дубликат имени (case-insensitive) → ValueError
- Лимит 100 пресетов → ValueError
- Файл не существует → создаётся []
- Повреждённый JSON → backup + чистый старт
- [SRE_MARKER] Atomic write
- [SRE_MARKER] threading.Lock на read-modify-write
"""

import json
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_preset_path(tmp_path):
    return str(tmp_path / "presets.json")


@pytest.fixture
def mock_config(tmp_preset_path):
    config = MagicMock()
    config.PRESETS_PATH = tmp_preset_path
    return config


@pytest.fixture
def preset_store(mock_config):
    from app.infrastructure.preset_store import PresetStore
    return PresetStore(mock_config)


# ──────────────────────────────────────────────
# 3.1 create_preset
# ──────────────────────────────────────────────
class TestCreatePreset:
    def test_create_and_get_roundtrip(self, preset_store):
        """create → get: данные совпадают."""
        preset = preset_store.create_preset(
            name="Jordan Blue",
            colors=["#0C56A0", "#000000", "#FFFFFF"],
            source_image_url="https://example.com/shoe.jpg",
        )

        assert preset.name == "Jordan Blue"
        assert preset.colors == ["#0C56A0", "#000000", "#FFFFFF"]
        assert preset.source_image_url == "https://example.com/shoe.jpg"
        assert preset.preset_id is not None
        assert preset.created_at is not None

        # get by id
        fetched = preset_store.get_preset(preset.preset_id)
        assert fetched is not None
        assert fetched.name == "Jordan Blue"

    def test_create_generates_unique_id(self, preset_store):
        p1 = preset_store.create_preset("Preset A", ["#FF0000"], None)
        p2 = preset_store.create_preset("Preset B", ["#00FF00"], None)
        assert p1.preset_id != p2.preset_id

    def test_create_persists_to_file(self, preset_store, tmp_preset_path):
        """Данные записываются в JSON-файл."""
        preset_store.create_preset("Test", ["#FF0000"], None)
        assert os.path.exists(tmp_preset_path)

        with open(tmp_preset_path, "r") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "Test"


# ──────────────────────────────────────────────
# 3.2 get_all_presets
# ──────────────────────────────────────────────
class TestGetAllPresets:
    def test_returns_all(self, preset_store):
        preset_store.create_preset("A", ["#FF0000"], None)
        preset_store.create_preset("B", ["#00FF00"], None)
        preset_store.create_preset("C", ["#0000FF"], None)

        result = preset_store.get_all_presets()
        assert len(result) == 3

    def test_sorted_newest_first(self, preset_store):
        """Сортировка: новые первыми."""
        preset_store.create_preset("First", ["#FF0000"], None)
        preset_store.create_preset("Second", ["#00FF00"], None)
        preset_store.create_preset("Third", ["#0000FF"], None)

        result = preset_store.get_all_presets()
        assert result[0].name == "Third"
        assert result[2].name == "First"

    def test_empty_returns_empty_list(self, preset_store):
        result = preset_store.get_all_presets()
        assert result == []


# ──────────────────────────────────────────────
# 3.3 get_preset
# ──────────────────────────────────────────────
class TestGetPreset:
    def test_existing(self, preset_store):
        p = preset_store.create_preset("Test", ["#FF0000"], None)
        fetched = preset_store.get_preset(p.preset_id)
        assert fetched is not None
        assert fetched.preset_id == p.preset_id

    def test_nonexistent_returns_none(self, preset_store):
        result = preset_store.get_preset("nonexistent_id_123")
        assert result is None


# ──────────────────────────────────────────────
# 3.4 update_preset
# ──────────────────────────────────────────────
class TestUpdatePreset:
    def test_update_name(self, preset_store):
        p = preset_store.create_preset("Old Name", ["#FF0000"], None)
        updated = preset_store.update_preset(p.preset_id, name="New Name")
        assert updated is not None
        assert updated.name == "New Name"

    def test_update_colors(self, preset_store):
        p = preset_store.create_preset("Test", ["#FF0000"], None)
        updated = preset_store.update_preset(
            p.preset_id, colors=["#00FF00", "#0000FF"]
        )
        assert updated.colors == ["#00FF00", "#0000FF"]

    def test_unchanged_fields_preserved(self, preset_store):
        p = preset_store.create_preset(
            "Original", ["#FF0000"], "https://example.com/img.jpg"
        )
        updated = preset_store.update_preset(p.preset_id, name="Changed")
        assert updated.colors == ["#FF0000"]
        assert updated.source_image_url == "https://example.com/img.jpg"

    def test_update_nonexistent_returns_none(self, preset_store):
        result = preset_store.update_preset("fake_id", name="Test")
        assert result is None

    def test_update_name_duplicate_raises(self, preset_store):
        """Обновление имени на дубликат → ValueError."""
        preset_store.create_preset("Existing", ["#FF0000"], None)
        p2 = preset_store.create_preset("Other", ["#00FF00"], None)

        with pytest.raises(ValueError, match="already exists"):
            preset_store.update_preset(p2.preset_id, name="Existing")


# ──────────────────────────────────────────────
# 3.5 delete_preset
# ──────────────────────────────────────────────
class TestDeletePreset:
    def test_delete_existing(self, preset_store):
        p = preset_store.create_preset("ToDelete", ["#FF0000"], None)
        assert preset_store.delete_preset(p.preset_id) is True
        assert preset_store.get_preset(p.preset_id) is None

    def test_delete_nonexistent(self, preset_store):
        assert preset_store.delete_preset("fake_id") is False

    def test_delete_persists(self, preset_store, tmp_preset_path):
        p = preset_store.create_preset("ToDelete", ["#FF0000"], None)
        preset_store.delete_preset(p.preset_id)

        with open(tmp_preset_path, "r") as f:
            data = json.load(f)
        assert len(data) == 0


# ──────────────────────────────────────────────
# Валидация имён
# ──────────────────────────────────────────────
class TestPresetNameValidation:
    def test_duplicate_name_case_insensitive(self, preset_store):
        """Дубликат имени (case-insensitive) → ValueError."""
        preset_store.create_preset("My Preset", ["#FF0000"], None)
        with pytest.raises(ValueError, match="already exists"):
            preset_store.create_preset("my preset", ["#00FF00"], None)

    def test_duplicate_exact_same(self, preset_store):
        preset_store.create_preset("Same", ["#FF0000"], None)
        with pytest.raises(ValueError, match="already exists"):
            preset_store.create_preset("Same", ["#00FF00"], None)


# ──────────────────────────────────────────────
# Лимит
# ──────────────────────────────────────────────
class TestPresetLimit:
    def test_max_100_presets(self, preset_store):
        """[SRE_MARKER] Лимит 100 пресетов → ValueError."""
        for i in range(100):
            preset_store.create_preset(f"Preset_{i}", ["#FF0000"], None)

        with pytest.raises(ValueError, match="100"):
            preset_store.create_preset("Preset_101", ["#FF0000"], None)


# ──────────────────────────────────────────────
# Файловая система
# ──────────────────────────────────────────────
class TestPresetFileHandling:
    def test_file_not_exists_creates_empty(self, mock_config, tmp_preset_path):
        """Файл не существует → создаётся []."""
        assert not os.path.exists(tmp_preset_path)
        from app.infrastructure.preset_store import PresetStore
        store = PresetStore(mock_config)
        result = store.get_all_presets()
        assert result == []

    def test_corrupted_json_creates_backup(self, mock_config, tmp_preset_path):
        """Повреждённый JSON → backup + чистый старт."""
        # Записать невалидный JSON
        with open(tmp_preset_path, "w") as f:
            f.write("{invalid json!!!}")

        from app.infrastructure.preset_store import PresetStore
        store = PresetStore(mock_config)
        result = store.get_all_presets()
        assert result == []

        # Backup должен существовать
        backup_files = [
            f for f in os.listdir(os.path.dirname(tmp_preset_path))
            if ".bak" in f
        ]
        assert len(backup_files) >= 1


# ──────────────────────────────────────────────
# [SRE_MARKER] Потокобезопасность
# ──────────────────────────────────────────────
class TestPresetStoreThreadSafety:
    def test_concurrent_creates(self, preset_store):
        """[SRE_MARKER] Параллельные create не теряют данные."""
        errors = []

        def create_preset(i):
            try:
                preset_store.create_preset(f"Thread_{i}", ["#FF0000"], None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_preset, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        all_presets = preset_store.get_all_presets()
        assert len(all_presets) == 10
