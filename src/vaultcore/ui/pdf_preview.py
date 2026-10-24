"""Предпросмотр PDF внутри приложения.

Основной путь — QtPdf (настоящий PDF, то, что уйдёт получателю). Если модуль
недоступен в сборке, показывается HTML-версия документа — визуально близкая,
но без постраничной вёрстки.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from .. import paths

try:  # QtPdf входит в PySide6-Addons, но не в минимальную установку
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    _HAS_QTPDF = True
except Exception:  # noqa: BLE001 - любая ошибка импорта = fallback
    QPdfDocument = None  # type: ignore[assignment]
    QPdfView = None  # type: ignore[assignment]
    _HAS_QTPDF = False


class PdfPreview(QWidget):
    """Виджет предпросмотра: PDF через QtPdf либо HTML-запасной вариант."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Предпросмотр пишется в каталог данных приложения, а не в системный
        # temp: предсказуемые права доступа и нет мусора в %TEMP%.
        self._preview_dir = paths.data_dir() / "preview"
        self._preview_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._view = None
        self._doc = None
        self._html = None
        self._placeholder = QLabel("Документ ещё не сформирован")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _HAS_QTPDF:
            self._doc = QPdfDocument(self)
            self._view = QPdfView(self)
            self._view.setDocument(self._doc)
            self._view.setPageMode(QPdfView.PageMode.SinglePage)
            self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self._view.setVisible(False)
            layout.addWidget(self._view)
        else:
            self._html = QTextBrowser(self)
            self._html.setVisible(False)
            layout.addWidget(self._html)

        layout.addWidget(self._placeholder)

    # ------------------------------------------------------------------

    def show_pdf(self, data: bytes, *, html_fallback: str = "") -> bool:
        """Показывает PDF из памяти. Возвращает True, если сработал QtPdf."""
        if _HAS_QTPDF and data:
            self._counter += 1
            path = self._preview_dir / f"preview-{self._counter}.pdf"
            path.write_bytes(data)
            try:
                if self._doc is not None:
                    self._doc.close()
                    self._doc.load(str(path))
                    if self._doc.status() == QPdfDocument.Status.Ready:
                        self._placeholder.setVisible(False)
                        self._view.setVisible(True)
                        self._html and self._html.setVisible(False)
                        return True
            except Exception:  # noqa: BLE001 - переходим к HTML
                pass

        if self._html is not None and html_fallback:
            self._html.setHtml(html_fallback)
            self._placeholder.setVisible(False)
            self._html.setVisible(True)
            return False
        self._placeholder.setText("Предпросмотр недоступен в этой сборке")
        self._placeholder.setVisible(True)
        return False

    def clear(self) -> None:
        self._placeholder.setText("Документ ещё не сформирован")
        self._placeholder.setVisible(True)
        if self._view is not None:
            self._view.setVisible(False)
        if self._html is not None:
            self._html.setVisible(False)
