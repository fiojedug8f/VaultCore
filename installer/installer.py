"""Установщик VaultCore (отдельный .exe).

Режимы:
    VaultCore-Setup.exe                 — мастер установки (GUI)
    VaultCore-Setup.exe --silent --dir <путь> [--no-shortcuts] [--no-registry]
    VaultCore-Setup.exe --uninstall     — удаление (GUI-подтверждение)
    VaultCore-Setup.exe --uninstall --silent

Ставит приложение в %LOCALAPPDATA%\\Programs\\VaultCore (без UAC), создаёт
ярлыки (меню «Пуск» и, по желанию, рабочий стол) и запись в
«Программы и компоненты» для текущего пользователя.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "VaultCore"


def _log(message: str) -> None:
    """Диагностический лог (windowed-сборка не имеет stdout)."""
    try:
        override = os.environ.get("VAULTCORE_SETUP_LOG")
        log_path = Path(override) if override else (
            Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "VaultCore" / "setup.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            from datetime import datetime

            handle.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass
APP_VERSION = "1.0.0"
PUBLISHER = "VaultCore"
EXE_NAME = "VaultCore.exe"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VaultCore"

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
LOGO_PATH = ASSETS / "logo.png"
PAYLOAD_DIR = ASSETS / "payload"

QSS = """
QWidget { color: #0f172a; font-family: "Segoe UI Variable Text", "Segoe UI", Arial; font-size: 10pt; }
QLineEdit { background: rgba(255,255,255,245); border: 1px solid #e5e9f2; border-radius: 12px;
            padding: 9px 12px; }
QLineEdit:focus { border: 1px solid #6366f1; }
QLabel#title { font-size: 22pt; font-weight: 800; }
QLabel#sub { color: #64748b; font-size: 9.5pt; }
QLabel#caption { color: #64748b; font-size: 9pt; }
QPushButton { background: rgba(255,255,255,220); border: 1px solid #e5e9f2; border-radius: 11px;
              padding: 9px 16px; }
QPushButton:hover { background: #ffffff; border-color: #cfd6e6; }
QPushButton:disabled { color: #a3adc2; background: #f5f7fc; }
QProgressBar { background: #eef1f8; border: none; border-radius: 7px; height: 14px; text-align: center; }
QProgressBar::chunk { border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #38bdf8); }
QCheckBox { spacing: 8px; }
"""


class GradientButton(QPushButton):
    """Кнопка с градиентом и анимацией наведения/нажатия."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self._hover = 0.0
        self._press = 0.0
        self.setMinimumHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        from PySide6.QtCore import QEasingCurve, QVariantAnimation

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._set_hover)
        self._press_anim = QVariantAnimation(self)
        self._press_anim.setDuration(90)
        self._press_anim.valueChanged.connect(self._set_press)

    def _set_hover(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _set_press(self, value) -> None:
        self._press = float(value)
        self.update()

    def enterEvent(self, event):  # noqa: N802
        self._animate(self._hover_anim, self._hover, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._animate(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        self._animate(self._press_anim, self._press, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._animate(self._press_anim, self._press, 0.0)
        super().mouseReleaseEvent(event)

    def _animate(self, animation, start: float, end: float) -> None:
        animation.stop()
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.start()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = QRectF(self.rect()).adjusted(3, 3, -3, -5)
        body.translate(0, 1.3 * self._press)
        enabled = self.isEnabled()

        if enabled:
            for step in range(4, 0, -1):
                alpha = int((6 + 10 * self._hover) * step / 4)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(99, 102, 241, alpha))
                painter.drawRoundedRect(body.adjusted(-step, -step + 1, step, step + 1),
                                        12 + step, 12 + step)

        start = QColor("#6366f1").lighter(int(100 + 12 * self._hover))
        end = QColor("#38bdf8").lighter(int(100 + 12 * self._hover))
        if not enabled:
            start, end = QColor("#c7cbf3"), QColor("#bfe3f6")
        if self._press > 0.5:
            start, end = QColor("#4f46e5"), QColor("#0ea5e9")

        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        gradient.setColorAt(0.0, start)
        gradient.setColorAt(1.0, end)
        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)
        painter.fillPath(path, gradient)
        painter.setPen(QColor(255, 255, 255, 235))
        font = self.font()
        font.setWeight(font.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(body, int(Qt.AlignmentFlag.AlignCenter), self.text())
        painter.end()


def default_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / APP_NAME


def payload_dir() -> Path:
    """Каталог собранного приложения (onedir) или каталог с одним exe."""
    if PAYLOAD_DIR.is_dir():
        return PAYLOAD_DIR
    candidates = [
        Path(os.environ.get("VAULTCORE_PAYLOAD", "")) if os.environ.get("VAULTCORE_PAYLOAD") else None,
        Path(__file__).resolve().parent.parent / "dist" / APP_NAME,
        Path(__file__).resolve().parent,
    ]
    for candidate in candidates:
        if candidate and (candidate / EXE_NAME).exists():
            return candidate
    raise FileNotFoundError("payload VaultCore не найден")


# --------------------------------------------------------------------------
# Ярлыки и реестр
# --------------------------------------------------------------------------


def _ps_shortcut(link: Path, target: Path, args: str = "") -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{link}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{target.parent}'; "
        f"$s.IconLocation = '{target},0'; "
        + (f"$s.Arguments = '{args}'; " if args else "")
        + "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True, capture_output=True,
    )


def write_uninstall_script(target: Path) -> None:
    """Удаление отдельным .cmd: он может стереть каталог, включая собственный exe."""
    script = f'''@echo off
setlocal
set "DIR=%~dp0"
set "EXE=%LOCALAPPDATA%\\Programs\\{APP_NAME}\\{EXE_NAME}"
:wait
tasklist /fi "imagename eq {EXE_NAME}" 2>nul | find /i "{EXE_NAME}" >nul && (
    ping -n 2 127.0.0.1 >nul
    goto wait
)
reg delete "HKCU\\{REG_KEY}" /f >nul 2>&1
del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NAME}.lnk" >nul 2>&1
del "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" >nul 2>&1
cd /d "%TEMP%"
rmdir /s /q "%DIR%" 2>nul
del "%~f0" >nul 2>&1
'''
    path = target / "Uninstall.cmd"
    path.write_text(script.replace("\n", "\r\n"), encoding="ascii", newline="")


def shortcut_paths() -> tuple[Path, Path]:
    from PySide6.QtCore import QStandardPaths

    programs = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ApplicationsLocation)
    )
    desktop = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    )
    return programs / f"{APP_NAME}.lnk", desktop / f"{APP_NAME}.lnk"


def write_registry(target: Path, size_kb: int) -> None:
    uninstall_cmd = f'"{target / "Uninstall.cmd"}"'
    icon = target / EXE_NAME
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(icon))
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(target))
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)


def delete_registry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except FileNotFoundError:
        pass


# --------------------------------------------------------------------------
# Установка / удаление
# --------------------------------------------------------------------------


def install(
    target: Path,
    *,
    shortcuts: bool = True,
    registry: bool = True,
    progress=None,
) -> None:
    source = payload_dir()
    target.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("Подготовка", 5)

    shutil.copytree(source, target, dirs_exist_ok=True)
    if progress:
        progress("Копирование приложения", 55)

    write_uninstall_script(target)
    if progress:
        progress("Файлы установлены", 70)

    if shortcuts:
        programs_link, desktop_link = shortcut_paths()
        _ps_shortcut(programs_link, target / EXE_NAME)
        _ps_shortcut(desktop_link, target / EXE_NAME)
    if progress:
        progress("Ярлыки", 85)

    if registry:
        size_kb = int(sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) / 1024)
        write_registry(target, size_kb)
    if progress:
        progress("Готово", 100)


def uninstall(
    target: Path, *, shortcuts: bool = True, registry: bool = True, remove_self: bool = True
) -> None:
    if shortcuts:
        programs_link, desktop_link = shortcut_paths()
        for link in (programs_link, desktop_link):
            try:
                link.unlink()
            except FileNotFoundError:
                pass
    if registry:
        delete_registry()

    for path in sorted(target.rglob("*"), reverse=True):
        try:
            path.unlink() if path.is_file() else path.rmdir()
        except OSError:
            pass
    try:
        target.rmdir()
    except OSError:
        pass

    if remove_self and getattr(sys, "frozen", False):
        # Каталог удалится после выхода процесса (exe занят самим собой).
        subprocess.Popen(
            ["cmd.exe", "/c", f'timeout /t 2 >nul & rmdir /s /q "{target}"'],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------


class InstallerWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} — установка")
        self.setFixedSize(640, 470)
        self._dark = False

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 22)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        pix = QPixmap(str(LOGO_PATH))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        head.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        titles.addWidget(title)
        sub = QLabel("Одноразовый заверенный документ · версия " + APP_VERSION)
        sub.setObjectName("sub")
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        root.addLayout(head)

        caption = QLabel(
            "Установка в папку текущего пользователя (права администратора не нужны). "
            "Приложение ставится целиком: и создание документов, и проверка чужих."
        )
        caption.setObjectName("caption")
        caption.setWordWrap(True)
        root.addWidget(caption)

        row = QHBoxLayout()
        self.path_edit = QLineEdit(str(default_dir()))
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        root.addLayout(row)

        self.desktop_check = QCheckBox("Ярлык на рабочем столе")
        self.desktop_check.setChecked(True)
        self.run_check = QCheckBox("Запустить VaultCore после установки")
        self.run_check.setChecked(True)
        root.addWidget(self.desktop_check)
        root.addWidget(self.run_check)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.status = QLabel("Готов к установке")
        self.status.setObjectName("caption")
        root.addWidget(self.status)

        root.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel = QPushButton("Отмена")
        self.cancel.clicked.connect(self.close)
        buttons.addWidget(self.cancel)
        self.install_button = GradientButton("Установить")
        self.install_button.setMinimumWidth(190)
        self.install_button.clicked.connect(self._start)
        buttons.addWidget(self.install_button)
        root.addLayout(buttons)

        self._worker: QThread | None = None
        self._target: Path | None = None

    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#f8faff"))
        gradient.setColorAt(1.0, QColor("#eef2fb"))
        painter.fillRect(self.rect(), gradient)
        for cx, cy, color in ((0.1, 0.05, QColor(99, 102, 241, 40)),
                              (0.9, 0.1, QColor(56, 189, 248, 36))):
            from PySide6.QtGui import QRadialGradient

            blob = QRadialGradient(self.width() * cx, self.height() * cy, self.width() * 0.5)
            blob.setColorAt(0.0, color)
            blob.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), blob)
        painter.end()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Куда установить", self.path_edit.text())
        if path:
            self.path_edit.setText(str(Path(path) / APP_NAME))

    def _start(self) -> None:
        target = Path(self.path_edit.text().strip() or default_dir())
        self._target = target
        self.install_button.setEnabled(False)
        self.cancel.setEnabled(False)
        self.status.setText("Устанавливаю…")

        shortcuts = True
        desktop = self.desktop_check.isChecked()

        try:
            install(
                target,
                shortcuts=shortcuts,
                registry=True,
                progress=self._progress_cb,
            )
            if not desktop:
                _programs, desktop_link = shortcut_paths()
                try:
                    desktop_link.unlink()
                except FileNotFoundError:
                    pass
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Ошибка установки: {exc}")
            self.install_button.setEnabled(True)
            self.cancel.setEnabled(True)
            return

        self.progress.setValue(100)
        self.status.setText(f"Установлено в {target}")
        self.install_button.setText("Готово")
        self.install_button.setEnabled(False)
        self.cancel.setText("Закрыть")
        self.cancel.setEnabled(True)
        if self.run_check.isChecked():
            exe = target / EXE_NAME
            if exe.exists():
                try:
                    subprocess.Popen([str(exe)], cwd=str(target))
                except OSError:
                    pass

    def _progress_cb(self, text: str, value: int) -> None:
        self.status.setText(text)
        self.progress.setValue(value)
        QApplication.processEvents()


def run_gui(screenshot: Path | None = None) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon

    app = QApplication(sys.argv[:1])
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_PATH)))
    app.setStyleSheet(QSS)
    window = InstallerWindow()
    window.show()
    if screenshot is not None:
        def grab() -> None:
            window.grab().save(str(screenshot))
            app.quit()

        QTimer.singleShot(700, grab)
    return app.exec()


# --------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="VaultCore-Setup")
    parser.add_argument("--silent", action="store_true", help="без интерфейса")
    parser.add_argument("--dir", default=None, help="каталог установки")
    parser.add_argument("--uninstall", action="store_true", help="удалить программу")
    parser.add_argument("--no-shortcuts", action="store_true")
    parser.add_argument("--no-registry", action="store_true")
    parser.add_argument("--keep-self", action="store_true", help="не удалять каталог после удаления")
    parser.add_argument("--screenshot", default=None, help="сохранить снимок окна и выйти")
    args = parser.parse_args(argv)
    _log(f"argv={argv if argv is not None else sys.argv[1:]!r} silent={args.silent} dir={args.dir}")

    target = Path(args.dir) if args.dir else default_dir()

    if args.uninstall:
        if args.silent:
            _log(f'uninstall {target}')
            uninstall(target, shortcuts=not args.no_shortcuts,
                      registry=not args.no_registry, remove_self=not args.keep_self)
            return 0
        # GUI-подтверждение удаления — простое окно Qt
        from PySide6.QtWidgets import QMessageBox

        app = QApplication(sys.argv[:1])
        app.setStyleSheet(QSS)
        answer = QMessageBox.question(
            None, f"Удалить {APP_NAME}?",
            f"Программа и её файлы будут удалены из:\n{target}\n\n"
            "Документы и ключи пользователя не затрагиваются.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return 0
        uninstall(target, shortcuts=not args.no_shortcuts,
                  registry=not args.no_registry, remove_self=True)
        return 0

    if args.silent:
        try:
            install(
                target,
                shortcuts=not args.no_shortcuts,
                registry=not args.no_registry,
            )
            _log(f"installed to {target}")
        except Exception as exc:  # noqa: BLE001 - причина должна попасть в лог
            import traceback

            _log("install failed: " + "".join(traceback.format_exception(exc)))
            return 1
        return 0

    return run_gui(Path(args.screenshot) if args.screenshot else None)


if __name__ == "__main__":
    raise SystemExit(main())
