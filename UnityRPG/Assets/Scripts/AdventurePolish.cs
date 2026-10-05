using System;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        static readonly string[] DifficultyNames = { "標準", "物語重視", "手ごたえ" };
        bool settingsOpen, reducedEffects;
        int newDifficulty;
        float musicVolume = .3f, soundVolume = .18f;
        string retryState;
        int EnemyHealth(int value) { return Math.Max(1, value * (state.difficulty == 1 ? 75 : state.difficulty == 2 ? 125 : 100) / 100); }
        int EnemyAttack(int value) { return Math.Max(1, value * (state.difficulty == 1 ? 65 : state.difficulty == 2 ? 120 : 100) / 100); }
        void InitPreferences()
        {
            musicVolume = Mathf.Clamp01(PlayerPrefs.GetFloat("AdventureMusic", .3f));
            soundVolume = Mathf.Clamp01(PlayerPrefs.GetFloat("AdventureSound", .18f));
            reducedEffects = PlayerPrefs.GetInt("AdventureReducedEffects", 0) == 1;
            textSpeed = Mathf.Clamp(PlayerPrefs.GetInt("AdventureTextSpeed", 2), 0, 3);
            ApplyPreferences();
        }
        void ApplyPreferences()
        { music.volume = musicVolume; effectAudio.volume = soundVolume; if (reducedEffects) { combatFx.Clear(); effectEnd = 0; } }
        void StorePreferences()
        {
            ApplyPreferences(); if (suppressSave) return;
            PlayerPrefs.SetFloat("AdventureMusic", musicVolume); PlayerPrefs.SetFloat("AdventureSound", soundVolume);
            PlayerPrefs.SetFloat("AdventureAmbient", ambientVolume); PlayerPrefs.SetInt("AdventureTextSpeed", textSpeed);
            PlayerPrefs.SetInt("AdventureReducedEffects", reducedEffects ? 1 : 0); PlayerPrefs.Save();
        }
        void RetryBattle()
        {
            if (state == null || state.mode != "over" || string.IsNullOrEmpty(retryState)) return;
            int chest = state.rewardBattle ? state.battleCell : -1;
            state = JsonUtility.FromJson<AdventureState>(retryState);
            if (chest >= 0 && chest < state.Current.tiles.Length) state.Current.tiles[chest] = 11;
            state.mode = "world"; state.enemies.Clear(); state.combo = 0; state.rewardBattle = false; state.Arrive(); ResetOrders();
            combatFx.Clear(); effectEnd = 0; selected = target = 0; log.Clear();
            notice = "戦闘前のHP・MP・所持品に戻して、この階の入口から再挑戦します。";
        }
        void OnApplicationQuit() { if (state != null && menu == "") AutoSave(); }
        void OnApplicationPause(bool paused) { if (paused && state != null && menu == "") AutoSave(); }
        void DrawSettings()
        {
            Panel(new Rect(250, 200, 1100, 700)); Text(286, 223, 850, 44, "設定 / 一時停止", headingStyle);
            if (Action(new Rect(1120, 224, 190, 40), "閉じる [P]")) settingsOpen = false;
            int current = state == null || menu == "title" ? newDifficulty : state.difficulty;
            Text(286, 291, 970, 36, "難易度（物語・報酬は共通。次の戦闘から反映）");
            bool canChange = state == null || menu == "title" || state.mode != "battle" && state.mode != "over" && state.mode != "clear";
            for (int i = 0; i < 3; i++) if (Action(new Rect(286 + i * 335, 345, 315, 50), DifficultyNames[i], canChange, current == i))
            { newDifficulty = i; if (state != null && menu != "title") state.difficulty = i; }
            Text(286, 412, 980, 60, current == 1 ? "物語重視：敵HP75%・攻撃65%。会話と探索をゆったり楽しむ。" : current == 2 ? "手ごたえ：敵HP125%・攻撃120%。装備・回復・防御を活かして挑む。" : "標準：短い通常戦と、予告を読むボス戦。初めての冒険におすすめ。", smallStyle);
            if (!canChange) Text(286, 476, 980, 28, state.mode == "clear" ? "クリアした冒険の難易度は記録として残します。新しい冒険はタイトルで選択。" : "戦闘を終えてから難易度を変更できます。", smallStyle);
            string[] audioLabels = { "音楽", "効果音", "環境音" }; float[] volumes = { musicVolume, soundVolume, ambientVolume };
            for (int row = 0; row < 3; row++)
            {
                Text(286, 505 + row * 47, 300, 36, audioLabels[row] + " " + Mathf.RoundToInt(volumes[row] * 100) + "%");
                for (int direction = -1; direction <= 1; direction += 2)
                    if (Action(new Rect(direction < 0 ? 640 : 800, 502 + row * 47, 140, 39), direction < 0 ? "− 10%" : "＋ 10%"))
                    { if (row == 0) musicVolume = Mathf.Clamp01(musicVolume + direction * .1f); else if (row == 1) soundVolume = Mathf.Clamp01(soundVolume + direction * .1f); else ambientVolume = Mathf.Clamp01(ambientVolume + direction * .1f); StorePreferences(); }
            }
            Text(286, 646, 950, 30, "会話の文字速度 / Spaceで全文を表示", smallStyle);
            string[] speeds = { "一括表示", "ゆっくり", "標準", "速い" };
            for (int i = 0; i < 4; i++) if (Action(new Rect(286 + i * 250, 680, 235, 38), speeds[i], true, textSpeed == i)) { textSpeed = i; StorePreferences(); }
            if (Action(new Rect(286, 737, 985, 46), reducedEffects ? "演出：簡略（揺れ・光・待ち時間なし）" : "演出：通常（揺れ・光・浮かぶ数字）")) { reducedEffects = !reducedEffects; StorePreferences(); }
            Text(286, 808, 980, 58, "Pで一時停止。F11で全画面。終了時は自動保存。Jで会話履歴と冒険の成果。\n全滅時は戦闘前の状態から再挑戦、または保存枠から再開できます。", smallStyle);
        }
    }
}

