"""
戦闘中「仲間の行動パターン」を状態にし、敵の狙い方を Q 学習で更新する軽量エージェント。
本編 main.py から参照（numpy 不要・単体でも動く）。
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import Any, Dict, List, Optional, Tuple

# 状態: 仲間の累計 (攻撃/防御/呪文) を各 0..5 に量子化 × 敵HP帯 3段
N_ATK = 6
N_DEF = 6
N_SPL = 6
N_HP = 3
N_STATES = N_ATK * N_DEF * N_SPL * N_HP
# 行動: 0=主人公狙い 1=HP最低の仲間 2=攻撃力最高の仲間
N_ACTIONS = 3


def _bucket(n: int) -> int:
    return max(0, min(5, int(n)))


def _hp_band(cur: float, mx: float) -> int:
    if mx <= 0:
        return 2
    r = cur / mx
    if r > 0.66:
        return 0
    if r > 0.33:
        return 1
    return 2


def encode_state(ally_atk: int, ally_def: int, ally_spell: int, enemy_hp: float, enemy_max_hp: float) -> int:
    a = _bucket(ally_atk)
    d = _bucket(ally_def)
    s = _bucket(ally_spell)
    h = _hp_band(enemy_hp, enemy_max_hp)
    return ((a * N_DEF + d) * N_SPL + s) * N_HP + h


class BattleQAgent:
    def __init__(self, save_path: Optional[str] = None, alpha: float = 0.18, gamma: float = 0.92, epsilon: float = 0.14):
        self.save_path = save_path
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.q: List[List[float]] = [[0.0 for _ in range(N_ACTIONS)] for _ in range(N_STATES)]
        self._last: Optional[Tuple[int, int, float]] = None  # state, action, reward already applied? use pending
        self._pending_sars: Optional[Tuple[int, int, float, int]] = None
        if save_path and os.path.isfile(save_path):
            self.load(save_path)

    def load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("q")
            if isinstance(rows, list) and len(rows) == N_STATES:
                for i, row in enumerate(rows):
                    if isinstance(row, list) and len(row) == N_ACTIONS:
                        self.q[i] = [float(x) for x in row]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    def save(self, path: Optional[str] = None) -> None:
        path = path or self.save_path
        if not path:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"q": self.q, "meta": {"n_states": N_STATES, "n_actions": N_ACTIONS}}, f, ensure_ascii=False)

    def begin_battle(self) -> None:
        self._pending_sars = None

    def flush_after_ally_round(self, state: int, action: int, reward: float, next_state: int) -> None:
        """直前の敵行動 (s,a) に対し、味方ターン後の next_state で TD 更新"""
        i = state
        aa = self.alpha
        g = self.gamma
        best_next = max(self.q[next_state])
        td_target = reward + g * best_next
        old = self.q[i][action]
        self.q[i][action] = old + aa * (td_target - old)

    def flush_terminal(self, state: int, action: int, reward: float) -> None:
        """戦闘終了時など、次状態が無い場合の収束更新"""
        i, aa = state, self.alpha
        self.q[i][action] += aa * (reward - self.q[i][action])

    def pick_action(self, state: int) -> int:
        if random.random() < self.epsilon:
            return random.randrange(N_ACTIONS)
        row = self.q[state]
        m = max(row)
        cands = [j for j, v in enumerate(row) if math.isclose(v, m, rel_tol=1e-5, abs_tol=1e-5)]
        return random.choice(cands)

    def reward_for_damage(self, damage: int) -> float:
        return max(0.0, min(1.2, damage / 22.0))


def pick_enemy_target_from_action(
    action: int,
    player: Dict[str, Any],
    party: List[Dict[str, Any]],
    max_party: int,
) -> Tuple[str, Any]:
    """
    Returns ("player", player) or ("party", member_dict)
    """
    if action == 0:
        return "player", player
    alive = [p for p in party[:max_party] if p.get("hp", 0) > 0 and not p.get("absent")]
    if not alive:
        return "player", player
    if action == 1:
        tgt = min(alive, key=lambda p: p.get("hp", 1) / max(1, p.get("max_hp", 1)))
        return "party", tgt
    # action == 2: 高火力狙い
    tgt = max(alive, key=lambda p: p.get("atk", 0))
    return "party", tgt
