"""Точка входа для PyInstaller: VaultCore (создание + проверка, --uninstall)."""

import sys

from vaultcore.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
