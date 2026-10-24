"""Консольный интерфейс: сквозной сценарий «запечатать → проверить»."""

from __future__ import annotations

import pytest

from vaultcore import cli


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setenv("POI_DATA_DIR", str(tmp_path / "data"))
    # Без POI_KEYSTORE: берётся платформенное хранилище (в Windows — DPAPI),
    # поэтому ключ переживает отдельные вызовы CLI, как у настоящего автора.
    monkeypatch.delenv("POI_KEYSTORE", raising=False)
    return tmp_path


def _public_key() -> str:
    from vaultcore.identity import IdentityService

    return IdentityService().identity().public_b64


def _verify(code: str, *extra: str) -> int:
    # «--code=…» устойчиво к значениям, начинающимся с «-» (base64url).
    return cli.main(["verify", f"--code={code}", *extra])


def test_seal_and_verify_roundtrip(cli_env, capsys):
    assert cli.main(["seal", "--title", "Заявление", "--text", "Текст намерения",
                     "--ts", "2026-10-21T14:32:00Z", "--out", str(cli_env / "d.poi")]) == 0
    code = capsys.readouterr().out.strip()
    assert code.startswith("VC1.")

    assert _verify(code, f"--pubkey={_public_key()}") == 0
    out = capsys.readouterr().out
    assert "valid" in out
    assert "Текст намерения" in out
    assert "Отпечаток ключа автора" in out


def test_verify_without_pin_is_still_valid(cli_env, capsys):
    """Без сверки отпечатка документ самодостаточен: ключ приехал внутри кода."""
    cli.main(["seal", "--text", "Текст", "--ts", "2026-10-21T14:32:00Z"])
    code = capsys.readouterr().out.strip()
    assert _verify(code) == cli.EXIT_OK


def test_verify_with_wrong_pin_fails(cli_env, capsys):
    cli.main(["seal", "--text", "Текст", "--ts", "2026-10-21T14:32:00Z"])
    code = capsys.readouterr().out.strip()
    wrong = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    assert wrong != _public_key()
    assert _verify(code, f"--pubkey={wrong}") == cli.EXIT_INVALID


def test_verify_tampered_returns_invalid(cli_env, capsys):
    cli.main(["seal", "--text", "Текст", "--ts", "2026-10-21T14:32:00Z"])
    code = capsys.readouterr().out.strip()
    broken = code[:-4] + ("AAAA" if not code.endswith("AAAA") else "BBBB")
    assert _verify(broken, f"--pubkey={_public_key()}") == cli.EXIT_INVALID


def test_render_and_pdf_output(cli_env, capsys):
    cli.main(["seal", "--text", "Текст", "--ts", "2026-10-21T14:32:00Z",
              "--out", str(cli_env / "d.poi"), "--pdf", str(cli_env / "d.pdf")])
    capsys.readouterr()
    assert (cli_env / "d.pdf").read_bytes().startswith(b"%PDF")
    assert cli.main(["render", "--code-file", str(cli_env / "d.poi"),
                     "--out", str(cli_env / "again.pdf")]) == 0
    assert (cli_env / "again.pdf").stat().st_size > 10_000


def test_poi_file_roundtrip(cli_env, capsys):
    cli.main(["seal", "--text", "Текст из файла", "--ts", "2026-10-21T14:32:00Z",
              "--out", str(cli_env / "doc.poi")])
    capsys.readouterr()
    content = (cli_env / "doc.poi").read_text("utf-8")
    assert "VC1." in content
    assert "Открытый ключ автора" in content
    assert cli.main(["verify", "--code-file", str(cli_env / "doc.poi"),
                     f"--pubkey={_public_key()}"]) == 0


def test_pubkey_command(cli_env, capsys):
    assert cli.main(["pubkey", "--out", str(cli_env / "pub.txt")]) == 0
    out = capsys.readouterr().out.strip()
    assert len(out) == 43
    assert (cli_env / "pub.txt").exists()
