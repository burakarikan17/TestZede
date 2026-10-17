"""White-box testler: ``coverage_runner._parse_junit`` karar noktaları.

Hedef: ``_parse_junit(path)``; elle yazılmış XML dosyalarıyla doğrudan çağrılır.

- ``try: ET.parse`` / ``except (OSError, ET.ParseError)`` -> BRANCH coverage: dosya yok
  (OSError) ve bozuk XML (ParseError) ayrı ayrı; ikisi de ``{}`` döndürür. (satır 133-134)
- ``module = (classname or name).split(".")[0]``         -> BRANCH coverage: classname dolu
  (normal test) ve classname boş (toplama hatası, ``name`` kullanılır).
- ``if not match: continue``                             -> BRANCH coverage: ``test_NNNN``
  kalıbına uymayan testcase atlanır. (satır 141)
- ``error`` / ``failure`` / passed zinciri               -> BRANCH coverage: üç dal da ayrı bir
  testcase ile çalıştırılır; ``error`` ve ``failure`` birlikte olduğunda ``error`` önceliklidir.
- ``if index not in result or severity > ...``           -> PATH coverage: ilk görülme,
  daha kötü sonucun üzerine yazması ve daha iyi sonucun yazmaması (üç farklı yol).
"""

from __future__ import annotations

from pathlib import Path

from testzede.execution.coverage_runner import _parse_junit


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "report.xml"
    xml = f'<?xml version="1.0" encoding="utf-8"?><testsuites>{body}</testsuites>'
    path.write_text(xml, encoding="utf-8")
    return path


def _case(classname: str, name: str = "test_x", child: str = "") -> str:
    return f'<testcase classname="{classname}" name="{name}">{child}</testcase>'


def test_missing_file_returns_empty(tmp_path):
    assert _parse_junit(tmp_path / "yok.xml") == {}


def test_malformed_xml_returns_empty(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text("<testsuites><testcase", encoding="utf-8")
    assert _parse_junit(path) == {}


def test_empty_file_returns_empty(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text("", encoding="utf-8")
    assert _parse_junit(path) == {}


def test_passed_failure_and_error_branches(tmp_path):
    path = _write(
        tmp_path,
        _case("test_0000")
        + _case("test_0001", child='<failure message="x"/>')
        + _case("test_0002", child='<error message="x"/>'),
    )
    assert _parse_junit(path) == {0: "passed", 1: "failed", 2: "error"}


def test_error_takes_precedence_over_failure_in_same_testcase(tmp_path):
    path = _write(tmp_path, _case("test_0000", child="<failure/><error/>"))
    assert _parse_junit(path) == {0: "error"}


def test_non_matching_module_name_is_skipped(tmp_path):
    path = _write(
        tmp_path,
        _case("other_module") + _case("test_12") + _case("test_0003") + _case("conftest"),
    )
    assert _parse_junit(path) == {3: "passed"}  # yalnızca test_NNNN (>= 4 hane) eşleşir


def test_collection_error_uses_name_when_classname_empty(tmp_path):
    path = _write(tmp_path, _case("", name="test_0005", child='<error message="x"/>'))
    assert _parse_junit(path) == {5: "error"}


def test_dotted_classname_uses_first_segment(tmp_path):
    path = _write(tmp_path, _case("test_0007.TestClass"))
    assert _parse_junit(path) == {7: "passed"}


def test_worse_outcome_overwrites_better_for_same_index(tmp_path):
    path = _write(tmp_path, _case("test_0000") + _case("test_0000", child="<failure/>"))
    assert _parse_junit(path) == {0: "failed"}


def test_better_outcome_does_not_overwrite_worse(tmp_path):
    path = _write(tmp_path, _case("test_0000", child="<error/>") + _case("test_0000"))
    assert _parse_junit(path) == {0: "error"}


def test_equal_severity_keeps_first(tmp_path):
    path = _write(tmp_path, _case("test_0000") + _case("test_0000"))
    assert _parse_junit(path) == {0: "passed"}


def test_no_testcases_returns_empty(tmp_path):
    assert _parse_junit(_write(tmp_path, "")) == {}
