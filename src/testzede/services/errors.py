"""Servis katmanı hataları."""

from __future__ import annotations


class ServiceError(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek anlaşılır (Türkçe) bir mesaj taşır."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
