import os

# CI'da ekran yok; Qt'yi ekransız çalıştır (QApplication oluşmadan önce ayarlanmalı).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
