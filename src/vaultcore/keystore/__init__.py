"""Выбор хранилища ключа: явный -> платформенный -> fallback с предупреждением.

Приоритет:

1. переменная окружения ``POI_KEYSTORE`` (``dpapi`` | ``keyring`` | ``ephemeral``);
2. платформенное умолчание: Windows — DPAPI, macOS/Linux — keyring;
3. если платформенное хранилище недоступно — эфемерный ключ.

Никакой третий вариант «сохранить ключ в файл» не предусмотрен: это прямой
запрет ТЗ и самая частая ошибка в подобных приложениях.
"""

from __future__ import annotations

import os
from pathlib import Path

from .base import Keystore, KeystoreError, wipe
from .dpapi import DpapiKeystore
from .ephemeral import EphemeralKeystore
from .keyring_backend import KeyringKeystore

__all__ = [
    "Keystore",
    "KeystoreError",
    "DpapiKeystore",
    "KeyringKeystore",
    "EphemeralKeystore",
    "resolve_keystore",
    "available_backends",
    "wipe",
]

ENV_VAR = "POI_KEYSTORE"


def _machine_scope() -> bool:
    return os.environ.get("POI_DPAPI_MACHINE_SCOPE", "").strip().lower() in {"1", "true", "yes"}


def resolve_keystore(data_dir: Path | str | None = None, preferred: str | None = None) -> Keystore:
    """Возвращает готовое к работе хранилище (не бросает, если есть fallback)."""
    from ..paths import data_dir as default_data_dir

    base = Path(data_dir) if data_dir is not None else default_data_dir()
    choice = (preferred or os.environ.get(ENV_VAR) or "").strip().lower()

    if choice and choice not in {"dpapi", "keyring", "ephemeral"}:
        raise KeystoreError(f"Неизвестное хранилище ключа: {choice!r}")

    if not choice:
        choice = "dpapi" if os.name == "nt" else "keyring"

    if choice == "dpapi":
        if DpapiKeystore.available():
            return DpapiKeystore(base, machine_scope=_machine_scope())
        if os.name == "nt":
            raise KeystoreError("DPAPI недоступен в этой сборке Windows")
        # На не-Windows явный выбор dpapi — ошибка конфигурации, а не повод
        # молча подменить хранилище.
        raise KeystoreError("DPAPI доступен только в Windows")

    if choice == "keyring":
        if KeyringKeystore.available():
            return KeyringKeystore()
        return EphemeralKeystore()

    return EphemeralKeystore()


def available_backends() -> list[tuple[str, bool, str]]:
    """Список (имя, доступно, описание) — для экрана «О приложении» и README."""
    return [
        ("dpapi", DpapiKeystore.available(), "Windows DPAPI (шифрование ключом ОС)"),
        ("keyring", KeyringKeystore.available(), "keyring: Keychain / Secret Service"),
        ("ephemeral", True, "ключ только в памяти (fallback, ограниченная пригодность)"),
    ]
