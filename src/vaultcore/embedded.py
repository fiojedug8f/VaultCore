"""Вшитый при сборке открытый ключ автора (режим «Проверка»).

Файл генерируется скриптом ``tools/embed_key.py`` прямо перед сборкой
PyInstaller: ключ попадает в код, а не читается из файла, который можно
подменить рядом с исполняемым файлом. Пустая строка = ключ не вшит (dev-сборка
автора), тогда проверка честно сообщает «доверенный ключ не задан».

Файл перезаписывается автоматически — не правьте его руками.
"""

from __future__ import annotations

from .b64util import b64u_decode

#: Заполняется tools/embed_key.py. Пусто — сборка без вшитого ключа.
EMBEDDED_PUBLIC_KEY_B64: str = ""
#: Человекочитаемое имя владельца ключа (для интерфейса).
EMBEDDED_KEY_OWNER: str = ""
#: Дата вшивания (ISO 8601 UTC).
EMBEDDED_AT: str = ""


def embedded_public_key() -> bytes | None:
    """32 байта открытого ключа или None."""
    value = (EMBEDDED_PUBLIC_KEY_B64 or "").strip()
    if not value:
        return None
    raw = b64u_decode(value)
    if len(raw) != 32:
        raise ValueError("Вшитый открытый ключ повреждён (должен быть 32 байта)")
    return raw


def has_embedded_key() -> bool:
    try:
        return embedded_public_key() is not None
    except ValueError:
        return False
