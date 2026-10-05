#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System;
using System.IO;
using System.Linq;
using System.Collections;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        IEnumerator CheckOpeningPlayer(string directory)
        {
            journalOpen = combosOpen = bagOpen = slotsOpen = false; combatFx.Clear(); effectEnd = 0;
            state = AdventureState.New(2027); menu = ""; log.Clear();
            while (state.mode == "story") Choose(story.First(n => n.id == state.storyId).choices[0]);
            int battles = 0, turns = 0, comboUses = 0; bool captured = false;
            for (int floor = 1; floor <= 10; floor++)
            {
                var route = DungeonLayout.Path(state.Current, state.Current.entrance, state.Current.stairs);
                if (floor == 1)
                {
                    int talk = Array.IndexOf(state.Current.tiles, 7);
                    route = DungeonLayout.Path(state.Current, state.Current.entrance, talk).Concat(DungeonLayout.Path(state.Current, talk, state.Current.stairs).Skip(1)).ToList();
                }
                foreach (int cell in route.Skip(1))
                {
                    Vector2 goal = new Vector2(cell % AdventureState.Width + .5f, cell / AdventureState.Width + .5f);
                    for (int frame = 0; Vector2.Distance(new Vector2(state.px, state.py), goal) > .005f && frame < 200; frame++)
                    {
                        var difference = goal - new Vector2(state.px, state.py);
                        MoveFree(difference.normalized * Mathf.Min(.3f, difference.magnitude));
                        if (state.mode == "battle")
                        {
                            battles++;
                            for (int turn = 0; state.mode == "battle" && turn < 50; turn++)
                            {
                                while (EffectsBusy) yield return null;
                                QueueAllAttacks();
                                if ((!state.bossBattle || state.round % 3 == 2) && CanCombo(0)) { QueueCombo(0); comboUses++; }
                                int wounded = Enumerable.Range(0, 5).Where(p => state.party[p].hp > 0).OrderBy(p => (float)state.party[p].hp / state.party[p].maxHp).First();
                                if (state.bossBattle && state.round % 3 == 1) { CancelCombo(); for (int p = 0; p < 5; p++) state.orders[p] = new Order { action = 2 }; }
                                else if (state.party[wounded].hp < state.party[wounded].maxHp * .65f && state.party[2].mp >= SkillCost(state.party[2], skills.First(k => k.name == "ヒール")))
                                { selected = 2; healTarget = wounded; Queue(4, skills.First(k => k.name == "ヒール")); }
                                Resolve(); turns++;
                                if (!captured) { for (int i = 0; i < 7; i++) yield return null; ScreenCapture.CaptureScreenshot(Path.Combine(directory, "20-battle-effects.png")); captured = true; }
                                while (EffectsBusy) yield return null;
                            }
                            if (state.mode == "over") { Debug.LogError("RUNTIME_OPENING_FAILED: floor=" + floor); Application.Quit(1); yield break; }
                        }
                        while (state.mode == "story") { Choose(story.First(n => n.id == state.storyId).choices[0]); yield return null; }
                        yield return null;
                    }
                    if (state.Current.tiles[cell] == 7) { ExploreConversation(); while (state.mode == "story") { Choose(story.First(n => n.id == state.storyId).choices[0]); yield return null; } }
                    if (state.Current.tiles[cell] == 4)
                    {
                        RecoverParty(); state.mode = "town";
                        for (int p = 0; p < 5; p++) if (state.party[p].weapon == 0 && Buy(3, 1)) Equip(p, 0, 1);
                        state.mode = "world";
                    }
                }
                Debug.Log("RUNTIME_FLOOR_PLAYED: " + floor + ", level=" + state.level + ", battles=" + battles);
                if (floor < 10) state.NextFloor();
            }
            if (!state.Current.bossDefeated || comboUses == 0) { Debug.LogError("RUNTIME_OPENING_FAILED: missing boss/combo"); Application.Quit(1); yield break; }
            for (int i = 0; i < 10; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "21-opening-cleared.png"));
            File.WriteAllText(Path.Combine(directory, "opening-playthrough.txt"), "Actual player scripted playthrough, seed 2027, floors 1-10, battles=" + battles + ", turns=" + turns + ", combos=" + comboUses + ", level=" + state.level + ", bossDefeated=" + state.Current.bossDefeated);
            Debug.Log("RUNTIME_OPENING_PASSED: 10 floors, " + battles + " encounters, " + turns + " turns, " + comboUses + " combos, first boss cleared.");
        }
        IEnumerator CaptureExpansion(string directory)
        {
            suppressSave = true; combosOpen = journalOpen = bagOpen = slotsOpen = false;
            state = AdventureState.New(2026); state.floor = 31; state.floors.Add(AdventureState.Generate(31, state.seed)); state.Arrive(); state.mode = "town"; state.gold = 2400;
            OpenBag(2);
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "13-shop.png"));
            for (int i = 0; i < 10; i++) yield return null;
            Buy(3, 2); Equip(0, 0, 2); Buy(4, 2); Equip(0, 1, 2); Buy(5, 2); Equip(0, 2, 2); bagTab = 1;
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "14-equipment.png"));
            for (int i = 0; i < 10; i++) yield return null;
            state.party[2].hp = 0; bagTab = 0; itemTarget = 2;
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "15-items.png"));
            for (int i = 0; i < 10; i++) yield return null;
            bagOpen = false; saveDirectoryOverride = Path.Combine(directory, "SlotSamples"); suppressSave = false;
            for (int slot = 1; slot <= 3; slot++) { RememberSlot(slot); state.gold = slot * 100; Save(); }
            AutoSave(); OpenSlots(); suppressSave = true;
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "16-save-slots.png"));
            for (int i = 0; i < 10; i++) yield return null;
            slotsOpen = false; saveDirectoryOverride = null;
            foreach (int floor in new[] { 1, 31, 61, 71, 91 })
            {
                state = AdventureState.New(2026); state.mode = "world"; state.floor = floor;
                if (floor != 1) state.floors.Add(AdventureState.Generate(floor, state.seed)); state.Arrive(); Array.Fill(state.Current.explored, true);
                for (int i = 0; i < 15; i++) yield return null;
                ScreenCapture.CaptureScreenshot(Path.Combine(directory, "17-chapter-" + floor + ".png"));
                for (int i = 0; i < 10; i++) yield return null;
            }
            state = AdventureState.New(2026); state.floor = 90; state.floors.Add(AdventureState.Generate(90, state.seed)); state.Arrive(); BeginBattle(state.Current.entrance, true);
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "18-boss-intent.png"));
            for (int i = 0; i < 10; i++) yield return null;
            state.mode = "world"; settingsOpen = true;
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "22-settings.png"));
            for (int i = 0; i < 10; i++) yield return null;
            settingsOpen = false; state = AdventureState.New(2027); state.mode = "world";
            BeginBattle(state.Current.entrance, false); foreach (var a in state.party) a.hp = 0; state.mode = "over";
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "23-retry.png"));
            for (int i = 0; i < 10; i++) yield return null;
            RetryBattle();
            state = AdventureState.New(2027); state.mode = "world"; Array.Fill(state.Current.explored, true);
            var walkPath = DungeonLayout.Path(state.Current, state.Current.entrance, state.Current.stairs);
            for (int waypoint = 1; waypoint < Mathf.Min(7, walkPath.Count); waypoint++)
            {
                int cell = walkPath[waypoint]; var goal = new Vector2(cell % AdventureState.Width + .5f, cell / AdventureState.Width + .5f);
                while (Vector2.Distance(new Vector2(state.px, state.py), goal) > .002f)
                {
                    var delta = goal - new Vector2(state.px, state.py); MoveFree(delta.normalized * Mathf.Min(.08f, delta.magnitude));
                    if (waypoint == 6 && delta.magnitude > .3f && delta.magnitude < .4f) ScreenCapture.CaptureScreenshot(Path.Combine(directory, "25-walking-party.png"));
                    yield return null;
                }
            }
            int chest = Array.IndexOf(state.Current.tiles, 3); CollectChest(chest);
            for (int i = 0; i < 7; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "26-treasure-feedback.png"));
            for (int i = 0; i < 10; i++) yield return null;
            state = AdventureState.New(2027); state.mode = "world"; state.level = 4;
            BeginBattle(state.Current.entrance, false); while (EffectsBusy) yield return null;
            for (int p = 0; p < 5; p++) state.orders[p] = new Order { action = 2 };
            selected = 4; Queue(3, skills.First(s => s.name == "ファイア")); Resolve();
            for (int i = 0; i < 9; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "27-magic-feedback.png"));
            while (EffectsBusy) yield return null;
            RepeatOrders();
            for (int i = 0; i < 10; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "28-repeat-orders.png"));
            for (int i = 0; i < 10; i++) yield return null;
            foreach (var enemy in state.enemies) enemy.hp = 1;
            state.experience = state.level * 35 - 1; QueueAllAttacks(); Resolve(); while (EffectsBusy) yield return null;
            for (int i = 0; i < 8; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "29-victory-level-up.png"));
            for (int i = 0; i < 10; i++) yield return null;
            int stairs = state.Current.stairs; state.px = stairs % AdventureState.Width + .5f; state.py = stairs / AdventureState.Width + .5f;
            state.x = (int)state.px; state.y = (int)state.py; Interact();
            for (int i = 0; i < 5; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "30-floor-transition.png"));
            while (EffectsBusy) yield return null;
            yield return CheckOpeningPlayer(directory);
        }
    }
}
#endif
