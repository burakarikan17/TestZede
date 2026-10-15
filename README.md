# TestZede — Reinforcement Learning ile Otomatik Test Case Hazırlama

Python kodu için çağrı grafiği, kod metrikleri, coverage ve mutasyon analizi yapan;
**pekiştirmeli öğrenme (RL)** ile otomatik unit test üreten masaüstü uygulaması.

> Test üretiminde LLM kullanılmaz. Tüm test girdileri RL ajanının seçtiği
> stratejilerle üretilir (proje kuralı).

## Özellikler

| # | Özellik | Modül | Puan |
|---|---------|-------|------|
| US-1 | HumanEval kodunun çağrı grafiği olarak gösterimi | `analysis/callgraph.py` | 10 |
| US-2 | 14 kod metriği (en az 10 gerekli; LOC, LLOC, SLOC, Halstead ailesi, McCabe, MI …) | `analysis/metrics.py` | 10 |
| US-3 | Proje kodu + test kodu ile RL tabanlı cover rate hesabı (satır/branch, fonksiyon bazlı) | `execution/`, `rl/` | 10 |
| US-4 | Cover Rate ve test sayısının gösterimi (RL ile test üretimi, istatistik ekranı) | `rl/` | 10 |
| US-5 | Mutation Score, Test Execution Time, Compilation Rate | `mutation/`, `execution/` | 10 |
| US-6 | 4 veri setinde toplu test ve veri seti bazlı rapor (CSV/HTML/XLSX) | `datasets/`, `batch/` | 10 |
| Opsiyonel | Kod metriklerinden tahmini hata sayısı ve optimum test sayısı (puansız; en sona bırakılır) | `prediction/` | – |

Diğer teslimler: Yazılım Şartnamesi (3), Task board (2), UI/UX ve tasarım kalıpları (2),
STD en az 5 test case (3), White-box en az 3 test (5), Kalite analizi — SonarQube
veya SourceMonitor çıktısı (5). **Toplam: 80 puan.**
Kabul testinde bulunan her hata −3, çökme −10 puandır. 4 ek uygulama (Test Bird,
Snake Game, Amiral Battı, Labirent ve Fare) ayrı repolardadır.

## Teknoloji

Python 3.11 · PySide6 + qt-material (arayüz) · networkx + matplotlib (graf) ·
radon (metrikler) · coverage.py + pytest (çalıştırma) · gymnasium + NumPy (RL) ·
pandas + Jinja2 (rapor) · scikit-learn (tahmin)

## Kurulum

Gereksinim: Python **3.11**, Git. TestGenEval koşuları için Docker (opsiyonel).

```bash
git clone <repo-url> testzede
cd testzede
python -m venv .venv
```

Ortamı etkinleştir:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS
source .venv/bin/activate
```

```bash
pip install -e ".[dev]"
pre-commit install
```

## Veri setleri

Veri setleri repoya **commit edilmez**, `data/raw/` altına indirilir:

```bash
testzede download --dataset humaneval
testzede download --dataset testgeneval-lite
testzede download --dataset testgeneval      # büyük, Docker gerektirir
# 67_Python_Code_Small_DataSet: ders sorumlusundan alınıp data/raw/small67/ altına koyulur
testzede make-splits                          # data leakage'sız ayrımı üretir
```

## Çalıştırma

```bash
testzede gui                                          # masaüstü arayüz
testzede batch --dataset humaneval --split external   # toplu test
testzede batch --all --report html                    # tüm setler, HTML rapor
```

Raporlar `reports/<tarih>/<veri_seti>/` altına yazılır.

## Proje yapısı

```
src/testzede/
  domain/       ortak veri modelleri (tüm modüllerin sözleşmesi)
  analysis/     çağrı grafiği, metrikler
  execution/    sandbox, coverage, süre ölçümü
  rl/           ortam, ajan, ödül, test sentezleyici
  mutation/     mutasyon operatörleri ve motoru
  prediction/   hata / optimum test sayısı tahmini
  datasets/     veri seti yükleyicileri ve split'ler
  batch/        toplu çalıştırıcı ve raporlayıcı
  services/     uygulama katmanı (GUI ile çekirdek arasındaki cephe)
  gui/          PySide6 arayüzü
tests/          unit ve entegrasyon testleri
docs/           şartname, STD, kalite raporları, diyagramlar
```

Ayrıntılı mimari için: [ARCHITECTURE.md](ARCHITECTURE.md) · Katkı kuralları: [CONTRIBUTING.md](CONTRIBUTING.md)

## Ekip ve görev dağılımı

Ödevler (side-projects) tamamlandı; kalan iş yalnızca TestZede'dir.

| Üye | Ortam | Modüller | GUI sayfaları | Diğer |
|-----|-------|----------|---------------|-------|
| Burak Arıkan | Windows | `analysis/` (US-1, US-2), `prediction/` (US-7), `datasets/` (yükleyiciler, `make-splits`, data leakage kuralları) | Çağrı Grafiği, Metrikler, Tahmin | Şartname, STD, Kalite analizi |
| Emre Alma | Windows | `execution/` (sandbox, coverage, süre; US-3), `mutation/` (US-5), `services/` | Kod Yükle, Coverage, Mutasyon + GUI iskeleti/tema | White-box testler (`tests/whitebox/`) |
| Enes Öztürk | macOS | `rl/` (US-3 artırım, US-4), `batch/` (US-6 toplu çalıştırıcı, CSV/HTML/XLSX rapor) | RL Test Üretimi, Toplu Test | CI, task board, release/etiketleme |

Ortak: `domain/models.py` (3 onay), STD senaryolarının çapraz manuel testi,
kabul testi hazırlığı.

Bağımlılıklar (sıra): `domain` → `execution` → `rl` / `mutation` → `prediction` / `batch`.
Emre `execution` sandbox'ını ilk sprintte teslim eder; Enes ve Burak ona göre ilerler.
