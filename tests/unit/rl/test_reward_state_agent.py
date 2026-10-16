import pytest

from testzede.domain.models import CoverageReport
from testzede.rl.agent import QLearningAgent
from testzede.rl.reward import RewardWeights, compute_reward
from testzede.rl.state import discretize, state_count, state_index

W = RewardWeights(alpha=1.0, beta=2.0, gamma=0.5, delta=1.0, epsilon=0.05)


def _cov(lines: int, branches: int, total_lines: int = 10, total_branches: int = 4):
    return CoverageReport(lines, total_lines, branches, total_branches)


def test_reward_for_coverage_gain():
    r = compute_reward(W, _cov(5, 2), _cov(10, 4), new_output_class=False, invalid=False)
    assert r == pytest.approx(1.0 * 0.5 + 2.0 * 0.5 - 0.05)


def test_reward_first_step_starts_from_zero():
    r = compute_reward(W, None, _cov(5, 1), new_output_class=True, invalid=False)
    assert r == pytest.approx(0.5 + 2.0 * 0.25 + 0.5 - 0.05)


def test_reward_penalizes_invalid_and_redundant_tests():
    redundant = compute_reward(W, _cov(5, 2), _cov(5, 2), new_output_class=False, invalid=False)
    invalid = compute_reward(W, _cov(5, 2), None, new_output_class=False, invalid=True)
    assert redundant == pytest.approx(-0.05)
    assert invalid == pytest.approx(-1.05)


def test_reward_without_branches_ignores_branch_term():
    r = compute_reward(
        W, None, _cov(10, 0, total_branches=0), new_output_class=False, invalid=False
    )
    assert r == pytest.approx(1.0 - 0.05)


def test_weights_from_config():
    w = RewardWeights.from_config({"alpha": 2, "epsilon": 0.1})
    assert (w.alpha, w.beta, w.epsilon) == (2.0, 2.0, 0.1)
    with pytest.raises(ValueError):
        RewardWeights.from_config({"zeta": 1})


def test_discretize_keeps_full_coverage_in_last_bin():
    full = discretize(_cov(10, 4), last_ok=True, step=50, max_steps=50)
    almost = discretize(_cov(9, 3), last_ok=True, step=49, max_steps=50)
    assert (full.line_bin, full.branch_bin, full.step_bin) == (4, 4, 4)
    assert (almost.line_bin, almost.branch_bin, almost.step_bin) == (3, 3, 3)


def test_discretize_without_report_is_zero():
    s = discretize(None, last_ok=False, step=0, max_steps=10)
    assert (s.line_bin, s.branch_bin, s.last_ok, s.step_bin) == (0, 0, False, 0)


def test_state_index_is_a_bijection():
    bins = 3
    seen = {
        state_index(
            discretize(_cov(lc, bc, 2, 2), last_ok=ok, step=st, max_steps=2, bins=bins), bins
        )
        for lc in range(3)
        for bc in range(3)
        for ok in (False, True)
        for st in range(3)
    }
    assert seen == set(range(state_count(bins)))


def test_discretize_rejects_bad_arguments():
    with pytest.raises(ValueError):
        discretize(None, last_ok=True, step=0, max_steps=0)
    with pytest.raises(ValueError):
        discretize(None, last_ok=True, step=0, max_steps=1, bins=1)


def test_agent_learns_rewarding_action():
    agent = QLearningAgent(1, 3, learning_rate=0.5, epsilon_greedy=0.3, seed=0)
    for _ in range(200):
        a = agent.select_action(0)
        agent.update(0, a, 1.0 if a == 2 else 0.0, 0, done=True)
    assert agent.select_action(0, greedy=True) == 2


def test_agent_update_uses_discounted_next_state_value():
    agent = QLearningAgent(2, 1, learning_rate=1.0, discount=0.9)
    agent.q[1, 0] = 10.0
    agent.update(0, 0, 1.0, 1, done=False)
    assert agent.q[0, 0] == pytest.approx(1.0 + 0.9 * 10.0)
    agent.update(0, 0, 1.0, 1, done=True)
    assert agent.q[0, 0] == pytest.approx(1.0)


def test_agent_rejects_empty_spaces():
    with pytest.raises(ValueError):
        QLearningAgent(0, 3)
