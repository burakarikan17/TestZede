"""Kod Yükle sayfası: kaynak kodu yapıştırma/dosyadan açma ve sözdizimi denetimi."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from testzede.gui.pages.base import BasePage
from testzede.gui.state import AppState

PAGE_TITLE = "Kod Yükle"
DEBOUNCE_MS = 400
_ERROR_COLOR = "#ff5252"
_OK_COLOR = "#69f0ae"


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


class CodePage(BasePage):
    """Kaynak kodu alır, denetler ve geçerliyse :class:`AppState`'e yazar."""

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(PAGE_TITLE, state, parent)
        self._committed = state.source  # en son yazdığımız/gördüğümüz AppState.source

        self.editor = QPlainTextEdit()
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.editor.setFont(font)
        self.editor.setPlaceholderText(
            "Python kodunu buraya yapıştırın veya 'Dosya Aç' ile yükleyin"
        )
        self.editor.setPlainText(state.source)
        self.open_button = QPushButton("Dosya Aç")
        self.validate_button = QPushButton("Doğrula")
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.validate_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.status_label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.validate)
        self.editor.textChanged.connect(self._timer.start)
        self.validate_button.clicked.connect(self.validate)
        self.open_button.clicked.connect(self.open_file)

    def validate(self) -> SourceCheck:
        """Editördeki kodu denetler, sonucu gösterir; geçerliyse ``AppState.source``'u günceller."""
        self._timer.stop()
        text = self.editor.toPlainText()
        result = check_source(text)
        message = result.message
        if result.ok:
            self.state.source = text
            self._committed = text
        elif self.state.source:
            message += " (Önceki geçerli kod korunuyor.)"
        self._show_status(message, result.ok)
        return result

    def load_file(self, path: Path) -> bool:
        """Dosyayı editöre yükleyip doğrular; okunamazsa hatayı sayfada gösterir (``False``)."""
        try:
            text = read_source_file(path)
        except ValueError as exc:
            self._show_status(str(exc), False)
            return False
        self.editor.setPlainText(text)
        self.validate()
        return True

    def open_file(self) -> None:
        """Dosya seçtirir ve yükler; iptal edilirse bir şey yapmaz."""
        name, _ = QFileDialog.getOpenFileName(self, "Python dosyası seç", "", "Python (*.py)")
        if name:
            self.load_file(Path(name))

    def on_enter(self) -> None:
        """Başka bir sayfa ``AppState.source``'u değiştirdiyse editörü onunla eşitler."""
        if self.state.source == self._committed:
            return  # dışarıdan değişiklik yok: yazılmamış taslak korunur
        self._committed = self.state.source
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.state.source)
        self.editor.blockSignals(False)
        self.validate()

    def _show_status(self, message: str, ok: bool) -> None:
        """Durum etiketini yeşil (geçerli) ya da kırmızı (hata) gösterir."""
        color = _OK_COLOR if ok else _ERROR_COLOR
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setProperty("status", "ok" if ok else "error")
