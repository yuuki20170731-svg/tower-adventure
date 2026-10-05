using System;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        int NormalRole(Actor e)
        {
            switch (e.image)
            {
                case "enemy_witch": return 1;
                case "enemy_knight": return 2;
                case "enemy_golem": case "enemy_orc": case "enemy_dragon": return 3;
                case "enemy_ghoul": return 4;
                default: return 0;
            }
        }
        string EnemyIntent(Actor e)
        {
            int role = NormalRole(e), phase = state.round % 3;
            return e.name + "：" + (role == 1 ? phase != 1 && state.enemies.Any(a => a.hp > 0 && a.hp < a.maxHp * .75f) ? "味方を回復" : phase != 1 ? "回復 / 傷がなければ術" : "術攻撃" : role == 2 && phase == 0 ? "盾でかばう / 魔法有効" : role == 3 && phase == 0 ? "溜め / 次は大技" : role == 3 && phase == 1 ? "大技 / 防御" : role == 4 && phase == 1 ? "毒 / 防御" : "通常攻撃");
        }
        bool IsRootBoss(Actor e) { return state.bossBattle && ReferenceEquals(e, state.enemies[0]); }
        void GivePoison(Actor a, int duration)
        {
            int turns = Math.Max(0, duration - (a.armorEffect == 1 ? a.armor : 0));
            a.poison = Math.Max(a.poison, turns); Message(a.name + (turns == 0 ? "は毒を防いだ。" : "に毒 " + turns + "ターン。"));
        }
        static readonly string[][] GearEffects = {
            new[] { "付与なし", "破甲", "吸魔" }, new[] { "付与なし", "毒耐性", "術耐性" }, new[] { "付与なし", "回復強化", "先手節約" }
        };
        static readonly string[][] GearDescriptions = {
            new[] { "標準の武器。", "通常攻撃で敵の守りを半分として計算。盾の軽減も弱める。", "この武器の通常攻撃で敵を倒すとMP＋3。" },
            new[] { "標準の防具。", "受ける毒を防具Lvだけ短縮。Lv3なら3ターンの毒を防ぐ。", "魔法系の敵・守護者の術による被ダメージを20%軽減。" },
            new[] { "標準の魔導具。", "回復魔法の回復量＋20%。", "戦闘の最初のターンだけ魔法の消費MP−2（最低1）。" }
        };
        int GearEffect(Actor a, int kind) { return kind == 0 ? a.weaponEffect : kind == 1 ? a.armorEffect : a.charmEffect; }
        void SetGearEffect(int actor, int kind, int effect)
        {
            if (state.mode == "battle" || actor < 0 || actor >= 5 || kind < 0 || kind > 2 || effect < 0 || effect > 2 || GearTier(state.party[actor], kind) == 0) return;
            var a = state.party[actor]; if (kind == 0) a.weaponEffect = effect; else if (kind == 1) a.armorEffect = effect; else a.charmEffect = effect;
            notice = GearNames[kind] + " / " + GearEffects[kind][effect] + "：" + GearDescriptions[kind][effect];
        }
        void RecordDialogue(string speaker, string text, string choice = "")
        {
            if (state.history.Count >= 1000) state.history.RemoveAt(0);
            state.history.Add(new DialogueRecord { floor = state.floor, speaker = speaker ?? "語り手", text = text ?? "", choice = choice ?? "" });
        }
        int textSpeed = 2, historyPage;
        string revealId; AdventureState revealState;
        float revealStarted; bool forceReveal;
        string RevealedStory(StoryNode node)
        {
            if (revealState != state || revealId != node.id) { revealState = state; revealId = node.id; revealStarted = Time.unscaledTime; forceReveal = false; }
            if (textSpeed == 0 || forceReveal || !Application.isPlaying) return node.text;
            int count = Math.Min(node.text.Length, (int)((Time.unscaledTime - revealStarted) * (textSpeed == 1 ? 20 : textSpeed == 2 ? 45 : 90)));
            if (count > 0 && count < node.text.Length && char.IsHighSurrogate(node.text[count - 1])) count--;
            return node.text.Substring(0, count);
        }
        void DrawDialogueHistory()
        {
            int pages = Math.Max(1, (state.history.Count + 19) / 20); historyPage = Mathf.Clamp(historyPage, 0, pages - 1);
            if (Action(new Rect(210, 410, 245, 40), "← 新しい20件", historyPage > 0)) { historyPage--; journalScroll = Vector2.zero; }
            Text(480, 415, 380, 34, (historyPage + 1) + " / " + pages + "ページ  全" + state.history.Count + "件", smallStyle);
            if (Action(new Rect(1070, 410, 300, 40), "古い20件 →", historyPage < pages - 1)) { historyPage++; journalScroll = Vector2.zero; }
            string text = string.Join("\n\n────────\n\n", state.history.AsEnumerable().Reverse().Skip(historyPage * 20).Take(20).Select(h => h.floor + "階 / " + h.speaker + "\n" + h.text + (h.choice.Length > 0 ? "\n選んだ返答：" + h.choice : "")));
            if (text.Length == 0) text = "会話と探索中の仲間の言葉を、ここに記録します。旧セーブでは追加後の会話から記録されます。";
            float height = Math.Max(380, bodyStyle.CalcHeight(new GUIContent(text), 1130));
            journalScroll = GUI.BeginScrollView(new Rect(210, 474, 1180, 390), journalScroll, new Rect(0, 0, 1130, height));
            GUI.Label(new Rect(0, 0, 1130, height), text, bodyStyle); GUI.EndScrollView();
        }
        string ProgressSummary()
        {
            string ending = state.flags.Contains("ending_restore") ? "星の記憶を世界へ返す" : state.flags.Contains("ending_guardian") ? "新たな星守になる" : state.flags.Contains("ending_freedom") ? "塔の仕組みを止める" : "冒険の途中";
            string text = "冒険の成果\n" + (state.mode == "clear" ? "100階踏破 / " : state.floor + "階 / ") + DifficultyNames[state.difficulty] + " / Lv " + state.level + "\n選んだ結末：" + ending;
            text += "\n守護者 " + state.floors.Count(f => f.bossDefeated) + " / 戦闘勝利 " + state.battlesWon + " / 行動ターン " + state.turnsTaken;
            text += "\n宝箱 " + state.chestsOpened + " / 道具使用 " + state.itemsUsed + " / 連携 " + state.combosUsed + " / 獲得金貨 " + state.goldEarned + "G";
            text += "\n解放した記憶 " + state.flags.Count(f => f.StartsWith("memory:")) + " / 救助 " + state.flags.Count(f => f.StartsWith("rescued:"));
            text += "\n工房：刃 " + state.workshop[0] + " / 守り " + state.workshop[1] + " / 灯り " + state.workshop[2];
            text += "\n会話履歴 " + state.history.Count + "件 / 記録開始 " + state.statsStartFloor + "階\n\n仲間との約束\n";
            for (int i = 0; i < 4; i++) text += CompanionNames[i] + "：" + (state.flags.Contains("path_" + QuestKeys[i] + "_personal") ? "個人の約束" : state.flags.Contains("path_" + QuestKeys[i] + "_team") ? "五人の約束" : QuestDone(i) ? "専用イベント達成" : "まだ約束を交わしていない") + "\n";
            return text;
        }
    }
}
