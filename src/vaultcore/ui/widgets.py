"""Кастомные виджеты премиального интерфейса (QPainter + QPropertyAnimation).

Почему не только QSS: QSS не умеет градиенты с анимацией прозрачности,
свечение и «вдавливание» кнопки. Поэтому акцентные элементы нарисованы
вручную, а остальное оформлено QSS (см. ``theme.py``).
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QWidget,
)


def glow(widget: QWidget, color: QColor, blur: float = 26.0, dy: float = 4.0) -> QGraphicsDropShadowEffect:
    """Мягкое свечение/тень под виджетом."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setColor(color)
    effect.setOffset(0, dy)
    widget.setGraphicsEffect(effect)
    return effect


def fade_in(widget: QWidget, duration: int = 240) -> None:
    """Плавное появление (fade-in) виджета."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    widget._fade_animation = animation  # noqa: SLF001 - держим ссылку от GC


class GradientButton(QPushButton):
    """Акцентная кнопка: градиент индиго→небесный, свечение при наведении.

    * hover — плавное усиление градиента и увеличение свечения;
    * press — кнопка «вдавливается» на 1 px и темнеет;
    * disabled — приглушённый градиент.
    """

    BASE_FROM = QColor("#6366f1")
    BASE_TO = QColor("#38bdf8")
    HOVER_FROM = QColor("#7c7ff5")
    HOVER_TO = QColor("#4cc3fb")
    PRESS_FROM = QColor("#4f46e5")
    PRESS_TO = QColor("#0ea5e9")

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._hover = 0.0
        self._press = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setFont(self._font())

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover)

        self._press_anim = QVariantAnimation(self)
        self._press_anim.setDuration(90)
        self._press_anim.valueChanged.connect(self._on_press)

    # --- служебное -----------------------------------------------------

    @staticmethod
    def _font() -> QFont:
        font = QFont()
        font.setPointSizeF(10.0)
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.2)
        return font

    def _on_hover(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _on_press(self, value) -> None:
        self._press = float(value)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        hint = super().sizeHint()
        return QSize(max(hint.width() + 30, 136), max(hint.height(), 46))

    # --- события -------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press)
        self._press_anim.setEndValue(1.0)
        self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press)
        self._press_anim.setEndValue(0.0)
        self._press_anim.setDuration(140)
        self._press_anim.start()
        super().mouseReleaseEvent(event)

    # --- отрисовка -----------------------------------------------------

    @staticmethod
    def _mix(a: QColor, b: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(
            int(a.red() + (b.red() - a.red()) * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue() + (b.blue() - a.blue()) * t),
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - рисуем полностью сами
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        enabled = self.isEnabled()
        body = QRectF(self.rect()).adjusted(4, 4, -4, -7)
        offset = 1.4 * self._press
        body.translate(0, offset)

        # Свечение рисуем сами (вложенные QGraphicsEffect в Qt ломают детей).
        if enabled:
            for step in range(5, 0, -1):
                alpha = int((6 + 9 * self._hover) * (step / 5.0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(99, 102, 241, alpha))
                painter.drawRoundedRect(
                    body.adjusted(-step, -step + 1, step, step + 1), 12 + step, 12 + step
                )

        if enabled:
            start = self._mix(self.BASE_FROM, self.HOVER_FROM, self._hover)
            end = self._mix(self.BASE_TO, self.HOVER_TO, self._hover)
            start = self._mix(start, self.PRESS_FROM, self._press)
            end = self._mix(end, self.PRESS_TO, self._press)
        else:
            start, end = QColor("#c7cbf3"), QColor("#bfe3f6")

        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        gradient.setColorAt(0.0, start)
        gradient.setColorAt(1.0, end)

        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)

        # внутренняя подсветка сверху — «стеклянный» объём
        painter.setClipPath(path)
        painter.fillPath(path, gradient)
        highlight = QLinearGradient(body.topLeft(), QPointF(body.left(), body.center().y()))
        highlight.setColorAt(0.0, QColor(255, 255, 255, 70))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(body, highlight)
        painter.setClipping(False)

        border = QColor(255, 255, 255, 60) if enabled else QColor(255, 255, 255, 30)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)

        painter.setPen(QColor(255, 255, 255) if enabled else QColor(255, 255, 255, 190))
        painter.setFont(self.font())
        painter.drawText(body, int(Qt.AlignmentFlag.AlignCenter), self.text())
        painter.end()


class SoftCheckBox(QCheckBox):
    """Чекбокс со скруглённым квадратом и галочкой, нарисованными вручную."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)

    def paintEvent(self, event) -> None:  # noqa: N802 - QSS не умеет галочку
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        size = 20.0
        top = (self.height() - size) / 2
        box = QRectF(2, top, size, size)
        checked = self.isChecked()

        if checked:
            gradient = QLinearGradient(box.topLeft(), box.bottomRight())
            gradient.setColorAt(0.0, QColor("#6366f1"))
            gradient.setColorAt(1.0, QColor("#38bdf8"))
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(QColor(255, 255, 255, 200))
            painter.setPen(QPen(QColor("#cbd2e1"), 1.4))
        painter.drawRoundedRect(box, 6, 6)

        if checked:
            pen = QPen(QColor("#ffffff"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(box.left() + 5.0, box.top() + 10.4)
            path.lineTo(box.left() + 8.6, box.top() + 14.0)
            path.lineTo(box.left() + 15.2, box.top() + 6.4)
            painter.drawPath(path)

        painter.setPen(QColor("#111827"))
        font = QFont(self.font())
        font.setPointSizeF(10.0)
        painter.setFont(font)
        text_rect = QRectF(box.right() + 10, 0, self.width() - box.right() - 12, self.height())
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self.text())
        painter.end()


class StatusLabel(QLabel):
    """Плашка статуса: градиент из QSS + мягкая подсветка, нарисованная вручную."""

    _GLOW = {
        "statusOk": QColor(16, 185, 129, 60),
        "statusErr": QColor(220, 38, 38, 34),
        "statusWarn": QColor(245, 158, 11, 34),
    }

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setObjectName("statusIdle")
        self.setMinimumHeight(46)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        color = self._GLOW.get(self.objectName())
        if color is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        for step in range(3, 0, -1):
            tint = QColor(color.red(), color.green(), color.blue(), color.alpha() // step)
            painter.setPen(QPen(tint, 1.1 * step))
            painter.drawRoundedRect(rect.adjusted(step, step, -step, -step), 14, 14)
        painter.end()


class GlassCard(QFrame):
    """Полупрозрачная карточка с мягким свечением (glassmorphism)."""

    def __init__(self, parent: QWidget | None = None, *, glow_color: QColor | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("glassCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        glow(self, glow_color or QColor(99, 102, 241, 38), blur=34.0, dy=10.0)


class LogoMark(QWidget):
    """Логотип VaultCore из ресурсов приложения (с мягкой тенью)."""

    def __init__(self, parent: QWidget | None = None, size: int = 46) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        from .. import paths

        self._pixmap = QPixmap(str(paths.resource("assets/logo.png")))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._pixmap.isNull():  # запасной вариант, если ресурс потерялся
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor("#6366f1"))
            gradient.setColorAt(1.0, QColor("#38bdf8"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, 13, 13)
            painter.end()
            return

        target = QRectF(0, 0, self._size, self._size)
        scaled = self._pixmap.scaled(
            int(self._size * 2),
            int(self._size * 2),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(target.toRect(), scaled)
        painter.end()
