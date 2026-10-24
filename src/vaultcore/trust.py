"""Источник доверенного открытого ключа + политика «доверия».

В режиме проверки ключ вшит в код (см. :mod:`vaultcore.embedded`). Замена
ключа возможна только одним способом — пересборкой с другим ключом; в UI
подменить его нельзя. Для разработки/CLI предусмотрен явный путь через
``--pubkey``, но это осознанное действие пользователя, а не «настройка».
"""

from __future__ import annotations

from pathlib import Path

from . import crypto
from .b64util import b64u_decode, b64u_encode
from .embedded import (
    EMBEDDED_AT,
    EMBEDDED_KEY_OWNER,
    EMBEDDED_PUBLIC_KEY_B64,
    embedded_public_key,
    has_embedded_key,
)

__all__ = [
    "trusted_public_key",
    "trusted_fingerprint",
    "trusted_source",
    "trusted_info",
    "load_public_key_file",
    "save_public_key_file",
    "has_embedded_key",
    "EMBEDDED_KEY_OWNER",
    "EMBEDDED_AT",
]


def trusted_public_key() -> bytes | None:
    """Доверенный ключ: вшитый при сборке, иначе None."""
    try:
        return embedded_public_key()
    except ValueError:
        return None


def trusted_fingerprint() -> str | None:
    key = trusted_public_key()
    return crypto.fingerprint(key) if key else None


def trusted_source() -> str:
    return "вшит в сборку" if trusted_public_key() else "не задан"


def trusted_info() -> dict[str, str]:
    key = trusted_public_key()
    return {
        "source": trusted_source(),
        "fingerprint": crypto.fingerprint(key) if key else "",
        "publicKey": EMBEDDED_PUBLIC_KEY_B64,
        "owner": EMBEDDED_KEY_OWNER,
        "embeddedAt": EMBEDDED_AT,
    }


def load_public_key_file(path: Path | str) -> bytes:
    """Читает открытый ключ из файла: base64url в первой непустой строке."""
    text = Path(path).read_text("utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw = b64u_decode(line)
        if len(raw) != 32:
            raise ValueError("Открытый ключ Ed25519 должен быть 32 байта")
        return raw
    raise ValueError("В файле нет открытого ключа")


def save_public_key_file(public_key: bytes, path: Path | str, *, owner: str = "") -> Path:
    """Сохраняет открытый ключ в текстовый файл для публикации."""
    if len(public_key) != 32:
        raise ValueError("Открытый ключ Ed25519 должен быть 32 байта")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VaultCore — открытый ключ автора (Ed25519, base64url)",
        f"# Отпечаток: {crypto.fingerprint(public_key)}",
    ]
    if owner:
        lines.append(f"# Владелец: {owner}")
    lines.append(b64u_encode(public_key))
    target.write_text("\n".join(lines) + "\n", "utf-8")
    return target
