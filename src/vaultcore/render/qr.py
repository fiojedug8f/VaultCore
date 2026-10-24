"""QR-код как PNG в памяти (без временных файлов).

QR содержит тот же передаваемый код, что и в тексте документа. Ошибка
коррекции «M» — компромисс: код длинный, а печать/фото дают умеренные
искажения. Для очень длинных документов QR может не влезть в разумный
модульный размер — тогда :func:`qr_png_bytes` вернёт None, и документ
печатается без QR (код всё равно есть в PDF как текст и в метаданных).
"""

from __future__ import annotations

import io


def qr_available() -> bool:
    try:
        import segno  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def qr_png_bytes(
    data: str,
    *,
    scale: int = 6,
    border: int = 2,
    dark: str = "#1f3a5f",
    light: str = "#ffffff",
) -> bytes | None:
    """PNG с QR-кодом или None, если библиотека недоступна / данные не влезают."""
    try:
        import segno  # noqa: PLC0415
    except ImportError:
        return None
    try:
        code = segno.make_qr(data, error="m")
    except Exception:  # noqa: BLE001 - слишком длинные данные и т.п.
        return None
    # Не раздуваем QR до неудобных размеров на печати.
    if code.symbol_size(scale=scale, border=border)[0] > 1400:
        scale = max(2, scale // 2)
    buffer = io.BytesIO()
    try:
        code.save(buffer, kind="png", scale=scale, border=border, dark=dark, light=light)
    except Exception:  # noqa: BLE001
        return None
    return buffer.getvalue()


def qr_modules(data: str) -> int:
    """Число модулей QR по стороне (для проверки, что код влезает в печать)."""
    matrix = qr_matrix(data)
    return len(matrix[0]) if matrix else 0


def qr_matrix(
    data: str, *, max_modules: int = 145
) -> tuple[tuple[bytearray, ...], int] | None:
    """Матрица модулей QR (0/1) — из неё PDF рисуется вектором, без растров.

    Векторный QR печатается резко при любом масштабе. Если код не влезает даже
    в версию 40 или получается слишком «плотным» (модуль меньше ~0,5 мм на
    печати), возвращается None: нечитаемый QR хуже его отсутствия — полный код
    в этом случае остаётся в текстовом слое PDF.
    """
    try:
        import segno  # noqa: PLC0415
    except ImportError:
        return None
    for level in ("m", "l"):
        try:
            code = segno.make_qr(data, error=level)
        except Exception:  # noqa: BLE001 - слишком длинные данные и т.п.
            continue
        matrix = tuple(bytearray(row) for row in code.matrix)
        if len(matrix) > max_modules:
            continue
        return matrix, len(matrix)
    return None
