"""Точка входа: ``python -m vaultcore`` / ``python -m vaultcore --mode verify``."""

from __future__ import annotations

import sys


def main() -> int:
    from .ui.app import main as ui_main

    return ui_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
