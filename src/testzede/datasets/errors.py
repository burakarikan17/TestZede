"""Veri seti işlemlerinin hataları.

Tüm hatalar ``DatasetError`` türündendir ve mesajları doğrudan kullanıcıya
gösterilebilir (Madde-1: kullanıcı kaynaklı hata arayüzde mesaj olarak çıkar).
"""

from __future__ import annotations


class DatasetError(Exception):
    """Veri seti işlemi başarısız oldu; mesaj kullanıcıya gösterilebilir."""


class DatasetNotFoundError(DatasetError):
    """Beklenen veri dosyası ya da klasörü yok."""


class DatasetFormatError(DatasetError):
    """Veri dosyası okunamadı ya da beklenen sütunlar yok."""


class DownloadError(DatasetError):
    """Veri seti indirilemedi."""


class IntegrityError(DatasetError):
    """Dosyanın SHA-256 özeti beklenenle uyuşmuyor."""


class SplitError(DatasetError):
    """Split üretilemedi ya da doğrulanamadı (örn. data leakage)."""
