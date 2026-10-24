"""Форматирование дат для отображения (не входит в подпись)."""

from __future__ import annotations

from datetime import datetime, timezone

from .canonical import Payload


def utc_offset_label(dt: datetime) -> str:
    """``UTC+03:00`` вместо платформенных имён вида «RTZ 2 (зима)»."""
    offset = dt.utcoffset()
    if offset is None:
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "−"
    hours, minutes = divmod(abs(total_minutes), 60)
    if hours == 0 and minutes == 0:
        return "UTC"
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def local_label(payload: Payload, tz=None) -> str:
    """Местное время создания: ``21.10.2026 18:38 (UTC+03:00)``."""
    try:
        dt = payload.local_datetime(tz if tz is not None else timezone.utc)
        if tz is None:
            dt = dt.astimezone()
        return f"{dt.strftime('%d.%m.%Y %H:%M')} ({utc_offset_label(dt)})"
    except Exception:  # noqa: BLE001 - форматирование не должно ломать рендер
        return "—"
