"""Приложение PySide6: точка входа и проверка пользовательского соглашения.

Приложение мультипользовательское и одно на всех: вкладка «Создание» пишет
документы своим ключом, вкладка «Проверка» проверяет любые чужие документы —
открытый ключ автора приходит внутри кода.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME, __version__, eula as eula_mod, paths
from ..identity import IdentityService
from ..keystore import KeystoreError
from .eula_dialog import EulaDialog
from .main_window import MainWindow
from .theme import apply_theme


def _build_service() -> IdentityService | None:
    try:
        return IdentityService()
    except KeystoreError:
        # Хранилище может отказать по причинам ОС. Окно всё равно откроем:
        # проверка чужих документов работает и без собственного ключа.
        return None


def run(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("VaultCore")

    # Иконка окна и панели задач — логотип из ресурсов сборки.
    icon_path = paths.resource("assets/icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_theme(app)

    # --- пользовательское соглашение (обязательный шлагбаум) ---------------
    try:
        eula = eula_mod.load_eula()
    except eula_mod.EulaError as exc:
        QMessageBox.critical(None, "Пользовательское соглашение", str(exc))
        return 2

    acceptance_path = paths.eula_acceptance_path()
    if not eula_mod.is_accepted(eula, acceptance_path):
        if not EulaDialog.ask(eula):
            return 0
        eula_mod.accept(eula, acceptance_path)

    window = MainWindow(service=_build_service())
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """CLI-обёртка: ``python -m vaultcore`` (режимов больше нет)."""
    import argparse
    import sys as _sys

    raw = list(_sys.argv[1:] if argv is None else argv)
    if "--uninstall" in raw:
        return _uninstall(raw)

    parser = argparse.ArgumentParser(prog="vaultcore", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument(
        "--mode", default=None,
        help="устарело: приложение всегда содержит обе вкладки (аргумент игнорируется)",
    )
    args, _unknown = parser.parse_known_args(raw)
    return run(args)


def _uninstall(raw: list[str]) -> int:
    """Удаление программы (вызывается из записи в «Программах и компонентах»)."""
    from pathlib import Path

    from ..uninstall import uninstall

    silent = "--silent" in raw or "--yes" in raw
    if not silent:
        app = QApplication(sys.argv[:1])
        answer = QMessageBox.question(
            None,
            f"Удалить {APP_NAME}?",
            "Программа будет удалена с этого компьютера.\n\n"
            "Документы, ключи и настройки пользователя не затрагиваются.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return 0

    # Каталог программы: папка, в которой лежит исполняемый файл.
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    uninstall(base)
    return 0
