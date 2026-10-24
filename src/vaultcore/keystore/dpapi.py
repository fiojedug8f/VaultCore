"""Windows DPAPI: закрытый ключ не лежит в открытом виде нигде и никогда.

Схема (ровно как в ТЗ):

1. При первом запуске генерируется Ed25519-сид (32 байта).
2. ``CryptProtectData`` с ``CRYPTPROTECT_UI_FORBIDDEN`` (и опционально
   ``CRYPTPROTECT_LOCAL_MACHINE``) шифрует его мастер-ключом DPAPI текущей
   учётной записи; дополнительно передаётся entropy — константа приложения.
3. Шифротекст пишется в ``%APPDATA%\\VaultCore\\key.blob`` (атомарно).
4. При подписи ``CryptUnprotectData`` возвращает сид, подпись вычисляется,
   сид затирается в памяти.
5. Копия ``key.blob`` на другом ПК/под другой учётной записью не расшифруется:
   DPAPI вернёт ошибку, приложение покажет её текстом, а не «тихо сгенерирует
   новый ключ» (иначе получатель молча получил бы другой авторский ключ).

Почему ctypes, а не pywin32: меньше зависимостей в сборке; используются только
две функции crypt32 с простыми сигнатурами.
"""

from __future__ import annotations

import ctypes
import os
import secrets
from ctypes import wintypes
from pathlib import Path

from .base import Keystore, KeystoreError, wipe

#: Константы из wincred.h / dpapi.h.
CRYPTPROTECT_UI_FORBIDDEN = 0x01
CRYPTPROTECT_LOCAL_MACHINE = 0x04

#: Дополнительная энтропия (RFC 2898-стиль «пароль» DPAPI). Копия blob без
#: знания этой строки не расшифруется даже на том же ПК.
ENTROPY = b"VaultCore/v1/ed25519-seed"

#: Магия файла: "VC1K" + байт флагов.
_MAGIC = b"VC1K"
_HEADER_LEN = len(_MAGIC) + 1


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


if os.name == "nt":  # pragma: no branch - на других ОС модуль просто не используется
    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),   # pDataIn
        wintypes.LPCWSTR,            # szDataDescr
        ctypes.POINTER(DATA_BLOB),   # pOptionalEntropy
        ctypes.c_void_p,             # pvReserved
        ctypes.c_void_p,             # pPromptStruct
        wintypes.DWORD,              # dwFlags
        ctypes.POINTER(DATA_BLOB),   # pDataOut
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),   # pDataIn
        ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr
        ctypes.POINTER(DATA_BLOB),   # pOptionalEntropy
        ctypes.c_void_p,             # pvReserved
        ctypes.c_void_p,             # pPromptStruct
        wintypes.DWORD,              # dwFlags
        ctypes.POINTER(DATA_BLOB),   # pDataOut
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    """Создаёт DATA_BLOB и держит буфер живым, пока он нужен."""
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _take(blob: DATA_BLOB) -> bytes:
    """Копирует данные из выходного блока и освобождает его через LocalFree."""
    try:
        if not blob.pbData or not blob.cbData:
            return b""
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        if blob.pbData:
            _kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def _win_error(what: str) -> KeystoreError:
    err = ctypes.get_last_error()
    try:
        text = ctypes.FormatError(err).strip() or f"код {err}"
    except Exception:  # noqa: BLE001 - сообщение об ошибке не должно падать
        text = f"код {err}"
    return KeystoreError(f"{what}: {text} (WinError {err})")


def protect(data: bytes, *, entropy: bytes = ENTROPY, machine_scope: bool = False) -> bytes:
    """Шифрует данные через DPAPI. Возвращает непрозрачный blob."""
    if os.name != "nt":
        raise KeystoreError("DPAPI доступен только в Windows")
    flags = CRYPTPROTECT_UI_FORBIDDEN | (CRYPTPROTECT_LOCAL_MACHINE if machine_scope else 0)
    in_blob, in_buf = _blob(data)
    ent_blob, ent_buf = _blob(entropy)
    out_blob = DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob), "VaultCore Ed25519 seed", ctypes.byref(ent_blob),
        None, None, flags, ctypes.byref(out_blob),
    )
    del in_buf, ent_buf  # noqa: F841 - держим буферы живыми до вызова
    if not ok:
        raise _win_error("DPAPI не смог зашифровать ключ")
    return _take(out_blob)


def unprotect(blob: bytes, *, entropy: bytes = ENTROPY, machine_scope: bool = False) -> bytes:
    """Расшифровывает blob DPAPI. На другом ПК/учётке вернёт KeystoreError."""
    if os.name != "nt":
        raise KeystoreError("DPAPI доступен только в Windows")
    flags = CRYPTPROTECT_UI_FORBIDDEN | (CRYPTPROTECT_LOCAL_MACHINE if machine_scope else 0)
    in_blob, in_buf = _blob(blob)
    ent_blob, ent_buf = _blob(entropy)
    out_blob = DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, ctypes.byref(ent_blob),
        None, None, flags, ctypes.byref(out_blob),
    )
    del in_buf, ent_buf  # noqa: F841
    if not ok:
        err = ctypes.get_last_error()
        if err in (0x8007000D, 0x8009000B, 0x80070057, 13):  # типичные коды «чужой blob»
            raise KeystoreError(
                "Файл ключа зашифрован DPAPI для другой учётной записи или другого "
                "компьютера. Ключ нельзя расшифровать здесь — скопируйте документы, "
                "а не файл ключа."
            )
        raise _win_error("DPAPI не смог расшифровать ключ")
    return _take(out_blob)


class DpapiKeystore(Keystore):
    """Сид, зашифрованный DPAPI, в ``<data_dir>/key.blob``."""

    name = "dpapi"

    def __init__(self, data_dir: Path, *, machine_scope: bool = False) -> None:
        self._path = Path(data_dir) / "key.blob"
        self._machine_scope = machine_scope

    # ------------------------------------------------------------------

    @staticmethod
    def available() -> bool:
        return os.name == "nt"

    def describe(self) -> str:
        scope = "локальный компьютер" if self._machine_scope else "текущий пользователь"
        return f"Windows DPAPI (область: {scope})"

    def exists(self) -> bool:
        return self._path.exists()

    def _read_blob(self) -> tuple[int, bytes]:
        raw = self._path.read_bytes()
        if len(raw) < _HEADER_LEN or not raw.startswith(_MAGIC):
            raise KeystoreError(
                "Файл ключа повреждён или имеет неизвестный формат. "
                "Удалите key.blob только если готовы потерять возможность подписывать "
                "старым ключом."
            )
        return raw[len(_MAGIC)], raw[_HEADER_LEN:]

    def _write_blob(self, flags: int, ciphertext: bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + f".{secrets.token_hex(4)}.tmp")
        tmp.write_bytes(_MAGIC + bytes([flags]) + ciphertext)
        try:
            os.replace(tmp, self._path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _load_or_create_seed(self) -> bytes:
        from .. import crypto

        if self._path.exists():
            flags, ciphertext = self._read_blob()
            machine_scope = bool(flags & CRYPTPROTECT_LOCAL_MACHINE)
            seed = unprotect(ciphertext, machine_scope=machine_scope)
            if len(seed) != 32:
                raise KeystoreError("DPAPI вернул ключ неверной длины")
            return seed

        seed = crypto.generate_seed()
        flags = CRYPTPROTECT_LOCAL_MACHINE if self._machine_scope else 0
        ciphertext = protect(seed, machine_scope=self._machine_scope)
        self._write_blob(flags, ciphertext)
        return seed

    def destroy(self) -> None:
        self._path.unlink(missing_ok=True)
