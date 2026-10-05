"""
ローカルPCで PPO によりプレイヤー移動方策を学習する。
敵の数・行動パターンは GridWorldConfig で指定（ドメインランダム化で毎エピソード変化も可）。

例:
  python rl/train_rl.py --timesteps 200000 --max-enemies 8 --save models/ppo_grid.zip
  python rl/train_rl.py --no-randomize-count --min-enemies 4 --max-enemies 4 --policies chase,random
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import EvalCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv
except ImportError:
    req = os.path.join(ROOT, "requirements-rl.txt")
    exe = sys.executable
    sys.stderr.write(
        "\n[RL] stable-baselines3 が見つかりません（このスクリプトだけ別パッケージが必要です）。\n"
        f"  今の Python: {exe}\n"
        "  プロジェクトの venv で次を実行してください:\n"
        f'    "{exe}" -m pip install -r "{req}"\n'
        "  （torch が入るため初回は時間と容量がかかります）\n\n"
    )
    raise SystemExit(1) from None

from rl.gridworld_env import EnemyPolicy, GridWorldConfig, GridWorldEnv


def _parse_policies(s: str) -> Tuple[EnemyPolicy, ...]:
    allowed: set[str] = {"chase", "random", "wander", "idle"}
    parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    for p in parts:
        if p not in allowed:
            raise SystemExit(f"不明な敵方針: {p} （許可: {', '.join(sorted(allowed))}）")
    if not parts:
        raise SystemExit("--policies に1つ以上指定してください")
    return tuple(parts)  # type: ignore[return-value]


def main():
    ap = argparse.ArgumentParser(description="RPG風グリッド移動の強化学習 (PPO)")
    ap.add_argument("--timesteps", type=int, default=300_000)
    ap.add_argument("--width", type=int, default=20)
    ap.add_argument("--height", type=int, default=20)
    ap.add_argument("--min-enemies", type=int, default=1)
    ap.add_argument("--max-enemies", type=int, default=6)
    ap.add_argument("--max-steps", type=int, default=250)
    ap.add_argument("--wall-density", type=float, default=0.08)
    ap.add_argument("--mud-density", type=float, default=0.06, help="泥マス密度（スリップで行動が無効化されやすい）")
    ap.add_argument("--mud-slip", type=float, default=0.18, help="泥に入ったとき移動失敗する確率")
    ap.add_argument("--chests", type=int, default=2, help="フロアあたりの宝箱数（観測に相対位置が入る）")
    ap.add_argument("--action-history", type=int, default=6, help="直近何ステップの行動を観測に含めるか（0で無効）")
    ap.add_argument(
        "--no-local-patch",
        action="store_true",
        help="観測から周辺3x3壁＋宝箱ベクトルを外す（ベースライン用）",
    )
    ap.add_argument(
        "--policies",
        type=str,
        default="chase,random,wander,idle",
        help="敵が取りうち方針のプール（カンマ区切り）。各エピソードで敵ごとにランダム選択",
    )
    ap.add_argument(
        "--no-randomize-count",
        action="store_true",
        help="敵数を固定（常に max-enemies 体）",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--save", type=str, default=os.path.join(ROOT, "models", "ppo_gridworld.zip"))
    ap.add_argument("--n-envs", type=int, default=4, help="DummyVecEnv による並列環境数（Windows 向け）")
    ap.add_argument("--eval-freq", type=int, default=10_000)
    args = ap.parse_args()
    if args.min_enemies > args.max_enemies:
        raise SystemExit("--min-enemies は --max-enemies 以下にしてください")

    policies = _parse_policies(args.policies)
    cfg = GridWorldConfig(
        width=args.width,
        height=args.height,
        max_enemies=args.max_enemies,
        min_enemies=args.min_enemies,
        max_steps=args.max_steps,
        randomize_enemy_count=not args.no_randomize_count,
        policies_pool=policies,
        wall_density=args.wall_density,
        mud_density=max(0.0, float(args.mud_density)),
        mud_slip_prob=max(0.0, min(1.0, float(args.mud_slip))),
        n_chests=max(0, int(args.chests)),
        use_local_wall_patch=not args.no_local_patch,
        action_history_len=max(0, int(args.action_history)),
    )

    def _make():
        return Monitor(GridWorldEnv(cfg))

    train_env = DummyVecEnv([_make for _ in range(max(1, args.n_envs))])
    eval_env = DummyVecEnv([_make])

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        seed=args.seed,
        learning_rate=3e-4,
        n_steps=512,
        batch_size=128,
        gamma=0.99,
        ent_coef=0.01,
    )

    save_dir = os.path.dirname(os.path.abspath(args.save))
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=save_dir or ".",
        log_path=os.path.join(save_dir, "eval_logs"),
        eval_freq=max(args.eval_freq // max(1, args.n_envs), 1),
        deterministic=True,
        render=False,
    )

    model.learn(total_timesteps=args.timesteps, callback=eval_cb, progress_bar=False)
    model.save(args.save)
    print(f"保存: {args.save}")


if __name__ == "__main__":
    main()
