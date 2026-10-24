"""Экран пользовательского соглашения при первом запуске.

Без явного принятия приложение не работает: кнопка «Принимаю» недоступна,
пока не отмечен флажок. Закрытие окна = отказ = выход.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ..eula import Eula
from .widgets import GradientButton, LogoMark, SoftCheckBox


class EulaDialog(QDialog):
    def __init__(self, eula: Eula, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VaultCore — Пользовательское соглашение")
        self.setMinimumSize(780, 660)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(LogoMark(size=52))
        title = QLabel(f"Пользовательское соглашение · редакция {eula.version}")
        title.setObjectName("brand")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        layout.addLayout(header)

        intro = QLabel(
            "Прочитайте соглашение целиком, чтобы продолжить. Оно содержит важные "
            "ограничения: создаваемые документы не имеют юридической силы, а ключ "
            "хранится в защищённом хранилище вашей учётной системы."
        )
        intro.setWordWrap(True)
        intro.setObjectName("caption")
        layout.addWidget(intro)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setMarkdown(eula.text)
        layout.addWidget(browser, 1)

        self._checkbox = SoftCheckBox("Я прочитал(а) и принимаю условия соглашения")
        layout.addWidget(self._checkbox)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        self._exit = QPushButton("Выход")
        self._exit.clicked.connect(self.reject)
        row.addWidget(self._exit)

        self._accept = GradientButton("Принимаю")
        self._accept.setEnabled(False)
        self._accept.setDefault(True)
        self._accept.clicked.connect(self.accept)
        row.addWidget(self._accept)
        layout.addLayout(row)

        self._checkbox.stateChanged.connect(
            lambda state: self._accept.setEnabled(state == Qt.CheckState.Checked.value)
        )

    # ------------------------------------------------------------------

    @staticmethod
    def ask(eula: Eula, parent=None) -> bool:
        dialog = EulaDialog(eula, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted
