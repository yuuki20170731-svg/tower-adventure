# -*- coding: utf-8 -*-
"""assets/audio に BGM・効果音を再取得する（OpenGameArt 等の公開URL・ライセンスは CREDITS.txt を参照）"""
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "audio")

URLS = {
    "battle.ogg": "https://opengameart.org/sites/default/files/fight.ogg",
    # 戦闘は「かっこいい」寄りを先に（オーケストラ）→ 速い戦闘曲へフォールバック
    "battle_epic.ogg": "https://opengameart.org/sites/default/files/CleytonRX%20-%20Battle%20RPG%20Theme%20Var_0.ogg",
    "battle_encounter.ogg": "https://opengameart.org/sites/default/files/fight.ogg",
    "world_adventure.ogg": "https://opengameart.org/sites/default/files/RPG_Exploration_The_Lost_City_.ogg",
    "title.ogg": "https://opengameart.org/sites/default/files/S31-Let%20the%20Games%20Begin.ogg",
    "victory.ogg": "https://opengameart.org/sites/default/files/victory_or_wedding_music_with_bells_c64_style_0.ogg",
    "ui_pack.zip": "https://opengameart.org/sites/default/files/UI%20pack%201.zip",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, url in URLS.items():
        dest = os.path.join(OUT, name)
        print(f"GET {url}")
        urllib.request.urlretrieve(url, dest)
        print(f"  -> {dest} ({os.path.getsize(dest)} bytes)")
    import zipfile
    zpath = os.path.join(OUT, "ui_pack.zip")
    with zipfile.ZipFile(zpath, "r") as zf:
        pick = None
        for n in zf.namelist():
            low = n.replace("\\", "/").lower()
            if low.endswith(".wav") and "menu" in low and "select" in low:
                pick = n
                break
        if not pick:
            raise SystemExit("ui_pack.zip 内に MENU*Select*.wav が見つかりません")
        with open(os.path.join(OUT, "ui_click.wav"), "wb") as f:
            f.write(zf.read(pick))
        print(f"extract {pick} -> ui_click.wav")
    os.remove(zpath)
    print("done. See assets/audio/CREDITS.txt for attribution.")


if __name__ == "__main__":
    main()
