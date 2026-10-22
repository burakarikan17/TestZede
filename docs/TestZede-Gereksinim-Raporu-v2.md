# TestZede — Gereksinim Raporu v2

Sürüm 2.0 · Tarih: 22-10-2026 · Yazılım sürümü: v0.3.1 (`develop` 9bfdb5f)
Proje ekibi: Burak Arıkan, Emre Alma, Enes Öztürk

# 1. GİRİŞ

## 1.1 Amaç

Bu rapor TestZede'nin gereksinimlerini tek listede toplar, her birine kimlik (GER-001 …), tür, öncelik, kaynak ve doğrulama yöntemi verir; her gereksinimi tasarım bileşenine (SDD) ve kabul testine (STD) bağlar.

## 1.2 Kaynaklar

| Kısaltma | Belge |
|---|---|
| Sözleşme | `docs/TestZede-Sozlesme.docx`, Kullanım, Teslim ve Destek Sözleşmesi, sürüm 1.0, 19/10/2026 |
| EK-A … EK-D | Sözleşme ekleri: EK-A Donanım, EK-B Yazılım, EK-C Güvenlik Yapılanması, EK-D Modül ve Fonksiyon Listesi |
| STD | `docs/TestZede-STD.docx`, sürüm 1.0; test case 3.1–3.9 ve v0.3.1 test kayıtları (4.2) |
| SDD | `docs/TestZede-SDD.md` / `.docx`, sürüm 1.0 |
| README, ARCHITECTURE | Depodaki `README.md`, `ARCHITECTURE.md` |
| Kod | `src/testzede/` (v0.3.1), `configs/`, `pyproject.toml`, `.github/workflows/ci.yml` |

## 1.3 Sürüm 1 hakkında

Depoda ve git geçmişinde "Gereksinim Raporu v1" adlı bir belge bulunamadı. Bu nedenle v2, sözleşmenin ekleri (EK-A … EK-D, 19/10/2026) temel (v1 yerine) alınarak hazırlanmıştır; §5'teki değişiklik özeti bu temele göredir. v1 başka bir yerde varsa (ör. ders sistemine yüklenmiş) §7'deki soru listesine bakınız.

# 2. SINIFLANDIRMA

**Tür.** İşlevsel (sistemin yaptığı iş), İşlevsel olmayan (kalite: dayanıklılık, kullanılabilirlik, taşınabilirlik, bütünlük), Kısıt (platform, süreç, teslim ve sözleşme koşulları).

**Öncelik.** Kaynaktan alınır, ekip tarafından yeniden puanlanmamıştır. *Zorunlu*: sözleşme ya da ekleri gerektirir, ya da STD kabul testinde sınanır. *Opsiyonel*: EK-D'de "Opsiyonel" diye geçer. STD'de bir test case'e bağlı gereksinimler için STD'deki risk seviyesi (Yüksek/Orta) ayrıca verilmiştir.

**Doğrulama yöntemi.** *Kabul testi*: STD test case'i (manuel, çapraz). *Birim testi*: `tests/unit/…` altında pytest. *White-box*: `tests/whitebox/`. *İnceleme*: belge ya da kod incelemesi. *CI*: `.github/workflows/ci.yml` (Windows ve macOS'ta `ruff` + `pytest`).

# 3. GEREKSİNİMLER

## 3.1 İşlevsel gereksinimler

| Kimlik | Gereksinim | Öncelik (risk) | Kaynak | Doğrulama |
|---|---|---|---|---|
| GER-001 | Sistem, yüklenen kodun ya da seçilen bir HumanEval görevinin fonksiyon çağrı grafiğini gösterir. | Zorunlu (Yüksek) | EK-D US-1 | Kabul testi STD 3.3; birim testi `tests/unit/analysis/test_callgraph.py` |
| GER-002 | Çağrı grafiğinde düğüm türleri (fonksiyon, yerleşik, harici, modül düzeyi) ayırt edilir, özyineleme gösterilir, seçilen düğümle ilgili düğüm ve çağrılar vurgulanır. | Zorunlu (Yüksek) | STD 3.3 kabul ölçütü; ARCHITECTURE §6 | Kabul testi STD 3.3 |
| GER-003 | Sistem kodun 14 metriğini açıklamalarıyla gösterir (en az 10 gerekli). | Zorunlu (Yüksek) | EK-D US-2; README US-2 | Kabul testi STD 3.4; birim testi `tests/unit/analysis/test_metrics.py` |
| GER-004 | Metrik tablosu CSV dosyasına aktarılabilir. | Zorunlu (Yüksek) | EK-D US-2 | Kabul testi STD 3.4 (4.4); birim testi `tests/unit/services/test_analysis_service.py` |
| GER-005 | Sürdürülebilirlik indeksi harf derecesiyle (A/B/C) gösterilir. | Zorunlu (Yüksek) | STD 3.4 kabul ölçütü; ARCHITECTURE §3 | Kabul testi STD 3.4 (4.3) |
| GER-006 | Kullanıcı kaynak kodu ve test kodunu yapıştırarak ya da dosyadan açarak yükler; yüklenen kod diğer sayfalarda kullanılabilir. | Zorunlu (Yüksek) | EK-D US-3 (Kod Yükle sayfası) | Kabul testi STD 3.1; birim testi `tests/unit/gui/test_code_page*.py` |
| GER-007 | Sistem kullanıcının kodu ve testleriyle satır ve dal (branch) coverage'ını, fonksiyon bazında da hesaplar. | Zorunlu (Yüksek) | EK-D US-3; README US-3 | Kabul testi STD 3.5; birim testi `tests/unit/execution/test_coverage_runner.py`; white-box `tests/whitebox/` |
| GER-008 | Her testin sonucu (Geçti, Başarısız, Hata, Zaman aşımı) ve kaynakta kapsanan/kapsanmayan satırlar gösterilir. | Zorunlu (Yüksek) | STD 3.5 kabul ölçütü | Kabul testi STD 3.5; birim testi `tests/unit/gui/test_coverage_page.py` |
| GER-009 | Sistem pekiştirmeli öğrenme (Q-learning) ajanının seçtiği girdi stratejileriyle unit test üretir. | Zorunlu (Yüksek) | Sözleşme 2.1, 2.2; EK-D US-4 | Kabul testi STD 3.6; birim testi `tests/unit/rl/` |
| GER-010 | Kullanıcı testleri verilirse RL bu testlerin coverage'ıyla başlar ve yalnızca kapsanmayan kısımlar için test ekler. | Zorunlu (Yüksek) | EK-D US-3 ("RL ile coverage artırımı"); ARCHITECTURE §3 | Kabul testi STD 3.6 (6.2); birim testi `tests/unit/services/test_rl_service.py` |
| GER-011 | RL Test Üretimi sayfasının alt şeridinde Test Case Statistics, Branch Count, Tested Line Count ve Coverage Rate gösterilir. | Zorunlu (Yüksek) | EK-D US-4 | Kabul testi STD 3.6 (6.2) |
| GER-012 | Üretilen testler pytest ile çalışan bir dosya olarak kaydedilebilir. | Zorunlu (Yüksek) | STD 3.6 kabul ölçütü | Kabul testi STD 3.6 (6.4); birim testi `tests/unit/services/test_rl_service.py` |
| GER-013 | Sistem mutation score hesaplar. | Zorunlu (Orta) | EK-D US-5 | Kabul testi STD 3.7; birim testi `tests/unit/mutation/` |
| GER-014 | Sistem test çalıştırma süresini (Test Execution Time) ölçer ve gösterir. | Zorunlu (Orta) | EK-D US-5 | Kabul testi STD 3.7 (kısmen, bkz. §4.2); birim testi `tests/unit/execution/test_coverage_runner.py`, `tests/unit/batch/test_report.py` |
| GER-015 | Sistem derlenebilirlik oranını (Compilation Rate) ölçer ve gösterir. | Zorunlu (Orta) | EK-D US-5 | Kabul testi STD 3.6 (6.2), 3.7 (kısmen, bkz. §4.2); birim testi `tests/unit/execution/test_coverage_runner.py` |
| GER-016 | Hayatta kalan mutantlar operatör, satır ve açıklamalarıyla listelenir; seçilen mutantın farkı gösterilir. | Zorunlu (Orta) | STD 3.7 kabul ölçütü | Kabul testi STD 3.7 (7.2, 7.3); birim testi `tests/unit/gui/test_mutation_logic.py` |
| GER-017 | Sistem dört veri setinde (HumanEval, TestGenEval, TestGenEvalLite, 67_Python_Code_Small) toplu test çalıştırır. | Zorunlu (Yüksek) | EK-D US-6; Sözleşme 2.4 | Kabul testi STD 3.8 (kısmen, bkz. §4.2); birim testi `tests/unit/batch/test_runner.py` |
| GER-018 | Toplu testin sonucu veri seti bazında CSV, HTML ve XLSX rapor olarak yazılır. | Zorunlu (Yüksek) | EK-D US-6 | Kabul testi STD 3.8 (8.2); birim testi `tests/unit/batch/test_report.py` |
| GER-019 | Toplu test sırasında ilerleme gösterilir; kullanıcı çalıştırmayı durdurabilir (mevcut birim bitince). | Zorunlu (Yüksek) | STD 3.8 kabul ölçütü; ARCHITECTURE §3 | Kabul testi STD 3.8 (8.1, 8.4); birim testi `tests/unit/batch/test_runner.py` |
| GER-020 | Bir birimde hata olursa toplu çalıştırma durmaz; hata `error` sütununa yazılır. | Zorunlu (Yüksek) | README "Çalıştırma"; STD 3.8 kabul ölçütü | Kabul testi STD 3.8 (8.1: 0 hatalı birim; hata yolu sınanmadı, bkz. §4.2); birim testi `tests/unit/batch/test_runner.py` |
| GER-021 | Veri setleri `testzede download` ile sabit bir sürümden indirilir ve SHA-256 ile doğrulanır; bozuk ya da değişmiş dosya reddedilir; doğru dosya yeniden indirilmez. | Zorunlu (Orta) | Sözleşme 4.1; EK-D Yardımcı | Kabul testi STD 3.9 (9.1, 9.2); birim testi `tests/unit/datasets/test_download.py` |
| GER-022 | Veri setleri sızıntı olmadan ayrılır: geliştirme TestGenEvalLite, ana deney TestGenEval eksi Lite (`instance_id` ile), dış test HumanEval + Small67; geliştirme kümesiyle birebir aynı kaynaklı birimler ana deneyden çıkarılır. | Zorunlu (Orta) | Sözleşme 2.6, 4.3; EK-D Yardımcı | Kabul testi STD 3.9 (9.3); birim testi `tests/unit/datasets/test_splits.py` |
| GER-023 | Her rapor kullanılan ayrım dosyasının SHA-256 özetini ve yapılandırma dosyasının adını taşır. | Zorunlu (Yüksek) | Sözleşme 4.3; README "Çalıştırma" | Kabul testi STD 3.8 (8.3); birim testi `tests/unit/batch/test_report.py`, `test_runner.py` |
| GER-024 | İşlenemeyen örnekler sessizce atılmaz, nedenleriyle birlikte raporlanır. | Zorunlu | Sözleşme 4.2 | STD karşılığı yok; birim testi `tests/unit/datasets/` (yükleyici ve `test_splits.py`) |
| GER-025 | Kod metriklerinden tahmini hata sayısı ve optimum test sayısı gösterilir. | Opsiyonel | EK-D Opsiyonel; README | STD 2.2.1: test edilmez; birim testi `tests/unit/prediction/` |

## 3.2 İşlevsel olmayan gereksinimler

| Kimlik | Gereksinim | Öncelik (risk) | Kaynak | Doğrulama |
|---|---|---|---|---|
| GER-026 | Test edilen kod ve testler ana uygulamadan ayrı bir alt süreçte, yalıtılmış Python modunda ve süre sınırıyla çalışır; sonsuz döngü ya da çöken kod yalnızca ilgili testi hatalı/zaman aşımı işaretler, uygulamayı düşürmez. | Zorunlu (Yüksek) | Sözleşme 7.4; EK-C "Kod izolasyonu", "Hata dayanıklılığı" | Kabul testi STD 3.5 (5.4), 3.2 (2.5); birim testi `tests/unit/execution/test_sandbox.py`, `test_run_outcomes.py` |
| GER-027 | Yakalanmamış her istisna kayda alınır ve kullanıcıya mesaj kutusunda gösterilir; uygulama kapanmaz. | Zorunlu (Yüksek) | EK-C "Hata dayanıklılığı" | Kabul testi STD 3.2 (2.5, dolaylı); birim testi `tests/unit/gui/test_error_handler.py` |
| GER-028 | Kod yüklenirken sözdizimi denetlenir; hata satır numarasıyla gösterilir ve önceki geçerli kod korunur; dosya okuma hataları (bulunamadı, UTF-8 değil, izin yok) anlaşılır mesajla bildirilir. | Zorunlu (Yüksek) | EK-C "Girdi doğrulama" | Kabul testi STD 3.2; birim testi `tests/unit/gui/test_code_page.py` |
| GER-029 | Uzun işlemler ayrı iş parçacığında çalışır, arayüz bloklanmaz; pencere kapanırken çalışan işler beklenir. | Zorunlu (Yüksek) | EK-C "Arka plan işleri" | Kabul testi STD 3.6 (6.5), 3.7 (7.4), 3.8 (8.1, 8.4); kapanırken bekleme: birim testi `tests/unit/gui/test_coverage_page.py::test_shutdown_waits_for_running_job` (diğer sayfalarda `shutdown()` yalnızca test sonu temizliğinde çağrılır, beklemeyi sınayan test yok) |
| GER-030 | Ayrım dosyaları ham verilerin özetini taşır; veri değişmişse toplu test başlamaz. | Zorunlu | EK-C "Veri bütünlüğü"; Sözleşme 4.3 | STD karşılığı yok (3.9 yalnızca özetlerin yazıldığını sınar); birim testi `tests/unit/datasets/test_splits.py::test_load_split_units_detects_changed_raw_data` |
| GER-031 | Kullanıcı girdisinden kaynaklanan hatalar anlaşılır bir mesajla gösterilir; komut satırında `Hata: …` yazılır, çıkış kodu 1 olur, hata izi (traceback) yazılmaz. | Zorunlu (Orta) | Sözleşme 7.4; STD 3.9 kabul ölçütü | Kabul testi STD 3.2, 3.9 (9.4); birim testi `tests/unit/datasets/test_cli.py`, `tests/unit/batch/test_cli_batch.py` |
| GER-032 | Aynı yapılandırma aynı sonucu verir: toplu çalıştırmada `i`. birim `seed + i` tohumunu kullanır. | Zorunlu | ARCHITECTURE §3 | STD karşılığı yok; birim testleri yalnızca parçaların tohumla belirlenimli olduğunu sınar: `tests/unit/rl/test_actions.py::test_generation_is_deterministic_for_same_seed` (eylem girdileri), `tests/unit/mutation/test_engine.py` (tohumlu mutant örneklemesi). `seed + i` kuralını ve toplu çalıştırmanın uçtan uca tekrarlanabilirliğini sınayan test yok: doğrulanamadı |
| GER-033 | TestZede Windows ve macOS üzerinde aynı şekilde çalışır. | Zorunlu | Sözleşme 3.2; EK-B | CI (Windows ve macOS); STD 1.2 (bkz. §4.2) |

## 3.3 Kısıtlar

| Kimlik | Kısıt | Öncelik | Kaynak | Doğrulama |
|---|---|---|---|---|
| GER-034 | Python yalnızca 3.11 sürümü desteklenir. | Zorunlu | EK-B; README | İnceleme: `pyproject.toml` `requires-python = ">=3.11,<3.12"`; CI |
| GER-035 | Önerilen donanım: 64 bit çok çekirdekli işlemci, 8 GB RAM, 5 GB boş disk, 1280 × 800 ve üzeri ekran (pencere 1200 × 780 açılır). | Zorunlu | EK-A | İnceleme: `gui/main_window.py` (`resize(1200, 780)`); mutantların paralel çalışması `mutation/engine.py` |
| GER-036 | İnternet erişimi yalnızca ilk kurulumda, veri setlerini indirmek için gerekir. | Zorunlu | EK-A | İnceleme (ağ yalnızca `datasets/download.py`'de) |
| GER-037 | Docker gerekmez. | Zorunlu | EK-B | İnceleme (kodda Docker kullanımı yok). README farklı yazıyor, bkz. §6 |
| GER-038 | Kütüphane bağımlılıkları `pyproject.toml`'da tanımlıdır (EK-B tablosu). | Zorunlu | EK-B | İnceleme. `gymnasium` listede var ama kodda kullanılmıyor, bkz. §6 |
| GER-039 | Test üretiminde büyük dil modeli (LLM) kullanılmaz. | Zorunlu | Sözleşme 2.1; README | İnceleme (`rl/` yalnızca NumPy ve standart kütüphane kullanır); kabul testi STD 3.6 beklenen çıktı |
| GER-040 | Veri setleri depoya eklenmez ve üçüncü kişilere dağıtılmaz. | Zorunlu | Sözleşme 4.4 | İnceleme: `.gitignore` (`data/raw/*`, `data/splits/*`, `reports/*`) |
| GER-041 | Ayarlar dondurulduktan (`configs/frozen.yaml`) sonra ana deney ve dış test kümelerinde değiştirilmez. | Zorunlu | Sözleşme 4.3; ARCHITECTURE §4 | İnceleme (`frozen.yaml` ve git geçmişi); STD karşılığı yok |
| GER-042 | Alt süreç bir güvenlik izolasyonu değildir (dosya sistemi ve ağı kısıtlamaz); müşteri güvenmediği kodu çalıştırmaz. | Zorunlu | Sözleşme 7.4; EK-C "Bilinen sınır" | İnceleme |
| GER-043 | Yazılım kaynak koduyla ve sürüm etiketiyle (GitHub release) teslim edilir. | Zorunlu | Sözleşme 3.1 | İnceleme: `v0.3.1` etiketi |
| GER-044 | Kurulum README'deki adımlarla yapılır; süresi 1 iş günüdür. | Zorunlu | Sözleşme 3.4 | İnceleme (README "Kurulum") |
| GER-045 | Kabul testi STD senaryolarıyla 26 Ekim 2026'da yapılır; her hata için 3, çökme için 10 puan düşülür. | Zorunlu | Sözleşme 6.2.1, 6.2.3, 6.3 | Kabul testi (STD 3.1–3.9) |
| GER-046 | Teslimden sonra en az bir oturumda tüm ekranlar gösterilir. | Zorunlu | Sözleşme 5.2 | İnceleme (süreç) |
| GER-047 | Kabulden sonra 3 ay ücretsiz destek; bildirilen hataya 2 iş günü içinde ilk müdahale. | Zorunlu | Sözleşme 7.1–7.3 | İnceleme (süreç) |

## 3.4 Proje teslim gereksinimleri

README'deki puan tablosunda yer alan, yazılım dışı teslimlerdir (tür: kısıt).

| Kimlik | Teslim | Puan | Kaynak | Durum / doğrulama |
|---|---|---|---|---|
| GER-048 | Yazılım Şartnamesi | 3 | README "Diğer teslimler" | Ekip kararı bekliyor: EK-A … EK-D bu teslimin yerine geçiyor mu? (§6, K1) |
| GER-049 | Task board | 2 | README | Trello depoda değil; doğrulanamadı |
| GER-050 | UI/UX ve tasarım kalıpları | 2 | README | SDD §5.2–5.3 (tema, erişilebilirlik), §6 (kalıplar) |
| GER-051 | STD: en az 5 test case | 3 | README | STD'de 9 test case (3.1–3.9), v0.3.1 kayıtları dolu |
| GER-052 | White-box: en az 3 test | 5 | README | `tests/whitebox/` altında 3 dosya |
| GER-053 | Kalite analizi (SonarQube ya da SourceMonitor çıktısı) | 5 | README | `docs/kalite/sonarqube-bulgular.md` ve `sonarqube-dashboard.png` |

# 4. İZLENEBİLİRLİK

## 4.1 Gereksinim → tasarım → test

SDD bölüm numaraları `docs/TestZede-SDD.md`'ye, STD numaraları `docs/TestZede-STD.docx` 3. ve 4.2. bölümlere göredir (parantez içi: durum numarası).

| Gereksinim | Tasarım bileşeni (SDD) | STD testi |
|---|---|---|
| GER-001 | `analysis.callgraph`, `AnalysisService.call_graph`, `CallGraphPage` (§3.5, §3.9, §5.1) | 3.3 (3.1–3.4) |
| GER-002 | `graph_canvas` (Okabe-Ito, vurgu), `CallGraphView` (§5.1, §5.3) | 3.3 (3.1–3.3) |
| GER-003 | `analysis.metrics.compute_metrics`, `MetricsPage` (§3.5) | 3.4 (4.1, 4.2) |
| GER-004 | `AnalysisService.export_metrics_csv` (§3.9) | 3.4 (4.4) |
| GER-005 | `metrics.maintainability_rank`, `MetricsView` (§3.5) | 3.4 (4.3) |
| GER-006 | `CodePage`, `test_loader`, `AppState` (§3.10, §5.1, Şekil 4b) | 3.1 (1.1–1.4) |
| GER-007 | `coverage_runner.run_tests`, `CoverageService` (§3.2, §3.9) | 3.5 (5.1, 5.2) |
| GER-008 | `CoveragePage`, `coverage_logic` (§5.1) | 3.5 (5.1–5.4) |
| GER-009 | `rl` paketi, `rl_service.generate`, `RLPage` (§3.4, Şekil 3c, 5) | 3.6 (6.1, 6.3) |
| GER-010 | `TestGenEnv` baseline, `rl_service` kullanıcı testleri (§3.4) | 3.6 (6.2) |
| GER-011 | `RLPage` `StatTile`'ları, `GenerationResult` (§5.1) | 3.6 (6.2) |
| GER-012 | `rl_service.tests_module`, "Testleri Kaydet…" (§3.9) | 3.6 (6.4) |
| GER-013 | `mutation.engine`, `operators`, `MutationService` (§3.3) | 3.7 (7.1) |
| GER-014 | `RunStats.execution_time_s`, `measure_suite` (§3.2, §3.8) | 3.7 (kısmen) |
| GER-015 | `RunStats.compilation_rate`, `coverage_runner` (§3.2) | 3.6 (6.2), 3.7 (kısmen) |
| GER-016 | `MutationRun.survivors`, `mutation_logic.mutant_diff`, `MutationPage` (§3.3, §5.1) | 3.7 (7.2, 7.3) |
| GER-017 | `datasets` yükleyicileri, `batch.runner`, `batch_service`, `BatchPage` (§3.7, §3.8) | 3.8 (yalnızca `external`) |
| GER-018 | `batch.report.write_report` (§3.8, §4.4) | 3.8 (8.2) |
| GER-019 | `run_batch` `progress`/`should_stop`, `TaskRunner` (§3.8, §5.5) | 3.8 (8.1, 8.4) |
| GER-020 | `run_unit` hata yakalama (§3.8, §7.1) | 3.8 (kısmen) |
| GER-021 | `datasets.download`, `sources` (§3.7) | 3.9 (9.1, 9.2) |
| GER-022 | `datasets.splits`, `verify_no_leakage` (§3.7, §4.3) | 3.9 (9.3) |
| GER-023 | `ReportMeta.split_hash`, `meta.csv` (§4.4) | 3.8 (8.3) |
| GER-024 | `LoadResult.skipped`, `SplitDefinition.stats` (§3.7) | — |
| GER-025 | `prediction`, `PredictionPage` (§3.6) | — (STD 2.2.1) |
| GER-026 | `sandbox`, `coverage_runner`, zaman aşımları (§2.3, §7.2, §7.3) | 3.5 (5.4), 3.2 (2.5) |
| GER-027 | `error_handler`, `Logger`, `Worker` (§7.1) | 3.2 (2.5, dolaylı) |
| GER-028 | `code_page.check_source`, `code_page.read_source_file`, `analysis.parsing` (§7.5) | 3.2 (2.1–2.4) |
| GER-029 | `TaskRunner`/`Worker`, `MainWindow.closeEvent` (§2.3, §3.10, §7.2) | 3.6 (6.5), 3.7 (7.4), 3.8 (8.1, 8.4) |
| GER-030 | `load_split_units` özet denetimi (§4.3, §7.6) | — |
| GER-031 | `ServiceError`, `cli.py` (§2.4, §7.1) | 3.2, 3.9 (9.4) |
| GER-032 | `run_batch` tohumları, `MutationEngine._sample` (§3.8) | — |
| GER-033 | Platformdan bağımsız alt süreç (`signal.alarm` yok), CI matrisi (§2.3) | 1.2 (test yaklaşımı) |
| GER-034 – GER-047 | Kısıtlar; tasarıma yansıyanlar: GER-035 (§3.10), GER-039 (§3.4), GER-040 (§4.3), GER-042 (§7.4) | GER-045: STD 3.1–3.9; diğerleri inceleme |
| GER-048 – GER-053 | Teslimler (§3.4) | GER-051: STD'nin kendisi |

## 4.2 STD'de karşılığı olmayan ya da kısmen olan gereksinimler

| Gereksinim | Durum | Not |
|---|---|---|
| GER-014 Test Execution Time | Kısmen | STD 3.7'nin amacı süreyi de sayar, ama geçme ölçütü yalnızca skoru doğrular. |
| GER-015 Compilation Rate | Kısmen | STD 3.6 (6.2) "üretilen 21, derlenen 21" değerini kaydeder; ayrı bir ölçüt yoktur. STD 3.7 ölçütü yalnızca skor. |
| GER-017 Dört veri setinde toplu test | Kısmen | STD 3.8 yalnızca `external` (HumanEval + Small67) ile, birim sınırı 5 ile koşulmuş; TestGenEval ve TestGenEvalLite toplu testte sınanmamış. |
| GER-020 Birim hatası çalıştırmayı durdurmaz | Kısmen | STD 3.8 kaydında hatalı birim yok (0 hatalı); hata yolu kabul testinde görülmemiş, birim testinde sınanıyor. |
| GER-024 İşlenemeyen örneklerin raporlanması | Yok | Yalnızca birim testleri. |
| GER-025 Tahmin | Yok | STD 2.2.1 kapsam dışı (opsiyonel). |
| GER-030 Veri değişince toplu test başlamaz | Yok | Yalnızca birim testi. |
| GER-032 Tekrarlanabilirlik | Yok | Birim testleri var; uçtan uca tekrar testi doğrulanamadı. |
| GER-033 Windows ve macOS | Kısmen | STD 1.2 "iki platformda" der; 4.1'deki test ortamı ve "Test eden" satırına göre her test case tek platformda koşulmuş (3.1–3.5, 3.7, 3.9 macOS; 3.6, 3.8 Windows). CI iki platformda birim testlerini koşar. |
| GER-041 Ayarların dondurulması | Yok | İnceleme ile. |

## 4.3 Gereksinimi olmayan testler

Her STD test case'i (3.1–3.9) en az bir sözleşme/EK gereksinimine bağlıdır; gereksinimsiz test case yoktur. Ancak aşağıdaki kabul ölçütlerinin sözleşmede ya da EK-D'de doğrudan karşılığı yoktur; kaynakları STD'nin kendisidir (gereksinim olarak bu raporda GER-002, 005, 008, 012, 016, 019 diye kayda alınmıştır):

- STD 3.3: düğüm türlerinin ayrımı, özyinelemenin gösterimi, seçimle vurgulama (GER-002).
- STD 3.4: sürdürülebilirlik harf derecesi (GER-005).
- STD 3.5: test sonucu etiketleri ve renkli satırlar (GER-008).
- STD 3.6: "Testleri Kaydet…" (GER-012).
- STD 3.7: hayatta kalan mutant listesi ve fark görünümü (GER-016).
- STD 3.8: "Durdur" düğmesi ve ilerleme (GER-019).

# 5. DEĞİŞİKLİK ÖZETİ

Temel: sözleşme ekleri EK-A … EK-D (19/10/2026); depoda v1 bulunamadığı için (bkz. §1.3).

**Eklenenler.**

- Kimlik, tür, öncelik, kaynak ve doğrulama yöntemi her gereksinim için ilk kez verildi (GER-001 … GER-053).
- EK-D'de olmayan ama STD kabul ölçütlerinde yer alan gereksinimler kayda alındı: GER-002, 005, 008, 012, 016, 019.
- Sözleşme gövdesinden gereksinim olarak çıkarılanlar: GER-024 (Sözleşme 4.2), GER-030/041 (4.3), GER-039 (2.1), GER-040 (4.4), GER-042 (7.4), GER-043–047 (3.1, 3.4, 5.2, 6.2–6.3, 7.1–7.3).
- README ve ARCHITECTURE'dan: GER-020 (birim hatası çalıştırmayı durdurmaz), GER-023 (raporda yapılandırma adı), GER-032 (tekrarlanabilirlik).
- Proje teslim gereksinimleri (GER-048 – GER-053).
- İzlenebilirlik tablosu (§4) ve STD kapsama boşlukları (§4.2).

**Netleştirilenler (koda göre).**

- US-3 "RL ile coverage artırımı": kullanıcı testlerinin coverage'ıyla başlama, yalnızca eksik kısma test ekleme (GER-010).
- US-5 ölçüleri tanımlandı: mutation score = `(öldürülen + zaman aşımı) / toplam`; Compilation Rate = derlenen / üretilen (derlenen: sözdizimi hatasız ve pytest sonucu `error` olmayan test); Test Execution Time = seçilen test paketinin tek bir tam çalıştırmasının süresi (toplu çalıştırmada).
- US-6 birim sınırı: `--limit` / "Birim sınırı" **veri seti başına** uygulanır (STD 3.8 kaydındaki notla aynı).
- Zaman aşımları ve limitler (oracle 2 sn, test çalıştırma 10 sn, paket 60 sn, mutasyon toplam 120 sn, en fazla 100 mutant) SDD §7.2'de sayısal olarak verildi.
- EK-C "Kod izolasyonu": yalıtılmış mod `python -I`; shell kullanılmaz.

**Kaldırılanlar.** Yok. Kodla çelişen ifadeler kaldırılmadı, §6'da karar için listelendi.

# 6. EKİP KARARI BEKLEYEN KONULAR

Bu bölümdeki konularda karar verilmemiştir; yalnızca dayanaklar yazılmıştır.

**K1 — EK-A … EK-D, "Yazılım Şartnamesi" (3 puan) teslimi yerine geçiyor mu?** Yerine geçiyorsa Trello'daki "Yazılım Şartnamesi" kartı kapatılabilir. Dayanaklar:

- Sözleşme 2.1: "Sistemi oluşturan modül ve fonksiyonların listesi ve kapsamları EK-D dokümanında yer almaktadır."
- Sözleşme 3.2: "TestZede'nin çalışması için gerekli donanım, işletim sistemi ve ek yazılımlar EK-A ve EK-B'de belirlenmiştir."
- Sözleşme 7.4: "Güvenlik yapılanması EK-C'de tanımlanmıştır."
- README: "Diğer teslimler: Yazılım Şartnamesi (3), …"; görev dağılımında "Şartname" Burak Arıkan'a atanmış.
- Bu rapor (GER-001 … GER-053) ekleri tek listede, kimlik ve doğrulama yöntemiyle topladığı için şartnamenin gereksinim bölümünü de karşılayabilir; ancak dersin "Yazılım Şartnamesi" için istediği biçim depoda yok, doğrulanamadı.

**K2 — Kodla çelişen belge ifadeleri hangi belgede düzeltilecek?** SDD §9'daki T1–T10. Bu raporu doğrudan etkileyenler:

- GER-037: EK-B "Docker: Gerekmez", README Kurulum "TestGenEval koşuları için Docker (opsiyonel)". Kodda Docker yok.
- GER-038: EK-B ve `pyproject.toml` `gymnasium`'u listeler; kod kullanmaz (`rl/env.py` gymnasium'a bağımlı değil).
- EK-B "PySide6, qt-material: … Material Design teması": varsayılan tema artık özel açık/koyu temadır; qt-material geri dönüş seçeneğidir.

**K3 — STD 1.2 "iki platformda" ifadesi.** Kabul testi öncesi kalan case'ler ikinci platformda da koşulacak mı, yoksa STD 1.2 mi düzeltilecek (GER-033)?

**K4 — STD kapsama boşlukları (§4.2).** GER-017 (TestGenEval ve Lite ile toplu test) ve GER-020 (hatalı birim yolu) için kabul testi öncesi ek durum yazılsın mı?

# 7. SORU LİSTESİ VE DOĞRULANAMAYANLAR

1. Gereksinim Raporu v1 nerede? Depoda ve git geçmişinde yok. Varsa bu raporun §5'i ona göre güncellenmeli.
2. Trello kartlarının içeriği depoda yok: GER-049 (Task board) doğrulanamadı.
3. Dersin "Yazılım Şartnamesi" için istediği şablon depoda yok (`.gitignore`'daki `sozlesme/` klasörü yerel tutuluyor, bu makinede yok); K1 bu yüzden ekip kararı.
4. GER-032: `seed + i` kuralını ya da toplu çalıştırmanın aynı yapılandırmayla aynı sonucu verdiğini uçtan uca sınayan bir test bulunamadı.
5. Öncelikler kaynaktan alındı (Zorunlu/Opsiyonel + STD riski); ekip ayrıca puanlamak isterse bu sütun güncellenmeli.
