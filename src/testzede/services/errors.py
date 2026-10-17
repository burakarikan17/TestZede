"""Servis katmanının hata türü."""

from __future__ import annotations


class ServiceError(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek hata mesajı."""
