"""Сборка приложения VaultCore (PyInstaller, onedir, с логотипом).

Запуск:  python tools/build_exe.py            # папка dist/VaultCore
         python tools/build_exe.py --onefile  # один файл (на этой машине
                                              # не проверить: распаковка
                                              # во %TEMP% блокируется)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vaultcore import APP_NAME, __version__  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="единый exe")
    args = parser.parse_args(argv)

    icon = ROOT / "src" / "vaultcore" / "assets" / "icon.ico"
    entry = ROOT / "tools" / "entry_author.py"
    sep = ";" if sys.platform == "win32" else ":"

    for folder in (ROOT / "build" / APP_NAME, ROOT / "dist" / APP_NAME,
                   ROOT / "dist" / f"{APP_NAME}.exe"):
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
        elif folder.is_file():
            folder.unlink()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--onefile" if args.onefile else "--onedir",
        "--name", APP_NAME,
        "--icon", str(icon),
        "--paths", str(ROOT / "src"),
        "--add-data", f"{ROOT / 'src' / 'vaultcore' / 'templates'}{sep}templates",
        "--add-data", f"{ROOT / 'src' / 'vaultcore' / 'assets'}{sep}assets",
        "--hidden-import", "segno",
        "--hidden-import", "vaultcore.keystore.dpapi",
        "--hidden-import", "vaultcore.keystore.keyring_backend",
        "--hidden-import", "vaultcore.keystore.ephemeral",
        str(entry),
    ]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT))

    if args.onefile:
        exe = ROOT / "dist" / f"{APP_NAME}.exe"
    else:
        exe = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
    if not exe.exists():
        print("Сборка не дала exe", file=sys.stderr)
        return 2
    size = sum(p.stat().st_size for p in exe.parent.rglob("*") if p.is_file()) / 1_048_576
    print(f"\nГотово: {exe} (каталог {size:.0f} МБ), версия {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
