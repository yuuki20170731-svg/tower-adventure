"""
RPGゲーム用ドット絵アセット生成スクリプト
Pillow を使ってタイルベースのドット絵を作成
"""

from PIL import Image, ImageDraw
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE, "assets")
DATA_DIR = os.path.join(BASE, "data")

# タイルサイズ
TILE_SIZE = 40
ICON_SZ = 40

def create_grass():
    """草地タイル — 道の石が一目で分かるドット絵（エンカウント床）"""
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (78, 138, 58))
    draw = ImageDraw.Draw(img)
    # 草のムラ（4pxブロック）
    for gx in range(0, TILE_SIZE, 4):
        for gy in range(0, TILE_SIZE, 4):
            if (gx // 4 + gy // 4) % 2 == 0:
                draw.rectangle([gx, gy, gx + 3, gy + 3], fill=(92, 158, 68))
            else:
                draw.rectangle([gx, gy, gx + 3, gy + 3], fill=(64, 122, 48))
    # 中央の踏み跡（薄い土色の石畳風）
    stones = [(16, 18), (20, 22), (18, 26), (22, 16), (14, 22)]
    for sx, sy in stones:
        draw.rectangle([sx, sy, sx + 5, sy + 4], fill=(118, 112, 102))
        draw.rectangle([sx + 1, sy + 1, sx + 4, sy + 3], fill=(148, 142, 132))
    # 草のハイライト点
    for px, py in ((6, 8), (30, 10), (10, 32), (28, 30)):
        draw.rectangle([px, py, px + 1, py + 1], fill=(190, 235, 140))
    img.save(os.path.join(ASSETS_DIR, "grass.png"))
    print("✓ grass.png created")

def create_forest():
    """森タイル — 危険ゾーンと分かる濃い森＋隅に ! マーク"""
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (22, 42, 22))
    draw = ImageDraw.Draw(img)
    # 地面の苔
    for gx in range(0, TILE_SIZE, 5):
        for gy in range(0, TILE_SIZE, 5):
            c = (28, 52, 28) if (gx // 5 + gy // 5) % 2 else (18, 36, 18)
            draw.rectangle([gx, gy, gx + 4, gy + 4], fill=c)
    # 大きめの針葉樹シルエット（2本）
    for ox in (6, 22):
        draw.rectangle([ox + 5, 22, ox + 7, 36], fill=(48, 32, 20))
        draw.polygon(
            [(ox + 6, 6), (ox, 22), (ox + 12, 22)],
            fill=(16, 58, 22),
        )
        draw.polygon(
            [(ox + 6, 10), (ox + 2, 20), (ox + 10, 20)],
            fill=(28, 88, 36),
        )
    # 右下: 警告「!」（白地＋赤）
    draw.rectangle([28, 26, 37, 37], fill=(245, 245, 250))
    draw.rectangle([29, 27, 36, 36], outline=(40, 40, 50), width=1)
    draw.rectangle([32, 29, 33, 34], fill=(220, 40, 40))
    draw.rectangle([31, 35, 34, 36], fill=(220, 40, 40))
    img.save(os.path.join(ASSETS_DIR, "forest.png"))
    print("✓ forest.png created")

def create_town():
    """町タイル — 赤屋根の宿＋看板＋暖色の窓（町マスと一目で分かる）"""
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (120, 92, 62))
    draw = ImageDraw.Draw(img)
    # 前庭の土
    draw.rectangle([0, 28, TILE_SIZE - 1, TILE_SIZE - 1], fill=(140, 108, 72))
    # 建物壁
    draw.rectangle([5, 14, 34, 36], fill=(188, 152, 112))
    draw.rectangle([5, 14, 34, 36], outline=(96, 68, 44), width=1)
    # 赤い三角屋根（宿）
    draw.polygon([(3, 14), (36, 14), (20, 2)], fill=(198, 52, 42))
    draw.line([(3, 14), (36, 14)], fill=(120, 28, 24), width=1)
    # 看板柱＋板（「町」に近いシンプルな横長看板）
    draw.rectangle([8, 10, 10, 14], fill=(86, 58, 36))
    draw.rectangle([3, 6, 15, 11], fill=(92, 62, 38))
    draw.rectangle([4, 7, 14, 10], fill=(240, 220, 160))
    draw.rectangle([6, 8, 12, 9], fill=(42, 42, 48))
    # 窓（灯り）
    draw.rectangle([10, 22, 16, 28], fill=(255, 230, 120))
    draw.line([(13, 22), (13, 28)], fill=(180, 120, 40), width=1)
    draw.line([(10, 25), (16, 25)], fill=(180, 120, 40), width=1)
    # ドア＋提灯
    draw.rectangle([22, 24, 29, 36], fill=(72, 48, 32))
    draw.ellipse([25, 30, 27, 32], fill=(255, 200, 80))
    draw.ellipse([30, 20, 36, 26], fill=(255, 190, 70))
    draw.rectangle([32, 26, 33, 28], fill=(120, 80, 40))
    img.save(os.path.join(ASSETS_DIR, "town.png"))
    print("✓ town.png created")

def create_dungeon():
    """ダンジョン入口 - 石造り"""
    img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (90, 90, 90))
    draw = ImageDraw.Draw(img)
    
    # 石のテクスチャ
    for i in range(0, TILE_SIZE, 12):
        for j in range(0, TILE_SIZE, 12):
            draw.rectangle([i, j, i+11, j+11], outline=(60, 60, 60), width=1)
            if (i // 12 + j // 12) % 2 == 0:
                draw.rectangle([i+1, j+1, i+10, j+10], fill=(110, 110, 110))
    
    # 入口（暗い）
    draw.rectangle([10, 15, 30, 32], fill=(30, 30, 35))
    draw.polygon([(12, 15), (28, 15), (20, 8)], fill=(50, 50, 60))
    
    img.save(os.path.join(ASSETS_DIR, "dungeon.png"))
    print("✓ dungeon.png created")

def create_floor():
    """床タイル - グレー"""
    img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (130, 130, 130))
    draw = ImageDraw.Draw(img)
    
    # タイル模様
    for i in range(0, TILE_SIZE, 10):
        for j in range(0, TILE_SIZE, 10):
            if (i // 10 + j // 10) % 2 == 0:
                draw.rectangle([i, j, i+9, j+9], fill=(110, 110, 110))
            else:
                draw.rectangle([i, j, i+9, j+9], fill=(150, 150, 150))
            draw.rectangle([i, j, i+9, j+9], outline=(80, 80, 80), width=1)
    
    img.save(os.path.join(ASSETS_DIR, "floor.png"))
    print("✓ floor.png created")

def create_wall():
    """壁タイル - レンガ風"""
    img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (150, 90, 70))
    draw = ImageDraw.Draw(img)
    
    # レンガのパターン
    for row in range(0, TILE_SIZE, 10):
        offset = 5 if row % 20 == 10 else 0
        for col in range(0 - offset, TILE_SIZE, 20):
            draw.rectangle([col, row, col+18, row+8], fill=(140, 85, 65))
            draw.rectangle([col, row, col+18, row+8], outline=(100, 50, 40), width=1)
    
    # モルタル
    for i in range(0, TILE_SIZE, 10):
        draw.line([(0, i), (TILE_SIZE, i)], fill=(110, 65, 50), width=1)
    
    img.save(os.path.join(ASSETS_DIR, "wall.png"))
    print("✓ wall.png created")

def create_stairs():
    """階段タイル — 上昇段差＋大きな ↑（次の階へ分かりやすく）"""
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (52, 56, 72))
    draw = ImageDraw.Draw(img)
    # 石段（下から上へ狭くなる）
    for i in range(5):
        y0 = 30 - i * 5
        x0 = 4 + i * 3
        x1 = 35 - i * 3
        draw.rectangle([x0, y0, x1, y0 + 4], fill=(168, 172, 188))
        draw.line([(x0, y0 + 4), (x1, y0 + 4)], fill=(72, 76, 92), width=1)
    # 中央の矢印「↑」（黄）
    cx = 20
    draw.rectangle([cx - 1, 6, cx + 1, 18], fill=(255, 230, 60))
    draw.polygon([(cx, 4), (cx - 6, 12), (cx + 6, 12)], fill=(255, 240, 90))
    draw.polygon([(cx, 5), (cx - 4, 11), (cx + 4, 11)], fill=(255, 200, 40))
    # 枠でマスを強調
    draw.rectangle([1, 1, TILE_SIZE - 2, TILE_SIZE - 2], outline=(230, 220, 255), width=1)
    img.save(os.path.join(ASSETS_DIR, "stairs.png"))
    print("✓ stairs.png created")


def create_spring():
    """泉タイル — 水色の池＋波紋＋キラ（回復マス）"""
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (62, 110, 88))
    draw = ImageDraw.Draw(img)
    draw.rectangle([2, 2, 37, 37], fill=(72, 140, 118))
    draw.ellipse([5, 8, 34, 32], fill=(110, 210, 240))
    draw.ellipse([8, 11, 31, 29], fill=(130, 228, 255))
    draw.ellipse([11, 14, 28, 26], outline=(40, 140, 190), width=1)
    draw.ellipse([14, 17, 25, 23], outline=(255, 255, 255), width=1)
    # 十字キラキラ
    for ox, oy in ((16, 12), (24, 22), (12, 26)):
        draw.line([(ox - 2, oy), (ox + 2, oy)], fill=(255, 255, 255), width=1)
        draw.line([(ox, oy - 2), (ox, oy + 2)], fill=(255, 255, 255), width=1)
    img.save(os.path.join(ASSETS_DIR, "spring.png"))
    print("✓ spring.png created")


def create_title_adventure():
    """タイトル用ワイドドット絵 — 夜明けの道と城・旅立ちの背中"""
    gw, gh = 140, 48  # 論理グリッド（4px 単位で拡大）
    scale = 5
    w, h = gw * scale, gh * scale
    img = Image.new("RGB", (w, h), (18, 22, 48))
    draw = ImageDraw.Draw(img)

    def cell(gx, gy, rgb):
        x0, y0 = gx * scale, gy * scale
        draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=rgb)

    # 空のグラデ（上が明るい）
    for gy in range(gh):
        t = gy / max(1, gh - 1)
        r = int(28 + t * 90)
        g_ = int(36 + t * 70)
        b = int(72 + t * 100)
        for gx in range(gw):
            cell(gx, gy, (r, g_, b))
    # 太陽（左上）
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            if dx * dx + dy * dy <= 17:
                cell(10 + dx, 6 + dy, (255, 210, 120))
    # 遠くの山並み
    for gx in range(gw):
        hump = int(8 + 5 * math.sin(gx * 0.12))
        for gy in range(gh - 18, gh - 10):
            if gy > gh - 11 - hump:
                cell(gx, gy, (34, 42, 62))
    # 遠方の城（右）
    castle_x = 108
    for gy in range(22, 34):
        for gx in range(castle_x, castle_x + 22):
            if gy > 30 or (castle_x + 4 <= gx <= castle_x + 8) or (castle_x + 13 <= gx <= castle_x + 17):
                cell(gx, gy, (52, 58, 78))
    for gx in range(castle_x + 6, castle_x + 16):
        cell(gx, 21, (72, 78, 98))
    cell(castle_x + 10, 20, (200, 200, 220))
    # 道（中央下へ）
    path_c = (92, 86, 72)
    for gx in range(62, 78):
        for gy in range(30, 46):
            if abs(gx - 69) + (gy - 30) // 2 < 10:
                cell(gx, gy, path_c)
    # 主人公シルエット（後ろ姿・中央下）
    hx = 66
    for gy, row in enumerate(
        [
            "0001111000",
            "0012222100",
            "0122222210",
            "0122222210",
            "0013333100",
            "0033333300",
            "0034343300",
            "0044444400",
            "0044444400",
            "0444444440",
        ]
    ):
        y = 34 + gy
        for i, ch in enumerate(row):
            x = hx + i - 5
            if ch == "0":
                continue
            if ch == "1":
                c = (48, 42, 58)
            elif ch == "2":
                c = (245, 210, 185)
            elif ch == "3":
                c = (58, 92, 210)
            elif ch == "4":
                c = (42, 48, 72)
            else:
                c = (220, 200, 60)
            cell(x, y, c)
    # 剣の先が光る
    cell(hx + 8, 38, (255, 250, 200))
    cell(hx + 9, 37, (255, 250, 200))
    img.save(os.path.join(ASSETS_DIR, "title_adventure.png"))
    print("✓ title_adventure.png created")

def create_chest():
    """宝箱タイル - 黄金色"""
    img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (110, 160, 60))
    draw = ImageDraw.Draw(img)
    
    # 宝箱の本体
    draw.rectangle([8, 12, 32, 28], fill=(210, 180, 60))
    draw.rectangle([8, 12, 32, 28], outline=(160, 130, 40), width=2)
    
    # ふた
    draw.polygon([(8, 12), (32, 12), (30, 8), (10, 8)], fill=(230, 200, 80))
    
    # ハイライト
    draw.line([(10, 10), (30, 10)], fill=(255, 230, 120), width=1)
    draw.line([(10, 15), (30, 15)], fill=(180, 150, 50), width=1)
    
    # ロック
    draw.rectangle([(18, 20), (22, 24)], fill=(150, 130, 100))
    draw.ellipse([(19, 21), (21, 23)], fill=(100, 80, 50))
    
    img.save(os.path.join(ASSETS_DIR, "chest.png"))
    print("✓ chest.png created")

def create_player():
    """プレイヤーキャラ - 青い騎士"""
    img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 体（青の鎧）
    draw.rectangle([14, 14, 26, 26], fill=(60, 120, 255))
    
    # 兜（銀）
    draw.rectangle([12, 8, 28, 14], fill=(220, 220, 220))
    draw.polygon([(12, 8), (28, 8), (26, 4), (14, 4)], fill=(200, 200, 200))
    
    # 目
    draw.point((16, 11), fill=(255, 255, 255))
    draw.point((24, 11), fill=(255, 255, 255))
    draw.point((16, 12), fill=(0, 0, 0))
    draw.point((24, 12), fill=(0, 0, 0))
    
    # 剣
    draw.line([(30, 8), (34, 22)], fill=(220, 220, 220), width=3)
    draw.rectangle([(32, 22), (36, 26)], fill=(160, 100, 50))
    
    img.save(os.path.join(ASSETS_DIR, "player.png"))
    print("✓ player.png created")


def create_player_walk_frames():
    """プレイヤー歩行2フレーム"""
    for i, shift in enumerate([0, 2], start=1):
        img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([14, 14, 26, 26], fill=(60, 120, 255))
        draw.rectangle([12, 8, 28, 14], fill=(220, 220, 220))
        draw.polygon([(12, 8), (28, 8), (26, 4), (14, 4)], fill=(200, 200, 200))
        draw.point((16, 11), fill=(255, 255, 255))
        draw.point((24, 11), fill=(255, 255, 255))
        draw.point((16, 12), fill=(0, 0, 0))
        draw.point((24, 12), fill=(0, 0, 0))
        draw.rectangle([15, 26, 18, 34 - shift], fill=(40, 80, 200))
        draw.rectangle([22, 26, 25, 34 - (2 - shift)], fill=(40, 80, 200))
        draw.line([(30, 8), (34, 22)], fill=(220, 220, 220), width=3)
        draw.rectangle([(32, 22), (36, 26)], fill=(160, 100, 50))
        name = f"player_walk{i}.png"
        img.save(os.path.join(ASSETS_DIR, name))
        print(f"✓ {name} created")


def create_ui_panel():
    """UIパネル背景"""
    img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (42, 46, 72))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, TILE_SIZE - 1, TILE_SIZE - 1], outline=(200, 200, 220), width=2)
    for y in range(4, TILE_SIZE, 6):
        draw.line([(4, y), (TILE_SIZE - 5, y)], fill=(52, 56, 86), width=1)
    img.save(os.path.join(ASSETS_DIR, "ui_panel.png"))
    print("✓ ui_panel.png created")

def create_enemy():
    """敵キャラ - 赤いモンスター"""
    img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 身体（赤）
    draw.polygon([(20, 6), (14, 14), (12, 26), (28, 26), (26, 14)], fill=(255, 60, 60))
    
    # 目
    draw.ellipse([14, 12, 18, 16], fill=(255, 255, 255))
    draw.ellipse([22, 12, 26, 16], fill=(255, 255, 255))
    draw.point((16, 14), fill=(0, 0, 0))
    draw.point((24, 14), fill=(0, 0, 0))
    
    # 角
    draw.line([(16, 6), (12, 0)], fill=(180, 40, 40), width=2)
    draw.line([(24, 6), (28, 0)], fill=(180, 40, 40), width=2)
    
    # 口
    draw.polygon([(18, 22), (22, 22), (20, 25)], fill=(200, 30, 30))
    
    img.save(os.path.join(ASSETS_DIR, "enemy.png"))
    print("✓ enemy.png created")


def create_enemy_tiers():
    """階層別の敵スプライトを生成"""
    tiers = [
        ("enemy_1.png", (255, 80, 80), (170, 40, 40)),
        ("enemy_2.png", (235, 90, 40), (160, 70, 30)),
        ("enemy_3.png", (220, 70, 160), (120, 40, 100)),
        ("enemy_4.png", (120, 90, 255), (70, 50, 180)),
        ("enemy_5.png", (80, 220, 220), (30, 120, 120)),
    ]
    for name, body, horn in tiers:
        img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.polygon([(20, 5), (12, 14), (10, 27), (30, 27), (28, 14)], fill=body)
        draw.ellipse([12, 12, 18, 18], fill=(255, 255, 255))
        draw.ellipse([22, 12, 28, 18], fill=(255, 255, 255))
        draw.point((15, 15), fill=(0, 0, 0))
        draw.point((25, 15), fill=(0, 0, 0))
        draw.line([(14, 6), (9, 0)], fill=horn, width=2)
        draw.line([(26, 6), (31, 0)], fill=horn, width=2)
        draw.polygon([(16, 24), (24, 24), (20, 28)], fill=(220, 40, 40))
        img.save(os.path.join(ASSETS_DIR, name))
        print(f"✓ {name} created")

def create_boss():
    """ボスキャラ - 紫色の大型モンスター"""
    img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 大きな身体（紫）
    draw.ellipse([6, 6, 34, 34], fill=(170, 60, 220))
    
    # 腕
    draw.ellipse([2, 14, 8, 20], fill=(170, 60, 220))
    draw.ellipse([32, 14, 38, 20], fill=(170, 60, 220))
    
    # 目（大きめ）
    draw.ellipse([12, 12, 18, 20], fill=(255, 255, 0))
    draw.ellipse([22, 12, 28, 20], fill=(255, 255, 0))
    draw.point((15, 16), fill=(0, 0, 0))
    draw.point((25, 16), fill=(0, 0, 0))
    
    # 角（大きめ）
    draw.line([(14, 6), (8, 0)], fill=(120, 40, 170), width=3)
    draw.line([(26, 6), (32, 0)], fill=(120, 40, 170), width=3)
    
    # 牙
    draw.polygon([(18, 28), (22, 28), (20, 32)], fill=(255, 255, 255))
    
    img.save(os.path.join(ASSETS_DIR, "boss.png"))
    print("✓ boss.png created")


def create_boss_tiers():
    """10階層ごとボス用の強化スプライト"""
    bosses = [
        ("boss_1.png", (180, 70, 210), (120, 50, 150)),
        ("boss_2.png", (130, 60, 230), (80, 40, 170)),
        ("boss_3.png", (90, 40, 200), (50, 25, 140)),
        ("boss_final.png", (30, 20, 60), (220, 40, 80)),
    ]
    for name, body, horn in bosses:
        img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 36, 36], fill=body)
        draw.ellipse([0, 14, 9, 23], fill=body)
        draw.ellipse([31, 14, 40, 23], fill=body)
        draw.ellipse([11, 12, 19, 21], fill=(255, 255, 80))
        draw.ellipse([21, 12, 29, 21], fill=(255, 255, 80))
        draw.point((15, 16), fill=(0, 0, 0))
        draw.point((25, 16), fill=(0, 0, 0))
        draw.line([(13, 6), (7, 0)], fill=horn, width=3)
        draw.line([(27, 6), (33, 0)], fill=horn, width=3)
        draw.polygon([(16, 28), (24, 28), (20, 34)], fill=(255, 255, 255))
        draw.line([(10, 30), (30, 30)], fill=(200, 40, 70), width=2)
        img.save(os.path.join(ASSETS_DIR, name))
        print(f"✓ {name} created")

def create_ally_portraits():
    """仲間用バトル顔ドット（40px想定で描画後スケールはmain側）"""
    buddies = [
        ("ally_warrior.png", (180, 70, 70), (220, 220, 240)),
        ("ally_priest.png", (240, 240, 250), (180, 180, 220)),
        ("ally_archer.png", (120, 160, 90), (90, 70, 50)),
        ("ally_mage.png", (130, 90, 200), (230, 230, 255)),
    ]
    for fname, robe, skin in buddies:
        img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([10, 12, 30, 32], fill=skin)
        draw.rectangle([12, 22, 28, 34], fill=robe)
        draw.rectangle([14, 8, 26, 16], fill=(80, 70, 90))
        draw.rectangle([15, 10, 17, 12], fill=(40, 40, 60))
        draw.rectangle([23, 10, 25, 12], fill=(40, 40, 60))
        img.save(os.path.join(ASSETS_DIR, fname))
        print(f"[OK] {fname}")


def create_named_enemy_chibis():
    """敵名ごとにシルエットを分ける（ウルフ＝狼・バット＝翼など／main の ENEMY_FACE_FILES と対応）"""

    def save(draw_fn, fname):
        img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_fn(draw)
        img.save(os.path.join(ASSETS_DIR, fname))
        print(f"[OK] {fname}")

    def draw_slime(draw):
        draw.ellipse([6, 14, 34, 38], fill=(130, 230, 160))
        draw.ellipse([10, 6, 30, 24], fill=(100, 200, 130))
        draw.ellipse([14, 12, 18, 16], fill=(50, 80, 60))
        draw.ellipse([22, 12, 26, 16], fill=(50, 80, 60))
        draw.polygon([(20, 34), (14, 38), (26, 38)], fill=(90, 180, 120))

    def draw_goblin(draw):
        draw.ellipse([10, 18, 30, 38], fill=(100, 160, 90))
        draw.ellipse([12, 8, 28, 22], fill=(190, 210, 170))
        draw.polygon([(12, 16), (8, 6), (14, 14)], fill=(120, 140, 90))
        draw.polygon([(28, 16), (32, 6), (26, 14)], fill=(120, 140, 90))
        draw.point((16, 14), fill=(30, 40, 25))
        draw.point((24, 14), fill=(30, 40, 25))

    def draw_orc(draw):
        draw.ellipse([8, 18, 32, 38], fill=(120, 140, 100))
        draw.ellipse([10, 6, 30, 24], fill=(180, 140, 110))
        draw.rectangle([14, 26, 26, 36], fill=(90, 70, 55))
        draw.polygon([(18, 8), (22, 8), (20, 4)], fill=(180, 160, 140))
        draw.point((15, 14), fill=(40, 25, 20))
        draw.point((25, 14), fill=(40, 25, 20))

    def draw_wolf(draw):
        """狼：伸びた吻・耳・尾"""
        draw.ellipse([14, 22, 34, 38], fill=(120, 95, 75))
        draw.ellipse([18, 10, 34, 26], fill=(150, 115, 85))
        draw.polygon([(34, 18), (40, 22), (34, 26)], fill=(140, 110, 85))
        draw.polygon([(18, 8), (14, 2), (22, 12)], fill=(130, 100, 80))
        draw.polygon([(26, 8), (30, 2), (22, 12)], fill=(130, 100, 80))
        draw.line([(28, 34), (38, 36)], fill=(90, 70, 55), width=3)
        draw.point((24, 18), fill=(30, 25, 20))
        draw.point((30, 18), fill=(30, 25, 20))

    def draw_skeleton(draw):
        draw.rectangle([14, 22, 26, 38], fill=(220, 220, 215))
        draw.ellipse([12, 8, 28, 22], fill=(235, 235, 230))
        draw.line([(16, 26), (14, 34)], fill=(180, 180, 175), width=2)
        draw.line([(24, 26), (26, 34)], fill=(180, 180, 175), width=2)
        draw.ellipse([24, 14, 26, 16], fill=(40, 40, 45))
        draw.ellipse([14, 14, 16, 16], fill=(40, 40, 45))

    def draw_bat(draw):
        """コウモリ：翼・耳"""
        draw.polygon([(8, 22), (2, 28), (10, 26)], fill=(70, 55, 90))
        draw.polygon([(32, 22), (38, 28), (30, 26)], fill=(70, 55, 90))
        draw.ellipse([14, 14, 26, 28], fill=(60, 45, 80))
        draw.polygon([(18, 14), (14, 8), (22, 16)], fill=(90, 75, 110))
        draw.polygon([(22, 14), (26, 8), (18, 16)], fill=(90, 75, 110))
        draw.point((17, 22), fill=(255, 120, 140))
        draw.point((23, 22), fill=(255, 120, 140))

    def draw_golem(draw):
        draw.rectangle([8, 12, 32, 38], fill=(130, 135, 140))
        draw.rectangle([10, 8, 30, 18], fill=(110, 115, 120))
        draw.rectangle([12, 24, 18, 36], fill=(90, 95, 100))
        draw.rectangle([22, 24, 28, 36], fill=(90, 95, 100))
        draw.rectangle([18, 14, 22, 16], fill=(60, 65, 70))

    def draw_dragon(draw):
        draw.ellipse([12, 18, 32, 36], fill=(200, 70, 55))
        draw.polygon([(8, 24), (2, 18), (8, 16)], fill=(180, 55, 45))
        draw.polygon([(32, 20), (38, 14), (34, 28)], fill=(180, 55, 45))
        draw.polygon([(22, 8), (18, 2), (26, 10)], fill=(160, 50, 40))
        draw.line([(14, 34), (8, 38)], fill=(140, 45, 35), width=2)
        draw.point((20, 22), fill=(255, 240, 120))

    def draw_ghoul(draw):
        draw.ellipse([10, 18, 30, 38], fill=(130, 150, 110))
        draw.ellipse([12, 8, 28, 24], fill=(160, 175, 140))
        draw.rectangle([16, 22, 24, 28], fill=(90, 110, 70))
        draw.point((16, 14), fill=(80, 40, 40))
        draw.point((24, 14), fill=(80, 40, 40))

    def draw_knight(draw):
        draw.rectangle([12, 22, 28, 38], fill=(110, 125, 150))
        draw.rectangle([10, 10, 30, 24], fill=(150, 155, 170))
        draw.rectangle([8, 12, 14, 22], fill=(190, 190, 200))
        draw.rectangle([26, 12, 32, 22], fill=(190, 190, 200))
        draw.polygon([(12, 10), (20, 4), (28, 10)], fill=(180, 180, 190))

    def draw_witch(draw):
        draw.polygon([(8, 22), (32, 22), (20, 6)], fill=(90, 55, 120))
        draw.ellipse([12, 18, 28, 36], fill=(180, 140, 200))
        draw.point((17, 26), fill=(60, 40, 90))
        draw.point((23, 26), fill=(60, 40, 90))
        draw.line([(26, 14), (34, 8)], fill=(200, 200, 255), width=2)

    def draw_mimic(draw):
        draw.rectangle([8, 18, 32, 38], fill=(170, 130, 80))
        draw.rectangle([10, 20, 30, 36], fill=(150, 110, 60))
        draw.polygon([(10, 18), (20, 10), (30, 18)], fill=(190, 160, 110))
        draw.rectangle([16, 26, 24, 32], fill=(40, 30, 25))
        draw.line([(18, 28), (22, 30)], fill=(255, 90, 90), width=2)

    pairs = [
        ("enemy_slime.png", draw_slime),
        ("enemy_goblin.png", draw_goblin),
        ("enemy_orc.png", draw_orc),
        ("enemy_wolf.png", draw_wolf),
        ("enemy_skeleton.png", draw_skeleton),
        ("enemy_bat.png", draw_bat),
        ("enemy_golem.png", draw_golem),
        ("enemy_dragon.png", draw_dragon),
        ("enemy_ghoul.png", draw_ghoul),
        ("enemy_knight.png", draw_knight),
        ("enemy_witch.png", draw_witch),
        ("enemy_mimic.png", draw_mimic),
    ]
    for fname, fn in pairs:
        save(fn, fname)


def create_shop_item_icons():
    """ショップ・インベントリ用アイコン（item_icon_map.json のファイル名ごとにドット絵）"""
    path = os.path.join(DATA_DIR, "item_icon_map.json")
    if not os.path.exists(path):
        print("[SKIP] item_icon_map.json not found")
        return
    import json
    with open(path, encoding="utf-8") as f:
        mp = json.load(f)
    todo = sorted(set(mp.values()))

    def bottle(draw, liquid, cap=(140, 90, 70)):
        draw.rectangle([14, 8, 26, 30], fill=liquid)
        draw.rectangle([15, 4, 25, 10], fill=cap)
        draw.rectangle([15, 28, 25, 34], fill=(180, 170, 160))

    def save_icon(fname, draw_fn):
        img = Image.new("RGBA", (ICON_SZ, ICON_SZ), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_fn(draw)
        img.save(os.path.join(ASSETS_DIR, fname))
        print(f"[OK] {fname}")

    drawers = {}

    def draw_herb(dr):
        dr.polygon([(20, 32), (12, 38), (28, 38)], fill=(90, 140, 70))
        dr.line([(20, 34), (18, 12)], fill=(70, 120, 55), width=3)
        dr.ellipse([16, 8, 24, 16], fill=(120, 180, 90))

    def mk_potion(liquid):
        return lambda dr: bottle(dr, liquid)

    drawers["item_herb.png"] = draw_herb
    drawers["item_potion_red.png"] = mk_potion((220, 70, 70))
    drawers["item_potion_red_l.png"] = mk_potion((240, 90, 90))
    drawers["item_potion_gold.png"] = mk_potion((230, 190, 90))
    drawers["item_potion_blue.png"] = mk_potion((80, 130, 230))
    drawers["item_potion_blue_l.png"] = mk_potion((120, 170, 250))
    drawers["item_potion_rainbow.png"] = lambda dr: bottle(dr, (200, 120, 220), cap=(255, 220, 100))

    def draw_elixir(dr):
        bottle(dr, (100, 220, 160))
        dr.line([(18, 12), (22, 22)], fill=(255, 255, 200), width=2)

    def draw_drink(dr):
        dr.rectangle([12, 14, 28, 34], fill=(180, 220, 255))
        dr.rectangle([14, 10, 26, 16], fill=(255, 80, 80))
        dr.line([(16, 18), (24, 26)], fill=(255, 255, 255), width=1)

    def draw_party_herb(dr):
        for i, ox in enumerate((10, 18, 26)):
            dr.polygon([(ox, 30), (ox - 3, 36), (ox + 3, 36)], fill=(100 + i * 30, 160, 90))

    def draw_antidote(dr):
        dr.rectangle([14, 8, 26, 32], fill=(200, 230, 200))
        dr.line([(18, 14), (22, 22)], fill=(40, 160, 60), width=2)

    def draw_bread(dr):
        dr.rectangle([8, 14, 32, 32], fill=(210, 170, 110))
        dr.arc([10, 16, 30, 28], 200, 340, fill=(180, 130, 80), width=2)

    def draw_mushroom(dr):
        dr.ellipse([8, 12, 32, 28], fill=(220, 90, 90))
        dr.rectangle([17, 22, 23, 36], fill=(240, 230, 210))

    def draw_goddess(dr):
        bottle(dr, (230, 230, 255), cap=(255, 215, 120))
        dr.polygon([(20, 6), (16, 14), (24, 14)], fill=(255, 255, 200))

    def draw_jerky(dr):
        dr.rectangle([10, 16, 30, 30], fill=(140, 90, 60))
        dr.line([(12, 20), (28, 26)], fill=(100, 60, 40), width=1)

    def draw_egg(dr):
        dr.ellipse([12, 12, 28, 30], fill=(255, 250, 230))
        dr.ellipse([16, 18, 24, 24], fill=(255, 240, 200))

    def draw_honey(dr):
        dr.rectangle([12, 10, 28, 32], fill=(255, 200, 80))
        dr.rectangle([15, 6, 25, 12], fill=(220, 160, 50))

    def draw_sugar(dr):
        dr.rectangle([10, 14, 30, 34], fill=(250, 250, 255))
        for i in range(6):
            dr.point((12 + (i % 3) * 6, 18 + (i // 3) * 8), fill=(220, 220, 240))

    def draw_salve(dr):
        dr.ellipse([10, 12, 30, 32], fill=(255, 245, 230))
        dr.rectangle([16, 6, 24, 12], fill=(200, 180, 150))

    def sword(dr, blade, hilt):
        dr.polygon([(20, 4), (14, 28), (26, 28)], fill=blade)
        dr.rectangle([17, 24, 23, 38], fill=hilt)

    drawers["item_elixir.png"] = draw_elixir
    drawers["item_drink.png"] = draw_drink
    drawers["item_party_herb.png"] = draw_party_herb
    drawers["item_antidote.png"] = draw_antidote
    drawers["item_bread.png"] = draw_bread
    drawers["item_mushroom.png"] = draw_mushroom
    drawers["item_goddess.png"] = draw_goddess
    drawers["item_jerky.png"] = draw_jerky
    drawers["item_egg.png"] = draw_egg
    drawers["item_honey.png"] = draw_honey
    drawers["item_sugar.png"] = draw_sugar
    drawers["item_salve.png"] = draw_salve

    drawers["item_sword_wood.png"] = lambda dr: sword(dr, (160, 120, 80), (120, 80, 40))
    drawers["item_sword_iron.png"] = lambda dr: sword(dr, (200, 210, 220), (100, 100, 110))

    def fix_great(dr):
        sword(dr, (190, 190, 210), (80, 50, 40))
        dr.rectangle([11, 26, 29, 30], fill=(140, 140, 150))

    def fix_magic(dr):
        sword(dr, (180, 140, 255), (90, 60, 140))
        dr.line([(18, 8), (22, 20)], fill=(200, 255, 255), width=1)

    def fix_dragon(dr):
        sword(dr, (220, 60, 50), (90, 40, 30))
        dr.polygon([(8, 10), (12, 4), (14, 12)], fill=(255, 200, 80))

    drawers["item_sword_great.png"] = fix_great
    drawers["item_sword_magic.png"] = fix_magic
    drawers["item_sword_dragon.png"] = fix_dragon

    def armor(dr, body, trim):
        dr.polygon([(8, 14), (32, 14), (28, 36), (12, 36)], fill=body)
        dr.rectangle([14, 8, 26, 18], fill=trim)

    drawers["item_armor_cloth.png"] = lambda dr: armor(dr, (200, 190, 180), (160, 150, 140))
    drawers["item_armor_leather.png"] = lambda dr: armor(dr, (140, 100, 70), (100, 70, 45))
    drawers["item_armor_iron.png"] = lambda dr: armor(dr, (150, 155, 165), (110, 115, 125))
    drawers["item_armor_robe.png"] = lambda dr: armor(dr, (120, 90, 200), (90, 70, 160))
    drawers["item_armor_dragon.png"] = lambda dr: armor(dr, (90, 130, 90), (200, 180, 60))

    def draw_ring(dr):
        dr.ellipse([10, 12, 30, 30], outline=(220, 180, 60), width=3)
        dr.ellipse([14, 16, 26, 24], fill=(255, 220, 100))

    def draw_gem(dr):
        dr.polygon([(20, 8), (30, 18), (20, 34), (10, 18)], fill=(150, 120, 255))
        dr.line([(20, 12), (20, 28)], fill=(255, 255, 255), width=1)

    def draw_arrows(dr):
        for i in range(3):
            dr.line([(8 + i * 10, 30), (22 + i * 10, 10)], fill=(120, 80, 50), width=2)

    def draw_charm(dr):
        dr.ellipse([14, 10, 26, 22], fill=(255, 200, 210))
        dr.rectangle([18, 22, 22, 34], fill=(200, 180, 160))

    def draw_seed(dr):
        dr.ellipse([12, 14, 28, 30], fill=(160, 220, 100))
        dr.line([(20, 18), (20, 10)], fill=(100, 140, 60), width=2)

    def draw_whet(dr):
        dr.rectangle([8, 14, 32, 28], fill=(140, 140, 150))
        dr.line([(10, 18), (30, 24)], fill=(200, 200, 210), width=2)

    def draw_oil(dr):
        bottle(dr, (180, 160, 100))
        dr.arc([12, 18, 28, 32], 0, 180, fill=(80, 60, 40), width=2)

    def draw_ribbon(dr):
        dr.polygon([(8, 18), (20, 12), (32, 18), (20, 28)], fill=(255, 150, 180))

    def draw_salt(dr):
        dr.rectangle([10, 14, 30, 34], fill=(245, 245, 250))
        for px in range(14, 28, 4):
            dr.point((px, 22), fill=(200, 200, 210))

    def draw_sachet(dr):
        dr.rectangle([12, 12, 28, 32], fill=(230, 210, 190))
        dr.line([(14, 16), (26, 26)], fill=(180, 140, 120), width=1)

    def draw_quill(dr):
        dr.polygon([(30, 8), (12, 28), (16, 30)], fill=(250, 245, 220))
        dr.line([(28, 10), (14, 26)], fill=(80, 60, 40), width=2)

    def draw_bag(dr):
        dr.ellipse([10, 16, 30, 36], fill=(180, 140, 80))
        dr.arc([10, 12, 30, 24], 0, 180, fill=(160, 120, 60), width=2)

    drawers["item_ring_power.png"] = draw_ring
    drawers["item_gem_magic.png"] = draw_gem
    drawers["item_arrows.png"] = draw_arrows
    drawers["item_charm.png"] = draw_charm
    drawers["item_seed_exp.png"] = draw_seed
    drawers["item_whetstone.png"] = draw_whet
    drawers["item_oil.png"] = draw_oil
    drawers["item_ribbon.png"] = draw_ribbon
    drawers["item_salt.png"] = draw_salt
    drawers["item_sachet.png"] = draw_sachet
    drawers["item_quill.png"] = draw_quill
    drawers["item_bag_coin.png"] = draw_bag

    for fname in todo:
        fn = drawers.get(fname)
        if fn:
            save_icon(fname, fn)
        else:
            img = Image.new("RGBA", (ICON_SZ, ICON_SZ), (60, 60, 80, 255))
            ImageDraw.Draw(img).rectangle([4, 4, 36, 36], outline=(200, 200, 220), width=2)
            img.save(os.path.join(ASSETS_DIR, fname))
            print(f"[OK] {fname} (fallback)")


def create_boss_cutin_banner():
    """ボスカットイン用ワイド画像"""
    w, h = 440, 150
    img = Image.new('RGB', (w, h), (25, 15, 35))
    draw = ImageDraw.Draw(img)
    for i in range(0, w, 24):
        draw.line([(i, 0), (i + 40, h)], fill=(60, 35, 55), width=2)
    draw.rectangle([20, 20, w - 20, h - 20], outline=(220, 180, 80), width=4)
    draw.polygon([(w // 2 - 60, h // 2 + 20), (w // 2 + 60, h // 2 + 20), (w // 2, h // 2 - 40)], fill=(160, 40, 70))
    draw.ellipse([w // 2 - 50, h // 2 - 35, w // 2 - 30, h // 2 - 15], fill=(255, 230, 200))
    draw.ellipse([w // 2 + 30, h // 2 - 35, w // 2 + 50, h // 2 - 15], fill=(255, 230, 200))
    img.save(os.path.join(ASSETS_DIR, "boss_cutin.png"))
    print("[OK] boss_cutin.png")


def create_sword():
    """剣 - 銀の刃"""
    img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 刃（三角形）
    draw.polygon([(20, 4), (15, 26), (25, 26)], fill=(230, 230, 230))
    draw.polygon([(20, 4), (17, 26), (23, 26)], fill=(255, 255, 255))
    
    # エッジ
    draw.line([(20, 4), (20, 26)], fill=(180, 180, 180), width=1)
    
    # 柄
    draw.rectangle([17, 24, 23, 38], fill=(160, 90, 50))
    draw.rectangle([17, 24, 23, 38], outline=(120, 60, 30), width=1)
    
    # つば
    draw.rectangle([14, 23, 26, 25], fill=(255, 220, 100))
    draw.rectangle([14, 23, 26, 25], outline=(200, 170, 50), width=1)
    
    # ポメル
    draw.ellipse([(18, 36), (22, 40)], fill=(255, 220, 100))
    
    img.save(os.path.join(ASSETS_DIR, "sword.png"))
    print("✓ sword.png created")

def main():
    """すべてのアセットを生成"""
    print("[ASSET] RPG asset generation start...")
    print(f"保存先: {ASSETS_DIR}")
    print()
    
    create_grass()
    create_forest()
    create_town()
    create_dungeon()
    create_floor()
    create_wall()
    create_stairs()
    create_spring()
    create_title_adventure()
    create_chest()
    create_player()
    create_player_walk_frames()
    create_ui_panel()
    create_enemy()
    create_enemy_tiers()
    create_boss()
    create_boss_tiers()
    create_ally_portraits()
    create_named_enemy_chibis()
    create_shop_item_icons()
    create_boss_cutin_banner()
    create_sword()
    
    print()
    print("[OK] Asset generation completed.")
    print("[RUN] You can now run main.py")

if __name__ == "__main__":
    main()

