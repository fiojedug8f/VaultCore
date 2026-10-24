"""Личность автора: ключ в хранилище ОС + открытые метаданные.

``identity.json`` намеренно содержит только открытый ключ и служебные поля.
Он не является источником истины: при каждом запуске открытый ключ
пересчитывается из сида, и если файл подменили — приложение отказывается
работать с «чужой» личностью, вместо того чтобы молча подписывать документы
не тем ключом.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from . import canonical, crypto, paths
from .b64util import b64u_decode, b64u_encode
from .keystore import Keystore, KeystoreError, resolve_keystore


class IdentityError(KeystoreError):
    """Личность автора не может быть установлена."""


@dataclass(frozen=True)
class Identity:
    public_key: bytes
    backend: str
    backend_description: str
    ephemeral: bool
    created_at: str

    @property
    def public_b64(self) -> str:
        return b64u_encode(self.public_key)

    @property
    def fingerprint(self) -> str:
        return crypto.fingerprint(self.public_key)


class IdentityService:
    """Единственное место, где приложение получает подписи автора."""

    def __init__(self, keystore: Keystore | None = None, data_dir: Path | str | None = None):
        self._data_dir = Path(data_dir) if data_dir is not None else paths.data_dir()
        self._keystore = keystore or resolve_keystore(self._data_dir)
        self._identity: Identity | None = None

    # ------------------------------------------------------------------

    @property
    def keystore(self) -> Keystore:
        return self._keystore

    @property
    def meta_path(self) -> Path:
        return self._data_dir / "identity.json"

    def identity(self) -> Identity:
        if self._identity is not None:
            return self._identity

        backend = self._keystore
        if backend.ephemeral:
            identity = Identity(
                public_key=backend.public_key(),
                backend=backend.name,
                backend_description=backend.describe(),
                ephemeral=True,
                created_at=canonical.utc_now_iso(),
            )
            self._identity = identity
            return identity

        public_key = backend.public_key()  # ключ остаётся в хранилище
        meta = self._read_meta()
        if meta is not None:
            stored = meta.get("publicKey")
            if stored != b64u_encode(public_key):
                raise IdentityError(
                    "Открытый ключ в identity.json не соответствует ключу в хранилище. "
                    "Файл метаданных подменён — подпись от имени автора заблокирована. "
                    f"Удалите {self.meta_path} только осознанно."
                )
            created_at = str(meta.get("createdAt") or canonical.utc_now_iso())
        else:
            created_at = canonical.utc_now_iso()
            self._write_meta(public_key, created_at)

        identity = Identity(
            public_key=public_key,
            backend=backend.name,
            backend_description=backend.describe(),
            ephemeral=False,
            created_at=created_at,
        )
        self._identity = identity
        return identity

    def seal(self, title: str, text: str, ts: str | None = None) -> canonical.Payload:
        """Нормализует поля, подписывает и вшивает открытый ключ в документ."""
        identity = self.identity()
        title_n = canonical.normalize_title(title) or canonical.DEFAULT_TITLE
        text_n = canonical.normalize_text(text)
        ts_n = ts or canonical.utc_now_iso()
        canonical.parse_utc(ts_n)

        # Ключ автора — часть документа (формат v2): проверяющему не нужно
        # ничего знать заранее. Ключ входит и в подписанные байты.
        public_b64 = identity.public_b64
        digest = canonical.compute_digest(
            canonical.FORMAT_VERSION, public_b64, title_n, text_n, ts_n
        )
        signature = self._keystore.sign(digest)
        return canonical.build_payload(
            title_n, text_n, ts_n, signature, identity.public_key
        )

    # ------------------------------------------------------------------

    def _read_meta(self) -> dict | None:
        path = self.meta_path
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise IdentityError(f"Файл метаданных личности повреждён: {exc}") from exc
        if not isinstance(data, dict):
            raise IdentityError("Файл метаданных личности повреждён")
        return data

    def _write_meta(self, public_key: bytes, created_at: str) -> None:
        from . import __version__

        payload = {
            "publicKey": b64u_encode(public_key),
            "fingerprint": crypto.fingerprint(public_key),
            "backend": self._keystore.name,
            "createdAt": created_at,
            "createdBy": f"VaultCore {__version__}",
            "note": "Открытый ключ. Закрытый ключ хранится только в хранилище ОС.",
        }
        path = self.meta_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
        os.replace(tmp, path)

    def public_key_bytes(self) -> bytes:
        return self.identity().public_key


def parse_public_key(text: str) -> bytes:
    """Разбирает открытый ключ из base64url (для CLI/тестов/экспорта)."""
    try:
        raw = b64u_decode(text.strip())
    except ValueError as exc:
        raise IdentityError(f"Открытый ключ не декодируется: {exc}") from exc
    if len(raw) != 32:
        raise IdentityError("Открытый ключ Ed25519 должен быть 32 байта")
    return raw
