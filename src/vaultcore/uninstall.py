"""Удаление VaultCore: ярлыки, запись в реестре, каталог программы.

Вызывается из самого приложения: ``VaultCore.exe --uninstall``. Так запись в
«Программы и компоненты» всегда указывает на существующий файл — отдельный
деинсталлятор не нужен и не может «потеряться» при копировании установщика.
"""

from __future__ import annotations

import os
import subprocess
import winreg
from pathlib import Path

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VaultCore"
APP_NAME = "VaultCore"


def shortcut_paths() -> tuple[Path, Path]:
    """Пути ярлыков в меню «Пуск» и на рабочем столе."""
    roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    programs = Path(roaming) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    desktop = Path.home() / "Desktop"
    return programs / f"{APP_NAME}.lnk", desktop / f"{APP_NAME}.lnk"


def delete_registry(key: str = REG_KEY) -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def remove_shortcuts() -> None:
    for link in shortcut_paths():
        try:
            link.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def remove_tree(target: Path) -> None:
    for path in sorted(target.rglob("*"), reverse=True):
        try:
            path.unlink() if path.is_file() else path.rmdir()
        except OSError:
            pass
    try:
        target.rmdir()
    except OSError:
        pass


def schedule_self_delete(target: Path) -> None:
    """Каталог удалится после выхода процесса (exe занят самим собой).

    ``timeout`` в отсоединённом процессе без консоли не работает, поэтому
    задержка делается через ``ping`` (он не требует консольного ввода).
    """
    command = (
        f'ping -n 4 127.0.0.1 >nul & rmdir /s /q "{target}" & rmdir /s /q "{target}"'
    )
    subprocess.Popen(
        ["cmd.exe", "/c", command],
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        close_fds=True,
    )


def uninstall(target: Path | str | None = None, *, keep_dir: bool = False) -> None:
    target = Path(target) if target else Path(__file__).resolve().parents[2]
    delete_registry()
    remove_shortcuts()
    if keep_dir:
        return
    remove_tree(target)
    if target.exists():
        schedule_self_delete(target)
