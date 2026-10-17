import pytest
from conftest import FakeExecutor

from testzede.domain.models import CodeUnit, TestCase
from testzede.rl.actions import ACTION_NAMES
from testzede.rl.env import EnvConfig, TestGenEnv
from testzede.rl.signature import SignatureError
from testzede.rl.trainer import RLConfig, generate_tests

BOUNDARY = ACTION_NAMES.index("BOUNDARY")
NEGATIVE = ACTION_NAMES.index("NEGATIVE")
EMPTY = ACTION_NAMES.index("EMPTY")
FROM_DOCSTRING = ACTION_NAMES.index("FROM_DOCSTRING")
MUTATE_BEST = ACTION_NAMES.index("MUTATE_BEST")


def test_steps_union_coverage_until_all_branches_hit(sign_unit, sign_executor):
    env = TestGenEnv(sign_unit, sign_executor)
    env.reset(seed=0)

    _, r1, done, _, info = env.step(FROM_DOCSTRING)  # sign(5) → x > 0
    assert info["kept"] and not done and r1 > 0
    _, _, done, _, _ = env.step(NEGATIVE)
    assert not done
    _, _, done, _, _ = env.step(EMPTY)  # sign(0)
    assert done

    report = env.episode.report()
    assert (report.covered_branches, report.total_branches) == (4, 4)
    assert len(env.episode.tests) == 3
    assert sign_executor.runs == 3  # her adımda yalnızca yeni test koşturulur


def test_redundant_input_is_penalized_and_dropped(sign_unit, sign_executor):
    env = TestGenEnv(sign_unit, sign_executor)
    env.reset(seed=0)
    env.step(FROM_DOCSTRING)
    _, reward, _, _, info = env.step(FROM_DOCSTRING)
    assert not info["kept"]
    assert reward == pytest.approx(-env.weights.epsilon)
    assert len(env.episode.tests) == 1


def test_inapplicable_action_is_invalid(sign_unit, sign_executor):
    env = TestGenEnv(sign_unit, sign_executor)
    env.reset(seed=0)
    _, reward, _, _, info = env.step(MUTATE_BEST)  # henüz en iyi girdi yok
    assert info["invalid"]
    assert reward == pytest.approx(-env.weights.delta - env.weights.epsilon)
    assert sign_executor.calls == []


def test_failing_test_is_not_kept(sign_unit, sign_executor, monkeypatch):
    def broken_run(unit, tests, *, timeout=10.0):
        result = FakeExecutor.run_tests(sign_executor, unit, tests, timeout=timeout)
        result.test_outcomes = {name: "error" for name in result.test_outcomes}
        return result

    monkeypatch.setattr(sign_executor, "run_tests", broken_run)
    env = TestGenEnv(sign_unit, sign_executor)
    env.reset(seed=0)
    _, _, _, _, info = env.step(FROM_DOCSTRING)
    assert info["invalid"]
    assert env.episode.tests == []
    assert env.episode.report() is None


def test_patience_truncates_episode(sign_unit, sign_executor):
    env = TestGenEnv(sign_unit, sign_executor, config=EnvConfig(patience=2))
    env.reset(seed=0)
    env.step(FROM_DOCSTRING)
    _, _, terminated, truncated, _ = env.step(FROM_DOCSTRING)
    assert not truncated
    _, _, terminated, truncated, _ = env.step(FROM_DOCSTRING)
    assert truncated and not terminated


def test_reset_raises_for_missing_entry_point(sign_executor):
    env = TestGenEnv(CodeUnit("x", "def g(): pass", entry_point="f"), sign_executor)
    with pytest.raises(SignatureError):
        env.reset()


def test_generate_tests_reaches_full_branch_coverage(sign_unit, sign_executor):
    config = RLConfig(episodes=3)
    result = generate_tests(sign_unit, sign_executor, config, seed=42)
    assert result.coverage.covered_branches == 4
    assert 3 <= len(result.tests) <= 4
    assert len({t.name for t in result.tests}) == len(result.tests)
    assert result.curve[-1].branch_rate == 1.0
    assert result.stats.generated >= len(result.tests)
    assert 0.0 < result.stats.compilation_rate <= 1.0


def test_config_from_mapping_matches_default_yaml_layout():
    config = RLConfig.from_mapping(
        {
            "reward": {"alpha": 1.0, "beta": 2.0, "gamma": 0.5, "delta": 1.0, "epsilon": 0.05},
            "agent": {
                "type": "q_learning",
                "learning_rate": 0.2,
                "discount": 0.9,
                "epsilon_greedy": 0.1,
                "max_steps": 30,
                "patience": 5,
            },
            "sandbox": {"timeout_s": 7},
        }
    )
    assert config.agent.learning_rate == 0.2
    assert (config.env.max_steps, config.env.patience) == (30, 5)
    assert config.env.run_timeout_s == 7.0


def test_config_rejects_unknown_agent_key():
    with pytest.raises(ValueError, match="gamma_typo"):
        RLConfig.from_mapping({"agent": {"gamma_typo": 1}})


def _user_test(*calls):
    # FakeExecutor, TestCase.name ile aynı adlı fonksiyonu çağırır.
    body = "\n".join(f"    sign({x})" for x in calls)
    return TestCase(
        "user_tests", f"from target import sign\n\n\ndef user_tests():\n{body}\n", "user"
    )


def test_episode_starts_from_user_test_coverage(sign_unit, sign_executor):
    env = TestGenEnv(sign_unit, sign_executor, baseline=[_user_test(5)])
    env.reset(seed=0)
    report = env.episode.report()
    assert (report.covered_lines, report.covered_branches) == (2, 1)
    assert env.episode.tests == []
    assert env.baseline_report() == report
    runs = sign_executor.runs
    env.reset(seed=1)
    assert sign_executor.runs == runs  # kullanıcı testleri bir kez çalıştırılır


def test_rl_adds_only_missing_coverage(sign_unit, sign_executor):
    result = generate_tests(
        sign_unit, sign_executor, RLConfig(episodes=2), seed=0, baseline=[_user_test(5)]
    )
    assert result.baseline.covered_branches == 1
    assert result.coverage.covered_branches == 4
    assert all(test.origin == "rl" for test in result.tests)


def test_no_tests_when_user_tests_cover_everything(sign_unit, sign_executor):
    result = generate_tests(sign_unit, sign_executor, seed=0, baseline=[_user_test(5, -5, 0)])
    assert result.tests == [] and result.steps == 0
    assert result.coverage.covered_branches == result.coverage.total_branches == 4
