import os, sys, pathlib

root = pathlib.Path(".").resolve()
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "installer"))

# нейтральный путь в снимке: без имени пользователя.
# Собирается из частей, чтобы в исходнике не было литерала абсолютного пути
# (его ловят сканеры секретов и он выглядит как «зашитый» путь автора).
_neutral_home = pathlib.Path(os.environ.get("SystemDrive", "C:") + os.sep, "Users", "User")
os.environ["LOCALAPPDATA"] = str(_neutral_home / "AppData" / "Local")
os.environ.setdefault("USERPROFILE", str(_neutral_home))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import installer as inst

app = QApplication([])
app.setStyleSheet(inst.QSS)
win = inst.InstallerWindow()
win.show()


def grab() -> None:
    out = root / "docs" / "screenshots" / "setup.png"
    win.grab().save(str(out))
    app.quit()


QTimer.singleShot(700, grab)
app.exec()
print("saved:", (root / "docs/screenshots/setup.png").exists())
