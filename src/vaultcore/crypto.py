"""Криптография: только проверенные библиотеки, никакой самописной математики.

* Hash — SHA-256 (``hashlib``, OpenSSL).
* Signature — Ed25519 (``cryptography``, OpenSSL/BoringSSL).

Почему Ed25519, а не ECDSA P-256:
    * детерминированные подписи (нет источника случайности при подписи);
    * нет проблемы «неканонического» представления подписи, которая есть
      у ECDSA (malleability через ``s`` против ``n-s``) — для одноразового
      заверенного документа это важно, иначе из одной подписи можно сделать
      вторую валидную;
    * ключи и подписи короче: 32 и 64 байта — важно для кода в base64url.

Что здесь НЕ реализовано намеренно: Ed25519ph (RFC 8032 §5.1). Мы подписываем
32-байтовый SHA-256-дайджест обычным Ed25519 — это то, что требует ТЗ
(«подписывается хеш SHA-256 от конкатенации»), и это не то же самое, что
prehashed-вариант Ed25519ph; верификатор должен использовать именно
``Ed25519.verify(digest, sig)``.
"""

from __future__ import annotations

import hashlib
import hmac

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .canonical import SIGNATURE_LEN

SEED_LEN = 32
PUBLIC_KEY_LEN = 32


class CryptoError(RuntimeError):
    """Ошибка работы с ключами."""


def generate_seed() -> bytes:
    """32 случайных байта — представление закрытого ключа Ed25519."""
    return ed25519.Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def private_key_from_seed(seed: bytes) -> ed25519.Ed25519PrivateKey:
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != SEED_LEN:
        raise CryptoError(f"Сид Ed25519 должен быть {SEED_LEN} байт")
    return ed25519.Ed25519PrivateKey.from_private_bytes(bytes(seed))


def public_from_seed(seed: bytes) -> bytes:
    """Открытый ключ по сиду (всегда выводим, никогда не «принимаем на веру»)."""
    key = private_key_from_seed(seed)
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def sign_digest(seed: bytes, digest: bytes) -> bytes:
    """Ed25519-подпись 32-байтового дайджеста (64 байта)."""
    if len(digest) != 32:
        raise CryptoError("Подписывается ровно 32-байтовый SHA-256-дайджест")
    return private_key_from_seed(seed).sign(bytes(digest))


def verify_digest(public_key: bytes, digest: bytes, signature: bytes) -> bool:
    """Проверка подписи. Любая внутренняя ошибка = «недействительна»."""
    if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != PUBLIC_KEY_LEN:
        return False
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != SIGNATURE_LEN:
        return False
    if not isinstance(digest, (bytes, bytearray)) or len(digest) != 32:
        return False
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(bytes(public_key)).verify(
            bytes(signature), bytes(digest)
        )
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def fingerprint(public_key: bytes) -> str:
    """Короткий отпечаток ключа: SHA-256 → первые 8 байт → ``7F:3A:...``."""
    if len(public_key) != PUBLIC_KEY_LEN:
        raise CryptoError("Нужен 32-байтовый открытый ключ Ed25519")
    return ":".join(f"{b:02X}" for b in hashlib.sha256(public_key).digest()[:8])


def signature_short(signature: bytes) -> str:
    """«Первые 16 символов sig» из ТЗ: 8 байт подписи в hex."""
    if len(signature) != SIGNATURE_LEN:
        raise CryptoError("Нужна 64-байтовая подпись Ed25519")
    return signature[:8].hex()


def fingerprint_short(public_key: bytes) -> str:
    """Первые 8 hex-символов отпечатка: ``56:47:5A:A7``.

    Это то, что человек диктует по телефону или сверяет в мессенджере.
    Полный отпечаток (8 байт) остаётся рядом — короткий лишь для сверки.
    """
    return ":".join(f"{b:02X}" for b in hashlib.sha256(public_key).digest()[:4])


def same_key(a: bytes | None, b: bytes | None) -> bool:
    """Сравнение ключей в постоянном времени."""
    if a is None or b is None:
        return False
    return hmac.compare_digest(bytes(a), bytes(b))
