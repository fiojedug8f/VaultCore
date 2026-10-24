"""Вкладка «Создание»: текст → «Запечатать» → код, ссылка, PDF.

Оформление — современные карточки: слева документ, справа результат и
предпросмотр. Логика та же, что в CLI: `document.seal()` → код → PDF.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import canonical, codec, document, paths, storage
from ..identity import Identity, IdentityService
from ..keystore import KeystoreError
from ..render import render_html, render_pdf_bytes
from .pdf_preview import PdfPreview
from .theme import Card
from .widgets import GradientButton, fade_in


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("caption")
    label.setWordWrap(True)
    return label


class AuthorPanel(QWidget):
    """Левая вкладка: текст → запечатать → код/PDF/ссылка."""

    sealed = Signal(str)

    def __init__(self, service: IdentityService | None, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._identity: Identity | None = None
        self._payload: canonical.Payload | None = None
        self._code: str = ""
        self._pdf_bytes: bytes = b""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(14)
        root.addWidget(splitter, 1)

        splitter.addWidget(self._build_editor_card())
        splitter.addWidget(self._build_result_column())
        splitter.setSizes([560, 520])

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(1000)
        self._tick()
        self.body_edit.textChanged.connect(self._update_count)

    # ------------------------------------------------------------------
    # Разметка
    # ------------------------------------------------------------------

    def _build_editor_card(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        heading = QLabel("Новый документ")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        layout.addWidget(_caption(
            "Любой текст: заявление, план, обещание, шутка. После запечатывания "
            "заголовок, текст и дата блокируются."
        ))

        row = QHBoxLayout()
        label = QLabel("Заголовок")
        label.setObjectName("caption")
        row.addWidget(label)
        self.title_edit = QLineEdit(canonical.DEFAULT_TITLE)
        self.title_edit.setMaxLength(canonical.MAX_TITLE_CHARS)
        self.title_edit.setPlaceholderText("Например: Заявление о намерении")
        row.addWidget(self.title_edit, 1)
        layout.addSpacing(4)
        layout.addLayout(row)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText(
            "Текст документа. Например: «Настоящим подтверждаю намерение…».\n"
            "Поддерживаются абзацы (пустая строка между ними)."
        )
        layout.addWidget(self.body_edit, 1)

        meta = QHBoxLayout()
        self.time_label = _caption("")
        self.count_label = _caption("")
        meta.addWidget(self.time_label)
        meta.addStretch(1)
        meta.addWidget(self.count_label)
        layout.addLayout(meta)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.reset_button = QPushButton("Новый документ")
        self.reset_button.setObjectName("ghost")
        self.reset_button.clicked.connect(self.reset)
        self.reset_button.setEnabled(False)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        self.seal_button = GradientButton("Запечатать")
        self.seal_button.clicked.connect(self._on_seal)
        actions.addWidget(self.seal_button)
        layout.addLayout(actions)
        return card

    def _build_result_column(self) -> QWidget:
        wrapper = QWidget()
        column = QVBoxLayout(wrapper)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(14)

        code_card = Card()
        code_layout = QVBoxLayout(code_card)
        code_layout.setContentsMargins(22, 20, 22, 16)
        code_layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Код документа")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        badge = QLabel("VC1")
        badge.setObjectName("caption")
        head.addWidget(badge)
        code_layout.addLayout(head)

        self.code_edit = QPlainTextEdit()
        self.code_edit.setObjectName("code")
        self.code_edit.setReadOnly(True)
        self.code_edit.setMinimumHeight(92)
        self.code_edit.setPlaceholderText("Появится после запечатывания")
        code_layout.addWidget(self.code_edit)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.copy_button = QPushButton("Скопировать код")
        self.copy_button.clicked.connect(self._copy_code)
        self.link_button = QPushButton("Ссылка")
        self.link_button.clicked.connect(self._copy_link)
        self.save_button = QPushButton("Сохранить .poi")
        self.save_button.clicked.connect(self._save_poi)
        self.pdf_button = QPushButton("Сохранить PDF")
        self.pdf_button.clicked.connect(self._save_pdf)
        for widget in (self.copy_button, self.link_button, self.save_button, self.pdf_button):
            widget.setEnabled(False)
            buttons.addWidget(widget)
        code_layout.addLayout(buttons)
        column.addWidget(code_card)

        preview_card = Card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(6)
        self.preview = PdfPreview()
        preview_layout.addWidget(self.preview, 1)
        column.addWidget(preview_card, 1)
        return wrapper

    # ------------------------------------------------------------------
    # Логика
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        if self._payload is not None:
            return
        self.time_label.setText(
            f"Время фиксации (UTC): {canonical.utc_now_iso()} — зафиксируется при запечатывании"
        )

    def _update_count(self) -> None:
        text = self.body_edit.toPlainText()
        self.count_label.setText(f"{len(text)} / {canonical.MAX_TEXT_CHARS}")

    def _ensure_identity(self) -> Identity | None:
        if self._identity is not None:
            return self._identity
        if self._service is None:
            QMessageBox.critical(self, "Ключ недоступен",
                                 "Закрытый ключ не найден и не может быть создан.")
            return None
        try:
            identity = self._service.identity()
        except KeystoreError as exc:
            QMessageBox.critical(self, "Ошибка хранилища ключа", str(exc))
            return None
        self._identity = identity
        return identity

    def _on_seal(self) -> None:
        identity = self._ensure_identity()
        if identity is None or self._service is None:
            return
        text = self.body_edit.toPlainText()
        try:
            canonical.normalize_text(text)
        except canonical.PayloadError as exc:
            QMessageBox.warning(self, "Проверьте текст", str(exc))
            return

        answer = QMessageBox.question(
            self,
            "Запечатать документ?",
            "После запечатывания заголовок, текст и дата блокируются — изменить документ\n"
            "и сохранить ту же подпись будет невозможно.\n\n"
            "Дата фиксируется по часам этого компьютера (UTC). Документ не имеет\n"
            "юридической силы. Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            payload, code = document.seal(self._service, self.title_edit.text(), text)
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки пользователю
            QMessageBox.critical(self, "Не удалось запечатать", str(exc))
            return

        self._payload = payload
        self._code = code
        try:
            self._pdf_bytes = render_pdf_bytes(payload, code=code, ephemeral=identity.ephemeral)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "PDF не сформирован",
                f"Документ подписан, но PDF собрать не удалось:\n{exc}\n"
                "Код документа по-прежнему действителен.",
            )

        self._lock_editor()
        self.code_edit.setPlainText(code)
        for widget in (self.copy_button, self.link_button, self.save_button, self.pdf_button):
            widget.setEnabled(True)
        if self._pdf_bytes:
            self.preview.show_pdf(
                self._pdf_bytes, html_fallback=render_html(payload, code=code)
            )
        self.time_label.setText(f"Зафиксировано (UTC): {payload.ts}")
        self.sealed.emit(code)

    def _lock_editor(self) -> None:
        self.title_edit.setEnabled(False)
        self.body_edit.setEnabled(False)
        self.seal_button.setEnabled(False)
        self.reset_button.setEnabled(True)
        self._clock.stop()

    def reset(self) -> None:
        self._payload = None
        self._code = ""
        self._pdf_bytes = b""
        self.title_edit.setEnabled(True)
        self.body_edit.setEnabled(True)
        self.body_edit.clear()
        self.seal_button.setEnabled(True)
        self.reset_button.setEnabled(False)
        self.code_edit.clear()
        for widget in (self.copy_button, self.link_button, self.save_button, self.pdf_button):
            widget.setEnabled(False)
        self.preview.clear()
        self._clock.start()
        self._tick()

    # --- кнопки -------------------------------------------------------

    def _copy_code(self) -> None:
        if self._code:
            QGuiApplication.clipboard().setText(self._code)

    def _copy_link(self) -> None:
        if self._code:
            QGuiApplication.clipboard().setText(codec.build_link(self._code))

    def _save_poi(self) -> None:
        if not self._payload:
            return
        suggested = str(paths.documents_dir() / f"document-{self._payload.document_id}.poi")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить документ", suggested,
                                             "Документ VaultCore (*.poi *.txt)")
        if not path:
            return
        try:
            storage.save_document(path, self._payload, self._code)
        except OSError as exc:
            QMessageBox.critical(self, "Не удалось сохранить", str(exc))

    def _save_pdf(self) -> None:
        if not self._payload or not self._pdf_bytes:
            return
        suggested = str(paths.documents_dir() / f"document-{self._payload.document_id}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", suggested, "PDF (*.pdf)")
        if not path:
            return
        try:
            Path(path).write_bytes(self._pdf_bytes)
        except OSError as exc:
            QMessageBox.critical(self, "Не удалось сохранить PDF", str(exc))
