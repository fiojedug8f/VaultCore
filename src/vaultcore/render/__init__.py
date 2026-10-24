"""Слой рендера: PDF A4, внешний шаблон, шрифты, QR, HTML-предпросмотр."""

from .fonts import FontBook, FontError, register_fonts
from .pdf import render_pdf, render_pdf_bytes
from .preview import render_html
from .qr import qr_available, qr_png_bytes
from .template import Template, load_template

__all__ = [
    "FontBook",
    "FontError",
    "register_fonts",
    "render_pdf",
    "render_pdf_bytes",
    "render_html",
    "qr_png_bytes",
    "qr_available",
    "Template",
    "load_template",
]
