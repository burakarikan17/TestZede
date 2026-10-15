# Katkı Rehberi

## Geliştirme ortamı

- Python **3.11** (herkes aynı sürümü kullanır).
- Kurulum adımları README'dedir.
- **Windows kullanıcıları:** Türkçe Windows'ta Python'un varsayılan kodlaması
  `cp1254` olabilir. Sistem ortam değişkenlerine `PYTHONUTF8=1` ekleyin ve
  kodda her `open()` çağrısında `encoding="utf-8"` yazın.

## İş akışı

1. Her iş, task board'da (GitHub Projects) bir karta bağlıdır.
   Sütunlar: Backlog → To Do → In Progress → Review → Done.
2. Branch'ler `develop`'tan açılır:
   - `feature/US-3-coverage-runner`
   - `fix/sandbox-timeout`
   - `docs/std-test-cases`
3. `main` ve `develop` korumalıdır; doğrudan push yapılmaz.
4. PR `develop`'a açılır. En az **1 onay** ve yeşil CI gerekir.
   `domain/models.py` değişikliklerinde **3 onay** gerekir.
5. Sprint sonunda `develop` → `main` birleştirilir ve etiketlenir (`v0.1.0` …).

## Commit mesajları (Conventional Commits)

```
feat(rl): add FROM_DOCSTRING action
fix(execution): kill child process on timeout
test(metrics): cover halstead edge cases
docs: update ARCHITECTURE data split
```

## Kod standartları

- Biçim ve lint: `ruff format` + `ruff check` (pre-commit otomatik çalıştırır).
- Tüm public fonksiyonlarda tip ipucu ve kısa docstring.
- Modüller arası veri yalnızca `domain` modelleriyle taşınır.
- GUI kodu çekirdek modülleri doğrudan import etmez; `services` kullanılır.

## Platformlar arası kurallar (Windows + macOS)

- Yollar için her zaman `pathlib.Path` kullanılır; `"\\"` ya da `"/"` elle birleştirilmez.
- `subprocess` çağrılarında `shell=True` kullanılmaz. `timeout=` zorunludur.
  Çağrılar her zaman `[sys.executable, "-m", ...]` biçiminde yapılır.
- `multiprocessing` kullanan giriş noktaları `if __name__ == "__main__":` korumasıyla yazılır.
- `signal.alarm` gibi yalnızca POSIX'te bulunan API'ler kullanılmaz.
- Satır sonları `.gitattributes` ile yönetilir (`* text=auto eol=lf`).
- CI her PR'ı `windows-latest` ve `macos-latest` üzerinde test eder.

## Testler

- Framework: `pytest` (+ GUI için `pytest-qt`).
- Her modülün sahibi kendi unit testlerini yazar (`tests/unit/<modül>/`).
- Çekirdek modüllerde hedef: en az %70 satır coverage.
- White-box test paketi teslimi `tests/whitebox/` altındadır (en az 3 test case).
- Çalıştırma: `pytest -q` · coverage ile: `pytest --cov=testzede`

## Kabul testine hazırlık (Madde-1)

Kabul testinde bulunan her hata −3, programı çökerten her hata −10 puandır. Bu yüzden:

- Kullanıcı girdisi kaynaklı her hata yakalanır ve arayüzde mesaj olarak gösterilir.
  Yakalanmamış istisna GUI'ye ulaşmaz (global `sys.excepthook` + log).
- Test edilen kod her zaman sandbox alt sürecinde çalışır.
- Teslimden önce `docs/std/` içindeki STD senaryoları üç kişi tarafından
  çapraz olarak (başkasının modülü) manuel test edilir.

## Yeni bir şey eklemek

- **Yeni veri seti:** `datasets/base.py`'deki `DatasetLoader`'dan türetin,
  `DatasetFactory`'ye kaydedin, `make-splits`'e ekleyin.
- **Yeni RL eylemi:** `rl/actions.py`'de `Action` strategy sınıfı yazın,
  `ACTION_REGISTRY`'ye ekleyin. Durum uzayı değişirse ARCHITECTURE'ı güncelleyin.
- **Yeni mutasyon operatörü:** `mutation/operators.py`'de `MutationOperator`'dan türetin.

## Veri ve büyük dosyalar

`data/`, `reports/`, `.venv/` ve model ağırlıkları repoya commit edilmez.
Paylaşılması gereken sonuçlar GitHub Release eki olarak yüklenir.

## Definition of Done

- [ ] Kod ve testler yazıldı, CI yeşil (Windows + macOS).
- [ ] İlgili GUI sayfası çalışıyor ve çökmüyor.
- [ ] Task board kartı güncellendi.
- [ ] Gerekirse README / ARCHITECTURE güncellendi.
