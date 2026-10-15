# Mimari

## 1. Genel bakış

Uygulama **N katmanlı** mimaridedir. Her katman yalnızca bir alttakine bağımlıdır;
GUI hiçbir çekirdek modülü doğrudan çağırmaz, `services` cephesini kullanır.

```mermaid
flowchart TD
    GUI[gui — PySide6 sayfaları] --> SVC[services — Facade]
    CLI[cli — testzede komutları] --> SVC
    SVC --> AN[analysis]
    SVC --> RL[rl]
    SVC --> EX[execution]
    SVC --> MU[mutation]
    SVC --> PR[prediction]
    SVC --> BA[batch]
    RL --> EX
    MU --> EX
    BA --> DS[datasets]
    AN & RL & EX & MU & PR & BA --> DOM[domain — ortak modeller]
```

## 2. Domain sözleşmesi

Ekip paralel çalışabilsin diye modüller arası veri **yalnızca** bu modellerle
taşınır (`src/testzede/domain/models.py`). Bu dosyadaki bir alan değişikliği
herkesi etkiler, PR'da üç kişinin de onayı gerekir.

```python
@dataclass(frozen=True)
class CodeUnit:
    uid: str  # "HumanEval/12", "small67/5", "<repo>::<modül>.<fonk>"
    source: str
    entry_point: str | None  # test edilecek fonksiyon adı
    dataset: str | None
    seed_examples: tuple[str, ...] = ()  # docstring'deki >>> örnekleri


@dataclass
class TestCase:
    name: str
    code: str  # tek bir pytest fonksiyonu
    origin: Literal["user", "rl"]


@dataclass
class CoverageReport:
    covered_lines: int
    total_lines: int
    covered_branches: int
    total_branches: int
    per_function: dict[str, float]  # Emma benzeri ağaç görünümü için

    @property
    def line_rate(self) -> float: ...


@dataclass
class MetricSet:
    values: dict[str, float]  # anahtarlar metrics.METRIC_NAMES


@dataclass
class MutationReport:
    total: int
    killed: int
    survived: int
    timeout: int

    @property
    def score(self) -> float: ...  # (killed + timeout) / total


@dataclass
class RunStats:
    generated: int
    compiled: int
    execution_time_s: float

    @property
    def compilation_rate(self) -> float: ...  # compiled / generated


@dataclass
class Prediction:
    estimated_bugs: float
    optimum_test_count: int
    method: str
```

## 3. Modüller

### analysis (US-1, US-2)
- `callgraph.py`: `ast` ile fonksiyon tanımlarını ve çağrıları çıkarır, `networkx.DiGraph`
  döndürür. Builtin çağrılar `<builtin>.len` biçiminde etiketlenir. Çizim GUI'de
  matplotlib canvas ile yapılır.
- `metrics.py`: radon `raw`, `metrics.h_visit`, `complexity.cc_visit`, `metrics.mi_visit`
  ile 14 metrik üretir: LOC, LLOC, SLOC, Yorum, Çoklu satır, Boş, Halstead
  Zorluk/Çaba/Uzunluk/Zaman/Kelime Haznesi/Hacim, Çevrimsel Karmaşıklık,
  Sürdürülebilirlik İndeksi.

### execution (US-3, US-5'in süre ve derlenebilirlik kısmı)
- `sandbox.py`: Her çalıştırma ayrı bir **alt süreçte** (`subprocess.run`, `timeout=`)
  geçici bir dizinde yapılır. `signal.alarm` kullanılmaz (Windows'ta yoktur).
  Sonsuz döngü ya da çöken test, yalnızca o testi `timeout`/`error` olarak işaretler.
  Uygulamayı asla düşürmez (Madde-1).
- `coverage_runner.py`: `coverage run --branch -m pytest` çalıştırır, JSON çıktısını
  `CoverageReport`'a çevirir.
- Compilation Rate: üretilen test dosyasının `ast.parse` + `py_compile` + pytest
  toplama (collection) aşamasını hatasız geçme oranıdır.

### rl (US-3, US-4)

Her **epizot** bir `CodeUnit` (test edilen fonksiyon) üzerinde geçer.

| Bileşen | Tasarım |
|---|---|
| Durum | (satır coverage dilimi, branch coverage dilimi, son eylem başarılı mı, adım dilimi): tabular Q-learning için ayrıklaştırılmış |
| Eylemler | Girdi üretim stratejileri: `BOUNDARY` (0, ±1, uç değerler), `EMPTY` ('' / [] / {}), `NEGATIVE`, `RANDOM_SMALL`, `RANDOM_LARGE`, `SPECIAL_CHARS`, `FROM_DOCSTRING` (>>> örnekleri), `MUTATE_BEST` (en iyi girdiyi bozma) |
| Ödül | `r = α·Δline + β·Δbranch + γ·yeni_çıktı_sınıfı − δ·(geçersiz/timeout) − ε` (ε: test başı maliyet; gereksiz test üretimini cezalandırır, optimum test sayısına yaklaştırır) |
| Bitiş | %100 branch coverage, maksimum adım ya da N adım boyunca coverage artışı olmaması |
| Oracle | Girdi, referans (canonical) çözümde çalıştırılır; çıktı `assert` olarak yazılır (regresyon oracle'ı). İstisna fırlatan girdiler `pytest.raises` testine dönüşür. |
| Ajan | Temel: tabular Q-learning (ε-greedy). Opsiyonel karşılaştırma: gymnasium uyumlu ortam üzerinde stable-baselines3 PPO. |

Çıktı: `TestCase` listesi + epizot boyunca coverage eğrisi. Coverage eğrisi
US-7'de optimum test sayısının hedef değeri olarak kullanılır.

### mutation (US-5)
Kendi AST tabanlı motorumuz kullanılır (Windows ve macOS'ta aynı davranış için).
Operatörler (**Strategy** kalıbı): AOR (`+`↔`-`, `*`↔`/`), ROR (`<`↔`<=`, `==`↔`!=`),
COR (`and`↔`or`), sabit değiştirme (`0`↔`1`), `return` değerini `None` yapma.
Her mutant sandbox'ta test paketine karşı koşturulur.

### prediction (US-7)
- **Temel tahmin:** Halstead teslim edilen hata sayısı `B = V / 3000`; McCabe
  karmaşıklığı ise minimum bağımsız yol (basis path) test sayısı olarak alınır.
- **Öğrenilmiş tahmin:** Geliştirme setinde RL'nin coverage eğrisinin doygunluğa
  ulaştığı test sayısı (diz noktası) hedef değişkendir; hayatta kalan mutant sayısı
  ise hata vekili olarak kullanılır. Kod metriklerinden scikit-learn regresyonu eğitilir.

### datasets + batch (US-6)
- **Factory** kalıbı: `DatasetFactory.get("humaneval")` → `DatasetLoader` →
  `Iterable[CodeUnit]`.
- `batch/runner.py`: her `CodeUnit` için metrik → RL → coverage → mutasyon → tahmin
  hattını çalıştırır. Sonuçları veri seti bazında `reports/` altına CSV/HTML/XLSX
  olarak yazar.

## 4. Data leakage'sız veri ayrımı

| Rol | Veri seti | Kullanım |
|---|---|---|
| Geliştirme | TestGenEvalLite | Ödül ağırlıkları ve hiperparametre ayarı |
| Ana deney | TestGenEval **eksi** TestGenEvalLite örnekleri | Coverage, mutation score, süre |
| Bağımsız dış test | HumanEval + 67_Python_Code_Small | Genellenebilirlik |

Kurallar:
1. Lite, TestGenEval'in alt kümesidir. Ana deney setinden Lite örnekleri
   `make-splits` ile çıkarılır; örnek kimlikleri `data/splits/*.json` dosyasına yazılır.
2. Ayar dondurulduktan (`configs/frozen.yaml`) sonra ana ve dış test setlerinde
   parametre **değiştirilmez**.
3. Her rapor, kullanılan split dosyasının hash değerini içerir.

## 5. Tasarım kalıpları

| Kalıp | Nerede |
|---|---|
| N katmanlı mimari | gui → services → çekirdek → domain |
| Singleton | `config.Settings`, `logging_setup.Logger` |
| Facade | `services/*_service.py` |
| Strategy | RL eylemleri, mutasyon operatörleri |
| Factory | `DatasetFactory` |
| Observer | Uzun işlemler Qt sinyalleriyle ilerleme bildirir (`QThread` worker) |

## 6. Arayüz

PySide6 + qt-material (Material Design teması). Sayfalar ve sahipleri:

| Sayfa | İçerik | Sahibi |
|---|---|---|
| Kod Yükle | Kaynak kod ve test kodu seçimi | Emre |
| Çağrı Grafiği | US-1 grafiği | Burak |
| Metrikler | US-2 tablosu | Burak |
| Coverage | Emma benzeri ağaç görünümü (eleman / coverage / kapsanan / kaçan / toplam) | Emre |
| RL Test Üretimi | Üretilen testler + alt şerit: Test Case Statistics, Branch Count, Tested Line Count, Coverage Rate | Enes |
| Mutasyon | Mutation score, süre, derlenebilirlik oranı | Emre |
| Toplu Test | Veri seti seçimi, ilerleme çubuğu, rapor | Enes |
| Tahmin | Tahmini hata ve optimum test sayısı | Burak |

Uzun işlemlerin tamamı `QThread` içinde çalışır; GUI iş parçacığı asla bloklanmaz.
