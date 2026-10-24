"""Сборка установщика VaultCore-Setup (onedir: папка dist/VaultCore-Setup).

Требует уже собранное приложение dist/VaultCore (tools/build_exe.py).
Запуск: python installer/build_installer.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer"
DIST = ROOT / "dist"
NAME = "VaultCore-Setup"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="единый exe установщика")
    args = parser.parse_args(argv)

    app_dir = DIST / "VaultCore"
    if not app_dir.exists():
        print("Сначала соберите приложение: python tools/build_exe.py", file=sys.stderr)
        return 2

    sep = ";" if sys.platform == "win32" else ":"
    targets = [ROOT / "build" / NAME]
    targets.append(DIST / f"{NAME}.exe" if args.onefile else DIST / NAME)
    for folder in targets:
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
        elif folder.is_file():
            folder.unlink()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--onefile" if args.onefile else "--onedir",
        "--name", NAME,
        "--icon", str(INSTALLER / "app.ico"),
        "--add-data", f"{INSTALLER / 'logo.png'}{sep}.",
        "--add-data", f"{app_dir}{sep}payload",
        str(INSTALLER / "installer.py"),
    ]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT))

    setup = DIST / NAME / f"{NAME}.exe" if not args.onefile else DIST / f"{NAME}.exe"
    if not setup.exists():
        print("Установщик не собран", file=sys.stderr)
        return 2
    print(f"\nГотово: {setup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
