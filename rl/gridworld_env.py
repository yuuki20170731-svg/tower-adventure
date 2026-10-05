"""
ダンジョン風グリッド上の移動を学習する Gymnasium 環境。
本編 main.py の WASD 1マス移動に合わせ、敵・壁に加えて「マップ変化」要素（泥・宝箱・局所地形）と
直近の行動履歴を観測に含められる（方策がギミック配置の統計に適応しやすくする）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Literal, Optional, Set, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

EnemyPolicy = Literal["chase", "random", "wander", "idle"]


@dataclass
class GridWorldConfig:
    width: int = 20
    height: int = 20
    max_enemies: int = 6
    min_enemies: int = 1
    max_steps: int = 250
    randomize_enemy_count: bool = True
    policies_pool: Tuple[EnemyPolicy, ...] = ("chase", "random", "wander", "idle")
    wall_density: float = 0.08
    # マップ変化: 泥（スリップ）・宝箱（1回報酬）・観測に含める周辺壁パッチ
    mud_density: float = 0.06
    n_chests: int = 2
    mud_slip_prob: float = 0.18
    use_local_wall_patch: bool = True
    action_history_len: int = 6


def _clamp_cell(x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    return max(0, min(w - 1, x)), max(0, min(h - 1, y))


def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class GridWorldEnv(gym.Env):
    """
    行動: 0=上 1=下 2=左 3=右
    報酬: ゴール +1.0、敵接触 -1.0、宝箱初回 +0.35、泥でスリップ時微ペナ
    観測: 正規化座標 + 敵相対 + 方針 onehot +（任意）3x3 壁 + 宝箱相対 + 直近行動
    """

    metadata = {"render_modes": ["ansi"]}

    def __init__(self, cfg: Optional[GridWorldConfig] = None, render_mode: Optional[str] = None):
        super().__init__()
        self.cfg = cfg or GridWorldConfig()
        self.render_mode = render_mode

        self.action_space = spaces.Discrete(4)
        me = self.cfg.max_enemies
        n_pol = len(self.cfg.policies_pool)
        base = 4 + me * (3 + n_pol)
        extra = 0
        if self.cfg.use_local_wall_patch:
            extra += 9 + 3  # 3x3 壁 + 宝箱 dx,dy,存在フラグ寄り
        extra += int(max(0, self.cfg.action_history_len))
        self._obs_extra = extra
        obs_dim = base + extra
        high = np.ones(obs_dim, dtype=np.float32)
        self.observation_space = spaces.Box(-high, high, dtype=np.float32)

        self._rng: np.random.Generator = np.random.default_rng()
        self._walls: np.ndarray
        self._mud: np.ndarray
        self._player: Tuple[int, int]
        self._goal: Tuple[int, int]
        self._chests: Set[Tuple[int, int]]
        self._chest_taken: Set[Tuple[int, int]]
        self._enemy_positions: List[Tuple[int, int]]
        self._enemy_policies: List[EnemyPolicy]
        self._steps: int = 0
        self._last_dir: Tuple[int, int] = (0, 0)
        self._action_hist: List[int]

    def seed(self, seed: Optional[int] = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        random.seed(int(self._rng.integers(0, 2**31 - 1)))

        c = self.cfg
        w, h = c.width, c.height
        self._walls = np.zeros((h, w), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                    self._walls[y, x] = 1
                elif self._rng.random() < c.wall_density:
                    self._walls[y, x] = 1

        self._mud = np.zeros((h, w), dtype=np.uint8)
        free = [(x, y) for y in range(h) for x in range(w) if self._walls[y, x] == 0]
        self._rng.shuffle(free)
        for x, y in free[2:]:
            if self._rng.random() < c.mud_density:
                self._mud[y, x] = 1

        self._player = tuple(free[0])
        self._goal = tuple(free[1])
        occupied = {self._player, self._goal}

        if c.randomize_enemy_count:
            n_en = int(self._rng.integers(c.min_enemies, c.max_enemies + 1))
        else:
            n_en = c.max_enemies

        self._enemy_positions = []
        self._enemy_policies = []
        pool = list(c.policies_pool)
        for i in range(n_en):
            if 2 + i >= len(free):
                break
            cell = free[2 + i]
            if cell in occupied:
                continue
            self._enemy_positions.append(cell)
            self._enemy_policies.append(pool[int(self._rng.integers(0, len(pool)))])
            occupied.add(cell)

        self._chests = set()
        self._chest_taken = set()
        for cell in free:
            if cell in occupied:
                continue
            if len(self._chests) >= max(0, c.n_chests):
                break
            self._chests.add(cell)
            occupied.add(cell)

        self._steps = 0
        self._last_dir = (0, 0)
        hl = int(max(0, c.action_history_len))
        self._action_hist = [-1] * hl if hl > 0 else []
        return self._obs(), {}

    def _obs(self) -> np.ndarray:
        c = self.cfg
        w, h = c.width, c.height
        px, py = self._player
        gx, gy = self._goal
        vec: List[float] = [
            (px / max(w - 1, 1)) * 2 - 1,
            (py / max(h - 1, 1)) * 2 - 1,
            (gx / max(w - 1, 1)) * 2 - 1,
            (gy / max(h - 1, 1)) * 2 - 1,
        ]
        n_pol = len(c.policies_pool)
        for i in range(c.max_enemies):
            if i < len(self._enemy_positions):
                ex, ey = self._enemy_positions[i]
                pol = self._enemy_policies[i]
                vec.append((ex - px) / max(w, 1))
                vec.append((ey - py) / max(h, 1))
                vec.append(1.0)
                for p in c.policies_pool:
                    vec.append(1.0 if pol == p else 0.0)
            else:
                vec.extend([0.0, 0.0, 0.0] + [0.0] * n_pol)

        if c.use_local_wall_patch:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = px + dx, py + dy
                    if not (0 <= nx < w and 0 <= ny < h):
                        vec.append(1.0)
                    else:
                        wall = float(self._walls[ny, nx])
                        mud = 0.35 * float(self._mud[ny, nx])
                        vec.append(min(1.0, wall + mud))
            best = None
            for cx, cy in self._chests:
                if (cx, cy) in self._chest_taken:
                    continue
                d = _manhattan((px, py), (cx, cy))
                if best is None or d < best[0]:
                    best = (d, cx, cy)
            if best is None:
                vec.extend([0.0, 0.0, -1.0])
            else:
                _, cx, cy = best
                vec.append((cx - px) / max(w, 1))
                vec.append((cy - py) / max(h, 1))
                vec.append(1.0)

        for a in self._action_hist:
            vec.append((a + 1) / 5.0 if a >= 0 else 0.0)

        return np.asarray(vec, dtype=np.float32)

    def _try_move(self, pos: Tuple[int, int], dx: int, dy: int) -> Tuple[int, int]:
        x, y = pos
        nx, ny = x + dx, y + dy
        if not (0 <= nx < self.cfg.width and 0 <= ny < self.cfg.height):
            return pos
        if self._walls[ny, nx] == 1:
            return pos
        if self._mud[ny, nx] == 1 and self._rng.random() < self.cfg.mud_slip_prob:
            return pos
        return nx, ny

    def step(self, action: int):
        c = self.cfg
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        dx, dy = dirs[int(action) % 4]
        self._player = self._try_move(self._player, dx, dy)
        self._last_dir = (dx, dy)
        if c.action_history_len > 0:
            self._action_hist.append(int(action) % 4)
            self._action_hist = self._action_hist[-int(c.action_history_len) :]

        chest_reward = 0.0
        if self._player in self._chests and self._player not in self._chest_taken:
            self._chest_taken.add(self._player)
            chest_reward = 0.35

        caught = False
        for i, epos in enumerate(self._enemy_positions):
            self._enemy_positions[i] = self._step_enemy(epos, self._enemy_policies[i])

        for epos in self._enemy_positions:
            if epos == self._player:
                caught = True
                break

        self._steps += 1
        terminated = caught or (self._player == self._goal)
        truncated = self._steps >= c.max_steps

        if self._player == self._goal:
            reward = 1.0 + chest_reward
        elif caught:
            reward = -1.0
        else:
            d0 = _manhattan(self._player, self._goal)
            reward = -0.01 * d0 / max(c.width + c.height, 1)
            if self._enemy_positions:
                mind = min(_manhattan(self._player, e) for e in self._enemy_positions)
                reward -= 0.002 / max(mind, 1)
            reward += chest_reward
            if self._mud[self._player[1], self._player[0]] == 1:
                reward -= 0.004

        return self._obs(), float(reward), terminated, truncated, {}

    def _step_enemy(self, pos: Tuple[int, int], pol: EnemyPolicy) -> Tuple[int, int]:
        px, py = self._player
        ex, ey = pos
        if pol == "idle":
            return pos
        if pol == "random":
            rdx, rdy = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            return self._try_move(pos, rdx, rdy)
        if pol == "wander":
            if self._rng.random() < 0.25:
                rdx, rdy = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            else:
                rdx, rdy = self._last_dir if self._last_dir != (0, 0) else random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            return self._try_move(pos, rdx, rdy)
        cand = []
        best = 999
        for rdx, rdy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = self._try_move(pos, rdx, rdy)
            d = _manhattan((nx, ny), (px, py))
            if d < best:
                best = d
                cand = [(nx, ny)]
            elif d == best:
                cand.append((nx, ny))
        return random.choice(cand)

    def render(self):
        if self.render_mode != "ansi":
            return None
        lines = []
        for y in range(self.cfg.height):
            row = []
            for x in range(self.cfg.width):
                ch = "#" if self._walls[y, x] else "."
                if ch == "." and self._mud[y, x] == 1:
                    ch = "~"
                if (x, y) == self._goal:
                    ch = "G"
                if (x, y) in self._chests and (x, y) not in self._chest_taken:
                    ch = "$"
                for e in self._enemy_positions:
                    if (x, y) == e:
                        ch = "E"
                if (x, y) == self._player:
                    ch = "@"
                row.append(ch)
            lines.append("".join(row))
        return "\n".join(lines)


def register_env():
    gym.register(
        id="RPGGridWorld-v0",
        entry_point="rl.gridworld_env:GridWorldEnv",
    )
