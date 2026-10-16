"""Test üretim ortamı: bir epizot tek bir ``CodeUnit`` üzerinde geçer.

API gymnasium'a benzer (``reset`` / ``step`` → ``obs, reward, terminated,
truncated, info``) ama gymnasium'a bağımlı değildir; gözlem Q-tablosu satır
indeksidir.

Her adımda yalnızca yeni test çalıştırılır; kapsanan satır ve branch kümeleri
ortamda birleştirilir (her adımda tüm paketi baştan koşturmak yavaştır).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.rl.actions import ACTION_NAMES, ACTION_REGISTRY, ActionContext
from testzede.rl.executor import Executor
from testzede.rl.reward import RewardWeights, branch_rate, compute_reward, line_rate
from testzede.rl.signature import extract_params, parse_seed_inputs
from testzede.rl.state import discretize, state_index
from testzede.rl.synthesizer import output_class, synthesize


@dataclass(frozen=True)
class EnvConfig:
    max_steps: int = 50
    patience: int = 10  # coverage artışı olmadan geçebilecek adım sayısı
    bins: int = 5
    call_timeout_s: float = 2.0
    run_timeout_s: float = 10.0


@dataclass(frozen=True)
class CurvePoint:
    """Bir adım sonundaki durum; opsiyonel tahmin modülü diz noktasını buradan bulur."""

    step: int
    tests: int
    line_rate: float
    branch_rate: float


@dataclass
class EpisodeState:
    tests: list[TestCase] = field(default_factory=list)
    covered_lines: set[int] = field(default_factory=set)
    covered_branches: set[tuple[int, int]] = field(default_factory=set)
    all_lines: set[int] = field(default_factory=set)
    all_branches: set[tuple[int, int]] = field(default_factory=set)
    seen_classes: set[str] = field(default_factory=set)
    curve: list[CurvePoint] = field(default_factory=list)
    best_input: tuple | None = None
    best_gain: float = 0.0
    generated: int = 0
    compiled: int = 0
    execution_time_s: float = 0.0
    step: int = 0
    stale_steps: int = 0
    last_ok: bool = True

    def report(self) -> CoverageReport | None:
        if not self.all_lines:
            return None
        return CoverageReport(
            covered_lines=len(self.covered_lines & self.all_lines),
            total_lines=len(self.all_lines),
            covered_branches=len(self.covered_branches & self.all_branches),
            total_branches=len(self.all_branches),
        )

    def stats(self) -> RunStats:
        return RunStats(self.generated, self.compiled, self.execution_time_s)


class TestGenEnv:
    """RL test üretim ortamı.

    Raises:
        SignatureError: ``reset`` sırasında giriş fonksiyonu çözümlenemezse.
    """

    __test__ = False  # pytest bu sınıfı test olarak toplamasın

    def __init__(
        self,
        unit: CodeUnit,
        executor: Executor,
        *,
        weights: RewardWeights | None = None,
        config: EnvConfig | None = None,
    ) -> None:
        self.unit = unit
        self.executor = executor
        self.weights = weights or RewardWeights()
        self.config = config or EnvConfig()
        self.n_actions = len(ACTION_NAMES)
        self.episode = EpisodeState()
        self._rng = random.Random()
        self._params = ()
        self._seeds: tuple[tuple, ...] = ()

    @property
    def entry_point(self) -> str:
        return self.unit.entry_point or ""

    def observe(self) -> int:
        state = discretize(
            self.episode.report(),
            last_ok=self.episode.last_ok,
            step=self.episode.step,
            max_steps=self.config.max_steps,
            bins=self.config.bins,
        )
        return state_index(state, self.config.bins)

    def reset(self, *, seed: int | None = None) -> tuple[int, dict]:
        self._rng = random.Random(seed)
        self._params = extract_params(self.unit)
        self._seeds = parse_seed_inputs(self.unit)
        self.episode = EpisodeState()
        return self.observe(), {}

    def step(self, action: int) -> tuple[int, float, bool, bool, dict]:
        ep = self.episode
        before = ep.report()
        ep.step += 1
        info: dict = {"action": ACTION_NAMES[action], "kept": False}

        test, args, out_class = self._run_action(action)
        invalid = test is None
        new_class = False
        gain = 0.0
        if test is not None:
            new_class = out_class not in ep.seen_classes
            ep.seen_classes.add(out_class)
            gain = line_rate(ep.report()) + branch_rate(ep.report())
            gain -= line_rate(before) + branch_rate(before)
            if gain > 0 or new_class:
                ep.tests.append(test)
                info["kept"] = True
            if gain > ep.best_gain:
                ep.best_gain, ep.best_input = gain, args

        after = ep.report()
        reward = compute_reward(
            self.weights, before, after, new_output_class=new_class, invalid=invalid
        )
        ep.last_ok = not invalid
        ep.stale_steps = 0 if gain > 0 else ep.stale_steps + 1
        ep.curve.append(CurvePoint(ep.step, len(ep.tests), line_rate(after), branch_rate(after)))

        terminated = self._fully_covered(after)
        truncated = not terminated and (
            ep.step >= self.config.max_steps or ep.stale_steps >= self.config.patience
        )
        info.update(invalid=invalid, new_class=new_class)
        return self.observe(), reward, terminated, truncated, info

    def _run_action(self, action: int) -> tuple[TestCase | None, tuple | None, str]:
        """Girdi üretir, oracle'dan geçirir, testi çalıştırır ve coverage'ı birleştirir.

        Geçersiz adımda (girdi yok, timeout, test geçmedi) ``(None, args, "")`` döner.
        """
        ep = self.episode
        ctx = ActionContext(self._params, self._seeds, ep.best_input)
        args = ACTION_REGISTRY[ACTION_NAMES[action]].generate(ctx, self._rng)
        if args is None:
            return None, None, ""

        outcome = self.executor.call_function(
            self.unit, repr(tuple(args)), timeout=self.config.call_timeout_s
        )
        ep.execution_time_s += outcome.duration_s
        test = synthesize(self.entry_point, args, outcome, ep.step)
        if test is None:
            return None, args, ""

        result = self.executor.run_tests(self.unit, [test], timeout=self.config.run_timeout_s)
        ep.generated += result.stats.generated
        ep.compiled += result.stats.compiled
        ep.execution_time_s += result.stats.execution_time_s
        if result.test_outcomes.get(test.name) != "passed":
            return None, args, ""

        ep.all_lines |= result.all_lines
        ep.all_branches |= result.all_branches
        ep.covered_lines |= result.covered_lines
        ep.covered_branches |= result.covered_branches
        return test, args, output_class(outcome)

    @staticmethod
    def _fully_covered(report: CoverageReport | None) -> bool:
        if report is None:
            return False
        if report.total_branches:
            return report.covered_branches == report.total_branches
        return report.total_lines > 0 and report.covered_lines == report.total_lines
