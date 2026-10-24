"""Генерирует примеры в ``examples/`` (PDF, код, ссылка, .poi, ключ).

Примеры подписаны ДЕМОНСТРАЦИОННЫМ ключом с фиксированным сидом
(``bytes(range(32))``) — так их можно воспроизвести и проверить независимо.
Этот ключ не является чьим-либо настоящим ключом и не должен использоваться
для реальных документов.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vaultcore import canonical, codec, crypto, document  # noqa: E402
from vaultcore.identity import IdentityService  # noqa: E402
from vaultcore.keystore.base import Keystore  # noqa: E402
from vaultcore.render import render_pdf  # noqa: E402
from vaultcore.storage import save_document  # noqa: E402

DEMO_SEED = bytes(range(32))
DEMO_TS = "2026-10-21T14:32:00Z"

TITLE = "Заверенное заявление о намерении"

TEXT = (
    "Настоящим подтверждаю намерение провести встречу по проекту 21 октября 2026 года в 16:00 "
    "и зафиксировать достигнутые договорённости без последующего изменения условий.\n\n"
    "Пункт 2. Содержимое зафиксировано в момент создания и подписано цифровой подписью "
    "Ed25519: любое изменение текста, заголовка или даты делает подпись недействительной.\n\n"
    "Пункт 3. Проверка выполняется офлайн, без обращения к сети; открытый ключ автора "
    "публикуется отдельно.\n\n"
    "Пункт 4. Документ не имеет юридической силы: это инструмент фиксации намерения."
)


class DemoKeystore(Keystore):
    name = "demo"

    def describe(self) -> str:
        return "демонстрационный ключ с фиксированным сидом"

    def exists(self) -> bool:
        return True

    def _load_or_create_seed(self) -> bytes:
        return DEMO_SEED


def main() -> int:
    out_dir = ROOT / "examples"
    out_dir.mkdir(exist_ok=True)

    service = IdentityService(keystore=DemoKeystore(), data_dir=ROOT / ".tmp" / "examples-identity")
    identity = service.identity()
    payload, code = document.seal(service, TITLE, TEXT, ts=DEMO_TS)

    pdf_path = render_pdf(payload, out_dir / "sample_document.pdf", code=code)
    save_document(out_dir / "sample.poi", payload, code)
    (out_dir / "sample_code.txt").write_text(code + "\n", "utf-8")
    (out_dir / "sample_link.txt").write_text(codec.build_link(code) + "\n", "utf-8")
    (out_dir / "demo_public_key.txt").write_text(
        "\n".join(
            [
                "# Демонстрационный открытый ключ (НЕ используйте для реальных документов)",
                f"# Отпечаток: {identity.fingerprint}",
                f"# Сид примера: {DEMO_SEED.hex()}",
                identity.public_b64,
                "",
            ]
        ),
        "utf-8",
    )

    print(f"PDF:        {pdf_path} ({pdf_path.stat().st_size} байт)")
    print(f"Код:        {len(code)} символов")
    print(f"Документ №  {payload.document_id}")
    print(f"Отпечаток:  {identity.fingerprint}")
    print(f"digest:     {payload.digest.hex()}")
    print(f"pubkey:     {identity.public_b64}")

    # Самопроверка: пример обязан проверяться тем же ключом.
    result = document.verify(code, identity.public_key)
    assert result.status == "valid", result.reason
    assert result.trust == "pinned"
    assert payload.digest == canonical.compute_digest(
        payload.version, payload.public_key_b64, payload.title, payload.text, payload.ts
    )
    assert crypto.verify_digest(payload.public_key, payload.digest, payload.signature)
    print(f"Отпечаток для сверки: {crypto.fingerprint_short(payload.public_key)}")
    print("Проверка:   valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
