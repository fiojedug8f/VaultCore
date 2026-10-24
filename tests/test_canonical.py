"""Формат кода v1: канонические байты, строгий разбор, вектор для независимой проверки."""

from __future__ import annotations

import json

import pytest

from vaultcore import canonical, codec, crypto
from vaultcore.b64util import EncodingError, b64u_decode, b64u_encode

# --------------------------------------------------------------------------
# Вектор для независимого верификатора (docs/FORMAT.md §6)
# --------------------------------------------------------------------------

#: Фиксированные поля вектора — их же использует документация формата.
VECTOR_TITLE = "Вектор формата"
VECTOR_TEXT = "Проверка независимого верификатора VaultCore."
VECTOR_TS = "2026-10-21T14:32:00Z"
VECTOR_PUBKEY = "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg"
VECTOR_FINGERPRINT = "56:47:5A:A7:54:63:47:4C"
VECTOR_FINGERPRINT_SHORT = "56:47:5A:A7"
VECTOR_DIGEST = "64bb7072d025876877a5a2865d8360c1a3cb172e5740c6a599fd0f65bfa0b42a"
VECTOR_SIG = (
    "0Qp6MXDENDS60IP_5qyZo5s6jb2uUQOoUl7hYPOND6yHPiNWy-LnjBq71hhFAQGyzcWgKq005la6cWV6UZ9dDw"
)
VECTOR_CODE = (
    "VC1.eyJ2IjoxLCJwayI6IkE2RUh2X1BPRUw0ZGNOMFk1MHZBbVdmazFqQ2JwUTFmSGR5R1pCSlZNYmciLCJ0aX"
    "RsZSI6ItCS0LXQutGC0L7RgCDRhNC-0YDQvNCw0YLQsCIsInRleHQiOiLQn9GA0L7QstC10YDQutCwINC90LXQ"
    "t9Cw0LLQuNGB0LjQvNC-0LPQviDQstC10YDQuNGE0LjQutCw0YLQvtGA0LAgVmF1bHRDb3JlLiIsInRzIjoiMj"
    "AyNi0xMC0yMVQxNDozMjowMFoiLCJzaWciOiIwUXA2TVhERU5EUzYwSVBfNXF5Wm81czZqYjJ1VVFPb1VsN2hZ"
    "UE9ORDZ5SFBpTld5LUxuakJxNzFoaEZBUUd5emNXZ0txMDA1bGE2Y1dWNlVaOWREdyJ9"
)


# --------------------------------------------------------------------------
# Нормализация и канонические байты
# --------------------------------------------------------------------------


def test_text_normalized_crlf_and_edges():
    assert canonical.normalize_text("a\r\nb\rc") == "a\nb\nc"
    assert canonical.normalize_text("\n\n  текст  \n\n") == "текст"


def test_empty_text_rejected():
    with pytest.raises(canonical.PayloadError):
        canonical.normalize_text("   \n  ")


def test_control_characters_rejected():
    with pytest.raises(canonical.PayloadError):
        canonical.normalize_text("текст\x00с нулём")


def test_title_single_line_and_limit():
    assert canonical.normalize_title("  Два\nслова ") == "Два слова"
    with pytest.raises(canonical.PayloadError):
        canonical.normalize_title("x" * (canonical.MAX_TITLE_CHARS + 1))


def test_framing_is_unambiguous():
    """«A» + «B\\nC» и «A\\nB» + «C» не должны давать одинаковый префикс."""
    pk = VECTOR_PUBKEY
    left = canonical.signing_preimage(1, pk, "A", "B\nC", "2026-10-21T14:32:00Z")
    right = canonical.signing_preimage(1, pk, "A\nB", "C", "2026-10-21T14:32:00Z")
    assert left != right


def test_public_key_is_inside_signed_bytes():
    """Ключ входит в подписанные байты: подменить его без подписи нельзя."""
    ts = "2026-10-21T14:32:00Z"
    first = canonical.compute_digest(1, VECTOR_PUBKEY, "T", "X", ts)
    other_pk = b64u_encode(crypto.public_from_seed(bytes(reversed(range(32)))))
    second = canonical.compute_digest(1, other_pk, "T", "X", ts)
    assert first != second


def test_parse_utc_strict():
    assert canonical.parse_utc("2026-10-21T14:32:00Z")
    for bad in ("2026-10-21T14:32:00", "2026-10-21 14:32:00Z", "2026-13-21T14:32:00Z",
                "2026-02-30T00:00:00Z", "2026-10-21T14:32:00+03:00"):
        with pytest.raises(canonical.PayloadError):
            canonical.parse_utc(bad)


def test_normalize_public_key_strict():
    assert len(canonical.normalize_public_key(VECTOR_PUBKEY)) == 32
    with pytest.raises(canonical.PayloadError):
        canonical.normalize_public_key("AAAA")               # короткий ключ
    with pytest.raises(canonical.PayloadError):
        canonical.normalize_public_key(VECTOR_PUBKEY + "=")  # padding


# --------------------------------------------------------------------------
# Строгий разбор JSON
# --------------------------------------------------------------------------


def _payload_json(**overrides) -> str:
    base = {
        "v": 1,
        "pk": VECTOR_PUBKEY,
        "title": "Заголовок",
        "text": "Текст документа",
        "ts": "2026-10-21T14:32:00Z",
        "sig": b64u_encode(b"\x01" * 64),
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


def test_roundtrip_json():
    payload = canonical.loads(_payload_json())
    assert payload.title == "Заголовок"
    assert payload.version == 1
    assert payload.public_key_b64 == VECTOR_PUBKEY
    assert canonical.loads(canonical.dumps(payload)) == payload


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"extra": "поле"}, "Неизвестные поля"),
        ({"v": 2}, "Неподдерживаемая версия"),
        ({"v": "2"}, "целым числом"),
        ({"pk": "AAAA"}, "32 байта"),
        ({"pk": VECTOR_PUBKEY + "="}, "base64url"),
        ({"text": "  пробелы по краям  "}, "не в каноническом виде"),
        ({"text": "a\r\nb"}, "не в каноническом виде"),
        ({"ts": "2026-10-21T14:32:00"}, "формате"),
        ({"sig": b64u_encode(b"\x01" * 63)}, "64 байт"),
        ({"sig": "!!!notbase64"}, "base64url"),
        ({"title": "a\nb"}, "не в каноническом виде"),
    ],
)
def test_strict_parsing_rejects(mutation, message):
    with pytest.raises(canonical.PayloadError) as excinfo:
        canonical.loads(_payload_json(**mutation))
    assert message in str(excinfo.value)


def test_missing_field_rejected():
    data = json.loads(_payload_json())
    del data["pk"]
    with pytest.raises(canonical.PayloadError, match="Отсутствуют"):
        canonical.loads(json.dumps(data))


def test_duplicate_keys_rejected():
    raw = (
        '{"v":1,"pk":"%s","title":"a","text":"b","ts":"2026-10-21T14:32:00Z",'
        '"sig":"%s","sig":"%s"}'
    ) % (VECTOR_PUBKEY, b64u_encode(b"\x01" * 64), b64u_encode(b"\x02" * 64))
    with pytest.raises(canonical.PayloadError, match="Повторяющийся ключ"):
        canonical.loads(raw)


def test_not_json():
    with pytest.raises(canonical.PayloadError):
        canonical.loads("не json")


def test_oversized_json_rejected():
    huge = '{"v":1,"title":"a","text":"' + "x" * (canonical.MAX_JSON_BYTES + 10) + '"}'
    with pytest.raises(canonical.PayloadError, match="слишком велика"):
        canonical.loads(huge)


# --------------------------------------------------------------------------
# base64url
# --------------------------------------------------------------------------


def test_b64url_roundtrip_and_canonical():
    data = bytes(range(256))
    encoded = b64u_encode(data)
    assert "=" not in encoded
    assert b64u_decode(encoded) == data
    with pytest.raises(EncodingError):
        b64u_decode(encoded + "=")
    with pytest.raises(EncodingError):
        b64u_decode("abc$def")


# --------------------------------------------------------------------------
# Верификация вектора
# --------------------------------------------------------------------------


def test_format_vector(fixed_seed):
    """Вектор воспроизводим: независимый верификатор должен получить те же значения."""
    assert crypto.public_from_seed(fixed_seed) == b64u_decode(VECTOR_PUBKEY)
    assert crypto.fingerprint(crypto.public_from_seed(fixed_seed)) == VECTOR_FINGERPRINT
    assert crypto.fingerprint_short(crypto.public_from_seed(fixed_seed)) == VECTOR_FINGERPRINT_SHORT

    digest = canonical.compute_digest(1, VECTOR_PUBKEY, VECTOR_TITLE, VECTOR_TEXT, VECTOR_TS)
    assert digest.hex() == VECTOR_DIGEST

    signature = crypto.sign_digest(fixed_seed, digest)
    assert b64u_encode(signature) == VECTOR_SIG

    payload = canonical.build_payload(
        VECTOR_TITLE, VECTOR_TEXT, VECTOR_TS, signature, b64u_decode(VECTOR_PUBKEY)
    )
    assert codec.encode(payload) == VECTOR_CODE

    parsed = codec.decode(VECTOR_CODE)
    assert parsed.title == VECTOR_TITLE
    assert parsed.public_key_b64 == VECTOR_PUBKEY
    assert parsed.digest == digest
    assert crypto.verify_digest(parsed.public_key, parsed.digest, parsed.signature)


def test_vector_is_stable(fixed_seed):
    """Тот же сид + те же поля = та же подпись (Ed25519 детерминирован)."""
    digest = canonical.compute_digest(1, VECTOR_PUBKEY, VECTOR_TITLE, VECTOR_TEXT, VECTOR_TS)
    assert crypto.sign_digest(fixed_seed, digest) == crypto.sign_digest(fixed_seed, digest)
