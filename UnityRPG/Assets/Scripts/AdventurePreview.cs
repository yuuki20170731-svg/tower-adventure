#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System;
using System.Collections;
using System.IO;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        void StartVisualCheckIfRequested()
        {
            string[] args = Environment.GetCommandLineArgs();
            int full = Array.IndexOf(args, "-full-playthrough");
            if (full >= 0 && full + 1 < args.Length) { StartCoroutine(FullPlaythrough(args[full + 1])); return; }
            int depth = Array.IndexOf(args, "-depth-visual-check");
            if (depth >= 0 && depth + 1 < args.Length) { StartCoroutine(CaptureDepthScreens(args[depth + 1])); return; }
            int index = Array.IndexOf(args, "-visual-check");
            if (index >= 0 && index + 1 < args.Length) StartCoroutine(CaptureScreens(args[index + 1]));
        }
        IEnumerator CaptureDepthScreens(string directory)
        {
            suppressSave = true; NewGame(); reducedEffects = false; textSpeed = 1; ApplyPreferences();
            fullDirectory = directory; Directory.CreateDirectory(directory); Directory.CreateDirectory(Path.Combine(directory, "Screens"));
            Screen.SetResolution(1200, 800, false); Application.targetFrameRate = 30;
            foreach (int floor in Enumerable.Range(0, 10).Select(c => c * 10 + 1))
            {
                state = AdventureState.New(2027); state.floor = floor;
                if (floor != 1) state.floors.Add(AdventureState.Generate(floor, 2027)); state.Arrive(); state.mode = "world";
                BeginBattle(state.Current.entrance, false); while (EffectsBusy) yield return null;
                yield return FullCapture("chapter-battle-" + floor);
            }
            state.mode = "world"; BeginStory("explore_91");
            for (int i = 0; i < 20; i++) yield return null;
            var node = story.First(n => n.id == state.storyId); int partial = RevealedStory(node).Length;
            if (partial == 0 || partial >= node.text.Length) { FullFailure("Slow text did not reveal gradually"); yield break; }
            yield return FullCapture("slow-text"); forceReveal = true;
            if (RevealedStory(node) != node.text) { FullFailure("Instant reveal failed"); yield break; }
            yield return FullCapture("revealed-text");
            while (state.mode == "story") Choose(story.First(n => n.id == state.storyId).choices[0]);
            journalOpen = true; journalTab = 3; yield return FullCapture("history"); journalOpen = false;
            state.mode = "town"; state.gold = 3000;
            for (int kind = 0; kind < 3; kind++) { Buy(kind + 3, 3); Equip(0, kind, 3); SetGearEffect(0, kind, 1); }
            OpenBag(1); yield return FullCapture("traits"); bagOpen = false;
            ImproveWorkshop(0); OpenBag(3); yield return FullCapture("workshop"); bagOpen = false;
            state = AdventureState.New(2027); state.floor = 63; state.floors.Add(AdventureState.Generate(63, 2027)); state.Arrive(); textSpeed = 0;
            BeginStory("landmark_6"); yield return FullCapture("chapter-landmark");
            state.mode = "world"; BeginBattle(state.Current.entrance, false); reducedEffects = true; ApplyPreferences();
            state.flags.Add("help:talk"); state.flags.Add("help:battle"); QueueCombo(0);
            for (int p = 0; p < 5; p++) if (state.orders[p].action == 0) state.orders[p] = new Order { action = 2 };
            Resolve(); combosOpen = true; yield return FullCapture("combo-preparation"); combosOpen = false;
            settingsOpen = true; yield return FullCapture("settings"); settingsOpen = false;
            Debug.Log("DEPTH_VISUAL_PASSED: 10 backgrounds, gradual/instant text, selected dialogue history, equipment traits and settings.");
            Application.Quit();
        }
        IEnumerator CaptureScreens(string directory)
        {
            suppressSave = true; reducedEffects = false; ApplyPreferences(); Directory.CreateDirectory(directory);
            Application.targetFrameRate = 30;
            Screen.SetResolution(1200, 800, false);
            for (int i = 0; i < 40; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "01-title.png"));
            for (int i = 0; i < 15; i++) yield return null;
            NewGame(); state = AdventureState.New(2026); state.mode = "world";
            for (int y = 0; y < AdventureState.Height; y++) for (int x = 0; x < AdventureState.Width; x++) state.Current.explored[y * AdventureState.Width + x] = true;
            Message("扉を開けた。星の塔の奥へ進もう。");
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "02-world.png"));
            for (int i = 0; i < 15; i++) yield return null;
            Array.Clear(state.Current.explored, 0, state.Current.explored.Length); state.Reveal();
            Vector2 walkStart = new Vector2(state.px, state.py);
            var walkingRoute = DungeonLayout.Path(state.Current, state.Current.entrance, state.Current.stairs);
            for (int waypoint = 1; waypoint <= Math.Min(6, walkingRoute.Count - 1); waypoint++)
            {
                int cell = walkingRoute[waypoint]; var goal = new Vector2(cell % AdventureState.Width + .5f, cell / AdventureState.Width + .5f);
                for (int frame = 0; Vector2.Distance(new Vector2(state.px, state.py), goal) > .005f && frame < 90; frame++)
                {
                    Vector2 difference = goal - new Vector2(state.px, state.py);
                    MoveFree(difference.normalized * Mathf.Min(difference.magnitude, 3f * Time.deltaTime));
                    yield return null;
                }
            }
            // Capture a fractional position, verifying that the character does not snap to cells.
            int following = walkingRoute[7];
            Vector2 nextGoal = new Vector2(following % AdventureState.Width + .5f, following / AdventureState.Width + .5f);
            MoveFree((nextGoal - new Vector2(state.px, state.py)).normalized * .25f);
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "07-free-movement.png"));
            Debug.Log("FREE_MOVEMENT_CAPTURED: from " + walkStart + " to " + new Vector2(state.px, state.py) + ", travel=" + state.encounterDistance);
            for (int i = 0; i < 15; i++) yield return null;
            state.floor = 61; state.floors.Add(AdventureState.Generate(61, state.seed)); state.level = 8;
            BeginBattle(31, false); selected = 0;
            state.orders[1] = new Order { action = 2, target = 0 };
            state.orders[2] = new Order { action = 4, target = 0, skill = "ヒール" };
            state.orders[3] = new Order { action = 1, target = 0 };
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "03-battle.png"));
            for (int i = 0; i < 15; i++) yield return null;
            state.floor = 31; state.floors.Add(AdventureState.Generate(31, state.seed)); state.Arrive();
            BeginStory("explore_31");
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "04-story.png"));
            for (int i = 0; i < 15; i++) yield return null;
            state.mode = "town";
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "05-town.png"));
            for (int i = 0; i < 15; i++) yield return null;
            Screen.SetResolution(1600, 1000, false); state.mode = "battle";
            for (int i = 0; i < 25; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "06-battle-1600.png"));
            for (int i = 0; i < 15; i++) yield return null;
            state = AdventureState.New(2026); log.Clear(); state.mode = "world"; state.floor = 12;
            state.floors.Add(AdventureState.Generate(12, state.seed)); state.Arrive();
            Array.Fill(state.Current.explored, true); React("floor");
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "08-journey-world.png"));
            for (int i = 0; i < 15; i++) yield return null;
            StartSideEvent(Array.IndexOf(state.Current.tiles, 10));
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "09-companion-quest.png"));
            for (int i = 0; i < 15; i++) yield return null;
            Choose(story.First(n => n.id == state.storyId).choices[0]);
            Choose(story.First(n => n.id == state.storyId).choices[0]);
            journalOpen = true;
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "10-journal.png"));
            for (int i = 0; i < 15; i++) yield return null;
            journalOpen = false; BeginBattle(state.y * AdventureState.Width + state.x, false);
            for (int i = 1; i < 4; i++) state.flags.Add("quest_" + QuestKeys[i] + "_done");
            combosOpen = true;
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "11-combo.png"));
            for (int i = 0; i < 15; i++) yield return null;
            combosOpen = false; QueueCombo(0);
            for (int i = 0; i < 15; i++) yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, "12-combo-reserved.png"));
            for (int i = 0; i < 15; i++) yield return null;
            yield return CaptureExpansion(directory);
            Debug.Log("VISUAL_CHECK_CAPTURED");
            Application.Quit();
        }
    }
}
#endif






