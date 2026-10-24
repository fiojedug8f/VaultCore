"""Примеры из ``examples/``: документ обязан проверяться демонстрационным ключом."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vaultcore import codec, crypto, document
from vaultcore.trust import load_public_key_file

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(scope="module")
def public_key() -> bytes:
    return load_public_key_file(EXAMPLES / "demo_public_key.txt")


def test_sample_code_verifies(public_key):
    code = (EXAMPLES / "sample_code.txt").read_text("utf-8").strip()
    result = document.verify(code, public_key)
    assert result.status == "valid", result.reason
    assert result.payload is not None
    assert result.payload.title


def test_sample_poi_matches_sample_code(public_key):
    from vaultcore.storage import load_document

    from_poi = load_document(EXAMPLES / "sample.poi")
    from_txt = (EXAMPLES / "sample_code.txt").read_text("utf-8").strip()
    assert from_poi == from_txt


def test_sample_pdf_contains_verifiable_signature(public_key):
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(str(EXAMPLES / "sample_document.pdf"))
    text = " ".join((" ".join((page.extract_text() or "") for page in reader.pages)).split())
    payload = codec.decode((EXAMPLES / "sample_code.txt").read_text("utf-8").strip())

    # Подпись и дайджест присутствуют в текстовом слое: PDF самодостаточен.
    assert payload.signature_b64 in text
    assert payload.digest.hex() in text
    assert "не имеет юридической силы" in text
    assert payload.ts in text


def test_link_file_points_to_same_code():
    code = (EXAMPLES / "sample_code.txt").read_text("utf-8").strip()
    link = (EXAMPLES / "sample_link.txt").read_text("utf-8").strip()
    assert link.startswith("vaultcore://verify?code=")
    assert codec.extract(link) == code


def test_examples_readme_lists_actual_signature():
    payload = codec.decode((EXAMPLES / "sample_code.txt").read_text("utf-8").strip())
    readme = (EXAMPLES / "README.md").read_text("utf-8")
    assert payload.signature_b64 in readme
    assert payload.digest.hex() in readme


def test_demo_key_is_marked_as_demo():
    text = (EXAMPLES / "demo_public_key.txt").read_text("utf-8")
    assert "НЕ используйте" in text
    assert re.search(r"[0-9A-F]{2}(:[0-9A-F]{2}){7}", text)
