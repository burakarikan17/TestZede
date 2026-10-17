"""GUI testleri ekransız (offscreen) Qt platformunda çalışır."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
