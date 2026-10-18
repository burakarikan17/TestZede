"""Tabular Q-learning ajanı (ε-greedy)."""

from __future__ import annotations

import numpy as np


class QLearningAgent:
    """Durum ve eylem indeksleri üzerinde çalışan Q-learning ajanı.

    Args:
        n_states: Durum uzayı boyutu (``state.state_count``).
        n_actions: Eylem sayısı (``len(actions.ACTION_NAMES)``).
        learning_rate: Öğrenme oranı α.
        discount: İndirim katsayısı γ.
        epsilon_greedy: Rastgele eylem seçme olasılığı.
        seed: Tekrarlanabilirlik için rastgelelik tohumu.
    """

    def __init__(
        self,
        n_states: int,
        n_actions: int,
        *,
        learning_rate: float = 0.1,
        discount: float = 0.9,
        epsilon_greedy: float = 0.2,
        seed: int | None = None,
    ) -> None:
        if n_states < 1 or n_actions < 1:
            raise ValueError("n_states ve n_actions pozitif olmalı")
        self.q = np.zeros((n_states, n_actions))
        self.learning_rate = learning_rate
        self.discount = discount
        self.epsilon_greedy = epsilon_greedy
        self._rng = np.random.default_rng(seed)

    def select_action(self, state: int, *, greedy: bool = False) -> int:
        """ε-greedy eylem seçer; eşit Q değerleri arasında rastgele seçim yapar."""
        if not greedy and self._rng.random() < self.epsilon_greedy:
            return int(self._rng.integers(self.q.shape[1]))
        row = self.q[state]
        best = np.flatnonzero(row == row.max())
        return int(self._rng.choice(best))

    def update(
        self, state: int, action: int, reward: float, next_state: int, *, done: bool
    ) -> None:
        """Q(s,a) ← Q(s,a) + α·(r + γ·max Q(s',·) − Q(s,a))."""
        target = reward if done else reward + self.discount * self.q[next_state].max()
        self.q[state, action] += self.learning_rate * (target - self.q[state, action])
