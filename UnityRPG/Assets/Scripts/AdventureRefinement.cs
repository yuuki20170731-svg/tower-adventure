using System;
using System.Collections.Generic;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        static readonly int[][] EncounterSpecies = {
            new[] { 0, 1, 2 }, new[] { 1, 2, 3 }, new[] { 3, 6, 1 }, new[] { 2, 5, 7 }, new[] { 4, 7, 5 },
            new[] { 6, 7, 4 }, new[] { 6, 7, 8 }, new[] { 4, 6, 7 }, new[] { 8, 9, 6 }, new[] { 9, 7, 8 }
        };
        static readonly string[] WorkshopNames = { "刃の鍛錬", "星紋の守り", "灯りの研磨" };
        static readonly string[] WorkshopDetails = { "五人の通常攻撃と攻撃連携を各段階＋2", "五人の守りを各段階＋2", "五人の魔法威力・回復量を各段階＋4" };
        static readonly int[] WorkshopPrices = { 1500, 3500, 6500 };
        static readonly string[] LandmarkNames = { "遺跡の星碑", "森の道標", "衛兵の誓約板", "歌を運ぶ泉", "研究所の記録盤", "砦の灯台", "氷水路の整流盤", "機関の調整弁", "竜門の契約石", "帰還の星座" };
        static readonly string[] LandmarkLines = {
            "崩れた星碑には、帰還する旅人の道順が残っていた。", "枝に刻まれた矢印が、迷い込んだ人を外へ導いている。リナは一つずつ確かめた。",
            "誓約板には『帰る人を守れ』とある。ガルドは盾を下ろし、その言葉を読み直した。", "泉の歌が、散り散りになった道を結んでいる。ミナは歌に合わせて指先を水へ浸した。",
            "記録盤には避難路と防護式が並ぶ。テオは、誰かの暮らしを守るための計算を選び直した。", "灯台の鏡は塔の内側も照らせる。遠くの扉に、小さな光が届いた。",
            "整流盤の氷を払うと、水路の地図が見えた。リナは『流れにも帰り道があるんだね』と笑う。", "調整弁の向こうから、呼吸のような音が聞こえる。テオは圧力を確かめ、止めずに守る方法を探した。",
            "契約石には、力を借りる条件が刻まれていた。ガルドは『誰のために使うかは、俺たちが決める』と答えた。", "星座は地上へ続く道を示している。ミナは四人の名前を呼び、同じ光を見ていることを確かめた。"
        };
        int WardPrice() { return 50 + state.floor * 2; }
        bool HealUseful(int target) { return target >= 0 && target < 5 && state.party[target].hp > 0 && (state.party[target].hp < state.party[target].maxHp || state.party[target].poison > 0); }
        IEnumerable<StoryNode> LandmarkStories()
        {
            for (int chapter = 0; chapter < 10; chapter++) yield return new StoryNode {
                id = "landmark_" + chapter, chapter = "章の寄り道 / " + LandmarkNames[chapter], speaker = "テオ", portrait = "ally_mage",
                text = LandmarkLines[chapter] + "\n\n「階段への道を読めるよ。金貨で装置を修復すれば、この階で五人を守る防護にもできる。必要な方を選ぼう」",
                choices = new[] {
                    new StoryChoice { text = "階段までの経路を地図に記録する（無料）", effect = "journey=survey" },
                    new StoryChoice { text = "防護を修復する（この階で五人の守り＋6）", effect = "journey=ward" },
                    new StoryChoice { text = "今は探索へ戻る" }
                }
            };
        }
        bool ImproveWorkshop(int kind)
        {
            if (state == null || state.mode != "town" || state.floor < 51 || kind < 0 || kind >= 3 || state.workshop[kind] >= 3) return false;
            int price = WorkshopPrices[state.workshop[kind]]; if (state.gold < price) return false;
            state.gold -= price; state.workshop[kind]++;
            notice = WorkshopNames[kind] + "を " + state.workshop[kind] + " 段階へ強化。" + WorkshopDetails[kind]; AutoSave(); return true;
        }
        void DrawWorkshop()
        {
            Text(250, 422, 1070, 65, "51階から利用できる工房。強化は五人に永続、各3段階。\n装備の付け替えでは失われません。買う前に効果と費用を確認できます。", smallStyle);
            for (int kind = 0; kind < 3; kind++)
            {
                int rank = state.workshop[kind];
                string price = rank == 3 ? "最大まで強化済み" : "次の強化 " + WorkshopPrices[rank] + "G";
                if (Action(new Rect(250, 521 + kind * 102, 1098, 86), WorkshopNames[kind] + " / " + rank + "段階 / " + price + "\n" + WorkshopDetails[kind], state.mode == "town" && state.floor >= 51 && rank < 3 && state.gold >= WorkshopPrices[rank])) ImproveWorkshop(kind);
            }
            Text(250, 843, 1080, 30, "攻撃・守り・魔法のどれを伸ばすかは自由。必要な分だけ購入できます。", smallStyle);
        }
    }
}
