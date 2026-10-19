# SonarQube bulguları

Tarama: SonarQube Community Build 26.10, `develop` (2026-10-19). Ana sayfa: [sonarqube-dashboard.png](sonarqube-dashboard.png).

Sonuç: Quality Gate **Passed**, Coverage %96.3, Duplications %0.5, Reliability A, Security A, Maintainability A.

## Düzeltilenler

| Kural | Yer | Düzeltme |
|-------|-----|----------|
| python:S5863 (Bug) | `tests/unit/services/test_analysis_service.py` `test_layout_is_deterministic` | `assert f(x) == f(x)` yerine iki çağrının sonucu ayrı değişkenlere alınıp karşılaştırıldı. Test aynı girdiyle iki çağrının aynı sonucu verdiğini doğruluyor. |
| python:S5863 (Bug) | `tests/unit/rl/test_actions.py` `test_generation_is_deterministic_for_same_seed` | Aynı düzeltme. |

## Kabul edilenler (Accepted)

| Kural | Yer | Gerekçe |
|-------|-----|---------|
| python:S2245 (Vulnerability) | `src/testzede/mutation/engine.py` `_sample` | `random.Random(seed)` yalnızca mutant sayısı sınırı aşıldığında mutantları tekrarlanabilir biçimde örneklemek için kullanılır. Güvenlik amacı yoktur. Aynı tohumla aynı mutantların seçilmesi gerektiği için `secrets` gibi kriptografik bir üreteç kullanılamaz. |
