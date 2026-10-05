"""学習済み PPO を数エピソード実行し、平均報酬を表示する（ターミナル確認用）。"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from stable_baselines3 import PPO
except ImportError:
    req = os.path.join(ROOT, "requirements-rl.txt")
    exe = sys.executable
    sys.stderr.write(
        "\n[RL] stable-baselines3 が見つかりません。\n"
        f'  "{exe}" -m pip install -r "{req}"\n\n'
    )
    raise SystemExit(1) from None

from rl.gridworld_env import GridWorldConfig, GridWorldEnv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=os.path.join(ROOT, "models", "ppo_gridworld.zip"))
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--width", type=int, default=20)
    ap.add_argument("--height", type=int, default=20)
    ap.add_argument("--max-enemies", type=int, default=6)
    args = ap.parse_args()

    cfg = GridWorldConfig(width=args.width, height=args.height, max_enemies=args.max_enemies)
    env = GridWorldEnv(cfg, render_mode="ansi" if args.render else None)
    model = PPO.load(args.model, env=env)

    rewards = []
    for ep in range(args.episodes):
        obs, _ = env.reset(seed=ep + 7)
        total = 0.0
        done = False
        while not done:
            if args.render:
                frame = env.render()
                if frame:
                    print(frame)
            action, _ = model.predict(obs, deterministic=True)
            obs, r, term, trunc, _ = env.step(int(action))
            total += r
            done = term or trunc
        rewards.append(total)
        if args.render:
            print("--- episode reward", total, "---")

    print(f"平均報酬 ({args.episodes} ep): {sum(rewards) / len(rewards):.3f}")


if __name__ == "__main__":
    main()
