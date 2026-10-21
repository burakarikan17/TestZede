# STD test kayıtları — v0.3.1 adayı

`docs/TestZede-STD.docx` Bölüm 4'e işlenen sonuçların kanıtları
(Enes Öztürk, macOS 27.0, Python 3.11.16, 21/10/2026; develop 75f0665 + PR #27).

- `run_std_gui.py`: 3.1–3.5 ve 3.7 adımlarını STD girdileriyle (K1, T1, T1a, K2, T3, H1)
  gerçek `MainWindow` üzerinde yürütür. Dosya iletişim kutuları yerine seçilen yol
  doğrudan verilir. Çalıştırma:
  `QT_QPA_PLATFORM=offscreen python docs/std/v0.3.1/run_std_gui.py <çıktı klasörü>`
- `results.json`: her durum numarası için ekrandan okunan metinler.
- `*.png`: adım adım ekran görüntüleri.
- `3.9-cli.log`: boş bir `--data-dir` ile `download` (iki kez), `make-splits` ve eksik
  veride `make-splits` çıktısı.

3.6 (RL) ve 3.8 (Toplu Test) Enes'in modülleri olduğu için çapraz test kuralı gereği
Burak Arıkan tarafından doldurulacak.
