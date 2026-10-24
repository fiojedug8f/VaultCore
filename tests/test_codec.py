"""Передаваемый код: упаковка, терпимая вставка, ссылки, отказ на мусоре."""

from __future__ import annotations

import pytest

from vaultcore import codec, document


@pytest.fixture()
def code(service) -> str:
    _, value = document.seal(service, "Заголовок", "Текст документа")
    return value


def test_code_has_prefix_and_base64url_body(code):
    assert code.startswith("VC1.")
    body = code[len("VC1."):]
    assert body and all(c.isalnum() or c in "-_" for c in body)


def test_decode_roundtrip(code):
    payload = codec.decode(code)
    assert payload.title == "Заголовок"
    assert payload.text == "Текст документа"


def test_paste_tolerates_line_breaks_and_quotes(code):
    wrapped = "«" + code[:40] + "\n" + code[40:] + "»"
    assert codec.extract(wrapped) == code


def test_extract_from_link(code):
    link = codec.build_link(code)
    assert link.startswith("vaultcore://verify?code=VC1.")
    assert codec.extract(link) == code
    web = codec.build_web_link(code)
    assert "#code=" in web
    assert codec.extract(web) == code


def test_bom_and_zero_width_stripped(code):
    assert codec.extract("\ufeff" + code) == code
    assert codec.extract(code[:10] + "\u200b" + code[10:]) == code


@pytest.mark.parametrize("bad", ["", "VC1.", "VC1.!!!!", "текст без кода"])
def test_extract_rejects_garbage(bad):
    with pytest.raises(codec.CodeError):
        codec.extract(bad)


@pytest.mark.parametrize("bad", ["VC1.", "VC1.AAAAA", "VC1.4py"])
def test_decode_rejects_bad_body(bad):
    with pytest.raises(codec.CodeError):
        codec.decode(bad)


def test_trailing_text_after_code_rejected(code):
    with pytest.raises(codec.CodeError, match="посторонний текст"):
        codec.extract(code + " и ещё что-то")


def test_code_with_padding_rejected(code):
    with pytest.raises(codec.CodeError):
        codec.decode(code + "=")


def test_is_code(code):
    assert codec.is_code(code)
    assert not codec.is_code("нет кода")
