"""VaultCore — одноразовый заверенный документ (локально, без сервера).

Пакет намеренно разделён на слои, чтобы криптография и формат кода были
проверяемы без графического интерфейса:

* :mod:`vaultcore.canonical` — каноническая форма подписываемых данных;
* :mod:`vaultcore.crypto`    — Ed25519 и SHA-256 (только ``cryptography``);
* :mod:`vaultcore.codec`     — передаваемый код ``VC1.<base64url>`` и ссылки;
* :mod:`vaultcore.keystore`  — хранение закрытого ключа в хранилище ОС;
* :mod:`vaultcore.identity`  — сборка ключа и подпись;
* :mod:`vaultcore.document`  — «запечатать» и «проверить»;
* :mod:`vaultcore.render`    — PDF A4 и предпросмотр;
* :mod:`vaultcore.ui`        — PySide6-интерфейс (два режима).

ВНИМАНИЕ: создаваемые документы НЕ имеют юридической силы. См. README.md,
eula_ru.md и docs/SECURITY.md.
"""

from __future__ import annotations

APP_NAME = "VaultCore"
APP_SUBTITLE = "заверенный документ о намерении"
__version__ = "1.0.0"

__all__ = ["APP_NAME", "APP_SUBTITLE", "__version__"]
