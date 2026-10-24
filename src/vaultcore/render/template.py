"""Внешний шаблон оформления документа.

Оформление вынесено в ``templates/document.json``: цвет, кегли, поля, тексты
блока заверения и штампа можно менять без пересборки приложения (файл читается
при каждом рендере; путь переопределяется ``POI_TEMPLATE``).

Важно: оформление НЕ является защитой. Подпись считается от «версия + заголовок
+ текст + дата», а не от PDF, поэтому любой редизайн безопасен для
существующих документов.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import paths

DEFAULT_TEMPLATE: dict[str, Any] = {
    "version": 1,
    "app": {
        "name": "VaultCore",
        "subtitle": "заверенный документ о намерении",
        "tagline": "локальная подпись Ed25519 · без сервера",
    },
    "document": {
        "idLabel": "Документ №",
        "formatLabel": "формат кода VC1 v",
        "dateLabel": "Дата и время создания (UTC)",
        "localDateLabel": "Местное время устройства (справочно, подписью не покрыто)",
        "certifyHeading": "Заверено цифровой подписью",
        "certifyIntro": "Содержимое зафиксировано цифровой подписью Ed25519.",
        "signatureLabel": "Подпись Ed25519 (base64url)",
        "signatureFingerprintLabel": "Отпечаток подписи",
        "digestLabel": "SHA-256 подписанных полей",
        "publicKeyLabel": "Открытый ключ автора (base64url)",
        "fingerprintShortLabel": "Отпечаток для сверки",
        "keyFingerprintLabel": "Полный отпечаток ключа автора",
        "tsaNote": "Независимое заверение времени (TSA) не использовалось.",
        "ephemeralNote": "Документ подписан эфемерным ключом.",
        "disclaimer": (
            "Документ не имеет юридической силы. Это инструмент фиксации намерения "
            "и доказательства неизменности."
        ),
        "verifyHint": "Проверка: VaultCore → «Проверка» → вставьте код. Работает офлайн.",
        "signatureLineLabel": "Место для подписи",
        "qrCaption": "Код проверки",
        "qrHint": "наведите камеру",
        "qrTooLong": (
            "Код длиннее QR-кода: он записан в метаданные PDF (поле Subject) — "
            "скопируйте его оттуда."
        ),
        "footerNote": (
            "VaultCore · инструмент фиксации намерения · "
            "не является юридическим документом"
        ),
        "pageLabel": "Стр.",
    },
    "colors": {
        "ink": "#1f2733",
        "muted": "#5a6472",
        "rule": "#1f3a5f",
        "accent": "#1f3a5f",
        "stamp": "#7b1f2b",
        "blockBg": "#f5f7fa",
        "blockBorder": "#9aa7b6",
        "line": "#c8d0da",
    },
    "page": {"marginMm": 20, "headerMm": 46, "headerCompactMm": 32, "footerMm": 14},
    "type": {
        "bodySize": 11,
        "leading": 1.45,
        "titleSize": 18,
        "metaSize": 8.4,
        "blockSize": 7.8,
        "monoSize": 6.4,
    },
    "watermark": {
        "text": "ОБРАЗЕЦ",
        "subText": "НЕ ЮРИДИЧЕСКИЙ ДОКУМЕНТ",
        "subText2": "VAULT CORE",
        "opacity": 0.14,
        "rotate": -18,
        "radius": 168,
    },
    "qr": {"sizeMm": 30, "scale": 6},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass(frozen=True)
class Template:
    raw: dict[str, Any]
    path: Path | None = None

    # --- доступ к строкам -------------------------------------------------

    def text(self, key: str, default: str = "") -> str:
        return str(self.raw.get("document", {}).get(key, default))

    def app(self, key: str, default: str = "") -> str:
        return str(self.raw.get("app", {}).get(key, default))

    # --- оформление -------------------------------------------------------

    def color(self, key: str, default: str = "#000000") -> str:
        return str(self.raw.get("colors", {}).get(key, default))

    def num(self, section: str, key: str, default: float) -> float:
        try:
            return float(self.raw.get(section, {}).get(key, default))
        except (TypeError, ValueError):
            return default

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}


def default_template_path() -> Path:
    override = os.environ.get("POI_TEMPLATE")
    if override:
        return Path(override).expanduser()
    return paths.templates_dir() / "document.json"


def load_template(path: Path | str | None = None) -> Template:
    """Читает шаблон; отсутствующие ключи берутся из встроенных умолчаний."""
    target = Path(path) if path is not None else default_template_path()
    data: dict[str, Any] = {}
    if target.exists():
        try:
            data = json.loads(target.read_text("utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Шаблон оформления повреждён ({target}): {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Шаблон оформления должен быть JSON-объектом: {target}")
    merged = _deep_merge(DEFAULT_TEMPLATE, data)
    return Template(raw=merged, path=target if target.exists() else None)
