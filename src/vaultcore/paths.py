"""Пути приложения: данные пользователя и упакованные ресурсы.

Данные (ключевой blob, принятие EULA, сгенерированные PDF) НИКОГДА не
пишутся рядом с исполняемым файлом: это и требование ТЗ, и защита от
случайной утечки через «перенос папки с программой».

Переопределение каталога данных — переменная окружения ``POI_DATA_DIR``
(используется тестами и переносными сборками).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


def _frozen_base() -> Path | None:
    """Каталог ресурсов в сборке PyInstaller (sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return None


def _resource_base() -> Path:
    return _frozen_base() or _PKG_DIR


def data_dir() -> Path:
    """Каталог данных приложения (создаётся при обращении)."""
    override = os.environ.get("POI_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / "VaultCore"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "VaultCore"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "VaultCore"
    path.mkdir(parents=True, exist_ok=True)
    return path


def documents_dir() -> Path:
    """Каталог для сгенерированных PDF (копии, не источник истины)."""
    path = data_dir() / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def keystore_blob_path() -> Path:
    """Файл с DPAPI-зашифрованным закрытым ключом (Windows)."""
    return data_dir() / "key.blob"


def identity_meta_path() -> Path:
    """Открытые метаданные личности: открытый ключ, дата создания, backend."""
    return data_dir() / "identity.json"


def eula_acceptance_path() -> Path:
    """Файл принятия пользовательского соглашения."""
    return data_dir() / "eula.json"


def assets_dir() -> Path:
    return _resource_base() / "assets"


def templates_dir() -> Path:
    return _resource_base() / "templates"


def resource(name: str) -> Path:
    """Путь к упакованному ресурсу (assets/eula_ru.md, templates/document.json)."""
    return _resource_base() / name
