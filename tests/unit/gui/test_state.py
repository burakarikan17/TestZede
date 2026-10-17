from __future__ import annotations

from testzede.domain.models import TestCase
from testzede.gui.state import AppState


def test_defaults_are_empty():
    state = AppState()
    assert state.source == ""
    assert state.tests == []
    assert state.execution_result is None
    assert state.mutation_run is None


def test_instances_do_not_share_the_tests_list():
    a, b = AppState(), AppState()
    a.tests.append(TestCase("t", "def test_t(): pass", "user"))
    assert b.tests == []


def test_reset_restores_every_field():
    state = AppState(
        source="x = 1",
        tests=[TestCase("t", "def test_t(): pass", "user")],
        execution_result=object(),  # type: ignore[arg-type]
        mutation_run=object(),  # type: ignore[arg-type]
    )
    old_tests = state.tests
    state.reset()
    assert state == AppState()
    assert state.tests is not old_tests  # eski liste paylaşılan referanslarda bozulmaz
    assert old_tests  # reset eski listeyi boşaltmadı
