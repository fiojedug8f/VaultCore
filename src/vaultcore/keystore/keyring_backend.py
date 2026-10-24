"""Хранилище ОС через ``keyring``: macOS Keychain и Linux Secret Service.

Используется только там, где нет DPAPI. Ограничение, которое нужно знать:

* macOS Keychain здесь хранит секрет как generic password; атрибут
  ``kSecAttrAccessibleWhenUnlockedThisDeviceOnly`` через ``keyring`` выставить
  нельзя (это потребовало бы pyobjc и прямых вызовов Security.framework).
  Практическая разница: элемент не синхронизируется через iCloud Keychain
  только если он создан с этим атрибутом, поэтому полагаться на это нельзя.
* Linux: Secret Service (gnome-keyring/KWallet) — разблокировка хранилища
  зависит от сессии пользователя.

Поэтому на этих платформах в README честно написано: уровень защиты ниже, чем
DPAPI, и для сценария «недоверенный автор» нужен аппаратный токен.
"""

from __future__ import annotations

from .base import Keystore, KeystoreError

SERVICE_NAME = "VaultCore"
ACCOUNT_NAME = "ed25519-seed-v1"


def _keyring():
    try:
        import keyring  # noqa: PLC0415 - необязательная зависимость
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise KeystoreError(
            "Модуль keyring не установлен. Установите extras: "
            'pip install "vaultcore[crossplatform]"'
        ) from exc
    return keyring


def _backend_is_usable(keyring) -> bool:
    try:
        backend = keyring.get_keyring()
        name = getattr(backend, "name", type(backend).__name__).lower()
        return "fail" not in name and "null" not in name
    except Exception:  # noqa: BLE001
        return False


class KeyringKeystore(Keystore):
    """Сид как «пароль» в системном хранилище секретов."""

    name = "keyring"

    def __init__(self, service: str = SERVICE_NAME, account: str = ACCOUNT_NAME) -> None:
        self._service = service
        self._account = account

    @staticmethod
    def available() -> bool:
        try:
            return _backend_is_usable(_keyring())
        except KeystoreError:
            return False

    def describe(self) -> str:
        return "системное хранилище секретов (keyring: Keychain / Secret Service)"

    def exists(self) -> bool:
        try:
            return _keyring().get_password(self._service, self._account) is not None
        except Exception:  # noqa: BLE001
            return False

    def _load_or_create_seed(self) -> bytes:
        import base64

        from .. import crypto

        keyring = _keyring()
        stored = keyring.get_password(self._service, self._account)
        if stored:
            try:
                seed = base64.b64decode(stored.encode("ascii"), validate=True)
            except Exception as exc:  # noqa: BLE001
                raise KeystoreError("Секрет в хранилище ОС повреждён") from exc
            if len(seed) != 32:
                raise KeystoreError("Секрет в хранилище ОС имеет неверную длину")
            return seed

        seed = crypto.generate_seed()
        try:
            keyring.set_password(
                self._service, self._account, base64.b64encode(seed).decode("ascii")
            )
        except Exception as exc:  # noqa: BLE001
            raise KeystoreError(f"Не удалось сохранить ключ в хранилище ОС: {exc}") from exc
        return seed

    def destroy(self) -> None:
        try:
            _keyring().delete_password(self._service, self._account)
        except Exception:  # noqa: BLE001 - удаление «чего нет» не ошибка
            pass
