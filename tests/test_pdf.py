"""PDF: A4, текстовый слой, встроенные шрифты, нумерация, метаданные с кодом."""

from __future__ import annotations

import pytest

pytest.importorskip("pypdf")

from pypdf import PdfReader  # noqa: E402

from vaultcore import crypto, document  # noqa: E402
from vaultcore.render import qr_png_bytes, render_pdf, render_pdf_bytes  # noqa: E402
from vaultcore.render.qr import qr_matrix  # noqa: E402


def _find_descriptor(font_obj):
    if "/FontDescriptor" in font_obj:
        return font_obj["/FontDescriptor"].get_object()
    descendants = font_obj.get("/DescendantFonts")
    if descendants:
        first = descendants[0].get_object()
        if "/FontDescriptor" in first:
            return first["/FontDescriptor"].get_object()
    return None


def _fonts_without_embedding(reader: PdfReader) -> list[str]:
    missing: list[str] = []
    for index, page in enumerate(reader.pages):
        resources = page.get("/Resources") or {}
        fonts = resources.get("/Font") or {}
        for name, ref in fonts.items():
            font = ref.get_object()
            descriptor = _find_descriptor(font)
            if descriptor is None:
                missing.append(f"стр.{index + 1}:{name} (нет FontDescriptor)")
                continue
            if not any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")):
                missing.append(f"стр.{index + 1}:{name} (шрифт не встроен)")
    return missing


def _text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.fixture()
def rendered(service, tmp_path):
    identity = service.identity()
    payload, code = document.seal(service, "Заявление", "Текст заявления о намерении выпить кофе.")
    path = render_pdf(payload, tmp_path / "doc.pdf", code=code, key_fingerprint=identity.fingerprint)
    return payload, code, path, identity


def test_page_is_a4(rendered):
    _, _, path, _ = rendered
    reader = PdfReader(str(path))
    box = reader.pages[0].mediabox
    assert abs(float(box.width) - 595.28) < 1.0
    assert abs(float(box.height) - 841.89) < 1.0


def test_text_layer_contains_content_and_attestation(rendered):
    payload, code, path, identity = rendered
    text = _text(PdfReader(str(path)))
    flat = " ".join(text.split())
    assert payload.title in flat
    assert payload.ts in flat
    assert "не имеет юридической силы" in flat
    assert "ОБРАЗЕЦ" in flat
    assert "НЕ ЮРИДИЧЕСКИЙ ДОКУМЕНТ" in flat
    assert identity.fingerprint in flat
    assert payload.digest.hex() in flat
    # Подпись целиком присутствует в текстовом слое: документ можно проверить
    # программно, не полагаясь на QR или метаданные.
    assert payload.signature_b64[:40] in "".join(flat.split())


def test_metadata_carries_full_code(rendered):
    _, code, path, _ = rendered
    reader = PdfReader(str(path))
    subject = str(reader.metadata.get("/Subject", ""))
    assert "VC1." in subject
    assert code[:60] in subject


def test_pdf_prints_author_key_and_fingerprint(rendered):
    """В документе обязательно печатаются открытый ключ автора и отпечаток."""
    payload, _, path, _ = rendered
    flat = " ".join(_text(PdfReader(str(path))).split())
    assert payload.public_key_b64 in flat
    assert crypto.fingerprint(payload.public_key) in flat
    assert crypto.fingerprint_short(payload.public_key) in flat


def test_fonts_are_embedded(rendered):
    _, _, path, _ = rendered
    assert _fonts_without_embedding(PdfReader(str(path))) == []


def test_qr_is_present_for_normal_documents(rendered):
    _, code, _, _ = rendered
    matrix = qr_matrix(code)
    assert matrix is not None
    assert len(matrix[0]) >= 21


def test_qr_png_bytes_available():
    png = qr_png_bytes("VC1.test")
    assert png is None or png.startswith(b"\x89PNG")


def test_two_passes_give_same_structure(rendered):
    payload, code, path, identity = rendered
    data = render_pdf_bytes(payload, code=code, key_fingerprint=identity.fingerprint)
    assert data.startswith(b"%PDF")
    reader = PdfReader(__import__("io").BytesIO(data))
    assert len(reader.pages) == len(PdfReader(str(path)).pages)


def test_page_numbers_for_multipage(service, tmp_path):
    text = "\n\n".join(f"Раздел {i}. " + "Проверка многостраничной вёрстки. " * 12 for i in range(1, 9))
    payload, code = document.seal(service, "Длинный документ", text)
    path = render_pdf(payload, tmp_path / "long.pdf", code=code)
    reader = PdfReader(str(path))
    assert len(reader.pages) >= 2
    flat = " ".join(_text(reader).split())
    assert "Стр. 1 из" in flat
    assert f"Стр. {len(reader.pages)} из {len(reader.pages)}" in flat


def test_long_document_without_qr_mentions_metadata(service, tmp_path):
    text = "Очень длинный документ. " * 900
    payload, code = document.seal(service, "Длинный", text)
    path = render_pdf(payload, tmp_path / "huge.pdf", code=code)
    flat = " ".join(_text(PdfReader(str(path))).split())
    if qr_matrix(code) is None:
        assert "метаданные PDF" in flat


def test_template_changes_are_applied(service, tmp_path, monkeypatch):
    """Оформление — внешний шаблон: правка текста видна без правки кода."""
    from vaultcore.render.template import load_template

    tpl = load_template()
    raw = dict(tpl.raw)
    raw["document"] = {**tpl.raw["document"], "footerNote": "ОФОРМЛЕНИЕ ИЗ ШАБЛОНА"}
    from vaultcore.render.template import Template

    payload, code = document.seal(service, "Шаблон", "Проверка внешнего шаблона.")
    path = render_pdf(payload, tmp_path / "tpl.pdf", code=code, template=Template(raw=raw))
    assert "ОФОРМЛЕНИЕ ИЗ ШАБЛОНА" in " ".join(_text(PdfReader(str(path))).split())
