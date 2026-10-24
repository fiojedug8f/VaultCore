"""Рендер документа в PDF A4.

Почему программная вёрстка (ReportLab), а не HTML→PDF:
    * нет системных зависимостей (WeasyPrint требует GTK на Windows) и нет
      «плавающих» версий браузерного движка — вывод детерминирован;
    * полный текстовый слой из настоящих глифов (важно: PDF должен позволять
      извлечь содержимое и подпись и проверить их программно);
    * двухпроходная сборка даёт корректную нумерацию «Стр. X из Y».

Вёрстка управляется внешним шаблоном ``templates/document.json`` (см.
:mod:`vaultcore.render.template`).
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics  # noqa: F401 - реэкспорт для утилит
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable
from xml.sax.saxutils import escape

from .. import canonical, codec, crypto, paths, __version__
from ..fmt import local_label
from .fonts import FontBook, register_fonts
from .qr import qr_matrix as _qr_matrix_of
from .template import Template, load_template

PAGE_W, PAGE_H = A4


class _QRFlowable(Flowable):
    """Векторный QR-код: модули рисуются прямоугольниками, без растровых XObject."""

    def __init__(self, matrix: tuple[bytearray, ...], size: float, color) -> None:
        super().__init__()
        self.matrix = matrix
        self.size = size
        self.color = color
        self.border = 2  # тихая зона в модулях

    def wrap(self, availWidth, availHeight):  # noqa: N802 - API ReportLab
        return self.size, self.size

    def draw(self) -> None:
        rows = len(self.matrix)
        if not rows:
            return
        total = rows + 2 * self.border
        module = self.size / total
        self.canv.saveState()
        self.canv.setFillColor(self.color)
        for y, row in enumerate(self.matrix):
            for x, value in enumerate(row):
                if value:
                    px = (x + self.border) * module
                    py = self.size - (y + 1 + self.border) * module
                    self.canv.rect(px, py, module, module, stroke=0, fill=1)
        self.canv.restoreState()


@dataclass
class _Ctx:
    payload: canonical.Payload
    code: str
    template: Template
    book: FontBook
    qr_matrix: tuple[bytearray, ...] | None
    ephemeral: bool
    total_pages: int

    # --- геометрия --------------------------------------------------------

    @property
    def margin(self) -> float:
        return self.template.num("page", "marginMm", 20.0) * mm

    @property
    def content_width(self) -> float:
        return PAGE_W - 2 * self.margin

    @property
    def footer_y(self) -> float:
        return self.template.num("page", "footerMm", 14.0) * mm

    @property
    def header_height(self) -> float:
        return self.template.num("page", "headerMm", 34.0) * mm

    @property
    def header_compact(self) -> float:
        return self.template.num("page", "headerCompactMm", 14.0) * mm


# --------------------------------------------------------------------------
# Отрисовка страницы: рамка, штамп, шапка, колонтитул
# --------------------------------------------------------------------------


def _draw_logo_image(c, x: float, y: float, size: float) -> bool:
    """Логотип VaultCore из ресурсов (fallback — векторный штамп)."""
    from reportlab.lib.utils import ImageReader

    path = paths.resource("assets/logo.png")
    if not path.exists():
        return False
    try:
        c.drawImage(ImageReader(str(path)), x, y, size, size, mask="auto")
    except Exception:  # noqa: BLE001 - логотип не должен ломать документ
        return False
    return True


def _draw_logo(c, x: float, y: float, size: float, color) -> None:
    """Векторный логотип: печать-кольцо, гексагон и галочка (без растровых файлов)."""
    c.saveState()
    cx, cy = x + size / 2, y + size / 2
    r_out = size * 0.44
    c.setStrokeColor(color)
    c.setLineWidth(size * 0.07)
    c.circle(cx, cy, r_out, stroke=1, fill=0)
    c.setLineWidth(size * 0.02)
    c.circle(cx, cy, r_out * 0.78, stroke=1, fill=0)

    r_hex = size * 0.21
    path = c.beginPath()
    for i in range(6):
        angle = math.radians(60 * i - 90)
        px, py = cx + r_hex * math.cos(angle), cy + r_hex * math.sin(angle)
        if i == 0:
            path.moveTo(px, py)
        else:
            path.lineTo(px, py)
    path.close()
    c.setLineWidth(size * 0.045)
    c.drawPath(path, stroke=1, fill=0)

    c.setLineWidth(size * 0.06)
    c.setLineCap(1)
    c.line(cx - r_hex * 0.5, cy + r_hex * 0.05, cx - r_hex * 0.12, cy - r_hex * 0.38)
    c.line(cx - r_hex * 0.12, cy - r_hex * 0.38, cx + r_hex * 0.55, cy + r_hex * 0.42)
    c.restoreState()


def _arc_text(c, text: str, radius: float, font: str, size: float) -> None:
    """Текст по дуге окружности (в системе координат уже сдвинутого canvas)."""
    from reportlab.pdfbase import pdfmetrics as _pm

    widths = [_pm.stringWidth(ch, font, size) + 1.6 for ch in text]
    total = sum(widths) or 1.0
    spread = 300.0
    pos = 90.0 - spread / 2
    for ch, width in zip(text, widths):
        step = width * spread / total
        angle = pos + step / 2
        rad = math.radians(angle)
        c.saveState()
        c.translate(radius * math.cos(rad), radius * math.sin(rad))
        c.rotate(angle - 90)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
        pos += step


def _fit_font_size(text: str, font: str, start_size: float, max_width: float) -> float:
    from reportlab.pdfbase import pdfmetrics as _pm

    size = start_size
    while size > 4 and _pm.stringWidth(text, font, size) > max_width:
        size -= 0.4
    return size


def _draw_watermark(c, ctx: _Ctx) -> None:
    """Декоративный круглый штамп. Полупрозрачный и НЕ является защитой."""
    tpl = ctx.template
    section = tpl.section("watermark")
    opacity = tpl.num("watermark", "opacity", 0.14)
    rotate = tpl.num("watermark", "rotate", -18.0)
    radius = tpl.num("watermark", "radius", 150.0)
    base = HexColor(tpl.color("stamp", "#7b1f2b"))

    c.saveState()
    c.translate(PAGE_W / 2, PAGE_H * 0.56)
    c.rotate(rotate)
    c.setFillColor(base, alpha=opacity)
    c.setStrokeColor(base, alpha=opacity)

    c.setLineWidth(3.2)
    c.circle(0, 0, radius, stroke=1, fill=0)
    c.setLineWidth(0.9)
    c.circle(0, 0, radius - 7, stroke=1, fill=0)
    c.setLineWidth(0.5)
    c.circle(0, 0, radius - 30, stroke=1, fill=0)

    arc = str(section.get("subText2", "VAULT CORE")) + " · " + str(
        section.get("subText2", "VAULT CORE")
    ) + " · "
    c.setFont(ctx.book.sans_bold, 11.5)
    _arc_text(c, arc, radius - 17, ctx.book.sans_bold, 11.5)

    center_text = str(section.get("text", "ОБРАЗЕЦ"))
    center_size = min(30.0, _fit_font_size(center_text, ctx.book.sans_bold, 30.0,
                                           (radius - 64) * 2))
    c.setFont(ctx.book.sans_bold, center_size)
    c.drawCentredString(0, -8, center_text)

    sub = str(section.get("subText", "НЕ ЮРИДИЧЕСКИЙ ДОКУМЕНТ"))
    sub_size = _fit_font_size(sub, ctx.book.sans_bold, 11.0, (radius - 58) * 2)
    c.setFont(ctx.book.sans_bold, sub_size)
    c.drawCentredString(0, -32, sub)
    c.restoreState()


def _draw_frame(c, ctx: _Ctx) -> None:
    """Тонкая двойная рамка страницы — «официальный» вид."""
    line = HexColor(ctx.template.color("line", "#c8d0da"))
    c.saveState()
    c.setStrokeColor(line, alpha=0.85)
    c.setLineWidth(0.7)
    inset = 11 * mm
    c.rect(inset, inset, PAGE_W - 2 * inset, PAGE_H - 2 * inset, stroke=1, fill=0)
    c.setLineWidth(0.3)
    c.rect(inset + 1.6 * mm, inset + 1.6 * mm,
           PAGE_W - 2 * inset - 3.2 * mm, PAGE_H - 2 * inset - 3.2 * mm, stroke=1, fill=0)
    c.restoreState()


def _draw_header(c, ctx: _Ctx, first: bool) -> None:
    tpl, book = ctx.template, ctx.book
    ink = HexColor(tpl.color("ink", "#1f2733"))
    muted = HexColor(tpl.color("muted", "#5a6472"))
    rule = HexColor(tpl.color("rule", "#1f3a5f"))
    top = PAGE_H - ctx.margin

    c.saveState()
    if first:
        logo_size = 15 * mm
        if not _draw_logo_image(c, ctx.margin, top - logo_size, logo_size):
            _draw_logo(c, ctx.margin, top - logo_size, logo_size, rule)

        text_x = ctx.margin + logo_size + 5.5 * mm
        c.setFillColor(ink)
        c.setFont(book.sans_bold, 15)
        c.drawString(text_x, top - 5.8 * mm, tpl.app("name", "VaultCore"))
        c.setFillColor(muted)
        c.setFont(book.sans, 8.8)
        c.drawString(text_x, top - 10.8 * mm, tpl.app("subtitle", ""))
        c.setFont(book.sans, 7.2)
        c.drawRightString(PAGE_W - ctx.margin, top - 5.8 * mm, tpl.app("tagline", ""))

        y = top - 19.5 * mm
        c.setStrokeColor(rule)
        c.setLineWidth(1.2)
        c.line(ctx.margin, y, PAGE_W - ctx.margin, y)
        c.setStrokeColor(HexColor(tpl.color("line", "#c8d0da")))
        c.setLineWidth(0.4)
        c.line(ctx.margin, y - 1.6, PAGE_W - ctx.margin, y - 1.6)
    else:
        c.setFillColor(muted)
        c.setFont(book.sans, 7.4)
        c.drawString(ctx.margin, top - 3.6 * mm,
                     f"{tpl.app('name', 'VaultCore')} · {tpl.app('subtitle', '')}")
        c.drawRightString(PAGE_W - ctx.margin, top - 3.6 * mm,
                          f"{tpl.text('idLabel', 'Документ №')} {ctx.payload.document_id}")
        y = top - 5.6 * mm
        c.setStrokeColor(HexColor(tpl.color("line", "#c8d0da")))
        c.setLineWidth(0.5)
        c.line(ctx.margin, y, PAGE_W - ctx.margin, y)
    c.restoreState()


def _draw_footer(c, ctx: _Ctx, page_no: int) -> None:
    tpl, book = ctx.template, ctx.book
    muted = HexColor(tpl.color("muted", "#5a6472"))
    line = HexColor(tpl.color("line", "#c8d0da"))
    y = ctx.footer_y
    c.saveState()
    c.setStrokeColor(line)
    c.setLineWidth(0.4)
    c.line(ctx.margin, y + 3.6 * mm, PAGE_W - ctx.margin, y + 3.6 * mm)
    c.setFillColor(muted)
    c.setFont(book.sans, 6.8)
    c.drawString(ctx.margin, y, tpl.text("footerNote", ""))
    total = ctx.total_pages or page_no
    c.drawRightString(
        PAGE_W - ctx.margin, y,
        f"{tpl.text('pageLabel', 'Стр.')} {page_no} из {total}",
    )
    c.restoreState()


def _make_on_page(ctx: _Ctx, first: bool):
    def on_page(c, doc) -> None:  # noqa: ANN001 - сигнатура ReportLab
        _draw_frame(c, ctx)
        _draw_watermark(c, ctx)
        _draw_header(c, ctx, first)
        _draw_footer(c, ctx, doc.page)

    return on_page


# --------------------------------------------------------------------------
# Стили и содержимое
# --------------------------------------------------------------------------


def _styles(ctx: _Ctx) -> dict[str, ParagraphStyle]:
    tpl, book = ctx.template, ctx.book
    ink = HexColor(tpl.color("ink", "#1f2733"))
    muted = HexColor(tpl.color("muted", "#5a6472"))
    stamp = HexColor(tpl.color("stamp", "#7b1f2b"))
    body_size = tpl.num("type", "bodySize", 11.0)
    leading = body_size * tpl.num("type", "leading", 1.45)
    block_size = tpl.num("type", "blockSize", 7.8)

    return {
        "title": ParagraphStyle(
            "poi-title", fontName=book.serif_bold, fontSize=tpl.num("type", "titleSize", 18.0),
            leading=tpl.num("type", "titleSize", 18.0) * 1.25, alignment=TA_CENTER,
            textColor=ink, spaceAfter=3,
        ),
        "meta": ParagraphStyle(
            "poi-meta", fontName=book.sans, fontSize=tpl.num("type", "metaSize", 8.4),
            leading=tpl.num("type", "metaSize", 8.4) * 1.35, alignment=TA_CENTER,
            textColor=muted, spaceAfter=1,
        ),
        "body": ParagraphStyle(
            "poi-body", fontName=book.serif, fontSize=body_size, leading=leading,
            alignment=TA_JUSTIFY, textColor=ink, spaceAfter=body_size * 0.55,
            splitLongWords=True, allowWidows=0, allowOrphans=0,
        ),
        "date": ParagraphStyle(
            "poi-date", fontName=book.serif, fontSize=body_size, leading=leading,
            alignment=TA_CENTER, textColor=ink, spaceAfter=1,
        ),
        "block_head": ParagraphStyle(
            "poi-block-head", fontName=book.sans_bold, fontSize=block_size + 1.6,
            leading=(block_size + 1.6) * 1.25, textColor=ink, spaceAfter=2,
        ),
        "block": ParagraphStyle(
            "poi-block", fontName=book.sans, fontSize=block_size,
            leading=block_size * 1.38, textColor=ink, spaceAfter=1.4,
        ),
        "block_muted": ParagraphStyle(
            "poi-block-muted", fontName=book.sans, fontSize=block_size - 0.4,
            leading=(block_size - 0.4) * 1.35, textColor=muted, spaceAfter=1.2,
        ),
        "mono": ParagraphStyle(
            "poi-mono", fontName=book.mono, fontSize=tpl.num("type", "monoSize", 6.4),
            leading=tpl.num("type", "monoSize", 6.4) * 1.3, textColor=ink,
            spaceAfter=1.2, splitLongWords=True,
        ),
        "label": ParagraphStyle(
            "poi-label", fontName=book.sans_bold, fontSize=block_size - 0.6,
            leading=(block_size - 0.6) * 1.3, textColor=muted, spaceAfter=0.4,
        ),
        "disclaimer": ParagraphStyle(
            "poi-disclaimer", fontName=book.sans_bold, fontSize=block_size + 0.8,
            leading=(block_size + 0.8) * 1.32, textColor=stamp, spaceAfter=1.5,
            spaceBefore=1.5,
        ),
        "small": ParagraphStyle(
            "poi-small", fontName=book.sans, fontSize=6.6, leading=8.4, textColor=muted,
        ),
    }


def _body_paragraphs(text: str, style: ParagraphStyle) -> list[Any]:
    out: list[Any] = []
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block.strip():
            continue
        html = "<br/>".join(escape(line) for line in block.split("\n"))
        out.append(Paragraph(html, style))
    return out


def _verification_block(
    ctx: _Ctx, st: dict[str, ParagraphStyle], key_fingerprint: str | None
) -> Any:
    tpl, payload = ctx.template, ctx.payload
    # Ключ автора теперь внутри документа: печатаем его целиком.
    key_fp = escape(key_fingerprint or crypto.fingerprint(payload.public_key))
    short_fp = crypto.fingerprint_short(payload.public_key)
    left: list[Any] = [
        Paragraph(escape(tpl.text("certifyHeading", "Заверено цифровой подписью")), st["block_head"]),
        Paragraph(escape(tpl.text("certifyIntro", "")), st["block_muted"]),
        Paragraph(f"<b>{escape(tpl.text('publicKeyLabel', 'Открытый ключ автора'))}</b>", st["label"]),
        Paragraph(escape(payload.public_key_b64), st["mono"]),
        Paragraph(
            f"<b>{escape(tpl.text('fingerprintShortLabel', 'Отпечаток для сверки'))}:</b> "
            f"{escape(short_fp)}    "
            f"<b>{escape(tpl.text('keyFingerprintLabel', 'Полный отпечаток'))}:</b> {key_fp}",
            st["block"],
        ),
        Paragraph(f"<b>{escape(tpl.text('signatureLabel', 'Подпись'))}</b>", st["label"]),
        Paragraph(escape(payload.signature_b64), st["mono"]),
        Paragraph(
            f"<b>{escape(tpl.text('signatureFingerprintLabel', 'Отпечаток подписи'))}:</b> "
            f"{crypto.signature_short(payload.signature)}",
            st["block"],
        ),
        Paragraph(
            f"<b>{escape(tpl.text('digestLabel', 'SHA-256'))}:</b> {payload.digest.hex()}",
            st["mono"],
        ),
        Paragraph(escape(tpl.text("tsaNote", "")), st["block_muted"]),
    ]
    if ctx.ephemeral:
        left.append(Paragraph(escape(tpl.text("ephemeralNote", "")), st["disclaimer"]))

    left.append(Paragraph(escape(tpl.text("disclaimer", "")), st["disclaimer"]))
    left.append(
        Table(
            [[""]],
            colWidths=[ctx.content_width * 0.42],
            rowHeights=[1],
            style=TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, HexColor(tpl.color("muted", "#5a6472")))]),
        )
    )
    left.append(Paragraph(escape(tpl.text("signatureLineLabel", "")), st["small"]))
    left.append(Spacer(1, 3))
    left.append(Paragraph(escape(tpl.text("verifyHint", "")), st["small"]))
    left.append(Paragraph(f"VC1 · v{payload.version} · VaultCore {__version__}", st["small"]))

    qr_min = tpl.num("qr", "sizeMm", 30.0) * mm
    if ctx.qr_matrix:
        # Плотный QR печатается крупнее: модуль не меньше ~0,3 мм, иначе
        # камера телефона перестаёт видеть код на бумаге.
        modules = len(ctx.qr_matrix)
        qr_size = max(qr_min, min(modules * 0.3 * mm, 44 * mm))
        right: list[Any] = [
            _QRFlowable(ctx.qr_matrix, qr_size, HexColor(tpl.color("rule", "#1f3a5f"))),
            Paragraph(escape(tpl.text("qrCaption", "")), st["label"]),
            Paragraph(escape(tpl.text("qrHint", "")), st["small"]),
        ]
    else:
        qr_size = qr_min
        right = [
            Paragraph(escape(tpl.text("qrCaption", "")), st["label"]),
            Paragraph(escape(tpl.text("qrTooLong", "")), st["small"]),
        ]

    # Ширина колонок: QR не должен упираться в рамку блока (padding учитывается).
    padding = 7
    qr_col = qr_size + 2 * padding
    col_widths = [ctx.content_width - qr_col, qr_col]
    table = Table([[left, right]], colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor(tpl.color("blockBg", "#f5f7fa"))),
                ("BOX", (0, 0), (-1, -1), 0.9, HexColor(tpl.color("blockBorder", "#9aa7b6"))),
                ("INNERGRID", (0, 0), (-1, -1), 0.0, HexColor(tpl.color("blockBg", "#f5f7fa"))),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _local_time_line(ctx: _Ctx) -> str:
    tpl = ctx.template
    try:
        return f"{escape(tpl.text('localDateLabel', ''))}: {escape(local_label(ctx.payload))}"
    except Exception:  # noqa: BLE001 - отображение не должно ломать документ
        return ""


def _stack_height(flowables: list[Any], width: float) -> float:
    """Оценка высоты вертикального стека (для прижатия блока к низу страницы)."""
    total = 0.0
    for flow in flowables:
        _, height = flow.wrap(width, 1e9)
        total += height
        get_before = getattr(flow, "getSpaceBefore", None)
        get_after = getattr(flow, "getSpaceAfter", None)
        if get_before:
            total += get_before()
        if get_after:
            total += get_after()
    return total


def _story(ctx: _Ctx, key_fingerprint: str | None) -> list[Any]:
    tpl, payload = ctx.template, ctx.payload
    st = _styles(ctx)
    story: list[Any] = [NextPageTemplate("later"), Spacer(1, 2)]

    story.append(Paragraph(escape(payload.title), st["title"]))
    story.append(
        Paragraph(
            f"{escape(tpl.text('idLabel', 'Документ №'))} {payload.document_id} · "
            f"{escape(tpl.text('formatLabel', 'формат кода VC1 v'))}{payload.version}",
            st["meta"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    story.append(
        Paragraph(
            f"<b>{escape(tpl.text('dateLabel', 'Дата создания (UTC)'))}:</b> {escape(payload.ts)}",
            st["date"],
        )
    )
    local_line = _local_time_line(ctx)
    if local_line:
        story.append(Paragraph(local_line, st["meta"]))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor(tpl.color("line", "#c8d0da")),
                            spaceBefore=2, spaceAfter=7))

    story.extend(_body_paragraphs(payload.text, st["body"]))
    story.append(Spacer(1, 7 * mm))

    block_parts = [_verification_block(ctx, st, key_fingerprint)]

    # Короткий документ: прижимаем блок заверения к нижней части страницы —
    # так документ выглядит как официальный бланк, а не как обрывок текста.
    try:
        frame_height = PAGE_H - ctx.margin - ctx.header_height
        used = _stack_height(story, ctx.content_width)
        block_height = _stack_height(block_parts, ctx.content_width)
        gap = frame_height - used - block_height - 12
        if gap > 36:
            story.append(Spacer(1, gap))
    except Exception:  # noqa: BLE001 - косметика не должна ломать рендер
        pass

    story.append(KeepTogether(block_parts))
    return story


# --------------------------------------------------------------------------
# Сборка PDF
# --------------------------------------------------------------------------


def _build(target: Any, ctx: _Ctx, *, key_fingerprint: str | None, total_pages: int) -> int:
    ctx.total_pages = total_pages
    margin = ctx.margin
    from reportlab.pdfgen.canvas import Canvas

    def _canvas(*args, **kwargs):  # noqa: ANN001, ANN202
        # Начальный шрифт страницы тоже наш TTF: иначе ReportLab кладёт в ресурсы
        # немой Helvetica (не встроенный, без кириллицы).
        kwargs.setdefault("initialFontName", ctx.book.serif)
        kwargs.setdefault("initialFontSize", 10)
        return Canvas(*args, **kwargs)

    doc = BaseDocTemplate(
        target,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"{ctx.payload.title} — VaultCore",
        author="VaultCore",
        subject=f"VaultCore code: {ctx.code}",
        keywords="VaultCore;VC1;Ed25519;не юридический документ",
        creator=f"VaultCore {__version__}",
        producer=f"VaultCore {__version__}",
    )

    width = ctx.content_width
    first_height = PAGE_H - margin - ctx.header_height
    later_height = PAGE_H - margin - ctx.header_compact
    first_frame = Frame(margin, margin, width, first_height, id="first",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later_frame = Frame(margin, margin, width, later_height, id="later",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=[first_frame], onPage=_make_on_page(ctx, True)),
            PageTemplate(id="later", frames=[later_frame], onPage=_make_on_page(ctx, False)),
        ]
    )
    doc.build(_story(ctx, key_fingerprint), canvasmaker=_canvas)
    return doc.page


def _prepare(payload: canonical.Payload, code: str | None, template: Template | None,
             ephemeral: bool) -> _Ctx:
    tpl = template or load_template()
    book = register_fonts()
    code_text = code or codec.encode(payload)
    matrix = _qr_matrix_of(code_text)
    return _Ctx(payload=payload, code=code_text, template=tpl, book=book,
                qr_matrix=matrix[0] if matrix else None, ephemeral=ephemeral, total_pages=0)


def render_pdf(
    payload: canonical.Payload,
    out_path: Path | str,
    *,
    code: str | None = None,
    template: Template | None = None,
    key_fingerprint: str | None = None,
    ephemeral: bool = False,
) -> Path:
    """Пишет PDF A4 и возвращает путь."""
    ctx = _prepare(payload, code, template, ephemeral)
    buffer = io.BytesIO()
    total = _build(buffer, ctx, key_fingerprint=key_fingerprint, total_pages=0)
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _build(str(target), ctx, key_fingerprint=key_fingerprint, total_pages=total)
    return target


def render_pdf_bytes(
    payload: canonical.Payload,
    *,
    code: str | None = None,
    template: Template | None = None,
    key_fingerprint: str | None = None,
    ephemeral: bool = False,
) -> bytes:
    """PDF в память (для предпросмотра в интерфейсе)."""
    ctx = _prepare(payload, code, template, ephemeral)
    buffer = io.BytesIO()
    total = _build(buffer, ctx, key_fingerprint=key_fingerprint, total_pages=0)
    out = io.BytesIO()
    _build(out, ctx, key_fingerprint=key_fingerprint, total_pages=total)
    return out.getvalue()


def render_local_datetime(payload: canonical.Payload, tz=None) -> datetime:
    """Местное время создания (для интерфейса; в подпись не входит)."""
    return payload.local_datetime(tz)
