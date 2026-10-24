"""Главное окно: одна программа с двумя вкладками («Создание» и «Проверка»).

Разделения на «сборку автора» и «сборку верификатора» больше нет: приложение
мультипользовательское. Любой ставит его себе, создаёт документы своим ключом и
может проверить чужой документ — открытый ключ автора приходит внутри кода.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..identity import Identity, IdentityService
from ..keystore import KeystoreError
from ..trust import EMBEDDED_KEY_OWNER, trusted_fingerprint
from .author_panel import AuthorPanel
from .theme import BG_BOTTOM, BG_TOP, Card
from .verify_panel import VerifyPanel
from .widgets import LogoMark, fade_in

BANNER_TEXT = (
    "Не юридический сервис: документы не имеют юридической силы. "
    "Это инструмент фиксации намерения и доказательства неизменности."
)


class MainWindow(QMainWindow):
    def __init__(self, service: IdentityService | None = None, **_legacy) -> None:
        super().__init__()
        self._service = service
        self.setWindowTitle(f"{APP_NAME} {__version__} — заверенный документ о намерении")
        self.resize(1240, 880)
        #: режим оставлен для совместимости тестов/скриптов; вкладки есть всегда
        self.mode = "author"

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(16)

        outer.addLayout(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, 1)

        self.author_panel = AuthorPanel(service)
        self.tabs.addTab(self.author_panel, "Создание")
        self.author_panel.sealed.connect(self._on_sealed)

        self.verify_panel = VerifyPanel()
        self.tabs.addTab(self.verify_panel, "Проверка")

        outer.addWidget(self._build_key_card())
        self.setCentralWidget(central)
        self.statusBar().showMessage("Готово · проверка работает офлайн, без сервера")
        self._fill_key_info()

    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - фон рисуем сами
        """Мягкий градиент + цветные «пятна» — база для стеклянных карточек."""
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(BG_TOP))
        gradient.setColorAt(1.0, QColor(BG_BOTTOM))
        painter.fillRect(self.rect(), gradient)

        for cx, cy, radius, color in (
            (0.12, 0.10, 0.55, QColor(99, 102, 241, 46)),
            (0.92, 0.06, 0.45, QColor(56, 189, 248, 40)),
            (0.85, 0.95, 0.60, QColor(129, 140, 248, 28)),
        ):
            blob = QRadialGradient(self.width() * cx, self.height() * cy,
                                   min(self.width(), self.height()) * radius)
            blob.setColorAt(0.0, color)
            blob.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), blob)
        painter.end()
        super().paintEvent(event)

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is not None:
            fade_in(widget, 220)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)

        row.addWidget(LogoMark())
        titles = QVBoxLayout()
        titles.setSpacing(1)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        titles.addWidget(brand)
        subtitle = QLabel("Одноразовый заверенный документ · ключ автора внутри кода")
        subtitle.setObjectName("subtle")
        titles.addWidget(subtitle)
        row.addLayout(titles)
        row.addStretch(1)

        chip = QLabel("Документы не имеют юридической силы")
        chip.setObjectName("banner")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setToolTip(BANNER_TEXT)
        row.addWidget(chip)
        return row

    def _build_key_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel("Мой открытый ключ")
        title.setObjectName("sectionTitle")
        left.addWidget(title)
        hint = QLabel("Публикуйте его свободно: по нему проверяют ваши документы. "
                      "Закрытый ключ не покидает хранилище ОС.")
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        left.addWidget(hint)
        row.addLayout(left, 1)

        self.key_edit = QPlainTextEdit()
        self.key_edit.setObjectName("code")
        self.key_edit.setReadOnly(True)
        self.key_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.key_edit.setFixedHeight(56)
        self.key_edit.setMaximumWidth(430)
        row.addWidget(self.key_edit)

        side = QVBoxLayout()
        side.setSpacing(4)
        self.fingerprint_label = QLabel("—")
        self.fingerprint_label.setObjectName("caption")
        self.fingerprint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self.fingerprint_label)
        self.backend_label = QLabel("")
        self.backend_label.setObjectName("caption")
        self.backend_label.setWordWrap(True)
        side.addWidget(self.backend_label)
        copy_button = QPushButton("Копировать ключ")
        copy_button.clicked.connect(self._copy_key)
        side.addWidget(copy_button, alignment=Qt.AlignmentFlag.AlignLeft)
        row.addLayout(side)
        return card

    # ------------------------------------------------------------------

    def _fill_key_info(self) -> None:
        if self._service is not None:
            try:
                identity = self._service.identity()
            except KeystoreError as exc:
                self.key_edit.setPlainText(f"ключ недоступен: {exc}")
                self.backend_label.setText("Создание документов недоступно")
                return
            self.set_key_info(identity, trusted_fingerprint())
            return

        key = trusted_fingerprint()
        self.key_edit.setPlainText("(в этой сборке закрытого ключа нет)")
        self.fingerprint_label.setText(
            f"Ожидаемый ключ: {key}" if key else "Ключ ещё не создан"
        )
        self.backend_label.setText(EMBEDDED_KEY_OWNER or "Режим без собственного ключа")

    def set_key_info(self, identity: Identity, trusted: str | None = None) -> None:
        self.key_edit.setPlainText(identity.public_b64)
        self.fingerprint_label.setText(f"Отпечаток: {identity.fingerprint}")
        parts = [identity.backend_description]
        if trusted and trusted != identity.fingerprint:
            parts.append(f"внимание: ожидаемый отпечаток {trusted}")
        if identity.ephemeral:
            parts.append("КЛЮЧ ЭФЕМЕРНЫЙ: после перезапуска подпись нельзя связать с вами")
        self.backend_label.setText(" · ".join(parts))

    def _copy_key(self) -> None:
        text = self.key_edit.toPlainText().strip()
        if text and not text.startswith("("):
            QGuiApplication.clipboard().setText(text)
            self.statusBar().showMessage("Открытый ключ скопирован", 4000)

    def _on_sealed(self, code: str) -> None:
        self.statusBar().showMessage(
            f"Документ запечатан · {len(code)} символов кода · PDF готов к сохранению", 8000
        )
