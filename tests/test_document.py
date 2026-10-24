"""Пять обязательных сценариев проверки + модель «ключ внутри документа»."""

from __future__ import annotations

import json

import pytest

from vaultcore import canonical, codec, crypto, document
from vaultcore.b64util import b64u_encode


def _reencode(payload: canonical.Payload, **changes) -> str:
    data = {
        "v": payload.version,
        "pk": payload.public_key_b64,
        "title": payload.title,
        "text": payload.text,
        "ts": payload.ts,
        "sig": payload.signature_b64,
    }
    data.update(changes)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "VC1." + b64u_encode(raw)


@pytest.fixture()
def sealed(service):
    payload, code = document.seal(service, "Заявление", "Текст заявления о намерении.")
    return payload, code


# --------------------------------------------------------------------------
# 1. Создание → проверка (успех)
# --------------------------------------------------------------------------


def test_seal_embeds_public_key(sealed):
    payload, code = sealed
    assert payload.public_key_b64
    assert codec.decode(code).public_key_b64 == payload.public_key_b64


def test_seal_then_verify_ok(sealed, public_key):
    payload, code = sealed
    result = document.verify(code, public_key)
    assert result.status == "valid"
    assert result.trust == "pinned"
    assert result.show_content
    assert result.payload is not None
    assert result.payload.text == payload.text
    assert result.author_fingerprint == crypto.fingerprint(public_key)
    assert all(check.ok for check in result.checks)


def test_verify_without_any_pinned_key(sealed, monkeypatch):
    """Без вшитого ключа проверяется математика: подпись + ключ из документа."""
    from vaultcore import embedded

    monkeypatch.setattr(embedded, "EMBEDDED_PUBLIC_KEY_B64", "")
    _, code = sealed
    result = document.verify(code)
    assert result.status == "valid"
    assert result.trust == "self-signed"
    assert result.payload is not None
    assert "сверьте" in result.reason.lower()


def test_seal_is_deterministic_in_fields(service):
    payload, _ = document.seal(service, "Заголовок", "Текст", ts="2026-10-21T14:32:00Z")
    assert payload.ts == "2026-10-21T14:32:00Z"
    digest = canonical.compute_digest(
        1, payload.public_key_b64, payload.title, payload.text, payload.ts
    )
    assert payload.digest == digest
    assert crypto.verify_digest(payload.public_key, digest, payload.signature)


def test_seal_rejects_empty_text(service):
    with pytest.raises(canonical.PayloadError):
        document.seal(service, "Заголовок", "   ")


def test_seal_rejects_bad_ts(service):
    with pytest.raises(canonical.PayloadError):
        document.seal(service, "Заголовок", "Текст", ts="2026-10-21 14:32")


def test_title_defaults_when_empty(service):
    payload, code = document.seal(service, "   ", "Текст документа")
    assert payload.title == canonical.DEFAULT_TITLE
    assert document.verify(code, payload.public_key).status == "valid"


# --------------------------------------------------------------------------
# 2–3. Изменение содержимого / даты → провал
# --------------------------------------------------------------------------


def test_modified_text_fails(sealed, public_key):
    payload, _ = sealed
    tampered = _reencode(payload, text=payload.text + " (дописано позже)")
    result = document.verify(tampered, public_key)
    assert result.status == "invalid"
    assert not result.show_content
    assert any(c.key == "signature" and not c.ok for c in result.checks)


def test_modified_title_fails(sealed, public_key):
    payload, _ = sealed
    assert document.verify(_reencode(payload, title="Другой документ"), public_key).status == "invalid"


def test_modified_date_fails(sealed, public_key):
    payload, _ = sealed
    assert document.verify(_reencode(payload, ts="2020-01-01T00:00:00Z"), public_key).status == "invalid"


def test_modified_date_by_one_second_fails(sealed, public_key):
    payload, _ = sealed
    alt = "2026-10-21T14:32:01Z" if payload.ts != "2026-10-21T14:32:01Z" else "2026-10-21T14:31:59Z"
    assert document.verify(_reencode(payload, ts=alt), public_key).status == "invalid"


# --------------------------------------------------------------------------
# 4. Подмена подписи → провал
# --------------------------------------------------------------------------


def test_modified_signature_fails(sealed, public_key):
    payload, _ = sealed
    broken = bytearray(payload.signature)
    broken[0] ^= 0x01
    tampered = _reencode(payload, sig=b64u_encode(bytes(broken)))
    assert document.verify(tampered, public_key).status == "invalid"


def test_signature_of_other_document_fails(sealed, public_key, service):
    payload, _ = sealed
    other = service.seal("Заявление", "Другой текст")
    tampered = _reencode(payload, sig=other.signature_b64)
    assert document.verify(tampered, public_key).status == "invalid"


# --------------------------------------------------------------------------
# 5. Чужой ключ (и подмена ключа в коде) → провал
# --------------------------------------------------------------------------


def test_foreign_key_fails_pinned_check(foreign_service, public_key):
    _, code = document.seal(foreign_service, "Заявление", "Текст")
    result = document.verify(code, public_key)
    assert result.status == "invalid"
    assert result.trust == "mismatch"
    assert "другим ключом" in result.reason


def test_foreign_document_is_valid_without_pin(foreign_service):
    """Чужой документ самодостаточен: математика верна, ключ — из документа."""
    _, code = document.seal(foreign_service, "Заявление", "Текст")
    result = document.verify(code, use_embedded_key=False)
    assert result.status == "valid"
    assert result.trust == "self-signed"
    assert result.payload.public_key == foreign_service.identity().public_key


def test_replaced_public_key_fails(sealed, public_key):
    """Подмена ключа в коде ломает подпись: ключ входит в подписанные байты."""
    payload, _ = sealed
    attacker = crypto.public_from_seed(bytes(reversed(range(32))))
    tampered = _reencode(payload, pk=b64u_encode(attacker))
    result = document.verify(tampered, public_key)
    assert result.status == "invalid"
    assert not result.show_content


# --------------------------------------------------------------------------
# Прочее: мусор, версия
# --------------------------------------------------------------------------


def test_malformed_code(public_key):
    result = document.verify("это не документ", public_key)
    assert result.status == "malformed"
    assert result.payload is None
    assert result.checks and not result.checks[0].ok


def test_unsupported_version_rejected(sealed, public_key):
    payload, _ = sealed
    tampered = _reencode(payload, v=2)
    result = document.verify(tampered, public_key)
    assert result.status in {"malformed", "invalid"}
    assert not result.show_content
