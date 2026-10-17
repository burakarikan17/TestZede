"""``configs/*.yaml`` yapılandırma dosyalarının okunması."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path("configs") / "default.yaml"
FROZEN_CONFIG = Path("configs") / "frozen.yaml"


class ConfigError(ValueError):
    """Yapılandırma dosyası okunamadı ya da biçimi bozuk."""


def default_config_path() -> Path:
    """Ayar dondurulduysa ``configs/frozen.yaml``, değilse ``configs/default.yaml``."""
    return FROZEN_CONFIG if FROZEN_CONFIG.is_file() else DEFAULT_CONFIG


def load_config(path: Path) -> Mapping:
    """YAML dosyasını sözlük olarak okur; boş dosya boş sözlüktür.

    Raises:
        ConfigError: Dosya okunamıyor, YAML bozuk ya da kök bir eşleme değil.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Yapılandırma dosyası okunamadı: {path} ({exc})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Yapılandırma dosyası bozuk: {path} ({exc})") from exc
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ConfigError(f"Yapılandırma dosyasının kökü bir eşleme olmalı: {path}")
    return data
