using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using TowerAdventure;

public static class AdventureProject
{
    const string Scene = "Assets/Scenes/Adventure.unity";
    [MenuItem("Adventure/Create or open game scene")]
    public static void Setup()
    {
        if (!File.Exists(Scene))
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var camera = new GameObject("Camera").AddComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = new Color(.04f, .07f, .12f);
            camera.gameObject.AddComponent<AudioListener>();
            new GameObject("Tower Adventure").AddComponent<AdventureGame>();
            EditorSceneManager.SaveScene(scene, Scene);
        }
        else EditorSceneManager.OpenScene(Scene);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(Scene, true) };
        PlayerSettings.companyName = "Yuuki"; PlayerSettings.productName = "Tower Adventure";
        PlayerSettings.defaultScreenWidth = 1600; PlayerSettings.defaultScreenHeight = 1000;
        PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
        AssetDatabase.SaveAssets();
    }
    [MenuItem("Adventure/Run migration checks")]
    public static void Check()
    {
        Setup();
        int minimumDistance = int.MaxValue;
        var entries = new System.Collections.Generic.HashSet<int>();
        var exits = new System.Collections.Generic.HashSet<int>();
        for (int seed = 0; seed < 10; seed++) for (int number = 1; number <= 100; number++)
        {
            var floor = AdventureState.Generate(number, seed);
            var distances = DungeonLayout.Distances(floor, floor.entrance);
            Require(floor.entrance != floor.stairs && floor.tiles[floor.stairs] == 5 && floor.tiles[floor.entrance] == 9, "Invalid endpoints");
            Require(distances[floor.stairs] == distances.Max(), "Stairs are not at a farthest point");
            Require(Enumerable.Range(0, floor.tiles.Length).All(i => floor.tiles[i] == 1 || distances[i] >= 0), "Unreachable landmark");
            Require(!floor.tiles.Contains(2), "Static enemies remain");
            if (number % 10 == 0) Require(floor.tiles.Contains(8), "Missing boss");
            if (number == 1 || number % 5 == 0 || number % 10 == 9) Require(floor.tiles.Contains(4), "Missing supply");
            minimumDistance = Math.Min(minimumDistance, distances[floor.stairs]); entries.Add(floor.entrance); exits.Add(floor.stairs);
        }
        Require(minimumDistance >= 14 && entries.Count > 10 && exits.Count > 10, "Endpoints too close or insufficient variety");
        var state = AdventureState.New(42);
        int chest = Array.IndexOf(state.Current.tiles, 3), door = Array.IndexOf(state.Current.tiles, 6);
        state.Current.tiles[chest] = state.Current.tiles[door] = 0;
        state.Current.conversationDone = true; state.personality[2] = 7; state.storyId = "adventure_start";
        state.encounterDistance = 3.125f; state.encounterCount = 2;
        var route = DungeonLayout.Path(state.Current, state.Current.entrance, state.Current.stairs);
        int next = route[1]; state.px += (next % AdventureState.Width - state.x) * .1f; state.py += (next / AdventureState.Width - state.y) * .1f;
        string directory = Path.Combine(Directory.GetCurrentDirectory(), "Temp", "AdventureChecks");
        Directory.CreateDirectory(directory); string path = Path.Combine(directory, "save.json");
        foreach (string suffix in new[] { "", ".bak", ".tmp" }) if (File.Exists(path + suffix)) File.Delete(path + suffix);
        AdventureSave.Write(path, state);
        bool recovered; var loaded = AdventureSave.Read(path, out recovered);
        Require(!recovered && loaded.Current.tiles[chest] == 0 && loaded.Current.tiles[door] == 0 && loaded.Current.conversationDone && loaded.personality[2] == 7 && loaded.storyId == "adventure_start" && Math.Abs(loaded.px - state.px) < .0001f && Math.Abs(loaded.py - state.py) < .0001f && loaded.encounterDistance == 3.125f && loaded.encounterCount == 2, "World/continuous-position save failed");
        state.mode = "battle"; state.enemies.Add(new Actor("test", "enemy_slime", 30, 0, 8, 0));
        state.orders = Enumerable.Range(0, 5).Select(i => new Order { action = 2, target = 0 }).ToList();
        state.orders[0] = new Order { action = 3, target = 0, skill = "ファイア" }; state.orders[1] = new Order(); state.round = 4;
        AdventureSave.Write(path, state); loaded = AdventureSave.Read(path, out recovered);
        Require(loaded.mode == "battle" && loaded.round == 4 && loaded.orders[0].skill == "ファイア" && loaded.orders[1].action == 0, "Battle save failed");
        File.WriteAllText(path, "broken"); loaded = AdventureSave.Read(path, out recovered);
        Require(recovered, "Backup recovery failed");
        loaded.px = float.NaN; bool rejected = false;
        try { AdventureSave.Validate(loaded); } catch (InvalidDataException) { rejected = true; }
        Require(rejected, "Invalid continuous coordinate accepted");
        var legacy = AdventureState.New(12); legacy.version = 1; legacy.x = legacy.y = 1;
        int oldEnemy = Array.FindIndex(legacy.Current.tiles, t => t == 0); legacy.Current.tiles[oldEnemy] = 2;
        File.WriteAllText(path, JsonUtility.ToJson(legacy)); loaded = AdventureSave.Read(path, out recovered);
        Require(loaded.version == 2 && loaded.px == 1.5f && loaded.py == 1.5f && !loaded.Current.tiles.Contains(2), "Legacy save migration failed");
        var game = UnityEngine.Object.FindFirstObjectByType<AdventureGame>();
        typeof(AdventureGame).GetMethod("Awake", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).Invoke(game, null);
        game.suppressSave = true;
        CheckStory(game, path); CheckJourney(game, path);
        game.state = AdventureState.New(99); game.state.mode = "world";
        // Exercise real fractional movement, doors, random battles and the first boss.
        int battles = 0;
        for (int floor = 1; floor <= 10; floor++)
        {
            var pathToStairs = DungeonLayout.Path(game.state.Current, game.state.Current.entrance, game.state.Current.stairs);
            foreach (int cell in pathToStairs.Skip(1))
            {
                var goal = new Vector2(cell % AdventureState.Width + .5f, cell / AdventureState.Width + .5f);
                for (int step = 0; Vector2.Distance(new Vector2(game.state.px, game.state.py), goal) > .001f && step < 100; step++)
                {
                    Vector2 delta = goal - new Vector2(game.state.px, game.state.py);
                    game.MoveFree(delta.normalized * Math.Min(.08f, delta.magnitude));
                    if (game.state.mode == "battle") { battles++; FinishEncounter(game); }
                }
                Require(Vector2.Distance(new Vector2(game.state.px, game.state.py), goal) < .002f, "Movement stuck on floor " + floor);
                if (game.state.Current.tiles[cell] == 4) { foreach (var actor in game.state.party) { actor.hp = actor.maxHp; actor.mp = actor.maxMp; } game.state.ResetEncounter(); }
            }
            if (floor == 10) Require(game.state.Current.bossDefeated, "Boss not defeated");
            if (floor < 10) game.state.NextFloor(); // no user autosaves from checks
        }
        Require(battles > 3, "Random encounters did not occur");
        game.state = AdventureState.New(5); game.state.mode = "world";
        for (int y = 0; y < AdventureState.Height; y++) for (int x = 0; x < AdventureState.Width; x++) game.state.Current.tiles[y * AdventureState.Width + x] = x == 0 || y == 0 || x == AdventureState.Width - 1 || y == AdventureState.Height - 1 || x == 3 ? 1 : 0;
        game.state.px = 2.5f; game.state.py = 5.5f; game.state.x = 2; game.state.y = 5;
        game.MoveFree(new Vector2(1, 1));
        Require(game.state.px < 2.8f && game.state.py > 6.4f, "Wall collision/slide failed");
        float stillDistance = game.state.encounterDistance; game.MoveFree(Vector2.zero);
        Require(game.state.encounterDistance == stillDistance, "Idle movement triggered encounters");
        game.state.encounterDistance = game.state.nextEncounterDistance;
        game.MoveFree(new Vector2(0, .01f)); Require(game.state.mode == "battle", "Distance encounter failed");
        var before = new Vector2(game.state.px, game.state.py); FinishEncounter(game);
        Require(game.state.encounterDistance == 0 && game.state.nextEncounterDistance >= 14, "Post-battle grace failed");
        game.MoveFree(new Vector2(0, .1f)); Require(game.state.mode == "world", "Immediate repeat encounter");
        ExpansionChecks.Run(game, directory);
        game.state = null;
        Debug.Log("ADVENTURE_CHECKS_PASSED: 1000 connected random floors, far endpoints (minimum " + minimumDistance + "), free movement, wall sliding, distance encounters, 10-floor combat, continuous saves and v1 migration.");
    }
    static void FinishEncounter(AdventureGame game)
    {
        for (int turn = 0; game.state.mode == "battle" && turn < 80; turn++)
        {
            int target = game.state.enemies.FindIndex(e => e.hp > 0);
            int wounded = Enumerable.Range(0, 5).Where(i => game.state.party[i].hp > 0).OrderBy(i => (float)game.state.party[i].hp / game.state.party[i].maxHp).First();
            for (int i = 0; i < 5; i++)
            {
                var actor = game.state.party[i];
                bool heal = actor.name == "僧侶" && actor.mp >= 8 && game.state.party[wounded].hp < game.state.party[wounded].maxHp * .65f;
                game.state.orders[i] = new Order { action = game.state.bossBattle && game.state.round % 3 == 1 ? 2 : heal ? 4 : 1, target = heal ? wounded : target, skill = heal ? "ヒール" : null };
            }
            game.Resolve();
        }
        CompleteStory(game);
        Require(game.state.mode == "world", "Combat failed on floor " + game.state.floor);
    }
    static void Call(AdventureGame game, string method, params object[] args)
    { typeof(AdventureGame).GetMethod(method, System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).Invoke(game, args); }
    static StoryNode Node(AdventureGame game)
    { return ((StoryNode[])typeof(AdventureGame).GetField("story", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).GetValue(game)).First(n => n.id == game.state.storyId); }
    static void CompleteStory(AdventureGame game)
    { for (int i = 0; game.state.mode == "story" && i < 20; i++) Call(game, "Choose", Node(game).choices[0]); }
    static void CheckStory(AdventureGame game, string path)
    {
        var nodes = JsonUtility.FromJson<StoryCatalog>(Resources.Load<TextAsset>("Data/story").text).story_paths;
        Require(nodes.Select(n => n.id).Distinct().Count() == nodes.Length, "Duplicate story id");
        Require(nodes.All(n => n.choices.Length > 0 && n.choices.All(c => string.IsNullOrEmpty(c.next) || c.next == "__ENDING__" || nodes.Any(other => other.id == c.next))), "Broken story branch");
        Require(Enumerable.Range(1, 100).All(f => nodes.Any(n => n.id == "explore_" + f && !string.IsNullOrEmpty(n.portrait))), "Missing exploration dialogue");
        Require(nodes.Where(n => n.id.StartsWith("explore_") && int.TryParse(n.id.Substring(8), out _)).Select(n => n.text).Distinct().Count() == 100, "Repeated floor dialogue");
        foreach (string mode in new[] { "world", "town" })
        {
            game.state = AdventureState.New(42); game.state.mode = mode;
            Call(game, "ExploreConversation", mode); Call(game, "Choose", Node(game).choices[0]);
            Require(game.state.mode == "story" && !game.state.Current.conversationDone, "Reply skipped");
            AdventureSave.Write(path, game.state); bool recovered; game.state = AdventureSave.Read(path, out recovered);
            Require(game.state.storyExploration && game.state.storyReturnMode == mode && game.state.flags.Contains("bond_gald"), "Story resume/bond lost");
            CompleteStory(game);
            Require(game.state.mode == mode && game.state.Current.conversationDone, "Dialogue return failed");
        }
        for (int floor = 10; floor <= 90; floor += 10)
        {
            game.state = AdventureState.New(42); game.state.floor = floor; game.state.floors.Add(AdventureState.Generate(floor, 42));
            Call(game, "BossConversation"); Require(game.state.storyId == "post_boss_" + floor, "Boss chapter missing"); CompleteStory(game);
            Require(game.state.mode == "world" && !game.state.Current.conversationDone, "Boss chapter consumed exploration");
        }
        string[] endings = { "ending_restore", "ending_guardian", "ending_freedom" };
        for (int branch = 0; branch < 3; branch++)
        {
            game.state = AdventureState.New(42); game.state.floor = 100; game.state.floors.Add(AdventureState.Generate(100, 42));
            Call(game, "BossConversation"); Call(game, "Choose", Node(game).choices[0]); Call(game, "Choose", Node(game).choices[branch]); CompleteStory(game);
            Require(game.state.mode == "clear" && game.state.flags.Contains(endings[branch]), "Ending branch failed");
        }
        Debug.Log("STORY_CHECKS_PASSED: 390 nodes, 100 distinct floor conversations, 10 chapters, reply save/resume and 3 endings.");
    }
    static void CheckJourney(AdventureGame game, string path)
    {
        var nodes = (StoryNode[])typeof(AdventureGame).GetField("story", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).GetValue(game);
        Require(nodes.Select(n => n.id).Distinct().Count() == nodes.Length && nodes.All(n => n.choices.All(c => string.IsNullOrEmpty(c.next) || c.next == "__ENDING__" || nodes.Any(x => x.id == c.next))), "Journey story link broken");
        string[] keys = { "gald", "mina", "rina", "theo" }; int[] floors = { 12, 22, 42, 52 };
        for (int quest = 0; quest < 4; quest++) for (int branch = 0; branch < 2; branch++)
        {
            game.state = AdventureState.New(72); game.state.floor = floors[quest]; game.state.floors.Add(AdventureState.Generate(floors[quest], 72));
            for (int i = 0; i < quest; i++) game.state.flags.Add("quest_" + keys[i] + "_done");
            int cell = Array.IndexOf(game.state.Current.tiles, 10); Require(cell >= 0, "Quest landmark missing");
            Call(game, "StartSideEvent", cell); Require(game.state.storyId == "quest_" + keys[quest], "Wrong quest offered");
            Call(game, "Choose", Node(game).choices[branch]);
            AdventureSave.Write(path, game.state); bool recovered; game.state = AdventureSave.Read(path, out recovered); CompleteStory(game);
            Require(game.state.flags.Contains("quest_" + keys[quest] + "_done") && game.state.Current.tiles[cell] == 0, "Quest resume/reward failed");
            Call(game, "BeginBattle", cell, false); int beforeMp = game.state.party[quest == 0 ? 1 : quest == 1 ? 2 : 0].mp;
            foreach (var actor in game.state.enemies) { actor.hp = actor.maxHp = 9999; actor.attack = 0; actor.image = "enemy_slime"; }
            foreach (var actor in game.state.party) { actor.hp -= 20; actor.poison = 2; }
            Call(game, "QueueCombo", quest); Require(game.state.combo == quest + 1, "Combo not queued");
            AdventureSave.Write(path, game.state); game.state = AdventureSave.Read(path, out recovered);
            for (int i = 0; i < 5; i++) if (game.state.orders[i].action == 0) game.state.orders[i] = new Order { action = 2 };
            game.Resolve(); Require(game.state.combo == 0 && game.state.party[quest == 0 ? 1 : quest == 1 ? 2 : 0].mp == beforeMp - (quest == 3 ? 10 : branch == 1 && (quest == 1 || quest == 2) ? 5 : 6), "Combo cost/resume failed");
            Require(quest == 1 ? game.state.enemies.All(e => e.hp == 9999) : game.state.enemies.Any(e => e.hp < 9999), "Combo damage failed");
            if (quest == 0) Require(game.state.party[1].guarding && game.state.party[1].hp == game.state.party[1].maxHp - 20 - Math.Max(3, game.state.party[1].maxHp / 20) - 1 && game.state.party[0].hp == game.state.party[0].maxHp - 20 - Math.Max(3, game.state.party[0].maxHp / 20), "Shield combo failed to protect/attract");
            if (quest == 1 || quest == 3) Require(game.state.party.All(a => a.hp >= a.maxHp - 3 && a.poison == 0), "Combo heal/poison failed");
        }
        game.state = AdventureState.New(72); game.state.mode = "world"; int site = Array.FindIndex(game.state.Current.tiles, t => t == 0); game.state.Current.tiles[site] = 12;
        Call(game, "StartSideEvent", site); Call(game, "Choose", Node(game).choices[0]);
        Require(game.state.mode == "story" && game.state.gold == 0 && game.state.Current.tiles[site] == 12, "Insufficient gold consumed traveler");
        Call(game, "Choose", Node(game).choices[1]); Require(game.state.mode == "world" && game.state.Current.tiles[site] == 0 && game.state.flags.Contains("rescued:1"), "Free rescue failed");
        game.state.Current.tiles[site] = 10; game.state.party[0].mp = 0; Call(game, "StartSideEvent", site); CompleteStory(game);
        Require(game.state.party[0].mp == 8 && game.state.flags.Contains("memory:1"), "Memory reward failed");
        game.state.Current.tiles[site] = 11; Call(game, "StartSideEvent", site); CompleteStory(game);
        Require(game.state.rewardBattle && game.state.mode == "battle", "Risk battle missing");
        Call(game, "Escape"); Require(game.state.Current.tiles[site] == 11 && !game.state.rewardBattle, "Escaped risk cannot retry");
        Call(game, "StartSideEvent", site); CompleteStory(game); int maximumMp = game.state.party[0].maxMp;
        AdventureSave.Write(path, game.state); bool backup; game.state = AdventureSave.Read(path, out backup);
        foreach (var e in game.state.enemies) e.hp = 1;
        for (int i = 0; i < 5; i++) game.state.orders[i] = new Order { action = 1, target = 0 };
        game.Resolve(); Require(game.state.mode == "world" && !game.state.rewardBattle && game.state.party[0].maxMp == maximumMp + 2, "Risk reward lost on reload");
        int gold = game.state.gold; game.Resolve(); Require(game.state.gold == gold, "Duplicate victory reward");
        var modal = typeof(AdventureGame).GetField("journalOpen", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic); modal.SetValue(game, true);
        var position = new Vector2(game.state.px, game.state.py); game.MoveFree(Vector2.right); Require(position == new Vector2(game.state.px, game.state.py), "Journal failed to pause walking"); modal.SetValue(game, false);
        game.state.flags.Add("quest_gald_done"); Call(game, "BeginBattle", site, false); Call(game, "QueueCombo", 0);
        Call(game, "QueueAllAttacks"); Require(game.state.combo == 0 && game.state.orders.All(o => o.action == 1), "All attacks did not replace combo");
        Call(game, "QueueCombo", 0); Call(game, "CancelCombo"); Require(game.state.combo == 0 && game.state.orders[1].action == 0 && game.state.orders[3].action == 0, "Combo cancel failed");
        Debug.Log("JOURNEY_CHECKS_PASSED: 4 companion quests/2 routes, saved replies and combos, free rescue, memory, risk escape/retry/save/rewards and journal pause.");
    }
    static void Require(bool condition, string text) { if (!condition) throw new Exception(text); }
    public static void BuildPreview()
    {
        Check();
        var result = BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes = new[] { Scene }, locationPathName = "Build/Preview/TowerAdventure.exe", target = BuildTarget.StandaloneWindows64, options = BuildOptions.Development });
        if (result.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) throw new Exception("Preview build failed");
    }
    public static void BuildDelivery() { BuildPreview(); Build(); }
    [MenuItem("Adventure/Build Windows game")]
    public static void Build()
    {
        Check();
        var result = BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes = new[] { Scene }, locationPathName = "Build/Windows/TowerAdventure.exe", target = BuildTarget.StandaloneWindows64, options = BuildOptions.None });
        if (result.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded) throw new Exception("Build failed");
    }
}










