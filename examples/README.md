# Примеры

Все файлы в этой папке созданы скриптом `tools/make_examples.py` и подписаны
**демонстрационным ключом** с фиксированным сидом (`000102…1f`). Этот ключ
опубликован здесь же — он не является чьим-либо настоящим ключом и не должен
использоваться для реальных документов.

| Файл | Что это |
|---|---|
| `sample_document.pdf` | документ A4: шапка, штамп «ОБРАЗЕЦ», блок заверения, QR-код |
| `sample_code.txt` | передаваемый код `VC1.…` (открытый ключ автора внутри) |
| `sample_link.txt` | ссылка `vaultcore://verify?code=…` |
| `sample.poi` | файл документа: метаданные в комментариях + код |
| `demo_public_key.txt` | открытый ключ и отпечаток (`56:47:5A:A7:54:63:47:4C`) |

Параметры примера (детерминированы, воспроизводятся повторным запуском):

```
title = Заверенное заявление о намерении
ts    = 2026-10-21T14:32:00Z
pk    = A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg
digest= a64233d20981a9da69581b70d0d3f65f7015690f73a7a494a5808f8445fcdf45
sig   = _YjqHNFjblKSv8TdWrCHu5oLEBLsLvQyFKj21JUx7gR06np-qPTgL_9RLKBEpLGK4AOrza-Q-TTrMjgo3mwTCg
```

Проверка примера:

```powershell
python -m vaultcore.cli verify --code-file examples/sample.poi ^
  --pubkey examples/demo_public_key.txt
# ... Статус: valid — Документ подлинный, содержимое не изменялось
```

Пересоздать примеры:

```powershell
python tools/make_examples.py
```
