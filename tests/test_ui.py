"""Смоук-тесты интерфейса (offscreen): окна строятся, запечатывание и проверка работают."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from vaultcore import document  # noqa: E402
from vaultcore.ui.eula_dialog import EulaDialog  # noqa: E402
from vaultcore.ui.main_window import MainWindow  # noqa: E402
from vaultcore.ui.theme import apply_theme  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    yield app


@pytest.fixture()
def window(qt_app, service):
    win = MainWindow(service=service)
    yield win
    win.close()


def test_window_has_both_tabs(window, service):
    """Одна программа, две вкладки — без «сборки автора/верификатора»."""
    assert window.tabs.count() == 2
    assert window.tabs.tabText(0).strip() == "Создание"
    assert window.tabs.tabText(1).strip() == "Проверка"
    assert service.identity().public_b64 in window.key_edit.toPlainText()


def test_window_without_service_still_verifies(qt_app, data_dir):
    """Без собственного ключа проверка чужих документов всё равно доступна."""
    win = MainWindow(service=None)
    try:
        assert win.tabs.count() == 2
        assert win.verify_panel is not None
    finally:
        win.close()


def test_author_panel_seals_and_locks(window, monkeypatch, service):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel = window.author_panel
    assert panel is not None
    panel.title_edit.setText("Заявление")
    panel.body_edit.setPlainText("Текст заявления о намерении.")
    panel._on_seal()

    assert panel._payload is not None
    assert panel.code_edit.toPlainText().startswith("VC1.")
    assert panel.body_edit.isEnabled() is False
    assert panel.title_edit.isEnabled() is False
    assert panel.seal_button.isEnabled() is False
    assert panel.save_button.isEnabled()
    assert panel._pdf_bytes.startswith(b"%PDF")
    assert document.verify(panel.code_edit.toPlainText(), service.identity().public_key).ok

    panel.reset()
    assert panel.body_edit.isEnabled() is True
    assert panel.code_edit.toPlainText() == ""


def test_author_panel_rejects_empty_text(window, monkeypatch):
    shown = {}
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.setdefault("warn", a))
    panel = window.author_panel
    panel.body_edit.setPlainText("   ")
    panel._on_seal()
    assert "warn" in shown
    assert panel._payload is None


def test_verify_panel_accepts_valid_code(window, service):
    _, code = document.seal(service, "Заявление", "Текст документа")
    panel = window.verify_panel
    panel.code_edit.setPlainText(code)
    panel._on_verify()

    assert panel._result is not None and panel._result.status == "valid"
    assert panel.status.objectName() == "statusOk"
    assert panel.save_pdf_button.isEnabled()
    assert panel._pdf_bytes.startswith(b"%PDF")
    # Ключ автора берётся из документа и показывается для сверки.
    assert panel._result.payload.public_key_b64 in panel.author_key_edit.toPlainText()
    assert "Отпечаток ключа автора" in panel.author_fp_label.text()


def test_verify_panel_rejects_tampered_document(window, service):
    _, code = document.seal(service, "Заявление", "Текст документа")
    broken = code[:-6] + ("AAAAAA" if not code.endswith("AAAAAA") else "BBBBBB")
    panel = window.verify_panel
    panel.code_edit.setPlainText(broken)
    panel._on_verify()

    assert panel._result is not None and panel._result.status != "valid"
    assert panel.status.objectName() in {"statusErr", "statusWarn"}
    assert panel.save_pdf_button.isEnabled() is False


def test_verify_panel_accepts_foreign_author(window, foreign_service):
    """Чужой документ: подпись верна, ключ пришёл внутри кода."""
    _, code = document.seal(foreign_service, "Чужое заявление", "Текст другого автора")
    panel = window.verify_panel
    panel.code_edit.setPlainText(code)
    panel._on_verify()
    assert panel._result.status == "valid"
    assert panel._result.payload.public_key == foreign_service.identity().public_key


def test_eula_dialog_requires_checkbox(qt_app):
    from vaultcore import eula as eula_mod

    dialog = EulaDialog(eula_mod.load_eula())
    try:
        assert dialog._accept.isEnabled() is False
        dialog._checkbox.setChecked(True)
        assert dialog._accept.isEnabled() is True
    finally:
        dialog.close()
