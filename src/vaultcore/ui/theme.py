"""Премиальная светлая тема: QSS (градиенты, стекло) + токены дизайна.

Фон окна — мягкий градиент с цветными «пятнами» (рисуется в MainWindow),
карточки — полупрозрачное стекло с тенью, акцент — градиент индиго→небесный
(кнопки рисуются в ``widgets.GradientButton``). Тень/свечение — через
QGraphicsDropShadowEffect, потому что QSS не умеет box-shadow.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsDropShadowEffect, QWidget

# --- палитра ---------------------------------------------------------------
BG_TOP = "#f8faff"
BG_BOTTOM = "#eef2fb"
CARD = "#ffffff"
BORDER = "#e5e9f2"
INK = "#0f172a"
MUTED = "#64748b"
ACCENT = "#6366f1"
ACCENT_2 = "#38bdf8"
ACCENT_HOVER = "#5457e8"
ACCENT_SOFT = "#eef1ff"
OK = "#059669"
OK_BG = "#ecfdf5"
ERR = "#dc2626"
ERR_BG = "#fef2f2"
WARN = "#b45309"
WARN_BG = "#fffbeb"
GLASS = "rgba(255, 255, 255, 214)"

QSS = f"""
/* --- базовое ------------------------------------------------------------ */
QWidget {{
    color: {INK};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Arial";
    font-size: 10pt;
}}
QMainWindow {{ background: transparent; }}
/* Диалог не рисует свой фон (в отличие от главного окна), поэтому прозрачность
   давала чёрный экран — у диалогов фон должен быть непрозрачным. */
QDialog {{ background: {BG_TOP}; }}
QDialog QTextBrowser {{
    background: #ffffff; color: {INK}; border: 1px solid {BORDER};
    border-radius: 14px; padding: 14px;
}}
QToolTip {{
    background: {INK}; color: #ffffff; border: none;
    border-radius: 8px; padding: 7px 10px;
}}

/* --- типографика -------------------------------------------------------- */
QLabel#brand {{ font-size: 21pt; font-weight: 800; color: {INK}; }}
QLabel#subtle {{ color: {MUTED}; font-size: 9.5pt; }}
QLabel#sectionTitle {{ font-size: 12.5pt; font-weight: 700; color: {INK}; }}
QLabel#caption {{ color: {MUTED}; font-size: 9pt; }}
QLabel#hint {{ color: {MUTED}; font-size: 9pt; }}
QLabel#mono {{
    font-family: "Cascadia Mono", Consolas, "SF Mono", monospace;
    font-size: 8.5pt; color: {MUTED};
}}

/* --- стеклянные карточки ------------------------------------------------ */
QFrame#card {{
    background: {GLASS};
    border: 1px solid rgba(255, 255, 255, 235);
    border-radius: 18px;
}}
QFrame#cardFlat {{
    background: rgba(255, 255, 255, 235);
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#divider {{ background: {BORDER}; border: none; max-height: 1px; }}

/* --- кнопки (вторичные) ------------------------------------------------- */
QPushButton {{
    background: rgba(255, 255, 255, 200);
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 9px 16px;
    color: {INK};
    font-size: 9.5pt;
}}
QPushButton:hover {{ background: #ffffff; border-color: #cfd6e6; }}
QPushButton:pressed {{ background: #f1f4fb; }}
QPushButton:disabled {{ color: #a3adc2; background: #f5f7fc; border-color: #edf0f7; }}

QPushButton#ghost {{
    background: transparent; border: 1px solid transparent; color: {ACCENT};
    padding: 8px 12px; font-weight: 600;
}}
QPushButton#ghost:hover {{ background: {ACCENT_SOFT}; }}
QPushButton#ghost:pressed {{ background: #e2e6ff; }}

QPushButton#danger {{
    background: transparent; border: 1px solid #fecdd3; color: {ERR}; font-weight: 600;
}}
QPushButton#danger:hover {{ background: {ERR_BG}; }}

/* --- поля ввода --------------------------------------------------------- */
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: rgba(255, 255, 255, 245);
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 11px 13px;
    selection-background-color: #dfe3ff;
    selection-color: {INK};
}}
QLineEdit:hover, QPlainTextEdit:hover {{ border-color: #d7dcec; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
    background: #ffffff;
}}
QLineEdit:disabled, QPlainTextEdit:disabled {{
    background: rgba(246, 248, 253, 220); color: {MUTED}; border-color: #eef1f8;
}}
QPlainTextEdit#code, QLineEdit#code {{
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 8.5pt;
    color: #334155;
    background: rgba(250, 251, 255, 240);
    border-radius: 14px;
}}

/* --- сегментированные вкладки ------------------------------------------ */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 10px 20px;
    margin-right: 6px;
    border: 1px solid transparent;
    border-radius: 12px;
    font-weight: 600;
    font-size: 9.5pt;
}}
QTabBar::tab:hover {{ background: rgba(255, 255, 255, 150); color: {INK}; }}
QTabBar::tab:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #eef1ff, stop:1 #e6f6ff);
    color: {ACCENT};
    border: 1px solid #dfe6ff;
}}

/* --- статусы (свечение добавляет панель через QGraphicsDropShadowEffect) */
QLabel#statusOk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ecfdf5, stop:1 #d9fbee);
    color: #047857; border: 1px solid #a7f3d0;
    border-radius: 14px; padding: 12px 16px; font-weight: 700;
}}
QLabel#statusErr {{
    background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;
    border-radius: 14px; padding: 12px 16px; font-weight: 700;
}}
QLabel#statusWarn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fffbeb, stop:1 #fff4dc);
    color: {WARN}; border: 1px solid #fde68a;
    border-radius: 14px; padding: 12px 16px; font-weight: 700;
}}
QLabel#statusIdle {{
    background: rgba(243, 245, 251, 220); color: {MUTED};
    border: 1px solid {BORDER};
    border-radius: 14px; padding: 12px 16px;
}}
QLabel#banner {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eef1ff, stop:1 #e8f7ff);
    color: #4338ca;
    border: 1px solid #dfe6ff; border-radius: 14px;
    padding: 9px 16px; font-size: 9pt; font-weight: 600;
}}

/* --- мелочи ------------------------------------------------------------- */
QSplitter::handle {{ background: transparent; width: 12px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #d7dcea; border-radius: 5px; min-height: 34px; }}
QScrollBar::handle:vertical:hover {{ background: #c3cbdd; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: #d7dcea; border-radius: 5px; min-width: 34px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QStatusBar {{ background: transparent; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QMessageBox {{ background: {CARD}; }}
"""


class Card(QFrame):
    """Стеклянная карточка со скруглением 18 px и мягкой тенью."""

    def __init__(self, parent: QWidget | None = None, *, flat: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("cardFlat" if flat else "card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._flat = flat

    def paintEvent(self, event) -> None:  # noqa: N802 - тень рисуем сами
        """Мягкая тень слоями + стеклянная поверхность.

        Тень намеренно не через QGraphicsDropShadowEffect: вложенные эффекты
        Qt не поддерживает, и карточка внутри анимируемой панели пропадала бы.
        """
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = 3 if self._flat else 6
        body = QRectF(self.rect()).adjusted(inset, inset, -inset, -(inset + 4))

        if not self._flat:
            painter.setPen(Qt.PenStyle.NoPen)
            for step in range(6, 0, -1):
                painter.setBrush(QColor(79, 70, 229, 3 + step // 2))
                painter.drawRoundedRect(
                    body.adjusted(-step, -step + 2, step, step + 2), 18 + step, 18 + step
                )

        surface = QLinearGradient(body.topLeft(), body.bottomLeft())
        surface.setColorAt(0.0, QColor(255, 255, 255, 240))
        surface.setColorAt(1.0, QColor(255, 255, 255, 222))
        painter.setBrush(surface)
        painter.setPen(QPen(QColor(255, 255, 255, 245), 1.0))
        painter.drawRoundedRect(body, 18 if not self._flat else 14, 18 if not self._flat else 14)
        painter.end()


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_BOTTOM))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#fafbff"))
    palette.setColor(QPalette.ColorRole.Text, QColor(INK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
    font = app.font()
    font.setPointSizeF(10.0)
    app.setFont(font)
