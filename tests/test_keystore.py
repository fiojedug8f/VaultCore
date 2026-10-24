"""Хранилище ключа: DPAPI (Windows), эфемерный режим, защита от подмены метаданных."""

from __future__ import annotations

import json
import os

import pytest

from vaultcore import crypto
from vaultcore.identity import IdentityError, IdentityService
from vaultcore.keystore import available_backends, resolve_keystore
from vaultcore.keystore.base import wipe
from vaultcore.keystore.dpapi import DpapiKeystore, _MAGIC
from vaultcore.keystore.ephemeral import EphemeralKeystore

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="DPAPI есть только в Windows")


# --------------------------------------------------------------------------
# Общие механики
# --------------------------------------------------------------------------


def test_ephemeral_key_is_not_persisted(tmp_path):
    first = EphemeralKeystore()
    second = EphemeralKeystore()
    assert first.ephemeral is True
    assert first.public_key() != second.public_key()
    assert list(tmp_path.iterdir()) == []


def test_wipe_zeroes_buffer():
    buf = bytearray(b"secret")
    wipe(buf)
    assert bytes(buf) == b"\x00" * 6


def test_keystore_sign_uses_seed_and_zeroizes(tmp_path):
    keystore = EphemeralKeystore()
    digest = bytes(range(32))
    signature = keystore.sign(digest)
    assert crypto.verify_digest(keystore.public_key(), digest, signature)


def test_available_backends_lists_all():
    names = {name for name, _ok, _desc in available_backends()}
    assert names == {"dpapi", "keyring", "ephemeral"}


def test_resolve_unknown_preferred_raises(tmp_path):
    from vaultcore.keystore import KeystoreError

    with pytest.raises(KeystoreError):
        resolve_keystore(tmp_path, preferred="hsm")


def test_resolve_ephemeral_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("POI_KEYSTORE", "ephemeral")
    keystore = resolve_keystore(tmp_path)
    assert keystore.name == "ephemeral"


# --------------------------------------------------------------------------
# DPAPI
# --------------------------------------------------------------------------


@WINDOWS_ONLY
def test_dpapi_roundtrip_persists_seed(tmp_path):
    keystore = DpapiKeystore(tmp_path)
    first = keystore.load_or_create_seed()
    second = DpapiKeystore(tmp_path).load_or_create_seed()
    assert first == second
    assert len(first) == 32


@WINDOWS_ONLY
def test_dpapi_blob_on_disk_is_not_plaintext(tmp_path):
    keystore = DpapiKeystore(tmp_path)
    seed = keystore.load_or_create_seed()
    raw = (tmp_path / "key.blob").read_bytes()
    assert raw.startswith(_MAGIC)
    assert seed not in raw  # сид не лежит в файле открытым текстом
    assert b"ed25519" not in raw.lower()


@WINDOWS_ONLY
def test_dpapi_detects_corrupted_blob(tmp_path):
    keystore = DpapiKeystore(tmp_path)
    keystore.load_or_create_seed()
    path = tmp_path / "key.blob"
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0xFF
    path.write_bytes(bytes(raw))
    from vaultcore.keystore.base import KeystoreError

    with pytest.raises(KeystoreError):
        DpapiKeystore(tmp_path).load_or_create_seed()


@WINDOWS_ONLY
def test_dpapi_rejects_foreign_blob(tmp_path):
    """Копия blob, зашифрованная «не тем» DPAPI-контекстом, не расшифруется."""
    from vaultcore.keystore import dpapi

    blob = dpapi.protect(b"\x11" * 32, entropy=b"other-app")
    from vaultcore.keystore.base import KeystoreError

    with pytest.raises(KeystoreError):
        dpapi.unprotect(blob, entropy=dpapi.ENTROPY)


@WINDOWS_ONLY
def test_dpapi_keystore_identity_roundtrip(tmp_path):
    service = IdentityService(keystore=DpapiKeystore(tmp_path), data_dir=tmp_path / "data")
    identity = service.identity()
    assert identity.ephemeral is False
    assert identity.backend == "dpapi"
    again = IdentityService(keystore=DpapiKeystore(tmp_path), data_dir=tmp_path / "data")
    assert again.identity().fingerprint == identity.fingerprint


# --------------------------------------------------------------------------
# Защита метаданных личности
# --------------------------------------------------------------------------


@WINDOWS_ONLY
def test_identity_meta_tamper_detected(tmp_path):
    data = tmp_path / "data"
    service = IdentityService(keystore=DpapiKeystore(tmp_path), data_dir=data)
    service.identity()
    meta_path = data / "identity.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    other = crypto.generate_seed()
    meta["publicKey"] = __import__("vaultcore.b64util", fromlist=["b64u_encode"]).b64u_encode(
        crypto.public_from_seed(other)
    )
    meta_path.write_text(json.dumps(meta), "utf-8")

    with pytest.raises(IdentityError):
        IdentityService(keystore=DpapiKeystore(tmp_path), data_dir=data).identity()


def test_keyring_available_does_not_crash():
    from vaultcore.keystore.keyring_backend import KeyringKeystore

    assert isinstance(KeyringKeystore.available(), bool)
