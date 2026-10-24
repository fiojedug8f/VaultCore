"""Базовый интерфейс хранилища закрытого ключа.

Ключевой инвариант: закрытый ключ существует в открытом виде только внутри
вызова :meth:`Keystore.sign` и только в памяти процесса. Ни один backend не
обязан и не имеет права возвращать его наружу — наружу отдаётся только
открытый ключ (он и так публичный) и подпись.
"""

from __future__ import annotations

import abc


class KeystoreError(RuntimeError):
    """Хранилище недоступно или ключ невозможно использовать."""


def wipe(buf: bytearray | None) -> None:
    """Затирает содержимое буфера (best effort: см. docs/SECURITY.md)."""
    if not buf:
        return
    for i in range(len(buf)):
        buf[i] = 0


class Keystore(abc.ABC):
    """Абстрактное хранилище Ed25519-сида."""

    #: Имя механизма: попадает в identity.json и в интерфейс.
    name: str = "unknown"
    #: True, если ключ живёт только до перезапуска приложения.
    ephemeral: bool = False

    @abc.abstractmethod
    def _load_or_create_seed(self) -> bytes:
        """Возвращает 32-байтовый сид, создавая его при первом обращении."""

    @abc.abstractmethod
    def exists(self) -> bool:
        """Есть ли уже сохранённый ключ."""

    def destroy(self) -> None:
        """Удаляет сохранённый ключ. По умолчанию — ничего."""

    def describe(self) -> str:
        return self.name

    # ------------------------------------------------------------------
    # Публичный фасад
    # ------------------------------------------------------------------

    def load_or_create_seed(self) -> bytes:
        seed = self._load_or_create_seed()
        if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
            raise KeystoreError("Хранилище вернуло сид неверной длины")
        return bytes(seed)

    def sign(self, digest: bytes) -> bytes:
        """Подписывает дайджест, затирая сид сразу после использования."""
        from .. import crypto

        buf = bytearray(self.load_or_create_seed())
        try:
            return crypto.sign_digest(bytes(buf), digest)
        finally:
            wipe(buf)

    def public_key(self) -> bytes:
        """Открытый ключ, выведенный из сохранённого сида."""
        from .. import crypto

        buf = bytearray(self.load_or_create_seed())
        try:
            return crypto.public_from_seed(bytes(buf))
        finally:
            wipe(buf)
