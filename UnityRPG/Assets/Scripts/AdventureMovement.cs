using System;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        Vector2 pointerDirection;
        const float BodyRadius = .21f;
        public void MoveFree(Vector2 displacement)
        {
            if (state == null || state.mode != "world" || Modal || EffectsBusy || displacement == Vector2.zero) return;
            int steps = Math.Max(1, Mathf.CeilToInt(displacement.magnitude / .12f));
            displacement /= steps;
            for (int i = 0; i < steps && state.mode == "world"; i++)
            {
                Vector2 before = new Vector2(state.px, state.py);
                if (CanStand(state.px + displacement.x, state.py)) state.px += displacement.x;
                if (CanStand(state.px, state.py + displacement.y)) state.py += displacement.y;
                float traveled = Vector2.Distance(before, new Vector2(state.px, state.py));
                if (traveled <= 0) continue; Tutorial("move");
                AdvanceWalk(before, new Vector2(state.px, state.py));
                state.x = Mathf.FloorToInt(state.px); state.y = Mathf.FloorToInt(state.py); state.Reveal();
                state.encounterDistance += traveled;
                int cell = state.y * AdventureState.Width + state.x, tile = state.Current.tiles[cell];
                if (tile == 3) CollectChest(cell);
                if (tile == 8 && !state.Current.bossDefeated) { BeginBattle(cell, true); break; }
                // Safe landmarks never spawn an encounter; only actual walking counts.
                if (tile == 0 && state.encounterDistance >= state.nextEncounterDistance)
                { state.encounterCount++; BeginBattle(cell, false); break; }
            }
        }
        bool CanStand(float x, float y)
        {
            int w = AdventureState.Width, h = AdventureState.Height;
            for (int yy = Mathf.FloorToInt(y - BodyRadius); yy <= Mathf.FloorToInt(y + BodyRadius); yy++)
                for (int xx = Mathf.FloorToInt(x - BodyRadius); xx <= Mathf.FloorToInt(x + BodyRadius); xx++)
                {
                    if (xx < 0 || xx >= w || yy < 0 || yy >= h) return false;
                    int index = yy * w + xx, tile = state.Current.tiles[index];
                    if (tile == 1) return false;
                    if (tile == 6) { state.Current.tiles[index] = 0; Message("扉を開けた。"); }
                }
            return true;
        }
        int NearbyObject()
        {
            int best = -1; float distance = 1.2f;
            for (int y = Math.Max(0, state.y - 1); y <= Math.Min(AdventureState.Height - 1, state.y + 1); y++)
                for (int x = Math.Max(0, state.x - 1); x <= Math.Min(AdventureState.Width - 1, state.x + 1); x++)
                {
                    int cell = y * AdventureState.Width + x, tile = state.Current.tiles[cell];
                    if (tile < 3 || tile == 9 || (tile == 7 && state.Current.conversationDone)) continue;
                    float d = Vector2.Distance(new Vector2(state.px, state.py), new Vector2(x + .5f, y + .5f));
                    if (d < distance) { best = cell; distance = d; }
                }
            return best;
        }
        void CollectChest(int cell)
        {
            if (cell < 0 || cell >= state.Current.tiles.Length || state.Current.tiles[cell] != 3) return;
            int gold = 25 + state.floor * 3; state.gold += gold; state.Current.tiles[cell] = 0;
            state.chestsOpened++; state.goldEarned += gold;
            int item = new System.Random(unchecked(state.seed + state.floor * 31 + cell)).Next(state.floor < 10 ? 2 : 3);
            bool full = state.items[item] >= 99; if (!full) state.items[item]++;
            string reward = ItemNames[item] + (full ? "（所持数が上限）" : " ×1"); Message(reward);
            PickupFeedback(cell, gold, reward); state.encounterDistance = Mathf.Min(state.encounterDistance, state.nextEncounterDistance - 3);
            Message("宝箱から " + gold + "G を手に入れた。"); React("chest");
        }
        void Interact()
        {
            int cell = NearbyObject(); if (cell < 0) return;
            int tile = state.Current.tiles[cell];
            if (tile >= 10) StartSideEvent(cell);
            else if (tile == 3) CollectChest(cell);
            else if (tile == 6) { state.Current.tiles[cell] = 0; Message("扉を開けた。"); }
            else if (tile == 4) { state.mode = "town"; Message("補給地点。休憩と会話ができる。"); }
            else if (tile == 7) ExploreConversation();
            else if (tile == 8) BeginBattle(cell, true);
            else if (tile == 5)
            {
                if (state.floor % 10 == 0 && !state.Current.bossDefeated) { Message("守護者を倒すと階段が開く。赤い印を探そう。"); return; }
                if (state.floor % 10 == 0 && !state.flags.Contains("seen:post_boss_" + state.floor)) { BossConversation(); return; }
                if (state.floor == 100) { state.mode = "clear"; AutoSave(); return; }
                state.NextFloor(); React("floor"); Message(state.floor + "階へ。入口と階段は毎階変わる。" ); AutoSave();
                ShowMoment(state.floor + "階 / " + Theme(), "新しい道を探索しよう", true);
            }
        }
        void Escape()
        {
            if (state.bossBattle) return;
            if (state.rewardBattle && state.battleCell >= 0) state.Current.tiles[state.battleCell] = 11;
            state.combo = 0; state.rewardBattle = false; state.mode = "world"; state.ResetEncounter();
            state.personality[0] = Math.Max(-100, state.personality[0] - 2);
            Message("敵を振り切った。しばらくは安全に歩ける。");
        }
        string InteractionHint()
        {
            int cell = NearbyObject(); if (cell < 0) return "Shiftでダッシュ / 敵の気配に注意";
            int tile = state.Current.tiles[cell];
            return "E: " + (tile == 13 ? LandmarkNames[(state.floor - 1) / 10] + "を調べる" : tile == 10 ? "記憶の灯りを調べる" : tile == 11 ? "封印の宝箱を調べる" : tile == 12 ? "旅人を助ける" : tile == 3 ? "宝箱を開ける" : tile == 4 ? "休憩する" : tile == 5 ? "次の階へ" : tile == 6 ? "扉を開ける" : tile == 7 ? "仲間と話す" : "守護者に挑む");
        }
    }
}






