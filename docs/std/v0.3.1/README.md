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
Burak Arıkan tarafından Windows'ta (Windows 10 Pro 10.0.19045, Python 3.11.16, develop 09493e4,
21/10/2026) doldurulmuştur:

- `run_std_gui_36_38.py`: 3.6 ve 3.8 adımlarını gerçek `MainWindow` üzerinde yürütür (K1 + `sign`,
  T1a, "Testleri Kaydet…" ve pytest, "Split: external" + birim sınırı 5 + CSV/HTML/XLSX,
  "Durdur"). Çalıştırma: depo kökünden
  `QT_QPA_PLATFORM=offscreen python docs/std/v0.3.1/run_std_gui_36_38.py <çıktı klasörü>`
  (veri setleri indirilmiş ve `make-splits` çalıştırılmış olmalı).
- `results_36_38.json`, `3.6-*.png`, `3.8-*.png`, `3.6-pytest.log`: ham sonuçlar ve kanıtlar.
- Not: birim sınırı veri seti başına uygulanır; `external` ayrımı iki veri seti içerdiği için sınır 5
  ile 10 birim çalışır (5 HumanEval + 5 small67).
