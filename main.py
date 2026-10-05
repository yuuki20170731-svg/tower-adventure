# -*- coding: utf-8 -*-
"""依存パッケージ: pip install pygame  （問題があれば pygame-ce でも可）"""
import array, copy, json, math, os, random, re, tempfile, traceback
import sys
import warnings

# setuptools の pkg_resources 警告が stderr に出ると「起動失敗」に見えることがあるため抑止
warnings.filterwarnings("ignore", category=UserWarning, message=".*pkg_resources.*")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

def _bootstrap_pygame():
    """Cursor など別の Python で開いたとき用: このインタプリタに pygame を入れてから読み込む。"""
    try:
        import pygame  # type: ignore[import-untyped]

        return pygame
    except ImportError:
        import subprocess

        exe = sys.executable
        sys.stderr.write(
            "pygame がこの Python にありません。自動インストールを試します…\n"
            f"  使用インタプリタ: {exe}\n"
        )
        for pkg in ("pygame", "pygame-ce"):
            try:
                subprocess.check_call(
                    [exe, "-m", "pip", "install", "-U", pkg],
                    timeout=600,
                )
            except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
                continue
            try:
                import importlib

                if "pygame" in sys.modules:
                    del sys.modules["pygame"]
                import pygame  # type: ignore[import-untyped]

                sys.stderr.write(f"  → {pkg} のインストールに成功しました。\n\n")
                return pygame
            except ImportError:
                continue
        sys.stderr.write(
            "\n[エラー] pygame を自動インストールできませんでした。\n"
            "  手動で（上記と同じ python で）実行してください:\n"
            f'    "{exe}" -m pip install -U pygame\n'
            "  または:\n"
            f'    "{exe}" -m pip install -U pygame-ce\n'
            "\n  VS Code / Cursor ならコマンドパレット「Python: Select Interpreter」で\n"
            "  インストール先の Python を選び直してください。\n\n"
        )
        raise SystemExit(1)


pygame = _bootstrap_pygame()

try:
    pygame.mixer.pre_init(44100, -16, 2, 512)
except Exception:
    pass
pygame.init()

INTERNAL_W, INTERNAL_H = 1000, 700
WIDTH, HEIGHT = INTERNAL_W, INTERNAL_H

display_window = None
fullscreen_display = False
windowed_size = [INTERNAL_W, INTERNAL_H]

_screen_tries = []
_sc = getattr(pygame, "SCALED", 0)
_flags_base = pygame.RESIZABLE
if _sc:
    _screen_tries.append((INTERNAL_W, INTERNAL_H, _flags_base | _sc))
_screen_tries += [
    (INTERNAL_W, INTERNAL_H, _flags_base),
    (960, 640, _flags_base),
    (800, 600, _flags_base),
]
for w, h, flags in _screen_tries:
    try:
        display_window = pygame.display.set_mode((w, h), flags)
        windowed_size[0], windowed_size[1] = w, h
        break
    except pygame.error:
        continue
if display_window is None:
    raise SystemExit("画面の初期化に失敗しました。グラフィックドライバを確認してください。")

pygame.display.set_caption("RPG — F11 / Alt+Enter でフルスクリーン")

screen = pygame.Surface((INTERNAL_W, INTERNAL_H))

clock = pygame.time.Clock()


def present_frame():
    """論理解像度の surface をウィンドウ／フルスクリーンへ表示。"""
    dw, dh = display_window.get_size()
    if dw == INTERNAL_W and dh == INTERNAL_H:
        display_window.blit(screen, (0, 0))
    else:
        scaled = pygame.transform.smoothscale(screen, (dw, dh))
        display_window.blit(scaled, (0, 0))
    pygame.display.flip()


def set_fullscreen(on):
    """フルスクリーンはデスクトップ解像度に伸縮表示（内部1000×700を拡大）。"""
    global display_window, fullscreen_display
    info = pygame.display.Info()
    want = bool(on)
    try:
        if want:
            display_window = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
        else:
            display_window = pygame.display.set_mode((windowed_size[0], windowed_size[1]), pygame.RESIZABLE)
        fullscreen_display = want
    except pygame.error:
        pass


def toggle_fullscreen():
    set_fullscreen(not fullscreen_display)
TILE = 40
# マップ表示領域（右側にステータスUIを固定して被らないようにする）
VIEWPORT_W = 660
VIEWPORT_H = 620
UI_AREA_X = VIEWPORT_W
UI_PANEL_W = WIDTH - UI_AREA_X

# マップサイズ
W, H = 50, 50
# 8: 通行不可（岩・壁）。0 はエンカウント床。
MAP_WALL_TILE = 8
# マップギミック（いずれも通路として生成時は道が繋がるよう検証）
TILE_FORK = 9  # 旧・分岐マス（未使用。互換のため草道扱い）
TILE_EVENT = 10  # ランダムイベント
TILE_SWITCH = 11  # 扉開放
TILE_DOOR = 12  # 閉じている間は通行不可（スイッチで開く）
TILE_WARP = 13  # ワープ床（ペア）
TILE_ONEWAY = 14  # 一方通行（進入方向のみ）
TILE_CHEST = 15  # フロア宝箱（1回だけ取得）

# フロアごとのギミック状態（セーブ対象外・マップ再生成で初期化）
FLOOR_EXTRA = {
    "fog": False,
    "doors_open": False,
    "warp": {},
    "oneway": {},
    "door_flash_timer": 0,
    "branch_region": {},
    "preview_safe_region": 0,
    "warp_pair_tag": {},
    "map_gen_seed": 0,
}
# マップ再現用マスターシード（変更でダンジョン形が変わる）
MAP_MASTER_SEED = 0xA17F2E9C
MAX_PARTY_MEMBERS = 4


def reset_floor_extra():
    global FLOOR_EXTRA
    FLOOR_EXTRA = {
        "fog": False,
        "doors_open": False,
        "warp": {},
        "oneway": {},
        "door_flash_timer": 0,
        "branch_region": {},
        "preview_safe_region": 0,
        "warp_pair_tag": {},
        "map_gen_seed": 0,
        "chest_looted": set(),
    }


def make_floor_rng(floor_num):
    """フロアごとに固定の乱数列（バランス調整・再現用）。"""
    seed = (MAP_MASTER_SEED ^ (floor_num * 2654435761) ^ (floor_num << 16)) & 0xFFFFFFFF
    return random.Random(seed)


def bfs_distance_map(tiles, start):
    """開始地点からの移動歩数（到達不能は無記録）。"""
    if not (0 <= start[0] < W and 0 <= start[1] < H):
        return {}
    if tile_blocks_path(tiles[start[1]][start[0]]):
        return {}
    dist = {start: 0}
    q = [start]
    qi = 0
    while qi < len(q):
        cx, cy = q[qi]
        qi += 1
        d0 = dist[(cx, cy)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            np = (nx, ny)
            if np in dist:
                continue
            if tile_blocks_path(tiles[ny][nx]):
                continue
            dist[np] = d0 + 1
            q.append(np)
    return dist


def compute_branch_regions(tiles):
    """分岐マスを基点に、二系統の勢力圏（Voronoi）を付与。fork が無ければ {}。"""
    fork_xy = None
    for yy in range(H):
        for xx in range(W):
            if tiles[yy][xx] == TILE_FORK:
                fork_xy = (xx, yy)
                break
        if fork_xy:
            break
    if not fork_xy:
        return {}
    fx, fy = fork_xy
    neigh = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = fx + dx, fy + dy
        if not (0 <= nx < W and 0 <= ny < H):
            continue
        if tile_blocks_path(tiles[ny][nx]):
            continue
        neigh.append((nx, ny))
    if len(neigh) < 2:
        return {}
    a, b = neigh[0], neigh[1]
    da = bfs_distance_map(tiles, a)
    db = bfs_distance_map(tiles, b)
    reg = {}
    for yy in range(H):
        for xx in range(W):
            if tile_blocks_path(tiles[yy][xx]):
                continue
            p = (xx, yy)
            ca = da.get(p, 10**9)
            cb = db.get(p, 10**9)
            if ca < cb:
                reg[p] = 0
            elif cb < ca:
                reg[p] = 1
            else:
                reg[p] = 2
    return reg


def finalize_floor_meta(tiles, stair_pos, rng):
    """分岐色・ワープ番号・検証。"""
    br = compute_branch_regions(tiles)
    FLOOR_EXTRA["branch_region"] = br
    FLOOR_EXTRA["preview_safe_region"] = rng.randint(0, 1)
    FLOOR_EXTRA["map_gen_seed"] = rng.randint(1, 2**31 - 1)
    tags = {}
    pair_idx = 0
    seen_pairs = set()
    for a, b in FLOOR_EXTRA.get("warp", {}).items():
        key = tuple(sorted((a, b)))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        tags[a] = pair_idx
        tags[b] = pair_idx
        pair_idx += 1
    FLOOR_EXTRA["warp_pair_tag"] = tags
    sx, sy = stair_pos
    if not tiles_have_path(tiles, (1, 1), (sx, sy)):
        raise RuntimeError("floor path broken after meta")


def world_player_tile():
    """プレイヤー中心が位置するタイル座標（整数）。自由移動の浮動小数点座標を吸収する。"""
    try:
        cx = float(player.get("x", 0)) + 0.5
        cy = float(player.get("y", 0)) + 0.5
    except (TypeError, ValueError):
        cx, cy = 1.5, 1.5
    return int(math.floor(cx)), int(math.floor(cy))


def explore_mark_cell():
    """現在フロアの踏破マス（ミニマップ用・セーブ可）。"""
    k = str(floor_number)
    d = player.setdefault("_map_explored", {})
    if not isinstance(d.get(k), list):
        d[k] = []
    cx, cy = world_player_tile()
    tag = f"{cx},{cy}"
    lst = d[k]
    if tag not in lst:
        lst.append(tag)


def cell_is_explored(x, y):
    k = str(floor_number)
    lst = player.get("_map_explored", {}).get(k)
    if not lst:
        return False
    return f"{x},{y}" in lst


def world_route_overlay(screen, px, py, cell, mx, my):
    """分岐エリアの色分け（未選択=淡い予告、選択後=意思の強調）。"""
    br = FLOOR_EXTRA.get("branch_region") or {}
    if not br:
        return
    reg = br.get((mx, my))
    if reg is None or reg == 2:
        return
    ps = FLOOR_EXTRA.get("preview_safe_region", 0)
    rm = player.get("route_mode")
    sh = pygame.Surface((cell, cell), pygame.SRCALPHA)
    if rm is None:
        if reg == ps:
            sh.fill((70, 130, 255, 30))
        else:
            sh.fill((255, 150, 70, 24))
    elif rm == "safe":
        if reg == ps:
            sh.fill((80, 190, 255, 52))
        else:
            sh.fill((140, 140, 170, 28))
    else:
        danger_reg = 1 - ps
        if reg == danger_reg:
            sh.fill((255, 70, 90, 56))
        else:
            sh.fill((130, 130, 160, 26))
    screen.blit(sh, (px, py))


def draw_world_minimap(screen, stairs_xy):
    """探索済みミニマップ（タイル種別の色分け）＋階段方位の矢印。"""
    mw, mh = 132, 132
    mx0 = VIEWPORT_W - mw - 6
    my0 = 6
    pygame.draw.rect(screen, (8, 10, 18), (mx0, my0, mw, mh))
    pygame.draw.rect(screen, (120, 135, 175), (mx0, my0, mw, mh), 2)
    scale = min((mw - 4) / W, (mh - 22) / H)
    oxm = mx0 + 2
    oym = my0 + 2
    pxv, pyv = world_player_tile()
    pxf = float(player.get("x", pxv))
    pyf = float(player.get("y", pyv))
    sx, sy = stairs_xy
    for yy in range(H):
        for xx in range(W):
            cx = int(oxm + xx * scale)
            cy = int(oym + yy * scale)
            cw = max(1, int(scale))
            if not cell_is_explored(xx, yy):
                pygame.draw.rect(screen, (22, 24, 34), (cx, cy, cw, cw))
                continue
            tid = tiles[yy][xx]
            if tid == MAP_WALL_TILE:
                col = (42, 46, 58)
            elif tid == 4:
                col = (235, 200, 85)
            elif tid == 2:
                col = (210, 140, 70)
            elif tid == 5:
                col = (90, 200, 240)
            elif tid == TILE_CHEST:
                col = (230, 185, 55)
            elif tid == TILE_EVENT:
                col = (200, 120, 40)
            elif tid == TILE_SWITCH:
                col = (190, 100, 70)
            elif tid == TILE_DOOR:
                col = (120, 118, 150) if FLOOR_EXTRA.get("doors_open") else (70, 72, 92)
            elif tid == TILE_WARP:
                col = (55, 165, 210)
            elif tid == TILE_ONEWAY:
                col = (95, 150, 95)
            elif tid == 1:
                col = (55, 95, 48)
            else:
                col = (58, 92, 62)
            pygame.draw.rect(screen, col, (cx, cy, cw, cw))
            if cw >= 4:
                pygame.draw.rect(screen, (10, 12, 20), (cx, cy, cw, cw), 1)
    plx = int(oxm + (pxf + 0.5) * scale)
    ply = int(oym + (pyf + 0.5) * scale)
    pygame.draw.circle(screen, (20, 22, 30), (plx, ply), max(3, int(scale * 0.55) + 1))
    pygame.draw.circle(screen, (255, 245, 140), (plx, ply), max(2, int(scale * 0.45)), 0)
    dx = sx - pxv
    dy = sy - pyv
    if dx != 0 or dy != 0:
        ln = max(1, (dx * dx + dy * dy) ** 0.5)
        ux = dx / ln * 26
        uy = dy / ln * 26
        pygame.draw.line(
            screen,
            (255, 230, 160),
            (mx0 + mw // 2, my0 + mh // 2 - 6),
            (mx0 + mw // 2 + int(ux), my0 + mh // 2 - 6 + int(uy)),
            3,
        )
        pygame.draw.circle(
            screen,
            (255, 235, 190),
            (mx0 + mw // 2 + int(ux), my0 + mh // 2 - 6 + int(uy)),
            4,
        )
    screen.blit(small.render("ミニマップ", True, (210, 220, 245)), (mx0 + 6, my0 + mh - 19))
    screen.blit(small.render("灰=階 茶=町 金=箱 水=泉", True, (160, 175, 205)), (mx0 + 6, my0 + mh - 36))


def draw_world_door_flash(screen, ox, oy, cell):
    t = FLOOR_EXTRA.get("door_flash_timer", 0)
    if t <= 0:
        return
    for yy in range(H):
        for xx in range(W):
            if tiles[yy][xx] != TILE_DOOR:
                continue
            px = int(ox + xx * cell)
            py = int(oy + yy * cell)
            pygame.draw.rect(screen, (255, 240, 120), (px - 1, py - 1, cell + 2, cell + 2), 2)
    FLOOR_EXTRA["door_flash_timer"] = t - 1


def tile_blocks_path(tid):
    if tid == MAP_WALL_TILE:
        return True
    if tid == TILE_DOOR and not FLOOR_EXTRA.get("doors_open"):
        return True
    return False


def route_tier_adjust():
    rm = player.get("route_mode")
    if rm == "safe":
        return -1
    if rm == "danger":
        return 1
    return 0


def route_encounter_mult():
    rm = player.get("route_mode")
    if rm == "safe":
        return 0.48
    if rm == "danger":
        return 1.55
    return 1.0


def route_loot_mult():
    rm = player.get("route_mode")
    if rm == "safe":
        return 0.62
    if rm == "danger":
        return 1.68
    return 1.0


def vision_radius_world():
    """霧フロアでの視界半径（マンハッタン）。霧でなければ全体表示。"""
    if not FLOOR_EXTRA.get("fog"):
        return 999
    base = 3
    if player.get("torch_turns", 0) > 0:
        return max(base, 10)
    return base


def tick_explore_buff_move():
    """イベント由来の一時強化／弱化を歩行で消化。"""
    if player.get("_event_mod_left", 0) <= 0:
        return
    player["_event_mod_left"] -= 1
    if player["_event_mod_left"] <= 0:
        player["_explore_atk_bonus"] = 0
        player["_explore_curse_def"] = 0


def trigger_explore_random_event():
    """イベントマス：毎回ランダム。深層ほど罠・戦闘が増え黄金・無難が減る。"""
    global mode
    depth = min(1.0, floor_number / 88.0)
    r = random.random()
    t0 = 0.14 + depth * 0.07
    t1 = t0 + 0.14 - depth * 0.035
    t2 = t1 + 0.13 - depth * 0.02
    t3 = t2 + 0.14 - depth * 0.02
    t4 = t3 + 0.13 + depth * 0.02
    t5 = t4 + 0.13 + depth * 0.025
    t6 = t5 + 0.12 + depth * 0.045
    t7 = t6 + 0.11 + depth * 0.06
    if r < t0:
        battle_log = "宝箱だ！…ミミックの牙！" if random.random() < 0.5 else "箱から仕掛けが飛び出した！"
        start_event_enemy_battle("ミミック")
        return
    if r < t1:
        g = 12 + floor_number * 4 + random.randint(0, 25)
        player["gold"] = player.get("gold", 0) + g
        battle_log = f"瓦礫の下から {g} G を拾った。"
        return
    if r < t2:
        it = _random_shop_item_name()
        if it:
            grant_inventory_item(it)
            battle_log = f"謎の行商人が {it} を置き去りにしていた…"
        else:
            battle_log = "旅の荷物が風に押し流された痕跡があるだけだった。"
        return
    if r < t3:
        m = random.choice(player["party"][:MAX_PARTY_MEMBERS])
        if m and not m.get("absent"):
            m["hp"] = min(m["max_hp"], m["hp"] + 8 + floor_number // 4)
            personality_apply({"compassion": 1})
            battle_log = f"{m['name']}が休んだ。仲間のHPが少し回復。"
        else:
            battle_log = "誰もいない…空っぽの野営跡。"
        return
    if r < t4:
        player["_explore_atk_bonus"] = 3 + floor_number // 25
        player["_explore_curse_def"] = 0
        player["_event_mod_left"] = 28
        battle_log = "古い祭壇が祝福を残している。（攻撃力一時UP）"
        return
    if r < t5:
        player["_explore_curse_def"] = min(8, 3 + floor_number // 30)
        player["_explore_atk_bonus"] = 0
        player["_event_mod_left"] = 22
        battle_log = "不吉な刻印が足元を這う…（守備一時ダウン）"
        return
    if r < t6:
        dmg = max(1, int(player["max_hp"] * (0.06 + random.random() * 0.06)))
        player["hp"] = max(1, player["hp"] - dmg)
        battle_log = f"罠だ！毒針が刺さり HP が {dmg} 減った。"
        return
    if r < t7 and random.random() < (0.42 + depth * 0.28):
        battle_log = "物音がして敵が襲いかかった！"
        start_random_battle()
        return
    battle_log = "風だけが通り過ぎ、何もなかった。"


def _random_shop_item_name():
    cat = shop_catalog()
    if not cat:
        return None
    pool = [it["name"] for it in cat if it.get("name") and it.get("price", 99) <= 80 + floor_number * 3]
    return random.choice(pool) if pool else None


def start_event_enemy_battle(enemy_key):
    """イベント指定の1体戦闘。"""
    global enemies
    if enemy_key not in enemy_catalog:
        enemy_key = "スライム"
    d = enemy_catalog.get(enemy_key, {})
    wave = [make_spawn_enemy_dict(enemy_key, d, 0)]
    pos = (-1, -1)
    player["_battle_wave"] = wave
    player["_battle_wave_idx"] = 0
    enemies[pos] = {k: wave[0][k] for k in wave[0]}
    start_battle(pos)


def scatter_floor_gimmicks(tiles, stair_pos, floor_num, rng):
    """道が繋がることを確認しながらギミックタイルを配置（rng で再現可能）。バイオームで量・種を少し変える。"""
    reset_floor_extra()
    sx, sy = stair_pos
    bio = min(9, max(0, (floor_num - 1) // 10))
    # 霧: 水辺・雪系はやや多め
    fog_bias = 0.06 if bio in (1, 2, 6) else 0.0
    FLOOR_EXTRA["fog"] = (floor_num % 8 == 0) or (rng.random() < 0.24 + fog_bias)

    def grass_cells():
        g = []
        for yy in range(H):
            for xx in range(W):
                if tiles[yy][xx] != 0:
                    continue
                if (xx, yy) in {(1, 1), (sx, sy)}:
                    continue
                g.append((xx, yy))
        return g

    def path_ok():
        return tiles_have_path(tiles, (1, 1), (sx, sy))

    grass = grass_cells()
    rng.shuffle(grass)
    n_ev = max(2, min(7, rng.randint(2 + bio // 5, 4 + bio // 3)))
    placed_ev = 0
    for p in grass:
        if placed_ev >= n_ev:
            break
        x, y = p
        tiles[y][x] = TILE_EVENT
        if path_ok():
            placed_ev += 1
        else:
            tiles[y][x] = 0

    grass = grass_cells()
    rng.shuffle(grass)
    warp_mul = 1.14 if bio in (1, 6, 8) else 1.0
    if len(grass) >= 2 and rng.random() < min(0.93, (0.70 + min(0.22, bio * 0.026)) * warp_mul):
        placed_warp = False
        for i in range(min(len(grass) - 1, 40)):
            a, b = grass[i], grass[i + 1]
            ax, ay = a
            bx, by = b
            oa, ob = tiles[ay][ax], tiles[by][bx]
            tiles[ay][ax] = TILE_WARP
            tiles[by][bx] = TILE_WARP
            if path_ok():
                FLOOR_EXTRA["warp"][a] = b
                FLOOR_EXTRA["warp"][b] = a
                placed_warp = True
                break
            tiles[ay][ax] = oa
            tiles[by][bx] = ob
        if not placed_warp:
            FLOOR_EXTRA["warp"] = {}
    else:
        FLOOR_EXTRA["warp"] = {}

    placed_one = False
    for _ in range(140):
        cx = rng.randint(2, W - 3)
        cy = rng.randint(2, H - 3)
        if tiles[cy][cx] != 0:
            continue
        dx, dy = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        px, py = cx - dx, cy - dy
        if not (0 <= px < W and 0 <= py < H):
            continue
        if tile_blocks_path(tiles[py][px]):
            continue
        old = tiles[cy][cx]
        tiles[cy][cx] = TILE_ONEWAY
        FLOOR_EXTRA["oneway"][(cx, cy)] = (dx, dy)
        if path_ok():
            placed_one = True
            break
        tiles[cy][cx] = old
        del FLOOR_EXTRA["oneway"][(cx, cy)]
    if not placed_one:
        FLOOR_EXTRA["oneway"] = {}

    door_p = min(0.42, 0.24 + (bio % 4) * 0.045)
    if rng.random() < door_p:
        gc = grass_cells()
        rng.shuffle(gc)
        for door_pos in gc[:90]:
            gx, gy = door_pos
            if tiles[gy][gx] != 0:
                continue
            tiles[gy][gx] = TILE_DOOR
            if not path_ok():
                tiles[gy][gx] = 0
                continue
            switches_tried = grass_cells()
            rng.shuffle(switches_tried)
            ok_sw = False
            for sw in switches_tried:
                sx2, sy2 = sw
                if sw == door_pos or tiles[sy2][sx2] != 0:
                    continue
                tiles[sy2][sx2] = TILE_SWITCH
                if path_ok():
                    ok_sw = True
                    break
                tiles[sy2][sx2] = 0
            if ok_sw:
                break
            tiles[gy][gx] = 0

    # 本編フロアの宝箱は最大4個。バイオームが進むほど多めになりやすい。
    _chest_ub = min(4, 2 + (bio // 3))
    n_chest = rng.randint(0, _chest_ub)
    for _ in range(n_chest):
        gc2 = grass_cells()
        rng.shuffle(gc2)
        for cx, cy in gc2[:200]:
            if tiles[cy][cx] != 0:
                continue
            tiles[cy][cx] = TILE_CHEST
            if path_ok():
                break
            tiles[cy][cx] = 0


# 10 階ごとのエンカウント敵プール（catalog に無い名前は無視）
BIOME_ENEMY_POOLS = [
    ["草原バッタ", "ミツバチ", "スライム", "ゴブリン", "ウルフ"],
    ["クラゲ", "ピラニア", "スライム", "グール"],
    ["砂ワーム", "ゴブリン", "バット", "グール"],
    ["コウモリ", "バット", "スケルトン", "グール"],
    ["ウルフ", "ミミック", "ゴブリン", "オーク"],
    ["ウィッチ", "スケルトン", "ナイト", "グール"],
    ["ゴーレム", "ナイト", "スケルトン", "オーク"],
    ["ドラゴン", "ウィッチ", "ゴーレム", "ナイト"],
    ["ドラゴン", "ナイト", "ゴーレム", "ミミック"],
    ["ドラゴン", "ナイト", "ゴーレム", "ウィッチ"],
]

BIOME_LABELS = [
    "草原ゾーン",
    "海岸・浅瀬",
    "乾いた砂丘",
    "洞窟の暗がり",
    "魔の森",
    "山岳・峡谷",
    "雪原・氷穴",
    "溶岩地帯",
    "奈落の影",
    "深淵の境界",
]
# ドット風表示用: 背景 / 帯(文字用) / 壁
BIOME_BG = [
    (20, 32, 24),
    (16, 28, 48),
    (36, 30, 18),
    (18, 16, 32),
    (12, 28, 16),
    (22, 24, 30),
    (24, 32, 48),
    (40, 18, 10),
    (12, 10, 22),
    (8, 6, 18),
]
BIOME_TEXT_BAND = [
    (12, 20, 16, 232),
    (8, 16, 32, 236),
    (24, 18, 8, 234),
    (10, 8, 20, 236),
    (6, 16, 8, 234),
    (12, 14, 20, 234),
    (14, 20, 32, 236),
    (32, 10, 4, 236),
    (6, 4, 14, 238),
    (4, 2, 10, 240),
]
BIOME_WALL = [
    (28, 48, 32),
    (18, 40, 58),
    (58, 48, 32),
    (40, 36, 58),
    (20, 48, 24),
    (50, 50, 58),
    (80, 88, 110),
    (70, 22, 8),
    (50, 20, 60),
    (30, 8, 40),
]
BIOME_FLOOR_TINT = [
    (40, 90, 50),
    (30, 80, 120),
    (100, 85, 50),
    (60, 50, 90),
    (25, 80, 35),
    (70, 75, 80),
    (90, 110, 130),
    (120, 40, 20),
    (80, 20, 100),
    (20, 10, 50),
]


def _safe_sysfont(size):
    for name in ("meiryo", "msgothic", "msmincho", "yugothic", "arial"):
        try:
            f = pygame.font.SysFont(name, size)
            if f and f.get_height() > 0:
                return f
        except (pygame.error, OSError, TypeError, ValueError):
            continue
    return pygame.font.Font(None, size)


font = _safe_sysfont(19)
small = _safe_sysfont(15)
big = _safe_sysfont(42)

# PyInstaller で配布した場合は、同梱リソースとユーザーが書き込むセーブ先を分ける。
# 通常の Python 実行時は従来どおりプロジェクト直下を使用する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
USER_DATA_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
DATA_DIR = os.path.join(RESOURCE_DIR, "data")
ASSETS_DIR = os.path.join(RESOURCE_DIR, "assets")
AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
# BGM は pygame.mixer.music の1ストリームのみ（Sound ループと二重にならない）
_snd_ui = None
_snd_victory = None
# 勝利ファンファーレは BGM と重ねず、再生終了後にフィールド／物語BGMへ戻す。
_victory_channel = None
_current_bgm = None
battle_music_started = False
# 戦闘開始フレームで sync_music_to_mode 側に必ず戦闘BGMを載せる（マップ曲の取り残し防止）
_battle_bgm_pending = False
# ストリーミングBGMを掛ける画面のみ。これらの mode が変わるたびに必ず全停止してから次曲へ
_MODES_WITH_STREAMING_BGM = frozenset({"world", "battle", "title", "story"})
_prev_streaming_bgm_mode = None
# 戦闘系ファイル名（ワールドBGM復帰判定用）
BATTLE_BGM_IDS = frozenset({"battle.ogg", "battle_encounter.ogg", "battle_epic.ogg", "boss_chamber.ogg"})
# マップ用: 冒険感のある曲をこの順で探す（無ければバイオーム別 world_XX）
FIELD_BGM_CANDIDATES = (
    "world_adventure.ogg",
    "map_adventure.ogg",
    "field_journey.ogg",
    "world_explore.ogg",
)
FIELD_BGM_LOGICAL_IDS = frozenset(FIELD_BGM_CANDIDATES)
STORY_BGM_CANDIDATES = (
    "story_theme.ogg",
    "story_scene.ogg",
    "event_theme.ogg",
    "title.ogg",
)
_proc_se_cache = {}
title_stars = None
bless_next_phys_mult = 1.0
battle_arcane_followup = False


def install_crash_logger():
    prev = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            crash_path = os.path.join(DATA_DIR, "last_crash.log")
            with open(crash_path, "w", encoding="utf-8") as f:
                f.write("RPG Crash Log\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except OSError:
            pass
        if prev:
            prev(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def load_audio_assets():
    global _snd_ui, _snd_victory
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init(44100, -16, 2, 512)
        except pygame.error:
            return
    try:
        pygame.mixer.set_num_channels(32)
        pygame.mixer.set_reserved(1)
    except pygame.error:
        pass
    p_ui = os.path.join(AUDIO_DIR, "ui_click.wav")
    if os.path.isfile(p_ui):
        try:
            _snd_ui = pygame.mixer.Sound(p_ui)
            _snd_ui.set_volume(0.42)
        except pygame.error:
            _snd_ui = None
    p_v = os.path.join(AUDIO_DIR, "victory.ogg")
    if os.path.isfile(p_v):
        try:
            _snd_victory = pygame.mixer.Sound(p_v)
            _snd_victory.set_volume(0.62)
        except pygame.error:
            _snd_victory = None


def _make_proc_tone(freq0, freq1, ms, vol):
    sr = 22050
    n = max(1, int(sr * ms / 1000))
    buf = array.array("h")
    for i in range(n):
        env = 1.0 - (i / max(1, n - 1))
        f = freq0 + (freq1 - freq0) * (i / max(1, n - 1))
        s = int(32767 * vol * env * env * math.sin(2 * math.pi * f * i / sr))
        buf.append(max(-32767, min(32767, s)))
    try:
        return pygame.mixer.Sound(buffer=buf.tobytes())
    except pygame.error:
        return None


def _get_proc_se(key):
    if key in _proc_se_cache:
        return _proc_se_cache[key]
    recipes = {
        "hit": (280, 160, 58, 0.2),
        "crit": (200, 55, 115, 0.26),
        "fire": (300, 520, 130, 0.22),
        "thunder": (95, 38, 95, 0.28),
        "heal": (480, 720, 95, 0.18),
        "magic": (210, 380, 88, 0.2),
        "step": (420, 280, 32, 0.1),
    }
    if key not in recipes:
        return None
    snd = _make_proc_tone(*recipes[key])
    _proc_se_cache[key] = snd
    return snd


def play_battle_se(kind):
    """戦闘用の短い手続きSE（ファイルが無くても鳴る）。"""
    if not player.get("opt_se_on", True) or not pygame.mixer.get_init():
        return
    snd = _get_proc_se(kind)
    if not snd:
        return
    try:
        g = max(0.0, min(1.0, float(player.get("opt_se_vol", 1.0))))
        ch = pygame.mixer.find_channel(False)
        if ch:
            ch.set_volume(g)
            ch.play(snd)
    except pygame.error:
        pass


battle_vfx = None
battle_action_seq_cursor_ms = 0
battle_timeline_text = ""
battle_damage_popups = []
battle_crit_cutin = {"timer": 0, "name": "", "title": "CRITICAL", "accent": (165, 28, 46)}


def trigger_battle_vfx(kind, frames=18):
    global battle_vfx
    if not kind or frames <= 0:
        return
    battle_vfx = (kind, int(frames))


def draw_battle_vfx_layer(screen, shx):
    if battle_vfx is None:
        return
    kind, t = battle_vfx
    surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    prng = random.Random(101 + hash(kind) % 100000 + t * 31)
    alpha = min(240, 10 + t * 12)
    enemy_band_x = WIDTH // 2 + 120 + shx // 2
    enemy_band_y = HEIGHT // 2 - 30
    if kind in ("fire", "inferno"):
        n = 32 if kind == "inferno" else 18
        for _ in range(n):
            x = prng.randint(40, WIDTH - 40) + shx
            y = prng.randint(60, HEIGHT - 140)
            r = prng.randint(4, 26)
            c = (255, prng.randint(50, 180), prng.randint(0, 70), min(230, alpha + prng.randint(-40, 40)))
            pygame.draw.circle(surf, c, (x, y), r)
        for _ in range(8 if kind == "inferno" else 4):
            x0 = prng.randint(0, WIDTH) + shx
            pygame.draw.line(
                surf,
                (255, 210, 130, min(200, alpha)),
                (x0, HEIGHT - 20),
                (x0 + prng.randint(-50, 50), prng.randint(40, 220)),
                3,
            )
    elif kind == "fire_wave":
        # ファイア: 敵側を横切る一文字の炎波
        band_y = enemy_band_y + prng.randint(-12, 12)
        for i in range(28):
            x = WIDTH // 4 + i * 28 + shx
            r = 10 + (i % 4) * 5 + (24 - min(24, t)) * 2
            col = (255, prng.randint(120, 200), prng.randint(40, 90), min(220, alpha))
            pygame.draw.circle(surf, col, (x, band_y + prng.randint(-12, 12)), r)
        pygame.draw.line(surf, (255, 240, 160, min(220, alpha)),
                         (140 + shx, band_y), (WIDTH - 60 + shx, band_y), 4)
    elif kind == "fire_pillar":
        # フレイム: 敵位置から立ち昇る火柱
        for col_i in range(3):
            base_x = enemy_band_x - 60 + col_i * 60
            top_y = enemy_band_y - 160 - (24 - min(24, t)) * 6
            for yy in range(top_y, enemy_band_y + 40, 18):
                r = 18 + prng.randint(-6, 10)
                c = (
                    255,
                    prng.randint(120, 220),
                    prng.randint(20, 80),
                    min(220, alpha),
                )
                pygame.draw.circle(surf, c, (base_x + prng.randint(-10, 10), yy), r)
    elif kind == "meteor_strike":
        # メテオ: 上空から流星が落下、着弾でホワイトアウト＋衝撃波
        progress = 1.0 - (t / 32.0) if t > 0 else 0
        progress = max(0.0, min(1.0, progress))
        tail_count = 3
        for j in range(tail_count):
            f = progress + j * 0.04
            mx = int(WIDTH * (0.18 + f * 0.6)) + shx
            my = int(20 + f * (enemy_band_y - 20))
            if my > enemy_band_y:
                continue
            pygame.draw.line(surf, (255, 220, 160, min(230, alpha)),
                             (mx - int(120 * (1 - f)), my - int(120 * (1 - f))),
                             (mx, my), 6)
            pygame.draw.circle(surf, (255, 230, 200, min(230, alpha)), (mx, my), 22 - j * 6)
            pygame.draw.circle(surf, (255, 140, 60, min(220, alpha)), (mx, my), 14 - j * 4)
        if progress >= 0.7:
            cx, cy = enemy_band_x, enemy_band_y
            shock = (1.0 - (1.0 - progress) / 0.3) if progress < 1.0 else 1.0
            for k in range(4):
                rr = int(40 + shock * 130 + k * 22)
                pygame.draw.circle(surf, (255, 230, 180, max(20, int(220 - k * 50 - shock * 80))),
                                   (cx, cy), rr, 4)
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((255, 250, 220, int(60 + shock * 90)))
            surf.blit(flash, (0, 0))
    elif kind == "thunder":
        for _ in range(6):
            x = prng.randint(80, WIDTH - 80) + shx
            pts = [(x, 30)]
            yi = 30
            while yi < HEIGHT - 120:
                yi += prng.randint(26, 44)
                x += prng.randint(-70, 70)
                pts.append((x, yi))
            pygame.draw.lines(surf, (245, 250, 255, min(235, alpha)), False, pts, 4)
            pygame.draw.lines(surf, (110, 190, 255, min(150, alpha // 2 + 30)), False, pts, 2)
    elif kind == "thunder_bolt":
        # サンダーボルト: 太い一閃の縦雷
        tx = enemy_band_x + prng.randint(-30, 30)
        pts = [(tx + prng.randint(-12, 12), y) for y in range(20, HEIGHT - 80, 22)]
        pygame.draw.lines(surf, (255, 255, 220, min(240, alpha)), False, pts, 9)
        pygame.draw.lines(surf, (170, 220, 255, min(220, alpha)), False, pts, 4)
        # 着雷点のグロウ
        pygame.draw.circle(surf, (220, 240, 255, min(220, alpha)), (tx, enemy_band_y + 40), 36)
        pygame.draw.circle(surf, (255, 255, 220, min(220, alpha)), (tx, enemy_band_y + 40), 18)
    elif kind == "thunder_chain":
        # 雷脈: 連鎖する細い稲妻が複数本
        chain_count = 6
        for ci in range(chain_count):
            cx = WIDTH // 3 + ci * 80 + shx + prng.randint(-30, 30)
            pts = [(cx, 30)]
            yi = 30
            while yi < HEIGHT - 120:
                yi += prng.randint(20, 36)
                cx += prng.randint(-44, 44)
                pts.append((cx, yi))
            pygame.draw.lines(surf, (220, 240, 255, min(230, alpha)), False, pts, 3)
            pygame.draw.lines(surf, (140, 200, 255, min(180, alpha)), False, pts, 1)
        # 雷球の連なり
        for k in range(8):
            px = WIDTH // 4 + k * 80 + shx
            py = enemy_band_y + prng.randint(-30, 30)
            pygame.draw.circle(surf, (200, 230, 255, min(220, alpha)), (px, py), 9)
    elif kind == "heal":
        for _ in range(24):
            x = prng.randint(100, WIDTH - 100) + shx
            y = HEIGHT - 60 - prng.randint(0, min(380, t * 22))
            pygame.draw.circle(surf, (110, 255, 190, min(210, alpha)), (x, y), prng.randint(3, 11))
    elif kind == "heal_aurora":
        # メガヒール: オーロラ＋光球
        for j in range(3):
            band = pygame.Surface((WIDTH, 32), pygame.SRCALPHA)
            band.fill((110, 255, 190, max(20, 80 - j * 20)))
            screen.blit(band, (0, 220 + j * 28))
        for _ in range(28):
            x = prng.randint(40, WIDTH - 40) + shx
            y = prng.randint(140, HEIGHT - 100)
            pygame.draw.circle(surf, (200, 255, 220, min(220, alpha)), (x, y), prng.randint(4, 12))
    elif kind == "venom":
        for _ in range(22):
            x = prng.randint(160, WIDTH - 100) + shx
            y = prng.randint(100, HEIGHT - 180)
            pygame.draw.circle(surf, (70, 255, 120, min(190, alpha)), (x, y), prng.randint(2, 9))
    elif kind == "venom_storm":
        # ポイズンストーム: 渦巻く毒霧
        cx, cy = enemy_band_x, enemy_band_y
        for k in range(80):
            ang = (k * 0.4 + t * 0.12) % (2 * math.pi)
            rr = 30 + (k % 16) * 8
            x = int(cx + math.cos(ang) * rr)
            y = int(cy + math.sin(ang) * rr * 0.55)
            pygame.draw.circle(surf, (90, 220, 110, min(210, alpha)), (x, y), 6)
        # 毒の核
        pygame.draw.circle(surf, (70, 200, 90, min(220, alpha)), (cx, cy), 22)
    elif kind == "cursed_threads":
        # 瘴糸: 緑の触手糸が複数伸びる
        for k in range(7):
            x0 = 200 + shx
            y0 = HEIGHT // 2 + prng.randint(-40, 40)
            x1 = enemy_band_x + prng.randint(-40, 40)
            y1 = enemy_band_y + prng.randint(-30, 30)
            mid_x = (x0 + x1) // 2 + prng.randint(-50, 50)
            mid_y = (y0 + y1) // 2 + prng.randint(-30, 30)
            pts = [(x0, y0), (mid_x, mid_y), (x1, y1)]
            pygame.draw.lines(surf, (100, 220, 110, min(220, alpha)), False, pts, 3)
            pygame.draw.circle(surf, (60, 180, 90, min(220, alpha)), (x1, y1), 8)
    elif kind == "arcane":
        for _ in range(16):
            x = prng.randint(60, WIDTH - 60) + shx
            y = prng.randint(90, HEIGHT - 140)
            pygame.draw.circle(surf, (190, 100, 255, min(200, alpha)), (x, y), prng.randint(12, 40), 2)
    elif kind == "chaos_storm":
        # カオスボルト: 紫光球＋雷
        for _ in range(20):
            x = prng.randint(60, WIDTH - 60) + shx
            y = prng.randint(90, HEIGHT - 140)
            pygame.draw.circle(surf, (200, 90, 255, min(220, alpha)), (x, y), prng.randint(8, 22))
        # 紫の稲妻
        for _ in range(3):
            x = prng.randint(120, WIDTH - 120) + shx
            pts = [(x, 30)]
            yi = 30
            while yi < HEIGHT - 120:
                yi += prng.randint(22, 38)
                x += prng.randint(-50, 50)
                pts.append((x, yi))
            pygame.draw.lines(surf, (240, 200, 255, min(230, alpha)), False, pts, 4)
            pygame.draw.lines(surf, (140, 80, 220, min(180, alpha)), False, pts, 2)
    elif kind == "apocalypse":
        # 終焉の星: 黒い穴 + 星 + 全画面振動
        cx, cy = WIDTH // 2 + shx // 2, HEIGHT // 2 - 30
        # 黒い渦
        for r in range(120, 20, -16):
            col = (max(0, 30 - r // 6), 0, max(0, 60 - r // 4), min(230, alpha))
            pygame.draw.circle(surf, col, (cx, cy), r)
        # オレンジ→白の核
        pygame.draw.circle(surf, (255, 120, 80, min(230, alpha)), (cx, cy), 38)
        pygame.draw.circle(surf, (255, 245, 220, min(230, alpha)), (cx, cy), 18)
        # 星屑
        for _ in range(40):
            ang = prng.random() * 2 * math.pi
            rr = 80 + prng.randint(0, 200)
            x = int(cx + math.cos(ang) * rr)
            y = int(cy + math.sin(ang) * rr)
            pygame.draw.circle(surf, (255, 230, 200, min(220, alpha)), (x, y), prng.randint(2, 4))
        # ホワイトアウト
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 240, 220, min(120, alpha // 2)))
        surf.blit(flash, (0, 0))
    elif kind == "phys":
        pygame.draw.line(
            surf,
            (255, 255, 255, min(210, alpha)),
            (100 + shx, HEIGHT // 2 - 30),
            (WIDTH - 100 + shx, HEIGHT // 2 - 10),
            3,
        )
    elif kind == "phys_strong":
        for _ in range(10):
            pygame.draw.line(
                surf,
                (255, 235, 200, min(220, alpha)),
                (prng.randint(0, WIDTH), prng.randint(100, HEIGHT // 2 + 60)),
                (prng.randint(0, WIDTH), prng.randint(HEIGHT // 2, HEIGHT - 80)),
                2,
            )
        # 強打時の衝撃リング
        cx, cy = WIDTH // 2 + shx // 2, HEIGHT // 2 - 24
        for k in range(3):
            rr = 30 + k * 26 + (24 - min(24, t)) * 4
            pygame.draw.circle(surf, (255, 245, 210, max(40, alpha - k * 55)), (cx, cy), rr, 3)
    elif kind == "cross_slash":
        # ブレイブスラッシュ: 十字斬り
        cx, cy = enemy_band_x, enemy_band_y
        progress = 1.0 - (t / 22.0) if t > 0 else 0
        progress = max(0.0, min(1.0, progress))
        ln_len = int(160 + progress * 80)
        pygame.draw.line(surf, (255, 250, 220, min(230, alpha)),
                         (cx - ln_len, cy - ln_len // 2),
                         (cx + ln_len, cy + ln_len // 2), 6)
        pygame.draw.line(surf, (255, 100, 100, min(230, alpha)),
                         (cx - ln_len, cy + ln_len // 2),
                         (cx + ln_len, cy - ln_len // 2), 6)
        pygame.draw.circle(surf, (255, 235, 200, min(220, alpha)), (cx, cy), 22)
    elif kind == "sword_dance":
        # ソードダンス: 多数の斬撃線
        cx, cy = enemy_band_x, enemy_band_y
        for k in range(8):
            ang = (k / 8.0) * 2 * math.pi + t * 0.18
            x1 = cx + int(math.cos(ang) * 30)
            y1 = cy + int(math.sin(ang) * 30)
            x2 = cx + int(math.cos(ang) * 160)
            y2 = cy + int(math.sin(ang) * 160)
            pygame.draw.line(surf, (255, 240, 220, min(230, alpha)), (x1, y1), (x2, y2), 4)
            pygame.draw.line(surf, (255, 180, 180, min(200, alpha)), (x1, y1), (x2, y2), 2)
        pygame.draw.circle(surf, (255, 250, 230, min(230, alpha)), (cx, cy), 16)
    elif kind == "berserk_burst":
        # 戦鬼解放: 赤いオーラ＋強い斬撃
        cx, cy = enemy_band_x, enemy_band_y
        for k in range(5):
            rr = 40 + k * 24 + (28 - min(28, t)) * 5
            col = (255, 60, 50, max(30, 200 - k * 45))
            pygame.draw.circle(surf, col, (cx, cy), rr, 5)
        # 鋭い斬撃線
        for k in range(6):
            ang = (k / 6.0) * math.pi + 0.2
            x1 = cx - int(math.cos(ang) * 200)
            y1 = cy - int(math.sin(ang) * 200)
            x2 = cx + int(math.cos(ang) * 200)
            y2 = cy + int(math.sin(ang) * 200)
            pygame.draw.line(surf, (255, 220, 200, min(230, alpha)), (x1, y1), (x2, y2), 5)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((220, 30, 30, max(0, alpha // 3)))
        surf.blit(flash, (0, 0))
    elif kind == "holy_ray":
        # ホーリーライト: 上から白光線
        beam_x = enemy_band_x
        bw = 64
        beam = pygame.Surface((bw, HEIGHT), pygame.SRCALPHA)
        for j in range(bw):
            a = int(220 * (1.0 - abs(j - bw / 2) / (bw / 2)))
            pygame.draw.line(beam, (255, 245, 200, min(220, a)), (j, 0), (j, HEIGHT), 1)
        surf.blit(beam, (beam_x - bw // 2, 0))
        for _ in range(20):
            x = beam_x + prng.randint(-30, 30)
            y = prng.randint(40, HEIGHT - 80)
            pygame.draw.circle(surf, (255, 250, 220, min(220, alpha)), (x, y), prng.randint(3, 9))
    elif kind == "bell_wave":
        # 守護の鐘: 味方側に金色の同心円
        cx, cy = 200 + shx, HEIGHT // 2 - 20
        for k in range(5):
            rr = 30 + k * 36 + (20 - min(20, t)) * 4
            pygame.draw.circle(surf, (255, 220, 120, max(30, 220 - k * 40)), (cx, cy), rr, 4)
        for _ in range(20):
            x = prng.randint(60, 380) + shx
            y = prng.randint(180, HEIGHT - 80)
            pygame.draw.circle(surf, (255, 235, 160, min(220, alpha)), (x, y), prng.randint(2, 6))
    elif kind == "sanctuary_dome":
        # 聖域結界: 半透明ドーム＋光粒
        cx = 200 + shx
        cy = HEIGHT // 2 + 30
        dome_r = 220
        dome = pygame.Surface((dome_r * 2, dome_r), pygame.SRCALPHA)
        pygame.draw.ellipse(dome, (200, 240, 255, min(110, alpha)), dome.get_rect())
        pygame.draw.ellipse(dome, (255, 250, 220, min(200, alpha)), dome.get_rect(), 3)
        screen.blit(dome, (cx - dome_r, cy - dome_r // 2))
        for _ in range(34):
            ang = prng.random() * math.pi
            rr = prng.randint(40, dome_r - 10)
            x = int(cx + math.cos(ang) * rr)
            y = int(cy - math.sin(ang) * rr * 0.55)
            pygame.draw.circle(surf, (255, 250, 220, min(220, alpha)), (x, y), prng.randint(2, 5))
    elif kind == "triple_arrow":
        # トリプルアロー: 3本の矢が敵に飛ぶ
        progress = 1.0 - (t / 18.0) if t > 0 else 0
        progress = max(0.0, min(1.0, progress))
        for j in range(3):
            y_off = -32 + j * 32
            ax = int(200 + (enemy_band_x - 200) * progress) + shx
            ay = enemy_band_y + y_off
            pygame.draw.line(surf, (220, 235, 255, min(230, alpha)),
                             (ax - 22, ay), (ax + 12, ay), 4)
            pygame.draw.polygon(surf, (240, 240, 200, min(230, alpha)),
                                [(ax + 12, ay - 5), (ax + 22, ay), (ax + 12, ay + 5)])
    elif kind == "pierce_shot":
        # 貫通狙撃: 1本の白光線（残光）
        ay = enemy_band_y + prng.randint(-8, 8)
        pygame.draw.line(surf, (255, 250, 220, min(240, alpha)),
                         (140 + shx, ay), (WIDTH - 40 + shx, ay), 9)
        pygame.draw.line(surf, (200, 230, 255, min(220, alpha)),
                         (140 + shx, ay + 2), (WIDTH - 40 + shx, ay + 2), 3)
        # 矢の先端
        pygame.draw.polygon(surf, (255, 240, 220, min(230, alpha)),
                            [(WIDTH - 30 + shx, ay - 14),
                             (WIDTH - 10 + shx, ay),
                             (WIDTH - 30 + shx, ay + 14)])
    elif kind == "arrow_storm":
        # 嵐の矢: 多数の矢の雨
        for _ in range(40):
            x = prng.randint(WIDTH // 3, WIDTH) + shx
            y = prng.randint(80, HEIGHT - 80)
            length = prng.randint(32, 56)
            pygame.draw.line(surf, (220, 240, 255, min(230, alpha)),
                             (x - length, y - length // 2),
                             (x, y), 3)
            pygame.draw.polygon(surf, (255, 240, 200, min(230, alpha)),
                                [(x - 4, y - 6), (x + 6, y), (x - 4, y + 6)])
    elif kind == "boss_finisher":
        # ボス用の超派手演出（トレーラー映え）
        for _ in range(18):
            x0 = prng.randint(0, WIDTH)
            y0 = prng.randint(20, HEIGHT - 20)
            x1 = x0 + prng.randint(-200, 200)
            y1 = y0 + prng.randint(-140, 140)
            pygame.draw.line(surf, (255, 120, 80, min(220, alpha)), (x0, y0), (x1, y1), 4)
            pygame.draw.line(surf, (255, 240, 180, min(180, alpha)), (x0, y0), (x1, y1), 1)
        core = pygame.Surface((260, 260), pygame.SRCALPHA)
        pygame.draw.circle(core, (255, 120, 80, min(180, alpha)), (130, 130), 96)
        pygame.draw.circle(core, (255, 245, 200, min(170, alpha)), (130, 130), 52)
        screen.blit(core, (WIDTH // 2 - 130 + shx // 2, HEIGHT // 2 - 160))
    screen.blit(surf, (0, 0))


def battle_begin_action_sequence():
    global battle_action_seq_cursor_ms
    battle_action_seq_cursor_ms = 0


def battle_next_action_delay_ms(step_ms=260):
    global battle_action_seq_cursor_ms
    d = battle_action_seq_cursor_ms
    battle_action_seq_cursor_ms += max(0, int(step_ms))
    return d


def battle_push_action_fx(actor_name, kind, side="ally", slot=0, target_slot=0, delay_ms=0):
    battle_action_fx.append(
        {
            "actor": str(actor_name),
            "kind": str(kind),
            "side": str(side),
            "slot": int(slot),
            "target_slot": int(target_slot),
            "ttl": 30,
            "max_ttl": 30,
            "start_ms": pygame.time.get_ticks() + max(0, int(delay_ms)),
        }
    )
    if len(battle_action_fx) > 28:
        del battle_action_fx[0]


def draw_battle_action_fx(screen, shx):
    if not battle_action_fx:
        return
    left_x = 56 + shx
    enemy_base_x = 332 + shx
    panel_inner = 250
    nbe = max(1, len(battle_enemies))
    gap = 8 if nbe > 1 else 0
    slot_w = (panel_inner - gap * max(0, nbe - 1)) // nbe
    now_ms = pygame.time.get_ticks()
    next_fx = []
    active_fx = None
    for fx in battle_action_fx:
        if now_ms < int(fx.get("start_ms", 0)):
            next_fx.append(fx)
            continue
        ttl = int(fx.get("ttl", 0))
        if ttl <= 0:
            continue
        mt = max(1, int(fx.get("max_ttl", 18)))
        p = 1.0 - (ttl / mt)
        side = fx.get("side", "ally")
        slot = int(fx.get("slot", 0))
        target_slot = int(fx.get("target_slot", 0))
        actor = fx.get("actor", "?")
        kind = fx.get("kind", "atk")
        if active_fx is None:
            active_fx = fx
        if side == "ally":
            sy = 82 if slot < 0 else 172 + slot * 88
            sx = left_x + int(32 + p * 145)
            tx = enemy_base_x + max(0, min(target_slot, nbe - 1)) * (slot_w + gap) + slot_w // 2
            ty = 142
            if kind == "atk":
                pygame.draw.line(screen, (255, 240, 170), (sx, sy), (tx, ty), 7)
                pygame.draw.line(screen, (255, 130, 130), (sx - 10, sy + 8), (tx - 10, ty + 8), 3)
                # 斬撃波（弧）
                ar = 36 + int(p * 24)
                pygame.draw.arc(screen, (255, 250, 210), (tx - ar, ty - ar, ar * 2, ar * 2), 0.4, 2.4, 3)
            elif kind == "spell":
                bx = int(sx + (tx - sx) * p)
                by = int(sy + (ty - sy) * p)
                pygame.draw.circle(screen, (120, 220, 255), (bx, by), 11)
                pygame.draw.circle(screen, (220, 250, 255), (bx, by), 5)
            elif kind == "def":
                sh = pygame.Surface((96, 24), pygame.SRCALPHA)
                sh.fill((110, 170, 255, 90))
                screen.blit(sh, (left_x - 4, sy - 10))
                pygame.draw.rect(screen, (170, 220, 255), (left_x - 4, sy - 10, 96, 24), 2)
            screen.blit(font.render(actor, True, (255, 245, 210)), (sx - 12, sy - 22))
        else:
            ex = enemy_base_x + max(0, min(slot, nbe - 1)) * (slot_w + gap) + slot_w // 2
            ey = 132
            if target_slot < 0:
                tx, ty = 88 + shx, 78
            else:
                tx, ty = 84 + shx, 172 + target_slot * 88
            if kind == "atk":
                pygame.draw.line(screen, (255, 110, 110), (ex, ey), (tx, ty), 7)
                pygame.draw.circle(screen, (255, 190, 190), (tx, ty), 8)
            elif kind == "spell":
                bx = int(ex + (tx - ex) * p)
                by = int(ey + (ty - ey) * p)
                pygame.draw.circle(screen, (245, 120, 255), (bx, by), 11)
                pygame.draw.circle(screen, (255, 220, 255), (bx, by), 5)
            screen.blit(font.render(actor, True, (255, 200, 200)), (ex - 18, ey - 28))
        fx["ttl"] = ttl - 1
        if fx["ttl"] > 0:
            next_fx.append(fx)
    if active_fx is not None:
        act = active_fx.get("actor", "?")
        kind = active_fx.get("kind", "")
        kl = {"atk": "攻撃", "spell": "呪文", "def": "防御"}.get(kind, kind)
        banner = pygame.Surface((420, 40), pygame.SRCALPHA)
        banner.fill((8, 10, 24, 188))
        screen.blit(banner, (290, 8))
        pygame.draw.rect(screen, (255, 218, 140), (290, 8, 420, 40), 2)
        screen.blit(font.render(f"{act} の {kl}!", True, (255, 245, 205)), (306, 18))
        # 画面上部のスピードライン
        st = pygame.Surface((WIDTH, 64), pygame.SRCALPHA)
        for i in range(0, WIDTH, 26):
            x = (i + int(pygame.time.get_ticks() * 0.6)) % (WIDTH + 80) - 40
            pygame.draw.line(st, (255, 236, 170, 42), (x, 0), (x - 30, 64), 2)
        screen.blit(st, (0, 0))
    battle_action_fx[:] = next_fx


def draw_battle_showcase_bg(screen, shx):
    """戦闘画面の見栄え強化: 動くオーロラとライト帯。"""
    t = pygame.time.get_ticks() * 0.001
    bg = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for i in range(6):
        x = int((math.sin(t * 0.7 + i) * 0.5 + 0.5) * WIDTH)
        y = 120 + i * 78
        w = 220 + (i % 3) * 80
        h = 54
        col = (70 + i * 18, 90 + i * 14, 180 + i * 8, 34)
        pygame.draw.ellipse(bg, col, (x - w // 2 + shx // 2, y, w, h))
    for k in range(4):
        lx = int((t * (120 + k * 38)) % (WIDTH + 300)) - 150
        pygame.draw.line(bg, (255, 235, 180, 24), (lx, 0), (lx - 220, HEIGHT), 2)
    screen.blit(bg, (0, 0))


def battle_add_damage_popup(label, x, y, col=(255, 235, 200), ttl=34):
    battle_damage_popups.append(
        {
            "label": str(label),
            "x": int(x),
            "y": int(y),
            "ttl": int(ttl),
            "max_ttl": int(ttl),
            "col": tuple(col),
        }
    )
    if len(battle_damage_popups) > 42:
        del battle_damage_popups[0]


def draw_battle_damage_popups(screen):
    if not battle_damage_popups:
        return
    keep = []
    for p in battle_damage_popups:
        ttl = int(p.get("ttl", 0))
        if ttl <= 0:
            continue
        mt = max(1, int(p.get("max_ttl", 30)))
        pr = 1.0 - ttl / mt
        y = int(p["y"] - pr * 30)
        alpha = max(20, min(255, int(255 * (ttl / mt))))
        c = p.get("col", (255, 235, 200))
        surf = font.render(p["label"], True, c)
        if alpha < 255:
            surf = surf.copy()
            surf.set_alpha(alpha)
        screen.blit(surf, (p["x"], y))
        p["ttl"] = ttl - 1
        if p["ttl"] > 0:
            keep.append(p)
    battle_damage_popups[:] = keep


def battle_trigger_crit_cutin(name, title="CRITICAL", accent=(165, 28, 46), timer=20):
    battle_crit_cutin["timer"] = int(timer)
    battle_crit_cutin["name"] = str(name)
    battle_crit_cutin["title"] = str(title)
    battle_crit_cutin["accent"] = tuple(accent)


def battle_trigger_skill_cutin(caster, skill_name):
    battle_trigger_crit_cutin(
        caster,
        title=str(skill_name).upper(),
        accent=(48, 38, 140),
        timer=18,
    )


def draw_battle_crit_cutin(screen):
    t = int(battle_crit_cutin.get("timer", 0))
    if t <= 0:
        return
    acc = battle_crit_cutin.get("accent", (165, 28, 46))
    band = pygame.Surface((WIDTH, 96), pygame.SRCALPHA)
    band.fill((acc[0], acc[1], acc[2], 188))
    screen.blit(band, (0, 250))
    pygame.draw.rect(screen, (255, 240, 190), (0, 250, WIDTH, 96), 3)
    nm = battle_crit_cutin.get("name", "勇者")
    # キャラシルエット風カットイン
    sil = pygame.Surface((340, 120), pygame.SRCALPHA)
    pygame.draw.polygon(sil, (18, 16, 22, 220), [(10, 110), (120, 24), (190, 42), (280, 12), (336, 110)])
    pygame.draw.polygon(sil, (255, 210, 120, 130), [(10, 110), (120, 24), (190, 42), (280, 12), (336, 110)], 2)
    screen.blit(sil, (40, 236))
    ttl = battle_crit_cutin.get("title", "CRITICAL")
    screen.blit(big.render(ttl[:18], True, (255, 245, 210)), (260, 266))
    screen.blit(font.render(f"{nm} の一撃!", True, (255, 228, 188)), (420, 318))
    battle_crit_cutin["timer"] = t - 1


def play_ui_sound():
    if not player.get("opt_se_on", True):
        return
    if _snd_ui:
        try:
            _snd_ui.play()
        except pygame.error:
            pass


def music_volume_scaled(base_volume):
    """プレイヤー設定 opt_bgm_vol（0〜1）を乗算したBGM音量（専用チャンネル）。"""
    try:
        m = max(0.0, min(1.0, float(player.get("opt_bgm_vol", 1.0))))
        return max(0.0, min(1.0, float(base_volume) * m))
    except (TypeError, ValueError):
        return max(0.0, min(1.0, float(base_volume)))


def refresh_streaming_bgm_volume():
    """再生中の曲の音量だけ opt_bgm_vol を反映（[ ] キー用）。"""
    if not pygame.mixer.get_init() or not _current_bgm:
        return
    fn = _current_bgm
    if fn == "boss_chamber.ogg":
        base = 0.56
    elif fn == "battle_epic.ogg":
        base = 0.55
    elif fn in BATTLE_BGM_IDS:
        base = 0.52
    elif fn.startswith("world_") or fn in FIELD_BGM_LOGICAL_IDS:
        base = 0.46
    elif fn == "title.ogg":
        base = 0.52
    else:
        base = 0.5
    try:
        pygame.mixer.music.set_volume(music_volume_scaled(base))
    except pygame.error:
        pass


def apply_sound_effect_settings():
    """opt_se_on / opt_se_vol に応じて効果音の音量を更新。"""
    global _snd_ui, _snd_victory
    try:
        m = max(0.0, min(1.0, float(player.get("opt_se_vol", 1.0))))
        on = bool(player.get("opt_se_on", True))
        gain = m if on else 0.0
        if _snd_ui:
            _snd_ui.set_volume(0.42 * gain)
        if _snd_victory:
            _snd_victory.set_volume(0.62 * gain)
        for _k, snd in list(_proc_se_cache.items()):
            if snd:
                try:
                    b = {"hit": 0.2, "crit": 0.26, "fire": 0.22, "thunder": 0.28, "heal": 0.18, "magic": 0.2}.get(_k, 0.2)
                    snd.set_volume(b * gain)
                except pygame.error:
                    pass
    except (TypeError, ValueError, pygame.error):
        pass


def victory_fanfare_playing():
    """勝利ファンファーレの間は、次のBGMを開始しない。"""
    if _victory_channel is None:
        return False
    try:
        return bool(_victory_channel.get_busy())
    except pygame.error:
        return False


def stop_victory_fanfare():
    global _victory_channel
    if _victory_channel is not None:
        try:
            _victory_channel.stop()
        except pygame.error:
            pass
    _victory_channel = None


def music_silence_immediate():
    """BGM を即停止（1曲につき遷移のたびに呼ぶ想定）。stop→unload を複数回＋pump で取り残しを潰す。"""
    global _current_bgm
    if not pygame.mixer.get_init():
        _current_bgm = None
        return
    mu = pygame.mixer.music
    for _ in range(2):
        try:
            if hasattr(mu, "fadeout"):
                mu.fadeout(0)
        except (pygame.error, TypeError, ValueError):
            pass
        try:
            mu.stop()
        except pygame.error:
            pass
        try:
            if hasattr(mu, "unload"):
                mu.unload()
        except pygame.error:
            pass
        for _p in range(4):
            try:
                pygame.event.pump()
            except pygame.error:
                break
    _current_bgm = None


def _music_stop_before_play_only():
    """load 済みのストリームで play 直前にだけ呼ぶ（unload はしない）。"""
    if not pygame.mixer.get_init():
        return
    try:
        pygame.mixer.music.stop()
    except pygame.error:
        pass


def _win_short_path_if_any(path):
    """Windows で全角などを含むパスを SDL_mixer に渡すと失敗することがあるため 8.3 短名を試す。"""
    if os.name != "nt" or not path or not os.path.isfile(path):
        return None
    try:
        import ctypes

        ab = os.path.normpath(os.path.abspath(path))
        buf = ctypes.create_unicode_buffer(4096)
        n = ctypes.windll.kernel32.GetShortPathNameW(ab, buf, len(buf))
        if n and buf.value and buf.value.lower() != ab.lower():
            return buf.value
    except (OSError, AttributeError, TypeError, ValueError):
        pass
    return None


def music_load_from_disk(path):
    """pygame.mixer.music.load のラッパー（非 ASCII パスで失敗したら短パスを試す）。"""
    if not path or not os.path.isfile(path):
        return False
    ap = os.path.normpath(os.path.abspath(path))
    order = [ap]
    sp = _win_short_path_if_any(ap)
    if sp:
        order.append(sp)
    seen = set()
    for try_path in order:
        if try_path in seen:
            continue
        seen.add(try_path)
        try:
            mu = pygame.mixer.music
            try:
                mu.stop()
            except pygame.error:
                pass
            try:
                if hasattr(mu, "unload"):
                    mu.unload()
            except pygame.error:
                pass
            mu.load(try_path)
            return True
        except pygame.error:
            continue
    return False


def music_start_battle_bgm(filename=None, volume=0.52, fade_ms=480):
    """戦闘BGM。かっこいい曲を優先: battle_epic → battle_encounter → battle。ボスは boss_chamber を最優先。"""
    global _current_bgm
    _ = fade_ms
    if not pygame.mixer.get_init():
        return
    stop_victory_fanfare()
    music_silence_immediate()
    if filename == "boss_chamber.ogg":
        candidates = ["boss_chamber.ogg", "battle_epic.ogg", "battle_encounter.ogg", "battle.ogg"]
    elif filename:
        candidates = [filename, "battle_epic.ogg", "battle_encounter.ogg", "battle.ogg"]
    else:
        candidates = ["battle_epic.ogg", "battle_encounter.ogg", "battle.ogg"]
    for fn in candidates:
        path = os.path.join(AUDIO_DIR, fn)
        if not os.path.isfile(path):
            continue
        try:
            if not music_load_from_disk(path):
                continue
            vol = volume
            if fn == "battle_epic.ogg":
                vol = max(volume, 0.54)
            pygame.mixer.music.set_volume(music_volume_scaled(vol))
            _music_stop_before_play_only()
            pygame.mixer.music.play(-1)
            _current_bgm = fn
            return
        except pygame.error:
            continue
    _current_bgm = None


def _field_bgm_resolve_path_and_logical(biome_index):
    """冒険系ファイル名を優先し、無ければ world_{tier}.ogg。"""
    for fn in FIELD_BGM_CANDIDATES:
        path = os.path.join(AUDIO_DIR, fn)
        if os.path.isfile(path):
            return path, fn
    tier_fn = f"world_{biome_index:02d}.ogg"
    tier_path = os.path.join(AUDIO_DIR, tier_fn)
    if os.path.isfile(tier_path):
        return tier_path, tier_fn
    return None, None


def music_play_field_bgm(biome_index):
    """マップBGM。冒険テーマ（複数ファイル名のいずれか）を優先、無ければバイオーム別 world_XX。"""
    global _current_bgm
    if not pygame.mixer.get_init():
        return
    path, logical = _field_bgm_resolve_path_and_logical(biome_index)
    if not path:
        return
    music_silence_immediate()
    try:
        if not music_load_from_disk(path):
            _current_bgm = None
            return
        pygame.mixer.music.set_volume(music_volume_scaled(0.46))
        _music_stop_before_play_only()
        pygame.mixer.music.play(-1)
        _current_bgm = logical
    except pygame.error:
        _current_bgm = None


def ensure_field_music_if_world():
    """マップ中のみ。戦闘曲から戻るときは必ず差し替え。同一ファイルなら再 play しない。"""
    if mode != "world":
        return
    tier = min(9, max(0, (floor_number - 1) // 10))
    _path, target = _field_bgm_resolve_path_and_logical(tier)
    if target is None:
        if _current_bgm in BATTLE_BGM_IDS:
            music_silence_immediate()
        return
    if _current_bgm in BATTLE_BGM_IDS:
        music_play_field_bgm(tier)
        return
    if _current_bgm == target:
        try:
            if pygame.mixer.music.get_busy():
                return
        except pygame.error:
            return
        music_play_field_bgm(tier)
        return
    music_play_field_bgm(tier)


def ensure_battle_music_if_battle():
    """戦闘BGM: 遷入時は pending で1回だけ開始。以降は戦闘曲IDに含まれないときだけ復旧する。
    以前はボス戦で boss_chamber が無いと battle_epic に落ちた後も毎フレーム music_start しており、
    重ね掛け・増幅の原因になっていた。"""
    global _battle_bgm_pending, battle_music_started
    if mode != "battle":
        return
    if not pygame.mixer.get_init():
        return
    want_boss = bool(battle_enemies) and any(e.get("type") == "boss" for e in battle_enemies)
    if _battle_bgm_pending:
        _battle_bgm_pending = False
        if want_boss:
            music_start_battle_bgm("boss_chamber.ogg", volume=0.56, fade_ms=720)
        else:
            music_start_battle_bgm()
        battle_music_started = True
        return
    if _current_bgm not in BATTLE_BGM_IDS:
        if want_boss:
            music_start_battle_bgm("boss_chamber.ogg", volume=0.56, fade_ms=720)
        else:
            music_start_battle_bgm()
        battle_music_started = True


def sync_music_to_mode():
    """BGM を mode に一本化。ストリーミングBGM対象の画面が切り替わるたびに必ず全停止してから各曲へ。"""
    global _battle_bgm_pending, _prev_streaming_bgm_mode
    if mode in _MODES_WITH_STREAMING_BGM:
        if _prev_streaming_bgm_mode is not None and _prev_streaming_bgm_mode != mode:
            music_silence_immediate()
        _prev_streaming_bgm_mode = mode
    if mode != "battle":
        _battle_bgm_pending = False
    # win() が流す勝利曲を最後まで聞かせてから、次の画面のBGMを始める。
    # これにより勝利曲とフィールド曲／物語曲が二重に鳴らない。
    if mode in ("world", "story") and victory_fanfare_playing():
        return
    if mode == "world":
        ensure_field_music_if_world()
    elif mode == "battle":
        ensure_battle_music_if_battle()
    elif mode == "title":
        music_ensure_title()
    elif mode == "story":
        music_ensure_story()


def music_ensure_title():
    """タイトル曲。sync_music_to_mode が毎フレーム呼ぶため「同一ファイルなら触らない」のが必須。"""
    global _current_bgm
    if not pygame.mixer.get_init():
        return
    path = os.path.join(AUDIO_DIR, "title.ogg")
    if not os.path.isfile(path):
        return
    if _current_bgm == "title.ogg":
        return
    music_silence_immediate()
    try:
        if not music_load_from_disk(path):
            _current_bgm = None
            return
        pygame.mixer.music.set_volume(music_volume_scaled(0.52))
        _music_stop_before_play_only()
        pygame.mixer.music.play(-1)
        _current_bgm = "title.ogg"
    except pygame.error:
        _current_bgm = None


def music_ensure_story():
    """ストーリー用BGM。候補を順に探して同一曲なら再生し直さない。"""
    global _current_bgm
    if not pygame.mixer.get_init():
        return
    target = None
    path = None
    for fn in STORY_BGM_CANDIDATES:
        p = os.path.join(AUDIO_DIR, fn)
        if os.path.isfile(p):
            target = fn
            path = p
            break
    if target is None or path is None:
        return
    if _current_bgm == target:
        return
    music_silence_immediate()
    try:
        if not music_load_from_disk(path):
            _current_bgm = None
            return
        pygame.mixer.music.set_volume(music_volume_scaled(0.5))
        _music_stop_before_play_only()
        pygame.mixer.music.play(-1)
        _current_bgm = target
    except pygame.error:
        _current_bgm = None


def ensure_title_stars():
    global title_stars
    if title_stars is None:
        title_stars = [
            (random.randint(0, max(1, WIDTH - 1)), random.randint(0, max(1, HEIGHT - 1)), random.uniform(0, math.tau))
            for _ in range(130)
        ]


install_crash_logger()
load_audio_assets()

SAVE_PATH = os.path.join(USER_DATA_DIR, "save.json")
# オートセーブ: 階段通過時 + この間隔（ミリ秒）で無通知セーブ
AUTOSAVE_INTERVAL_MS = 120000
_last_periodic_autosave_ms = 0  # メインループ開始直後に get_ticks で上書き
# BGM は pygame.mixer.music の1ストリームのみ（SE は Sound / チャンネル）。
BATTLE_RL_SAVE_PATH = os.path.join(DATA_DIR, "enemy_rl_q.json")

_RL_BATTLE_Q_MODULE = None
try:
    import rl.battle_q_agent as _rl_battle_q_agent

    _RL_BATTLE_Q_MODULE = _rl_battle_q_agent
    encode_state = _rl_battle_q_agent.encode_state
    pick_enemy_target_from_action = _rl_battle_q_agent.pick_enemy_target_from_action
except ImportError:
    encode_state = None
    pick_enemy_target_from_action = None

enemy_rl_agent = None


def _ensure_enemy_rl_agent():
    """Q学習エージェントは初回の単体戦まで遅延（起動を軽くする）。"""
    global enemy_rl_agent
    if enemy_rl_agent is not None:
        return enemy_rl_agent
    if _RL_BATTLE_Q_MODULE is None:
        return None
    enemy_rl_agent = _RL_BATTLE_Q_MODULE.BattleQAgent(save_path=BATTLE_RL_SAVE_PATH)
    return enemy_rl_agent

PERSONALITY_AXES = ("morality", "greed", "bravery", "compassion", "honor", "cunning")
# 仲間の「好み」× プレイヤー性格の内積がこれ未満で離脱（イベント離脱を主にするためほぼ発動しない）
COMPANION_LEAVE_AFFINITY = -200
MEMBER_AFFINITY_WEIGHTS = {
    "戦士": {"bravery": 1.0, "honor": 0.75, "morality": 0.35, "greed": -0.55, "cunning": -0.2},
    "僧侶": {"morality": 1.05, "compassion": 1.0, "greed": -1.15, "cunning": -0.45, "bravery": 0.15},
    "弓使い": {"cunning": 0.65, "bravery": 0.55, "honor": 0.25, "compassion": 0.2, "greed": -0.35},
    "魔法使い": {"cunning": 0.9, "compassion": 0.35, "morality": 0.25, "bravery": -0.15, "greed": 0.1},
}

battle_ally_atk_cnt = 0
battle_ally_def_cnt = 0
battle_ally_sp_cnt = 0
enemy_rl_deferred = None

town_mode = "chat"
bond_crisis_state = None
pending_bond_check = False
battle_ui_shake = 0
crit_slow_timer = 0
slash_timer = 0
battle_action_fx = []

TOWN_ETHICS_OPTIONS = [
    {"text": "無償で手を差し伸べる", "deltas": {"morality": 3, "compassion": 2, "greed": -1}},
    {"text": "見返りを求める", "deltas": {"greed": 2, "cunning": 1, "compassion": -1}},
    {"text": "他人事だと突き放す", "deltas": {"morality": -3, "compassion": -2, "cunning": 1}},
]

# 町NPC（会話の末路が性格・ストーリーフラグ・絆イベントにつながりうる）
TOWN_NPC_SCRIPTS = [
    {
        "name": "宿屋の主人",
        "lines": [
            "「ようこそ。ここは旅人の足を休める場所さ」",
            "「…だが噂話には気をつけな。仲間の絆まで揺さぶる話もある」",
        ],
        "choices": [
            {"text": "暗い噂を根掘り葉掘り聞く", "deltas": {"cunning": 2, "morality": -2, "compassion": -1}, "try_bond": True},
            {"text": "礼を言って部屋だけ借りる", "deltas": {"honor": 1, "morality": 1}},
            {"text": "冗談で誤魔化す", "deltas": {"bravery": 1, "cunning": 1}},
        ],
    },
    {
        "name": "旅の学者",
        "lines": [
            "「君たちの歩みは、地図の外側に線を引いている」",
            "「道徳の天秤が傾けば…仲間は去り、別の物語が始まる。覚悟はあるかい？」",
        ],
        "choices": [
            {"text": "正しさを選び続けると誓う", "deltas": {"morality": 2, "honor": 2, "greed": -1}},
            {"text": "結果だけが正義だと吐き捨てる", "deltas": {"greed": 2, "morality": -3, "compassion": -2}, "try_bond": True},
            {"text": "黙って立ち去る", "deltas": {"bravery": -1, "cunning": 1}},
        ],
    },
    {
        "name": "衛兵",
        "lines": [
            "「町の秩序は俺たちが守る。だが…お前たちの仲間内の火種までは止められん」",
            "「誰かが裏切りの匂いをまとったら、門前で揉めることになるぞ」",
        ],
        "choices": [
            {"text": "仲間を信じると言い切る", "deltas": {"honor": 2, "bravery": 1}},
            {"text": "金なら解決すると吐く", "deltas": {"greed": 3, "morality": -2, "honor": -2}, "try_bond": True},
            {"text": "衛兵に酒を差し出す（社交）", "deltas": {"cunning": 2, "compassion": 1}},
        ],
    },
    {
        "name": "路地の子ども",
        "lines": [
            "「ねえ、お兄ちゃんお姉ちゃん。仲良し？」",
            "「嘘つきの大人は…みんな、どこかへ行っちゃうんだよ」",
        ],
        "choices": [
            {"text": "優しく抱きしめる約束をする", "deltas": {"compassion": 3, "morality": 1}},
            {"text": "余計な口出しをするなと怒鳴る", "deltas": {"morality": -2, "compassion": -3}, "try_bond": True},
            {"text": "小銭をそっと握らせる", "deltas": {"compassion": 1, "greed": -1}},
        ],
    },
]


def town_apply_npc_choice(npc_id, choice_idx):
    global battle_log, mode, town_mode, town_npc_id, town_npc_line
    scr = TOWN_NPC_SCRIPTS[npc_id]
    opts = scr.get("choices") or []
    if choice_idx < 0 or choice_idx >= len(opts):
        return
    ch = opts[choice_idx]
    if ch.get("deltas"):
        personality_apply(ch["deltas"])
    if ch.get("try_bond"):
        try_start_bond_crisis()
        if mode == "companion_crisis":
            battle_log = "町での言葉が、仲間の心にひびを入れた…"
            return
    battle_log = "町での会話が、少し心に残った。"
    town_mode = "hub"
    town_npc_id = -1
    town_npc_line = 0


def tiles_have_path(tiles, start, goal, oneway=None):
    """壁・閉じた扉以外を踏んで start→goal へ到達可能か。oneway は (nx,ny)→許容入射ベクトル。"""
    if tile_blocks_path(tiles[start[1]][start[0]]) or tile_blocks_path(tiles[goal[1]][goal[0]]):
        return False
    ow = oneway if oneway is not None else FLOOR_EXTRA.get("oneway") or {}
    q = [start]
    seen = {start}
    qi = 0
    while qi < len(q):
        cx, cy = q[qi]
        qi += 1
        if (cx, cy) == goal:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            np = (nx, ny)
            if np in seen:
                continue
            if tile_blocks_path(tiles[ny][nx]):
                continue
            req = ow.get(np)
            if req and (nx - cx, ny - cy) != req:
                continue
            seen.add(np)
            q.append(np)
    return False


def generate_map(floor_num=1):
    # 0:草(エンカウント), 1:敵ゾーン, 2:町, 3:予備, 4:階段, 5:泉, 8:壁
    rng = make_floor_rng(floor_num)
    tier = min(9, max(0, (floor_num - 1) // 10))
    base_wall = 0.10 + tier * 0.018
    if floor_num % 10 == 0:
        base_wall *= 0.68
    elif floor_num % 10 == 9:
        base_wall *= 0.82

    min_stair_dist = max(12, (W + H) // 6)

    for _attempt in range(140):
        tiles = [[0 for _ in range(W)] for _ in range(H)]
        for try_place in range(80):
            sx = rng.randint(5, W - 6)
            sy = rng.randint(5, H - 6)
            if abs(sx - 1) + abs(sy - 1) < min_stair_dist:
                continue
            break
        else:
            sx, sy = W - 6, H - 6
        tiles[sy][sx] = 4
        stairs_pos = (sx, sy)
        tiles[1][1] = 0

        town_pos = None
        if rng.random() < 0.045:
            for _ in range(500):
                tx, ty = rng.randint(1, W - 2), rng.randint(1, H - 2)
                if (tx, ty) != (sx, sy) and (tx, ty) != (1, 1) and tiles[ty][tx] == 0:
                    tiles[ty][tx] = 2
                    town_pos = (tx, ty)
                    break

        n_springs = rng.choices([0, 1, 2], weights=[0.42, 0.48, 0.10])[0]
        for _ in range(n_springs):
            for _att in range(900):
                fx, fy = rng.randint(1, W - 2), rng.randint(1, H - 2)
                if tiles[fy][fx] == 0 and (fx, fy) != (1, 1):
                    tiles[fy][fx] = 5
                    break

        wall_p = min(0.34, base_wall + rng.uniform(-0.022, 0.022))
        reserved = {(1, 1), (sx, sy)}
        if town_pos:
            reserved.add(town_pos)
        for y in range(H):
            for x in range(W):
                if (x, y) in reserved:
                    continue
                if tiles[y][x] != 0:
                    continue
                if rng.random() < wall_p:
                    tiles[y][x] = MAP_WALL_TILE

        tiles[1][1] = 0
        if tiles[sy][sx] != 4:
            tiles[sy][sx] = 4
        if not tiles_have_path(tiles, (1, 1), (sx, sy)):
            continue
        scatter_floor_gimmicks(tiles, (sx, sy), floor_num, rng)
        try:
            finalize_floor_meta(tiles, (sx, sy), rng)
        except RuntimeError:
            continue
        return tiles, town_pos, stairs_pos

    tiles = [[0 for _ in range(W)] for _ in range(H)]
    sx, sy = W - 8, H - 8
    tiles[sy][sx] = 4
    tiles[1][1] = 0
    rng_fb = make_floor_rng(floor_num + 90421)
    scatter_floor_gimmicks(tiles, (sx, sy), floor_num, rng_fb)
    try:
        finalize_floor_meta(tiles, (sx, sy), rng_fb)
    except RuntimeError:
        pass
    return tiles, None, (sx, sy)


def shuffle_memory_map():
    """記憶の街：死亡後に草地・森タイルの一部を入れ替えて迷路の印象を変える"""
    global tiles
    sx, sy = STAIRS_POS
    blocked = {(sx, sy)}
    if TOWN_POS:
        blocked.add(TOWN_POS)
    pts = []
    for y in range(H):
        for x in range(W):
            if (x, y) in blocked:
                continue
            if tiles[y][x] in (0, 1):
                pts.append((x, y))
    if len(pts) < 6:
        return
    random.shuffle(pts)
    n = max(10, len(pts) // 10)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[len(pts) - 1 - i]
        tiles[y1][x1], tiles[y2][x2] = tiles[y2][x2], tiles[y1][x1]


def memory_death_recovery():
    global mode, enemy, enemy_pos, battle_log, battle_plan_units, battle_plan_focus, battle_pending, spell_menu_target, spell_menu_cursor, battle_music_started, battle_enemies, _battle_bgm_pending
    player["_battle_wave"] = None
    player["_battle_wave_idx"] = 0
    battle_enemies = []
    music_silence_immediate()
    battle_music_started = False
    _battle_bgm_pending = False
    advance_world_tactics()
    enemy_rl_finish_battle(True)
    shuffle_memory_map()
    player["hp"] = max(1, player["max_hp"] // 4)
    player["mp"] = max(0, min(player["mp"], max(1, player["max_mp"] // 2)))
    battle_log = "記憶が歪んだ…かすかな鼓動が戻ってきた。"
    if enemy_pos is not None and enemy_pos in enemies:
        del enemies[enemy_pos]
    enemy = None
    enemy_pos = None
    battle_plan_units = []
    battle_plan_focus = 0
    battle_pending = {}
    spell_menu_target = None
    spell_menu_cursor = 0
    mode = "world"


def apply_floor_buff_choice(choice_idx):
    """10階踏破後の初回のみ（11,21,…階到達時）永久バフを1つ選択"""
    global mode, pending_floor_buff_tier
    tier = pending_floor_buff_tier
    if tier is None:
        mode = "world"
        return
    picked = player.setdefault("floor_buff_picked", [])
    if tier in picked:
        pending_floor_buff_tier = None
        mode = "world"
        return
    picked.append(tier)
    if choice_idx == 0:
        player["perm_bonus_atk"] = player.get("perm_bonus_atk", 0) + 2 + tier
        battle_log = f"永久: 攻撃力が強まった（+{2 + tier}）"
    elif choice_idx == 1:
        player["perm_bonus_def"] = player.get("perm_bonus_def", 0) + 2 + tier
        battle_log = f"永久: 守りが強まった（+{2 + tier}）"
    else:
        dh = 15 + tier * 5
        dm = 8 + tier * 2
        player["max_hp"] += dh
        player["hp"] += dh
        player["max_mp"] += dm
        player["mp"] += dm
        battle_log = f"永久: 生命力と魔力が増した（HP+{dh} MP+{dm}）"
    pending_floor_buff_tier = None
    mode = "world"


# 初期化
floor_number = 1
random_encounter_cooldown = 0
tiles, TOWN_POS, STAIRS_POS = generate_map(floor_number)
party_action_choices = ["攻撃", "防御", "呪文"]
battle_log = ""
pending_synergy_notes = []
town_dialog_index = 0
town_dialogs = [
    "町人: ようこそ旅人さん。",
    "町人: 装備を整えてから森へ向かうといいよ。",
    "町人: 仲間の行動は戦闘前に決めておくと楽だよ。",
]
town_npc_id = -1
town_npc_line = 0
player_defending = False
battle_action_target_index = 0
selected_shop_item_index = -1
pending_floor_move = False
last_story_choice = "none"
story_data = {}
story_nodes = {}
story_current_id = None
flash_timer = 0
enemy_shake_timer = 0
walk_frame = 0
world_facing = (0, 1)
story_anim_node = None
story_anim_start_ms = 0
encounter_flash = 0
inventory_selected = 0
boss_intro_timer = 0
# 同一ターン内で全員の行動を入力してから ENTER で実行
battle_plan_units = []
battle_plan_focus = 0
battle_pending = {}
spell_menu_target = None
spell_menu_cursor = 0
item_icons_by_name = {}
selection_event_done = False
event_choice_selected = 0
pending_event = None
quest_defs = [
    {"id": "q_boss10", "title": "試練の始まり", "target_floor": 10, "done": False},
    {"id": "q_boss50", "title": "深層への挑戦", "target_floor": 50, "done": False},
    {"id": "q_boss100", "title": "深淵王討伐", "target_floor": 100, "done": False},
]
# 主人公専用呪文チェーン（仲間・敵と名前が被らない）
PLAYER_SKILL_CHAIN = ["ファイア", "フレイム", "メガヒール", "サンダーボルト", "ポイズンストーム", "雷脈"]
# 仲間ごとの固有呪文（重複なし・レベルで順に習得）
MEMBER_SKILL_CHAINS = {
    "戦士": ["ブレイブスラッシュ", "ソードダンス", "戦鬼解放"],
    "僧侶": ["瘴糸", "ホーリーライト", "守護の鐘", "聖域結界"],
    "弓使い": ["トリプルアロー", "貫通狙撃", "嵐の矢"],
    "魔法使い": ["メテオ", "カオスボルト", "終焉の星"],
}
PARTY_FACE_FILES = {
    "戦士": "ally_warrior.png",
    "僧侶": "ally_priest.png",
    "弓使い": "ally_archer.png",
    "魔法使い": "ally_mage.png",
}
RELICS = [
    {"name": "紅蓮の紋章", "effect": "atk+4"},
    {"name": "蒼天の護符", "effect": "hp+30"},
    {"name": "賢者の涙", "effect": "mp+20"},
]
MEMBER_SPELL_MP = {
    "瘴糸": 8,
    "ブレイブスラッシュ": 6,
    "ソードダンス": 12,
    "戦鬼解放": 22,
    "ホーリーライト": 10,
    "守護の鐘": 14,
    "聖域結界": 24,
    "トリプルアロー": 8,
    "貫通狙撃": 14,
    "嵐の矢": 20,
    "メテオ": 18,
    "カオスボルト": 22,
    "終焉の星": 32,
}
HEAL_MEMBER_SPELLS = frozenset({"ホーリーライト", "守護の鐘", "聖域結界"})
HEAL_PLAYER_SKILLS = frozenset({"ヒール", "メガヒール"})
ALLY_DAMAGE_MEMBER_SPELLS = frozenset(set(MEMBER_SPELL_MP) - set(HEAL_MEMBER_SPELLS))
MEMBER_BASE_MP = {"戦士": 24, "僧侶": 48, "弓使い": 30, "魔法使い": 52}
pending_floor_buff_tier = None
shop_scroll = 0
SHOP_PAGE = 9


def load_json(filename, default):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_image(filename):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.scale(img, (TILE, TILE))
    except pygame.error:
        return None


def load_portrait(filename, size=36):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.scale(img, (size, size))
    except pygame.error:
        return None


def load_icon_file(filename, size=38):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, (size, size))
    except pygame.error:
        return None


def blit_item_icon(surface, item_key, x, y, size=34):
    ic = item_icons_by_name.get(item_key)
    if ic is None:
        fn = _item_icon_map_data.get(item_key)
        if fn:
            if fn not in _icache_icons:
                _icache_icons[fn] = load_icon_file(fn, 38)
            ic = _icache_icons.get(fn)
            if ic:
                item_icons_by_name[item_key] = ic
    if ic:
        if ic.get_width() != size:
            ic = pygame.transform.smoothscale(ic, (size, size))
        surface.blit(ic, (x, y))
    else:
        pygame.draw.rect(surface, (52, 56, 72), (x, y, size, size))
        pygame.draw.rect(surface, (130, 140, 170), (x, y, size, size), 1)


def draw_bar(x, y, w, h, value, max_value, fg=(80, 220, 80), bg=(60, 60, 60)):
    pygame.draw.rect(screen, bg, (x, y, w, h))
    ratio = 0 if max_value <= 0 else max(0, min(1, value / max_value))
    pygame.draw.rect(screen, fg, (x, y, int(w * ratio), h))
    pygame.draw.rect(screen, (220, 220, 220), (x, y, w, h), 1)


def draw_retro_frame(surf, x, y, w, h, inner=(14, 22, 38), border=(220, 228, 255)):
    """白枠・濃紺パネル（汎用レトロRPG風・特定作品の模倣ではない）"""
    pygame.draw.rect(surf, inner, (x, y, w, h))
    pygame.draw.rect(surf, border, (x, y, w, h), 2)
    pygame.draw.line(surf, (255, 255, 255), (x + 2, y + 2), (x + w - 3, y + 2))


def retro_scale_surface(src, w, h):
    """ドット絵用：なめらか補間せず拡大"""
    if src is None:
        return None
    if src.get_width() == w and src.get_height() == h:
        return src
    return pygame.transform.scale(src, (w, h))


def ensure_party_slots():
    defaults = [
        {"name": "戦士", "hp": 80, "max_hp": 80, "atk": 8, "skills": [], "status": {}},
        {"name": "僧侶", "hp": 60, "max_hp": 60, "atk": 5, "skills": [], "status": {}},
        {"name": "弓使い", "hp": 70, "max_hp": 70, "atk": 7, "skills": [], "status": {}},
        {"name": "魔法使い", "hp": 55, "max_hp": 55, "atk": 6, "skills": [], "status": {}},
    ]
    party = player.setdefault("party", [])
    for i in range(min(len(defaults), MAX_PARTY_MEMBERS)):
        if i >= len(party):
            party.append(defaults[i].copy())
        else:
            party[i].setdefault("name", defaults[i]["name"])
            party[i].setdefault("max_hp", defaults[i]["max_hp"])
            party[i].setdefault("hp", party[i]["max_hp"])
            party[i].setdefault("atk", defaults[i]["atk"])
            party[i].setdefault("skills", defaults[i]["skills"][:])
            party[i].setdefault("status", {})
    if len(party) > MAX_PARTY_MEMBERS:
        del party[MAX_PARTY_MEMBERS:]
    for member in party:
        member.setdefault("absent", False)
        member.setdefault("level", 1)
        member.setdefault("exp", 0)
        member.setdefault("exp_next", 36)
        member.setdefault("battle_action", "呪文")
        member.setdefault("status", {})
        base_mp = MEMBER_BASE_MP.get(member["name"], 30)
        member.setdefault("max_mp", base_mp)
        member.setdefault("mp", member["max_mp"])
        chain = MEMBER_SKILL_CHAINS.get(member["name"], [])
        member["skills"] = [s for s in member.get("skills", []) if s in chain]
        if not member["skills"] and chain:
            member["skills"] = [chain[0]]


def ensure_player_state():
    if not isinstance(player.get("story_flags"), dict):
        player["story_flags"] = {}
    if not isinstance(player.get("personality"), dict):
        player["personality"] = {k: 0 for k in PERSONALITY_AXES}
    if not isinstance(player.get("build"), dict):
        player["build"] = {}
    if not isinstance(player.get("party"), list):
        player["party"] = []
    if not isinstance(player.get("inventory"), list):
        player["inventory"] = []
    if not isinstance(player.get("traits"), list):
        player["traits"] = []
    player.setdefault("gold", 0)
    player.setdefault("inventory", [])
    player.setdefault("status", {})
    player.setdefault("skills", ["ファイア"])
    player.setdefault("max_mp", 50)
    player.setdefault("mp", player["max_mp"])
    player.setdefault("quests", [q.copy() for q in quest_defs])
    player.setdefault("story_flags", {})
    player.setdefault("job", "冒険者")
    player.setdefault("traits", [])
    player.setdefault("relics", [])
    player.setdefault("perm_bonus_atk", 0)
    player.setdefault("perm_bonus_def", 0)
    player.setdefault("route_mode", None)
    player.setdefault("route_for_floor", -1)
    player.setdefault("torch_turns", 0)
    player.setdefault("_explore_atk_bonus", 0)
    player.setdefault("_explore_curse_def", 0)
    player.setdefault("_event_mod_left", 0)
    player.setdefault("_map_explored", {})
    player.setdefault("_gimmick_tutorial", {})
    player.setdefault("_map_legend_short", False)
    player.setdefault("floor_buff_picked", [])
    player.setdefault("skill_points", 0)
    player.setdefault("party_battle_mode", "manual")
    if player.get("party_battle_mode") not in ("manual", "auto"):
        player["party_battle_mode"] = "manual"
    player.setdefault("world_phase", "day")
    if player.get("world_phase") not in ("day", "night"):
        player["world_phase"] = "day"
    player.setdefault("world_weather", "clear")
    if player.get("world_weather") not in ("clear", "rain"):
        player["world_weather"] = "clear"
    player.setdefault("seal", None)
    if player.get("seal") not in (None, "火", "雷", "光"):
        player["seal"] = None
    player.setdefault("codex_enemies", [])
    player.setdefault("codex_skills", [])
    player.setdefault("codex_normals", [])
    player.setdefault("codex_bosses", [])
    player.setdefault("codex_rares", [])
    player.setdefault("codex_items", [])
    if not isinstance(player.get("codex_enemies"), list):
        player["codex_enemies"] = []
    if not isinstance(player.get("codex_skills"), list):
        player["codex_skills"] = []
    if not isinstance(player.get("codex_normals"), list):
        player["codex_normals"] = []
    if not isinstance(player.get("codex_bosses"), list):
        player["codex_bosses"] = []
    if not isinstance(player.get("codex_rares"), list):
        player["codex_rares"] = []
    if not isinstance(player.get("codex_items"), list):
        player["codex_items"] = []
    if not player.get("_codex_items_backfilled"):
        for it in player.get("inventory", []):
            if isinstance(it, str):
                register_codex_item(it)
        player["_codex_items_backfilled"] = True
    if player.get("codex_enemies") and not player.get("_codex_split_migrated"):
        for n in player["codex_enemies"]:
            if isinstance(n, str) and n not in player["codex_normals"]:
                player["codex_normals"].append(n)
        player["_codex_split_migrated"] = True
    player.setdefault("difficulty", "normal")
    if player.get("difficulty") not in ("easy", "normal", "hard"):
        player["difficulty"] = "normal"
    player.setdefault("achievements", {})
    if not isinstance(player.get("achievements"), dict):
        player["achievements"] = {}
    player.setdefault("_wins", 0)
    player.setdefault("_night_wins", 0)
    _player_build()
    player.setdefault("personality", {k: 0 for k in PERSONALITY_AXES})
    for k in PERSONALITY_AXES:
        player["personality"].setdefault(k, 0)
        v = player["personality"][k]
        player["personality"][k] = max(-100, min(100, int(v)))
    player["skills"] = [s for s in player.get("skills", []) if s in PLAYER_SKILL_CHAIN]
    if not player["skills"]:
        player["skills"] = [PLAYER_SKILL_CHAIN[0]]
    ensure_party_slots()
    player.setdefault("opt_bgm_vol", 1.0)
    player.setdefault("opt_se_vol", 1.0)
    player.setdefault("opt_se_on", True)
    player.setdefault("play_time_sec", 0.0)
    try:
        player["opt_bgm_vol"] = max(0.0, min(1.0, float(player["opt_bgm_vol"])))
        player["opt_se_vol"] = max(0.0, min(1.0, float(player["opt_se_vol"])))
    except (TypeError, ValueError):
        player["opt_bgm_vol"] = 1.0
        player["opt_se_vol"] = 1.0
    # 自由移動: 浮動小数点座標へ正規化
    try:
        player["x"] = float(player.get("x", 1))
        player["y"] = float(player.get("y", 1))
    except (TypeError, ValueError):
        player["x"] = 1.0
        player["y"] = 1.0
    last_tile = player.get("_world_last_tile")
    if not (isinstance(last_tile, (list, tuple)) and len(last_tile) == 2):
        cx = int(math.floor(float(player["x"]) + 0.5))
        cy = int(math.floor(float(player["y"]) + 0.5))
        player["_world_last_tile"] = [cx, cy]
    player.setdefault("_world_walked_dist", 0.0)
    apply_sound_effect_settings()


def personality_apply(deltas):
    if not deltas:
        return
    p = player.setdefault("personality", {k: 0 for k in PERSONALITY_AXES})
    for k, dv in deltas.items():
        if k not in p:
            continue
        p[k] = max(-100, min(100, p[k] + int(dv)))
    maybe_companion_desertion()
    try_start_bond_crisis()


def personality_deltas_from_effect_text(effect_str):
    if not effect_str:
        return {}
    out = {}
    for axis in PERSONALITY_AXES:
        pat = re.compile(re.escape(axis) + r"\s*([+-])\s*(\d+)")
        for m in pat.finditer(effect_str):
            sign = 1 if m.group(1) == "+" else -1
            out[axis] = out.get(axis, 0) + sign * int(m.group(2))
    return out


def member_affinity(member):
    w = MEMBER_AFFINITY_WEIGHTS.get(member.get("name"), {})
    p = player.get("personality", {})
    if not isinstance(p, dict):
        p = {}
    return sum(p.get(axis, 0) * wt for axis, wt in w.items())


def maybe_companion_desertion():
    global battle_log
    for i, m in enumerate(player.get("party", [])[:MAX_PARTY_MEMBERS]):
        if m.get("absent") or m.get("hp", 0) <= 0:
            continue
        if member_affinity(m) < COMPANION_LEAVE_AFFINITY:
            m["absent"] = True
            m["hp"] = 0
            nm = m.get("name", "仲間")
            battle_log = f"{nm}はあなたの在り方に耐えられず、一行を去った……"
            return


def _player_build():
    b = player.setdefault("build", {})
    for k in ("spell_power", "debuff_focus", "crit_focus", "guard_focus"):
        b[k] = max(0, min(8, int(b.get(k, 0))))
    return b


def debuff_proc_bonus():
    return _player_build().get("debuff_focus", 0) * 0.045


def spell_power_bonus():
    return _player_build().get("spell_power", 0) * 2.5


LIGHTNING_SKILLS = frozenset({"サンダーボルト", "雷脈", "カオスボルト"})
FIRE_SKILLS = frozenset({"ファイア", "フレイム", "メテオ", "ポイズンストーム"})
MAGE_ARCANE_TRIGGERS = frozenset({"メテオ", "カオスボルト", "終焉の星"})


def party_alive_names():
    return {
        m.get("name")
        for m in player.get("party", [])[:MAX_PARTY_MEMBERS]
        if m.get("hp", 0) > 0 and not m.get("absent")
    }


def env_spell_power_mult(spell_name):
    """天候×刻印のシナジー（雷＋雨など）。上限で壊れにくく。"""
    m = 1.0
    w = player.get("world_weather", "clear")
    seal = player.get("seal")
    if w == "rain" and spell_name in LIGHTNING_SKILLS:
        m *= 1.48
    if seal == "雷" and spell_name in LIGHTNING_SKILLS and w == "rain":
        m *= 1.22
    if seal == "火" and spell_name in FIRE_SKILLS:
        m *= 1.14
    return min(2.1, m)


def tactical_heal_mult():
    """昼＝回復寄り、光刻印＝さらに回復。"""
    m = 1.0
    if player.get("world_phase") == "day":
        m *= 1.16
    if player.get("seal") == "光":
        m *= 1.1
    return min(1.38, m)


def synergy_war_priest_flat():
    """戦士＋僧侶：被ダメをわずかに軽減（編成シナジー）"""
    n = party_alive_names()
    if "戦士" in n and "僧侶" in n:
        return 2
    return 0


def tactics_short_summary():
    ph = "昼" if player.get("world_phase") == "day" else "夜"
    w = "雨" if player.get("world_weather") == "rain" else "晴"
    seal = player.get("seal") or "無"
    return f"【{ph}・{w}】刻:{seal}"


def advance_world_tactics():
    """戦闘終了ごとに昼夜が切り替わり、天候が少し変わる（戦略の切り替え用）"""
    player["world_phase"] = "night" if player.get("world_phase") == "day" else "day"
    player["world_weather"] = "rain" if random.random() < 0.3 else "clear"


def cycle_player_seal():
    order = [None, "火", "雷", "光"]
    cur = player.get("seal")
    i = order.index(cur) if cur in order else 0
    player["seal"] = order[(i + 1) % len(order)]


def register_codex_enemy(name, tier="normal"):
    if not name:
        return
    if tier == "boss":
        lst = player.setdefault("codex_bosses", [])
    elif tier == "rare":
        lst = player.setdefault("codex_rares", [])
    else:
        lst = player.setdefault("codex_normals", [])
    if name not in lst:
        lst.append(name)
    legacy = player.setdefault("codex_enemies", [])
    if name not in legacy:
        legacy.append(name)


def register_codex_item(name):
    if not name:
        return
    cx = player.setdefault("codex_items", [])
    if name not in cx:
        cx.append(name)


def grant_inventory_item(name):
    player.setdefault("inventory", []).append(name)
    register_codex_item(name)


def register_codex_skill(name):
    cx = player.setdefault("codex_skills", [])
    if name and name not in cx:
        cx.append(name)


ACHIEVEMENT_LABELS = {
    "ach_first_win": "初陣の勝利",
    "ach_night3": "夜戦の手練れ",
    "ach_codex10": "図鑑・敵10種",
}

ALLY_ROLE_TAG = {
    "戦士": "火力・自己強化",
    "僧侶": "回復・支援呪文",
    "弓使い": "クリ・術後の追撃",
    "魔法使い": "範囲・大術",
    "闇傭兵": "デバフ・クリ",
}


def codex_unique_enemy_species():
    u = set(player.get("codex_normals", [])) | set(player.get("codex_bosses", [])) | set(player.get("codex_rares", []))
    if not u:
        return len(set(player.get("codex_enemies", [])))
    return len(u)


def next_goal_one_line():
    """クエスト・図鑑から「今の目安」を1行（ワールド左下用）。"""
    qs = [q for q in player.get("quests", []) if isinstance(q, dict)]
    pending = [q for q in qs if not q.get("done")]
    if pending:
        pending.sort(key=lambda q: int(q.get("target_floor", 999)))
        q = pending[0]
        tf = q.get("target_floor", "?")
        return f"次の目標: {q.get('title', 'クエスト')}（{tf}階のボスで達成）"
    cu = codex_unique_enemy_species()
    if cu < 12:
        return f"図鑑を広げよう（敵の種 {cu} …多様な遭遇が記録される）"
    if floor_number < 100:
        return f"更深層へ（現在 {floor_number} 階）。装備とレベルを整えて"
    return "エンディング以降の探索・実績を楽しもう"


def cycle_difficulty():
    order = ("normal", "easy", "hard")
    cur = tactics_difficulty()
    i = order.index(cur) if cur in order else 0
    player["difficulty"] = order[(i + 1) % len(order)]


def physical_crit_chance():
    c = 0.06 + _player_build().get("crit_focus", 0) * 0.035
    for m in player.get("party", [])[:MAX_PARTY_MEMBERS]:
        if not m.get("absent") and m.get("bond_crit_bonus"):
            c += float(m.get("bond_crit_bonus", 0))
    if player.get("world_phase") == "night":
        c += 0.08
        for m in player.get("party", [])[:MAX_PARTY_MEMBERS]:
            if m.get("hp", 0) > 0 and not m.get("absent") and m.get("name") == "弓使い":
                c += 0.05
                break
    return min(0.48, c)


def bump_attack_fx(is_crit=False):
    global battle_ui_shake, enemy_shake_timer, slash_timer, crit_slow_timer
    battle_ui_shake = min(28, battle_ui_shake + (18 if is_crit else 9))
    enemy_shake_timer = max(enemy_shake_timer, 14 if is_crit else 8)
    slash_timer = max(slash_timer, 10 if is_crit else 5)
    if is_crit:
        crit_slow_timer = max(crit_slow_timer, 22)
    play_battle_se("crit" if is_crit else "hit")
    trigger_battle_vfx("phys_strong" if is_crit else "phys", 24 if is_crit else 14)


def bump_magic_fx(strong=False):
    global flash_timer, enemy_shake_timer, battle_ui_shake
    flash_timer = max(flash_timer, 12 if strong else 8)
    enemy_shake_timer = max(enemy_shake_timer, 9 if strong else 6)
    battle_ui_shake = min(22, battle_ui_shake + (7 if strong else 4))


def try_apply_skill_status(skill, target_enemy=True):
    if enemy is None or not target_enemy:
        return
    ex = debuff_proc_bonus()
    if not isinstance(skill, dict):
        return
    for key, st in (("poison_chance", "毒"), ("paralyze_chance", "麻痺")):
        if key not in skill:
            continue
        try:
            p = float(skill[key]) + ex
        except (TypeError, ValueError):
            continue
        if random.random() < min(0.92, p):
            apply_status(enemy, st)


DARK_MERC_TEMPLATE = {
    "name": "闇傭兵",
    "hp": 95,
    "max_hp": 95,
    "atk": 16,
    "skills": ["ブレイブスラッシュ"],
    "status": {},
    "level": 6,
    "exp": 0,
    "exp_next": 40,
    "battle_action": "攻撃",
    "absent": False,
    "max_mp": 20,
    "mp": 20,
    "bond_dark": True,
}


def try_fill_dark_mercenary():
    for i, m in enumerate(player["party"][:MAX_PARTY_MEMBERS]):
        if m.get("absent"):
            player["party"][i] = copy.deepcopy(DARK_MERC_TEMPLATE)
            return True
    return False


def try_start_bond_crisis():
    """ワールド等で仲間価値観イベントを開始（戦闘中はキュー）"""
    global mode, bond_crisis_state, pending_bond_check, battle_log
    if bond_crisis_state is not None:
        return
    if mode == "battle":
        pending_bond_check = True
        return
    if mode not in ("world", "town"):
        return
    ret_mode = mode
    pers = player.get("personality")
    if not isinstance(pers, dict):
        pers = {}
    mor = int(pers.get("morality", 0))
    brv = int(pers.get("bravery", 0))
    comp = int(pers.get("compassion", 0))
    grd = int(pers.get("greed", 0))
    party = player.get("party", [])[:MAX_PARTY_MEMBERS]
    for i, m in enumerate(party):
        if not isinstance(m, dict):
            continue
        if m.get("absent"):
            continue
        nm = m.get("name", "")
        if nm == "僧侶":
            st = m.get("priest_bond_stage")
            if mor < -5 and st == "await_final":
                bond_crisis_state = {"path": "priest_leave", "idx": i, "step": 1, "ret": ret_mode}
                mode = "companion_crisis"
                return
            if mor < -5 and st is None:
                bond_crisis_state = {"path": "priest_leave", "idx": i, "step": 0, "ret": ret_mode}
                mode = "companion_crisis"
                return
        if nm == "戦士" and brv > 5 and not m.get("warrior_awaken_done"):
            bond_crisis_state = {"path": "warrior_awaken", "idx": i, "step": 0, "ret": ret_mode}
            mode = "companion_crisis"
            return
        if nm == "弓使い" and mor >= 22 and comp >= 20 and not m.get("archer_oath_done"):
            bond_crisis_state = {"path": "archer_oath", "idx": i, "step": 0, "ret": ret_mode}
            mode = "companion_crisis"
            return
    sf = player.get("story_flags") if isinstance(player.get("story_flags"), dict) else {}
    if grd > 34 and mor < -12 and not sf.get("dark_merc_offered"):
        if any(p.get("absent") for p in party):
            bond_crisis_state = {"path": "dark_merc", "idx": -1, "step": 0, "ret": ret_mode}
            mode = "companion_crisis"
            return


def bond_crisis_apply_choice(choice_idx):
    """choice_idx 0-based 左から1番"""
    global mode, bond_crisis_state, battle_log
    if not bond_crisis_state:
        mode = "world"
        return
    path = bond_crisis_state["path"]
    idx = bond_crisis_state["idx"]
    step = bond_crisis_state["step"]
    party = player["party"]
    m = party[idx] if idx >= 0 else None

    if path == "priest_leave" and m:
        if step == 0:
            if choice_idx == 0:
                personality_apply({"morality": 4, "compassion": 2})
                m["priest_bond_stage"] = None
                battle_log = "僧侶: …ありがとう。まだ一緒に歩きたい。"
            else:
                m["priest_bond_stage"] = "await_final"
                battle_log = "僧侶: …そう、ですか。（静かに目を伏せた）"
        elif step == 1:
            if choice_idx == 0:
                personality_apply({"morality": 2, "compassion": 1})
                m["priest_bond_stage"] = None
                battle_log = "僧侶: …分かりました。もう一度、信じてみます。"
            else:
                m["absent"] = True
                m["hp"] = 0
                m["priest_bond_stage"] = "gone"
                battle_log = "僧侶: ご武運を。…失礼します。"
    elif path == "warrior_awaken" and m:
        if choice_idx == 0:
            m["atk"] = m.get("atk", 8) + 5
            m["max_hp"] = m.get("max_hp", 80) + 12
            m["hp"] = min(m["max_hp"], m.get("hp", 0) + 12)
            m["warrior_awaken_done"] = True
            personality_apply({"bravery": 1, "honor": 1})
            battle_log = "戦士: 本気を見せてやる…覚悟しろ敵ども！"
            bump_magic_fx(True)
        else:
            m["warrior_awaken_done"] = True
            personality_apply({"bravery": -1})
            battle_log = "戦士: …抑えておく。まだ早い。"
    elif path == "archer_oath" and m:
        if choice_idx == 0:
            m["archer_oath_done"] = True
            m["bond_crit_bonus"] = 0.09
            personality_apply({"honor": 1})
            battle_log = "弓使い: 背中は任せろ。お前となら、まだ遠くへ行ける。"
        else:
            m["archer_oath_done"] = True
            battle_log = "弓使い: …照れるな。気を取り直して進もうぜ。"
    elif path == "dark_merc":
        if choice_idx == 0:
            if try_fill_dark_mercenary():
                player.setdefault("story_flags", {})["dark_merc_offered"] = True
                personality_apply({"greed": 2, "morality": -3, "cunning": 2})
                battle_log = "闇傭兵: 契約成立だ。俺の刃は高いぞ…お前の欲望なら安い。"
            else:
                battle_log = "仲間の空きがない。"
        else:
            player.setdefault("story_flags", {})["dark_merc_offered"] = True
            personality_apply({"honor": 1, "greed": -1})
            battle_log = "闇の気配が霧のように消えた。"

    ret = bond_crisis_state.get("ret", "world")
    bond_crisis_state = None
    mode = ret
    try_start_bond_crisis()


def spend_skill_point(branch):
    """branch 0..3 : spell_power / debuff / crit / guard"""
    if player.get("skill_points", 0) <= 0:
        return "スキルポイントが足りない"
    b = _player_build()
    keys = ("spell_power", "debuff_focus", "crit_focus", "guard_focus")
    labels = ("呪文火力", "デバフ・状態異常", "会心", "防御時の軽減")
    key = keys[branch]
    if b[key] >= 8:
        return "この路線は上限です"
    b[key] += 1
    player["skill_points"] -= 1
    return f"鍛錬: {labels[branch]} を強化した"


def mood_hint_text():
    pers = player.get("personality", {})
    if not isinstance(pers, dict):
        pers = {}
    mor = int(pers.get("morality", 0))
    brv = int(pers.get("bravery", 0))
    grd = int(pers.get("greed", 0))
    if mor <= -25:
        return "空気がどこか冷たい…"
    if grd >= 40:
        return "金の匂いがついてまわる。"
    if brv >= 35:
        return "胸の鼓動が高鳴っている。"
    if mor >= 35 and int(pers.get("compassion", 0)) >= 25:
        return "道行く人の目が少し柔らかい。"
    return ""


def apply_story_effect(effect):
    global last_story_choice
    if not effect:
        return
    for seg in effect.split("|"):
        seg = seg.strip()
        if seg.startswith("story_flag="):
            k = seg.split("=", 1)[1].strip()
            if k:
                sf = player.setdefault("story_flags", {})
                if k.startswith("ending_abyss"):
                    for o in ("ending_abyss_sacrifice", "ending_abyss_jester", "ending_abyss_void"):
                        if o != k:
                            sf.pop(o, None)
                sf[k] = True
    clean = "|".join(p for p in effect.split("|") if not p.strip().startswith("story_flag="))
    pd = personality_deltas_from_effect_text(clean)
    if pd:
        personality_apply(pd)
    if "stat_type=attack" in effect:
        player["atk"] += 2
        player["job"] = "ウォリアー"
        if "猛攻" not in player["traits"]:
            player["traits"].append("猛攻")
        last_story_choice = "attack"
    elif "stat_type=defense" in effect:
        player["max_hp"] += 20
        player["hp"] = player["max_hp"]
        player["job"] = "ガーディアン"
        if "鉄壁" not in player["traits"]:
            player["traits"].append("鉄壁")
        last_story_choice = "defense"
    elif "stat_type=magic" in effect:
        player["max_mp"] += 15
        player["mp"] = player["max_mp"]
        player["job"] = "ソーサラー"
        if "魔力増幅" not in player["traits"]:
            player["traits"].append("魔力増幅")
        last_story_choice = "magic"


def quest_update(floor, boss_defeated):
    if not boss_defeated:
        return
    for q in player["quests"]:
        if floor >= q["target_floor"]:
            q["done"] = True


def get_ending_text():
    completed = sum(1 for q in player["quests"] if q.get("done"))
    pq = len(player["quests"]) or 1
    relic_count = len(player.get("relics", []))
    pers = player.get("personality", {})
    if not isinstance(pers, dict):
        pers = {}
    m = lambda k: int(pers.get(k, 0))
    left = sum(1 for p in player.get("party", [])[:MAX_PARTY_MEMBERS] if p.get("absent"))
    traits = set(player["traits"]) if isinstance(player.get("traits"), list) else set()
    sf = player.get("story_flags") if isinstance(player.get("story_flags"), dict) else {}

    if sf.get("ending_abyss_sacrifice"):
        return (
            "星渡りの墓標エンド: お前は自分の名を削り、深淵の扉に楔を打った。"
            "誰も覚えていない英雄がいる——だが世界は、知らぬ間に呼吸を取り戻している。"
            "泣き笑いみたいな凪の朝。それでいい、と君は小声で言った。"
        )
    if sf.get("ending_abyss_jester"):
        return (
            "道化の王冠エンド: 最後の最後で、お前は世界に茶化しの一発を食らわせた。"
            "神も魔王も呆れ顔で、それでも拍手が遠くで鳴った。"
            "滑稽さは、ときどき救いより強い。"
        )
    if sf.get("ending_abyss_void"):
        return (
            "空白の凱旋エンド: お前は何も語らず、何も証明しなかった。"
            "けれど深淵は静かになり、星はまた巡り始めた。"
            "誰かの心にだけ残る物語は、紙の上には載らない。"
        )
    if sf.get("ending_echo_love") and m("compassion") >= 38:
        return (
            "残響の恋文エンド: 倒した相手の瞳に映った自分が、怖くて優しかった。"
            "君は手紙を地面に埋めた。芽が出るかは、風次第。"
            "それでも「好きだった」と呟けるのは、負けではない。"
        )

    if left >= 3:
        return "孤独の覇者エンド: 誰も信じなかった者だけが王座に座る。雪のように静かで、どこか滑稽な勝利だった。"
    if m("compassion") >= 48 and m("morality") >= 42 and left == 0 and completed >= pq - 1:
        return "涙の絆エンド: 傷ついた村々に灯を灯し続けた君の手は、誰かの記憶に温かく残った。別れはあっても、愛は消えない。"
    if m("greed") >= 55 and m("morality") <= -35:
        return "黄金の墓標エンド: 財宝の山は高かったが、振り返れば誰もいない。笑えば笑うほど、胸の穴は風が通り抜けた。"
    if m("bravery") <= -40 and completed >= 1:
        return "影の生還エンド: 生き延びたことだけが才能だった世界で、君はそれを貫いた。誇れないが、嘘もつかない。"
    if m("honor") >= 45 and m("cunning") <= -20 and completed >= 2:
        return "白銀の誓いエンド: 裏切らないと決めた道は険しかった。それでも旗は汚れず、民は君の名を囁く。"
    if m("cunning") >= 50 and "深智契約" in traits:
        return "深淵の棋士エンド: 世界は盤面、神々は観客。君は最後の一手で、運命のルールそのものを書き換えた。"
    if m("morality") <= -50 and m("greed") >= 30:
        return "堕落の王エンド: 善悪の秤は砕け、欲望だけが法となった。新世界は暗いが、君には眩しかった。"
    if m("morality") >= 55 and m("compassion") >= 40 and relic_count == 0 and completed >= 2:
        return "無名の聖者エンド: 遺物も名声もいらないと笑い、君はただ人を抱きしめた。史書には載らないが、泣けるほど美しい。"
    if completed == len(player["quests"]) and last_story_choice == "magic" and relic_count >= 2:
        return "真理エンド: 叡智と遺物の力で世界の歪みは浄化された。"
    if player.get("job") == "ウォリアー" and completed >= 2 and m("bravery") >= 25:
        return "覇道エンド: 剣の王として新時代を切り開いた。傷だらけの手で掴んだ未来は、誰よりも熱かった。"
    if player.get("job") == "ガーディアン" and completed >= 2:
        return "守護エンド: 民を守る永遠の盾として語り継がれた。"
    if player.get("job") == "ソーサラー" and relic_count >= 1:
        return "秘術エンド: 魔導の塔を再建し、魔法文明を復興した。"
    if completed >= 2 and left == 0:
        return "英雄エンド: 仲間と笑い合いながら、深淵の扉を閉じた。平凡な言葉が、いちばん面白いエピローグになる。"
    if relic_count >= 1 and m("greed") >= 20:
        return "蒐集家の黄昏エンド: 遺物は揃った。しかし満たされないのは心だけ——次に集めるのは、失われた日々かもしれない。"
    if relic_count >= 1:
        return "蒐集家エンド: 遺物を集め、歴史を後世に残した。"
    if completed >= 1 and m("compassion") >= 25:
        return "旅路の灯エンド: 魔王は倒れた。君が残した小さな優しさは、道端の花のように増えていくだろう。"
    return "旅人エンド: 魔王は倒れたが、まだ世界には未知が残っている。物語は続く——君の歩幅で。"


def start_random_battle():
    base_tier = min(9, max(0, (floor_number - 1) // 10))
    tier = min(9, max(0, base_tier + route_tier_adjust()))
    pool = BIOME_ENEMY_POOLS[tier] if tier < len(BIOME_ENEMY_POOLS) else BIOME_ENEMY_POOLS[0]
    enemy_names = [n for n in pool if n in enemy_catalog]
    if not enemy_names:
        enemy_names = list(enemy_catalog.keys()) if enemy_catalog else ["スライム"]
    pos = (-1, -1)
    pack = encounter_pack_size()
    wave = []
    for i in range(pack):
        n = random.choice(enemy_names)
        wave.append(make_spawn_enemy_dict(n, enemy_catalog.get(n, {}), i))
    player["_battle_wave"] = wave
    player["_battle_wave_idx"] = 0
    enemies[pos] = {k: wave[0][k] for k in wave[0]}
    start_battle(pos)


def apply_relic(relic):
    if relic["name"] in player["relics"]:
        return
    player["relics"].append(relic["name"])
    effect = relic["effect"]
    if "atk+" in effect:
        player["atk"] += int(effect.replace("atk+", ""))
    elif "hp+" in effect:
        v = int(effect.replace("hp+", ""))
        player["max_hp"] += v
        player["hp"] += v
    elif "mp+" in effect:
        v = int(effect.replace("mp+", ""))
        player["max_mp"] += v
        player["mp"] += v


def equip_from_inventory(index):
    if index < 0 or index >= len(player["inventory"]):
        return "そのスロットは空です"
    name = player["inventory"][index]
    if name in weapons:
        player["weapon"] = name
        return f"{name}を装備した"
    if name in armors:
        player["armor"] = name
        return f"{name}を装備した"
    return f"{name}は装備できない"


def shop_item_by_name(name):
    for it in SHOP_CATALOG_ALL:
        if it.get("name") == name:
            return it
    return None


def inventory_use_consumable(index):
    global inventory_selected
    if index < 0 or index >= len(player["inventory"]):
        return "スロットがありません"
    name = player["inventory"][index]
    it = shop_item_by_name(name)
    if not it or it.get("type") != "consumable":
        return "ここでは使えない（装備は数字で装備）"
    msg = apply_item_effect(it)
    player["inventory"].pop(index)
    inv = player["inventory"]
    if index < inventory_selected:
        inventory_selected -= 1
    elif inventory_selected >= len(inv):
        inventory_selected = max(0, len(inv) - 1)
    # #region agent log
    try:
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-5f7464.log")
        with open(_p, "a", encoding="utf-8") as _df:
            import time as _agent_time

            _df.write(
                json.dumps(
                    {
                        "sessionId": "5f7464",
                        "hypothesisId": "H1",
                        "location": "main.py:inventory_use_consumable",
                        "message": "post-use_sel_ok",
                        "data": {
                            "index": index,
                            "inv_len": len(inv),
                            "inventory_selected": inventory_selected,
                        },
                        "timestamp": int(_agent_time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
    return msg


def inventory_discard(index):
    global inventory_selected
    if index < 0 or index >= len(player["inventory"]):
        return "スロットがありません"
    name = player["inventory"].pop(index)
    inv = player["inventory"]
    if index < inventory_selected:
        inventory_selected -= 1
    elif inventory_selected >= len(inv):
        inventory_selected = max(0, len(inv) - 1)
    return f"{name}を捨てた"


def inventory_sell_selected(index):
    """ショップ定価の約半額で売却（未登録名は低めの買取）。"""
    global inventory_selected
    inv = player["inventory"]
    if index < 0 or index >= len(inv):
        return "売却できません"
    name = inv.pop(index)
    it = shop_item_by_name(name)
    base = int(it.get("price", 22)) if it else 18
    gold_add = max(2, base // 2)
    player["gold"] = player.get("gold", 0) + gold_add
    if index < inventory_selected:
        inventory_selected -= 1
    elif inventory_selected >= len(inv):
        inventory_selected = max(0, len(inv) - 1)
    return f"{name}を {gold_add}G で売却した"


def inventory_swap_next(index):
    inv = player["inventory"]
    if index < 0 or index >= len(inv) - 1:
        return "並べ替えできません"
    inv[index], inv[index + 1] = inv[index + 1], inv[index]
    return "並びを入れ替えた"


def next_member_skill(member):
    chain = MEMBER_SKILL_CHAINS.get(member["name"], [])
    learned = set(member.get("skills", []))
    for s in chain:
        if s not in learned:
            return s
    return None


def next_player_skill():
    learned = set(player.get("skills", []))
    for s in PLAYER_SKILL_CHAIN:
        if s not in learned:
            return s
    return None


def cycle_party_action(index):
    member = player["party"][index]
    now = member.get("battle_action", "攻撃")
    idx = party_action_choices.index(now) if now in party_action_choices else 0
    member["battle_action"] = party_action_choices[(idx + 1) % len(party_action_choices)]


def enemy_stat_scaled(base, floor, stat):
    """階層が上がるほど敵が伸びる（歯ごたえ重視の連戦・ボス前提のカーブ）。
    1階でも 1〜2 撃では倒せず、3〜4 撃でようやく落ちる強度を確保する。"""
    tier = max(0, floor // 10)
    floor_off = max(0, floor - 1)  # 1階基準で 0 起算
    if stat == "hp":
        return int(base.get("hp", 30) * (1.32 + floor_off * 0.11 + tier * 0.14))
    if stat == "atk":
        return int(base.get("attack", 6) * (1.18 + floor_off * 0.07 + tier * 0.06))
    if stat == "exp":
        return int(base.get("exp", 15) * (1.04 + floor_off * 0.072 + tier * 0.045) * 0.92)
    return 0


def encounter_pack_size():
    """ランダム戦闘で複数体が出る確率（1階から普通に2〜3体出る・高階で増）。"""
    f = floor_number
    r = random.random()
    # 1〜3 階: 5% で 3 体、25% で 2 体、それ以外は 1 体
    if f <= 3:
        if r < 0.05:
            return 3
        if r < 0.30:
            return 2
        return 1
    # 4〜9 階: 8% で 3 体、35% で 2 体
    if f <= 9:
        if r < 0.08:
            return 3
        if r < 0.43:
            return 2
        return 1
    # 10〜29 階: 14% で 3 体、45% で 2 体
    if f <= 29:
        if r < 0.14:
            return 3
        if r < 0.59:
            return 2
        return 1
    # 30〜74 階: 22% で 3 体、55% で 2 体
    if f <= 74:
        if r < 0.22:
            return 3
        if r < 0.77:
            return 2
        return 1
    # 75 階以降: 32% で 3 体、70% で 2 体
    if r < 0.32:
        return 3
    if r < 0.92:
        return 2
    return 1


def make_spawn_enemy_dict(name_key, catalog_entry, slot_index):
    """slot_index 1 以降は控え目に弱めるが、連戦でも歯ごたえを残す。"""
    d = catalog_entry or {}
    scaled = {
        "name": name_key,
        "hp": enemy_stat_scaled(d, floor_number, "hp"),
        "atk": enemy_stat_scaled(d, floor_number, "atk"),
        "exp": enemy_stat_scaled(d, floor_number, "exp"),
        "type": "normal",
        "rare": bool(d.get("rare")),
    }
    if slot_index >= 1:
        # 多体戦は手数が増えるため、後列はやや低めにするが極端には弱くしない
        scaled["hp"] = max(12, int(scaled["hp"] * (0.92 - 0.04 * (slot_index - 1))))
        scaled["atk"] = max(3, int(scaled["atk"] * (0.95 - 0.03 * (slot_index - 1))))
        scaled["exp"] = max(5, int(scaled["exp"] * (0.78 - 0.05 * (slot_index - 1))))
    scaled["max_hp"] = scaled["hp"]
    return scaled


def floor_enemy_image_key(floor, enemy_type):
    if enemy_type == "boss":
        if floor >= 100:
            return "boss_final"
        if floor >= 70:
            return "boss_3"
        if floor >= 40:
            return "boss_2"
        return "boss_1"
    if floor >= 80:
        return "enemy_5"
    if floor >= 60:
        return "enemy_4"
    if floor >= 40:
        return "enemy_3"
    if floor >= 20:
        return "enemy_2"
    return "enemy_1"


def generate_floor(floor):
    spawned = {}
    # 通常敵は草むらでランダムエンカウントに変更。固定配置はボスのみ。
    if floor % 10 == 0:
        boss_name = "階層ボス"
        if floor == 100:
            boss_name = "深淵王アビス"
        base_hp = 260 + floor * 16
        base_atk = 26 + floor // 2
        if floor < 100:
            base_hp = int(base_hp * 1.42)
            base_atk = int(base_atk * 1.28)
        else:
            base_hp = int(base_hp * 2.95)
            base_atk = int(base_atk * 1.62)
        spawned[(10, 5)] = {
            "name": boss_name,
            "hp": base_hp,
            "atk": base_atk,
            "exp": 200 + floor * 8,
            "type": "boss",
        }
    return spawned


def give_member_exp(member, gained):
    member["exp"] += max(1, gained // 2)
    while member["exp"] >= member["exp_next"]:
        member["exp"] -= member["exp_next"]
        member["exp_next"] += 26
        member["level"] += 1
        member["atk"] += 1
        member["max_hp"] += 8
        member["hp"] = min(member["max_hp"], member["hp"] + 8)
        member["max_mp"] = member.get("max_mp", 30) + 2
        member["mp"] = min(member["max_mp"], member.get("mp", 0) + 2)
        new_skill = next_member_skill(member)
        if new_skill:
            member["skills"].append(new_skill)


def member_cast_spell(member, s):
    global flash_timer, enemy_shake_timer, bless_next_phys_mult, battle_arcane_followup
    sync_battle_enemy_pointer()
    if enemy is None:
        return (False, "", 0)
    if s not in member.get("skills", []):
        return (False, "", 0)
    cost = MEMBER_SPELL_MP.get(s, 10)
    if member.get("mp", 0) < cost:
        return (False, "", 0)
    member["mp"] -= cost
    register_codex_skill(s)

    def _edmg(raw):
        em = env_spell_power_mult(s)
        bw, boss_msgs = boss_weakness_spell_mult_and_msgs(s)
        for p in env_spell_synergy_parts(s) + boss_msgs:
            push_synergy(p)
        d = int(raw * em * bw)
        enemy["hp"] -= d
        sync_battle_enemy_pointer()
        return d

    caster_name = member.get("name", "仲間")
    if s == "ブレイブスラッシュ":
        damage = _edmg(random.randint(member["atk"], member["atk"] + 14))
        enemy_shake_timer = 8
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "ソードダンス":
        damage = _edmg(random.randint(18, 38))
        enemy_shake_timer = 7
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "戦鬼解放":
        damage = _edmg(random.randint(40, 65))
        flash_timer = 10
        enemy_shake_timer = 12
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "瘴糸":
        damage = _edmg(random.randint(8, 16) + member.get("atk", 5) // 2)
        bump_magic_fx(False)
        if random.random() < 0.38 + debuff_proc_bonus():
            apply_status(enemy, "毒")
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "ホーリーライト":
        heal = int(random.randint(18, 35) * tactical_heal_mult())
        player["hp"] = min(player["max_hp"], player["hp"] + heal)
        flash_timer = 6
        if member.get("name") == "僧侶":
            bless_next_phys_mult = max(bless_next_phys_mult, 1.12)
        emit_spell_fx(s, caster_name)
        return (True, s, heal)
    if s == "守護の鐘":
        h = int(12 * tactical_heal_mult())
        for p in player["party"][:MAX_PARTY_MEMBERS]:
            if p["hp"] > 0:
                p["hp"] = min(p["max_hp"], p["hp"] + h)
        flash_timer = 5
        if member.get("name") == "僧侶":
            bless_next_phys_mult = max(bless_next_phys_mult, 1.12)
        emit_spell_fx(s, caster_name)
        return (True, s, h)
    if s == "聖域結界":
        big = int(45 * tactical_heal_mult())
        player["hp"] = min(player["max_hp"], player["hp"] + big)
        for p in player["party"][:MAX_PARTY_MEMBERS]:
            if p["hp"] > 0:
                p["hp"] = min(p["max_hp"], p["hp"] + max(1, big // 2))
        flash_timer = 8
        if member.get("name") == "僧侶":
            bless_next_phys_mult = max(bless_next_phys_mult, 1.12)
        emit_spell_fx(s, caster_name)
        return (True, s, big)
    if s == "トリプルアロー":
        damage = _edmg(sum(random.randint(4, max(5, member["atk"] // 2)) for _ in range(3)))
        enemy_shake_timer = 6
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "貫通狙撃":
        damage = _edmg(random.randint(25, 48))
        enemy_shake_timer = 9
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "嵐の矢":
        damage = _edmg(sum(random.randint(8, 18) for _ in range(5)))
        flash_timer = 6
        enemy_shake_timer = 8
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "メテオ":
        damage = _edmg(random.randint(28, 48))
        flash_timer = 8
        enemy_shake_timer = 8
        if member.get("name") == "魔法使い":
            battle_arcane_followup = True
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "カオスボルト":
        damage = _edmg(random.randint(35, 58))
        flash_timer = 7
        enemy_shake_timer = 10
        if member.get("name") == "魔法使い":
            battle_arcane_followup = True
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    if s == "終焉の星":
        damage = _edmg(random.randint(55, 90))
        flash_timer = 12
        enemy_shake_timer = 14
        if member.get("name") == "魔法使い":
            battle_arcane_followup = True
        emit_spell_fx(s, caster_name)
        return (True, s, damage)

    info = skills_data.get(s, {})
    if "heal" in info:
        weak = min([p for p in player["party"] if p["hp"] > 0] + [player], key=lambda x: x["hp"] / max(1, x["max_hp"]))
        hv = int(int(info["heal"]) * tactical_heal_mult())
        weak["hp"] = min(weak["max_hp"], weak["hp"] + hv)
        flash_timer = 4
        if member.get("name") == "僧侶":
            bless_next_phys_mult = max(bless_next_phys_mult, 1.12)
        emit_spell_fx(s, caster_name)
        return (True, s, hv)
    if "power" in info:
        pw = int(info["power"])
        damage = _edmg(random.randint(max(1, pw // 2), pw))
        bump_magic_fx(pw >= 40)
        try_apply_skill_status(info)
        emit_spell_fx(s, caster_name)
        return (True, s, damage)
    return (False, "", 0)


def ally_can_cast(member, s):
    if s not in member.get("skills", []):
        return False
    return member.get("mp", 0) >= MEMBER_SPELL_MP.get(s, 999)


def tactics_difficulty():
    d = player.get("difficulty", "normal")
    return d if d in ("easy", "normal", "hard") else "normal"


def day_heal_ai_thresholds():
    """難易は主に昼の回復判断で吸収（夜AIはそのまま）。"""
    d = tactics_difficulty()
    if d == "easy":
        return 0.58, 0.50
    if d == "hard":
        return 0.46, 0.40
    return 0.52, 0.45


def suggest_ally_command(idx):
    """仲間の自動作戦（HP・MP・敵残りから汎用ヒューリスティック）"""
    sync_battle_enemy_pointer()
    if enemy is None or all_enemies_defeated():
        return {"t": "atk"}
    m = player["party"][idx]
    if m.get("absent") or m.get("hp", 0) <= 0:
        return {"t": "def"}
    casts = [s for s in m.get("skills", []) if ally_can_cast(m, s)]
    heals = [s for s in casts if s in HEAL_MEMBER_SPELLS]
    off = [s for s in casts if s not in HEAL_MEMBER_SPELLS]

    def ratio(t):
        return t["hp"] / max(1, t["max_hp"])

    ratios = [ratio(player)]
    for p in player["party"][:MAX_PARTY_MEMBERS]:
        if p.get("hp", 0) > 0 and not p.get("absent"):
            ratios.append(ratio(p))
    lowest = min(ratios) if ratios else 1.0
    liv = living_enemy_indices()
    if liv:
        thp = sum(max(0, battle_enemies[i]["hp"]) for i in liv)
        tmx = sum(max(1, battle_enemies[i].get("max_hp", 1)) for i in liv)
        er = thp / max(1, tmx)
    else:
        er = 1.0

    if player.get("world_phase") == "day":
        heal_thresh, guard_thresh = day_heal_ai_thresholds()
    else:
        heal_thresh, guard_thresh = 0.42, 0.38
    if heals and lowest < heal_thresh:
        for h in ("聖域結界", "守護の鐘", "ホーリーライト"):
            if h in heals:
                return {"t": "spell", "name": h}

    if off and er > 0.12 and (er > 0.5 or lowest > 0.62 or random.random() < 0.5):
        off.sort(key=lambda s: MEMBER_SPELL_MP.get(s, 0), reverse=True)
        return {"t": "spell", "name": off[0]}

    if lowest < guard_thresh and random.random() < 0.35:
        return {"t": "def"}
    return {"t": "atk"}


def build_plan_units():
    u = ["hero"]
    for i in range(MAX_PARTY_MEMBERS):
        m = player["party"][i]
        if m["hp"] > 0 and not m.get("absent"):
            u.append(i)
    return u


def plan_focused_key():
    if player.get("party_battle_mode") == "auto":
        return "hero"
    if not battle_plan_units:
        return "hero"
    k = battle_plan_units[battle_plan_focus % len(battle_plan_units)]
    return k


def reset_battle_plan_state():
    global battle_plan_units, battle_plan_focus, battle_pending, spell_menu_target, spell_menu_cursor
    battle_plan_units = build_plan_units()
    battle_plan_focus = 0
    battle_pending = {}
    spell_menu_target = None
    spell_menu_cursor = 0
    if player.get("party_battle_mode") == "auto":
        for k in battle_plan_units:
            if k != "hero":
                battle_pending[k] = suggest_ally_command(k)


def all_commands_set():
    for k in battle_plan_units:
        if k == "hero":
            if "hero" not in battle_pending:
                return False
        else:
            if k not in battle_pending:
                return False
    return len(battle_plan_units) > 0


def pending_label(k):
    c = battle_pending.get("hero" if k == "hero" else k)
    if not c:
        return "未設定"
    t = c.get("t")
    if t == "atk":
        return "攻撃"
    if t == "def":
        return "防御"
    if t == "spell":
        return f"呪文:{c.get('name', '')}"
    if t == "flee":
        return "逃走"
    return "—"


def hero_execute_attack():
    global player_defending, battle_log, enemy_shake_timer, bless_next_phys_mult
    sync_battle_enemy_pointer()
    if enemy is None:
        return "あなた:敵がいない"
    if "麻痺" in player.get("status", {}):
        return "あなた:痺れて動けない！"
    tg = enemy.get("name", "敵")
    base = get_atk() + random.randint(0, 10)
    crit = random.random() < physical_crit_chance()
    dmg = int(base * 1.75) if crit else base
    if bless_next_phys_mult > 1.01:
        dmg = int(dmg * bless_next_phys_mult)
        bless_next_phys_mult = 1.0
    enemy["hp"] -= dmg
    battle_add_damage_popup(f"-{dmg}", 470, 168, col=(255, 210, 170))
    if crit:
        battle_trigger_crit_cutin("勇者")
    battle_push_action_fx("勇者", "atk", side="ally", slot=-1, target_slot=battle_target_enemy_index, delay_ms=battle_next_action_delay_ms())
    player_defending = False
    bump_attack_fx(is_crit=crit)
    try_link_combo()
    if random.random() < 0.12 + debuff_proc_bonus() * 0.6:
        apply_status(enemy, "毒")
    sync_battle_enemy_pointer()
    tag = " CRITICAL!" if crit else ""
    return f"あなた:{tg}に攻撃({dmg}){tag}"


def hero_execute_skill(name):
    global player_defending, battle_log, flash_timer, enemy_shake_timer, bless_next_phys_mult
    sync_battle_enemy_pointer()
    skill = skills_data.get(name, {})
    cost = skill.get("cost", 0)
    if "power" in skill and enemy is None:
        return "敵がいない！"
    if player["mp"] < cost:
        return "MPが足りない！"
    player["mp"] -= cost
    register_codex_skill(name)
    msg = ""
    if "power" in skill:
        pw = int(skill["power"]) + int(spell_power_bonus())
        damage = random.randint(max(1, pw - 5), pw + 5)
        damage = int(damage * env_spell_power_mult(name))
        bw, boss_msgs = boss_weakness_spell_mult_and_msgs(name)
        damage = int(damage * bw)
        for p in env_spell_synergy_parts(name) + boss_msgs:
            push_synergy(p)
        enemy["hp"] -= damage
        battle_add_damage_popup(f"-{damage}", 478, 156, col=(170, 225, 255))
        battle_push_action_fx("勇者", "spell", side="ally", slot=-1, target_slot=battle_target_enemy_index, delay_ms=battle_next_action_delay_ms())
        if pw >= 45:
            battle_trigger_skill_cutin("勇者", name)
        bump_magic_fx(pw >= 45)
        try_apply_skill_status(skill)
        sync_battle_enemy_pointer()
        msg = f"あなた:{name}({damage})"
        emit_spell_fx(name)
    elif "heal" in skill:
        heal = int((int(skill["heal"]) + int(_player_build().get("spell_power", 0) * 2)) * tactical_heal_mult())
        player["hp"] = min(player["hp"] + heal, player["max_hp"])
        battle_add_damage_popup(f"+{heal}", 120, 96, col=(150, 255, 185))
        bless_next_phys_mult = max(bless_next_phys_mult, 1.1)
        msg = f"あなた:{name}(+{heal})"
        battle_push_action_fx("勇者", "def", side="ally", slot=-1, target_slot=battle_target_enemy_index, delay_ms=battle_next_action_delay_ms())
        flash_timer = max(flash_timer, 6)
        emit_spell_fx(name)
    else:
        msg = f"あなた:{name}"
    player_defending = False
    try_link_combo()
    return msg


def hero_execute_defend():
    global player_defending
    player_defending = True
    battle_push_action_fx("勇者", "def", side="ally", slot=-1, target_slot=battle_target_enemy_index, delay_ms=battle_next_action_delay_ms())
    return "あなた:防御"


def ally_execute_attack(idx):
    global enemy_shake_timer, bless_next_phys_mult, battle_arcane_followup
    sync_battle_enemy_pointer()
    m = player["party"][idx]
    if m.get("absent"):
        return f"{m.get('name', '仲間')}:不在"
    if enemy is None:
        return f"{m.get('name', '仲間')}:敵がいない"
    if "麻痺" in m.get("status", {}):
        return f"{m['name']}:痺れて動けない！"
    tg = enemy.get("name", "敵")
    base = random.randint(2, m["atk"])
    cc = physical_crit_chance()
    crit = random.random() < min(0.45, cc)
    dmg = int(base * 1.65) if crit else base
    if bless_next_phys_mult > 1.01:
        dmg = int(dmg * bless_next_phys_mult)
        bless_next_phys_mult = 1.0
    if m.get("name") == "弓使い" and battle_arcane_followup:
        dmg = int(dmg * 1.14)
        battle_arcane_followup = False
    enemy["hp"] -= dmg
    battle_add_damage_popup(f"-{dmg}", 500, 180 + idx * 10, col=(255, 210, 170))
    if crit:
        battle_trigger_crit_cutin(m.get("name", "仲間"))
    battle_push_action_fx(
        m.get("name", "仲間"),
        "atk",
        side="ally",
        slot=idx,
        target_slot=battle_target_enemy_index,
        delay_ms=battle_next_action_delay_ms(),
    )
    bump_attack_fx(is_crit=crit)
    try_link_combo()
    if random.random() < 0.08 + debuff_proc_bonus() * 0.45:
        apply_status(enemy, "毒")
    sync_battle_enemy_pointer()
    return f"{m['name']}:{tg}に攻撃({dmg}){' CRIT!' if crit else ''}"


def ally_execute_defend(idx):
    m = player["party"][idx]
    if m.get("absent"):
        return f"{m.get('name', '仲間')}:不在"
    m["defending"] = True
    battle_push_action_fx(
        m.get("name", "仲間"),
        "def",
        side="ally",
        slot=idx,
        target_slot=battle_target_enemy_index,
        delay_ms=battle_next_action_delay_ms(),
    )
    return f"{m['name']}:防御"


def ally_execute_spell(idx, spell_name):
    m = player["party"][idx]
    if m.get("absent"):
        return f"{m.get('name', '仲間')}:不在"
    ok, sn, amt = member_cast_spell(m, spell_name)
    if ok:
        col = (170, 225, 255) if amt < 0 else (150, 255, 185)
        battle_add_damage_popup(f"{amt:+d}", 130, 188 + idx * 88, col=col)
        if spell_name in ("戦鬼解放", "終焉の星", "メテオ", "カオスボルト", "聖域結界"):
            battle_trigger_skill_cutin(m.get("name", "仲間"), spell_name)
        battle_push_action_fx(
            m.get("name", "仲間"),
            "spell",
            side="ally",
            slot=idx,
            target_slot=battle_target_enemy_index,
            delay_ms=battle_next_action_delay_ms(),
        )
        try_link_combo()
        return f"{m['name']}:{sn}({amt})"
    return f"{m['name']}:呪文を唱えられなかった"


def execute_party_round():
    global battle_log, battle_timeline_text
    battle_begin_action_sequence()
    sync_battle_enemy_pointer()
    if enemy is None:
        return
    if not all_commands_set():
        if player.get("party_battle_mode") == "auto":
            battle_log = "勇者のコマンドを選んで ENTER（T:仲間を手動指示）"
        else:
            battle_log = "←→:対象切替  1攻撃 2呪文 3防御 (勇者のみ4逃走)  ENTER:みんなで実行（T:仲間オート）"
        return

    lines = []
    order_names = ["勇者"]
    hc = battle_pending.get("hero")
    if not hc:
        battle_log = "勇者の行動がありません"
        return

    if hc.get("t") == "flee":
        escape_battle()
        return

    # 勇者
    if "麻痺" in player.get("status", {}):
        lines.append("あなた:麻痺でスキップ")
    elif hc["t"] == "atk":
        lines.append(hero_execute_attack())
    elif hc["t"] == "spell":
        lines.append(hero_execute_skill(hc.get("name")))
    elif hc["t"] == "def":
        lines.append(hero_execute_defend())

    if all_enemies_defeated():
        tally_ally_round_from_pending()
        battle_log = (" / ".join(lines) + format_pending_synergy_suffix())[:240]
        win()
        return

    for idx in range(MAX_PARTY_MEMBERS):
        if player["party"][idx].get("absent") or player["party"][idx]["hp"] <= 0:
            continue
        ac = battle_pending.get(idx)
        if not ac:
            continue
        order_names.append(player["party"][idx].get("name", f"仲間{idx+1}"))
        if ac["t"] == "atk":
            lines.append(ally_execute_attack(idx))
        elif ac["t"] == "spell":
            lines.append(ally_execute_spell(idx, ac.get("name")))
        elif ac["t"] == "def":
            lines.append(ally_execute_defend(idx))

        if all_enemies_defeated():
            tally_ally_round_from_pending()
            battle_log = (" / ".join(lines) + format_pending_synergy_suffix())[:240]
            win()
            return

    tally_ally_round_from_pending()
    battle_timeline_text = "行動順: " + " → ".join(order_names) if order_names else ""
    battle_log = (" / ".join(lines) + format_pending_synergy_suffix())[:240]
    enemy_turn()


shop_data = load_json("shop.json", {"shop_items": []})
SHOP_CATALOG_ALL = shop_data.get("shop_items", [])

# 獲得EXPの全体倍率（レベル上がりやすさの調整）
HERO_EXP_GAIN_MULT = 0.62


def shop_catalog():
    f = floor_number
    return [it for it in SHOP_CATALOG_ALL if int(it.get("min_floor", 1)) <= f]


def _chest_weapon_armor_candidates():
    return [it for it in shop_catalog() if it.get("type") in ("weapon", "armor") and it.get("name")]


def _chest_healing_consumable_candidates():
    """HP/MP/パーティ回復系の消耗品（宝箱の主産出）。"""
    out = []
    for it in shop_catalog():
        if it.get("type") != "consumable" or not it.get("name"):
            continue
        eff = str(it.get("effect", "")).replace(" ", "")
        if "hp+" in eff or "mp+" in eff or "party_hp+" in eff:
            out.append(it)
    return out


def _chest_tier_band(floor_n):
    return max(0, min(14, int(floor_n) // 7))


def _chest_healing_weight(it, f):
    mf = int(it.get("min_floor", 1))
    if mf > f:
        return 0.0
    base = 220.0 / (max(8, int(it.get("price", 40))) ** 0.72)
    tier = _chest_tier_band(f)
    ideal_mf = max(1, min(f, 1 + int(tier * 2.4)))
    spread = 5.5 + f / 22.0
    proximity = math.exp(-((mf - ideal_mf) ** 2) / (2 * spread * spread))
    climb = 1.0 + min(2.4, (f / 100.0) * (mf / max(8, f * 0.62)))
    return base * (0.4 + 1.65 * proximity) * climb


def _chest_weapon_armor_weight(it, f):
    mf = int(it.get("min_floor", 1))
    if mf > f:
        return 0.001
    price = int(it.get("price", 40))
    rank = price + mf * 14
    target = 42 + f * 5.5
    return math.exp(-abs(rank - target) / (70 + f * 0.95)) + 0.14


def _roll_chest_loot():
    """宝箱: 回復中心・階が上がるほど良い品が出やすい。低確率で武器・防具、一部は金。"""
    f = floor_number
    wc = _chest_weapon_armor_candidates()
    hc = _chest_healing_consumable_candidates()
    r = random.random()
    if r < 0.065 and wc:
        weights = [_chest_weapon_armor_weight(w, f) for w in wc]
        return "item", random.choices(wc, weights=weights, k=1)[0]["name"]
    if r < 0.115:
        gld = 15 + f * 2 + random.randint(0, 18 + f // 5)
        return "gold", gld
    if hc:
        weights = [_chest_healing_weight(it, f) for it in hc]
        return "item", random.choices(hc, weights=weights, k=1)[0]["name"]
    if wc:
        weights = [_chest_weapon_armor_weight(w, f) for w in wc]
        return "item", random.choices(wc, weights=weights, k=1)[0]["name"]
    gld = 15 + f * 2 + random.randint(0, 18 + f // 5)
    return "gold", gld


def apply_item_effect(item):
    kind = item.get("type")
    if kind == "weapon":
        player["weapon"] = item["name"]
        return f"{item['name']}を装備した"
    if kind == "armor":
        player["armor"] = item["name"]
        return f"{item['name']}を装備した"
    if kind == "consumable":
        effect = item.get("effect", "").replace(" ", "")
        for seg in effect.split("|"):
            if not seg:
                continue
            if seg.startswith("party_hp+"):
                amt = int(seg.replace("party_hp+", ""))
                for m in player["party"][:MAX_PARTY_MEMBERS]:
                    if m["hp"] > 0 and not m.get("absent"):
                        m["hp"] = min(m["max_hp"], m["hp"] + amt)
            elif "hp+" in seg:
                amt = int(seg.replace("hp+", ""))
                player["hp"] = min(player["max_hp"], player["hp"] + amt)
            elif "mp+" in seg:
                amt = int(seg.replace("mp+", ""))
                player["mp"] = min(player["max_mp"], player["mp"] + amt)
        return f"{item['name']}を使った"
    return f"{item['name']}を使った"


def buy_shop_item(idx):
    cat = shop_catalog()
    if idx < 0 or idx >= len(cat):
        return "その商品はありません"
    item = cat[idx]
    if player["gold"] < item["price"]:
        return "ゴールドが足りない"
    player["gold"] -= item["price"]
    if item.get("type") == "consumable":
        return apply_item_effect(item)
    grant_inventory_item(item["name"])
    return f"{item['name']}をインベントリに追加した"


def handle_shop_purchase_choice(idx, equip_now):
    cat = shop_catalog()
    if idx < 0 or idx >= len(cat):
        return "その商品はありません"
    item = cat[idx]
    if player["gold"] < item["price"]:
        return "ゴールドが足りない"
    player["gold"] -= item["price"]
    if equip_now:
        return apply_item_effect(item)
    grant_inventory_item(item["name"])
    return f"{item['name']}をインベントリに入れた"


def shop_steal_selected(idx):
    global mode, selected_shop_item_index
    cat = shop_catalog()
    if idx < 0 or idx >= len(cat):
        return "その商品はない"
    item = cat[idx]
    personality_apply({"greed": 3, "morality": -4, "honor": -3, "cunning": 2})
    if item.get("type") == "consumable":
        grant_inventory_item(item["name"])
    else:
        grant_inventory_item(item["name"])
    selected_shop_item_index = -1
    mode = "town"
    return f"{item['name']}を盗み出した…指先が震える。"


def try_move_next_floor():
    global floor_number, enemies, battle_log, mode, pending_floor_move, tiles, TOWN_POS, STAIRS_POS, pending_floor_buff_tier
    if not pending_floor_move:
        mode = "world"
        return
    if floor_number % 10 == 0:
        boss_left = any(v.get("type") == "boss" for v in enemies.values())
        if boss_left:
            battle_log = "この階はボスを倒さないと進めない！"
            mode = "world"
            pending_floor_move = False
            return
    if floor_number < 100:
        floor_number += 1
        player["route_mode"] = None
        player["route_for_floor"] = -1
        player["torch_turns"] = 0
        tiles, TOWN_POS, STAIRS_POS = generate_map(floor_number)
        enemies = generate_floor(floor_number)
        player["x"], player["y"] = 1.0, 1.0
        world_reset_movement_state()
        battle_log = f"{floor_number}階層へ進んだ"
        save(show_toast=False)
        tier = (floor_number - 1) // 10
        if floor_number > 1 and floor_number % 10 == 1 and tier not in player.get("floor_buff_picked", []):
            pending_floor_buff_tier = tier
            mode = "floor_buff"
            pending_floor_move = False
            return
    mode = "world"
    pending_floor_move = False

# ===== モード =====
mode = "title"  # title / story / world / battle / party / town / shop / shop_choice / stairs_confirm / inventory / event_choice / ending / floor_buff / companion_crisis / build_menu / codex

# ===== プレイヤー =====
player = {
    "x":1,"y":1,
    "hp":100,"max_hp":100,
    "mp":50,"max_mp":50,
    "atk":10,
    "level":1,
    "exp":0,
    "exp_next":62,
    "gold":100,
    "skills":["ファイア"],
    "weapon":None,
    "armor":None,
    "job":"冒険者",
    "traits":[],
    "relics":[],
    "party":[
        {"name":"戦士","hp":80,"max_hp":80,"atk":8,"skills":[],"status":{}},
        {"name":"僧侶","hp":60,"max_hp":60,"atk":5,"skills":[],"status":{}},
        {"name":"弓使い","hp":70,"max_hp":70,"atk":7,"skills":[],"status":{}},
        {"name":"魔法使い","hp":55,"max_hp":55,"atk":6,"skills":[],"status":{}}
    ],
    "party_battle_mode": "manual",
}

# ===== データ =====
skills_data = load_json("skills.json", {"ファイア": {"cost": 0, "power": 30, "unlock": 1}})


# 技ごとのカットイン演出設定（強技は色とタイトルを変えて見せ場を作る）
SKILL_CUTIN_CONFIG = {
    # 勇者
    "フレイム":       ("FLAME",       (200, 70, 40),   22),
    "サンダーボルト": ("THUNDER BOLT",(80, 130, 220),  22),
    "ポイズンストーム":("POISON STORM",(70, 170, 90),  22),
    "雷脈":           ("CHAIN BOLT",  (90, 150, 220),  24),
    "メガヒール":     ("MEGA HEAL",   (90, 200, 150),  18),
    # 戦士
    "ソードダンス":   ("SWORD DANCE", (200, 80, 110),  22),
    "戦鬼解放":       ("BERSERK",     (220, 50, 40),   28),
    # 僧侶
    "守護の鐘":       ("AEGIS BELL",  (220, 180, 70),  20),
    "聖域結界":       ("SANCTUARY",   (210, 220, 240), 26),
    # 弓使い
    "貫通狙撃":       ("PIERCE",      (210, 220, 240), 22),
    "嵐の矢":         ("ARROW STORM", (130, 170, 220), 24),
    # 魔法使い
    "メテオ":         ("METEOR",      (220, 130, 60),  26),
    "カオスボルト":   ("CHAOS BOLT",  (180, 90, 220),  24),
    "終焉の星":       ("APOCALYPSE",  (40, 30, 70),    32),
}


def trigger_skill_cutin_if_big(actor_name, spell_name):
    """設定があれば、その技専用のカットインを発火する。"""
    cfg = SKILL_CUTIN_CONFIG.get(spell_name)
    if not cfg:
        return False
    title, accent, timer = cfg
    battle_trigger_crit_cutin(actor_name, title=title, accent=accent, timer=timer)
    return True


def emit_spell_fx(spell_name, caster_name="勇者"):
    """呪文・術ごとに、固有のVFXとSEを発火する。大技はカットインも入れる。"""
    # ── 勇者の魔法 ──
    if spell_name == "ファイア":
        trigger_battle_vfx("fire_wave", 20)
        play_battle_se("fire")
    elif spell_name == "フレイム":
        trigger_battle_vfx("fire_pillar", 24)
        play_battle_se("fire")
    elif spell_name == "サンダーボルト":
        trigger_battle_vfx("thunder_bolt", 22)
        play_battle_se("thunder")
    elif spell_name == "雷脈":
        trigger_battle_vfx("thunder_chain", 26)
        play_battle_se("thunder")
    elif spell_name == "ポイズンストーム":
        trigger_battle_vfx("venom_storm", 26)
        play_battle_se("magic")
    elif spell_name == "メガヒール" or spell_name == "ヒール":
        trigger_battle_vfx("heal_aurora" if spell_name == "メガヒール" else "heal", 22)
        play_battle_se("heal")
    # ── 戦士の技 ──
    elif spell_name == "ブレイブスラッシュ":
        trigger_battle_vfx("cross_slash", 18)
        play_battle_se("hit")
    elif spell_name == "ソードダンス":
        trigger_battle_vfx("sword_dance", 22)
        play_battle_se("hit")
    elif spell_name == "戦鬼解放":
        trigger_battle_vfx("berserk_burst", 28)
        play_battle_se("fire")
        play_battle_se("hit")
    # ── 僧侶の技 ──
    elif spell_name == "瘴糸":
        trigger_battle_vfx("cursed_threads", 20)
        play_battle_se("magic")
    elif spell_name == "ホーリーライト":
        trigger_battle_vfx("holy_ray", 22)
        play_battle_se("heal")
    elif spell_name == "守護の鐘":
        trigger_battle_vfx("bell_wave", 22)
        play_battle_se("heal")
    elif spell_name == "聖域結界":
        trigger_battle_vfx("sanctuary_dome", 28)
        play_battle_se("heal")
        play_battle_se("magic")
    # ── 弓使いの技 ──
    elif spell_name == "トリプルアロー":
        trigger_battle_vfx("triple_arrow", 18)
        play_battle_se("hit")
    elif spell_name == "貫通狙撃":
        trigger_battle_vfx("pierce_shot", 22)
        play_battle_se("hit")
    elif spell_name == "嵐の矢":
        trigger_battle_vfx("arrow_storm", 26)
        play_battle_se("hit")
    # ── 魔法使いの技 ──
    elif spell_name == "メテオ":
        trigger_battle_vfx("meteor_strike", 32)
        play_battle_se("fire")
        play_battle_se("magic")
    elif spell_name == "カオスボルト":
        trigger_battle_vfx("chaos_storm", 26)
        play_battle_se("thunder")
        play_battle_se("magic")
    elif spell_name == "終焉の星":
        trigger_battle_vfx("apocalypse", 36)
        play_battle_se("fire")
        play_battle_se("magic")
    else:
        # フォールバック: skills.json などの汎用パラメタから推測
        info = skills_data.get(spell_name, {})
        if "heal" in info:
            trigger_battle_vfx("heal", 18)
            play_battle_se("heal")
        elif "power" in info:
            pw = int(info.get("power", 30))
            trigger_battle_vfx("inferno" if pw >= 50 else "arcane", 22 if pw >= 50 else 16)
            play_battle_se("magic")

    # 大技には固有のカットインを重ねて見せ場を作る
    trigger_skill_cutin_if_big(caster_name, spell_name)


def spell_deals_hp_damage_to_enemy(spell_name):
    if spell_name in HEAL_MEMBER_SPELLS or spell_name in HEAL_PLAYER_SKILLS:
        return False
    if spell_name in ALLY_DAMAGE_MEMBER_SPELLS:
        return True
    return "power" in skills_data.get(spell_name, {})


def push_synergy(msg):
    global pending_synergy_notes
    if not msg:
        return
    if msg in pending_synergy_notes:
        return
    if len(pending_synergy_notes) >= 6:
        return
    pending_synergy_notes.append(msg)


def format_pending_synergy_suffix():
    global pending_synergy_notes
    if not pending_synergy_notes:
        return ""
    out = "".join(f" [{p}]" for p in pending_synergy_notes)
    pending_synergy_notes.clear()
    return out


def clear_pending_synergy():
    global pending_synergy_notes
    pending_synergy_notes.clear()


def env_spell_synergy_parts(spell_name):
    parts = []
    w = player.get("world_weather", "clear")
    seal = player.get("seal")
    if w == "rain" and spell_name in LIGHTNING_SKILLS:
        parts.append("雨×雷:威力UP")
    if seal == "雷" and spell_name in LIGHTNING_SKILLS and w == "rain":
        parts.append("雷刻印:相乗り")
    if seal == "火" and spell_name in FIRE_SKILLS:
        parts.append("火刻印:火力UP")
    return parts


def boss_weakness_spell_mult_and_msgs(spell_name):
    """ボスは戦闘開始時に弱点が1種類。術ダメージのみ（通常攻撃には付かない）。"""
    if enemy is None or enemy.get("type") != "boss":
        return 1.0, []
    tag = enemy.get("weakness_tag")
    if not tag:
        return 1.0, []
    seal = player.get("seal")
    mult = 1.0
    msgs = []
    if tag == "雷" and spell_name in LIGHTNING_SKILLS:
        mult *= 1.34
        msgs.append("弱点:雷")
        if seal == "雷":
            mult *= 1.1
            msgs.append("雷刻印連動")
    elif tag == "火" and spell_name in FIRE_SKILLS:
        mult *= 1.34
        msgs.append("弱点:火")
        if seal == "火":
            mult *= 1.1
            msgs.append("火刻印連動")
    elif tag == "聖" and seal == "光" and spell_deals_hp_damage_to_enemy(spell_name):
        mult *= 1.34
        msgs.append("弱点:聖×光刻印")
    return min(1.78, mult), msgs


MEMBER_SPELL_DESC = {
    "ブレイブスラッシュ": "敵単体に物理に近い斬撃ダメージ。",
    "ソードダンス": "剣閃で中〜大ダメージ。",
    "戦鬼解放": "大技。高火力の一撃。",
    "瘴糸": "敵にダメージ＋毒付与を狙う。",
    "ホーリーライト": "勇者のHPを回復。",
    "守護の鐘": "生存している仲間全員のHPを少し回復。",
    "聖域結界": "勇者と仲間に大きな回復。",
    "トリプルアロー": "小ダメージを3回。期待値は高め。",
    "貫通狙撃": "単体に大きな一射。",
    "嵐の矢": "複数ヒットで敵を削る。",
    "メテオ": "隕石で敵単体に大ダメージ。",
    "カオスボルト": "混沌の雷で高火力。",
    "終焉の星": "消費MP大。極大ダメージ。",
}


def get_spell_description(spell_name):
    if spell_name in MEMBER_SPELL_DESC:
        return MEMBER_SPELL_DESC[spell_name]
    return skills_data.get(spell_name, {}).get("desc", "効果のある呪文。")


equipment_data = load_json("equipment.json", {})
enemy_catalog = load_json("enemies.json", {"スライム": {"hp": 20, "attack": 5, "exp": 10}})
# 敵名とドット絵ファイル（generate_assets で生成 / 同名で差し替え可）
ENEMY_FACE_FILES = {
    "スライム": "enemy_slime.png",
    "ゴブリン": "enemy_goblin.png",
    "オーク": "enemy_orc.png",
    "ウルフ": "enemy_wolf.png",
    "スケルトン": "enemy_skeleton.png",
    "バット": "enemy_bat.png",
    "ゴーレム": "enemy_golem.png",
    "ドラゴン": "enemy_dragon.png",
    "グール": "enemy_ghoul.png",
    "ナイト": "enemy_knight.png",
    "ウィッチ": "enemy_witch.png",
    "ミミック": "enemy_mimic.png",
}
enemy_named_surfaces = {}
story_data = load_json("story_branches.json", {"story_paths": []})
story_nodes = {n["id"]: n for n in story_data.get("story_paths", [])}
if story_current_id is None:
    story_current_id = "start" if "start" in story_nodes else None

weapons = {name: data.get("attack", 0) for name, data in equipment_data.get("weapon", {}).items()}
armors = {name: data.get("defense", 0) for name, data in equipment_data.get("armor", {}).items()}
if not weapons:
    weapons = {"木の剣": 3, "鉄の剣": 6}
if not armors:
    armors = {"布の服": 2, "鉄の鎧": 5}

# ===== 画像 =====
images = {
    "grass": load_image("grass.png"),
    "forest": load_image("forest.png"),
    "stairs": load_image("stairs.png"),
    "spring": load_image("spring.png"),
    "player": load_image("player.png"),
    "player_walk1": load_image("player_walk1.png"),
    "player_walk2": load_image("player_walk2.png"),
    "town": load_image("town.png"),
    "ui_panel": load_image("ui_panel.png"),
    "enemy_1": load_image("enemy_1.png") or load_image("enemy.png"),
    "enemy_2": load_image("enemy_2.png"),
    "enemy_3": load_image("enemy_3.png"),
    "enemy_4": load_image("enemy_4.png"),
    "enemy_5": load_image("enemy_5.png"),
    "boss_1": load_image("boss_1.png") or load_image("boss.png"),
    "boss_2": load_image("boss_2.png"),
    "boss_3": load_image("boss_3.png"),
    "boss_final": load_image("boss_final.png"),
}


def load_cutin_wide(filename):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, (440, 150))
    except pygame.error:
        return None


images["boss_cutin"] = load_cutin_wide("boss_cutin.png")
party_portraits = {name: load_portrait(fn, 40) for name, fn in PARTY_FACE_FILES.items()}
for _ename, _fn in ENEMY_FACE_FILES.items():
    surf = load_image(_fn)
    if surf:
        enemy_named_surfaces[_ename] = surf

MINI_SCALE = min(VIEWPORT_W / (W * TILE), VIEWPORT_H / (H * TILE))
MINI_CELL = max(2, int(TILE * MINI_SCALE))


def _mk_mini(img):
    if img is None:
        return None
    return pygame.transform.scale(img, (MINI_CELL, MINI_CELL))


mini_tile = {
    0: _mk_mini(images["grass"]),
    1: _mk_mini(images["forest"]),
    2: _mk_mini(images["town"]),
    3: _mk_mini(images["forest"]),
    4: _mk_mini(images["stairs"]),
    5: _mk_mini(images["spring"]),
}


def load_title_adventure_banner():
    """タイトル用ワイドイラスト（旅立ちの雰囲気）。無ければ None。"""
    path = os.path.join(ASSETS_DIR, "title_adventure.png")
    if not os.path.isfile(path):
        return None
    try:
        raw = pygame.image.load(path).convert()
        max_w = min(WIDTH - 72, 928)
        max_h = 240
        rw, rh = raw.get_size()
        sc = min(max_w / rw, max_h / rh)
        nw, nh = max(1, int(rw * sc)), max(1, int(rh * sc))
        return pygame.transform.scale(raw, (nw, nh))
    except pygame.error:
        return None


_title_adventure_banner_ready = False
title_adventure_banner = None


def _ensure_title_adventure_banner():
    """タイトル用ワイド絵はタイトル画面初表示まで遅延。"""
    global title_adventure_banner, _title_adventure_banner_ready
    if _title_adventure_banner_ready:
        return title_adventure_banner
    _title_adventure_banner_ready = True
    title_adventure_banner = load_title_adventure_banner()
    return title_adventure_banner


def procedural_enemy_sprite(enemy_dict):
    """16×16 を拡大したオリジナルドット風（外部キャラクターは使用しない）"""
    name = str(enemy_dict.get("name", "?"))
    seed = sum((i + 1) * ord(c) for i, c in enumerate(name)) % 100003
    rng = random.Random(seed)
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    boss = enemy_dict.get("type") == "boss"
    r, g, b = rng.randint(45, 170), rng.randint(40, 150), rng.randint(50, 170)
    if boss:
        r, g, b = 130, 28, 50
    pygame.draw.ellipse(s, (r, g, b), (2, 4, 12, 10))
    er, eg, eb = min(255, r + 70), min(255, g + 60), min(255, b + 50)
    pygame.draw.rect(s, (er, eg, eb), (5, 7, 2, 2))
    pygame.draw.rect(s, (er, eg, eb), (9, 7, 2, 2))
    if boss:
        pygame.draw.polygon(s, (210, 190, 60), [(8, 2), (4, 6), (12, 6)])
        pygame.draw.polygon(s, (70, 35, 90), [(3, 12), (8, 16), (13, 12)])
    else:
        pygame.draw.rect(s, (max(0, r - 40), max(0, g - 40), max(0, b - 40)), (6, 11, 4, 3))
    return pygame.transform.scale(s, (72, 72))


def procedural_ally_sprite(job_id, out_w=34, out_h=34):
    palettes = {
        "戦士": ((95, 130, 190), (150, 85, 65), (238, 215, 195)),
        "僧侶": ((235, 235, 245), (175, 155, 85), (88, 88, 115)),
        "弓使い": ((115, 165, 105), (85, 125, 190), (225, 205, 165)),
        "魔法使い": ((130, 85, 170), (195, 195, 255), (75, 55, 110)),
    }
    robes, trim, skin = palettes.get(job_id, ((115, 115, 135), (75, 75, 95), (215, 195, 175)))
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    pygame.draw.rect(s, robes, (4, 6, 8, 9))
    pygame.draw.rect(s, skin, (6, 3, 4, 4))
    pygame.draw.rect(s, trim, (5, 10, 6, 2))
    pygame.draw.rect(s, (32, 32, 42), (6, 5, 2, 1))
    pygame.draw.rect(s, (32, 32, 42), (9, 5, 2, 1))
    return pygame.transform.scale(s, (out_w, out_h))


_world_player_marker_cache = {}


def procedural_world_player_sprite(out_px, walk=0, facing=(0, 1)):
    """ワールドマップ用・勇者のミニドット（16pxベースを拡大・上下視点）。"""
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    fx, fy = facing
    leg_shift = -1 if walk % 2 == 0 else 1
    body_col = (78, 125, 228)
    trim_col = (188, 148, 72)
    pygame.draw.rect(s, (118, 74, 52), (5, 2, 6, 4))
    pygame.draw.rect(s, (248, 212, 188), (5, 5, 6, 4))
    if fy < 0:
        pygame.draw.rect(s, (54, 48, 76), (5, 5, 6, 2))
    else:
        pygame.draw.rect(s, (42, 38, 58), (6, 6, 2, 2))
        pygame.draw.rect(s, (42, 38, 58), (9, 6, 2, 2))
    pygame.draw.rect(s, body_col, (4, 9, 8, 6))
    pygame.draw.rect(s, trim_col, (4, 12, 8, 1))
    if fx != 0:
        arm_x = 3 if fx < 0 else 11
        pygame.draw.rect(s, (232, 238, 255), (arm_x, 9, 2, 2))
        pygame.draw.rect(s, (255, 242, 190), (arm_x, 11, 2, 4))
    else:
        pygame.draw.rect(s, (232, 238, 255), (12, 8, 2, 2))
        pygame.draw.rect(s, (255, 242, 190), (12, 10, 2, 5))
    pygame.draw.rect(s, (52, 62, 92), (5 + leg_shift, 14, 2, 2))
    pygame.draw.rect(s, (52, 62, 92), (9 - leg_shift, 14, 2, 2))
    return pygame.transform.scale(s, (max(4, out_px), max(4, out_px)))


def world_player_marker_surface(px, walk=0, facing=(0, 1)):
    key = (px, walk % 2, int(facing[0]), int(facing[1]))
    if key not in _world_player_marker_cache:
        _world_player_marker_cache[key] = procedural_world_player_sprite(px, walk=walk, facing=facing)
    return _world_player_marker_cache[key]


_item_icon_map_data = load_json("item_icon_map.json", {})
_icache_icons = {}

# ===== セーブ =====
def refresh_story_branches():
    global story_data, story_nodes
    story_data = load_json("story_branches.json", {"story_paths": []})
    story_nodes = {n["id"]: n for n in story_data.get("story_paths", [])}


def save(show_toast=True):
    """show_toast=False でオートセーブ（トーストなし）。失敗時は必ずトースト。"""
    d = os.path.dirname(os.path.abspath(SAVE_PATH)) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", prefix="rpg_save_", dir=d, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(player, f, ensure_ascii=False)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        os.replace(tmp_path, SAVE_PATH)
        if show_toast:
            player["_toast_save"] = "セーブしました。"
    except Exception as e:
        player["_toast_save"] = f"セーブ失敗: {e}"


def load():
    global player
    if not os.path.exists(SAVE_PATH):
        ensure_player_state()
        refresh_story_branches()
        return
    try:
        with open(SAVE_PATH, encoding="utf-8") as f:
            raw = f.read()
        player = json.loads(raw)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        player["_toast_map"] = f"セーブが読めません（壊れている可能性）: {e}"
        ensure_player_state()
        refresh_story_branches()
        apply_sound_effect_settings()
        return
    ensure_player_state()
    refresh_story_branches()
    apply_sound_effect_settings()
    player["_toast_map"] = "ロードしました。扉・霧・ギミックはフロア生成時の状態です（再入場で更新）。"

# ===== 敵 =====
enemy=None
enemy_pos=None
battle_enemies = []
battle_target_enemy_index = 0


def living_enemy_indices():
    if not battle_enemies:
        return []
    return [i for i, e in enumerate(battle_enemies) if e and e.get("hp", 0) > 0]


def sync_battle_enemy_pointer():
    global enemy, battle_target_enemy_index
    liv = living_enemy_indices()
    if not liv:
        enemy = None
        return
    if battle_target_enemy_index not in liv:
        battle_target_enemy_index = liv[0]
    enemy = battle_enemies[battle_target_enemy_index]


def cycle_battle_enemy_target(delta):
    global battle_target_enemy_index
    liv = living_enemy_indices()
    if len(liv) <= 1:
        return
    try:
        j = liv.index(battle_target_enemy_index)
    except ValueError:
        battle_target_enemy_index = liv[0]
        sync_battle_enemy_pointer()
        return
    battle_target_enemy_index = liv[(j + delta) % len(liv)]
    sync_battle_enemy_pointer()


def all_enemies_defeated():
    return not living_enemy_indices()


def build_enemy_object_from_spawn_data(data):
    """マップ／スポーン用辞書から戦闘用敵オブジェクト（1体分）を生成。"""
    mh = int(data.get("max_hp", data.get("hp", 10)))
    hp = int(data.get("hp", mh))
    ed = {
        "name": data.get("name", "敵"),
        "hp": hp,
        "max_hp": mh,
        "atk": int(data.get("atk", 5)),
        "exp": int(data.get("exp", 15)),
        "type": data.get("type", "normal"),
        "image_key": floor_enemy_image_key(floor_number, data.get("type", "normal")),
        "status": {},
        "sprite": enemy_named_surfaces.get(data.get("name")),
    }
    if ed.get("type") == "boss":
        ed["weakness_tag"] = random.choice(("雷", "聖", "火"))
    else:
        ed["weakness_tag"] = None
    return ed


def set_battle_enemies_from_spawn_list(spawn_list):
    global battle_enemies, battle_target_enemy_index, enemy, boss_intro_timer, bless_next_phys_mult, battle_arcane_followup
    bless_next_phys_mult = 1.0
    battle_arcane_followup = False
    clear_pending_synergy()
    battle_enemies = []
    for raw in spawn_list:
        d = dict(raw) if isinstance(raw, dict) else {}
        ed = build_enemy_object_from_spawn_data(d)
        battle_enemies.append(ed)
        et = "boss" if ed.get("type") == "boss" else ("rare" if d.get("rare") else "normal")
        register_codex_enemy(ed.get("name", "敵"), et)
    battle_target_enemy_index = 0
    sync_battle_enemy_pointer()
    boss_intro_timer = 140 if any(e.get("type") == "boss" for e in battle_enemies) else 0
    for member in player["party"][:MAX_PARTY_MEMBERS]:
        member["defending"] = False
    _rl_ag = _ensure_enemy_rl_agent()
    if _rl_ag and len(battle_enemies) == 1:
        _rl_ag.begin_battle()

# ===== マップ =====
enemies = generate_floor(floor_number)

ensure_player_state()

# ===== 計算 =====
def get_atk():
    base=player["atk"]
    if player["weapon"]:
        base+=weapons.get(player["weapon"],0)
    base += player.get("perm_bonus_atk", 0)
    base += player.get("_explore_atk_bonus", 0)
    return base

def get_def():
    d = 0
    if player["armor"]:
        d += armors.get(player["armor"],0)
    d += player.get("perm_bonus_def", 0)
    d -= player.get("_explore_curse_def", 0)
    return max(0, d)


def enemy_rl_finish_battle(terminal=False):
    global enemy_rl_deferred
    if enemy_rl_agent is None or encode_state is None:
        enemy_rl_deferred = None
        return
    if enemy_rl_deferred is None:
        return
    s, a, r = enemy_rl_deferred
    if terminal:
        enemy_rl_agent.flush_terminal(s, a, r)
    enemy_rl_deferred = None
    try:
        enemy_rl_agent.save()
    except OSError:
        pass


def tally_ally_round_from_pending():
    global battle_ally_atk_cnt, battle_ally_def_cnt, battle_ally_sp_cnt
    for k in battle_plan_units:
        if k == "hero":
            continue
        cmd = battle_pending.get(k)
        if not cmd:
            continue
        t = cmd.get("t")
        if t == "atk":
            battle_ally_atk_cnt += 1
        elif t == "def":
            battle_ally_def_cnt += 1
        elif t == "spell":
            battle_ally_sp_cnt += 1


# ===== 状態異常 =====
def apply_status(target, status):
    if target is None or not isinstance(target, dict):
        return
    target.setdefault("status",{})
    target["status"][status]=3

def update_status(target):
    if target is None or not isinstance(target, dict):
        return
    if "status" not in target: return
    remove=[]
    for s in target["status"]:
        target["status"][s]-=1
        if s=="毒":
            target["hp"]-=3
        if target["status"][s]<=0:
            remove.append(s)
    for r in remove:
        del target["status"][r]

def try_link_combo():
    global battle_log
    sync_battle_enemy_pointer()
    liv = living_enemy_indices()
    if not liv:
        return
    alive = [m for m in player["party"][:MAX_PARTY_MEMBERS] if m["hp"] > 0 and not m.get("absent")]
    if len(alive) < 2:
        return
    if random.random() > 0.34:
        return
    bonus = sum(m["atk"] for m in alive) // 3 + max(0, floor_number // 10)
    ti = random.choice(liv)
    battle_enemies[ti]["hp"] -= bonus
    sync_battle_enemy_pointer()
    battle_log = (battle_log + f" / 連携撃→{battle_enemies[ti].get('name','敵')}({bonus})")[:220]


def escape_battle():
    global mode, battle_log, battle_music_started, battle_enemies, battle_target_enemy_index, random_encounter_cooldown, _battle_bgm_pending
    sync_battle_enemy_pointer()
    if enemy is None:
        return
    has_boss = any(e.get("type") == "boss" for e in battle_enemies)
    if has_boss:
        if random.random() < 0.65:
            battle_log = "ボスからは逃げられない…！"
            enemy_turn()
            return
    else:
        if random.random() < 0.35:
            battle_log = "逃げられなかった！"
            enemy_turn()
            return
    if any(e.get("type") == "boss" for e in battle_enemies):
        personality_apply({"bravery": -2, "honor": -1})
    enemy_rl_finish_battle(True)
    if enemy_pos in enemies:
        del enemies[enemy_pos]
    player["_battle_wave"] = None
    player["_battle_wave_idx"] = 0
    battle_enemies.clear()
    battle_target_enemy_index = 0
    music_silence_immediate()
    battle_music_started = False
    _battle_bgm_pending = False
    advance_world_tactics()
    mode = "world"
    battle_log = "逃走した！"
    random_encounter_cooldown = 20
    reset_battle_plan_state()


# ===== 戦闘 =====
def start_battle(pos):
    global mode, enemy, enemy_pos, battle_log, player_defending, battle_action_target_index, boss_intro_timer
    global battle_ally_atk_cnt, battle_ally_def_cnt, battle_ally_sp_cnt, enemy_rl_deferred
    global battle_ui_shake, slash_timer, crit_slow_timer, battle_music_started, _battle_bgm_pending
    global bless_next_phys_mult, battle_arcane_followup, battle_vfx, battle_action_fx, battle_timeline_text, battle_damage_popups, battle_crit_cutin
    music_silence_immediate()
    bless_next_phys_mult = 1.0
    battle_arcane_followup = False
    clear_pending_synergy()
    battle_ally_atk_cnt = battle_ally_def_cnt = battle_ally_sp_cnt = 0
    enemy_rl_deferred = None
    battle_ui_shake = slash_timer = crit_slow_timer = 0
    battle_vfx = None
    battle_action_fx = []
    battle_timeline_text = ""
    battle_damage_popups = []
    battle_crit_cutin = {"timer": 0, "name": "", "title": "CRITICAL", "accent": (165, 28, 46)}
    enemy_pos = pos
    if pos != (-1, -1):
        player["_battle_wave"] = None
        player["_battle_wave_idx"] = 0
        spawn_list = [enemies[pos]]
    elif player.get("_battle_wave"):
        spawn_list = list(player["_battle_wave"])
        player["_battle_wave"] = None
        player["_battle_wave_idx"] = 0
    else:
        spawn_list = [enemies[pos]]
    set_battle_enemies_from_spawn_list(spawn_list)
    player["_battle_phase_snapshot"] = player.get("world_phase", "day")
    wk = ""
    if enemy and enemy.get("type") == "boss" and enemy.get("weakness_tag"):
        wk = f" ボス弱点【{enemy['weakness_tag']}】（術・刻印で伸ばす）"
    multi = ""
    if len(battle_enemies) > 1:
        multi = f" 敵{len(battle_enemies)}体 Q/Eで狙い"
    battle_log = (
        "戦闘開始！T:仲間オート⇔手動  ←→:仲間対象  Q/E:敵ターゲット  ENTER  "
        + tactics_short_summary()
        + wk
        + multi
    )
    player_defending = False
    battle_action_target_index = 0
    reset_battle_plan_state()
    mode = "battle"
    _battle_bgm_pending = True


ENEMY_SKILL_VFX = {
    # スキル文字列 → (VFX, タイトル, アクセント色, ダメージ倍率, 追加状態)
    "firebreath":  ("fire_wave",       "FIRE BREATH",  (220, 90, 50),   1.55, None),
    "frostbolt":   ("thunder_bolt",    "FROST BOLT",   (110, 180, 230), 1.30, "麻痺"),
    "powerattack": ("phys_strong",     "POWER STRIKE", (230, 200, 120), 1.65, None),
    "doublehit":   ("phys",            "DOUBLE HIT",   (230, 120, 90),  0.80, None),  # 2 回当たる
    "bonecurse":   ("cursed_threads",  "BONE CURSE",   (170, 120, 220), 1.10, "毒"),
    "sonic":       ("arcane",          "SONIC",        (200, 180, 240), 1.20, None),
    "poison":      ("venom_storm",     "POISON",       (90, 200, 110),  1.10, "毒"),
    "shield":      ("bell_wave",       "AEGIS",        (230, 200, 120), 0.70, None),  # 守り
    "disguise":    ("arcane",          "DISGUISE",     (210, 170, 90),  1.35, None),
}


def enemy_lookup_skill_id(enemy_name):
    """敵カタログから skill 文字列を取得（不明は 'none'）。"""
    info = enemy_catalog.get(enemy_name) if isinstance(enemy_catalog, dict) else None
    sk = info.get("skill") if isinstance(info, dict) else None
    if isinstance(sk, str) and sk and sk != "none":
        return sk
    return None


def maybe_use_enemy_skill(enemy_dict):
    """敵が今ターンに固有スキルを使うかを判定し、設定を返す（使わなければ None）。"""
    sk_id = enemy_lookup_skill_id(enemy_dict.get("name", ""))
    if not sk_id:
        return None
    cfg = ENEMY_SKILL_VFX.get(sk_id)
    if not cfg:
        return None
    # 階層に応じて使う頻度を上げる（敵の歯ごたえアップ）
    rate = 0.22 + min(0.20, floor_number * 0.005)
    if enemy_dict.get("type") == "boss":
        rate = max(rate, 0.45)
    if random.random() >= rate:
        return None
    return {"skill_id": sk_id, "config": cfg}


def enemy_turn():
    global player_defending, battle_log, enemy_rl_deferred, battle_timeline_text, flash_timer
    battle_begin_action_sequence()
    sync_battle_enemy_pointer()
    if enemy is None:
        return
    living = [(i, battle_enemies[i]) for i in living_enemy_indices()]
    if not living:
        return

    _rl_live = None
    if len(living) == 1 and encode_state and pick_enemy_target_from_action:
        _rl_live = _ensure_enemy_rl_agent()
    use_rl = _rl_live is not None

    msgs = []
    order_names = []
    last_dmg = 0
    last_target_obj = player
    state_now = action = None

    for ei, ev in living:
        order_names.append(ev.get("name", "敵"))
        if "麻痺" in ev.get("status", {}):
            msgs.append(f"{ev.get('name', '敵')}:痺れて動けず")
            continue

        if use_rl:
            mxhp = float(max(1, ev.get("max_hp", ev["hp"])))
            state_now = encode_state(
                battle_ally_atk_cnt,
                battle_ally_def_cnt,
                battle_ally_sp_cnt,
                float(ev["hp"]),
                mxhp,
            )
            if enemy_rl_deferred is not None:
                s0, a0, r0 = enemy_rl_deferred
                _rl_live.flush_after_ally_round(s0, a0, r0, state_now)
            action = _rl_live.pick_action(state_now)
            kind, obj = pick_enemy_target_from_action(action, player, player["party"], MAX_PARTY_MEMBERS)
            target = {"kind": kind, "obj": obj}
        else:
            targets = [{"kind": "player", "obj": player}]
            for p in player["party"][:MAX_PARTY_MEMBERS]:
                if p["hp"] > 0 and not p.get("absent"):
                    targets.append({"kind": "party", "obj": p})
            if player.get("world_phase") == "night" and len(targets) > 1 and random.random() < 0.36:
                party_only = [t for t in targets if t["kind"] == "party"]
                target = random.choice(party_only if party_only else targets)
            else:
                target = random.choice(targets)
            action = None

        dmg = random.randint(3, ev["atk"]) - get_def()
        # 敵の固有スキル（カタログの skill 文字列）
        skill_use = maybe_use_enemy_skill(ev)
        skill_status = None
        skill_hits = 1
        skill_label = ""
        if skill_use is not None:
            vfx_kind, title, accent, mult, status_add = skill_use["config"]
            sk_id = skill_use["skill_id"]
            dmg = max(1, int(dmg * mult))
            if sk_id == "doublehit":
                skill_hits = 2  # 1ターンに 2 回攻撃
            skill_status = status_add
            skill_label = title
            # 敵の技 VFX とカットイン
            trigger_battle_vfx(vfx_kind, frames=22)
            battle_trigger_crit_cutin(ev.get("name", "敵"), title=title, accent=accent, timer=18)
            if vfx_kind in ("fire_wave",):
                play_battle_se("fire")
            elif vfx_kind in ("thunder_bolt",):
                play_battle_se("thunder")
            elif vfx_kind in ("bell_wave",):
                play_battle_se("heal")
            else:
                play_battle_se("magic")
            flash_timer = max(flash_timer, 8)
        if ev.get("type") == "boss" and random.random() < 0.22:
            dmg = int(dmg * 1.55) + 2
            flash_timer = max(flash_timer, 8)
            trigger_battle_vfx("phys_strong", frames=20)
            msgs.append(f"{ev.get('name','ボス')}の必殺が炸裂！")
        syn_wp = ""
        red = synergy_war_priest_flat()
        if red:
            dmg = max(1, dmg - red)
            syn_wp = f"[戦士+僧侶-{red}]"
        nm = ev.get("name", "敵")

        if target["kind"] == "player":
            if player_defending:
                dmg = max(1, dmg // 2)
                dmg = max(1, dmg - _player_build().get("guard_focus", 0) // 2)
            total_dmg = 0
            for _h in range(max(1, skill_hits)):
                hit_dmg = dmg if _h == 0 else max(1, int(dmg * 0.7))
                player["hp"] -= hit_dmg
                bump_attack_fx(is_crit=False)
                battle_add_damage_popup(f"-{hit_dmg}", 86, 86, col=(255, 170, 170))
                total_dmg += hit_dmg
            tag = "（狙い撃ち）" if action == 0 and use_rl else ""
            sk_tag = f"【{skill_label}】" if skill_label else ""
            msgs.append(f"{nm}{sk_tag}→君{total_dmg}{tag}{syn_wp}")
            battle_push_action_fx(nm, "atk", side="enemy", slot=ei, target_slot=-1, delay_ms=battle_next_action_delay_ms())
            player_defending = False
            last_dmg = total_dmg
            last_target_obj = player
            if player["hp"] <= 0:
                enemy_rl_finish_battle(True)
                memory_death_recovery()
                return
        else:
            member = target["obj"]
            if member.get("defending"):
                dmg = max(1, dmg // 2)
            total_dmg = 0
            for _h in range(max(1, skill_hits)):
                hit_dmg = dmg if _h == 0 else max(1, int(dmg * 0.7))
                member["hp"] -= hit_dmg
                battle_add_damage_popup(f"-{hit_dmg}", 96, 188 + 0 * 88, col=(255, 170, 170))
                total_dmg += hit_dmg
            member["defending"] = False
            tag = ""
            if use_rl and action == 1:
                tag = "（弱）"
            elif use_rl and action == 2:
                tag = "（崩）"
            sk_tag = f"【{skill_label}】" if skill_label else ""
            msgs.append(f"{nm}{sk_tag}→{member['name']}{total_dmg}{tag}{syn_wp}")
            tslot = 0
            for pi, pm in enumerate(player["party"][:MAX_PARTY_MEMBERS]):
                if pm is member:
                    tslot = pi
                    break
            battle_push_action_fx(nm, "atk", side="enemy", slot=ei, target_slot=tslot, delay_ms=battle_next_action_delay_ms())
            last_dmg = total_dmg
            last_target_obj = member

        if use_rl and encode_state and state_now is not None and action is not None:
            enemy_rl_deferred = (state_now, action, _rl_live.reward_for_damage(last_dmg))
        else:
            enemy_rl_deferred = None

        # 敵スキルが状態異常を付与
        if skill_status:
            try:
                apply_status(last_target_obj, skill_status)
            except (TypeError, ValueError):
                pass
        if random.random() < 0.14:
            apply_status(last_target_obj, "麻痺")

    battle_log = (" | ".join(msgs))[:240]
    battle_timeline_text = "行動順: " + " → ".join(order_names) if order_names else ""
    sync_battle_enemy_pointer()
    if mode == "battle" and enemy is not None:
        reset_battle_plan_state()

def roll_post_battle_loot(be_snap):
    """撃破時ドロップ（通常・レア・高級・超低確率）。ショップ品は町で売却可。"""
    notes = []
    if not be_snap:
        return notes
    lm = route_loot_mult()
    cat = shop_catalog()
    names_ok = {it["name"] for it in cat}

    def pick(seq):
        avail = [n for n in seq if n in names_ok]
        return random.choice(avail) if avail else None

    def pk(base_prob):
        return min(0.96, base_prob * lm)

    common_cands = (
        "銅貨袋",
        "砥石",
        "携帯パン",
        "薬草",
        "解毒草",
        "祝福の塩",
        "肉の干し",
        "温泉卵",
        "羽ペン",
    )
    rare_cands = ("回復薬", "万能軟膏", "MP回復薬", "元気ドリンク", "鉄の剣", "ハチミツ瓶", "盾のオイル")
    epic_cands = ("良質な回復薬", "魔力の秘薬", "大剣", "魔法の剣", "鉄甲冑", "魔法の衣", "パーティハーブ")
    ultra_cands = ("女神のしずく", "ドラゴンスレイヤー", "竜騎士の鎧", "完全回復薬", "エリクサー")

    for ed in be_snap:
        is_boss = ed.get("type") == "boss"
        if random.random() < pk(0.26 if is_boss else 0.17):
            it = pick(common_cands)
            if it:
                grant_inventory_item(it)
                notes.append(it)
        if random.random() < pk(0.12 if is_boss else 0.052):
            it = pick(rare_cands)
            if it:
                grant_inventory_item(it)
                notes.append(it + "☆")
        if random.random() < pk(0.048 if is_boss else 0.017):
            it = pick(epic_cands)
            if it:
                grant_inventory_item(it)
                notes.append(it + "★")
        if random.random() < pk(0.0038 if is_boss else 0.0009):
            it = pick(ultra_cands)
            if it:
                grant_inventory_item(it)
                notes.append(it + "!!")
    return notes


# ===== 仲間スキル =====
def party_skill(p):
    sync_battle_enemy_pointer()
    if p["name"] == "戦士":
        if enemy is not None:
            enemy["hp"] -= random.randint(10, 20)
            sync_battle_enemy_pointer()
    elif p["name"] == "僧侶":
        player["hp"] = min(player["hp"] + 20, player["max_hp"])

# ===== 勝利 =====
def win():
    global mode, battle_log, battle_plan_units, battle_plan_focus, battle_pending, spell_menu_target, spell_menu_cursor, pending_bond_check, battle_music_started, story_current_id, enemy, battle_enemies, battle_target_enemy_index, random_encounter_cooldown, flash_timer, _battle_bgm_pending, _victory_channel
    enemy_rl_finish_battle(True)
    battle_plan_units = []
    battle_plan_focus = 0
    battle_pending = {}
    spell_menu_target = None
    spell_menu_cursor = 0
    battle_music_started = False
    _battle_bgm_pending = False
    music_silence_immediate()
    random_encounter_cooldown = 22
    if _snd_victory and player.get("opt_se_on", True):
        try:
            stop_victory_fanfare()
            _victory_channel = _snd_victory.play()
        except pygame.error:
            _victory_channel = None
            pass

    be_snap = list(battle_enemies) if battle_enemies else ([enemy] if enemy else [])
    raw_exp = sum(int(x.get("exp", 20)) for x in be_snap) if be_snap else 20
    gained = max(1, int(raw_exp * HERO_EXP_GAIN_MULT))
    boss_defeated = any(x.get("type") == "boss" for x in be_snap)
    if boss_defeated:
        personality_apply({"bravery": 2, "honor": 1})
        flash_timer = max(flash_timer, 12)
        trigger_battle_vfx("boss_finisher", frames=28)
        battle_trigger_crit_cutin("BOSS BREAK")

    player["exp"] += gained
    gadd = max(5, gained)
    if "弓使い" in party_alive_names():
        gadd = int(gadd * 1.08)
    player["gold"] += gadd
    battle_log = f"撃破 +{gadd}G +{gained}EXP"
    loot_notes = roll_post_battle_loot(be_snap)
    if loot_notes:
        battle_log = (battle_log + " ドロップ:" + " ".join(loot_notes[:6]))[:240]

    for member in player["party"][:MAX_PARTY_MEMBERS]:
        if member["hp"] > 0 and not member.get("absent"):
            give_member_exp(member, gained)

    if player["exp"] >= player["exp_next"]:
        levelup()

    player["_battle_wave"] = None
    player["_battle_wave_idx"] = 0
    battle_enemies.clear()
    battle_target_enemy_index = 0
    enemy = None

    if enemy_pos in enemies:
        del enemies[enemy_pos]

    advance_world_tactics()
    player["_wins"] = player.get("_wins", 0) + 1
    ach = player.setdefault("achievements", {})
    ach_new = []
    if player["_wins"] >= 1 and not ach.get("ach_first_win"):
        ach["ach_first_win"] = True
        ach_new.append("初陣の勝利")
    if player.get("_battle_phase_snapshot") == "night":
        player["_night_wins"] = player.get("_night_wins", 0) + 1
        if player["_night_wins"] >= 3 and not ach.get("ach_night3"):
            ach["ach_night3"] = True
            ach_new.append("夜戦の手練れ")
    if codex_unique_enemy_species() >= 10 and not ach.get("ach_codex10"):
        ach["ach_codex10"] = True
        ach_new.append("図鑑・敵10種")
    if ach_new:
        battle_log = (battle_log + " ［実績］" + "、".join(ach_new))[:220]

    quest_update(floor_number, boss_defeated)
    if boss_defeated or random.random() < 0.08:
        relic = random.choice(RELICS)
        if relic["name"] not in player["relics"]:
            apply_relic(relic)
            battle_log = (battle_log + f" レア:{relic['name']}入手！")[:240]

    if floor_number == 100 and boss_defeated:
        if "post_boss_100" in story_nodes:
            story_current_id = "post_boss_100"
            mode = "story"
            battle_log = (battle_log + " ―深淵の心臓が、一拍遅れて止まった。")[:240]
            return
        mode = "ending"
        battle_log = (battle_log + " 最終決戦、制した。")[:240]
        return

    if boss_defeated and floor_number % 10 == 0 and floor_number < 100:
        sid = f"post_boss_{floor_number}"
        if sid in story_nodes:
            story_current_id = sid
            mode = "story"
            battle_log = (battle_log + " ―階を守る者が跪いた。静寂があなたを包む。")[:240]
            return

    mode = "world"
    if pending_bond_check:
        pending_bond_check = False
        try_start_bond_crisis()

# ===== レベルアップ =====
def levelup():
    player["level"]+=1
    player["skill_points"] = player.get("skill_points", 0) + 1
    player["exp"]=0
    player["exp_next"]+=26
    player["atk"]+=2
    player["max_hp"]+=20
    player["hp"]=player["max_hp"]
    player["max_mp"]+=5
    player["mp"]=player["max_mp"]

    for member in player["party"][:MAX_PARTY_MEMBERS]:
        if member.get("absent"):
            continue
        member["atk"] += 1
        member["max_hp"] += 5
        member["hp"] = member["max_hp"]
        member["max_mp"] = member.get("max_mp", 30) + 3
        member["mp"] = member["max_mp"]

    ns = next_player_skill()
    if ns:
        player["skills"].append(ns)

# ===== 仲間入れ替え =====
selected_index=0

def swap_party(i):
    if i < min(len(player["party"]), MAX_PARTY_MEMBERS):
        if player["party"][i].get("absent") or player["party"][0].get("absent"):
            return
        player["party"][0], player["party"][i] = player["party"][i], player["party"][0]

# ===== 移動（自由移動・連続歩行・ドラクエ風滑らか歩行） =====
WORLD_MOVE_TILES_PER_SEC = 5.6  # 連続歩行の速度（マス/秒）
WORLD_HITBOX = 0.58              # プレイヤー当たり判定（マスに対する比率・小さめで通り抜け易く）
WORLD_STEP_SE_DIST = 0.9         # 足音SEと歩行アニメの間隔（マス）
WORLD_DT_MAX = 0.05              # 1フレームに進める最大時間（壁すり抜け抑止）


def _world_aabb_tile_range(px, py):
    """指定位置に立ったときに当たり判定が触れるタイル範囲を返す。"""
    pad = (1.0 - WORLD_HITBOX) / 2.0
    minx = px + pad
    maxx = px + 1.0 - pad
    miny = py + pad
    maxy = py + 1.0 - pad
    return (
        int(math.floor(minx)),
        int(math.floor(maxx - 1e-9)),
        int(math.floor(miny)),
        int(math.floor(maxy - 1e-9)),
    )


def world_position_blocked(px, py, ox, oy):
    """(px, py) へ AABB を進めると壁・領域外・進入禁止の一方通行に阻まれるか。"""
    tx0, tx1, ty0, ty1 = _world_aabb_tile_range(px, py)
    otx0, otx1, oty0, oty1 = _world_aabb_tile_range(ox, oy)
    mvx = px - ox
    mvy = py - oy
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            if not (0 <= tx < W and 0 <= ty < H):
                return True
            tid = tiles[ty][tx]
            if tile_blocks_path(tid):
                return True
            if tid == TILE_ONEWAY:
                already = otx0 <= tx <= otx1 and oty0 <= ty <= oty1
                if not already:
                    req = FLOOR_EXTRA.get("oneway", {}).get((tx, ty))
                    if req and (mvx * req[0] + mvy * req[1]) < 1e-6:
                        return True
    return False


def _world_normalize_last_tile():
    last = player.get("_world_last_tile")
    if isinstance(last, (list, tuple)) and len(last) == 2:
        try:
            return (int(last[0]), int(last[1]))
        except (TypeError, ValueError):
            return None
    return None


def world_reset_movement_state():
    """新しいフロアやセーブロード後に呼び、自由移動の追跡情報を整える。"""
    try:
        player["x"] = float(player.get("x", 1))
        player["y"] = float(player.get("y", 1))
    except (TypeError, ValueError):
        player["x"] = 1.0
        player["y"] = 1.0
    cur = world_player_tile()
    player["_world_last_tile"] = [int(cur[0]), int(cur[1])]
    player["_world_walked_dist"] = 0.0
    player["_render_x"] = float(player["x"])
    player["_render_y"] = float(player["y"])


def world_continuous_update():
    """毎フレーム、ワールドモード時のキー入力を読み取り自由移動を進める。"""
    global walk_frame, world_facing

    if mode != "world":
        return

    keys = pygame.key.get_pressed()
    raw_dx = (1 if (keys[pygame.K_d] or keys[pygame.K_RIGHT]) else 0) - (
        1 if (keys[pygame.K_a] or keys[pygame.K_LEFT]) else 0
    )
    raw_dy = (1 if (keys[pygame.K_s] or keys[pygame.K_DOWN]) else 0) - (
        1 if (keys[pygame.K_w] or keys[pygame.K_UP]) else 0
    )

    if not isinstance(player.get("x"), (int, float)):
        player["x"] = 1.0
    if not isinstance(player.get("y"), (int, float)):
        player["y"] = 1.0

    if raw_dx == 0 and raw_dy == 0:
        return

    dt_ms = clock.get_time()
    dt = (dt_ms / 1000.0) if dt_ms > 0 else (1.0 / 30.0)
    if dt > WORLD_DT_MAX:
        dt = WORLD_DT_MAX
    speed = WORLD_MOVE_TILES_PER_SEC * dt
    rdx = float(raw_dx)
    rdy = float(raw_dy)
    if rdx != 0.0 and rdy != 0.0:
        rdx *= 0.70710678
        rdy *= 0.70710678

    ox = float(player["x"])
    oy = float(player["y"])
    nx_target = ox + rdx * speed
    ny_target = oy + rdy * speed

    if rdx != 0.0:
        if not world_position_blocked(nx_target, oy, ox, oy):
            player["x"] = nx_target
        else:
            # 壁にめり込まないギリギリまで詰める（壁ピタ寄せ）
            lo, hi = ox, nx_target
            for _ in range(8):
                mid = (lo + hi) / 2.0
                if world_position_blocked(mid, oy, ox, oy):
                    hi = mid
                else:
                    lo = mid
            if lo != ox and not world_position_blocked(lo, oy, ox, oy):
                player["x"] = lo
    cur_x = float(player["x"])
    if rdy != 0.0:
        if not world_position_blocked(cur_x, ny_target, cur_x, oy):
            player["y"] = ny_target
        else:
            lo, hi = oy, ny_target
            for _ in range(8):
                mid = (lo + hi) / 2.0
                if world_position_blocked(cur_x, mid, cur_x, oy):
                    hi = mid
                else:
                    lo = mid
            if lo != oy and not world_position_blocked(cur_x, lo, cur_x, oy):
                player["y"] = lo

    new_x = float(player["x"])
    new_y = float(player["y"])
    moved_dx = new_x - ox
    moved_dy = new_y - oy
    moved_dist = math.hypot(moved_dx, moved_dy)
    if moved_dist <= 1e-6:
        return

    if abs(moved_dx) >= abs(moved_dy):
        world_facing = (1 if moved_dx > 0 else -1, 0)
    else:
        world_facing = (0, 1 if moved_dy > 0 else -1)

    walked = float(player.get("_world_walked_dist", 0.0)) + moved_dist
    while walked >= WORLD_STEP_SE_DIST:
        walked -= WORLD_STEP_SE_DIST
        play_battle_se("step")
        walk_frame = (walk_frame + 1) % 2
    player["_world_walked_dist"] = walked

    cur_tile = world_player_tile()
    last_tile = _world_normalize_last_tile()
    if last_tile is None:
        player["_world_last_tile"] = [int(cur_tile[0]), int(cur_tile[1])]
        return
    if cur_tile != last_tile:
        player["_world_last_tile"] = [int(cur_tile[0]), int(cur_tile[1])]
        world_on_enter_tile(cur_tile[0], cur_tile[1])


def world_on_enter_tile(tx, ty):
    """プレイヤーの中心タイルが切り替わったときに発火する進入イベント。"""
    global mode, town_dialog_index, town_mode, town_npc_id, town_npc_line
    global pending_floor_move, pending_event, encounter_flash
    global random_encounter_cooldown, FLOOR_EXTRA, battle_log

    if not (0 <= tx < W and 0 <= ty < H):
        return

    explore_mark_cell()
    if random_encounter_cooldown > 0:
        random_encounter_cooldown -= 1
    tick_explore_buff_move()
    if player.get("torch_turns", 0) > 0:
        player["torch_turns"] -= 1

    tid = tiles[ty][tx]

    if tid == TILE_WARP:
        dest = FLOOR_EXTRA.get("warp", {}).get((tx, ty))
        if dest:
            wid = FLOOR_EXTRA.get("warp_pair_tag", {}).get((tx, ty))
            tag = chr(ord("A") + wid) if wid is not None and wid < 26 else "?"
            battle_log = f"ワープ床ペア「{tag}」が光り、対になる床へ運ぶ！"
            tut = player.setdefault("_gimmick_tutorial", {})
            if not tut.get("warp"):
                battle_log += " 【ヒント】記号が同じ床と行き来する。"
                tut["warp"] = True
            player["x"] = float(dest[0])
            player["y"] = float(dest[1])
            tx, ty = int(dest[0]), int(dest[1])
            player["_world_last_tile"] = [tx, ty]
            player["_render_x"] = float(player["x"])
            player["_render_y"] = float(player["y"])
            explore_mark_cell()
            tid = tiles[ty][tx]

    if tid == TILE_SWITCH and not FLOOR_EXTRA.get("doors_open"):
        FLOOR_EXTRA["doors_open"] = True
        # ワールドは 60FPS なので 60*3 ≒ 3秒のフラッシュ
        FLOOR_EXTRA["door_flash_timer"] = 180
        battle_log = "スイッチを押した。どこかで重い扉が開いた。"
        tut = player.setdefault("_gimmick_tutorial", {})
        if not tut.get("switch"):
            battle_log += " 【ヒント】灰色の扉ブロックが開くことがある。"
            tut["switch"] = True

    if tid == TILE_EVENT:
        trigger_explore_random_event()
        return

    if tid == 2:
        town_dialog_index = 0
        town_mode = "hub"
        town_npc_id = -1
        town_npc_line = 0
        mode = "town"
        return
    if tid == 4:
        pending_floor_move = True
        mode = "stairs_confirm"
        return
    if tid == 5:
        player["hp"] = player["max_hp"]
        player["mp"] = player["max_mp"]
        battle_log = "泉でHP/MPが全快した！"
        return
    if tid == TILE_CHEST:
        looted = FLOOR_EXTRA.setdefault("chest_looted", set())
        if (tx, ty) not in looted:
            looted.add((tx, ty))
            kind, val = _roll_chest_loot()
            if kind == "item":
                grant_inventory_item(val)
                battle_log = f"宝箱を開けた！{val}を手に入れた。"
            else:
                player["gold"] = player.get("gold", 0) + val
                battle_log = f"宝箱に {val}G が入っていた！"
        else:
            battle_log = "からっぽの箱だ…"
        return

    sf = player.get("story_flags") if isinstance(player.get("story_flags"), dict) else {}
    if floor_number in (30, 60) and not sf.get(f"event_{floor_number}", False):
        pending_event = floor_number
        mode = "event_choice"
        return

    if (tx, ty) in enemies:
        start_battle((tx, ty))
        return

    enc_ok = tid == 0 or tid == TILE_FORK
    if enc_ok and random_encounter_cooldown <= 0:
        encounter_rate = min(0.16, 0.028 + floor_number * 0.0011 + (floor_number // 20) * 0.0045)
        encounter_rate *= route_encounter_mult()
        if random.random() < encounter_rate:
            encounter_flash = 5
            start_random_battle()


def move(dx, dy):
    """互換用: 1マス分ジャンプし進入イベントを発火（自由移動の単発呼び出し用）。"""
    global walk_frame, world_facing
    if mode != "world":
        return
    try:
        ox = float(player.get("x", 1))
        oy = float(player.get("y", 1))
    except (TypeError, ValueError):
        ox, oy = 1.0, 1.0
    nx = ox + float(dx)
    ny = oy + float(dy)
    if world_position_blocked(nx, oy, ox, oy):
        nx = ox
    if world_position_blocked(nx, ny, nx, oy):
        ny = oy
    if nx == ox and ny == oy:
        return
    player["x"] = nx
    player["y"] = ny
    if dx or dy:
        world_facing = (int(dx) or 0, int(dy) or 0)
    play_battle_se("step")
    walk_frame = (walk_frame + 1) % 2
    cur_tile = world_player_tile()
    last_tile = _world_normalize_last_tile()
    if last_tile != cur_tile:
        player["_world_last_tile"] = [int(cur_tile[0]), int(cur_tile[1])]
        world_on_enter_tile(cur_tile[0], cur_tile[1])

def world_header_height():
    """見出し・戦術・マップ凡例2行＋任意で分岐・霧の一言。"""
    h = 80
    if FLOOR_EXTRA.get("branch_region"):
        h += 14
    if FLOOR_EXTRA.get("fog"):
        h += 18
    return h


def world_map_cell_layout(player_x, player_y):
    """ワールドはプレイヤー中心のカメラ表示で、近距離の冒険感を出す。"""
    MAP_HDR = world_header_height()
    pad = 8
    view_l = pad
    view_r = VIEWPORT_W - pad
    view_t = MAP_HDR
    view_b = VIEWPORT_H - pad
    avail_w = max(80, view_r - view_l)
    avail_h = max(80, view_b - view_t)
    # 全体表示ではなく、探索中は少し寄った視点にする。
    zoom = 1.6
    cell = max(12, int(TILE * zoom))
    mw, mh = W * cell, H * cell
    target_cx = view_l + avail_w // 2
    target_cy = view_t + avail_h // 2
    ox = int(target_cx - (player_x + 0.5) * cell)
    oy = int(target_cy - (player_y + 0.5) * cell)
    min_ox = view_r - mw
    max_ox = view_l
    min_oy = view_b - mh
    max_oy = view_t
    ox = max(min_ox, min(max_ox, ox))
    oy = max(min_oy, min(max_oy, oy))
    return cell, ox, oy, view_l, view_r, view_t, view_b


def world_tile_surface(src, cell):
    """ミニタイル画像を現在のセルサイズへ（ドット絵はネアレストでくっきり）。"""
    if src is None:
        return None
    if src.get_size() == (cell, cell):
        return src
    return pygame.transform.scale(src, (cell, cell))


def world_floor_biome_shade(screen, px, py, cell, tint_rgb):
    """草地画像の上にバイオーム色と市松模様を載せてレトロ感を出す。"""
    sh = pygame.Surface((cell, cell), pygame.SRCALPHA)
    sh.fill((*tint_rgb, 38))
    screen.blit(sh, (px, py))
    dot = max(2, cell // 5)
    c1 = (min(255, tint_rgb[0] + 22), min(255, tint_rgb[1] + 20), min(255, tint_rgb[2] + 16), 30)
    c2 = (max(0, tint_rgb[0] - 18), max(0, tint_rgb[1] - 14), max(0, tint_rgb[2] - 10), 24)
    for yy in range(0, cell, dot):
        for xx in range(0, cell, dot):
            if ((xx // dot) + (yy // dot)) % 2 == 0:
                pygame.draw.rect(sh, c1, (xx, yy, dot, dot))
            else:
                pygame.draw.rect(sh, c2, (xx, yy, dot, dot))
    screen.blit(sh, (px, py))


def world_wall_tile_draw(screen, px, py, cell, wall_rgb):
    pygame.draw.rect(screen, wall_rgb, (px, py, cell, cell))
    dk = max(0, wall_rgb[0] - 26), max(0, wall_rgb[1] - 22), max(0, wall_rgb[2] - 18)
    pygame.draw.rect(screen, dk, (px, py, cell, cell), 1)
    step = max(2, cell // 5)
    for u in range(px + 1, px + cell - 1, step * 2):
        pygame.draw.line(screen, dk, (u, py + 1), (u, py + cell - 2), 1)
    for v in range(py + step, py + cell - 1, step * 2):
        pygame.draw.line(screen, dk, (px + 1, v), (px + cell - 2, v), 1)


def draw_town_backdrop(screen):
    """固有作品を避けた、汎用レトロJRPG風の町背景。"""
    sky_top = (72, 124, 212)
    sky_bot = (150, 194, 244)
    for y in range(0, 260):
        t = y / 260.0
        c = (
            int(sky_top[0] * (1.0 - t) + sky_bot[0] * t),
            int(sky_top[1] * (1.0 - t) + sky_bot[1] * t),
            int(sky_top[2] * (1.0 - t) + sky_bot[2] * t),
        )
        pygame.draw.line(screen, c, (0, y), (VIEWPORT_W, y))
    pygame.draw.rect(screen, (92, 164, 96), (0, 260, VIEWPORT_W, 240))
    pygame.draw.rect(screen, (168, 146, 96), (0, 500, VIEWPORT_W, 120))
    # 石畳の市松
    step = 22
    for y in range(500, 620, step):
        for x in range(0, VIEWPORT_W, step):
            col = (156, 136, 88) if ((x // step) + (y // step)) % 2 == 0 else (142, 124, 80)
            pygame.draw.rect(screen, col, (x, y, step, step))
    # 家並み（色のみでレトロ感、特定作品の建物形状は避ける）
    houses = [
        (64, 280, 120, 96, (188, 160, 110), (160, 68, 58)),
        (230, 298, 130, 92, (172, 146, 96), (142, 82, 66)),
        (418, 286, 138, 104, (178, 154, 108), (168, 70, 60)),
    ]
    for hx, hy, hw, hh, wall, roof in houses:
        pygame.draw.rect(screen, wall, (hx, hy, hw, hh))
        pygame.draw.rect(screen, (96, 74, 48), (hx, hy, hw, hh), 2)
        pygame.draw.polygon(screen, roof, [(hx - 8, hy), (hx + hw + 8, hy), (hx + hw // 2, hy - 44)])
        pygame.draw.polygon(screen, (96, 54, 48), [(hx - 8, hy), (hx + hw + 8, hy), (hx + hw // 2, hy - 44)], 2)
        pygame.draw.rect(screen, (118, 84, 52), (hx + hw // 2 - 14, hy + hh - 38, 28, 38))
        pygame.draw.rect(screen, (80, 58, 38), (hx + hw // 2 - 14, hy + hh - 38, 28, 38), 1)
        pygame.draw.rect(screen, (238, 228, 150), (hx + 16, hy + 20, 18, 14))
        pygame.draw.rect(screen, (238, 228, 150), (hx + hw - 34, hy + 20, 18, 14))


def draw_world_pseudo3d(screen, bt, pxv, pyv, view_l, view_r, view_t, view_b, vr_cells):
    """簡易アイソメ表示。既存マップデータを使い、疑似3Dに見せる。"""
    horizon_y = view_t + 56
    pygame.draw.rect(screen, (70, 120, 200), (view_l, view_t, view_r - view_l, max(12, horizon_y - view_t)))
    pygame.draw.rect(screen, (98, 154, 112), (view_l, horizon_y, view_r - view_l, max(24, view_b - horizon_y)))
    center_x = (view_l + view_r) // 2
    base_y = horizon_y + 34
    tile_w = 40
    tile_h = 20
    wall_h = 20
    draw_r = 10
    cells = []
    for y in range(max(0, pyv - draw_r), min(H, pyv + draw_r + 1)):
        for x in range(max(0, pxv - draw_r), min(W, pxv + draw_r + 1)):
            md = abs(x - pxv) + abs(y - pyv)
            if md > draw_r:
                continue
            if vr_cells < 900 and md > vr_cells:
                continue
            sx = center_x + (x - y - (pxv - pyv)) * (tile_w // 2)
            sy = base_y + (x + y - (pxv + pyv)) * (tile_h // 2)
            if sx < view_l - tile_w or sx > view_r + tile_w:
                continue
            if sy < view_t - tile_h or sy > view_b + tile_h:
                continue
            cells.append((sy, x, y, sx))
    cells.sort(key=lambda c: c[0])
    fl = BIOME_FLOOR_TINT[bt]
    wall = BIOME_WALL[bt]
    for sy, x, y, sx in cells:
        tid = tiles[y][x]
        top = [(sx, sy), (sx + tile_w // 2, sy + tile_h // 2), (sx, sy + tile_h), (sx - tile_w // 2, sy + tile_h // 2)]
        floor_col = fl
        if tid == 4:
            floor_col = (185, 185, 198)
        elif tid == 2:
            floor_col = (176, 130, 90)
        elif tid == 5:
            floor_col = (110, 170, 210)
        elif tid == TILE_CHEST:
            floor_col = (190, 145, 70)
        elif tid in (TILE_EVENT, TILE_SWITCH, TILE_DOOR, TILE_WARP, TILE_ONEWAY):
            floor_col = (150, 112, 70)
        pygame.draw.polygon(screen, floor_col, top)
        pygame.draw.polygon(screen, (30, 28, 34), top, 1)
        if tid == MAP_WALL_TILE:
            front = [(sx - tile_w // 2, sy + tile_h // 2), (sx, sy + tile_h), (sx, sy + tile_h + wall_h), (sx - tile_w // 2, sy + tile_h // 2 + wall_h)]
            side = [(sx + tile_w // 2, sy + tile_h // 2), (sx, sy + tile_h), (sx, sy + tile_h + wall_h), (sx + tile_w // 2, sy + tile_h // 2 + wall_h)]
            pygame.draw.polygon(screen, wall, top)
            pygame.draw.polygon(screen, (max(0, wall[0] - 18), max(0, wall[1] - 18), max(0, wall[2] - 18)), front)
            pygame.draw.polygon(screen, (min(255, wall[0] + 12), min(255, wall[1] + 12), min(255, wall[2] + 8)), side)
        elif (x, y) in enemies:
            pygame.draw.circle(screen, (194, 62, 70), (sx, sy + tile_h // 2 - 8), 6)
        elif tid == TILE_CHEST:
            pygame.draw.rect(screen, (195, 148, 58), (sx - 8, sy + tile_h // 2 - 12, 16, 10))
            pygame.draw.rect(screen, (80, 52, 26), (sx - 8, sy + tile_h // 2 - 12, 16, 10), 1)
    # プレイヤー（見やすいチビ騎士）
    psx = center_x
    psy = base_y + tile_h // 2 - 8
    shadow = pygame.Surface((28, 14), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (20, 24, 32, 120), (0, 0, 28, 14))
    screen.blit(shadow, (psx - 14, psy + 8))
    # マント
    pygame.draw.polygon(screen, (190, 46, 66), [(psx - 10, psy + 2), (psx + 10, psy + 2), (psx, psy + 18)])
    # 体
    pygame.draw.rect(screen, (70, 92, 190), (psx - 7, psy - 1, 14, 14))
    pygame.draw.rect(screen, (30, 42, 96), (psx - 7, psy - 1, 14, 14), 1)
    # 顔
    pygame.draw.circle(screen, (248, 220, 178), (psx, psy - 6), 6)
    pygame.draw.circle(screen, (38, 48, 72), (psx, psy - 6), 6, 1)
    pygame.draw.circle(screen, (32, 40, 60), (psx - 2, psy - 7), 1)
    pygame.draw.circle(screen, (32, 40, 60), (psx + 2, psy - 7), 1)
    # かみ/兜
    pygame.draw.arc(screen, (56, 62, 90), (psx - 6, psy - 13, 12, 8), math.pi, math.tau, 2)
    # 剣
    pygame.draw.line(screen, (220, 230, 245), (psx + 7, psy + 2), (psx + 13, psy - 8), 2)
    pygame.draw.line(screen, (110, 120, 140), (psx + 5, psy + 4), (psx + 10, psy + 0), 2)


def draw_story_scene_fx(screen, node_id):
    """ストーリー画面の簡易シネマ演出。"""
    t = pygame.time.get_ticks() * 0.001
    tone = (28, 34, 56) if str(node_id).startswith("post_boss") else (22, 28, 48)
    for y in range(0, HEIGHT, 3):
        b = min(255, tone[2] + y // 10)
        pygame.draw.line(screen, (tone[0], tone[1], b), (0, y), (WIDTH, y))
    # 流れる粒子
    for i in range(40):
        ph = i * 0.37
        x = int((i * 53 + t * 45 + 70 * math.sin(t + ph)) % WIDTH)
        y = int((i * 29 + t * 25 + 40 * math.cos(t * 0.7 + ph)) % HEIGHT)
        r = 1 + (i % 3)
        col = (150 + (i % 40), 180 + (i % 30), 230 + (i % 20))
        pygame.draw.circle(screen, col, (x, y), r)
    # 斜めライト
    beam = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    bx = int((math.sin(t * 0.9) * 0.5 + 0.5) * WIDTH)
    pygame.draw.polygon(
        beam,
        (255, 245, 190, 38),
        [(bx - 120, 0), (bx + 80, 0), (bx - 260, HEIGHT), (bx - 420, HEIGHT)],
    )
    screen.blit(beam, (0, 0))
    # ストーリー立ち絵（簡易）
    bob = int(math.sin(t * 2.6) * 4)
    elapsed = max(0, pygame.time.get_ticks() - int(story_anim_start_ms))
    slide = max(0, 240 - elapsed // 3)
    cx, cy = WIDTH - 190 + slide, 350 + bob
    pygame.draw.circle(screen, (248, 220, 188), (cx, cy - 120), 34)
    pygame.draw.rect(screen, (72, 98, 196), (cx - 34, cy - 86, 68, 92))
    cape = [(cx - 42, cy - 78), (cx + 42, cy - 78), (cx + 26, cy + 22), (cx - 26, cy + 22)]
    pygame.draw.polygon(screen, (178, 42, 62), cape)
    eye_c = (28, 36, 58)
    pygame.draw.circle(screen, eye_c, (cx - 11, cy - 126), 2)
    pygame.draw.circle(screen, eye_c, (cx + 11, cy - 126), 2)
    pygame.draw.arc(screen, eye_c, (cx - 12, cy - 114, 24, 12), 0.2, math.pi - 0.2, 1)
    if str(node_id).startswith("post_boss"):
        # かっこいい斬撃エフェクト
        slx = int((t * 380) % (WIDTH + 300)) - 150
        pygame.draw.line(screen, (255, 245, 180), (slx - 110, 520), (slx + 80, 280), 5)
        pygame.draw.line(screen, (130, 220, 255), (slx - 100, 526), (slx + 90, 286), 2)


def world_boss_arena_trim(screen, px, py, cell, active):
    if not active:
        return
    pygame.draw.rect(screen, (230, 190, 55), (px, py, cell, cell), 2)
    pygame.draw.rect(screen, (255, 245, 160), (px + 1, py + 1, cell - 2, cell - 2), 1)


def world_draw_chest_tile(screen, px, py, cell, biome_i):
    """フロア宝箱 — バイオームで木目トーンを少し変える。"""
    bx = px + max(1, cell // 8)
    by = py + max(1, cell // 7)
    bw = cell - 2 * max(1, cell // 8)
    bh = cell - 2 * max(1, cell // 7)
    if biome_i >= 8:
        wood, edge = (72, 68, 88), (40, 38, 52)
    elif biome_i in (4, 5, 6):
        wood, edge = (88, 98, 72), (48, 56, 40)
    elif biome_i in (1, 2):
        wood, edge = (92, 78, 58), (48, 40, 32)
    else:
        wood, edge = (118, 78, 44), (62, 42, 26)
    pygame.draw.rect(screen, wood, (bx, by, bw, bh))
    pygame.draw.rect(screen, edge, (bx, by, bw, bh), 1)
    lid_y = by + bh // 3
    pygame.draw.polygon(
        screen,
        (200, 155, 55),
        [(bx - 1, lid_y), (bx + bw + 1, lid_y), (bx + bw // 2, by + 1)],
    )
    pygame.draw.polygon(screen, (230, 190, 80), [(bx + 2, lid_y), (bx + bw - 2, lid_y), (bx + bw // 2, by + 3)])
    pygame.draw.circle(
        screen,
        (255, 235, 130),
        (px + cell // 2, by + bh - max(2, cell // 8)),
        max(2, cell // 9),
    )


def world_draw_gimmick_tile(screen, tid, mx, my, px, py, cell, biome_i):
    """ギミック床のドット寄り記号。(mx,my)=マップ座標。バイオームで色味を変える。"""
    pal = BIOME_FLOOR_TINT[biome_i]
    cx, cy = px + cell // 2, py + cell // 2
    th = max(2, cell // 10)
    bq = biome_i // 3  # 0..3 の帯でパレットをずらす
    ev_bg = (130 + bq * 8, 82 + bq * 4, 28 + bq * 10)
    ev_ac = (220 - bq * 6, 50 + bq * 5, 45)
    if tid == TILE_EVENT:
        pygame.draw.rect(screen, ev_bg, (px, py, cell, cell))
        pygame.draw.rect(screen, (60, 38, 12), (px, py, cell, cell), 1)
        pygame.draw.rect(screen, (255, 248, 220), (px + cell // 4, py + 2, cell // 2, cell - 4))
        pygame.draw.rect(screen, (40, 28, 10), (px + cell // 4 + 2, py + 4, cell // 2 - 4, cell - 8), 1)
        # 「!」を太めの矩形で
        iw = max(2, cell // 14)
        ix = cx - iw // 2
        pygame.draw.rect(screen, ev_ac, (ix, cy - cell // 5, iw, cell // 3))
        pygame.draw.rect(screen, ev_ac, (ix - cell // 16, cy + cell // 8, iw + cell // 8, iw + 1))
    elif tid == TILE_SWITCH:
        pygame.draw.rect(screen, (78, 52, 38), (px, py, cell, cell))
        pygame.draw.rect(screen, (42, 28, 18), (px, py, cell, cell), 1)
        # 台座
        pygame.draw.rect(
            screen,
            (52, 48, 58),
            (px + cell // 5, py + cell // 2, cell - 2 * (cell // 5), cell // 3),
        )
        # 赤いレバー玉
        pygame.draw.circle(screen, (240, 60, 55), (cx, py + cell // 3), max(4, cell // 6))
        pygame.draw.line(screen, (35, 30, 28), (cx, py + cell // 3), (cx, py + 2 * cell // 3), th)
    elif tid == TILE_DOOR:
        if FLOOR_EXTRA.get("doors_open"):
            pygame.draw.rect(screen, pal, (px, py, cell, cell))
            pygame.draw.line(screen, (230, 230, 245), (px + 5, cy), (px + cell - 5, cy), 2)
            pygame.draw.line(screen, (255, 240, 160), (cx, py + 5), (cx, py + cell - 5), 1)
        else:
            pygame.draw.rect(screen, (48, 50, 62), (px, py, cell, cell))
            pygame.draw.rect(screen, (28, 30, 40), (px + 3, py + 3, cell - 6, cell - 6), 1)
            # 扉板（縦線）
            for ox in range(px + cell // 5, px + cell - cell // 5, max(3, cell // 8)):
                pygame.draw.line(screen, (95, 92, 115), (ox, py + 5), (ox, py + cell - 5), 1)
            # 鍵穴
            kr = max(2, cell // 14)
            pygame.draw.circle(screen, (25, 25, 32), (cx, cy + cell // 10), kr + 1)
            pygame.draw.circle(screen, (200, 195, 220), (cx, cy + cell // 10), kr)
    elif tid == TILE_WARP:
        w0, w1 = (22 + bq * 6, 60 + bq * 8, 98 + bq * 4), (14 + bq * 4, 40 + bq * 6, 70 + bq * 4)
        pygame.draw.rect(screen, w0, (px, py, cell, cell))
        pygame.draw.rect(screen, w1, (px, py, cell, cell), 1)
        pygame.draw.circle(screen, (160, 250, 255), (cx, cy), max(4, cell // 4), 2)
        pygame.draw.circle(screen, (80, 200, 240), (cx, cy), max(2, cell // 6))
        pygame.draw.circle(screen, (40, 120, 180), (cx, cy), max(1, cell // 12), 1)
        wid = FLOOR_EXTRA.get("warp_pair_tag", {}).get((mx, my))
        if wid is not None:
            ch = chr(ord("A") + wid) if wid < 22 else str(wid)
            screen.blit(small.render(ch, True, (240, 252, 255)), (px + 3, py + cell - 14))
    elif tid == TILE_ONEWAY:
        pygame.draw.rect(screen, pal, (px, py, cell, cell))
        vec = FLOOR_EXTRA.get("oneway", {}).get((mx, my), (1, 0))
        vx, vy = vec[0], vec[1]
        ex = cx + vx * (cell // 2 - 4)
        ey = cy + vy * (cell // 2 - 4)
        pygame.draw.line(screen, (255, 220, 80), (cx - vx * (cell // 5), cy - vy * (cell // 5)), (ex, ey), max(3, cell // 10))
        # 矢印頭（三角形っぽく3線）
        back_x, back_y = ex - vx * (cell // 5), ey - vy * (cell // 5)
        perp = (-vy, vx)
        pm = max(3, cell // 8)
        p1 = (int(back_x + perp[0] * pm), int(back_y + perp[1] * pm))
        p2 = (int(back_x - perp[0] * pm), int(back_y - perp[1] * pm))
        pygame.draw.polygon(screen, (255, 235, 120), [(ex, ey), p1, p2])


# ===== 描画 =====
def draw():
    global flash_timer, enemy_shake_timer, encounter_flash, boss_intro_timer, slash_timer, battle_ui_shake, battle_vfx, story_anim_node, story_anim_start_ms
    screen.fill((20,20,30))

    if mode=="title":
        ensure_title_stars()
        t = pygame.time.get_ticks() * 0.001
        for y in range(0, HEIGHT, 3):
            u = y / max(1, HEIGHT)
            c = int(8 + u * 22), int(4 + u * 12), int(28 + u * 55)
            pygame.draw.line(screen, c, (0, y), (WIDTH, y))
        for sx, sy, ph in title_stars or []:
            tw = 0.55 + 0.45 * math.sin(t * 1.4 + ph)
            br = int(160 + 95 * tw)
            pygame.draw.circle(screen, (br, br, 255), (int(sx + math.sin(t + ph) * 6), int(sy)), 1)
        ban = _ensure_title_adventure_banner()
        title_y = 172
        menu_y = 310
        if ban:
            bx = WIDTH // 2 - ban.get_width() // 2
            by = 28
            pygame.draw.rect(screen, (14, 18, 42), (bx - 10, by - 8, ban.get_width() + 20, ban.get_height() + 16))
            pygame.draw.rect(screen, (255, 195, 100), (bx - 10, by - 8, ban.get_width() + 20, ban.get_height() + 16), 3)
            screen.blit(ban, (bx, by))
            title_y = by + ban.get_height() + 12
            menu_y = title_y + 108
        else:
            pygame.draw.rect(screen, (22, 26, 58), (108, 156, 784, 110))
            pygame.draw.rect(screen, (255, 205, 120), (108, 156, 784, 110), 3)
            pygame.draw.rect(screen, (240, 240, 255), (116, 164, 768, 94), 1)
        shadow = big.render("RPG", True, (32, 16, 64))
        screen.blit(shadow, (WIDTH // 2 - shadow.get_width() // 2 + 4, title_y + 4))
        gx = int(18 * math.sin(t * 2.1))
        col = (min(255, 248 + gx), min(255, 228 + gx // 2), 128)
        title_surf = big.render("RPG", True, col)
        screen.blit(title_surf, (WIDTH // 2 - title_surf.get_width() // 2, title_y))
        sub = font.render("いま、旅立ちのとき  —  深層へ", True, (210, 225, 255))
        screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, title_y + 52))
        draw_retro_frame(screen, WIDTH // 2 - 220, menu_y, 440, 118, inner=(12, 16, 36), border=(230, 225, 255))
        screen.blit(font.render("ENTER : 新しく始める", True, (245, 245, 255)), (WIDTH // 2 - 200, menu_y + 12))
        screen.blit(font.render("L     : セーブをロード", True, (230, 235, 255)), (WIDTH // 2 - 200, menu_y + 42))
        if story_current_id:
            screen.blit(font.render("SPACE : ストーリーへ", True, (220, 255, 220)), (WIDTH // 2 - 200, menu_y + 72))
        screen.blit(small.render("F11 / Alt+Enter … フルスクリーン切替（マップ・戦闘でも可）", True, (195, 210, 235)), (WIDTH // 2 - 340, HEIGHT - 62))
        screen.blit(small.render("BGM: Let the Games Begin (OpenGameArt)  /  SE: Kenney系・OGA", True, (160, 160, 190)), (WIDTH // 2 - 280, HEIGHT - 34))

    elif mode=="story":
        node = story_nodes.get(story_current_id, {})
        if story_anim_node != story_current_id:
            story_anim_node = story_current_id
            story_anim_start_ms = pygame.time.get_ticks()
            player["_story_prev_chars"] = 0
        draw_story_scene_fx(screen, story_current_id)
        frame = pygame.Surface((840, 500), pygame.SRCALPHA)
        frame.fill((10, 12, 24, 186))
        screen.blit(frame, (80, 92))
        pygame.draw.rect(screen, (210, 220, 255), (80, 92, 840, 500), 2)
        screen.blit(big.render("STORY", True, (255, 220, 120)), (380, 52))
        text = node.get("text", "...")
        elapsed = max(0, pygame.time.get_ticks() - story_anim_start_ms)
        show_chars = min(len(text), 10 + elapsed // 18)
        prev_chars = int(player.get("_story_prev_chars", 0))
        if show_chars > prev_chars and (show_chars % 12 == 0):
            play_battle_se("magic")
        player["_story_prev_chars"] = show_chars
        text = text[:show_chars]
        y_txt = 128
        for pos in range(0, len(text), 34):
            chunk = text[pos : pos + 34]
            emph = any(k in chunk for k in ("！", "!", "★", "危機", "宿命", "絆"))
            col = (255, 236, 170) if emph else (238, 240, 255)
            screen.blit(small.render(chunk, True, col), (108, y_txt))
            y_txt += 24
        y_ch = max(362, y_txt + 20)
        for i, c in enumerate(node.get("choices", [])[:3]):
            pulse = int(12 * (0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.004 + i)))
            col = (220 + pulse, 220 + pulse, 220 + pulse)
            screen.blit(font.render(f"{i+1}: {c.get('text','')}", True, col), (120, y_ch + i * 36))
        esc_hint = "ESC: ワールドへ戻る" if str(story_current_id).startswith("post_boss") else "ESC: タイトルへ"
        screen.blit(small.render(f"数字キーで選択  {esc_hint}", True, (210, 215, 255)), (120, min(HEIGHT - 48, y_ch + 126)))

    elif mode=="world":
        bt = min(9, max(0, (floor_number - 1) // 10))
        bg_col = BIOME_BG[bt]
        band = BIOME_TEXT_BAND[bt]
        boss_floor = floor_number > 0 and floor_number % 10 == 0
        if boss_floor:
            band = (min(255, band[0] + 30), min(255, band[1] + 20), min(200, band[2] + 8), min(255, band[3] + 6))
        pygame.draw.rect(screen, bg_col, (0, 0, VIEWPORT_W, min(VIEWPORT_H, HEIGHT)))
        hdr_h = world_header_height()
        hb = pygame.Surface((VIEWPORT_W, hdr_h), pygame.SRCALPHA)
        hb.fill(band)
        screen.blit(hb, (0, 0))
        _t0 = player.pop("_toast_map", None)
        _t1 = player.pop("_toast_save", None)
        toast_map_msg = " ／ ".join(p for p in (_t0, _t1) if p) or None
        pxv, pyv = world_player_tile()
        # 自由移動はプレイヤー位置がフレーム毎に滑らかに変化する。
        # カメラは現在位置を直接使用（遅延ゼロでブレずに追従）
        rx = float(player["x"])
        ry = float(player["y"])
        player["_render_x"], player["_render_y"] = rx, ry
        cell, ox, oy, view_l, view_r, view_t, view_b = world_map_cell_layout(rx, ry)
        tile_cache = {}
        for _tk in (0, 1, 2, 3, 4, 5):
            src = mini_tile.get(_tk)
            if src:
                tile_cache[_tk] = world_tile_surface(src, cell)
        enemy_tile = tile_cache.get(1)
        fl_tint = BIOME_FLOOR_TINT[bt]
        wcol = BIOME_WALL[bt]
        bname = BIOME_LABELS[bt]
        head1 = f"マップ  {bname}  {floor_number}階" + ("  ★ボス層" if boss_floor else "")
        hy = 8
        screen.blit(small.render(head1, True, (252, 252, 255)), (12, hy))
        hy += 18
        screen.blit(small.render(tactics_short_summary(), True, (230, 240, 255)), (12, hy))
        hy += 18
        screen.blit(
            small.render(
                "記号: 灰=階段  茶=町  水色=泉  金=宝箱(一度)  岩=壁  草=遭遇あり",
                True,
                (228, 232, 245),
            ),
            (12, hy),
        )
        hy += 18
        screen.blit(
            small.render(
                "ギミック: 黄=イベント 橙=柱  灰色扉=鍵  水色床=ワープ(同じ字が対)  矢=一方通行",
                True,
                (215, 225, 240),
            ),
            (12, hy),
        )
        hy += 18
        if FLOOR_EXTRA.get("branch_region"):
            screen.blit(
                small.render(
                    "分岐帯: 青=安全寄り 橙=危険寄り（未確定は淡色）",
                    True,
                    (210, 225, 255),
                ),
                (12, hy),
            )
            hy += 14
        if FLOOR_EXTRA.get("fog"):
            vr_hdr = vision_radius_world()
            ts = player.get("torch_turns", 0)
            fogline = (
                f"深霧：周囲約{vr_hdr}マス  T:松明（残{ts}歩）"
                if ts
                else f"深霧：周囲約{vr_hdr}マス  T:松明で拡大"
            )
            screen.blit(small.render(fogline, True, (255, 235, 180)), (12, hy))
            hy += 18
        vr_cells = vision_radius_world()
        pseudo_3d = False  # 2D表示
        if pseudo_3d:
            draw_world_pseudo3d(screen, bt, pxv, pyv, view_l, view_r, view_t, view_b, vr_cells)
        else:
            x0 = max(0, int((view_l - ox) // cell) - 1)
            x1 = min(W - 1, int((view_r - ox) // cell) + 1)
            y0 = max(0, int((view_t - oy) // cell) - 1)
            y1 = min(H - 1, int((view_b - oy) // cell) + 1)
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    px = int(ox + x * cell)
                    py = int(oy + y * cell)
                    tid = tiles[y][x]
                    if vr_cells < 900 and abs(x - pxv) + abs(y - pyv) > vr_cells:
                        pygame.draw.rect(screen, (8, 10, 18), (px, py, cell, cell))
                        pygame.draw.rect(screen, (22, 26, 38), (px, py, cell, cell), 1)
                        continue
                    in_boss_ring = boss_floor and 1 <= abs(x - 10) + abs(y - 5) <= 3
                    if tid == MAP_WALL_TILE:
                        world_wall_tile_draw(screen, px, py, cell, wcol)
                    elif tid == TILE_CHEST:
                        world_draw_chest_tile(screen, px, py, cell, bt)
                    elif tid in (TILE_EVENT, TILE_SWITCH, TILE_DOOR, TILE_WARP, TILE_ONEWAY):
                        world_draw_gimmick_tile(screen, tid, x, y, px, py, cell, bt)
                    elif tid == TILE_FORK:
                        tk = 0
                        sm = tile_cache.get(tk)
                        if sm:
                            screen.blit(sm, (px, py))
                            world_floor_biome_shade(screen, px, py, cell, fl_tint)
                        else:
                            pygame.draw.rect(screen, fl_tint, (px, py, cell, cell))
                            pygame.draw.rect(
                                screen,
                                (
                                    max(0, fl_tint[0] - 40),
                                    max(0, fl_tint[1] - 40),
                                    max(0, fl_tint[2] - 30),
                                ),
                                (px, py, cell, cell),
                                1,
                            )
                    elif tid == 5:
                        sm5 = tile_cache.get(5)
                        if sm5:
                            screen.blit(sm5, (px, py))
                            world_floor_biome_shade(screen, px, py, cell, fl_tint)
                        else:
                            wcol2 = (
                                min(255, fl_tint[0] + 50),
                                min(255, fl_tint[1] + 100),
                                min(255, fl_tint[2] + 120),
                            )
                            pygame.draw.rect(screen, wcol2, (px, py, cell, cell))
                            pygame.draw.circle(
                                screen, (200, 235, 255), (px + cell // 2, py + cell // 2), max(2, cell // 4)
                            )
                    elif (x, y) in enemies:
                        if enemy_tile:
                            screen.blit(enemy_tile, (px, py))
                        else:
                            pygame.draw.rect(screen, (175, 55, 62), (px, py, cell, cell))
                    else:
                        tk = tid if tid in mini_tile else 0
                        sm = tile_cache.get(tk)
                        if sm:
                            screen.blit(sm, (px, py))
                            if tk == 0:
                                world_floor_biome_shade(screen, px, py, cell, fl_tint)
                        else:
                            pygame.draw.rect(screen, fl_tint, (px, py, cell, cell))
                            pygame.draw.rect(
                                screen,
                                (
                                    max(0, fl_tint[0] - 40),
                                    max(0, fl_tint[1] - 40),
                                    max(0, fl_tint[2] - 30),
                                ),
                                (px, py, cell, cell),
                                1,
                            )
                    if in_boss_ring and tid != MAP_WALL_TILE:
                        world_boss_arena_trim(screen, px, py, cell, True)
                    if tid != MAP_WALL_TILE and tid != 5:
                        world_route_overlay(screen, px, py, cell, x, y)
            draw_world_door_flash(screen, ox, oy, cell)
            # 自由移動: マスを示す枠は出さず、足元の影と勇者ドットだけで描く（昔のドラクエ風）
            cell_x = int(ox + rx * cell)
            cell_y = int(oy + ry * cell)
            pw = max(6, min(cell - 4, int(cell * 0.72)))
            pcx = cell_x + (cell - pw) // 2
            pcy = cell_y + (cell - pw) // 2
            shadow = pygame.Surface((pw, max(3, pw // 4)), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (12, 16, 24, 120), shadow.get_rect())
            screen.blit(shadow, (pcx, pcy + pw - max(3, pw // 4) + 1))
            hero_dot = world_player_marker_surface(pw, walk=walk_frame, facing=world_facing)
            screen.blit(hero_dot, (pcx, pcy))
        draw_world_minimap(screen, STAIRS_POS)
        if toast_map_msg:
            tw = small.render(toast_map_msg, True, (255, 245, 220))
            tx, ty = 12, VIEWPORT_H - 88
            pad = 6
            bgw = min(VIEWPORT_W - 24, tw.get_width() + pad * 2)
            bgh = tw.get_height() + pad * 2
            toast_bg = pygame.Surface((bgw, bgh), pygame.SRCALPHA)
            toast_bg.fill((12, 14, 28, 210))
            screen.blit(toast_bg, (8, ty))
            pygame.draw.rect(screen, (180, 195, 230), (8, ty, bgw, bgh), 1)
            screen.blit(tw, (8 + pad, ty + pad))

        ux = UI_AREA_X + 10
        bar_w = max(120, UI_PANEL_W - 28)
        pygame.draw.rect(screen, (26, 30, 44), (UI_AREA_X, 0, UI_PANEL_W, HEIGHT))
        pygame.draw.rect(screen, (46, 54, 78), (UI_AREA_X + 6, 8, UI_PANEL_W - 12, HEIGHT - 16))
        pygame.draw.rect(screen, (130, 145, 185), (UI_AREA_X + 6, 8, UI_PANEL_W - 12, HEIGHT - 16), 2)
        pygame.draw.line(screen, (170, 185, 220), (UI_AREA_X, 0), (UI_AREA_X, HEIGHT), 3)

        exp_need = max(0, player["exp_next"] - player["exp"])
        pygame.draw.rect(screen, (44, 52, 72), (ux - 4, 14, UI_PANEL_W - 20, 26))
        screen.blit(small.render("ステータス", True, (250, 252, 255)), (ux, 18))
        screen.blit(font.render(f"Lv{player['level']}  {player['job']}", True, (252, 252, 255)), (ux, 46))
        pt_sec = int(player.get("play_time_sec", 0))
        screen.blit(
            font.render(
                f"{floor_number}階 ・ {player['gold']} G ・ 累計{pt_sec // 60}分",
                True,
                (255, 228, 130),
            ),
            (ux, 70),
        )
        vr_ui = "視界: 全体" if not FLOOR_EXTRA.get("fog") else f"視界: 約{vision_radius_world()}マス"
        vr_ui += "  /  描画: 2D"
        screen.blit(small.render(vr_ui, True, (175, 190, 215)), (ux, 92))
        screen.blit(small.render(f"次Lvまで {exp_need} EXP", True, (205, 225, 255)), (ux, 108))
        draw_bar(ux, 132, bar_w, 15, player["hp"], player["max_hp"], fg=(70, 220, 110))
        screen.blit(small.render(f"HP  {player['hp']} / {player['max_hp']}", True, (215, 255, 220)), (ux, 148))
        draw_bar(ux, 170, bar_w, 15, player["mp"], player["max_mp"], fg=(95, 175, 255))
        screen.blit(small.render(f"MP  {player['mp']} / {player['max_mp']}", True, (200, 225, 255)), (ux, 186))
        wep = player["weapon"] or "なし"
        arm = player["armor"] or "なし"
        screen.blit(small.render(f"武器 {wep}", True, (235, 238, 245)), (ux, 210))
        screen.blit(small.render(f"防具 {arm}", True, (235, 238, 245)), (ux, 228))
        pygame.draw.rect(screen, (34, 40, 58), (ux - 4, 250, UI_PANEL_W - 20, 52))
        screen.blit(small.render("操作", True, (210, 220, 245)), (ux, 252))
        screen.blit(small.render("I 袋  P 仲間  J 図鑑  F5 保存", True, (225, 235, 250)), (ux, 270))
        screen.blit(small.render("B 鍛錬（刻印・難易）", True, (215, 225, 245)), (ux, 288))
        raw_trait = ",".join(player["traits"][:2]) if player["traits"] else "なし"
        raw_relic = ",".join(player["relics"][:2]) if player["relics"] else "なし"
        trait_txt = raw_trait[:20] + ("…" if len(raw_trait) > 20 else "")
        relic_txt = raw_relic[:20] + ("…" if len(raw_relic) > 20 else "")
        screen.blit(small.render(f"特性 {trait_txt}", True, (255, 205, 205)), (ux, 310))
        screen.blit(small.render(f"遺物 {relic_txt}", True, (255, 235, 190)), (ux, 328))

        leg_short = player.get("_map_legend_short", False)
        leg_y0 = 332
        if leg_short:
            leg_h = 22
            pygame.draw.rect(screen, (36, 42, 58), (ux - 4, leg_y0, UI_PANEL_W - 20, leg_h))
            pygame.draw.rect(screen, (95, 108, 145), (ux - 4, leg_y0, UI_PANEL_W - 20, leg_h), 1)
            screen.blit(
                small.render("凡例は画面上部。Tabでこのメモの表示切替", True, (200, 215, 235)),
                (ux, leg_y0 + 3),
            )
        else:
            leg_h = 52
            pygame.draw.rect(screen, (36, 42, 58), (ux - 4, leg_y0, UI_PANEL_W - 20, leg_h))
            pygame.draw.rect(screen, (95, 108, 145), (ux - 4, leg_y0, UI_PANEL_W - 20, leg_h), 1)
            screen.blit(small.render("マップ凡例", True, (220, 230, 250)), (ux, leg_y0 + 4))
            screen.blit(
                small.render("詳細は左ペイン上部（タイトル直下）を参照。", True, (215, 224, 235)),
                (ux, leg_y0 + 22),
            )
            screen.blit(
                small.render("Tab: このメモを一行に省略", True, (200, 212, 228)),
                (ux, leg_y0 + 36),
            )
        party_y0 = leg_y0 + leg_h + 6
        pygame.draw.rect(screen, (38, 46, 62), (ux - 4, party_y0, UI_PANEL_W - 20, 22))
        screen.blit(small.render("仲間", True, (230, 235, 250)), (ux, party_y0 + 2))
        for i, p in enumerate(player["party"][:MAX_PARTY_MEMBERS]):
            yy = party_y0 + 26 + i * 28
            nm = f"{p['name'][:6]}" + ("…" if len(p["name"]) > 6 else "")
            line = f"{i + 1}.{nm} Lv{p['level']}"
            screen.blit(small.render(line, True, (220, 228, 238)), (ux, yy))
            draw_bar(ux + bar_w - 118, yy + 2, 116, 9, p["hp"], p["max_hp"], fg=(85, 210, 115))

        qy = party_y0 + 26 + MAX_PARTY_MEMBERS * 28 + 10
        qt = " / ".join([f"{q['title'][:10]}:{'済' if q['done'] else '未'}" for q in player["quests"][:2]])
        if len(qt) > 34:
            qt = qt[:33] + "…"
        screen.blit(small.render(f"Quest {qt}", True, (200, 220, 255)), (ux, qy))
        mh = mood_hint_text()
        if mh:
            mh_disp = mh[:36] + ("…" if len(mh) > 36 else "")
            screen.blit(small.render(mh_disp, True, (190, 205, 230)), (ux, qy + 20))

        hint_bar_y = HEIGHT - 48
        hint_bar_h = 46
        vw = VIEWPORT_W - 16
        foot_rgb = (max(8, band[0] - 10), max(8, band[1] - 10), max(8, band[2] - 10))
        foot_edge = (min(255, foot_rgb[0] + 70), min(255, foot_rgb[1] + 75), min(255, foot_rgb[2] + 85))
        goal_txt = next_goal_one_line()
        if len(goal_txt) > 54:
            goal_txt = goal_txt[:53] + "…"
        pygame.draw.rect(screen, (26, 30, 44), (8, hint_bar_y - 58, vw, 24))
        pygame.draw.rect(screen, (95, 108, 142), (8, hint_bar_y - 58, vw, 24), 1)
        screen.blit(small.render(goal_txt, True, (205, 222, 242)), (14, hint_bar_y - 54))
        if battle_log:
            ly = hint_bar_y - 32
            pygame.draw.rect(screen, foot_rgb, (8, ly - 2, vw, 28))
            pygame.draw.rect(screen, foot_edge, (8, ly - 2, vw, 28), 1)
            screen.blit(small.render(battle_log[:76], True, (255, 245, 225)), (14, ly))
        pygame.draw.rect(screen, foot_rgb, (8, hint_bar_y, vw, hint_bar_h))
        pygame.draw.rect(screen, foot_edge, (8, hint_bar_y, vw, hint_bar_h), 1)
        screen.blit(
            small.render(
                "[ ] BGM  F8 効果音   移動 WASD / 矢印（押しっぱなしで自由移動・斜め可）   Tab 凡例   F11 画面",
                True,
                (235, 240, 255),
            ),
            (14, hint_bar_y + 14),
        )

    elif mode=="party":
        screen.blit(big.render("パーティ編成",True,(255,255,0)),(350,50))
        row = 56
        for i,p in enumerate(player["party"][:MAX_PARTY_MEMBERS]):
            tag = "（離脱）" if p.get("absent") else ""
            y0 = 130 + i * row
            screen.blit(font.render(f"{i}:{p['name']}{tag} HP:{p['hp']}/{p['max_hp']} ATK:{p['atk']}",True,(255,255,255)),(280,y0))
            role = ALLY_ROLE_TAG.get(p.get("name"), "")
            if role:
                screen.blit(small.render(f"    {role}", True, (190, 210, 235)), (280, y0 + 22))
        screen.blit(font.render("数字で入替 / ESCで戻る",True,(255,255,255)),(350,420))

    elif mode == "codex":
        screen.fill((16, 18, 30))
        screen.blit(big.render("図鑑・実績", True, (255, 220, 120)), (380, 28))
        dlab = {"easy": "易しい（昼の回復判断が早い）", "normal": "ふつう", "hard": "きつめ（昼の回復判断が遅い）"}.get(
            tactics_difficulty(), "ふつう"
        )
        screen.blit(small.render(f"戦闘難易: {dlab}  ※鍛錬メニューで 6 切替", True, (200, 210, 235)), (260, 72))
        cb = player.get("codex_bosses", []) or []
        cr = player.get("codex_rares", []) or []
        cn = player.get("codex_normals", []) or []
        if not cn and not cb and not cr:
            cn = list(player.get("codex_enemies", []) or [])
        cs = player.get("codex_skills", []) or []
        ci = player.get("codex_items", []) or []
        ach = player.get("achievements", {}) or {}
        ux, y = 40, 96
        screen.blit(font.render(f"★ボス {len(cb)}種", True, (255, 220, 140)), (ux, y))
        y += 28
        for nm in cb[:7]:
            screen.blit(small.render(f"★ {nm}", True, (255, 230, 200)), (ux, y))
            y += 22
        if len(cb) > 7:
            screen.blit(small.render(f"…ほか {len(cb) - 7}", True, (160, 150, 120)), (ux, y))
            y += 22
        y += 6
        screen.blit(font.render(f"☆レア {len(cr)}種", True, (220, 200, 255)), (ux, y))
        y += 28
        for nm in cr[:7]:
            screen.blit(small.render(f"☆ {nm}", True, (215, 200, 245)), (ux, y))
            y += 22
        if len(cr) > 7:
            screen.blit(small.render(f"…ほか {len(cr) - 7}", True, (140, 130, 170)), (ux, y))
            y += 22
        y += 6
        screen.blit(font.render(f"通常 {len(cn)}種", True, (200, 220, 235)), (ux, y))
        y += 28
        for nm in cn[:8]:
            screen.blit(small.render(f"・{nm}", True, (185, 200, 220)), (ux, y))
            y += 20
        if len(cn) > 8:
            screen.blit(small.render(f"…ほか {len(cn) - 8}", True, (130, 150, 175)), (ux, y))
        screen.blit(font.render(f"仲間の術 {len(cs)}種", True, (230, 230, 245)), (480, 96))
        y2 = 126
        for nm in cs[:14]:
            screen.blit(small.render(f"・{nm}", True, (200, 215, 235)), (480, y2))
            y2 += 20
        if len(cs) > 14:
            screen.blit(small.render(f"…ほか {len(cs) - 14}", True, (150, 165, 190)), (480, y2))
        screen.blit(font.render(f"入手アイテム {len(ci)}種", True, (230, 245, 220)), (480, 330))
        y3 = 358
        for nm in ci[:12]:
            screen.blit(small.render(f"・{nm}", True, (200, 225, 205)), (480, y3))
            y3 += 20
        if len(ci) > 12:
            screen.blit(small.render(f"…ほか {len(ci) - 12}", True, (150, 170, 155)), (480, y3))
        screen.blit(font.render("実績", True, (255, 230, 160)), (40, 400))
        ya = 432
        for k, label in ACHIEVEMENT_LABELS.items():
            got = ach.get(k)
            col = (160, 240, 170) if got else (120, 120, 140)
            mark = "[済] " if got else "[  ] "
            screen.blit(small.render(f"{mark}{label}", True, col), (40, ya))
            ya += 24
        screen.blit(small.render("ボスは雷/聖/火の弱点が1つ。術と刻印の組み合わせで伸ばせます。", True, (190, 200, 220)), (40, 580))
        screen.blit(small.render("ESC: ワールドへ戻る", True, (210, 210, 230)), (380, 660))

    elif mode=="inventory":
        screen.blit(big.render("INVENTORY", True, (255, 230, 120)), (320, 40))
        screen.blit(font.render(f"装備: 武器={player['weapon']} / 防具={player['armor']}", True, (230, 230, 210)), (140, 95))
        screen.blit(font.render("↑↓:選択 E:装備 U:消費 S:売却 X:捨てる N:下と入替 ESC:戻る", True, (210, 230, 255)), (140, 122))
        inv = player["inventory"]
        if inv:
            for i, item in enumerate(inv[:14]):
                y = 160 + i * 30
                sel = i == inventory_selected
                color = (255, 255, 140) if sel else (220, 220, 220)
                prefix = ">" if sel else " "
                blit_item_icon(screen, item, 118, y - 2, 30)
                screen.blit(font.render(f"{prefix} {item}", True, color), (158, y))
        else:
            screen.blit(font.render("インベントリは空です", True, (210, 210, 210)), (180, 180))

    elif mode=="town":
        draw_town_backdrop(screen)
        screen.blit(big.render("TOWN", True, (255, 242, 180)), (370, 58))
        panel = pygame.Surface((640, 300), pygame.SRCALPHA)
        panel.fill((24, 20, 38, 208))
        screen.blit(panel, (180, 140))
        pygame.draw.rect(screen, (228, 206, 150), (180, 140, 640, 300), 2)
        pygame.draw.rect(screen, (255, 243, 208), (186, 146, 628, 288), 1)
        kf_eth = f"town_ethics_{floor_number}"
        if town_mode == "ethics":
            screen.blit(font.render("村人: 怪我人の荷物が…どうする？", True, (255, 245, 220)), (200, 175))
            for i, opt in enumerate(TOWN_ETHICS_OPTIONS):
                screen.blit(font.render(f"{i+1}. {opt['text']}", True, (244, 238, 255)), (200, 215 + i * 38))
            screen.blit(small.render("1〜3: 決断（性格に影響）  ESC: 広場に戻る", True, (225, 225, 206)), (200, 390))
        elif town_mode == "hub":
            screen.blit(font.render("広場 — 旅人と村人が行き交う。", True, (255, 245, 220)), (200, 165))
            y0 = 198
            for i, npc in enumerate(TOWN_NPC_SCRIPTS):
                screen.blit(small.render(f"{i+1}. {npc['name']}", True, (230, 228, 255)), (200, y0 + i * 22))
            y1 = y0 + len(TOWN_NPC_SCRIPTS) * 22 + 12
            if not player.get("story_flags", {}).get(kf_eth):
                screen.blit(small.render("E: 難儀の噂を聞く（大きな道徳の選択）", True, (255, 215, 175)), (200, y1))
                y1 += 22
            else:
                screen.blit(small.render("（この階の大きな難儀はもう聞いた）", True, (175, 185, 200)), (200, y1))
                y1 += 22
            screen.blit(small.render("S: ショップ   ESC: 町を出る", True, (220, 220, 210)), (200, y1))
        elif town_mode == "npc" and 0 <= town_npc_id < len(TOWN_NPC_SCRIPTS):
            scr = TOWN_NPC_SCRIPTS[town_npc_id]
            screen.blit(font.render(scr["name"], True, (255, 230, 140)), (200, 165))
            lines = scr["lines"]
            li = min(town_npc_line, max(0, len(lines) - 1))
            screen.blit(font.render(lines[li], True, (255, 240, 225)), (200, 205))
            if li < len(lines) - 1:
                hint = "C: 次の台詞  ESC: 広場へ"
            elif scr.get("choices"):
                hint = "C: 選択肢へ"
            else:
                hint = "C: 別れを告げる  ESC: 広場へ"
            screen.blit(small.render(hint, True, (208, 208, 228)), (200, 392))
        elif town_mode == "npc_choice" and 0 <= town_npc_id < len(TOWN_NPC_SCRIPTS):
            scr = TOWN_NPC_SCRIPTS[town_npc_id]
            screen.blit(font.render(f"{scr['name']} — 問い", True, (255, 215, 160)), (200, 165))
            for i, opt in enumerate(scr.get("choices", [])):
                screen.blit(font.render(f"{i+1}. {opt['text']}", True, (230, 232, 255)), (200, 205 + i * 36))
            screen.blit(
                small.render("1〜3: 決断（性格・仲間の絆イベントの引き金になり得る） ESC: 広場へ", True, (205, 195, 195)),
                (200, 390),
            )

    elif mode=="shop":
        cat = shop_catalog()
        mx_s = max(0, len(cat) - SHOP_PAGE)
        shop_scroll_clamped = min(shop_scroll, mx_s)
        screen.blit(big.render("SHOP", True, (255, 230, 120)), (370, 36))
        screen.blit(font.render(f"所持ゴールド: {player['gold']} G", True, (255, 230, 120)), (320, 82))
        screen.blit(small.render(f"この階({floor_number}F)で解禁されている品（階が進むと強化）", True, (190, 210, 235)), (220, 72))
        last_i = min(len(cat), shop_scroll_clamped + SHOP_PAGE)
        screen.blit(small.render(f"↑↓でスクロール  商品 {shop_scroll_clamped + 1}〜{last_i} / {len(cat)}  1〜9で購入", True, (200, 210, 230)), (220, 108))
        visible = cat[shop_scroll_clamped : shop_scroll_clamped + SHOP_PAGE]
        for i, item in enumerate(visible):
            y = 138 + i * 48
            blit_item_icon(screen, item["name"], 210, y - 4, 40)
            label = f"{i+1}. {item['name']}  ({item['type']})  {item['price']}G"
            screen.blit(font.render(label, True, (225, 225, 225)), (262, y + 8))
        inv = ", ".join(player["inventory"][-5:]) if player["inventory"] else "なし"
        screen.blit(small.render(f"所持(末尾): {inv}", True, (200, 210, 250)), (180, 620))
        screen.blit(font.render("ESC: 町へ戻る", True, (230, 230, 230)), (400, 660))

    elif mode=="shop_choice":
        screen.blit(big.render("購入方法を選択", True, (255, 230, 120)), (280, 180))
        cat_sc = shop_catalog()
        if 0 <= selected_shop_item_index < len(cat_sc):
            item = cat_sc[selected_shop_item_index]
            blit_item_icon(screen, item["name"], 420, 232, 48)
            screen.blit(font.render(f"{item['name']} をどうする？", True, (240, 240, 240)), (340, 292))
        screen.blit(font.render("I: インベントリに入れる", True, (220, 220, 255)), (350, 330))
        screen.blit(font.render("E: 即装備する", True, (220, 255, 220)), (350, 365))
        screen.blit(font.render("F: 盗む（道徳大ダメージ）", True, (255, 180, 160)), (350, 400))
        screen.blit(font.render("ESC: キャンセル(返金)", True, (255, 220, 220)), (350, 430))

    elif mode=="battle":
        if boss_intro_timer > 0:
            boss_intro_timer -= 1
            t = boss_intro_timer
            screen.fill((14, 10, 20))
            veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fade_in = 140 - t
            if t > 88:
                veil.fill((0, 0, 0, min(210, max(0, fade_in) * 5)))
            screen.blit(veil, (0, 0))
            if t <= 88 and t > 38:
                bc = images.get("boss_cutin")
                if bc:
                    screen.blit(bc, (WIDTH // 2 - bc.get_width() // 2, 110))
                screen.blit(big.render("BOSS WARNING!!", True, (255, 70, 100)), (300, 285))
                pygame.draw.rect(screen, (80, 30, 45), (0, HEIGHT - 72, WIDTH, 72))
            if t <= 38 and t > 12:
                flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                flash.fill((255, 255, 255, 55 + (38 - t)))
                screen.blit(flash, (0, 0))
                step = (t % 8) * 30
                pygame.draw.rect(screen, (255, 240, 160), (step, HEIGHT // 2, WIDTH, 6))
                pygame.draw.rect(screen, (255, 200, 80), (0, HEIGHT // 2 + 20, WIDTH, 3))
        else:
            screen.fill((8, 10, 26))
            shx = random.randint(-7, 7) if battle_ui_shake > 0 else 0
            if battle_ui_shake > 0:
                battle_ui_shake -= 1
            draw_battle_showcase_bg(screen, shx)
            draw_retro_frame(screen, 8 + shx, 36, 304, 658)
            draw_retro_frame(screen, 320 + shx, 36, 272, 328)
            draw_retro_frame(screen, 602 + shx, 36, 392, 658)
            if battle_timeline_text:
                screen.blit(small.render(battle_timeline_text[:56], True, (235, 220, 160)), (22 + shx, 18))

            screen.blit(font.render("勇者", True, (230, 235, 255)), (20 + shx, 44))
            draw_bar(20 + shx, 64, 276, 12, player["hp"], player["max_hp"], fg=(90, 230, 90))
            screen.blit(small.render(f"HP {player['hp']}/{player['max_hp']}", True, (210, 255, 210)), (20 + shx, 78))
            draw_bar(20 + shx, 96, 276, 10, player["mp"], player["max_mp"], fg=(100, 160, 255))
            screen.blit(small.render(f"MP {player['mp']}/{player['max_mp']}  ATK{get_atk()}", True, (200, 220, 255)), (20 + shx, 108))
            sp_short = " / ".join(player["skills"][:5])
            if len(player["skills"]) > 5:
                sp_short += "…"
            screen.blit(small.render(f"呪文 {sp_short}", True, (175, 200, 240)), (20 + shx, 124))

            py = 156
            for i, p in enumerate(player["party"][:MAX_PARTY_MEMBERS]):
                face = party_portraits.get(p["name"])
                if face:
                    face = retro_scale_surface(face, 34, 34)
                else:
                    face = procedural_ally_sprite(p["name"], 34, 34)
                screen.blit(face, (16 + shx, py))
                px = 56 + shx
                learned = "→".join(p.get("skills", [])[:2])
                if len(p.get("skills", [])) > 2:
                    learned += "…"
                nm = f"{p['name']}(離脱)" if p.get("absent") else p["name"]
                col = (110, 110, 120) if p.get("absent") else (220, 220, 230)
                screen.blit(small.render(f"{nm} ATK{p['atk']}", True, col), (px, py))
                screen.blit(small.render(learned, True, (145, 185, 225)), (px, py + 16))
                draw_bar(px, py + 32, 232, 8, p["hp"], p["max_hp"], fg=(120, 220, 120))
                draw_bar(px, py + 42, 160, 6, p.get("mp", 0), max(1, p.get("max_mp", 1)), fg=(120, 170, 255))
                py += 88

            if battle_enemies:
                nbe = len(battle_enemies)
                # 敵数を一目で分かるようにヘッダにバッジ表示
                hdr_label = "敵（Q/Eで狙い）" if nbe > 1 else "敵"
                screen.blit(font.render(hdr_label, True, (255, 170, 170)), (332 + shx, 44))
                if nbe > 1:
                    # 「×N」バッジで複数戦と分かるように
                    badge_x = 332 + shx + font.size(hdr_label)[0] + 12
                    badge_y = 42
                    pygame.draw.rect(screen, (190, 40, 60), (badge_x, badge_y, 56, 24), border_radius=4)
                    pygame.draw.rect(screen, (255, 220, 180), (badge_x, badge_y, 56, 24), 2, border_radius=4)
                    screen.blit(font.render(f"x{nbe}", True, (255, 245, 220)), (badge_x + 12, badge_y + 1))
                panel_inner = 250
                gap = 8 if nbe > 1 else 0
                slot_w = (panel_inner - gap * max(0, nbe - 1)) // max(1, nbe)
                slot_top = 76
                slot_panel_h = 236
                # 複数戦はやや小さめに、単体戦は大きく見せる
                if nbe <= 1:
                    sp_sz = 96
                elif nbe == 2:
                    sp_sz = 80
                else:
                    sp_sz = max(48, min(72, slot_w - 6))
                living_count = sum(1 for e in battle_enemies if e and e.get("hp", 0) > 0)
                _pulse = (math.sin(pygame.time.get_ticks() * 0.008) * 0.5 + 0.5)
                for bi, ed in enumerate(battle_enemies):
                    x0 = int(332 + shx + bi * (slot_w + gap))
                    alive = ed.get("hp", 0) > 0
                    is_tg = alive and bi == battle_target_enemy_index
                    mxhp = max(1, ed.get("max_hp", 1))
                    hp = max(0, int(ed["hp"]))
                    # 深度感のためにわずかに上下ジグザグ
                    depth_off = 0 if nbe <= 1 else ((bi % 2) * -6 + 3)
                    if nbe > 1 and alive:
                        if is_tg:
                            pulse_alpha = int(56 + _pulse * 28)
                            hi = pygame.Surface((slot_w + 10, slot_panel_h), pygame.SRCALPHA)
                            hi.fill((255, 235, 140, pulse_alpha))
                            screen.blit(hi, (x0 - 5, slot_top - 4))
                            pygame.draw.rect(
                                screen,
                                (255, 215, 70),
                                (x0 - 5, slot_top - 4, slot_w + 10, slot_panel_h),
                                3,
                            )
                            # ターゲット矢印
                            tri_y = slot_top - 12
                            pygame.draw.polygon(
                                screen,
                                (255, 230, 110),
                                [
                                    (x0 + slot_w // 2 - 8, tri_y - 8),
                                    (x0 + slot_w // 2 + 8, tri_y - 8),
                                    (x0 + slot_w // 2, tri_y + 2),
                                ],
                            )
                        else:
                            pygame.draw.rect(
                                screen,
                                (110, 92, 132),
                                (x0 - 2, slot_top - 1, slot_w + 4, slot_panel_h - 6),
                                1,
                            )
                    nm_col = (255, 255, 235) if is_tg else ((255, 215, 215) if alive else (130, 110, 110))
                    nm = str(ed.get("name", "?"))
                    if len(nm) > 11:
                        nm = nm[:10] + "…"
                    # 個体ナンバー (1〜) を強調表示してどの敵か分かりやすく
                    if nbe > 1:
                        idx_bg = pygame.Surface((22, 22), pygame.SRCALPHA)
                        idx_bg.fill((20, 20, 32, 200))
                        screen.blit(idx_bg, (x0 - 4, slot_top - 14))
                        pygame.draw.rect(
                            screen,
                            (255, 215, 90) if is_tg else (200, 200, 235),
                            (x0 - 4, slot_top - 14, 22, 22),
                            2,
                        )
                        screen.blit(small.render(str(bi + 1), True, (255, 250, 220)), (x0 + 2, slot_top - 12))
                    screen.blit(small.render(nm, True, nm_col), (x0 + (24 if nbe > 1 else 0), slot_top))
                    hp_lab = f"{hp} / {mxhp}"
                    screen.blit(
                        small.render(hp_lab, True, (210, 190, 190) if alive else (120, 100, 100)),
                        (x0, slot_top + 19),
                    )
                    draw_bar(x0, slot_top + 38, slot_w, 12, hp, mxhp, fg=(255, 95, 95) if alive else (90, 70, 75))
                    enemy_img = ed.get("sprite") or images.get(ed.get("image_key"))
                    jx = 5 if (enemy_shake_timer > 0 or battle_ui_shake > 0) else 0
                    sx = random.randint(-jx, jx) if enemy_shake_timer > 0 else 0
                    sy = random.randint(-3, 3) if enemy_shake_timer > 0 else 0
                    ex = x0 + max(0, (slot_w - sp_sz) // 2) + sx
                    ey = slot_top + 56 + sy + depth_off
                    # 敵の足元に影を入れて複数いる時の立体感を出す
                    shadow = pygame.Surface((sp_sz, max(4, sp_sz // 6)), pygame.SRCALPHA)
                    pygame.draw.ellipse(shadow, (10, 12, 22, 140), shadow.get_rect())
                    screen.blit(shadow, (ex, ey + sp_sz - max(4, sp_sz // 6) // 2))
                    if enemy_img:
                        screen.blit(retro_scale_surface(enemy_img, sp_sz, sp_sz), (ex, ey))
                    else:
                        pe = procedural_enemy_sprite(ed)
                        if pe.get_width() != sp_sz:
                            pe = pygame.transform.scale(pe, (sp_sz, sp_sz))
                        screen.blit(pe, (ex, ey))
                    # ターゲット中の敵は薄い縁取り（白）を加えて視認性UP
                    if is_tg and alive and nbe > 1:
                        ring = pygame.Surface((sp_sz + 8, sp_sz + 8), pygame.SRCALPHA)
                        pygame.draw.rect(
                            ring,
                            (255, 235, 130, 180),
                            ring.get_rect(),
                            3,
                            border_radius=8,
                        )
                        screen.blit(ring, (ex - 4, ey - 4))
                    if not alive:
                        veil = pygame.Surface((sp_sz, sp_sz), pygame.SRCALPHA)
                        veil.fill((18, 14, 28, 150))
                        screen.blit(veil, (ex, ey))
                        # ×印を重ねて倒したことを明確に
                        pygame.draw.line(screen, (255, 90, 90), (ex + 8, ey + 8), (ex + sp_sz - 8, ey + sp_sz - 8), 3)
                        pygame.draw.line(screen, (255, 90, 90), (ex + sp_sz - 8, ey + 8), (ex + 8, ey + sp_sz - 8), 3)
                if nbe > 1:
                    screen.blit(
                        small.render(
                            f"◀ Q 狙い替え E ▶   生存 {living_count}/{nbe}",
                            True,
                            (185, 205, 255),
                        ),
                        (332 + shx, slot_top + slot_panel_h + 2),
                    )
            elif enemy is not None:
                screen.blit(font.render("敵", True, (255, 170, 170)), (332 + shx, 44))
                screen.blit(small.render(str(enemy["name"]), True, (255, 210, 210)), (332 + shx, 66))
                draw_bar(332 + shx, 84, 248, 14, max(0, enemy["hp"]), max(1, enemy.get("max_hp", 1)), fg=(255, 90, 90))
                enemy_img = enemy.get("sprite") or images.get(enemy.get("image_key"))
                jx = 5 if (enemy_shake_timer > 0 or battle_ui_shake > 0) else 0
                ex = 368 + shx + (random.randint(-jx, jx) if enemy_shake_timer > 0 else 0)
                ey = 118 + (random.randint(-3, 3) if enemy_shake_timer > 0 else 0)
                if enemy_img:
                    screen.blit(retro_scale_surface(enemy_img, 72, 72), (ex, ey))
                else:
                    screen.blit(procedural_enemy_sprite(enemy), (ex, ey))

            rx, ry = 608 + shx, 42
            cmd_panel_w = WIDTH - rx - 14
            pauto = player.get("party_battle_mode") == "auto"
            plan_hdr = "行動（仲間オート）" if pauto else "行動予約（←→で対象）"
            screen.blit(font.render(plan_hdr, True, (255, 245, 210)), (rx, ry))
            ry += 26
            if battle_plan_units:
                for pi, pk in enumerate(battle_plan_units):
                    nm = "勇者" if pk == "hero" else player["party"][pk]["name"]
                    if pauto and pk != "hero":
                        sel = " "
                        lab = f"{pending_label(pk)} [自動]"
                    else:
                        sel = ">" if pi == (battle_plan_focus % len(battle_plan_units)) else " "
                        lab = pending_label(pk)
                    screen.blit(small.render(f"{sel}{nm}: {lab}", True, (228, 228, 248)), (rx, ry))
                    ry += 18
            ry = max(ry, 192)
            fk_cmd = plan_focused_key()
            box_top = ry + 4
            guide_h = 96
            pygame.draw.rect(screen, (16, 18, 38), (rx - 6, box_top, cmd_panel_w, guide_h))
            pygame.draw.rect(screen, (95, 110, 175), (rx - 6, box_top, cmd_panel_w, guide_h), 1)
            gy = box_top + 10
            if fk_cmd == "hero":
                screen.blit(small.render("1 攻撃   2 呪文   3 防御   4 逃走", True, (255, 250, 220)), (rx, gy))
            else:
                screen.blit(small.render("1 攻撃   2 呪文   3 防御", True, (255, 250, 220)), (rx, gy))
            gy += 26
            screen.blit(font.render("ENTER  ターン実行", True, (130, 255, 155)), (rx, gy))
            gy += 30
            screen.blit(small.render("T オート切替   Q/E 敵の狙い（複数時）", True, (165, 205, 250)), (rx, gy))
            draw_retro_frame(screen, 612 + shx, 360, 372, 320, inner=(12, 16, 32), border=(200, 205, 230))
            screen.blit(small.render("[ログ]", True, (190, 195, 220)), (620 + shx, 366))
            log_txt = battle_log if battle_log else "—"
            screen.blit(small.render(log_txt[:52], True, (255, 228, 195)), (620 + shx, 384))
            screen.blit(small.render(log_txt[52:104], True, (255, 225, 188)), (620 + shx, 404))
            screen.blit(small.render(log_txt[104:156], True, (255, 225, 188)), (620 + shx, 424))
            screen.blit(small.render(log_txt[156:208], True, (255, 225, 188)), (620 + shx, 444))
            if slash_timer > 0:
                pygame.draw.line(screen, (255, 100, 130), (60 + shx, 340), (WIDTH - 100 + shx, 338), 4)
                slash_timer -= 1

            draw_battle_vfx_layer(screen, shx)
            draw_battle_action_fx(screen, shx)
            draw_battle_damage_popups(screen)
            draw_battle_crit_cutin(screen)
            if battle_vfx is not None:
                _vk, _vt = battle_vfx
                battle_vfx = None if _vt <= 1 else (_vk, _vt - 1)

            if spell_menu_target is not None:
                dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 185))
                screen.blit(dim, (0, 0))
                bx, by, bw, bh = 80, 40, 920, 520
                draw_retro_frame(screen, bx, by, bw, bh, inner=(16, 20, 38), border=(235, 232, 250))
                spells_use = player["skills"][:9] if spell_menu_target == "hero" else player["party"][spell_menu_target].get("skills", [])[:9]
                nsp = len(spells_use)
                cur_i = min(max(0, spell_menu_cursor), max(0, nsp - 1)) if nsp else 0
                if spell_menu_target == "hero":
                    screen.blit(big.render("勇者の呪文", True, (255, 230, 140)), (400, 52))
                else:
                    am = player["party"][spell_menu_target]
                    screen.blit(big.render(f"{am['name']}の呪文", True, (255, 220, 180)), (380, 52))
                mx, my = 110, 100
                for i, sp in enumerate(spells_use):
                    if spell_menu_target == "hero":
                        cost = int(skills_data.get(sp, {}).get("cost", 0))
                        ok_mp = player["mp"] >= cost
                    else:
                        am = player["party"][spell_menu_target]
                        cost = MEMBER_SPELL_MP.get(sp, 0)
                        ok_mp = am.get("mp", 0) >= cost
                    is_cur = i == cur_i
                    col = (255, 245, 130) if is_cur else ((230, 235, 255) if ok_mp else (110, 110, 130))
                    mark = ">" if is_cur else " "
                    screen.blit(font.render(f"{mark}{i+1}. {sp}  MP{cost}", True, col), (mx, my + i * 34))
                desc_sp = spells_use[cur_i] if nsp else ""
                desc = get_spell_description(desc_sp) if desc_sp else "呪文がありません。"
                screen.blit(font.render("【説明】", True, (210, 235, 255)), (520, 96))
                dy = 128
                pos = 0
                while pos < len(desc) and dy < 430:
                    chunk = desc[pos : pos + 34]
                    screen.blit(small.render(chunk, True, (205, 220, 240)), (520, dy))
                    dy += 22
                    pos += 34
                screen.blit(small.render("↑↓:カーソル  数字:決定  ESC:戻る", True, (190, 200, 225)), (mx, 492))

    elif mode == "companion_crisis":
        screen.fill((18, 16, 28))
        pygame.draw.rect(screen, (48, 42, 72), (120, 80, 760, 480))
        pygame.draw.rect(screen, (200, 190, 240), (120, 80, 760, 480), 2)
        st = bond_crisis_state or {}
        path = st.get("path", "")
        step = st.get("step", 0)
        lines = []
        if path == "priest_leave":
            lines = (
                ["僧侶が足を止め、震える声で言った。", "「これ以上は…ついていけません。」", "1: 話を聞き、歩みを合わせる", "2: 背を向け、距離を置く"]
                if step == 0
                else ["僧侶の瞳に涙が浮かぶ。", "「…本当に、私を捨てるのですか。」", "1: やめてくれと懇願する", "2: 去ることを告げる"]
            )
        elif path == "warrior_awaken":
            lines = ["戦士の瞳に炎が宿った。", "「…本気を見せてやる。覚悟はいいか？」", "1: 共に戦え（覚醒・強化）", "2: まだ抑えろ"]
        elif path == "archer_oath":
            lines = ["弓使いが不意に笑う。", "「お前の背中、悪くない。…任せてみるか。」", "1: 頼む（会心の誓い）", "2: 照れるからやめろ"]
        elif path == "dark_merc":
            lines = [
                "闇が人の形をまとい、囁く。",
                "「契約しよう。お前の欲を、俺が斬る代わりに…魂の一片をよこせ。」",
                "1: 契約する（空き枠に闇傭兵）",
                "2: 断る",
            ]
        y = 110
        for ln in lines:
            screen.blit(font.render(ln, True, (240, 236, 255)), (150, y))
            y += 36
        screen.blit(small.render("数字キーで選択  ESCは穏便な選択（説得寄り）", True, (200, 200, 220)), (150, 520))

    elif mode == "build_menu":
        screen.fill((22, 22, 34))
        screen.blit(big.render("鍛錬（ビルド）", True, (255, 220, 120)), (360, 60))
        b = _player_build()
        screen.blit(font.render(f"スキルポイント: {player.get('skill_points', 0)}  （レベルアップで+1）", True, (230, 230, 230)), (220, 120))
        screen.blit(font.render(f"1: 呪文火力 [{b['spell_power']}/8]  ※威力・回復量", True, (220, 230, 230)), (220, 165))
        screen.blit(font.render(f"2: デバフ特化 [{b['debuff_focus']}/8]  ※毒・麻痺付与", True, (220, 230, 230)), (220, 200))
        screen.blit(font.render(f"3: 会心 [{b['crit_focus']}/8]  ※物理クリ率", True, (220, 230, 230)), (220, 235))
        screen.blit(font.render(f"4: 守護 [{b['guard_focus']}/8]  ※防御時の被ダメ軽減", True, (220, 230, 230)), (220, 270))
        seal = player.get("seal")
        seal_txt = "なし" if seal is None else str(seal)
        screen.blit(font.render(f"5: 刻印を切替（現在: {seal_txt}）火→雷→光→なし", True, (220, 245, 200)), (220, 305))
        dtxt = {"easy": "易", "normal": "ふつう", "hard": "きつめ"}.get(tactics_difficulty(), "ふつう")
        screen.blit(font.render(f"6: 戦闘難易（現在: {dtxt}）平常→易→きつめ", True, (220, 200, 255)), (220, 338))
        screen.blit(small.render("1〜4:スキル消費  5:刻印  6:難易  ESC:戻る", True, (200, 200, 220)), (300, 378))

    elif mode=="event_choice":
        screen.blit(big.render("運命の選択", True, (255, 220, 120)), (330, 120))
        screen.blit(font.render("1:禁断の力を受け入れる(ATK大幅UP/最大HP減)", True, (255, 220, 220)), (140, 260))
        screen.blit(font.render("2:聖印を結ぶ(最大HP/防御系強化)", True, (220, 255, 220)), (140, 300))
        screen.blit(font.render("3:叡智の契約(MP/呪文強化)", True, (220, 220, 255)), (140, 340))
        screen.blit(font.render("数字キーで選択", True, (230, 230, 230)), (140, 390))

    elif mode=="floor_buff":
        tier = pending_floor_buff_tier or 0
        screen.blit(big.render("階層の恩恵（永久・一度だけ）", True, (255, 230, 120)), (220, 80))
        screen.blit(font.render(f"区間 {tier} の報酬を1つ選んでください", True, (230, 230, 230)), (260, 140))
        screen.blit(font.render(f"1: 攻撃力 +{2 + tier}（永久）", True, (255, 220, 200)), (260, 200))
        screen.blit(font.render(f"2: 守備補正 +{2 + tier}（永久・防具に加算）", True, (220, 240, 255)), (260, 240))
        screen.blit(font.render(f"3: 最大HP +{15 + tier * 5} / 最大MP +{8 + tier * 2}", True, (220, 255, 220)), (260, 280))
        screen.blit(font.render("数字キーで決定", True, (220, 220, 220)), (380, 360))

    elif mode=="stairs_confirm":
        screen.blit(big.render("次の階へ進む？", True, (255, 230, 120)), (280, 220))
        screen.blit(font.render("ENTER: 進む / ESC: やめる", True, (240, 240, 240)), (320, 300))

    elif mode=="ending":
        screen.blit(big.render("ENDING", True, (255, 230, 120)), (360, 80))
        et = get_ending_text()
        y0 = 140
        for li, chunk in enumerate([et[i : i + 34] for i in range(0, len(et), 34)]):
            screen.blit(small.render(chunk, True, (240, 240, 245)), (80, y0 + li * 22))
        screen.blit(font.render("ESC: タイトルへ", True, (220, 220, 220)), (420, 620))

    if mode in ("world", "battle", "town", "story"):
        pygame.draw.rect(screen, (22, 24, 34), (0, HEIGHT - 24, WIDTH, 24))
        screen.blit(small.render("F11 / Alt+Enter … 画面サイズ（フルスクリーン）", True, (170, 182, 205)), (12, HEIGHT - 20))

    if flash_timer > 0:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        alpha = min(180, flash_timer * 25)
        overlay.fill((255, 255, 255, alpha))
        screen.blit(overlay, (0, 0))
        flash_timer -= 1
    if enemy_shake_timer > 0:
        enemy_shake_timer -= 1
    if encounter_flash > 0:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, min(120, encounter_flash * 30)))
        screen.blit(overlay, (0, 0))
        encounter_flash -= 1

    present_frame()

# ===== メイン =====
_last_periodic_autosave_ms = pygame.time.get_ticks()
running=True
# ワールド探索は 60 FPS で滑らかに、その他は 30 FPS（演出タイマー互換）
WORLD_TARGET_FPS = 60
DEFAULT_TARGET_FPS = 30
while running:
    if crit_slow_timer > 0:
        clock.tick(11)
        crit_slow_timer -= 1
    elif mode == "world":
        clock.tick(WORLD_TARGET_FPS)
    else:
        clock.tick(DEFAULT_TARGET_FPS)

    for e in pygame.event.get():
        if e.type==pygame.QUIT:
            running=False

        elif e.type == pygame.VIDEORESIZE and not fullscreen_display:
            nw = getattr(e, "w", None)
            nh = getattr(e, "h", None)
            if (nw is None or nh is None) and hasattr(e, "size"):
                nw, nh = e.size
            if nw and nh:
                windowed_size[0] = max(480, min(int(nw), 4096))
                windowed_size[1] = max(360, min(int(nh), 4096))
                try:
                    display_window = pygame.display.set_mode(
                        (windowed_size[0], windowed_size[1]), pygame.RESIZABLE
                    )
                except pygame.error:
                    pass

        elif e.type==pygame.KEYDOWN:
            if e.key == pygame.K_F11 or (
                e.key == pygame.K_RETURN and (e.mod & pygame.KMOD_ALT)
            ):
                play_ui_sound()
                toggle_fullscreen()

            elif mode=="title":
                if e.key==pygame.K_RETURN:
                    play_ui_sound()
                    music_silence_immediate()
                    mode="world"
                elif e.key==pygame.K_SPACE and story_current_id:
                    play_ui_sound()
                    music_silence_immediate()
                    mode="story"
                elif e.key==pygame.K_l:
                    play_ui_sound()
                    music_silence_immediate()
                    load()
                    mode="world"
                elif e.key == pygame.K_LEFTBRACKET:
                    player["opt_bgm_vol"] = max(0.0, float(player.get("opt_bgm_vol", 1.0)) - 0.1)
                    refresh_streaming_bgm_volume()
                elif e.key == pygame.K_RIGHTBRACKET:
                    player["opt_bgm_vol"] = min(1.0, float(player.get("opt_bgm_vol", 1.0)) + 0.1)
                    refresh_streaming_bgm_volume()
                elif e.key == pygame.K_F8:
                    player["opt_se_on"] = not player.get("opt_se_on", True)
                    apply_sound_effect_settings()

            elif mode=="story":
                node = story_nodes.get(story_current_id, {})
                choices = node.get("choices", [])
                if pygame.K_1 <= e.key <= pygame.K_3:
                    i = e.key - pygame.K_1
                    if i < len(choices):
                        play_ui_sound()
                        choice = choices[i]
                        apply_story_effect(choice.get("effect", ""))
                        nxt = choice.get("next")
                        if nxt == "__ENDING__":
                            mode = "ending"
                        elif nxt and nxt in story_nodes:
                            story_current_id = nxt
                        else:
                            mode = "world"
                            if pending_bond_check:
                                pending_bond_check = False
                                try_start_bond_crisis()
                elif e.key == pygame.K_ESCAPE:
                    if isinstance(story_current_id, str) and story_current_id.startswith("post_boss"):
                        play_ui_sound()
                        mode = "world"
                        if pending_bond_check:
                            pending_bond_check = False
                            try_start_bond_crisis()
                    else:
                        mode = "title"

            elif mode=="world":
                # 自由移動はキー押下中の連続入力で処理する（KEYDOWN では移動キーは無視）
                if e.key in (
                    pygame.K_w,
                    pygame.K_s,
                    pygame.K_a,
                    pygame.K_d,
                    pygame.K_UP,
                    pygame.K_DOWN,
                    pygame.K_LEFT,
                    pygame.K_RIGHT,
                ):
                    pass
                elif e.key == pygame.K_t and FLOOR_EXTRA.get("fog"):
                    play_ui_sound()
                    player["torch_turns"] = 48
                    battle_log = "松明を掲げた。霧の奥がまだ見える…（歩くほど消費）"
                elif e.key==pygame.K_F5: save()
                elif e.key==pygame.K_i:
                    mode="inventory"
                    inv = player["inventory"]
                    if inventory_selected >= len(inv) and inv:
                        inventory_selected = len(inv) - 1
                elif e.key==pygame.K_o: player["weapon"]="鉄の剣"
                elif e.key==pygame.K_k: player["armor"]="鉄甲冑" if "鉄甲冑" in armors else "鉄の鎧"
                elif e.key==pygame.K_p: mode="party"
                elif e.key == pygame.K_b:
                    mode = "build_menu"
                elif e.key == pygame.K_j:
                    play_ui_sound()
                    mode = "codex"
                elif e.key == pygame.K_TAB:
                    play_ui_sound()
                    player["_map_legend_short"] = not player.get("_map_legend_short", False)
                    battle_log = "凡例メモ（右）を切替。色分けは右上ミニマップ参照"
                elif e.key == pygame.K_LEFTBRACKET:
                    player["opt_bgm_vol"] = max(0.0, float(player.get("opt_bgm_vol", 1.0)) - 0.1)
                    battle_log = f"BGM音量 {int(player['opt_bgm_vol'] * 100)}%"
                    refresh_streaming_bgm_volume()
                elif e.key == pygame.K_RIGHTBRACKET:
                    player["opt_bgm_vol"] = min(1.0, float(player.get("opt_bgm_vol", 1.0)) + 0.1)
                    battle_log = f"BGM音量 {int(player['opt_bgm_vol'] * 100)}%"
                    refresh_streaming_bgm_volume()
                elif e.key == pygame.K_F8:
                    player["opt_se_on"] = not player.get("opt_se_on", True)
                    apply_sound_effect_settings()
                    battle_log = "効果音 OFF" if not player["opt_se_on"] else "効果音 ON"

            elif mode == "build_menu":
                if pygame.K_1 <= e.key <= pygame.K_4:
                    battle_log = spend_skill_point(e.key - pygame.K_1)
                elif e.key == pygame.K_5:
                    play_ui_sound()
                    cycle_player_seal()
                    st = player.get("seal")
                    battle_log = f"刻印: {'なし' if st is None else st}"
                elif e.key == pygame.K_6:
                    play_ui_sound()
                    cycle_difficulty()
                    dtxt = {"easy": "易", "normal": "ふつう", "hard": "きつめ"}.get(tactics_difficulty(), "ふつう")
                    battle_log = f"難易を「{dtxt}」にした"
                elif e.key == pygame.K_ESCAPE:
                    mode = "world"

            elif mode == "codex":
                if e.key == pygame.K_ESCAPE:
                    play_ui_sound()
                    mode = "world"

            elif mode == "companion_crisis":
                if e.key in (pygame.K_1, pygame.K_2):
                    bond_crisis_apply_choice(e.key - pygame.K_1)
                elif e.key == pygame.K_ESCAPE:
                    bond_crisis_apply_choice(0)

            elif mode=="party":
                if pygame.K_0 <= e.key <= pygame.K_9:
                    swap_party(e.key-pygame.K_0)
                elif e.key==pygame.K_ESCAPE:
                    mode="world"

            elif mode=="inventory":
                inv = player["inventory"]
                if e.key == pygame.K_UP:
                    inventory_selected = max(0, inventory_selected - 1)
                elif e.key == pygame.K_DOWN:
                    inventory_selected = min(max(0, len(inv) - 1), inventory_selected + 1)
                elif pygame.K_1 <= e.key <= pygame.K_9:
                    idx = e.key - pygame.K_1
                    if idx < len(inv):
                        inventory_selected = idx
                elif e.key == pygame.K_e:
                    battle_log = equip_from_inventory(inventory_selected)
                elif e.key == pygame.K_u:
                    battle_log = inventory_use_consumable(inventory_selected)
                elif e.key == pygame.K_s:
                    battle_log = inventory_sell_selected(inventory_selected)
                elif e.key == pygame.K_x:
                    battle_log = inventory_discard(inventory_selected)
                elif e.key == pygame.K_n:
                    battle_log = inventory_swap_next(inventory_selected)
                elif e.key==pygame.K_ESCAPE:
                    mode="world"

            elif mode=="town":
                kf = f"town_ethics_{floor_number}"
                if town_mode == "ethics":
                    if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        play_ui_sound()
                        opt = TOWN_ETHICS_OPTIONS[e.key - pygame.K_1]
                        personality_apply(opt["deltas"])
                        player["story_flags"][kf] = True
                        town_mode = "hub"
                        town_npc_id = -1
                        town_npc_line = 0
                        battle_log = "町での選択が心に刻まれた。"
                    elif e.key == pygame.K_ESCAPE:
                        town_mode = "hub"
                elif town_mode == "npc_choice":
                    if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        play_ui_sound()
                        town_apply_npc_choice(town_npc_id, e.key - pygame.K_1)
                    elif e.key == pygame.K_ESCAPE:
                        town_mode = "hub"
                        town_npc_id = -1
                        town_npc_line = 0
                elif town_mode == "npc":
                    if e.key == pygame.K_c:
                        scr = TOWN_NPC_SCRIPTS[town_npc_id]
                        lines = scr["lines"]
                        if town_npc_line < len(lines) - 1:
                            town_npc_line += 1
                        elif scr.get("choices"):
                            town_mode = "npc_choice"
                        else:
                            town_mode = "hub"
                            town_npc_id = -1
                            town_npc_line = 0
                    elif e.key == pygame.K_ESCAPE:
                        town_mode = "hub"
                        town_npc_id = -1
                        town_npc_line = 0
                elif town_mode == "hub":
                    if pygame.K_1 <= e.key <= pygame.K_4:
                        ni = e.key - pygame.K_1
                        if ni < len(TOWN_NPC_SCRIPTS):
                            play_ui_sound()
                            town_npc_id = ni
                            town_npc_line = 0
                            town_mode = "npc"
                    elif e.key == pygame.K_e and not player.get("story_flags", {}).get(kf):
                        play_ui_sound()
                        town_mode = "ethics"
                    elif e.key == pygame.K_s:
                        play_ui_sound()
                        shop_scroll = 0
                        mode = "shop"
                    elif e.key == pygame.K_ESCAPE:
                        mode = "world"

            elif mode=="shop":
                cat_keys = shop_catalog()
                mx_s = max(0, len(cat_keys) - SHOP_PAGE)
                if e.key == pygame.K_UP:
                    shop_scroll = max(0, shop_scroll - 1)
                elif e.key == pygame.K_DOWN:
                    shop_scroll = min(mx_s, shop_scroll + 1)
                elif e.key == pygame.K_PAGEUP:
                    shop_scroll = max(0, shop_scroll - SHOP_PAGE)
                elif e.key == pygame.K_PAGEDOWN:
                    shop_scroll = min(mx_s, shop_scroll + SHOP_PAGE)
                elif pygame.K_1 <= e.key <= pygame.K_9:
                    i = e.key - pygame.K_1
                    sc = min(shop_scroll, mx_s)
                    idx = sc + i
                    if idx < len(cat_keys):
                        if cat_keys[idx].get("type") == "consumable":
                            battle_log = buy_shop_item(idx)
                        else:
                            selected_shop_item_index = idx
                            mode = "shop_choice"
                elif e.key == pygame.K_ESCAPE:
                    town_mode = "hub"
                    mode = "town"

            elif mode=="shop_choice":
                if e.key == pygame.K_i:
                    battle_log = handle_shop_purchase_choice(selected_shop_item_index, equip_now=False)
                    mode = "shop"
                elif e.key == pygame.K_e:
                    battle_log = handle_shop_purchase_choice(selected_shop_item_index, equip_now=True)
                    mode = "shop"
                elif e.key == pygame.K_f:
                    battle_log = shop_steal_selected(selected_shop_item_index)
                elif e.key == pygame.K_ESCAPE:
                    selected_shop_item_index = -1
                    mode = "shop"

            elif mode=="battle":
                if boss_intro_timer > 0:
                    pass
                elif e.key == pygame.K_LEFTBRACKET:
                    player["opt_bgm_vol"] = max(0.0, float(player.get("opt_bgm_vol", 1.0)) - 0.1)
                    battle_log = f"BGM音量 {int(player['opt_bgm_vol'] * 100)}%"
                    refresh_streaming_bgm_volume()
                elif e.key == pygame.K_RIGHTBRACKET:
                    player["opt_bgm_vol"] = min(1.0, float(player.get("opt_bgm_vol", 1.0)) + 0.1)
                    battle_log = f"BGM音量 {int(player['opt_bgm_vol'] * 100)}%"
                    refresh_streaming_bgm_volume()
                elif e.key == pygame.K_F8:
                    player["opt_se_on"] = not player.get("opt_se_on", True)
                    apply_sound_effect_settings()
                    battle_log = "効果音 OFF" if not player["opt_se_on"] else "効果音 ON"
                elif spell_menu_target is not None:
                    spells_list = (
                        player["skills"][:9]
                        if spell_menu_target == "hero"
                        else player["party"][spell_menu_target].get("skills", [])[:9]
                    )
                    nsp = len(spells_list)
                    if e.key == pygame.K_ESCAPE:
                        spell_menu_target = None
                    elif e.key == pygame.K_UP and nsp:
                        spell_menu_cursor = (spell_menu_cursor - 1) % nsp
                    elif e.key == pygame.K_DOWN and nsp:
                        spell_menu_cursor = (spell_menu_cursor + 1) % nsp
                    elif pygame.K_1 <= e.key <= pygame.K_9:
                        i = e.key - pygame.K_1
                        if i < nsp:
                            play_ui_sound()
                            spell_menu_cursor = i
                            if spell_menu_target == "hero":
                                battle_pending["hero"] = {"t": "spell", "name": spells_list[i]}
                            else:
                                battle_pending[spell_menu_target] = {"t": "spell", "name": spells_list[i]}
                            spell_menu_target = None
                elif e.key == pygame.K_t:
                    cur = player.get("party_battle_mode", "manual")
                    player["party_battle_mode"] = "auto" if cur == "manual" else "manual"
                    if player["party_battle_mode"] == "auto":
                        for k in battle_plan_units:
                            if k != "hero":
                                battle_pending[k] = suggest_ally_command(k)
                    else:
                        for k in list(battle_pending.keys()):
                            if k != "hero":
                                del battle_pending[k]
                elif e.key == pygame.K_LEFT:
                    if player.get("party_battle_mode") != "auto" and battle_plan_units:
                        battle_plan_focus = (battle_plan_focus - 1) % len(battle_plan_units)
                elif e.key == pygame.K_RIGHT:
                    if player.get("party_battle_mode") != "auto" and battle_plan_units:
                        battle_plan_focus = (battle_plan_focus + 1) % len(battle_plan_units)
                elif e.key in (pygame.K_q, pygame.K_e):
                    if len(living_enemy_indices()) > 1:
                        cycle_battle_enemy_target(-1 if e.key == pygame.K_q else 1)
                        play_ui_sound()
                elif e.key == pygame.K_RETURN:
                    play_ui_sound()
                    execute_party_round()
                elif e.key == pygame.K_1:
                    fk = plan_focused_key()
                    if fk == "hero":
                        battle_pending["hero"] = {"t": "atk"}
                    else:
                        battle_pending[fk] = {"t": "atk"}
                elif e.key == pygame.K_2:
                    spell_menu_target = plan_focused_key()
                    spell_menu_cursor = 0
                elif e.key == pygame.K_3:
                    fk = plan_focused_key()
                    if fk == "hero":
                        battle_pending["hero"] = {"t": "def"}
                    else:
                        battle_pending[fk] = {"t": "def"}
                elif e.key == pygame.K_4:
                    if plan_focused_key() == "hero":
                        battle_pending["hero"] = {"t": "flee"}

            elif mode=="floor_buff":
                if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    apply_floor_buff_choice(e.key - pygame.K_1)

            elif mode=="stairs_confirm":
                if e.key == pygame.K_RETURN:
                    try_move_next_floor()
                elif e.key == pygame.K_ESCAPE:
                    pending_floor_move = False
                    mode = "world"

            elif mode=="event_choice":
                if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    if e.key == pygame.K_1:
                        player["atk"] += 8
                        player["max_hp"] = max(40, player["max_hp"] - 20)
                        player["hp"] = min(player["hp"], player["max_hp"])
                        player["traits"].append("暴走因子")
                        personality_apply({"greed": 2, "morality": -3, "bravery": 1, "cunning": 2})
                    elif e.key == pygame.K_2:
                        player["max_hp"] += 40
                        player["hp"] += 40
                        player["traits"].append("聖印守護")
                        personality_apply({"morality": 3, "compassion": 2, "honor": 2, "greed": -1})
                    else:
                        player["max_mp"] += 30
                        player["mp"] += 30
                        player["traits"].append("深智契約")
                        personality_apply({"cunning": 2, "compassion": -1, "bravery": -1})
                    player["story_flags"][f"event_{pending_event}"] = True
                    pending_event = None
                    mode = "world"

            elif mode=="ending":
                if e.key == pygame.K_ESCAPE:
                    mode = "title"

    if mode not in ("title", "ending"):
        try:
            player["play_time_sec"] = float(player.get("play_time_sec", 0.0)) + clock.get_time() / 1000.0
        except (TypeError, ValueError):
            player["play_time_sec"] = 0.0
        now = pygame.time.get_ticks()
        if now - _last_periodic_autosave_ms >= AUTOSAVE_INTERVAL_MS:
            save(show_toast=False)
            _last_periodic_autosave_ms = now

    # ワールドモード中は毎フレーム自由移動を更新（キー押下中の連続歩行）
    if mode == "world":
        world_continuous_update()

    sync_music_to_mode()
    draw()

pygame.quit()
