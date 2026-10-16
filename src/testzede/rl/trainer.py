"""Epizot döngüsü ve tek bir kod birimi için test üretimi (US-3, US-4)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields

from testzede.domain.models import CodeUnit, CoverageReport, RunStats, TestCase
from testzede.rl.actions import ACTION_NAMES
from testzede.rl.agent import QLearningAgent
from testzede.rl.env import CurvePoint, EnvConfig, TestGenEnv
from testzede.rl.executor import Executor
from testzede.rl.reward import RewardWeights, branch_rate, line_rate
from testzede.rl.state import state_count


@dataclass(frozen=True)
class AgentConfig:
    learning_rate: float = 0.1
    discount: float = 0.9
    epsilon_greedy: float = 0.2


@dataclass(frozen=True)
class RLConfig:
    weights: RewardWeights = field(default_factory=RewardWeights)
    env: EnvConfig = field(default_factory=EnvConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    episodes: int = 1

    @classmethod
    def from_mapping(cls, config: Mapping) -> RLConfig:
        """``configs/*.yaml`` içeriğinden (``reward``, ``agent``, ``sandbox``) yapılandırma kurar."""
        agent_section = dict(config.get("agent", {}))
        agent_section.pop("type", None)
        env_names = {f.name for f in fields(EnvConfig)}
        agent_names = {f.name for f in fields(AgentConfig)}
        env_values = {k: agent_section.pop(k) for k in list(agent_section) if k in env_names}
        episodes = int(agent_section.pop("episodes", 1))
        unknown = set(agent_section) - agent_names
        if unknown:
            raise ValueError(f"Bilinmeyen agent ayarı: {', '.join(sorted(unknown))}")
        sandbox = config.get("sandbox", {})
        if "timeout_s" in sandbox:
            env_values["run_timeout_s"] = float(sandbox["timeout_s"])
        return cls(
            weights=RewardWeights.from_config(config.get("reward", {})),
            env=EnvConfig(**env_values),
            agent=AgentConfig(**agent_section),
            episodes=episodes,
        )

    def make_agent(self, *, seed: int | None = None) -> QLearningAgent:
        return QLearningAgent(
            state_count(self.env.bins),
            len(ACTION_NAMES),
            learning_rate=self.agent.learning_rate,
            discount=self.agent.discount,
            epsilon_greedy=self.agent.epsilon_greedy,
            seed=seed,
        )


@dataclass
class EpisodeResult:
    tests: list[TestCase]
    coverage: CoverageReport | None
    stats: RunStats
    curve: list[CurvePoint]
    total_reward: float
    steps: int

    def score(self) -> tuple[float, float, int]:
        """Karşılaştırma anahtarı: önce branch, sonra satır coverage, sonra az test."""
        return (branch_rate(self.coverage), line_rate(self.coverage), -len(self.tests))


def run_episode(
    env: TestGenEnv, agent: QLearningAgent, *, learn: bool = True, seed: int | None = None
) -> EpisodeResult:
    """Bir epizot oynatır; ``learn`` ise Q-tablosunu günceller."""
    obs, _ = env.reset(seed=seed)
    total = 0.0
    done = False
    while not done:
        action = agent.select_action(obs, greedy=not learn)
        next_obs, reward, terminated, truncated, _ = env.step(action)
        if learn:
            agent.update(obs, action, reward, next_obs, done=terminated)
        total += reward
        obs = next_obs
        done = terminated or truncated
    ep = env.episode
    return EpisodeResult(
        tests=list(ep.tests),
        coverage=ep.report(),
        stats=ep.stats(),
        curve=list(ep.curve),
        total_reward=total,
        steps=ep.step,
    )


def generate_tests(
    unit: CodeUnit,
    executor: Executor,
    config: RLConfig | None = None,
    *,
    agent: QLearningAgent | None = None,
    seed: int | None = None,
) -> EpisodeResult:
    """Kod birimi için ``config.episodes`` epizot oynatır, en iyi epizodun testlerini döner.

    ``agent`` verilirse Q-tablosu birimler arasında paylaşılır (toplu çalıştırma).
    Çalıştırma istatistikleri (``stats``) tüm epizotların toplamıdır.

    Raises:
        SignatureError: Giriş fonksiyonu çözümlenemezse.
    """
    config = config or RLConfig()
    agent = agent or config.make_agent(seed=seed)
    env = TestGenEnv(unit, executor, weights=config.weights, config=config.env)
    best: EpisodeResult | None = None
    generated = compiled = 0
    elapsed = 0.0
    for i in range(max(1, config.episodes)):
        result = run_episode(env, agent, seed=None if seed is None else seed + i)
        generated += result.stats.generated
        compiled += result.stats.compiled
        elapsed += result.stats.execution_time_s
        if best is None or result.score() > best.score():
            best = result
    assert best is not None
    best.stats = RunStats(generated, compiled, elapsed)
    return best
