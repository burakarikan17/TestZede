from testzede.domain.models import CodeUnit


def test_code_unit_defaults():
    unit = CodeUnit(uid="HumanEval/0", source="def f(): ...", entry_point="f", dataset=None)
    assert unit.seed_examples == ()
