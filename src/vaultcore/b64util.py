"""Строгий base64url без padding — единственный кодировщик, используемый в формате.

Почему свой модуль: формат кода фиксирован (docs/FORMAT.md), и верификатор
обязан отвергать всё, что не является канонической записью. Стандартный
``base64.urlsafe_b64decode`` молча игнорирует часть мусора и лишние ``=``,
поэтому здесь декодирование проверяется повторным кодированием.
"""

from __future__ import annotations

import base64
import re

#: Символы base64url (RFC 4648 §5), padding не допускается.
_B64URL_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


class EncodingError(ValueError):
    """Строка не является каноническим base64url."""


def b64u_encode(data: bytes) -> str:
    """Кодирует байты в base64url без ``=``."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise EncodingError("b64u_encode ожидает bytes")
    return base64.urlsafe_b64encode(bytes(data)).decode("ascii").rstrip("=")


def b64u_decode(text: str) -> bytes:
    """Декодирует base64url, требуя каноническую запись (без ``=``, без мусора)."""
    if not isinstance(text, str):
        raise EncodingError("b64u_decode ожидает str")
    if not text or not _B64URL_RE.match(text):
        raise EncodingError("недопустимые символы в base64url")
    if len(text) % 4 == 1:  # такая длина невозможна для base64
        raise EncodingError("недопустимая длина base64url")
    padded = text + "=" * (-len(text) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:  # noqa: BLE001 - любую ошибку выдаём как свою
        raise EncodingError("base64url не декодируется") from exc
    # Каноничность: перекодирование должно дать ровно ту же строку.
    if b64u_encode(raw) != text:
        raise EncodingError("неканоническая запись base64url")
    return raw
