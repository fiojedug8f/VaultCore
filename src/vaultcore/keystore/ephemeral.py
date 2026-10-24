"""Эфемерный ключ: крайний fallback, когда хранилища ОС нет.

ТЗ прямо разрешает такой режим, но требует отразить ограничение. Мы делаем это
в трёх местах: баннер в интерфейсе, отдельная строка в блоке заверения PDF и
раздел README. Практический смысл: автор может напечатать документы, но после
перезапуска приложения проверить их «от автора» уже нельзя — только целостность.

Ключ НЕ пишется на диск ни в каком виде.
"""

from __future__ import annotations

import secrets

from .base import Keystore, KeystoreError


class EphemeralKeystore(Keystore):
    """"Ключ на один запуск", живущий только в памяти процесса."""

    name = "ephemeral"
    ephemeral = True

    def __init__(self) -> None:
        from .. import crypto

        self._seed = crypto.generate_seed()

    @staticmethod
    def available() -> bool:
        return True

    def describe(self) -> str:
        return "эфемерный ключ в памяти (хранилище ОС недоступно)"

    def exists(self) -> bool:
        return True

    def _load_or_create_seed(self) -> bytes:
        return self._seed

    def destroy(self) -> None:
        # Сид всё равно живёт в памяти до выхода; затираем, чтобы не остался
        # в куче после «сброса» личности.
        self._seed = secrets.token_bytes(32)
        self._seed = b""
        raise KeystoreError("Эфемерный ключ уничтожен; перезапустите приложение")
