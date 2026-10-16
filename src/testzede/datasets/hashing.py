"""Dosya özeti (SHA-256) yardımcıları."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Dosyanın SHA-256 özetini (hex) parça parça okuyarak hesaplar."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Metnin SHA-256 özetini (hex) hesaplar."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
