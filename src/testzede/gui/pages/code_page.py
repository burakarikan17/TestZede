"""Kod Yükle sayfası: kaynak ve test kodunu yapıştırma/dosyadan açma, sözdizimi denetimi."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState
from testzede.gui.styles import apply_monospace, set_status_style, status_colors
from testzede.services.test_loader import load_tests

PAGE_TITLE = "Kod Yükle"
DEBOUNCE_MS = 400


@dataclass(frozen=True)
class SourceCheck:
    """Sözdizimi denetiminin sonucu."""

    ok: bool
    message: str
    line: int | None = None  # sözdizimi hatasının satırı
    functions: list[str] = field(default_factory=list)  # geçerli kodda üst düzey fonksiyonlar


def read_source_file(path: Path) -> str:
    """UTF-8 dosyayı okur; okunamazsa anlaşılır Türkçe mesajlı ``ValueError`` fırlatır.

    Windows Not Defteri'nin eklediği UTF-8 BOM işareti atlanır.
    """
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValueError(f"Dosya bulunamadı: {path}") from exc
    except IsADirectoryError as exc:
        raise ValueError(f"Bu bir klasör, dosya değil: {path}") from exc
    except PermissionError as exc:
        raise ValueError(f"Dosyayı okuma izniniz yok: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Dosya UTF-8 olarak okunamadı (bayt {exc.start}). "
            "Lütfen dosyayı UTF-8 olarak kaydedip tekrar deneyin."
        ) from exc
    except OSError as exc:
        raise ValueError(f"Dosya okunamadı: {exc}") from exc


def check_source(text: str) -> SourceCheck:
    """Kodu ``ast.parse`` ile denetler; boş kod geçersiz sayılır."""
    if not text.strip():
        return SourceCheck(False, "Kod boş. Lütfen kod yapıştırın veya bir dosya açın.")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        where = f"Satır {exc.lineno}: " if exc.lineno else ""
        return SourceCheck(False, f"{where}{exc.msg}", line=exc.lineno)
    except ValueError as exc:  # örn. null bayt
        return SourceCheck(False, f"Kod geçerli değil: {exc}")
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    if names:
        return SourceCheck(
            True, f"Kod geçerli. Üst düzey fonksiyonlar: {', '.join(names)}", None, names
        )
    return SourceCheck(True, "Kod geçerli. Üst düzey fonksiyon bulunamadı.")


def _make_editor(placeholder: str) -> QPlainTextEdit:
    """Monospace kod editörü oluşturur."""
    editor = QPlainTextEdit()
    apply_monospace(editor)
    editor.setPlaceholderText(placeholder)
    return editor


def _make_tab(
    open_button: QPushButton,
    validate_button: QPushButton,
    editor: QPlainTextEdit,
    status: QLabel,
) -> QWidget:
    """Düğmeler, editör ve durum etiketinden oluşan bir sekme içeriği kurar."""
    status.setWordWrap(True)
    tab = QWidget()
    buttons = QHBoxLayout()
    buttons.addWidget(open_button)
    buttons.addWidget(validate_button)
    buttons.addStretch(1)
    layout = QVBoxLayout(tab)
    layout.addLayout(buttons)
    layout.addWidget(editor, 1)
    layout.addWidget(status)
    return tab


def _debounce(parent: QWidget, callback: Callable[[], object]) -> QTimer:
    """Tek atımlık, ``DEBOUNCE_MS`` gecikmeli zamanlayıcı döndürür."""
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(DEBOUNCE_MS)
    timer.timeout.connect(callback)
    return timer


class CodePage(BasePage):
    """Kaynak ve test kodunu alır, denetler ve geçerliyse :class:`AppState`'e yazar."""

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(PAGE_TITLE, state, parent)
        self.colors = status_colors(self)
        self._committed = state.source  # en son yazdığımız/gördüğümüz AppState.source
        self._committed_tests = state.tests  # en son yazdığımız/gördüğümüz AppState.tests
        self._pending_module: str | None = None  # son açılan kaynak dosyanın adı

        # Kaynak kod sekmesi
        self.editor = _make_editor("Python kodunu buraya yapıştırın veya 'Dosya Aç' ile yükleyin")
        self.editor.setPlainText(state.source)
        self.open_button = QPushButton("Dosya Aç")
        self.validate_button = QPushButton("Doğrula")
        self.status_label = QLabel("")
        source_tab = _make_tab(
            self.open_button, self.validate_button, self.editor, self.status_label
        )

        # Test kodu sekmesi
        self.tests_editor = _make_editor(
            "pytest testlerini buraya yapıştırın veya 'Dosya Aç' ile yükleyin"
        )
        self.tests_open_button = QPushButton("Dosya Aç")
        self.tests_validate_button = QPushButton("Doğrula")
        self.tests_status_label = QLabel("")
        tests_tab = _make_tab(
            self.tests_open_button,
            self.tests_validate_button,
            self.tests_editor,
            self.tests_status_label,
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(source_tab, "Kaynak Kod")
        self.tabs.addTab(tests_tab, "Test Kodu")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        self._timer = _debounce(self, self.validate)
        self._tests_timer = _debounce(self, self.validate_tests)
        self.editor.textChanged.connect(self._timer.start)
        self.tests_editor.textChanged.connect(self._tests_timer.start)
        self.validate_button.clicked.connect(self.validate)
        self.open_button.clicked.connect(self.open_file)
        self.tests_validate_button.clicked.connect(self.validate_tests)
        self.tests_open_button.clicked.connect(self.open_tests_file)

    # --- kaynak kod ----------------------------------------------------------------------------

    def validate(self) -> SourceCheck:
        """Editördeki kodu denetler, sonucu gösterir; geçerliyse ``AppState.source``'u günceller.

        Kaynak değişince test sekmesi de yeniden doğrulanır (modül adı değişmiş olabilir).
        """
        self._timer.stop()
        text = self.editor.toPlainText()
        result = check_source(text)
        message = result.message
        if result.ok:
            self.state.source = text
            self._committed = text
            if self._pending_module is not None:
                self.state.module_name = self._pending_module
                self._pending_module = None
        elif self.state.source:
            message += " (Önceki geçerli kod korunuyor.)"
        self._set_status(self.status_label, message, result.ok)
        if result.ok and self.tests_editor.toPlainText().strip():
            self.validate_tests()
        return result

    def load_file(self, path: Path) -> bool:
        """Dosyayı editöre yükleyip doğrular; okunamazsa hatayı sayfada gösterir (``False``).

        Dosya adının uzantısız hali, kod geçerliyse ``AppState.module_name`` olur.
        """
        try:
            text = read_source_file(path)
        except ValueError as exc:
            self._set_status(self.status_label, str(exc), False)
            return False
        self._pending_module = Path(path).stem
        self.editor.setPlainText(text)
        self.validate()
        self._pending_module = None  # geçersiz kodda modül adı da uygulanmaz
        return True

    def open_file(self) -> None:
        """Kaynak dosyasını seçtirir ve yükler; iptal edilirse bir şey yapmaz."""
        name, _ = QFileDialog.getOpenFileName(self, "Python dosyası seç", "", "Python (*.py)")
        if name:
            self.load_file(Path(name))

    # --- test kodu -----------------------------------------------------------------------------

    def validate_tests(self) -> bool:
        """Test kodunu ``load_tests`` ile ayrıştırır; geçerliyse ``AppState.tests``'i günceller."""
        self._tests_timer.stop()
        try:
            cases = load_tests(self.tests_editor.toPlainText(), self.state.module_name)
        except ValueError as exc:
            message = str(exc)
            if self.state.tests:
                message += " (Önceki geçerli testler korunuyor.)"
            self._set_status(self.tests_status_label, message, False)
            return False
        self.state.tests = cases
        self._committed_tests = cases
        names = ", ".join(case.name for case in cases)
        self._set_status(self.tests_status_label, f"{len(cases)} test bulundu: {names}", True)
        return True

    def load_tests_file(self, path: Path) -> bool:
        """Test dosyasını editöre yükleyip doğrular; okunamazsa hatayı gösterir (``False``)."""
        try:
            text = read_source_file(path)
        except ValueError as exc:
            self._set_status(self.tests_status_label, str(exc), False)
            return False
        self.tests_editor.setPlainText(text)
        self.validate_tests()
        return True

    def open_tests_file(self) -> None:
        """Test dosyasını seçtirir ve yükler; iptal edilirse bir şey yapmaz."""
        name, _ = QFileDialog.getOpenFileName(self, "Test dosyası seç", "", "Python (*.py)")
        if name:
            self.load_tests_file(Path(name))

    def _set_status(self, label: QLabel, message: str, ok: bool) -> None:
        """Durum etiketini geçerli (ok) ya da hata rengiyle gösterir."""
        kind = "ok" if ok else "error"
        label.setText(message)
        set_status_style(label, self.colors[kind])
        label.setProperty("status", kind)

    # --- sayfa yaşam döngüsü -------------------------------------------------------------------

    def on_enter(self) -> None:
        """Başka sayfa ``AppState``'i değiştirdiyse (ya da sıfırladıysa) editörleri eşitler."""
        if self.state.tests is not self._committed_tests:
            self._committed_tests = self.state.tests
            if not self.state.tests:  # sıfırlama: test taslağı ve mesajı da temizlenir
                self.tests_editor.blockSignals(True)
                self.tests_editor.clear()
                self.tests_editor.blockSignals(False)
                self.tests_status_label.clear()
                set_status_style(self.tests_status_label, None)
                self.tests_status_label.setProperty("status", None)
        if self.state.source == self._committed:
            return  # dışarıdan değişiklik yok: yazılmamış taslak korunur
        self._committed = self.state.source
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.state.source)
        self.editor.blockSignals(False)
        self.validate()
