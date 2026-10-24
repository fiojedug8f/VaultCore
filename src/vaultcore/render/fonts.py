"""Поиск и регистрация Unicode-шрифтов для PDF.

Почему не встроенные шрифты ReportLab (Helvetica/Times-Roman): они не содержат
кириллицы и не встраиваются в файл. Документ без встроенного шрифта на другом
компьютере может выглядеть иначе (а иногда — квадратами), что для «официального
вида» недопустимо.

Порядок поиска: упакованные шрифты → ``POI_FONTS_DIR`` → системные каталоги.
Если кириллический шрифт не найден, рендер падает с понятным сообщением, а не
выпускает документ с пустыми прямоугольниками вместо букв.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .. import paths

FONT_FAMILIES: dict[str, list[str]] = {
    "serif": [
        "PT_Serif-Web-Regular.ttf",
        "PTSerif-Regular.ttf",
        "times.ttf",
        "Times New Roman.ttf",
        "LiberationSerif-Regular.ttf",
        "DejaVuSerif.ttf",
        "NotoSerif-Regular.ttf",
    ],
    "serif_bold": [
        "PT_Serif-Web-Bold.ttf",
        "PTSerif-Bold.ttf",
        "timesbd.ttf",
        "Times New Roman Bold.ttf",
        "LiberationSerif-Bold.ttf",
        "DejaVuSerif-Bold.ttf",
        "NotoSerif-Bold.ttf",
    ],
    "serif_italic": [
        "PT_Serif-Web-Italic.ttf",
        "PTSerif-Italic.ttf",
        "timesi.ttf",
        "Times New Roman Italic.ttf",
        "LiberationSerif-Italic.ttf",
        "DejaVuSerif-Italic.ttf",
    ],
    "sans": [
        "PT_Sans-Web-Regular.ttf",
        "PTSans-Regular.ttf",
        "arial.ttf",
        "Arial.ttf",
        "LiberationSans-Regular.ttf",
        "DejaVuSans.ttf",
        "NotoSans-Regular.ttf",
    ],
    "sans_bold": [
        "PT_Sans-Web-Bold.ttf",
        "PTSans-Bold.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
        "LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "NotoSans-Bold.ttf",
    ],
    "mono": [
        "PT_Mono-Web-Regular.ttf",
        "PTMono-Regular.ttf",
        "cour.ttf",
        "Consola.ttf",
        "LiberationMono-Regular.ttf",
        "DejaVuSansMono.ttf",
        "NotoSansMono-Regular.ttf",
    ],
}

REGISTERED_NAMES = {
    "serif": "POI-Serif",
    "serif_bold": "POI-Serif-Bold",
    "serif_italic": "POI-Serif-Italic",
    "sans": "POI-Sans",
    "sans_bold": "POI-Sans-Bold",
    "mono": "POI-Mono",
}


class FontError(RuntimeError):
    """Не найден ни один пригодный Unicode-шрифт."""


@dataclass(frozen=True)
class FontBook:
    serif: str
    serif_bold: str
    serif_italic: str
    sans: str
    sans_bold: str
    mono: str
    sources: dict[str, str]

    def describe(self) -> str:
        return ", ".join(f"{k}={Path(v).name}" for k, v in self.sources.items())


def _font_dirs() -> list[Path]:
    dirs: list[Path] = [paths.assets_dir() / "fonts"]
    override = os.environ.get("POI_FONTS_DIR")
    if override:
        dirs.append(Path(override).expanduser())
    if os.name == "nt":
        win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        dirs.append(win)
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ]
    else:
        dirs += [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts",
        ]
    return dirs


def _glob_candidates(folder: Path, filename: str) -> list[Path]:
    direct = folder / filename
    if direct.exists():
        return [direct]
    if folder.exists():
        # На Linux шрифты лежат в подкаталогах (truetype/dejavu/...).
        try:
            return sorted(folder.rglob(filename))[:3]
        except OSError:
            return []
    return []


def find_font(role: str) -> Path | None:
    names = FONT_FAMILIES.get(role, [])
    for folder in _font_dirs():
        for name in names:
            for candidate in _glob_candidates(folder, name):
                if candidate.is_file():
                    return candidate
    return None


def _register(role: str, path: Path) -> str:
    name = REGISTERED_NAMES[role]
    try:
        existing = pdfmetrics.getFont(name)
        if existing:  # уже зарегистрирован в этом процессе
            return name
    except KeyError:
        pass
    pdfmetrics.registerFont(TTFont(name, str(path)))
    return name


_CACHE: FontBook | None = None


def register_fonts(force: bool = False) -> FontBook:
    """Регистрирует шрифты в ReportLab и возвращает имена для стилей."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for role in FONT_FAMILIES:
        found = find_font(role)
        if found:
            resolved[role] = found
        else:
            missing.append(role)

    if "serif" not in resolved and "sans" not in resolved:
        raise FontError(
            "Не найден ни один Unicode-шрифт с кириллицей. Установите системный шрифт "
            "(Times New Roman / DejaVu / Liberation) или положите TTF в "
            f"{paths.assets_dir() / 'fonts'} либо укажите каталог в POI_FONTS_DIR."
        )

    # Деградация по семейству: жирный/курсив → обычный, mono → sans.
    def fallback(role: str) -> str:
        if role in resolved:
            return _register(role, resolved[role])
        family = "serif" if role.startswith("serif") else ("mono" if role == "mono" else "sans")
        for alt in (family, "serif", "sans"):
            if alt in resolved:
                return _register(alt, resolved[alt])
        raise FontError(f"Нет шрифта для {role}")

    book = FontBook(
        serif=fallback("serif"),
        serif_bold=fallback("serif_bold"),
        serif_italic=fallback("serif_italic"),
        sans=fallback("sans"),
        sans_bold=fallback("sans_bold"),
        mono=fallback("mono"),
        sources={role: str(path) for role, path in resolved.items()},
    )
    # ReportLab использует эти семейства для <b>/<i> внутри Paragraph.
    pdfmetrics.registerFontFamily(
        book.serif, normal=book.serif, bold=book.serif_bold, italic=book.serif_italic,
        boldItalic=book.serif_bold,
    )
    pdfmetrics.registerFontFamily(
        book.sans, normal=book.sans, bold=book.sans_bold, italic=book.sans,
        boldItalic=book.sans_bold,
    )
    pdfmetrics.registerFontFamily(
        book.mono, normal=book.mono, bold=book.mono, italic=book.mono,
        boldItalic=book.mono,
    )

    # Стандартный «Helvetica» ReportLab не встраивается и не содержит кириллицы.
    # Текст им мы никогда не печатаем, но он попадает в ресурсы страницы как
    # начальный шрифт документа. Подменяем его нашим TTF, чтобы в PDF не
    # оставалось ни одного невстроенного шрифта.
    alias_source = resolved.get("serif") or resolved.get("sans")
    if alias_source is not None:
        try:
            pdfmetrics.registerFont(TTFont("Helvetica", str(alias_source)))
        except Exception:  # noqa: BLE001 - подмена не критична для рендера
            pass

    _CACHE = book
    return book
