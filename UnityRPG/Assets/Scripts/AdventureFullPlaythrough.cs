#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        string fullDirectory;
        bool fullFailed, fullMidSaved;
        int fullLowest, fullBossTurns, fullNormalTurns, fullBosses, fullNormals, fullRests;
        readonly HashSet<string> fullRoleCaptures = new HashSet<string>();
        void FullFailure(string text)
        {
            fullFailed = true; File.WriteAllText(Path.Combine(fullDirectory, "failure.txt"), text);
            Debug.LogError("FULL_PLAYTHROUGH_FAILED: " + text); Application.Quit(1);
        }
        IEnumerator FullCapture(string name)
        {
            for (int i = 0; i < 8; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(fullDirectory, "Screens", name + ".png"));
            for (int i = 0; i < 8; i++) yield return null;
        }
        IEnumerator FullStory()
        {
            for (int page = 0; state.mode == "story" && page < 30; page++)
            {
                var node = story.First(n => n.id == state.storyId);
                // Alternate the personal/team promise routes; other dialogue chooses its first answer.
                int quest = Array.FindIndex(QuestKeys, k => node.id == "quest_" + k);
                Choose(node.choices[quest >= 0 ? quest % 2 : node.id == "side_traveler" ? 1 : 0]);
                yield return null;
            }
            if (state.mode == "story") FullFailure("Conversation loop: " + state.storyId);
        }
        void FullOrders()
        {
            target = state.enemies.FindIndex(e => e.hp > 0 && !IsRootBoss(e) && NormalRole(e) == 1);
            if (target < 0) target = state.enemies.FindIndex(e => e.hp > 0);
            QueueAllAttacks();
            bool danger = state.round % 3 == 1 && (state.bossBattle && state.enemies[0].hp > 0 || state.enemies.Any(e => e.hp > 0 && NormalRole(e) == 3));
            if (danger) { QueueAllGuards(); return; }
            int wounded = Enumerable.Range(0, 5).Where(p => state.party[p].hp > 0).OrderBy(p => (float)state.party[p].hp / state.party[p].maxHp).First();
            int dead = state.party.FindIndex(a => a.hp == 0);
            if (dead >= 0 && state.items[2] > 0)
            { selected = state.party.FindIndex(a => a.hp > 0); itemTarget = dead; SelectItem(2); return; }
            if (state.party.Count(a => a.hp > 0 && a.hp < a.maxHp * .7f) >= 2 && CanCombo(1)) QueueCombo(1);
            else if (CanCombo(2) && state.enemies.Count(e => e.hp > 0) > 1) QueueCombo(2);
            else if (CanCombo(0)) QueueCombo(0);
            var heal = skills.Where(k => k.heal > 0 && AllowedSkill(state.party[2], k) && state.party[2].mp >= SkillCost(state.party[2], k)).OrderByDescending(k => HealPower(state.party[2], k)).FirstOrDefault();
            if (heal != null && state.party[2].hp > 0 && state.party[wounded].hp < state.party[wounded].maxHp * .65f && !(state.combo > 0 && ComboActors(state.combo - 1).Contains(2)))
            { selected = 2; healTarget = wounded; Queue(4, heal); }
            if (state.party[wounded].hp < state.party[wounded].maxHp * .4f && state.orders[2].action != 4 && state.combo != 2 && state.items[0] > 0)
            { selected = 0; itemTarget = wounded; SelectItem(0); }
            bool useMagic = state.bossBattle && state.round % 3 == 0 && (state.floor == 30 || state.floor == 60) || !state.bossBattle && state.round % 3 == 0 && NormalRole(state.enemies[target]) == 2;
            if (useMagic && state.party[4].hp > 0 && !(state.combo > 0 && ComboActors(state.combo - 1).Contains(4)))
            {
                var attack = skills.Where(k => k.power > 0 && AllowedSkill(state.party[4], k) && state.party[4].mp >= SkillCost(state.party[4], k)).OrderByDescending(k => SpellPower(state.party[4], k)).FirstOrDefault();
                if (attack != null) { selected = 4; Queue(3, attack); }
            }
        }
        IEnumerator FullBattle()
        {
            bool boss = state.bossBattle; if (boss) fullBosses++; else fullNormals++;
            if (boss) yield return FullCapture("boss-" + state.floor);
            else
                foreach (var enemy in state.enemies.ToArray())
                    if (NormalRole(enemy) > 0 && fullRoleCaptures.Add(enemy.image)) yield return FullCapture("role-" + enemy.image);
            for (int turn = 0; state.mode == "battle" && turn < 80; turn++)
            {
                FullOrders();
                if (!fullMidSaved && state.floor >= 55 && state.combo > 0)
                {
                    string checkpoint = Path.Combine(fullDirectory, "checkpoint-battle.json");
                    int combo = state.combo, ready = state.comboReadyRound, round = state.round; int[] workshop = state.workshop.ToArray();
                    string orders = JsonUtility.ToJson(state); AdventureSave.Write(checkpoint, state); LoadFrom(checkpoint);
                    if (state.combo != combo || state.round != round || state.comboReadyRound != ready || !state.workshop.SequenceEqual(workshop) || JsonUtility.ToJson(state) != orders) { FullFailure("Mid-battle orders/workshop reload changed state"); yield break; }
                    fullMidSaved = true; Debug.Log("FULL_MID_BATTLE_RELOAD_PASSED: floor " + state.floor + ", combo=" + combo);
                }
                Resolve(); if (boss) fullBossTurns++; else fullNormalTurns++;
                fullLowest = Math.Min(fullLowest, (int)state.party.Min(a => a.hp * 100f / a.maxHp));
                yield return null;
            }
            if (state.mode == "battle" || state.mode == "over") { FullFailure("Battle did not clear at floor " + state.floor); yield break; }
            yield return FullStory();
        }
        void FullShop()
        {
            RecoverParty(); fullRests++;
            int tier = state.floor >= 51 ? 3 : state.floor >= 21 ? 2 : 1;
            for (int p = 0; p < 5; p++) for (int kind = 0; kind < 3; kind++)
            {
                if (GearTier(state.party[p], kind) < tier && Buy(kind + 3, tier)) Equip(p, kind, tier);
                SetGearEffect(p, kind, kind == 0 ? p == 4 || p == 0 ? 2 : 1 : kind == 1 ? state.floor < 61 ? 1 : 2 : p == 2 ? 1 : 2);
            }
            for (int kind = 0; kind < 3; kind++) while (state.items[kind] < (kind == 2 ? 2 : 4) && Buy(kind, 0)) { }
            for (int kind = 0; kind < 3; kind++) if (state.workshop[kind] < 3) ImproveWorkshop(kind);
            notice = "";
        }
        IEnumerator FullTravel(int destination)
        {
            if (destination < 0 || state.mode == "clear") yield break;
            var path = DungeonLayout.Path(state.Current, state.y * AdventureState.Width + state.x, destination);
            if (path.Count == 0) { FullFailure("No route to " + destination + " on " + state.floor); yield break; }
            foreach (int cell in path.Skip(1))
            {
                var goal = new Vector2(cell % AdventureState.Width + .5f, cell / AdventureState.Width + .5f);
                int frames = 0;
                while (Vector2.Distance(new Vector2(state.px, state.py), goal) > .005f && frames++ < 100)
                {
                    var delta = goal - new Vector2(state.px, state.py); MoveFree(delta.normalized * Mathf.Min(.6f, delta.magnitude));
                    if (state.mode == "battle") yield return FullBattle();
                    if (fullFailed || state.mode == "clear") yield break;
                    yield return null;
                }
                if (frames >= 100) { FullFailure("Movement blocked at " + state.floor + "/" + cell); yield break; }
                if (state.Current.tiles[cell] == 4)
                {
                    Interact(); if (state.mode != "town") { FullFailure("Rest interaction failed"); yield break; }
                    FullShop(); state.mode = "world";
                }
            }
        }
        IEnumerator FullVisit(int tile)
        {
            int cell = Array.IndexOf(state.Current.tiles, tile); if (cell < 0) yield break;
            if (tile == 7 && state.Current.conversationDone) yield break;
            yield return FullTravel(cell); if (fullFailed || state.mode == "clear") yield break;
            if (tile == 4 || tile == 3) yield break;
            Interact(); if (state.mode == "story") yield return FullStory();
            if (state.mode == "battle") yield return FullBattle();
        }
        IEnumerator FullPlaythrough(string directory)
        {
            fullDirectory = directory; Directory.CreateDirectory(directory); Directory.CreateDirectory(Path.Combine(directory, "Screens"));
            suppressSave = true; NewGame(); state = AdventureState.New(2027); reducedEffects = true; textSpeed = 0; ApplyPreferences();
            Application.targetFrameRate = 120; Screen.SetResolution(1200, 800, false);
            for (int i = 0; i < 20; i++) yield return null;
            yield return FullStory();
            var report = new StringBuilder("floor,battles,turns,level,minimum_sampled_hp_percent,gold,history_count\n");
            for (int floor = 1; floor <= 100; floor++)
            {
                int startBattles = state.battlesWon, startTurns = state.turnsTaken; fullLowest = 100;
                if (floor % 10 == 1) yield return FullCapture("chapter-" + ((floor - 1) / 10 + 1));
                yield return FullVisit(4); yield return FullVisit(7);
                if (floor % 10 == 3) yield return FullVisit(13);
                if (AvailableQuest() >= 0 || floor % 10 == 1) yield return FullVisit(10);
                if (floor % 20 == 4) yield return FullVisit(12);
                if (floor % 10 == 5) yield return FullVisit(3);
                // Risk/reward is optional; sample it once per chapter.
                if (floor % 10 == 6) yield return FullVisit(11);
                if (fullFailed) yield break;
                if (floor == 50)
                {
                    string checkpoint = Path.Combine(directory, "checkpoint-50.json"); AdventureSave.Write(checkpoint, state);
                    int history = state.history.Count, wins = state.battlesWon, turns = state.turnsTaken; LoadFrom(checkpoint);
                    if (state.floor != 50 || state.history.Count != history || state.battlesWon != wins || state.turnsTaken != turns) { FullFailure("Checkpoint reload failed"); yield break; }
                    Debug.Log("FULL_CHECKPOINT_RELOAD_PASSED: floor 50, history=" + history);
                }
                yield return FullTravel(state.Current.stairs); if (fullFailed) yield break;
                report.AppendLine(floor + "," + (state.battlesWon - startBattles) + "," + (state.turnsTaken - startTurns) + "," + state.level + "," + fullLowest + "," + state.gold + "," + state.history.Count);
                File.WriteAllText(Path.Combine(directory, "actual-100-floors.csv"), report.ToString());
                Debug.Log("FULL_FLOOR_PLAYED: " + floor + ", victories=" + state.battlesWon + ", turns=" + state.turnsTaken + ", Lv=" + state.level);
                if (state.mode == "clear") break;
                Interact(); if (state.mode == "story") { yield return FullStory(); if (state.mode != "clear") Interact(); }
                if (floor < 100 && state.floor != floor + 1) { FullFailure("Stairs failed at " + floor); yield break; }
            }
            if (state.mode != "clear" || state.floor != 100 || state.floors.Count(f => f.bossDefeated) != 10 || state.party.All(a => a.hp == 0) || Enumerable.Range(0, 4).Any(i => !QuestDone(i)))
            { FullFailure("Missing final clear, boss or companion promise"); yield break; }
            AdventureSave.Write(Path.Combine(directory, "clear-save.json"), state);
            string result = "Actual Windows development player, scripted rendered playthrough. Seed 2027, standard difficulty. Accelerated movement and simplified effects; no HP/MP/gold/level/enemy-health cheats.\n" +
                "Normal encounters=" + fullNormals + ", boss encounters=" + fullBosses + ", normal mean turns=" + (fullNormalTurns / (float)fullNormals).ToString("F2") + ", boss mean turns=" + (fullBossTurns / (float)fullBosses).ToString("F2") + ", rests=" + fullRests + "\n" + ProgressSummary();
            File.WriteAllText(Path.Combine(directory, "result.txt"), result);
            momentEnd = -10; reducedEffects = false; yield return FullCapture("clear-ending");
            journalOpen = true; journalTab = 4; yield return FullCapture("clear-records");
            journalTab = 3; yield return FullCapture("dialogue-history"); journalOpen = false;
            settingsOpen = true; yield return FullCapture("settings"); settingsOpen = false;
            Debug.Log("FULL_100_CLEAR_PASSED: " + result); Application.Quit();
        }
    }
}
#endif
