"""Пользовательское соглашение: текст, версия, фиксация принятия."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vaultcore import eula as eula_mod

ROOT = Path(__file__).resolve().parents[1]


def _flat(text: str) -> str:
    """Текст без переносов строк: пункты соглашения сверяются по смыслу, не по вёрстке."""
    return " ".join(text.split()).lower()


def test_packaged_eula_loads():
    eula = eula_mod.load_eula()
    text = _flat(eula.text)
    assert eula.version
    assert len(eula.text) > 1000
    assert "не имеют юридической силы" in text
    assert "как есть» (as is)" in text
    assert "нотариус" in text
    assert "отметок времени" in text


def test_eula_mentions_all_required_points():
    text = _flat(eula_mod.load_eula().text)
    required = [
        "как есть",                        # 1. AS IS, без гарантий
        "не имеют юридической силы",       # 2. документы без силы
        "нотариус",                        # 3. не юридический сервис
        "ответственность за содержание",   # 4. ответственность пользователя
        "не использует серверов",          # 5. всё локально
        "хранилище операционной системы",  # 6. ключ в хранилище ОС
        "третьими лицами",                 # 7. третьими лицами
        "запрещено",                       # 8. запреты
        "может быть обновлено",            # 9. обновления соглашения
    ]
    for fragment in required:
        assert fragment in text, f"в соглашении нет пункта: {fragment}"


def test_root_copy_is_identical_to_packaged():
    root = ROOT / "eula_ru.md"
    packaged = ROOT / "src" / "vaultcore" / "assets" / "eula_ru.md"
    assert root.exists() and packaged.exists()
    assert hashlib.sha256(root.read_bytes()).hexdigest() == hashlib.sha256(
        packaged.read_bytes()
    ).hexdigest(), "копии eula_ru.md разошлись — правьте обе или пересоберите"


def test_acceptance_flow(tmp_path):
    eula = eula_mod.load_eula()
    path = tmp_path / "eula.json"
    assert not eula_mod.is_accepted(eula, path)
    acceptance = eula_mod.accept(eula, path)
    assert acceptance.version == eula.version
    assert eula_mod.is_accepted(eula, path)
    stored = eula_mod.read_acceptance(path)
    assert stored is not None and stored.sha256 == eula.sha256


def test_updated_text_requires_new_acceptance(tmp_path):
    eula = eula_mod.load_eula()
    path = tmp_path / "eula.json"
    eula_mod.accept(eula, path)

    edited = tmp_path / "eula_edited.md"
    changed_text = eula.text.replace(
        "## 7. Прочее", "## 7. Прочее\n\n7.0. Новая редакция для проверки механизма."
    )
    edited.write_text(f"<!-- eula-version: 1.1 -->\n{changed_text}", "utf-8")

    changed = eula_mod.load_eula(edited)
    assert changed.version == "1.1"
    assert changed.sha256 != eula.sha256
    assert not eula_mod.is_accepted(changed, path)


def test_missing_version_marker_rejected(tmp_path):
    bad = tmp_path / "eula.md"
    bad.write_text("# Соглашение\n\nБез маркера версии.\n", "utf-8")
    with pytest.raises(eula_mod.EulaError, match="маркер"):
        eula_mod.load_eula(bad)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(eula_mod.EulaError):
        eula_mod.load_eula(tmp_path / "nope.md")


def test_bom_in_eula_file_tolerated(tmp_path):
    source = eula_mod.load_eula()
    path = tmp_path / "eula.md"
    path.write_text("\ufeff<!-- eula-version: 9.9 -->\n" + source.text, "utf-8")
    assert eula_mod.load_eula(path).version == "9.9"
