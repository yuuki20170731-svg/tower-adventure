using System;
using System.IO;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        static readonly Color Ink = new Color(.035f, .065f, .12f, .95f);
        static readonly Color Paper = new Color(.96f, .95f, .89f);
        static readonly Color Muted = new Color(.68f, .76f, .82f);
        static readonly Color Gold = new Color(.95f, .78f, .38f);
        static readonly Color Teal = new Color(.25f, .8f, .68f);
        GUIStyle bodyStyle, smallStyle, mapStyle, cardStyle, headingStyle, titleStyle, buttonStyle, selectedStyle, compactStyle, compactSelectedStyle;
        Texture2D normalButton, hoverButton, pressedButton;
        static readonly string[] PartyArt = { "player", "ally_warrior", "ally_priest", "ally_archer", "ally_mage", "guide" };
        static readonly string[] EnemyArt = { "enemy_slime", "enemy_goblin", "enemy_wolf", "enemy_skeleton", "enemy_golem", "enemy_ghoul", "enemy_knight", "enemy_witch", "enemy_orc", "enemy_dragon", "boss", "boss_final" };
        static readonly string[] PropArt = { "chest", "door", "stairs", "town", "spring", "talk", "enemy", "boss_marker" };
        void Styles()
        {
            if (bodyStyle != null) return;
            bodyStyle = new GUIStyle(GUI.skin.label) { font = font, fontSize = 24, wordWrap = true, richText = false };
            bodyStyle.normal.textColor = Paper;
            smallStyle = new GUIStyle(bodyStyle) { fontSize = 20 }; smallStyle.normal.textColor = Muted;
            cardStyle = new GUIStyle(bodyStyle) { fontSize = 20 };
            mapStyle = new GUIStyle(smallStyle) { fontSize = 18 };
            headingStyle = new GUIStyle(bodyStyle) { fontSize = 30, fontStyle = FontStyle.Bold }; headingStyle.normal.textColor = Gold;
            titleStyle = new GUIStyle(headingStyle) { fontSize = 76 };
            normalButton = Swatch(new Color(.09f, .16f, .25f));
            hoverButton = Swatch(new Color(.17f, .28f, .37f));
            pressedButton = Swatch(new Color(.27f, .31f, .28f));
            buttonStyle = new GUIStyle(GUI.skin.button) { font = font, fontSize = 24, alignment = TextAnchor.MiddleLeft, wordWrap = true, padding = new RectOffset(18, 14, 8, 8), border = new RectOffset(0, 0, 0, 0) };
            buttonStyle.normal.background = normalButton; buttonStyle.hover.background = hoverButton; buttonStyle.active.background = pressedButton;
            buttonStyle.normal.textColor = Paper; buttonStyle.hover.textColor = Gold; buttonStyle.active.textColor = Gold;
            selectedStyle = new GUIStyle(buttonStyle); selectedStyle.normal.background = pressedButton; selectedStyle.normal.textColor = Gold;
            compactStyle = new GUIStyle(buttonStyle) { fontSize = 20, padding = new RectOffset(12, 8, 1, 1) };
            compactSelectedStyle = new GUIStyle(compactStyle); compactSelectedStyle.normal.background = pressedButton; compactSelectedStyle.normal.textColor = Gold;
        }
        static Texture2D Swatch(Color color)
        { var t = new Texture2D(1, 1); t.SetPixel(0, 0, color); t.Apply(); return t; }
        static void Fill(Rect rect, Color color)
        { var previous = GUI.color; GUI.color = color; GUI.DrawTexture(rect, Texture2D.whiteTexture); GUI.color = previous; }
        void Panel(Rect rect, bool active = false)
        {
            Fill(new Rect(rect.x + 3, rect.y + 5, rect.width, rect.height), new Color(0, 0, 0, .3f));
            Fill(rect, active ? Gold : new Color(.47f, .56f, .61f));
            Fill(new Rect(rect.x + 2, rect.y + 2, rect.width - 4, rect.height - 4), Ink);
            Fill(new Rect(rect.x + 6, rect.y + 6, rect.width - 12, 1), new Color(.8f, .83f, .8f, .3f));
        }
        void Text(float x, float y, float w, float h, string value, GUIStyle style = null)
        { GUI.Label(new Rect(x, y, w, h), value, style ?? bodyStyle); }
        bool Action(Rect rect, string text, bool enabled = true, bool active = false)
        {
            Fill(new Rect(rect.x - 1, rect.y - 1, rect.width + 2, rect.height + 2), active ? Gold : new Color(.42f, .51f, .58f, .8f));
            GUI.enabled = enabled && (!Modal && !EffectsBusy || drawingJourneyOverlay || drawingExpansion);
            bool clicked = GUI.Button(rect, text, rect.height <= 45 ? (active ? compactSelectedStyle : compactStyle) : (active ? selectedStyle : buttonStyle));
            GUI.enabled = !Modal && !EffectsBusy || drawingJourneyOverlay || drawingExpansion; return clicked;
        }
        void Bar(float x, float y, float w, int value, int maximum, Color color)
        {
            Fill(new Rect(x, y, w, 9), new Color(.14f, .2f, .27f));
            Fill(new Rect(x, y, w * DisplayBar(new Rect(x, y, w, 9), Mathf.Clamp01((float)value / Math.Max(1, maximum))), 9), color);
        }
        // Atlas cells are addressed directly: keep generated alpha and full resolution.
        void Art(string key, Rect rect, bool portrait = false)
        {
            int index = Array.IndexOf(PartyArt, key), columns = 3, rows = 2; string atlas = "party_hd";
            if (index < 0) { index = Array.IndexOf(EnemyArt, key); columns = 4; rows = 3; atlas = "enemies_hd"; }
            if (index < 0) { index = Array.IndexOf(PropArt, key); columns = 4; rows = 2; atlas = "props_hd"; }
            Texture2D texture;
            if (index >= 0 && textures.TryGetValue(atlas, out texture))
            {
                var uv = new Rect((index % columns) / (float)columns, 1 - (index / columns + 1) / (float)rows, 1f / columns, 1f / rows);
                if (portrait) { uv.x += uv.width * .34f; uv.width *= .42f; uv.y += uv.height * .57f; uv.height *= .43f; }
                float aspect = texture.width * uv.width / (texture.height * uv.height);
                float width = Mathf.Min(rect.width, rect.height * aspect), height = width / aspect;
                GUI.DrawTextureWithTexCoords(new Rect(rect.center.x - width / 2, rect.center.y - height / 2, width, height), texture, uv);
            }
            else if (textures.TryGetValue(key, out texture)) GUI.DrawTexture(rect, texture, ScaleMode.ScaleToFit);
        }
        void Backdrop()
        {
            Texture2D background;
            Fill(new Rect(0, 0, 1600, 1000), Ink);
            if (!DrawChapterBackground(new Rect(0, 0, 1600, 1000)) && textures.TryGetValue("landscape_hd", out background)) GUI.DrawTexture(new Rect(0, 0, 1600, 1000), background, ScaleMode.ScaleAndCrop);
            Fill(new Rect(0, 0, 1600, 1000), new Color(.015f, .045f, .09f, .20f));
        }
        void OnGUI()
        {
            float scale = Mathf.Min(Screen.width / 1600f, Screen.height / 1000f);
            GUI.matrix = Matrix4x4.TRS(new Vector3((Screen.width - 1600 * scale) / 2, (Screen.height - 1000 * scale) / 2, 0), Quaternion.identity, new Vector3(scale, scale, 1));
            Styles(); Backdrop();
            if (state == null || menu == "title") { DrawTitle(); GUI.enabled = true; DrawExpansionOverlay(); return; }
            Panel(new Rect(24, 16, 1552, 68));
            Text(48, 30, 640, 44, "星の塔   " + state.floor + "階 / 100    " + Theme(), headingStyle);
            if (Action(new Rect(1020, 30, 126, 42), "記録 J")) { journalOpen = !journalOpen; pointerDirection = Vector2.zero; combosOpen = false; }
            Text(704, 36, 170, 36, "Lv " + state.level + "     " + state.gold + " G");
            if (Action(new Rect(884, 30, 126, 42), "どうぐ B", state.mode != "over" && state.mode != "clear")) OpenBag();
            if (Action(new Rect(1156, 30, 126, 42), "保存枠")) OpenSlots();
            if (Action(new Rect(1292, 30, 126, 42), "設定 P")) settingsOpen = true;
            if (Action(new Rect(1428, 30, 124, 42), "タイトル")) { AutoSave(); menu = "title"; }
            GUI.enabled = !Modal && !EffectsBusy;
            DrawParty();
            bool modal = Modal || EffectsBusy; GUI.enabled = !modal;
            string mode = EffectsBusy && battleEffects ? "battle" : state.mode;
            if (mode == "world") DrawWorld();
            else if (mode == "battle") DrawBattle();
            else if (mode == "story") DrawStory();
            else if (mode == "town") DrawTown();
            else DrawEnding();
            GUI.enabled = true; DrawEffects(); DrawFeedback(); DrawJourneyOverlay(); DrawExpansionOverlay();
            Panel(new Rect(24, 916, 1552, 68));
            string hint = mode == "world" ? "WASD / 矢印: 移動    Shift: ダッシュ    E: 調べる    F5: 保存    F9: 復帰    B: 道具    J: 記録    P: 設定 / 停止" : mode == "battle" ? "← →: 仲間    Q / E: 敵    1: 攻撃    2: 防御    G: 全員防御    Enter: 実行    B: 道具    P: 設定 / 停止" : mode == "story" ? "Space: 全文表示    選択肢をクリック    F5: 会話途中も保存    F9: 復帰    P: 設定 / 停止" : "J: 冒険の記録    F9: 再開    P: 設定";
            Text(46, string.IsNullOrEmpty(notice) ? 936 : 922, 1508, 30, hint, smallStyle);
            if (!string.IsNullOrEmpty(notice)) Text(46, 952, 1508, 28, notice, smallStyle);
        }
        void DrawTitle()
        {
            Art("player", new Rect(895, 200, 600, 710));
            Panel(new Rect(80, 235, 725, 595));
            Text(125, 265, 610, 45, "仲間と紡ぐ、100階の冒険", smallStyle);
            Text(120, 325, 650, 110, "星 の 塔", titleStyle);
            Text(125, 452, 630, 76, "選んだ言葉が、仲間との物語を変える。\n一歩ずつ、星の向こうへ。");
            if (Action(new Rect(125, 557, 625, 62), "▶  新しい冒険", true, true)) NewGame();
            if (Action(new Rect(125, 636, 625, 62), "    セーブから再開", Enumerable.Range(0, 4).Any(i => File.Exists(SlotPath(i)) || File.Exists(SlotPath(i) + ".bak")))) OpenSlots();
            for (int i = 0; i < 3; i++) if (Action(new Rect(125 + i * 214, 711, 200, 42), DifficultyNames[i], true, newDifficulty == i)) newDifficulty = i;
            Text(125, 766, 640, 42, string.IsNullOrEmpty(notice) ? "P: 設定 / 移動: WASD / 操作は各画面で案内" : notice, smallStyle);
        }
        void DrawParty()
        {
            for (int i = 0; i < 5; i++)
            {
                var actor = state.party[i]; float x = 24 + i * 313;
                bool active = state.mode == "battle" && selected == i;
                Panel(new Rect(x, 102, 300, 144), active);
                Art(actor.image, new Rect(x + 8 + FxMotion(true, i), 111, 100, 119), true);
                Text(x + 112, 109, 180, 32, i == 0 ? "勇者" : CompanionNames[i - 1] + " / " + actor.name, cardStyle);
                Text(x + 112, 144, 180, 30, "HP " + actor.hp + " / " + actor.maxHp, smallStyle);
                Bar(x + 113, 175, 165, actor.hp, actor.maxHp, actor.hp < actor.maxHp / 4 ? new Color(.93f, .35f, .35f) : Teal);
                Text(x + 112, 187, 180, 30, "MP " + actor.mp + " / " + actor.maxMp, smallStyle);
                Bar(x + 113, 220, 165, actor.mp, actor.maxMp, new Color(.42f, .62f, .96f));
                if (state.mode == "battle" && GUI.Button(new Rect(x, 102, 300, 144), GUIContent.none, GUIStyle.none) && actor.hp > 0) { selected = i; skillScroll = Vector2.zero; }
                if (actor.hp <= 0) Text(x + 14, 207, 100, 28, "戦闘不能", smallStyle);
                else if (actor.poison > 0 || actor.slow > 0) Text(x + 12, 224, 100, 24, actor.poison > 0 ? "毒" : "攻撃低下", mapStyle);
            }
        }
        string Theme()
        {
            return ChapterPlaces[(state.floor - 1) / 10];
        }
        void DrawWorld()
        {
            Panel(new Rect(24, 264, 1028, 646));
            const float size = 54, ox = 78, oy = 289;
            var bounds = new Rect(ox, oy, AdventureState.Width * size, AdventureState.Height * size);
            Fill(bounds, ChapterColors[(state.floor - 1) / 10]);
            Texture2D floorArt = null;
            if (DrawChapterBackground(bounds, true) || textures.TryGetValue("landscape_hd", out floorArt))
            {
                if (!textures.ContainsKey("chapters_hd")) GUI.DrawTextureWithTexCoords(bounds, floorArt, new Rect(0, 0, 1, .30f));
                Fill(bounds, new Color(ChapterColors[(state.floor - 1) / 10].r, ChapterColors[(state.floor - 1) / 10].g, ChapterColors[(state.floor - 1) / 10].b, .74f));
            }
            // Join adjacent walls, avoiding the old checkerboard and per-cell outlines.
            for (int y = 0; y < AdventureState.Height; y++) for (int x = 0; x < AdventureState.Width; )
            {
                if (state.Current.tiles[y * AdventureState.Width + x] != 1) { x++; continue; }
                int end = x + 1;
                while (end < AdventureState.Width && state.Current.tiles[y * AdventureState.Width + end] == 1) end++;
                var wall = new Rect(ox + x * size, oy + y * size, (end - x) * size, size);
                Fill(new Rect(wall.x + 3, wall.y + 6, wall.width, wall.height), new Color(0, 0, 0, .3f));
                Color wallColor = ChapterColors[(state.floor - 1) / 10] * .55f; wallColor.a = 1; Fill(wall, wallColor);
                Fill(new Rect(wall.x, wall.y, wall.width, 7), new Color(.36f, .40f, .38f));
                x = end;
            }
            DrawChapterDecor(ox, oy, size);
            for (int i = 0; i < state.Current.tiles.Length; i++)
            {
                if (!state.Current.explored[i]) continue;
                int tile = state.Current.tiles[i]; float x = ox + (i % AdventureState.Width) * size, y = oy + (i / AdventureState.Width) * size;
                string key = tile == 13 ? "spring" : tile == 3 ? "chest" : tile == 4 ? "town" : tile == 5 ? "stairs" : tile == 6 ? "door" : tile == 7 && !state.Current.conversationDone ? "talk" : tile == 8 ? "boss_marker" : tile == 10 ? "spring" : tile == 11 ? "chest" : tile == 12 ? "talk" : null;
                if (key != null) Art(key, new Rect(x - 2, y - 7, size + 4, size + 10));
                if (tile >= 10) { Fill(new Rect(x + 2, y + 39, 50, 19), Ink); Text(x + 3, y + 35, 51, 28, tile == 13 ? "装置" : tile == 10 ? "記憶" : tile == 11 ? "封印" : "旅人", smallStyle); }
                if (tile == 9) { Art("spring", new Rect(x + 4, y + 3, size - 8, size - 8)); Text(x + 5, y + 35, 55, 25, "入口", smallStyle); }
            }
            for (int y = 0; y < AdventureState.Height; y++) for (int x = 0; x < AdventureState.Width; )
            {
                if (state.Current.explored[y * AdventureState.Width + x]) { x++; continue; }
                int end = x + 1;
                while (end < AdventureState.Width && !state.Current.explored[y * AdventureState.Width + end]) end++;
                Fill(new Rect(ox + x * size, oy + y * size, (end - x) * size, size), new Color(.025f, .045f, .065f)); x = end;
            }
            DrawWorldActors(ox, oy, size);
            Panel(new Rect(1070, 264, 506, 646));
            Text(1094, 282, 452, 40, "次の目的", headingStyle);
            string tutorial = TutorialText();
            bool stairsKnown = state.Current.explored[state.Current.stairs];
            Text(1094, 332, 452, 66, tutorial.Length > 0 ? tutorial : state.floor % 10 == 0 && !state.Current.bossDefeated ? "赤い印の守護者を倒して、\nこの階の階段を探そう。" : stairsKnown ? "見つけた階段へ向かおう。\n近くで E を押すと次の階へ。" : Objective());
            Text(1094, 410, 452, 32, InteractionHint());
            float ratio = state.encounterDistance / state.nextEncounterDistance;
            Text(1094, 457, 452, 30, "敵の気配: " + (ratio < .45f ? "静か" : ratio < .8f ? "少し近い" : "近い！"), smallStyle);
            Bar(1094, 494, 452, Mathf.RoundToInt(ratio * 100), 100, ratio >= .8f ? Gold : Teal);
            Text(1094, 518, 452, 36, "探索マップ", headingStyle);
            const float mini = 13;

            for (int i = 0; i < state.Current.tiles.Length; i++)
            {
                bool known = state.Current.explored[i]; int tile = state.Current.tiles[i];
                Color color = !known ? new Color(.025f, .045f, .07f) : tile == 1 ? new Color(.19f, .25f, .28f) : tile == 5 ? Gold : tile == 4 ? Teal : tile == 8 ? new Color(.9f, .3f, .3f) : tile == 13 ? new Color(.95f, .65f, .3f) : tile == 10 ? new Color(.3f, .9f, .95f) : tile == 11 ? new Color(.8f, .4f, .95f) : tile == 12 ? Paper : tile == 9 ? new Color(.43f, .65f, .96f) : new Color(.58f, .63f, .59f);
                Fill(new Rect(1094 + (i % AdventureState.Width) * mini, 566 + (i / AdventureState.Width) * mini, mini, mini), color);
            }
            Fill(new Rect(1094 + state.px * mini - 3, 566 + state.py * mini - 3, 6, 6), Paper);
            string[] mapLegend = { "白: 現在地", "青: 入口", "金: 階段", "緑: 補給", "赤: 守護者", "水色: 記憶", "紫: 封印", "橙: 装置" };
            for (int i = 0; i < mapLegend.Length; i++) Text(1340, 566 + i * 18, 208, 24, mapLegend[i], mapStyle);
            string latest = log.LastOrDefault(line => !CompanionNames.Any(name => line.StartsWith(name))) ?? "寄り道の手掛かりは記録帳で確認できます。";
            if (Time.unscaledTime >= chatterUntil) Text(1094, 726, 452, 61, latest.Length > 40 ? latest.Substring(0, 39) + "…" : latest, smallStyle);
            if (Time.unscaledTime < chatterUntil) { Panel(new Rect(1088, 717, 470, 69)); Art(chatterPortrait, new Rect(1093, 721, 64, 62), true); Text(1164, 720, 382, 64, chatterText, mapStyle); }
            if (Event.current.type == EventType.Repaint) pointerDirection = Vector2.zero;
            bool up = GUI.RepeatButton(new Rect(1280, 788, 78, 43), "↑", compactStyle);
            bool left = GUI.RepeatButton(new Rect(1185, 844, 78, 43), "←", compactStyle);
            bool down = GUI.RepeatButton(new Rect(1280, 844, 78, 43), "↓", compactStyle);
            bool right = GUI.RepeatButton(new Rect(1375, 844, 78, 43), "→", compactStyle);
            if (up || left || down || right) pointerDirection = new Vector2((right ? 1 : 0) - (left ? 1 : 0), (down ? 1 : 0) - (up ? 1 : 0));
        }
        void DrawBattle()
        {
            Panel(new Rect(24, 282, 1108, 374));
            Texture2D background; if (!DrawChapterBackground(new Rect(30, 288, 1096, 362)) && textures.TryGetValue("landscape_hd", out background)) GUI.DrawTexture(new Rect(30, 288, 1096, 362), background, ScaleMode.ScaleAndCrop);
            Panel(new Rect(44, 296, 1068, 52), state.bossBattle && state.round % 3 == 1);
            string warning = state.bossBattle ? BossIntent() : string.Join(" / ", state.enemies.Where(e => e.hp > 0).Select(EnemyIntent));
            Text(64, 299, 1020, 48, warning, smallStyle);
            DrawBattleActors();
            int count = state.enemies.Count;
            for (int i = 0; i < count; i++)
            {
                var enemy = state.enemies[i]; float width = 528f / count, x = 589 + width * i;
                float artWidth = Mathf.Min(250, width - 8);
                var actorRect = new Rect(x + (width - artWidth) / 2, 352, artWidth, 218); actorRect.x += FxMotion(false, i);
                if (enemy.hp > 0 || EffectsBusy) { var original = GUI.color; var finalHit = combatFx.LastOrDefault(f => !f.ally && f.index == i && f.text.StartsWith("−")); if (enemy.hp <= 0 && finalHit != null) GUI.color = new Color(original.r, original.g, original.b, Mathf.Clamp01(1 - (Time.unscaledTime - finalHit.start) / .65f)); LivingEnemyArt(enemy.image, actorRect, i); GUI.color = original; }
                else Text(actorRect.x + 75, 446, 130, 40, "撃破", smallStyle);
                float cardWidth = Mathf.Min(320, width - 20), cardX = x + (width - cardWidth) / 2;
                if (Action(new Rect(cardX, 575, cardWidth, 43), (target == i ? "▶ " : "") + (i + 1) + "  " + enemy.name, enemy.hp > 0, target == i)) target = i;
                Fill(new Rect(cardX, 617, cardWidth, 38), Ink);
                Text(cardX + 8, 619, cardWidth - 16, 28, "HP " + enemy.hp + " / " + enemy.maxHp + (enemy.poison > 0 ? "   毒" : ""), smallStyle);
                Bar(cardX, 648, cardWidth, enemy.hp, enemy.maxHp, new Color(.92f, .39f, .32f));
            }
            Panel(new Rect(1150, 282, 426, 374));
            Text(1174, 303, 378, 42, "戦いの記録", headingStyle);
            if (Action(new Rect(1434, 610, 118, 35), "連携技")) combosOpen = true;
            if (Action(new Rect(1174, 610, 120, 35), "全員攻撃")) QueueAllAttacks();
            if (Action(new Rect(1304, 610, 120, 35), "全員防御")) QueueAllGuards();
            if (Action(new Rect(1174, 562, 378, 35), "前の行動を予約 [R]", CanRepeat)) RepeatOrders();
            Text(1174, 358, 378, 194, string.Join("\n", log.Skip(Math.Max(0, log.Count - 4))), smallStyle);
            Panel(new Rect(24, 674, 296, 236));
            Text(44, 688, 250, 34, state.party[selected].name + " の行動", headingStyle);
            bool canAct = state.party[selected].hp > 0;
            if (Action(new Rect(44, 737, 256, 45), "1  こうげき", canAct)) Queue(1, null);
            if (Action(new Rect(44, 794, 256, 45), "2  ぼうぎょ", canAct)) Queue(2, null);
            if (Action(new Rect(44, 851, 256, 42), "にげる", !state.bossBattle)) { Escape(); return; }
            Panel(new Rect(338, 674, 686, 236));
            Text(358, 688, 640, 38, "じゅもん  /  消費MPと効果を確認", headingStyle);
            var available = skills.Where(k => AllowedSkill(state.party[selected], k)).ToArray();
            skillScroll = GUI.BeginScrollView(new Rect(358, 738, 646, 155), skillScroll, new Rect(0, 0, 618, Math.Max(150, available.Length * 88)));
            for (int i = 0; i < available.Length; i++)
            {
                var skill = available[i];
                int estimate = SpellPower(state.party[selected], skill);
                if (state.bossBattle && state.round % 3 == 2) estimate = estimate * 3 / 2;
                string detail = skill.heal > 0 ? "味方1人のHPを " + HealPower(state.party[selected], skill) + " 回復（蘇生不可）" : "敵1体 / ダメージ目安 " + estimate;
                if (skill.poison_chance > 0) detail += " / 毒 " + Mathf.RoundToInt(skill.poison_chance * 100) + "%（3回）";
                if (skill.paralyze_chance > 0) detail += " / 麻痺 " + Mathf.RoundToInt(skill.paralyze_chance * 100) + "%（1行動）";
                if (Action(new Rect(1, i * 88 + 1, 610, 80), skill.name + "   MP " + SkillCost(state.party[selected], skill) + "\n" + detail, canAct && state.party[selected].mp >= SkillCost(state.party[selected], skill))) Queue(skill.heal > 0 ? 4 : 3, skill);
            }
            if (available.Length == 0) Text(12, 24, 590, 88, "この仲間は攻撃と防御が得意です。\n魔法は勇者・僧侶・魔法使いが使えます。", smallStyle);
            GUI.EndScrollView();
            Panel(new Rect(1042, 674, 534, 236));
            int pending = state.party.Where((a, i) => a.hp > 0 && state.orders[i].action == 0).Count();
            Text(1064, 690, 490, 34, pending == 0 ? "全員の予約がそろいました" : "あと " + pending + "人の行動を選ぼう");
            if (Action(new Rect(1064, 735, 490, 52), "▶  予約を実行  [Enter]", pending == 0, pending == 0)) { Resolve(); return; }
            Text(1064, 796, 490, 28, "ヒールの対象（選んでから魔法を予約）", smallStyle);
            for (int i = 0; i < 5; i++) if (Action(new Rect(1064 + (i % 3) * 164, 830 + (i / 3) * 36, 156, 30), state.party[i].name, state.party[i].hp > 0, healTarget == i)) healTarget = i;
            // Reserved actions are shown over each card, separate from HP / MP.
            for (int i = 0; i < 5; i++)
            {
                float x = 24 + i * 313; Panel(new Rect(x, 248, 300, 29), state.orders[i].action != 0);
                Text(x + 10, 248, 280, 29, OrderText(i), smallStyle);
            }
        }
        void DrawStory()
        {
            var node = story.FirstOrDefault(n => n.id == state.storyId);
            if (node == null) return;
            Art(string.IsNullOrEmpty(node.portrait) ? "guide" : node.portrait, new Rect(55, 280, 410, 610));
            Panel(new Rect(486, 280, 1090, 266));
            Text(518, 298, 1000, 42, (string.IsNullOrEmpty(node.chapter) ? "" : node.chapter + "  /  ") + (string.IsNullOrEmpty(node.speaker) ? "旅人の言葉" : node.speaker), headingStyle);
            string visible = RevealedStory(node);
            float height = Mathf.Max(166, bodyStyle.CalcHeight(new GUIContent(visible), 990));
            storyScroll = GUI.BeginScrollView(new Rect(518, 350, 1030, 180), storyScroll, new Rect(0, 0, 990, height));
            GUI.Label(new Rect(0, 0, 990, height), visible, bodyStyle);
            GUI.EndScrollView();
            if (visible.Length < node.text.Length)
            { if (Action(new Rect(514, 571, 1034, 62), "全文を表示 [Space]")) forceReveal = true; return; }
            for (int i = 0; i < node.choices.Length; i++)
            {
                var choice = node.choices[i];
                bool affordable = !(choice.effect ?? "").Contains("journey=ward") || state.gold >= WardPrice();
                if ((choice.effect ?? "").Contains("journey=supply")) affordable = state.gold >= 30;
                if (Action(new Rect(514, 571 + i * 100, 1034, 82), "▶  " + choice.text + "\n" + ChoiceEffect(choice.effect), affordable)) { Choose(choice); break; }
            }
        }
        string ChoiceEffect(string effects)
        {
            string[] keys = { "bravery", "morality", "compassion", "honor", "greed", "cunning" };
            string[] names = Axes.Split(',');
            var labels = (effects ?? "").Split('|').Select(effect =>
            {
                for (int i = 0; i < keys.Length; i++) if (effect.StartsWith(keys[i])) return names[i] + " " + effect.Substring(keys[i].Length);
                if (effect.StartsWith("story_flag=bond_")) return "仲間との約束";
                if (effect == "journey=ward") return "必要 " + WardPrice() + "G / 所持 " + state.gold + "G / 階を離れるまで有効";
                if (effect == "journey=survey") return "無料 / 階段への経路を地図に記録";
                if (effect == "journey=supply") return "必要30G / 所持 " + state.gold + "G";
                if (effect.StartsWith("stat_type=")) return effect.EndsWith("attack") ? "攻撃に優れた勇者になる" : effect.EndsWith("defense") ? "守りに優れた勇者になる" : "魔法に優れた勇者になる";
                return "";
            }).Where(value => value.Length > 0);
            return string.Join("   ", labels);
        }
        void DrawTown()
        {
            Art("guide", new Rect(55, 280, 420, 610));
            Panel(new Rect(486, 280, 1090, 610));
            Art("town", new Rect(1300, 310, 220, 170));
            Text(524, 313, 730, 60, "旅人の休憩地点", headingStyle);
            Text(524, 401, 710, 114, "長い冒険には、ひと休みも必要です。\n無料で全員のHP・MPを回復します。\n戦闘不能の仲間も、ここで復帰できます。");
            if (Action(new Rect(524, 562, 1010, 68), "▶  休憩して全回復", true, true)) { RecoverParty(); React("rest"); Message("パーティーは全回復した。"); AutoSave(); notice = "全員のHP・MPを回復しました。"; }
            if (Action(new Rect(1320, 480, 212, 58), "店・装備")) OpenBag(2);
            if (Action(new Rect(524, 655, 1010, 68), "    仲間と話す", !state.Current.conversationDone)) { ExploreConversation("town"); }
            int quest = AvailableQuest();
            if (quest >= 0 && Action(new Rect(524, 748, 1010, 55), "    " + CompanionNames[quest] + "の手掛かりを相談する")) { state.journeyCell = -1; BeginStory("quest_" + QuestKeys[quest], "town"); }
            if (Action(new Rect(524, 818, 1010, 55), "    探索に戻る")) state.mode = "world";
        }
        void DrawEnding()
        {
            Panel(new Rect(300, 350, 1000, 440));
            Text(346, 390, 908, 70, state.mode == "clear" ? "塔を踏破した！" : "パーティーは倒れた…", headingStyle);
            string ending = state.mode == "clear" ? EndingText() : "保存した冒険から、もう一度歩き出そう。";
            float height = Mathf.Max(160, bodyStyle.CalcHeight(new GUIContent(ending), 880));
            storyScroll = GUI.BeginScrollView(new Rect(346, 489, 908, 170), storyScroll, new Rect(0, 0, 880, height)); GUI.Label(new Rect(0, 0, 880, height), ending, bodyStyle); GUI.EndScrollView();
            if (state.mode == "over" && Action(new Rect(346, 665, 908, 52), "戦闘前の状態で、この階の入口から再挑戦", !string.IsNullOrEmpty(retryState))) RetryBattle();
            if (Action(new Rect(346, state.mode == "over" ? 730 : 670, 908, 52), "保存枠から再開")) OpenSlots();
            if (state.mode == "clear" && Action(new Rect(346, 733, 908, 40), "冒険の成果と仲間の約束を見る")) { journalOpen = true; journalTab = 4; journalScroll = Vector2.zero; }
        }
    }
}




















