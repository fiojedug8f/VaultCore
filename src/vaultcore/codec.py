"""Передаваемый код документа: ``VC1.<base64url(JSON)>`` и ссылки на него.

Начиная с формата v2 открытый ключ автора лежит **внутри кода**: получателю не
нужно ничего заранее знать об отправителе — документ самодостаточен.
Проверяющий сверяет лишь отпечаток ключа с тем, что прислал автор.

Ссылки — только обёртки над кодом:

* ``vaultcore://verify?code=VC1....`` — своя схема (нужна регистрация);
* ``https://vaultcore.app/verify#code=VC1....`` — фрагмент ``#`` не уходит
  на сервер даже при открытии в браузере.
"""

from __future__ import annotations

import re

from . import canonical
from .b64util import EncodingError, b64u_decode, b64u_encode

CODE_PREFIX = "VC1."
URL_SCHEME = "vaultcore://verify?code="
WEB_LINK_BASE = "https://vaultcore.app/verify#code="

MAX_CODE_CHARS = 600_000

# Код целиком (используется и для извлечения из произвольного текста).
_CODE_RE = re.compile(r"VC1\.([A-Za-z0-9_-]+)")


class CodeError(ValueError):
    """Строка не является кодом VaultCore."""


def encode(payload: canonical.Payload) -> str:
    """Payload → передаваемый код."""
    return CODE_PREFIX + b64u_encode(canonical.dumps(payload))


def decode(code: str) -> canonical.Payload:
    """Код → Payload со строгой проверкой формата."""
    body = extract(code)
    try:
        raw = b64u_decode(body[len(CODE_PREFIX):])
    except EncodingError as exc:
        raise CodeError(f"Тело кода повреждено: {exc}") from exc
    if len(raw) > canonical.MAX_JSON_BYTES:
        raise CodeError("Код слишком длинный")
    try:
        return canonical.loads(raw)
    except canonical.PayloadError as exc:
        raise CodeError(str(exc)) from exc


def extract(text: str) -> str:
    """Достаёт канонический код из произвольной вставки.

    Терпит пробелы, переводы строк, BOM, обёртку-ссылку и «умные» кавычки вокруг
    кода: люди копируют код из мессенджеров, и отказ из-за перенесённой строки
    выглядел бы как поломка приложения. При этом сам код проверяется строго —
    ровно так, как он записан (без «починки» символов).
    """
    if not isinstance(text, str):
        raise CodeError("Код должен быть строкой")
    cleaned = text.replace("\ufeff", "").replace("\u200b", "")
    if len(cleaned) > MAX_CODE_CHARS:
        raise CodeError("Вставленный текст слишком длинный")
    # Переносы строк внутри кода — самая частая «порча» при копировании.
    compact = "".join(cleaned.split())
    match = _CODE_RE.search(compact)
    if not match:
        raise CodeError(
            "Код не найден. Ожидается строка, начинающаяся с «VC1.», "
            "или ссылка vaultcore://verify?code=…"
        )
    code = match.group(0)
    tail = compact[match.end():].strip(" \t\r\n\"'«»”“().,;")
    if tail:
        # После кода есть посторонний текст — не угадываем, а отказываем.
        raise CodeError("После кода обнаружен посторонний текст")
    return code


def build_link(code: str) -> str:
    """Ссылка для мессенджера (собственная схема)."""
    return URL_SCHEME + extract(code)


def build_web_link(code: str, base: str = WEB_LINK_BASE) -> str:
    """HTTPS-ссылка; код лежит во фрагменте и не попадает на сервер."""
    base = base.rstrip("#")
    return base + "#code=" + extract(code)


def is_code(text: str) -> bool:
    try:
        extract(text)
    except CodeError:
        return False
    return True
