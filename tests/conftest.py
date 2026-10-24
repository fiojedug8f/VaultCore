"""Общие фикстуры тестов.

Криптография и формат проверяются без интерфейса: это главное, что должно
работать «всегда», независимо от GUI и платформы.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Qt-тесты не должны открывать окна на рабочем столе.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from vaultcore import crypto  # noqa: E402
from vaultcore.identity import IdentityService  # noqa: E402
from vaultcore.keystore.base import Keystore  # noqa: E402

#: Детерминированный сид для тестов и вектора формата.
FIXED_SEED = bytes(range(32))


class FixedSeedKeystore(Keystore):
    """Хранилище с заранее известным сидом — воспроизводимые подписи."""

    name = "test-fixed"

    def __init__(self, seed: bytes = FIXED_SEED) -> None:
        self._seed = seed

    def describe(self) -> str:
        return "тестовое хранилище (детерминированный сид)"

    def exists(self) -> bool:
        return True

    def _load_or_create_seed(self) -> bytes:
        return self._seed


@pytest.fixture()
def tmp_path():
    """Временный каталог внутри проекта.

    Штатный ``tmp_path`` создаёт каталоги с режимом 0o700, а на этой машине
    такие каталоги затем недоступны процессу (ограничение окружения), поэтому
    тесты используют собственный каталог с обычными правами.
    """
    import uuid

    base = ROOT / ".tmp" / "pytest"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid.uuid4().hex[:12]
    path.mkdir()
    return path


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Изолированный каталог данных: ничего не пишем в реальный %APPDATA%."""
    monkeypatch.setenv("POI_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def fixed_seed() -> bytes:
    return FIXED_SEED


@pytest.fixture()
def service(data_dir, fixed_seed) -> IdentityService:
    return IdentityService(keystore=FixedSeedKeystore(fixed_seed), data_dir=data_dir)


@pytest.fixture()
def public_key(fixed_seed) -> bytes:
    return crypto.public_from_seed(fixed_seed)


@pytest.fixture(autouse=True)
def _no_embedded_key(monkeypatch):
    """Тесты не зависят от того, вшит ли ключ в dev-сборку.

    Доверенный ключ проверяется отдельными тестами, передавая его явно.
    """
    from vaultcore import embedded

    monkeypatch.setattr(embedded, "EMBEDDED_PUBLIC_KEY_B64", "")
    monkeypatch.setattr(embedded, "EMBEDDED_KEY_OWNER", "")
    return None


@pytest.fixture()
def embedded_key(monkeypatch, public_key):
    """Имитирует сборку «только проверка»: доверенный ключ вшит в код."""
    from vaultcore import embedded
    from vaultcore.b64util import b64u_encode

    monkeypatch.setattr(embedded, "EMBEDDED_PUBLIC_KEY_B64", b64u_encode(public_key))
    monkeypatch.setattr(embedded, "EMBEDDED_KEY_OWNER", "Тестовый автор")
    return public_key


@pytest.fixture()
def foreign_service(data_dir) -> IdentityService:
    """Другой автор: его подписи не должны приниматься."""
    seed = bytes(reversed(FIXED_SEED))
    return IdentityService(keystore=FixedSeedKeystore(seed), data_dir=data_dir / "foreign")
