"""Uygulama genelinde tek log yapılandırması (Singleton)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Self

_LOGGER_NAME = "testzede"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3


def default_log_path() -> Path:
    """Kullanıcı dizinindeki varsayılan log dosyası yolunu döndürür."""
    return Path.home() / ".testzede" / "logs" / "testzede.log"


class Logger:
    """Dönen dosyaya UTF-8 yazan tekil logger sarmalayıcısı."""

    _instance: Self | None = None
    _logger: logging.Logger | None
    _path: Path | None

    def __new__(cls) -> Self:
        """Her çağrıda aynı örneği döndürür."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._logger = None
            instance._path = None
            cls._instance = instance
        return cls._instance

    def configure(self, path: Path | None = None) -> logging.Logger:
        """Dosya handler'ını kurar (idempotent); dosya açılamazsa yalnızca konsola düşer."""
        if self._logger is not None:
            return self._logger
        log = logging.getLogger(_LOGGER_NAME)
        log.setLevel(logging.INFO)
        target = path or default_log_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = RotatingFileHandler(
                target, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
            )
            self._path = target
        except OSError:
            handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        log.addHandler(handler)
        self._logger = log
        return log

    @property
    def logger(self) -> logging.Logger:
        """Yapılandırılmış logger'ı döndürür; gerekirse varsayılanlarla kurar."""
        return self._logger or self.configure()

    @property
    def path(self) -> Path | None:
        """Log dosyasının yolu (dosya kullanılamıyorsa ``None``)."""
        return self._path

    def reset(self) -> None:
        """Handler'ları kapatıp durumu sıfırlar (testler için)."""
        if self._logger is not None:
            for handler in list(self._logger.handlers):
                handler.close()
                self._logger.removeHandler(handler)
        self._logger = None
        self._path = None
