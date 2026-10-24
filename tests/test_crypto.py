"""Примитивы: подписи, отпечатки, отказ на некорректных длинах."""

from __future__ import annotations

import pytest

from vaultcore import canonical, crypto

PK = "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg"
TS = "2026-10-21T14:32:00Z"


def _digest(text: str = "X", title: str = "T") -> bytes:
    return canonical.compute_digest(1, PK, title, text, TS)


def test_sign_and_verify(fixed_seed):
    digest = _digest()
    signature = crypto.sign_digest(fixed_seed, digest)
    public = crypto.public_from_seed(fixed_seed)
    assert len(signature) == 64
    assert crypto.verify_digest(public, digest, signature)


def test_verify_fails_for_other_digest(fixed_seed):
    digest = _digest()
    signature = crypto.sign_digest(fixed_seed, digest)
    assert not crypto.verify_digest(crypto.public_from_seed(fixed_seed), _digest("Y"), signature)


def test_verify_fails_for_other_key(fixed_seed):
    digest = _digest()
    signature = crypto.sign_digest(fixed_seed, digest)
    other_public = crypto.public_from_seed(bytes(reversed(fixed_seed)))
    assert not crypto.verify_digest(other_public, digest, signature)


def test_verify_rejects_bad_lengths(fixed_seed):
    digest = _digest()
    public = crypto.public_from_seed(fixed_seed)
    assert not crypto.verify_digest(public, digest, b"short")
    assert not crypto.verify_digest(b"short", digest, b"\x00" * 64)
    assert not crypto.verify_digest(public, b"short", b"\x00" * 64)
    with pytest.raises(crypto.CryptoError):
        crypto.sign_digest(fixed_seed, b"short")


def test_signature_short_is_16_hex_chars(fixed_seed):
    short = crypto.signature_short(crypto.sign_digest(fixed_seed, _digest()))
    assert len(short) == 16
    assert all(c in "0123456789abcdef" for c in short)


def test_fingerprint_format(fixed_seed):
    fp = crypto.fingerprint(crypto.public_from_seed(fixed_seed))
    parts = fp.split(":")
    assert len(parts) == 8
    assert all(len(p) == 2 and p == p.upper() for p in parts)


def test_fingerprint_short_is_first_8_hex_chars(fixed_seed):
    public = crypto.public_from_seed(fixed_seed)
    short = crypto.fingerprint_short(public)
    assert short == ":".join(crypto.fingerprint(public).split(":")[:4])
    assert len(short) == 11  # 8 hex-символов + 3 двоеточия


def test_public_from_seed_is_deterministic(fixed_seed):
    assert crypto.public_from_seed(fixed_seed) == crypto.public_from_seed(fixed_seed)
    assert len(crypto.public_from_seed(fixed_seed)) == 32
