"""Пользовательское соглашение: показ при первом запуске и локальная фиксация принятия.

Текст лежит отдельным файлом (``eula_ru.md`` в ресурсах пакета), чтобы его можно
было обновить без пересборки. Принятие хранится как
``{версия, sha256 текста, дата принятия}``: если файл изменили (даже не подняв
версию), приложение снова покажет соглашение — «принял старую редакцию» не
должно означать «принял любую будущую».
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import canonical, paths

_EULA_VERSION_RE = re.compile(r"<!--\s*eula-version:\s*([0-9][0-9A-Za-z.\-]*)\s*-->")


class EulaError(RuntimeError):
    """Текст соглашения отсутствует или повреждён."""


@dataclass(frozen=True)
class Eula:
    version: str
    text: str
    sha256: str
    path: Path | None = None

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]


@dataclass(frozen=True)
class Acceptance:
    version: str
    sha256: str
    accepted_at: str
    app_version: str
    platform: str

    def as_dict(self) -> dict:
        return {
            "eulaVersion": self.version,
            "eulaSha256": self.sha256,
            "acceptedAt": self.accepted_at,
            "appVersion": self.app_version,
            "platform": self.platform,
        }


def default_eula_path() -> Path:
    """Упакованная редакция; для запуска из репозитория — файл в его корне."""
    packaged = paths.resource("assets/eula_ru.md")
    if packaged.exists():
        return packaged
    root = Path(__file__).resolve().parents[2] / "eula_ru.md"
    if root.exists():
        return root
    raise EulaError("Файл пользовательского соглашения не найден (eula_ru.md)")


def _canonical_text(raw: str) -> str:
    return raw.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def load_eula(path: Path | str | None = None) -> Eula:
    target = Path(path) if path is not None else default_eula_path()
    if not target.exists():
        raise EulaError(f"Файл соглашения не найден: {target}")
    try:
        raw = target.read_text("utf-8-sig")
    except OSError as exc:
        raise EulaError(f"Не удалось прочитать соглашение: {exc}") from exc

    match = _EULA_VERSION_RE.search(raw)
    if not match:
        raise EulaError(
            "В тексте соглашения нет маркера версии "
            "(<!-- eula-version: 1.0 -->) — обновление нельзя отследить"
        )
    version = match.group(1)
    body = _EULA_VERSION_RE.sub("", raw, count=1)
    body = _canonical_text(body)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return Eula(version=version, text=body, sha256=digest, path=target)


def read_acceptance(path: Path | str | None = None) -> Acceptance | None:
    target = Path(path) if path is not None else paths.eula_acceptance_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return Acceptance(
            version=str(data["eulaVersion"]),
            sha256=str(data["eulaSha256"]),
            accepted_at=str(data["acceptedAt"]),
            app_version=str(data.get("appVersion", "")),
            platform=str(data.get("platform", "")),
        )
    except KeyError:
        return None


def is_accepted(eula: Eula, path: Path | str | None = None) -> bool:
    """Принята ли ИМЕННО эта редакция (по хешу текста, а не только по номеру)."""
    acceptance = read_acceptance(path)
    return acceptance is not None and acceptance.sha256 == eula.sha256


def accept(eula: Eula, path: Path | str | None = None) -> Acceptance:
    """Фиксирует принятие локально (атомарная запись)."""
    import sys

    from . import __version__

    target = Path(path) if path is not None else paths.eula_acceptance_path()
    acceptance = Acceptance(
        version=eula.version,
        sha256=eula.sha256,
        accepted_at=canonical.utc_now_iso(),
        app_version=__version__,
        platform=f"{sys.platform}",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(acceptance.as_dict(), ensure_ascii=False, indent=2) + "\n", "utf-8")
    os.replace(tmp, target)
    return acceptance


def revoke(path: Path | str | None = None) -> None:
    """Сбрасывает принятие (для тестов и «сброса настроек»)."""
    target = Path(path) if path is not None else paths.eula_acceptance_path()
    target.unlink(missing_ok=True)
