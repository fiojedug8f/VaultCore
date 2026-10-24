"""Консольный интерфейс (без GUI) — удобно для скриптов и для проверки в CI.

Коды возврата:
    0 — успех (для verify: документ подлинный);
    1 — документ недействителен / не разобран;
    2 — ошибка окружения (нет ключа, нет файла, нет шрифтов и т.п.);
    3 — документ подлинный по подписи, но доверенный ключ не задан.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME, __version__, canonical, codec, crypto, document, eula as eula_mod
from .identity import IdentityService
from .keystore import KeystoreError
from .render import render_pdf
from .storage import load_document, save_document
from .trust import load_public_key_file, save_public_key_file, trusted_fingerprint, trusted_public_key

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ENV = 2
EXIT_UNTRUSTED = 3


def _read_text(value: str | None, file: str | None) -> str:
    if file:
        return Path(file).read_text("utf-8-sig")
    if value:
        return value
    return sys.stdin.read()


def _service() -> IdentityService:
    return IdentityService()


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------


def cmd_keygen(args: argparse.Namespace) -> int:
    service = _service()
    identity = service.identity()
    print(f"Хранилище:   {identity.backend_description}")
    print(f"Отпечаток:   {identity.fingerprint}")
    print(f"Открытый ключ (base64url):")
    print(identity.public_b64)
    if identity.ephemeral:
        print(
            "ВНИМАНИЕ: доступно только эфемерное хранилище — ключ живёт до перезапуска.",
            file=sys.stderr,
        )
    if args.out:
        save_public_key_file(identity.public_key, args.out, owner=args.owner)
        print(f"Открытый ключ сохранён: {args.out}")
    return EXIT_OK


def cmd_pubkey(args: argparse.Namespace) -> int:
    service = _service()
    identity = service.identity()
    print(identity.public_b64)
    print(f"# fingerprint: {identity.fingerprint}", file=sys.stderr)
    if args.out:
        save_public_key_file(identity.public_key, args.out, owner=args.owner)
    return EXIT_OK


def cmd_seal(args: argparse.Namespace) -> int:
    service = _service()
    text = _read_text(args.text, args.text_file)
    payload, code = document.seal(service, args.title, text, args.ts)
    identity = service.identity()

    print(code)
    print(f"# документ № {payload.document_id}", file=sys.stderr)
    print(f"# дата (UTC): {payload.ts}", file=sys.stderr)
    print(f"# отпечаток подписи: {crypto.signature_short(payload.signature)}", file=sys.stderr)
    print(f"# отпечаток ключа автора: {crypto.fingerprint(payload.public_key)}", file=sys.stderr)
    print(f"# отпечаток для сверки: {crypto.fingerprint_short(payload.public_key)}", file=sys.stderr)

    if args.out:
        save_document(args.out, payload, code, owner=args.owner)
        print(f"# файл документа: {args.out}", file=sys.stderr)
    if args.pdf:
        render_pdf(payload, args.pdf, code=code, ephemeral=identity.ephemeral)
        print(f"# PDF: {args.pdf}", file=sys.stderr)
    return EXIT_OK


def _expected_key(args: argparse.Namespace) -> bytes | None:
    """Ключ, которому обязан соответствовать документ (сверка отпечатка)."""
    if not args.pubkey:
        return None
    candidate = Path(args.pubkey)
    try:
        exists = candidate.exists()
    except OSError:
        exists = False
    if exists:
        return load_public_key_file(candidate)
    from .identity import parse_public_key

    return parse_public_key(args.pubkey)


def cmd_verify(args: argparse.Namespace) -> int:
    source = args.code or (Path(args.code_file).read_text("utf-8-sig") if args.code_file else sys.stdin.read())
    if args.code_file and not args.code and Path(args.code_file).suffix == ".poi":
        source = load_document(args.code_file)

    expected = _expected_key(args)
    result = document.verify(source, expected, use_embedded_key=not args.no_embedded)

    for check in result.checks:
        print(f"[{'OK ' if check.ok else 'FAIL'}] {check.title}: {check.detail}")
    print(f"Статус: {result.status} — {result.reason}")
    if result.payload is not None:
        print(f"Отпечаток ключа автора: {result.author_fingerprint_short} "
              f"(полный: {result.author_fingerprint})")

    if result.payload is not None and result.status == "valid":
        payload = result.payload
        print("─" * 60)
        print(f"Заголовок: {payload.title}")
        print(f"Создан (UTC): {payload.ts}")
        print(f"Документ № {payload.document_id}")
        print("─" * 60)
        print(payload.text)
        print("─" * 60)
        if args.pdf:
            render_pdf(payload, args.pdf, key_fingerprint=trusted_fingerprint())
            print(f"# PDF: {args.pdf}", file=sys.stderr)
    elif result.status == "untrusted":
        print("Содержимое не показано: доверенный ключ автора не задан (--pubkey).", file=sys.stderr)

    return {"valid": EXIT_OK, "invalid": EXIT_INVALID, "malformed": EXIT_INVALID}.get(
        result.status, EXIT_UNTRUSTED
    )


def cmd_render(args: argparse.Namespace) -> int:
    source = Path(args.code_file).read_text("utf-8-sig") if args.code_file else sys.stdin.read()
    payload = codec.decode(source)
    render_pdf(payload, args.out)
    print(f"PDF: {args.out}", file=sys.stderr)
    return EXIT_OK


def cmd_eula(args: argparse.Namespace) -> int:
    eula = eula_mod.load_eula()
    from . import paths

    path = paths.eula_acceptance_path()
    if args.accept:
        acceptance = eula_mod.accept(eula, path)
        print(f"Принято: редакция {acceptance.version}, {acceptance.accepted_at}")
        return EXIT_OK
    accepted = eula_mod.is_accepted(eula, path)
    print(f"Редакция: {eula.version} (sha256 {eula.short_hash}…), файл: {eula.path}")
    print(f"Принята: {'да' if accepted else 'нет'} ({path})")
    return EXIT_OK if accepted else EXIT_INVALID


# --------------------------------------------------------------------------
# Парсер
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vaultcore-cli", description=f"{APP_NAME} {__version__} (CLI)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="создать/показать ключ автора в хранилище ОС")
    p.add_argument("--out", help="сохранить открытый ключ в файл")
    p.add_argument("--owner", default="", help="подпись владельца для файла ключа")
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("pubkey", help="напечатать открытый ключ и отпечаток")
    p.add_argument("--out", help="сохранить открытый ключ в файл")
    p.add_argument("--owner", default="")
    p.set_defaults(func=cmd_pubkey)

    p = sub.add_parser("seal", help="запечатать документ")
    p.add_argument("--title", default="", help="заголовок документа")
    p.add_argument("--text", help="текст документа (иначе stdin)")
    p.add_argument("--text-file", help="файл с текстом документа (UTF-8)")
    p.add_argument("--ts", help="дата в формате 2026-10-21T14:32:00Z (по умолчанию текущая)")
    p.add_argument("--out", help="сохранить .poi")
    p.add_argument("--pdf", help="сохранить PDF")
    p.add_argument("--owner", default="")
    p.set_defaults(func=cmd_seal)

    p = sub.add_parser("verify", help="проверить код документа офлайн")
    p.add_argument("--code", help="код или ссылка")
    p.add_argument("--code-file", help="файл с кодом (.poi/.txt)")
    p.add_argument("--pubkey", help="доверенный открытый ключ: файл или base64url")
    p.add_argument("--no-embedded", action="store_true", help="не использовать вшитый ключ")
    p.add_argument("--pdf", help="сохранить PDF проверенного документа")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("render", help="пересобрать PDF из кода")
    p.add_argument("--code-file", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("eula", help="статус пользовательского соглашения")
    p.add_argument("--accept", action="store_true", help="принять соглашение (для CI/автоматизации)")
    p.set_defaults(func=cmd_eula)

    p = sub.add_parser("workdir", help="показать каталог данных приложения")
    p.set_defaults(func=lambda _a: print(__import__("vaultcore.paths", fromlist=["data_dir"]).data_dir()) or 0)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeystoreError as exc:
        print(f"Ошибка хранилища ключа: {exc}", file=sys.stderr)
        return EXIT_ENV
    except (canonical.PayloadError, codec.CodeError) as exc:
        print(f"Некорректный документ: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except FileNotFoundError as exc:
        print(f"Файл не найден: {exc}", file=sys.stderr)
        return EXIT_ENV


if __name__ == "__main__":
    raise SystemExit(main())
