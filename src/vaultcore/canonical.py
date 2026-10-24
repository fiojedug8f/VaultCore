"""Каноническая форма подписываемых данных — формат кода версии 2.

Отличие от v1: открытый ключ автора входит в сам код документа. Поэтому
проверяющий не нуждается ни в какой предварительной настройке «а вот ключ
этого автора»: документ подтверждает себя математически, а подлинность автора
проверяется сверкой отпечатка (fingerprint) по независимому каналу.

Что подписывается (и ничего сверх этого)::

    preimage = DOMAIN
             + len(v)     as 4-byte big-endian + ascii(v)
             + len(pk)    as 4-byte big-endian + ascii(base64url(pubkey))
             + len(title) as 4-byte big-endian + utf8(title)
             + len(text)  as 4-byte big-endian + utf8(text)
             + len(ts)    as 4-byte big-endian + ascii(ts)
    digest   = SHA-256(preimage)
    sig      = Ed25519.Sign(seed, digest)

Длина в 4 байта перед каждым полем убирает неоднозначность границ: иначе
заголовок «A» с текстом «B\\nC» и заголовок «A\\nB» с текстом «C» дали бы
одинаковый префикс. Ключ входит в подписанные байты, чтобы подменить его
нельзя было даже на «математически эквивалентный» — состав полей фиксирован.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .b64util import EncodingError, b64u_decode, b64u_encode

#: Домен разделяет подписи: чужая подпись Ed25519 над теми же данными не подойдёт.
DOMAIN = b"vaultcore.code.v1"
FORMAT_VERSION = 1
SIGNATURE_LEN = 64
PUBLIC_KEY_LEN = 32

#: Заголовок по умолчанию; он тоже подписывается (пустой заголовок невозможен).
DEFAULT_TITLE = "Заверенное заявление"

MAX_TITLE_CHARS = 200
MAX_TEXT_CHARS = 100_000
MAX_JSON_BYTES = 420_000  # защита от «JSON-бомб» перед парсингом

FIELDS = ("v", "pk", "title", "text", "ts", "sig")

_TS_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
# Управляющие символы, которые нельзя записать в PDF и которые часто
# появляются при вставке текста из «умных» редакторов.
_BAD_CONTROLS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class PayloadError(ValueError):
    """Код не соответствует формату: структура, типы, значения или каноничность."""


# --------------------------------------------------------------------------
# Нормализация
# --------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Приводит содержимое к каноническому виду ПЕРЕД подписью.

    * ``\\r\\n`` и ``\\r`` → ``\\n`` (иначе одинаковый текст с разных ОС даёт
      разные подписи и «документ изменён» на ровном месте);
    * убираются пробелы/переводы строк по краям;
    * запрещаются управляющие символы, кроме ``\\t`` и ``\\n``;
    * пустой документ не подписывается.
    """
    if not isinstance(text, str):
        raise PayloadError("Содержимое должно быть строкой")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    if not text:
        raise PayloadError("Пустой документ запечатать нельзя")
    if _BAD_CONTROLS_RE.search(text):
        raise PayloadError("Содержимое содержит недопустимые управляющие символы")
    if len(text) > MAX_TEXT_CHARS:
        raise PayloadError(f"Содержимое длиннее {MAX_TEXT_CHARS} символов")
    return text


def normalize_title(title: str) -> str:
    """Заголовок — одна строка (он подписывается так же, как содержимое)."""
    if title is None:
        title = ""
    if not isinstance(title, str):
        raise PayloadError("Заголовок должен быть строкой")
    title = " ".join(title.split())
    if _BAD_CONTROLS_RE.search(title):
        raise PayloadError("Заголовок содержит недопустимые управляющие символы")
    if len(title) > MAX_TITLE_CHARS:
        raise PayloadError(f"Заголовок длиннее {MAX_TITLE_CHARS} символов")
    return title


def utc_now_iso() -> str:
    """Текущее время в формате RFC 3339, всегда UTC и всегда с «Z»."""
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(ts: str) -> datetime:
    """Разбор ``ts`` со строгой проверкой календарной корректности."""
    if not isinstance(ts, str) or not _TS_RE.match(ts):
        raise PayloadError("Дата должна быть в формате 2026-10-21T14:32:00Z (UTC)")
    try:
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise PayloadError("Дата содержит недопустимое значение") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != ts:
        raise PayloadError("Дата не является канонической записью UTC")
    return parsed


def normalize_public_key(pk_b64: str) -> bytes:
    """Разбирает открытый ключ из base64url и проверяет каноническую запись."""
    if not isinstance(pk_b64, str) or not pk_b64:
        raise PayloadError("Поле pk должно быть непустой строкой base64url")
    try:
        raw = b64u_decode(pk_b64)
    except EncodingError as exc:
        raise PayloadError(f"Открытый ключ: {exc}") from exc
    if len(raw) != PUBLIC_KEY_LEN:
        raise PayloadError(f"Открытый ключ Ed25519 должен быть {PUBLIC_KEY_LEN} байта")
    if b64u_encode(raw) != pk_b64:
        raise PayloadError("Открытый ключ записан неканонически")
    return raw


# --------------------------------------------------------------------------
# Канонические байты
# --------------------------------------------------------------------------


def _frame(value: bytes) -> bytes:
    if len(value) > 0xFFFFFFFF:
        raise PayloadError("Слишком длинное поле")
    return len(value).to_bytes(4, "big") + value


def signing_preimage(version: int, public_key_b64: str, title: str, text: str, ts: str) -> bytes:
    """Байты, хеш которых подписывается. Воспроизводится в любом языке за 10 строк."""
    if not isinstance(version, int) or isinstance(version, bool):
        raise PayloadError("Версия формата должна быть целым числом")
    return (
        DOMAIN
        + _frame(str(version).encode("ascii"))
        + _frame(public_key_b64.encode("ascii"))
        + _frame(title.encode("utf-8"))
        + _frame(text.encode("utf-8"))
        + _frame(ts.encode("ascii"))
    )


def compute_digest(version: int, public_key_b64: str, title: str, text: str, ts: str) -> bytes:
    """SHA-256 от канонических байтов (32 байта)."""
    return hashlib.sha256(signing_preimage(version, public_key_b64, title, text, ts)).digest()


# --------------------------------------------------------------------------
# Модель
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Payload:
    """Подписанный документ в разобранном виде (ключ автора — внутри)."""

    title: str
    text: str
    ts: str
    signature: bytes
    public_key: bytes
    version: int = FORMAT_VERSION

    @property
    def public_key_b64(self) -> str:
        return b64u_encode(self.public_key)

    @property
    def digest(self) -> bytes:
        """Пересчитанный SHA-256 от подписанных полей."""
        return compute_digest(
            self.version, self.public_key_b64, self.title, self.text, self.ts
        )

    @property
    def signature_b64(self) -> str:
        return b64u_encode(self.signature)

    @property
    def document_id(self) -> str:
        """Короткий идентификатор документа, выводимый из подписи (не секрет)."""
        return hashlib.sha256(self.signature).hexdigest()[:12].upper()

    def local_datetime(self, tz=None) -> datetime:
        """Дата создания в часовом поясе отображения (подписью НЕ покрыта)."""
        return parse_utc(self.ts).astimezone(tz)


def build_payload(title: str, text: str, ts: str, signature: bytes,
                  public_key: bytes, version: int = FORMAT_VERSION) -> Payload:
    """Собирает :class:`Payload` с нормализацией и проверкой длин."""
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != SIGNATURE_LEN:
        raise PayloadError(f"Подпись Ed25519 должна быть ровно {SIGNATURE_LEN} байт")
    if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != PUBLIC_KEY_LEN:
        raise PayloadError(f"Открытый ключ Ed25519 должен быть {PUBLIC_KEY_LEN} байт")
    title = normalize_title(title)
    text = normalize_text(text)
    parse_utc(ts)
    return Payload(
        title=title, text=text, ts=ts, signature=bytes(signature),
        public_key=bytes(public_key), version=version,
    )


# --------------------------------------------------------------------------
# Сериализация: JSON строго фиксированного состава
# --------------------------------------------------------------------------


def dumps(payload: Payload) -> bytes:
    """Компактный JSON с фиксированным порядком ключей (UTF-8, без пробелов)."""
    obj: dict[str, Any] = {
        "v": payload.version,
        "pk": payload.public_key_b64,
        "title": payload.title,
        "text": payload.text,
        "ts": payload.ts,
        "sig": payload.signature_b64,
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise PayloadError(f"Повторяющийся ключ JSON: {key!r}")
        seen[key] = value
    return seen


def loads(data: bytes | str) -> Payload:
    """Строгий разбор JSON-полезной нагрузки.

    Отвергается всё, что не описано форматом: неизвестные поля, повторяющиеся
    ключи, неверные типы, не-UTC-даты, не-каноническое содержимое. Так
    верификатор не «додумывает» данные, которых не было в подписанном виде.
    """
    if isinstance(data, str):
        try:
            data = data.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise PayloadError("Полезная нагрузка не является UTF-8") from exc
    if not isinstance(data, (bytes, bytearray)):
        raise PayloadError("Полезная нагрузка должна быть bytes")
    if len(data) > MAX_JSON_BYTES:
        raise PayloadError("Полезная нагрузка слишком велика")
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PayloadError("Полезная нагрузка не является UTF-8") from exc

    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicates)
    except PayloadError:
        raise
    except json.JSONDecodeError as exc:
        raise PayloadError(f"Полезная нагрузка не является корректным JSON: {exc.msg}") from exc

    if not isinstance(obj, dict):
        raise PayloadError("Полезная нагрузка должна быть JSON-объектом")

    keys = set(obj)
    unknown = keys - set(FIELDS)
    missing = set(FIELDS) - keys
    if unknown:
        raise PayloadError(f"Неизвестные поля формата: {', '.join(sorted(unknown))}")
    if missing:
        raise PayloadError(f"Отсутствуют обязательные поля: {', '.join(sorted(missing))}")

    version = obj["v"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise PayloadError("Поле v должно быть целым числом")
    if version != FORMAT_VERSION:
        raise PayloadError(f"Неподдерживаемая версия формата: {version}")

    title, text_, ts, sig_b64, pk_b64 = (
        obj["title"], obj["text"], obj["ts"], obj["sig"], obj["pk"]
    )
    if not isinstance(title, str) or not isinstance(text_, str) or not isinstance(ts, str):
        raise PayloadError("Поля title/text/ts должны быть строками")
    if not isinstance(sig_b64, str):
        raise PayloadError("Поле sig должно быть строкой base64url")
    if not isinstance(pk_b64, str):
        raise PayloadError("Поле pk должно быть строкой base64url")

    # Каноничность: разобранные значения обязаны совпадать с нормализованными,
    # иначе в подписанном тексте могли быть «невидимые» различия.
    if normalize_title(title) != title:
        raise PayloadError("Заголовок не в каноническом виде")
    if normalize_text(text_) != text_:
        raise PayloadError("Содержимое не в каноническом виде")

    public_key = normalize_public_key(pk_b64)
    parse_utc(ts)
    try:
        signature = b64u_decode(sig_b64)
    except EncodingError as exc:
        raise PayloadError(f"Подпись: {exc}") from exc
    if len(signature) != SIGNATURE_LEN:
        raise PayloadError(f"Подпись Ed25519 должна быть {SIGNATURE_LEN} байт")

    return Payload(
        title=title, text=text_, ts=ts, signature=signature,
        public_key=public_key, version=version,
    )
