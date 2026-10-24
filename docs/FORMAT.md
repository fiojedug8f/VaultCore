# Формат кода VaultCore, версия 1 (`VC1`)

Документ — это не PDF. Документ — это подписанные поля: версия, **открытый
ключ автора**, заголовок, текст и дата. PDF, QR-код, ссылка и файл `.poi` —
лишь способы передать одни и те же байты.

Ключ автора лежит **внутри кода**, поэтому приложение мультипользовательское:
получателю не нужно заранее настраивать «чью-то» сборку или импортировать
чужой ключ — документ самодостаточен.

---

## 1. Контейнер

```
code = "VC1." + base64url_nopad( utf8( json_payload ) )
```

* `base64url_nopad` — `A–Z a–z 0–9 - _`, **без** `=` и переводов строк (RFC 4648 §5).
* Декодер обязан отвергать padding, не-UTF-8 и любую неканоническую запись
  (проверка: `b64u_encode(b64u_decode(x)) == x`).

Ссылки — обёртки над кодом:

| Формат | Пример |
|---|---|
| Собственная схема | `vaultcore://verify?code=VC1....` |
| HTTPS (код во фрагменте) | `https://vaultcore.app/verify#code=VC1....` |

---

## 2. JSON-полезная нагрузка

Ровно шесть полей, все обязательны, лишние запрещены:

```json
{"v":1,"pk":"A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg","title":"…","text":"…","ts":"2026-10-21T14:32:00Z","sig":"…"}
```

| Поле | Тип | Ограничения |
|---|---|---|
| `v` | целое | строго `1` |
| `pk` | строка | base64url, ровно 32 байта (открытый ключ Ed25519), каноническая запись |
| `title` | строка | ≤ 200 символов, одна строка, нормализован |
| `text` | строка | 1…100 000 символов, нормализован |
| `ts` | строка | ровно `YYYY-MM-DDThh:mm:ssZ`, UTC |
| `sig` | строка | base64url, ровно 64 байта |

Строгий разбор: объект верхнего уровня; дубликаты ключей запрещены; набор
ключей ровно `{v,pk,title,text,ts,sig}`; размер ≤ 420 000 байт. Дайджест в коде
не передаётся — верификатор всегда пересчитывает его из полей.

---

## 3. Канонические байты

```
DOMAIN = utf8("vaultcore.code.v1")
frame(x) = u32_be(len(x)) || x

preimage = DOMAIN || frame(ascii("1"))
                   || frame(ascii(pk))
                   || frame(utf8(title))
                   || frame(utf8(text))
                   || frame(ascii(ts))

digest = SHA-256(preimage)
sig    = Ed25519.sign(private_seed, digest)
```

* Ключ входит в подписанные байты: подменить `pk` нельзя, не сломав подпись.
* Префиксы длины убирают неоднозначность границ полей.
* Подписывается 32-байтовый дайджест штатным Ed25519 (**не** Ed25519ph).

Отпечатки (в подпись не входят):

```
signature_short   = lowercase_hex(sig[:8])                         # 16 символов
fingerprint       = ":".join(upper_hex(b) for b in sha256(pk)[:8])   # 8 байт
fingerprint_short = первые 8 hex-символов fingerprint: "56:47:5A:A7"
```

`fingerprint_short` — то, что получатель сверяет с отправителем в мессенджере;
полный отпечаток остаётся для ручной проверки.

---

## 4. Алгоритм проверки

```
1. payload = strict_json( b64u_decode(code[4:]) )
2. digest  = sha256(preimage(payload.v, payload.pk, payload.title, payload.text, payload.ts))
3. ok      = Ed25519.verify(payload.pk, digest, payload.sig)      # ключ ИЗ документа
4. доверие = необязательная сверка: payload.pk == ожидаемый ключ?
```

Результаты:

* подпись сходится → **документ подлинный** (математически); показывается
  отпечаток ключа автора для сверки с отправителем;
* передан/вшит ожидаемый ключ и он совпал → статус «ключ автора подтверждён»;
* ключ не совпал → **документ подписан другим ключом**, содержимое скрывается;
* подпись не сходится → **документ изменён или подпись недействительна**.

---

## 5. Тестовый вектор

Сид демонстрационного ключа — `000102…1f` (не настоящий ключ).

```
pk (b64u)         = A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg
fingerprint       = 56:47:5A:A7:54:63:47:4C
fingerprint_short = 56:47:5A:A7

v     = 1
title = Вектор формата
text  = Проверка независимого верификатора VaultCore.
ts    = 2026-10-21T14:32:00Z

digest = 64bb7072d025876877a5a2865d8360c1a3cb172e5740c6a599fd0f65bfa0b42a
sig    = 0Qp6MXDENDS60IP_5qyZo5s6jb2uUQOoUl7hYPOND6yHPiNWy-LnjBq71hhFAQGyzcWgKq005la6cWV6UZ9dDw

code =
VC1.eyJ2IjoxLCJwayI6IkE2RUh2X1BPRUw0ZGNOMFk1MHZBbVdmazFqQ2JwUTFmSGR5R1pCSlZNYmciLCJ0
aXRsZSI6ItCS0LXQutGC0L7RgCDRhNC-0YDQvNCw0YLQsCIsInRleHQiOiLQn9GA0L7QstC10YDQutCwINC90LXQ
t9Cw0LLQuNGB0LjQvNC-0LPQviDQstC10YDQuNGE0LjQutCw0YLQvtGA0LAgVmF1bHRDb3JlLiIsInRzIjoiMjAy
Ni0xMC0yMVQxNDozMjowMFoiLCJzaWciOiIwUXA2TVhERU5EUzYwSVBfNXF5Wm81czZqYjJ1VVFPb1VsN2hZUE9O
RDZ5SFBpTld5LUxuakJxNzFoaEZBUUd5emNXZ0txMDA1bGE2Y1dWNlVaOWREdyJ9
```

(В коде переводы строк добавлены только для читаемости.)

---

## 6. Верификатор-эталон (≈20 строк)

```python
import base64, hashlib, json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DOMAIN = b"vaultcore.code.v1"
FIELDS = {"v", "pk", "title", "text", "ts", "sig"}

def b64u(s: str) -> bytes:
    assert set(s) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def frame(b: bytes) -> bytes:
    return len(b).to_bytes(4, "big") + b

def verify(code: str) -> tuple[bool, dict]:
    assert code.startswith("VC1.")
    payload = json.loads(b64u(code[4:]).decode("utf-8"))
    assert set(payload) == FIELDS and payload["v"] == 1
    preimage = (DOMAIN + frame(b"1") + frame(payload["pk"].encode())
                + frame(payload["title"].encode()) + frame(payload["text"].encode())
                + frame(payload["ts"].encode()))
    digest = hashlib.sha256(preimage).digest()
    try:
        Ed25519PublicKey.from_public_bytes(b64u(payload["pk"])).verify(
            b64u(payload["sig"]), digest)
        return True, payload
    except Exception:
        return False, payload
```

---

## 7. Совместимость

* Код начинается с `VC1.`; старые коды `POI1./POI2.` не поддерживаются.
* Любое изменение состава полей → `v=2`, префикс `VC2.`, новый `DOMAIN`.
* Вера в «правильный» ключ — отдельный, необязательный слой: вшитый при сборке
  ключ или отпечаток, присланный автором. Без него проверяется целостность.
