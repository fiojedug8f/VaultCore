"""Вкладка «Проверка»: код → офлайн-проверка → документ в том же оформлении.

Ключ автора берётся ИЗ КОДА документа. Проверяющему остаётся сверить отпечаток
(короткий — для мессенджера, полный — для ручной сверки) с тем, что прислал
автор.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import codec, crypto, document, paths
from ..render import render_html, render_pdf_bytes
from .pdf_preview import PdfPreview
from .theme import Card
from .widgets import GradientButton, StatusLabel

_STATUS_STYLE = {
    "valid": ("statusOk", "Документ подлинный, содержимое не изменялось"),
    "invalid": ("statusErr", "Документ изменён или подпись недействительна"),
    "malformed": ("statusErr", "Это не документ VaultCore или код повреждён"),
}


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("caption")
    label.setWordWrap(True)
    return label


class VerifyPanel(QWidget):
    """Вкладка «Проверка»: вставить код, проверить, посмотреть/сохранить PDF."""

    verified = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pdf_bytes: bytes = b""
        self._result: document.Verification | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(14)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setSizes([520, 560])
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------

    def _build_left(self) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        heading = QLabel("Проверка документа")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        layout.addWidget(_caption(
            "Вставьте код (начинается с «VC1.») или ссылку vaultcore://… "
            "Ключ автора приходит вместе с документом — ничего настраивать не нужно."
        ))

        self.code_edit = QPlainTextEdit()
        self.code_edit.setObjectName("code")
        self.code_edit.setPlaceholderText("VC1.…")
        self.code_edit.setMinimumHeight(120)
        layout.addWidget(self.code_edit)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.paste_button = QPushButton("Вставить из буфера")
        self.paste_button.setObjectName("ghost")
        self.paste_button.clicked.connect(
            lambda: self.code_edit.setPlainText(QGuiApplication.clipboard().text())
        )
        buttons.addWidget(self.paste_button)

        self.open_button = QPushButton("Открыть файл")
        self.open_button.setObjectName("ghost")
        self.open_button.clicked.connect(self._open_file)
        buttons.addWidget(self.open_button)

        buttons.addStretch(1)
        self.verify_button = GradientButton("Проверить")
        self.verify_button.clicked.connect(self._on_verify)
        buttons.addWidget(self.verify_button)
        layout.addLayout(buttons)

        self.status = StatusLabel("Проверка ещё не выполнялась")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.trust_hint = _caption("")
        layout.addWidget(self.trust_hint)

        protocol_title = QLabel("Протокол проверки")
        protocol_title.setObjectName("sectionTitle")
        layout.addWidget(protocol_title)

        self.details = QTextBrowser()
        self.details.setMinimumHeight(150)
        layout.addWidget(self.details, 1)
        return card

    def _build_right(self) -> QWidget:
        wrapper = QWidget()
        column = QVBoxLayout(wrapper)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(14)

        key_card = Card()
        key_layout = QVBoxLayout(key_card)
        key_layout.setContentsMargins(22, 18, 22, 16)
        key_layout.setSpacing(6)
        title = QLabel("Ключ автора (из документа)")
        title.setObjectName("sectionTitle")
        key_layout.addWidget(title)
        self.author_fp_label = QLabel("—")
        self.author_fp_label.setObjectName("caption")
        self.author_fp_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        key_layout.addWidget(self.author_fp_label)
        self.author_key_edit = QPlainTextEdit()
        self.author_key_edit.setObjectName("code")
        self.author_key_edit.setReadOnly(True)
        self.author_key_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.author_key_edit.setFixedHeight(56)
        self.author_key_edit.setPlaceholderText("32 байта, base64url")
        key_layout.addWidget(self.author_key_edit)
        column.addWidget(key_card)

        preview_card = Card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(8)
        self.preview = PdfPreview()
        preview_layout.addWidget(self.preview, 1)
        self.save_pdf_button = QPushButton("Сохранить PDF документа")
        self.save_pdf_button.setEnabled(False)
        self.save_pdf_button.clicked.connect(self._save_pdf)
        preview_layout.addWidget(self.save_pdf_button)
        column.addWidget(preview_card, 1)
        return wrapper

    # ------------------------------------------------------------------

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть документ", str(paths.documents_dir()),
            "Документ VaultCore (*.poi *.txt);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            self.code_edit.setPlainText(Path(path).read_text("utf-8-sig"))
        except OSError as exc:
            QMessageBox.critical(self, "Не удалось открыть файл", str(exc))

    def _on_verify(self) -> None:
        raw = self.code_edit.toPlainText().strip()
        if not raw:
            QMessageBox.information(self, "Нужен код",
                                    "Вставьте код документа или откройте файл .poi")
            return
        try:
            result = document.verify(raw)
        except Exception as exc:  # noqa: BLE001 - не роняем интерфейс на странном вводе
            QMessageBox.critical(self, "Ошибка проверки", str(exc))
            return

        self._result = result
        self._render_result(result)
        self.verified.emit(result.status)

    def _render_result(self, result: document.Verification) -> None:
        object_name, text = _STATUS_STYLE.get(result.status, ("statusWarn", "Неизвестный статус"))
        self.status.setObjectName(object_name)
        self.status.setText(text)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.update()

        payload = result.payload
        if payload is not None:
            short = crypto.fingerprint_short(payload.public_key)
            full = crypto.fingerprint(payload.public_key)
            self.author_fp_label.setText(
                f"Отпечаток ключа автора: {short}    (полный: {full})"
            )
            self.author_key_edit.setPlainText(payload.public_key_b64)
        else:
            self.author_fp_label.setText("Ключ не разобран")
            self.author_key_edit.clear()

        if result.status == "valid":
            if result.trust == "pinned":
                self.trust_hint.setText("Ключ совпал с ожидаемым — документ точно от этого автора.")
            else:
                self.trust_hint.setText(
                    f"Ключ взят из документа. Сверьте отпечаток {result.author_fingerprint_short} "
                    "с тем, что прислал автор (мессенджер, сайт, визитка)."
                )
        elif result.status == "invalid":
            self.trust_hint.setText(result.reason)
        else:
            self.trust_hint.setText(result.reason)

        rows = []
        for check in result.checks:
            mark = "✔" if check.ok else "✘"
            color = "#059669" if check.ok else "#dc2626"
            rows.append(
                f"<tr><td style='color:{color};font-weight:700;padding-right:6px'>{mark}</td>"
                f"<td style='padding-right:10px;color:#111827'>{check.title}</td>"
                f"<td style='color:#6b7280'>{check.detail}</td></tr>"
            )
        extra = ""
        if payload is not None:
            extra = (
                f"<tr><td></td><td style='color:#6b7280'>Документ №</td>"
                f"<td style='color:#6b7280'>{payload.document_id}</td></tr>"
                f"<tr><td></td><td style='color:#6b7280'>Дата создания (UTC)</td>"
                f"<td style='color:#6b7280'>{payload.ts}</td></tr>"
            )
        self.details.setHtml(
            "<table cellspacing='0' cellpadding='3'>" + "".join(rows) + extra + "</table>"
        )

        self._pdf_bytes = b""
        self.save_pdf_button.setEnabled(False)

        if result.status == "valid" and payload is not None:
            try:
                self._pdf_bytes = render_pdf_bytes(payload)
            except Exception as exc:  # noqa: BLE001
                self.details.append(f"<p style='color:#dc2626'>PDF не сформирован: {exc}</p>")
            if self._pdf_bytes:
                self.preview.show_pdf(
                    self._pdf_bytes, html_fallback=render_html(payload, valid=True)
                )
                self.save_pdf_button.setEnabled(True)
        else:
            self.preview.clear()

    def _save_pdf(self) -> None:
        if not self._pdf_bytes:
            return
        doc_id = self._result.payload.document_id if self._result and self._result.payload else "doc"
        suggested = str(paths.documents_dir() / f"verified-{doc_id}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", suggested, "PDF (*.pdf)")
        if not path:
            return
        try:
            Path(path).write_bytes(self._pdf_bytes)
        except OSError as exc:
            QMessageBox.critical(self, "Не удалось сохранить PDF", str(exc))
