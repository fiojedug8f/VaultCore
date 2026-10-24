"""Файлы документов (.poi) — перенос кода в виде файла.

Формат человекочитаемый: комментарии с метаданными и сам код в последней
строке. Код остаётся единственным носителем истины — метаданные в шапке
файла носят справочный характер и при проверке не используются.
"""

from __future__ import annotations

from pathlib import Path

from . import canonical, codec, crypto


def save_document(
    path: Path | str,
    payload: canonical.Payload,
    code: str,
    *,
    key_fingerprint: str | None = None,  # оставлено для совместимости: ключ уже в payload
    owner: str = "",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VaultCore — файл документа",
        "# Документ не имеет юридической силы. Это инструмент фиксации намерения.",
        f"# Заголовок: {payload.title}",
        f"# Создан (UTC): {payload.ts}",
        f"# Идентификатор: {payload.document_id}",
        f"# Отпечаток подписи: {crypto.signature_short(payload.signature)}",
        f"# Отпечаток ключа автора: {crypto.fingerprint(payload.public_key)}",
        f"# Открытый ключ автора: {payload.public_key_b64}",
    ]
    if owner:
        lines.append(f"# Владелец ключа: {owner}")
    lines.append(code)
    target.write_text("\n".join(lines) + "\n", "utf-8")
    return target


def load_document(path: Path | str) -> str:
    """Достаёт код из файла .poi (или любого текста с кодом внутри)."""
    text = Path(path).read_text("utf-8-sig")
    return codec.extract(text)
