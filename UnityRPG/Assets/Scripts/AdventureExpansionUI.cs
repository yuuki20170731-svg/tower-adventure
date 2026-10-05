using System;
using System.Linq;
using System.IO;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        static readonly string[] ChapterPlaces = { "忘れられた遺跡", "手紙の森", "衛兵の回廊", "歌の庭", "記憶の研究所", "星守の砦", "声の氷水路", "灯りの機関", "竜門の庭", "星の深淵" };
        static readonly Color[] ChapterColors = {
            new Color(.40f,.36f,.26f), new Color(.17f,.35f,.20f), new Color(.28f,.31f,.39f), new Color(.17f,.40f,.30f), new Color(.31f,.24f,.38f),
            new Color(.22f,.27f,.37f), new Color(.16f,.37f,.46f), new Color(.46f,.25f,.14f), new Color(.38f,.26f,.28f), new Color(.16f,.14f,.31f)
        };
        void DrawChapterDecor(float ox, float oy, float size)
        {
            int band = (state.floor - 1) / 10; Color accent = ChapterColors[band] * 1.7f; accent.a = .6f;
            for (int i = 0; i < state.Current.tiles.Length; i++)
            {
                if (!state.Current.explored[i] || state.Current.tiles[i] == 1 || (i + state.seed) % 4 != 0) continue;
                float x = ox + i % AdventureState.Width * size, y = oy + i / AdventureState.Width * size;
                if (band == 1 || band == 3) { Fill(new Rect(x + 5, y + 6, 8, 22), accent); Fill(new Rect(x + 10, y + 3, 17, 9), accent); Fill(new Rect(x + 3, y + 13, 14, 9), accent); }
                else if (band == 6) { Fill(new Rect(x + 2, y + 8, 42, 3), accent); Fill(new Rect(x + 12, y + 17, 38, 3), accent); Fill(new Rect(x + 3, y + 28, 40, 2), accent); }
                else if (band == 7) { Fill(new Rect(x + 7, y + 8, 4, 30), accent); Fill(new Rect(x + 7, y + 33, 31, 4), accent); Fill(new Rect(x + 33, y + 12, 4, 23), accent); }
                else if (band == 4 || band == 9) { Fill(new Rect(x + 7, y + 7, 31, 2), accent); Fill(new Rect(x + 7, y + 7, 2, 31), accent); Fill(new Rect(x + 37, y + 7, 2, 31), accent); Fill(new Rect(x + 7, y + 37, 31, 2), accent); Fill(new Rect(x + 20, y + 18, 7, 7), accent); }
                else if (band == 8) { Fill(new Rect(x + 5, y + 8, 16, 4), accent); Fill(new Rect(x + 17, y + 8, 4, 18), accent); Fill(new Rect(x + 17, y + 23, 18, 4), accent); }
                else { Fill(new Rect(x + 8, y + 12, 32, 3), accent); Fill(new Rect(x + 16, y + 27, 21, 2), accent); }
            }
        }
        void OpenBag(int tab = 0)
        { bagOpen = true; bagTab = tab; journalOpen = combosOpen = slotsOpen = false; pointerDirection = Vector2.zero; itemTarget = healTarget; }
        void DrawExpansionOverlay()
        {
            drawingExpansion = true;
            if (settingsOpen) DrawSettings();
            else if (slotsOpen) DrawSlots();
            else if (bagOpen) DrawBag();
            drawingExpansion = false;
        }
        void DrawSlots()
        {
            Panel(new Rect(210, 260, 1180, 636)); Text(240, 277, 900, 45, "冒険の保存 / 手動3枠＋自動保存", headingStyle);
            if (Action(new Rect(1160, 280, 200, 40), "閉じる [Esc]")) slotsOpen = false;
            for (int i = 0; i < 4; i++)
            {
                float y = 342 + i * 117; Panel(new Rect(239, y, 1121, 103), activeSlot == i);
                Text(255, y + 10, 140, 35, i == 0 ? "自動保存" : "スロット " + i, smallStyle);
                Text(402, y + 11, 618, 80, slotSummaries[i], smallStyle);
                if (Action(new Rect(1030, y + 14, 146, 36), "読み込む", slotAvailable[i])) { int previous = activeSlot; if (i > 0) activeSlot = i; LoadFrom(SlotPath(i)); if (slotsOpen) activeSlot = previous; else RememberSlot(i); }
                if (i > 0 && Action(new Rect(1187, y + 14, 157, 36), confirmSlot == i ? "上書き確定" : "ここに保存", state != null && state.mode != "over"))
                {
                    if ((File.Exists(SlotPath(i)) || File.Exists(SlotPath(i) + ".bak")) && confirmSlot != i) { confirmSlot = i; notice = "スロット " + i + " を上書きします。もう一度「上書き確定」を押してください。"; }
                    else { RememberSlot(i); Save(); RefreshSlots(); confirmSlot = 0; }
                }
                if (i > 0 && Action(new Rect(1030, y + 57, 314, 31), activeSlot == i ? "F5 / F9 の対象です" : "この枠をF5 / F9の対象に", true, activeSlot == i)) RememberSlot(i);
            }
        }
        void DrawBag()
        {
            Panel(new Rect(220, 270, 1160, 626)); Text(250, 286, 770, 45, "どうぐ・装備  /  " + state.gold + "G", headingStyle);
            if (Action(new Rect(1150, 287, 200, 40), "閉じる [Esc]")) bagOpen = false;
            string[] tabs = { "どうぐ", "装備", "店", "工房（51階～）" };
            for (int i = 0; i < tabs.Length; i++) if (Action(new Rect(250 + i * 280, 350, 264, 41), tabs[i], i < 2 || state.mode == "town", bagTab == i)) bagTab = i;
            if (bagTab == 3) { DrawWorkshop(); return; }
            if (bagTab < 2)
            {
                for (int i = 0; i < 5; i++) if (Action(new Rect(250 + i * 220, 414, 206, 41), i == 0 ? "勇者" : CompanionNames[i - 1], true, (bagTab == 0 ? itemTarget : bagActor) == i)) { if (bagTab == 0) itemTarget = i; else bagActor = i; }
            }
            if (bagTab == 0)
            {
                Text(250, 470, 1060, 40, state.mode == "battle" ? "選択中の仲間が使用。対象を選び、予約後に全員の行動を実行。" : "対象を選んで使用。戦闘不能の仲間も選べます。", smallStyle);
                string[] details = { "HP65または最大HPの35%回復（大きい方）＋毒解除", "MP25または最大MPの30%回復（大きい方）", "戦闘不能から最大HPの半分で蘇生" };
                for (int i = 0; i < 3; i++)
                {
                    int free = state.items[i] - (state.mode == "battle" ? ReservedItems(i, selected) : 0);
                    if (Action(new Rect(250, 525 + i * 100, 1100, 83), ItemNames[i] + "  所持 " + state.items[i] + (state.mode == "battle" ? " / 予約可能 " + free : "") + "\n" + details[i], free > 0 && ItemUseful(i, itemTarget) && (state.mode != "battle" || state.party[selected].hp > 0))) SelectItem(i);
                }
            }
            else if (bagTab == 1)
            {
                var a = state.party[bagActor]; Text(250, 472, 1100, 34, "攻撃 " + AttackStat(a) + " / 守り " + DefenseStat(a) + " / 魔導具で威力・回復上昇、消費MP軽減", smallStyle);
                for (int kind = 0; kind < 3; kind++)
                {
                    float y = 529 + kind * 104; int tier = GearTier(a, kind);
                    Text(250, y, 160, 42, GearNames[kind] + " Lv " + tier);
                    for (int t = 0; t <= 3; t++) if (Action(new Rect(430 + t * 225, y, 212, 59), t == 0 ? "外す" : "Lv " + t + " / 在庫 " + state.gearOwned[kind * 3 + t - 1], state.mode != "battle" && (t == 0 || tier == t || state.gearOwned[kind * 3 + t - 1] > 0), tier == t)) Equip(bagActor, kind, t);
                    for (int effect = 0; effect < 3; effect++) if (Action(new Rect(430 + effect * 295, y + 66, 280, 29), GearEffects[kind][effect], state.mode != "battle" && tier > 0, GearEffect(a, kind) == effect)) SetGearEffect(bagActor, kind, effect);
                }
            }
            else
            {
                for (int i = 0; i < 3; i++) if (Action(new Rect(250 + i * 370, 425, 350, 62), ItemNames[i] + " / " + ItemPrices[i] + "G", state.gold >= ItemPrices[i] && state.items[i] < 99)) Buy(i, 0);
                int stock = state.floor >= 51 ? 3 : state.floor >= 21 ? 2 : 1;
                Text(250, 510, 1100, 36, "装備は21階でLv2、51階でLv3が入荷。買った後は装備タブで装着。", smallStyle);
                for (int kind = 0; kind < 3; kind++) for (int tier = 1; tier <= 3; tier++)
                    if (Action(new Rect(250 + (tier - 1) * 370, 567 + kind * 93, 350, 75), GearNames[kind] + " Lv " + tier + " / " + GearPrices[tier - 1] + "G\n在庫 " + state.gearOwned[kind * 3 + tier - 1] + (tier > stock ? " / 未入荷" : ""), tier <= stock && state.gold >= GearPrices[tier - 1] && state.gearOwned[kind * 3 + tier - 1] < 99)) Buy(kind + 3, tier);
            }
        }
    }
}


