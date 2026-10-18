# Kalite analizi (SonarQube)

Şartname "SonarQube ana sayfa analiz ekran çıktısı **ya da** SourceMonitor (Kiviat grafiği,
Block Histogram)" ister (5 puan) ve bu çıktılarda problem olup olmadığına bakar.

## Neden SonarQube

SourceMonitor yalnızca C++, C, C#, VB.NET, Java, Delphi, Visual Basic (VB6) ve HTML kaynaklarını
ölçer; **Python desteklemez** ([kaynak](https://alternativeto.net/software/sourcemonitor/about)).
TestZede Python ile yazıldığı için bu repo için SonarQube kullanılır. SonarQube Python'u destekler
ve karmaşıklık, tekrar, kod kokusu, hata ve güvenlik açığı ölçümlerini ana sayfada tek ekranda verir.

## Hazırlık (repoda hazır)

- `sonar-project.properties`: proje anahtarı, kaynak (`src`) ve test (`tests`) klasörleri, Python 3.11,
  coverage raporu yolu.
- `coverage.xml` `.gitignore`'dadır; repoya girmez.

## Adımlar (Windows)

1. **Java 17 ya da üzeri** kurulu olmalı (`java -version`).
2. SonarSource'un resmi sayfasından **SonarQube Community Build**'i indirip bir klasöre açın.
3. `bin\windows-x86-64\StartSonar.bat` dosyasını çalıştırın; "SonarQube is operational" yazısını bekleyin.
4. Tarayıcıda `http://localhost:9000` açın. İlk giriş `admin` / `admin`; şifreyi değiştirmeniz istenir.
5. **Create a local project** ile proje oluşturun (proje anahtarı: `testzede`), **Use the global setting**
   ve ardından **Locally** seçin; bir **token** üretin ve not edin. Token'ı repoya yazmayın.
6. SonarSource'un resmi sayfasından **SonarScanner CLI**'yi indirip açın; `bin` klasörünü `PATH`'e ekleyin.
7. Proje klasöründe sanal ortam etkinken coverage raporunu üretin:

   ```powershell
   pytest --cov=testzede --cov-report=xml
   ```

8. Taramayı çalıştırın:

   ```powershell
   sonar-scanner "-Dsonar.host.url=http://localhost:9000" "-Dsonar.token=<token>"
   ```

9. `http://localhost:9000/dashboard?id=testzede` sayfasını açın.

## Teslim edilecek ekran görüntüsü

Proje ana sayfasının tamamı: Quality Gate sonucu, Bugs, Vulnerabilities, Security Hotspots, Code Smells,
Coverage ve Duplications kutuları. Görüntüyü `docs/kalite/` klasörüne koyun ve STD ile birlikte teslim edin.

## "Problem var mı?" sorusu için

Taramadan sonra ana sayfadaki her kutuya girip bulguları gözden geçirin. Düzeltilebilenleri düzeltip taramayı
tekrarlayın; düzeltilmeyenler için kısa bir gerekçe yazın (örneğin: test edilen kodu çalıştırmak projenin amacıdır,
bu yüzden `exec` kullanımı bilerek yapılmıştır). Bu not da teslime eklenir.

Projede zaten uygulanan kalite kuralları: `ruff check` ve `ruff format --check` (CI'da her PR'da çalışır), çekirdek
modüllerde en az %70 satır coverage hedefi, tüm public fonksiyonlarda tip ipucu ve docstring.
