"""Вшивает открытый ключ автора в исходник сборки (режим «Проверка»).

Зачем: требование «открытый ключ в режиме проверки должен быть вшит на этапе
сборки, а не читаться из файла, который можно подменить». Скрипт перезаписывает
``src/vaultcore/embedded.py`` — единственное место, откуда приложение берёт
доверенный ключ.

Использование:

    python tools/embed_key.py                     # ключ из хранилища ОС автора
    python tools/embed_key.py --key-file pub.txt  # ключ из опубликованного файла
    python tools/embed_key.py --owner "Иван Петров"
    python tools/embed_key.py --clear             # вернуть пустую заглушку
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vaultcore import crypto  # noqa: E402
from vaultcore.b64util import b64u_encode  # noqa: E402

TARGET = ROOT / "src" / "vaultcore" / "embedded.py"

TEMPLATE = '''"""Вшитый при сборке открытый ключ автора (режим «Проверка»).

Файл генерируется скриптом ``tools/embed_key.py`` прямо перед сборкой
PyInstaller: ключ попадает в код, а не читается из файла, который можно
подменить рядом с исполняемым файлом. Пустая строка = ключ не вшит (dev-сборка
автора), тогда проверка честно сообщает «доверенный ключ не задан».

Файл перезаписывается автоматически — не правьте его руками.
"""

from __future__ import annotations

from .b64util import b64u_decode

#: Заполняется tools/embed_key.py. Пусто — сборка без вшитого ключа.
EMBEDDED_PUBLIC_KEY_B64: str = "{public_key}"
#: Человекочитаемое имя владельца ключа (для интерфейса).
EMBEDDED_KEY_OWNER: str = "{owner}"
#: Дата вшивания (ISO 8601 UTC).
EMBEDDED_AT: str = "{embedded_at}"


def embedded_public_key() -> bytes | None:
    """32 байта открытого ключа или None."""
    value = (EMBEDDED_PUBLIC_KEY_B64 or "").strip()
    if not value:
        return None
    raw = b64u_decode(value)
    if len(raw) != 32:
        raise ValueError("Вшитый открытый ключ повреждён (должен быть 32 байта)")
    return raw


def has_embedded_key() -> bool:
    try:
        return embedded_public_key() is not None
    except ValueError:
        return False
'''


def _key_from_keystore() -> bytes:
    from vaultcore.identity import IdentityService

    return IdentityService().identity().public_key


def _key_from_file(path: Path) -> bytes:
    from vaultcore.trust import load_public_key_file

    return load_public_key_file(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Вшить открытый ключ автора в сборку")
    parser.add_argument("--key-file", help="файл с открытым ключом (base64url)")
    parser.add_argument("--owner", default="", help="имя владельца ключа")
    parser.add_argument("--clear", action="store_true", help="убрать вшитый ключ")
    parser.add_argument("--out", default=str(TARGET), help="куда писать embedded.py")
    args = parser.parse_args(argv)

    if args.clear:
        public_key, owner, embedded_at = "", "", ""
    else:
        key = _key_from_file(Path(args.key_file)) if args.key_file else _key_from_keystore()
        public_key = b64u_encode(key)
        owner = args.owner
        embedded_at = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"Отпечаток ключа: {crypto.fingerprint(key)}")

    target = Path(args.out)
    target.write_text(
        TEMPLATE.format(public_key=public_key, owner=owner, embedded_at=embedded_at),
        "utf-8",
    )
    print(f"Записано: {target}")
    if public_key:
        print("Теперь соберите режим проверки: python tools/build_verifier.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
