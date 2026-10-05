using System;
using System.Linq;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        UnityEngine.Vector2 storyScroll;
        void BeginStory(string id, string returnMode = "world", bool exploration = false)
        {
            if (!story.Any(n => n.id == id)) return;
            state.storyId = id; state.storyReturnMode = returnMode; state.storyExploration = exploration;
            storyScroll = UnityEngine.Vector2.zero; state.mode = "story"; pointerDirection = UnityEngine.Vector2.zero;
        }
        void ExploreConversation(string returnMode = "world")
        {
            if (state.Current.conversationDone) return; Tutorial("talk");
            string id = "explore_" + state.floor;
            if (!story.Any(n => n.id == id)) id = "ready_for_adventure";
            BeginStory(id, returnMode, true);
        }
        void BossConversation()
        {
            string id = "post_boss_" + state.floor;
            if (!state.flags.Contains("seen:" + id)) BeginStory(id);
        }
        void FinishStory()
        {
            if (state.storyExploration) state.Current.conversationDone = true;
            state.storyExploration = false;
            state.mode = state.storyReturnMode == "town" ? "town" : "world";
            state.ResetEncounter();
            Message("仲間の言葉を胸に、冒険を続けよう。");
            FinishJourneyEvent(); AutoSave();
        }
        string EndingText()
        {
            string ending = state.flags.Contains("ending_restore") ? "五人は星の記憶を分け合い、世界へ返した。失われた名前をひとつずつ呼び直す旅が、今度は地上で始まる。" :
                state.flags.Contains("ending_guardian") ? "君は新たな星守となり、仲間を地上へ送り出した。四人は君を忘れず、毎年、塔の麓で再会を約束する。" :
                state.flags.Contains("ending_freedom") ? "塔の仕組みを止めた五人は、自分たちの手で夜を越える道を選んだ。世界は不完全なまま、誰の記憶も奪わずに朝を迎える。" :
                "仲間と歩いた記憶が、世界に新しい希望を残した。";
            int bonds = new[] { "bond_gald", "bond_mina", "bond_rina", "bond_theo" }.Count(state.flags.Contains);
            return ending + (bonds == 4 ? "\n\n四人は声を揃える。『次も、五人で行こう』" : bonds > 0 ? "\n\n旅で結んだ約束は、塔を出ても消えなかった。" : "");
        }
    }
}



