"""Сборка и проверка документа: единственный путь «запечатать» и «проверить».

Модель мультипользовательская: закрытый ключ есть только у автора, открытый —
внутри самого кода документа. Проверяющий не настраивает «чью-то» сборку: он
получает документ и проверяет математику, а подлинность автора подтверждает
сверкой отпечатка ключа по независимому каналу (мессенджер, сайт, визитка).

Проверка всегда пересчитывает дайджест из разобранных полей. В коде документа
дайджеста нет вовсе: если бы он там был, верификатор мог бы случайно проверять
подпись от «приложенного» дайджеста, а не от содержимого.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from . import canonical, codec, crypto
from .identity import IdentityService
from .trust import trusted_public_key

Status = Literal["valid", "invalid", "malformed"]
Trust = Literal["pinned", "self-signed", "mismatch"]


@dataclass(frozen=True)
class Check:
    """Один пункт протокола проверки — ровно то, что показывается пользователю."""

    key: str
    title: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class Verification:
    status: Status
    payload: canonical.Payload | None
    checks: tuple[Check, ...] = field(default_factory=tuple)
    reason: str = ""
    #: «pinned» — ключ совпал с вшитым/заданным; «self-signed» — ключ взят из
    #: документа и не сверен; «mismatch» — ключ не тот, что ожидали.
    trust: Trust = "self-signed"

    @property
    def ok(self) -> bool:
        return self.status == "valid"

    @property
    def show_content(self) -> bool:
        """Показывать ли содержимое.

        Требование ТЗ: при подделке содержимое не показывается (или показывается
        только с явной пометкой). Мы не показываем содержимое при недействительной
        подписи — иначе «документ-победитель» с подменённым текстом читался бы как
        настоящий, а красная плашка легко теряется.
        """
        return self.status == "valid"

    @property
    def author_fingerprint(self) -> str:
        return crypto.fingerprint(self.payload.public_key) if self.payload else ""

    @property
    def author_fingerprint_short(self) -> str:
        return crypto.fingerprint_short(self.payload.public_key) if self.payload else ""


def seal(service: IdentityService, title: str, text: str, ts: str | None = None) -> tuple[canonical.Payload, str]:
    """Запечатывает документ. Возвращает Payload (с ключом внутри) и код."""
    payload = service.seal(title=title, text=text, ts=ts)
    return payload, codec.encode(payload)


def verify(code_text: str, expected_public_key: bytes | None = None, *,
           use_embedded_key: bool = True) -> Verification:
    """Полная проверка кода. Сеть не используется.

    ``expected_public_key`` — ключ, которому *обязан* соответствовать документ
    (например, отпечаток, полученный от автора по другому каналу). Это не
    «ключ для проверки подписи»: подпись всегда проверяется ключом из документа.
    ``use_embedded_key`` — учитывать ключ, вшитый в сборку (если он есть).
    """
    checks: list[Check] = []

    try:
        payload = codec.decode(code_text)
    except (codec.CodeError, canonical.PayloadError) as exc:
        checks.append(Check("format", "Формат кода", False, str(exc)))
        return Verification("malformed", None, tuple(checks), str(exc))

    checks.append(Check("format", "Формат кода", True, "Код разобран, состав полей строго по формату"))

    version_ok = payload.version == canonical.FORMAT_VERSION
    checks.append(
        Check(
            "version",
            "Версия формата",
            version_ok,
            f"v{payload.version}" + ("" if version_ok else " — не поддерживается"),
        )
    )
    if not version_ok:
        return Verification("invalid", payload, tuple(checks), "Неподдерживаемая версия формата")

    digest = payload.digest
    checks.append(
        Check(
            "digest",
            "Целостность содержимого (SHA-256)",
            True,
            f"Пересчитано из подписанных полей: {digest.hex()[:16]}…",
        )
    )

    # Подпись проверяется ключом, который пришёл В ДОКУМЕНТЕ.
    signature_ok = crypto.verify_digest(payload.public_key, digest, payload.signature)
    checks.append(
        Check(
            "signature",
            "Подпись Ed25519",
            signature_ok,
            (
                f"Сходится с ключом автора {crypto.fingerprint(payload.public_key)}"
                if signature_ok
                else "Подпись не соответствует содержимому или ключу автора"
            ),
        )
    )
    if not signature_ok:
        return Verification(
            "invalid",
            payload,
            tuple(checks),
            "Документ изменён или подпись недействительна",
        )

    # Сверка с ожидаемым ключом: вшитый в сборку или переданный явно.
    expected = expected_public_key
    if expected is None and use_embedded_key:
        expected = trusted_public_key()

    if expected is None:
        checks.append(
            Check(
                "trust",
                "Ключ автора",
                True,
                f"{crypto.fingerprint(payload.public_key)} — взят из документа, "
                "не сверен по независимому каналу",
            )
        )
        return Verification(
            "valid",
            payload,
            tuple(checks),
            "Документ подлинный: подпись математически верна. "
            "Подлинность автора сверьте по отпечатку ключа.",
            trust="self-signed",
        )

    matches = crypto.same_key(expected, payload.public_key)
    checks.append(
        Check(
            "trust",
            "Ключ автора совпадает с ожидаемым",
            matches,
            (
                f"ожидался {crypto.fingerprint(expected)}, "
                f"в документе {crypto.fingerprint(payload.public_key)}"
            ),
        )
    )
    if not matches:
        return Verification(
            "invalid",
            payload,
            tuple(checks),
            "Документ подписан другим ключом, чем ожидалось",
            trust="mismatch",
        )

    return Verification(
        "valid",
        payload,
        tuple(checks),
        "Документ подлинный, содержимое не изменялось",
        trust="pinned",
    )


def verify_from_trusted(payload: canonical.Payload, expected: bytes) -> bool:
    """Проверка уже разобранного Payload: подпись + совпадение ключа."""
    return (
        crypto.verify_digest(payload.public_key, payload.digest, payload.signature)
        and crypto.same_key(expected, payload.public_key)
    )
