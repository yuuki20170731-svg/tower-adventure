using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEngine;
using TowerAdventure;

public static class ExpansionChecks
{
    static object Call(AdventureGame game, string name, params object[] args)
    { return typeof(AdventureGame).GetMethod(name, BindingFlags.Instance | BindingFlags.Static | BindingFlags.NonPublic).Invoke(game, args); }
    static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    static void FinishStory(AdventureGame game)
    {
        var nodes = (StoryNode[])typeof(AdventureGame).GetField("story", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(game);
        for (int page = 0; game.state.mode == "story" && page < 20; page++) Call(game, "Choose", nodes.First(n => n.id == game.state.storyId).choices[0]);
    }
    public static void Run(AdventureGame game, string directory)
    {
        game.suppressSave = true; game.state = AdventureState.New(2027); game.state.mode = "town"; game.state.gold = 1000;
        Require((bool)Call(game, "Buy", 3, 1), "Weapon purchase failed"); Call(game, "Equip", 0, 0, 1);
        Require(game.state.gold == 940 && game.state.party[0].weapon == 1 && (int)Call(game, "AttackStat", game.state.party[0]) == 23, "Gear price/stat failed");
        Call(game, "Equip", 0, 0, 0); Call(game, "Equip", 1, 0, 1);
        Require(game.state.gearOwned[0] == 0 && game.state.party[0].weapon == 0 && game.state.party[1].weapon == 1, "Equipment duplicated/lost");
        Require(!(bool)Call(game, "Buy", 3, 2), "Premature shop stock"); game.state.gold = 0;
        Require(!(bool)Call(game, "Buy", 0, 0), "Negative balance purchase");
        game.state.party[2].hp = 0; int feathers = game.state.items[2];
        Require((bool)Call(game, "UseItem", 2, 2) && game.state.items[2] == feathers - 1 && game.state.party[2].hp == game.state.party[2].maxHp / 2, "Resurrection failed");
        int herbs = game.state.items[0]; game.state.party[0].hp = game.state.party[0].maxHp;
        Require(!(bool)Call(game, "UseItem", 0, 0) && game.state.items[0] == herbs, "Useless item consumed");
        Call(game, "BeginBattle", game.state.Current.entrance, false); game.state.items[0] = 1;
        game.state.party[0].hp = 20; game.state.party[1].hp = 20;
        var fields = typeof(AdventureGame); fields.GetField("itemTarget", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(game, 0);
        Call(game, "SelectItem", 0); Call(game, "SelectItem", 0);
        Require(game.state.orders.Count(o => o.action == 5) == 1, "Same item over-reserved");
        string path = Path.Combine(directory, "equipment-save.json"); AdventureSave.Write(path, game.state); bool backup; game.state = AdventureSave.Read(path, out backup);
        Require(game.state.party[1].weapon == 1 && game.state.orders[0].action == 5 && game.state.items[0] == 1, "Equipment/item reservation save failed");
        for (int i = 0; i < 5; i++) if (game.state.orders[i].action == 0) game.state.orders[i] = new Order { action = 2 };
        game.Resolve(); Require(game.state.items[0] == 0 && game.state.party[0].hp >= 80, "Queued item did not resolve");
        string oldJson = System.Text.RegularExpressions.Regex.Replace(JsonUtility.ToJson(game.state), "\"(items|gearOwned)\"\\s*:\\s*\\[[^\\]]*\\],?", ""); File.WriteAllText(path, oldJson); game.state = AdventureSave.Read(path, out backup);
        Require(game.state.items.Length == 3 && game.state.gearOwned.Length == 9, "Old inventory migration failed");
        game.state = AdventureState.New(2027); Call(game, "BeginBattle", game.state.Current.entrance, false);
        game.state.party[3].hp = 0; foreach (var e in game.state.enemies) { e.hp = e.maxHp = 9999; e.attack = 0; }
        for (int i = 0; i < 5; i++) game.state.orders[i] = new Order { action = i == 3 ? 0 : 2 };
        game.state.orders[2] = new Order { action = 5, skill = "item:2", target = 3 };
        game.Resolve(); Require(game.state.party[3].hp > 0 && game.state.enemies.All(e => e.hp == 9999), "Resurrection gave an unreserved attack");
        game.saveDirectoryOverride = Path.Combine(directory, "Slots"); game.suppressSave = false;
        for (int slot = 1; slot <= 3; slot++) { Call(game, "RememberSlot", slot); game.state.gold = slot * 100; Call(game, "Save"); }
        Call(game, "AutoSave"); Call(game, "RefreshSlots");
        for (int slot = 1; slot <= 3; slot++) { Call(game, "RememberSlot", slot); Call(game, "Load"); Require(game.state.gold == slot * 100 && !string.IsNullOrEmpty(game.state.savedAt), "Slot isolation failed"); }
        string auto = (string)Call(game, "SlotPath", 0); game.state.gold = 777; Call(game, "AutoSave"); File.WriteAllText(auto, "corrupt"); Call(game, "LoadFrom", auto);
        Require(game.state.gold == 300, "Auto backup recovery failed");
        game.suppressSave = true; game.saveDirectoryOverride = null; Call(game, "RememberSlot", 1);
        foreach (int floor in Enumerable.Range(1, 10).Select(n => n * 10))
        {
            game.state = AdventureState.New(2027); game.state.floor = floor; game.state.floors.Add(AdventureState.Generate(floor, 2027)); game.state.Arrive();
            Call(game, "BeginBattle", game.state.Current.entrance, true); var boss = game.state.enemies[0];
            game.state.orders = Enumerable.Range(0, 5).Select(i => new Order { action = 2 }).ToList();
            boss.hp -= 30; int before = boss.hp; Call(game, "EnemyTurn", boss, 0);
            if (floor == 60) { Require(boss.hp > before, "Mirror heal missing"); game.state.orders[4].action = 3; before = boss.hp; Call(game, "EnemyTurn", boss, 0); Require(boss.hp == before, "Mirror heal counter failed"); }
            if (floor == 90) Require(game.state.enemies.Count == 2, "Boss summon missing");
            game.state.round = 1; foreach (var ally in game.state.party) ally.guarding = false; Call(game, "EnemyTurn", boss, 0);
            if (floor == 40) Require(game.state.party.All(a => a.poison == 3), "Poison boss missing");
            if (floor == 50) Require(game.state.party.All(a => a.mp < a.maxMp), "Mana boss missing");
            if (floor == 70) Require(game.state.party.All(a => a.slow == 2), "Ice boss missing");
            Require(((string)Call(game, "BossIntent")).Length > 0, "Boss telegraph missing");
        }
        CheckPolish(game, directory);
        DepthChecks(game, directory);
        CheckRefinement(game, directory);
        foreach (int difficulty in new[] { 0, 1, 2 }) foreach (int seed in new[] { 2027, 17, 9031 }) Balance(game, directory, seed, difficulty);
        Debug.Log("EXPANSION_CHECKS_PASSED: gear/shop/inventory, resurrection, item reservation/save, 3 slots/auto backup, boss mechanics and 100-floor progression.");
    }
    static void CheckPolish(AdventureGame game, string directory)
    {
        game.state = AdventureState.New(2027); FinishStory(game);
        int baseHp = (int)Call(game, "EnemyHealth", 100), baseAttack = (int)Call(game, "EnemyAttack", 100);
        game.state.difficulty = 1; Require((int)Call(game, "EnemyHealth", 100) < baseHp && (int)Call(game, "EnemyAttack", 100) < baseAttack, "Story difficulty not easier");
        game.state.difficulty = 2; Require((int)Call(game, "EnemyHealth", 100) > baseHp && (int)Call(game, "EnemyAttack", 100) > baseAttack, "Tactical difficulty not harder");
        string path = Path.Combine(directory, "difficulty.json"); AdventureSave.Write(path, game.state); bool backup; game.state = AdventureSave.Read(path, out backup);
        Require(game.state.difficulty == 2, "Difficulty save lost");
        game.state.party[0].maxHp = 500; game.state.party[0].hp = 10; Call(game, "UseItem", 0, 0);
        Require(game.state.party[0].hp == 185, "Late-game herb did not scale");
        game.state.gold = 500; int herbs = game.state.items[0], hp = game.state.party[0].hp;
        game.state.flags.Add("retry:test"); game.state.Current.tiles[game.state.Current.entrance] = 0;
        Call(game, "BeginBattle", game.state.Current.entrance, false);
        game.state.items[0] = 0; game.state.gold = 0; foreach (var a in game.state.party) a.hp = 0; game.state.mode = "over";
        Call(game, "RetryBattle"); AdventureSave.Validate(game.state);
        Require(game.state.mode == "world" && game.state.gold == 500 && game.state.items[0] == herbs && game.state.party[0].hp == hp && game.state.flags.Contains("retry:test") && game.state.Current.tiles[game.state.Current.entrance] == 0, "Retry lost pre-battle world or resources");
        int chest = game.state.Current.entrance; Call(game, "BeginBattle", chest, false); game.state.rewardBattle = true; game.state.mode = "over";
        Call(game, "RetryBattle"); Require(game.state.Current.tiles[chest] == 11 && !game.state.rewardBattle, "Failed treasure battle could not be retried");
        typeof(AdventureGame).GetField("settingsOpen", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(game, true);
        float px = game.state.px, py = game.state.py; game.MoveFree(Vector2.right * .1f);
        Require(game.state.px == px && game.state.py == py, "Settings did not pause movement");
        typeof(AdventureGame).GetField("settingsOpen", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(game, false);
        game.state.difficulty = 3; bool invalid = false; try { AdventureSave.Validate(game.state); } catch (InvalidDataException) { invalid = true; }
        Require(invalid, "Invalid difficulty accepted");
        game.state = AdventureState.New(2027); FinishStory(game);
        var start = new Vector2(game.state.px, game.state.py);
        Call(game, "AdvanceWalk", start, start + Vector2.right * .3f);
        Call(game, "AdvanceWalk", start + Vector2.right * .3f, start + Vector2.right * .3f + Vector2.up * .3f);
        Require((int)Call(game, "WalkFacing", Vector2.left) == 3 && (int)Call(game, "WalkFacing", Vector2.down) == 2, "Walk direction incorrect");
        object follower = Call(game, "FollowPoint", .15f); var pointType = follower.GetType();
        Require(Vector2.Distance((Vector2)pointType.GetField("position").GetValue(follower), start + Vector2.right * .15f) < .001f, "Follower cut across a corner");
        game.state = AdventureState.New(17); Call(game, "EnsureWalk", new Vector2(game.state.px, game.state.py));
        Require((float)typeof(AdventureGame).GetField("walkDistance", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(game) == 0, "New adventure kept old trail");
        var walkArt = Resources.Load<Texture2D>("Art/party_walk_hd"); Require(walkArt != null && walkArt.width == 1536 && walkArt.height == 1024, "Walking atlas missing or wrong layout");
        game.state = AdventureState.New(2027); FinishStory(game); Call(game, "BeginBattle", game.state.Current.entrance, false);
        game.state.enemies.Add(new Actor("test", "enemy_slime", 500, 0, 1, 0));
        game.state.orders = Enumerable.Range(0, 5).Select(p => new Order { action = 1, target = 0 }).ToList();
        game.state.orders[2] = new Order { action = 4, target = 0, skill = "ヒール" };
        game.state.orders[4] = new Order { action = 5, target = 0, skill = "item:0" };
        Call(game, "RememberOrders"); game.state.round++; game.state.enemies[0].hp = 0; game.state.party[2].mp = 0;
        Call(game, "RepeatOrders");
        Require(game.state.orders[0].target == 1 && game.state.orders[2].action == 0 && game.state.orders[4].action == 0, "Repeat used dead target, unavailable magic or inventory");
        AdventureSave.Validate(game.state);
        Call(game, "BeginBattle", game.state.Current.entrance, false); Call(game, "RepeatOrders");
        Require(game.state.orders.All(o => o.action == 0), "Repeat leaked into next battle");
        game.state.mode = "world"; int treasure = Array.IndexOf(game.state.Current.tiles, 3), money = game.state.gold;
        Call(game, "CollectChest", treasure); int received = game.state.gold; Call(game, "CollectChest", treasure);
        Require(received > money && game.state.gold == received, "Treasure reward duplicated");
        Debug.Log("POLISH_CHECKS_PASSED: difficulty/save/recovery/retry, walk/followers, repeat validation/isolation and treasure single reward.");
    }
    static void DepthChecks(AdventureGame game, string directory)
    {
        game.state = AdventureState.New(2027); FinishStory(game); Call(game, "BeginBattle", game.state.Current.entrance, false);
        var witch = new Actor("回復役", "enemy_witch", 100, 0, 10, 0);
        var knight = new Actor("盾役", "enemy_knight", 100, 0, 10, 8); knight.hp = 20;
        var charger = new Actor("溜め役", "enemy_golem", 100, 0, 20, 0);
        game.state.enemies.Clear(); game.state.enemies.Add(witch); game.state.enemies.Add(knight); game.state.enemies.Add(charger);
        int before = knight.hp; Call(game, "EnemyTurn", witch, 0); Require(knight.hp > before, "Normal healer did not heal ally");
        int total = game.state.party.Sum(a => a.hp); Call(game, "EnemyTurn", charger, 0); Require(total == game.state.party.Sum(a => a.hp), "Charging enemy attacked during warning");
        game.state.round = 1; Call(game, "EnemyTurn", charger, 0); Require(total > game.state.party.Sum(a => a.hp), "Charging enemy never attacked");
        var hero = game.state.party[0]; hero.armor = 3; hero.armorEffect = 1; Call(game, "GivePoison", hero, 3); Require(hero.poison == 0, "Poison resistance failed");
        hero.armor = 1; Call(game, "GivePoison", hero, 3); Require(hero.poison == 2, "Poison duration reduction failed");
        var heal = Resources.Load<TextAsset>("Data/skills"); Require(heal != null, "Skills missing");
        var skill = JsonUtility.FromJson<SkillCatalog>(heal.text).entries.First(k => k.heal > 0);
        hero.charm = 1; int baseHeal = (int)Call(game, "HealPower", hero, skill); hero.charmEffect = 1;
        Require((int)Call(game, "HealPower", hero, skill) == baseHeal * 120 / 100, "Healing trait failed");
        hero.charmEffect = 2; game.state.round = 1; int regularCost = (int)Call(game, "SkillCost", hero, skill); game.state.round = 0;
        Require((int)Call(game, "SkillCost", hero, skill) == Math.Max(1, regularCost - 2), "First turn MP trait failed");
        game.state.history.Clear(); for (int i = 0; i < 1001; i++) Call(game, "RecordDialogue", "ミナ", "会話" + i, "返答" + i);
        Require(game.state.history.Count == 1000 && game.state.history[0].text == "会話1", "History limit/order failed");
        hero.weapon = 1; hero.weaponEffect = 2; game.state.turnsTaken = 17; game.state.battlesWon = 3;
        string path = Path.Combine(directory, "depth-save.json"); AdventureSave.Write(path, game.state); bool backup; game.state = AdventureSave.Read(path, out backup);
        Require(game.state.party[0].weaponEffect == 2 && game.state.history.Last().choice == "返答1000" && game.state.turnsTaken == 17 && game.state.battlesWon == 3, "Depth save roundtrip failed");
        game.state.party[0].weaponEffect = 9; bool rejected = false; try { AdventureSave.Validate(game.state); } catch (InvalidDataException) { rejected = true; } Require(rejected, "Invalid trait accepted");
        game.state.party[0].weaponEffect = 0; game.state.history = null; game.state.statsStartFloor = 0; game.state.Upgrade(); AdventureSave.Validate(game.state);
        Require(game.state.history.Count == 0 && game.state.statsStartFloor == game.state.floor, "Old depth save migration failed");
        game.state.mode = "world"; game.state.floor = 50; game.state.floors.Add(AdventureState.Generate(50, 2027)); game.state.Arrive();
        string oldJson = System.Text.RegularExpressions.Regex.Replace(JsonUtility.ToJson(game.state), "\"statsStartFloor\"\\s*:\\s*\\d+,?", "");
        File.WriteAllText(path, oldJson); game.state = AdventureSave.Read(path, out backup);
        Require(game.state.statsStartFloor == 50, "Old save claimed retrospective statistics");
        int shieldHit = 0;
        for (int trait = 0; trait <= 1; trait++)
        {
            game.state = AdventureState.New(2027); FinishStory(game); Call(game, "BeginBattle", game.state.Current.entrance, false);
            game.state.enemies.Clear(); game.state.enemies.Add(new Actor("盾役", "enemy_knight", 1000, 0, 1, 8));
            game.state.party[0].weapon = 1; game.state.party[0].weaponEffect = trait;
            game.state.orders = Enumerable.Range(0, 5).Select(p => new Order { action = p == 0 ? 1 : 2 }).ToList();
            game.Resolve(); int hit = 1000 - game.state.enemies[0].hp;
            if (trait == 0) shieldHit = hit; else Require(hit > shieldHit, "Breaker did not improve physical attack against shield");
        }
        game.state = AdventureState.New(2027); FinishStory(game); Call(game, "BeginBattle", game.state.Current.entrance, false);
        game.state.enemies[0].hp = 1; game.state.party[0].weapon = 1; game.state.party[0].weaponEffect = 2; game.state.party[0].mp = 10;
        game.state.orders = Enumerable.Range(0, 5).Select(p => new Order { action = p == 0 ? 1 : 2 }).ToList();
        game.Resolve(); Require(game.state.party[0].mp == 16 && game.state.battlesWon == 1 && game.state.turnsTaken == 1, "Absorption or battle statistics failed");
        Call(game, "BeginBattle", game.state.Current.entrance, false); game.state.round = 1;
        var caster = new Actor("術役", "enemy_witch", 100, 0, 40, 0); var recipient = game.state.party[2]; recipient.armor = 1;
        recipient.hp = recipient.maxHp; Call(game, "EnemyTurn", caster, 0); int plainHit = recipient.maxHp - recipient.hp;
        recipient.hp = recipient.maxHp; recipient.armorEffect = 2; Call(game, "EnemyTurn", caster, 0);
        Require(recipient.maxHp - recipient.hp < plainHit, "Magic resistance did not reduce enemy spell damage");
        var backgrounds = Resources.Load<Texture2D>("Art/chapters_hd"); Require(backgrounds != null && backgrounds.width == 1536 && backgrounds.height == 1024, "Chapter atlas dimensions changed");
        Debug.Log("DEPTH_CHECKS_PASSED: healer/charge, poison/heal/MP traits, history cap, save roundtrip/migration/validation and chapter art.");
    }
    static void CheckRefinement(AdventureGame game, string directory)
    {
        game.state = AdventureState.New(2027); FinishStory(game); Call(game, "BeginBattle", game.state.Current.entrance, false);
        game.state.enemies.Clear(); var knight = new Actor("盾", "enemy_knight", 1000, 0, 1, 8); var witch = new Actor("回復", "enemy_witch", 1000, 0, 1, 0);
        game.state.enemies.Add(knight); game.state.enemies.Add(witch);
        game.state.orders = Enumerable.Range(0, 5).Select(p => new Order { action = p == 0 ? 1 : 2, target = 1 }).ToList();
        game.Resolve(); Require(knight.hp < 1000 && witch.hp == 1000, "Shield did not cover healer");
        game.state.round = 0; knight.hp = witch.hp = 1000;
        game.state.orders = Enumerable.Range(0, 5).Select(p => new Order { action = p == 0 ? 3 : 2, target = 1, skill = p == 0 ? "ファイア" : null }).ToList();
        game.Resolve(); Require(knight.hp == 1000 && witch.hp < 1000, "Magic did not bypass cover");
        game.state = AdventureState.New(2027); FinishStory(game); game.state.flags.Add("help:talk"); game.state.flags.Add("help:battle");
        Call(game, "BeginBattle", game.state.Current.entrance, false); foreach (var e in game.state.enemies) { e.hp = e.maxHp = 10000; e.attack = 0; e.image = "enemy_slime"; }
        Call(game, "QueueCombo", 0); for (int p = 0; p < 5; p++) if (game.state.orders[p].action == 0) game.state.orders[p] = new Order { action = 2 };
        game.Resolve(); Require(!(bool)Call(game, "CanCombo", 0), "Combo can be repeated without preparation");
        string path = Path.Combine(directory, "refinement-save.json"); AdventureSave.Write(path, game.state); bool backup; game.state = AdventureSave.Read(path, out backup);
        Require(!(bool)Call(game, "CanCombo", 0), "Load reset combo preparation");
        game.state.orders = Enumerable.Range(0, 5).Select(p => new Order { action = 2 }).ToList(); game.Resolve();
        Require((bool)Call(game, "CanCombo", 0), "Combo never becomes ready");
        Call(game, "QueueCombo", 0); Call(game, "QueueAllGuards"); Require(game.state.combo == 0 && game.state.orders.All(o => o.action == 2), "Guard all did not replace combo orders");
        Call(game, "QueueCombo", 0); game.state.party[1].hp = 0;
        Require((int)Call(game, "ResolveCombo") == 0 && game.state.combo == 0, "Failed combo kept its damage/taunt status");
        Call(game, "ResetOrders");
        var fields = typeof(AdventureGame); fields.GetField("selected", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(game, 2); fields.GetField("healTarget", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(game, 0);
        var heal = JsonUtility.FromJson<SkillCatalog>(Resources.Load<TextAsset>("Data/skills").text).entries.First(s => s.name == "ヒール"); game.state.party[0].hp = game.state.party[0].maxHp;
        Call(game, "Queue", 4, heal); Require(game.state.orders[2].action == 0, "Unnecessary heal was queued");
        game.state.party[0].poison = 1; Call(game, "Queue", 4, heal); Require(game.state.orders[2].action == 4, "Healing impending poison damage was blocked");
        game.state = AdventureState.New(2027); game.state.mode = "town"; game.state.gold = 12000;
        Require(!(bool)Call(game, "ImproveWorkshop", 0), "Workshop unlocked too early");
        game.state.floor = 51; game.state.floors.Add(AdventureState.Generate(51, 2027)); game.state.Arrive();
        int attack = (int)Call(game, "AttackStat", game.state.party[0]);
        for (int i = 0; i < 3; i++) Require((bool)Call(game, "ImproveWorkshop", 0), "Workshop purchase failed");
        Require(game.state.gold == 500 && game.state.workshop[0] == 3 && (int)Call(game, "AttackStat", game.state.party[0]) == attack + 6 && !(bool)Call(game, "ImproveWorkshop", 0), "Workshop price/cap/stat failed");
        AdventureSave.Write(path, game.state); game.state = AdventureSave.Read(path, out backup); Require(game.state.workshop[0] == 3, "Workshop was lost on reload");
        game.state.workshop = null; game.state.Upgrade(); Require(game.state.workshop.Length == 3, "Old workshop migration failed");
        var nodes = (StoryNode[])typeof(AdventureGame).GetField("story", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(game);
        for (int chapter = 0; chapter < 10; chapter++) for (int branch = 0; branch < 2; branch++)
        {
            game.state = AdventureState.New(2027); game.state.floor = chapter * 10 + 3; game.state.floors.Add(AdventureState.Generate(game.state.floor, 2027)); game.state.Arrive(); game.state.mode = "world";
            int cell = Array.IndexOf(game.state.Current.tiles, 13); Require(cell >= 0, "Chapter device missing");
            Call(game, "StartSideEvent", cell); var node = nodes.First(n => n.id == game.state.storyId);
            if (branch == 1) { Call(game, "Choose", node.choices[1]); Require(game.state.mode == "story" && game.state.Current.tiles[cell] == 13, "Insufficient funds consumed device"); }
            game.state.gold = 1000; Call(game, "Choose", node.choices[branch]);
            Require(game.state.mode == "world" && game.state.Current.tiles[cell] == 0 && game.state.flags.Contains((branch == 0 ? "survey:" : "ward:") + game.state.floor), "Device choice reward missing");
            Require(branch == 0 ? game.state.Current.explored[game.state.Current.stairs] : game.state.gold == 1000 - 50 - game.state.floor * 2, "Device map/price incorrect");
            AdventureSave.Write(path, game.state); game.state = AdventureSave.Read(path, out backup); Require(game.state.Current.tiles[cell] == 0, "Device duplicated after reload");
            int remaining = game.state.gold, recorded = game.state.history.Count;
            Call(game, "Choose", node.choices[branch]); Require(game.state.gold == remaining && game.state.history.Count == recorded, "Finished dialogue accepted a duplicate choice");
        }
        Debug.Log("REFINEMENT_CHECKS_PASSED: cover/magic, combo preparation/save, workshop price/cap/stats/migration, 10 devices x 2 choices and reward persistence.");
    }
    static void Balance(AdventureGame game, string directory, int seed, int difficulty)
    {
        game.state = AdventureState.New(seed); game.state.difficulty = difficulty; FinishStory(game);
        int battles = 0, rounds = 0, rests = 0, bossRounds = 0, normalRounds = 0; var report = new System.Text.StringBuilder("floor,battles,rounds,level,lowest_sampled_party_hp_percent,end_floor_party_hp_percent,gold\n");
        for (int floor = 1; floor <= 100; floor++)
        {
            int floorBattles = 0, floorRounds = 0, lowestHp = 100;
            foreach (int cell in DungeonLayout.Path(game.state.Current, game.state.Current.entrance, game.state.Current.stairs).Skip(1))
            {
                var goal = new Vector2(cell % AdventureState.Width + .5f, cell / AdventureState.Width + .5f);
                for (int step = 0; Vector2.Distance(new Vector2(game.state.px, game.state.py), goal) > .002f && step < 200; step++)
                {
                    var delta = goal - new Vector2(game.state.px, game.state.py); game.MoveFree(delta.normalized * Math.Min(.09f, delta.magnitude));
                    if (game.state.mode == "battle")
                    {
                        battles++; floorBattles++;
                        for (int turn = 0; game.state.mode == "battle" && turn < 50; turn++)
                        {
                            int target = game.state.enemies.FindIndex(e => e.hp > 0);
                            int wounded = Enumerable.Range(0, 5).Where(p => game.state.party[p].hp > 0).OrderBy(p => (float)game.state.party[p].hp / game.state.party[p].maxHp).First();
                            for (int p = 0; p < 5; p++)
                            {
                                var a = game.state.party[p]; bool heal = p == 2 && a.mp >= 8 && game.state.party[wounded].hp < game.state.party[wounded].maxHp * .65f;
                                game.state.orders[p] = new Order { action = game.state.bossBattle && game.state.round % 3 == 1 ? 2 : heal ? 4 : 1, target = heal ? wounded : target, skill = heal ? "ヒール" : null };
                            }
                            bool bossTurn = game.state.bossBattle;
                            game.Resolve(); floorRounds++; rounds++; if (bossTurn) bossRounds++; else normalRounds++;
                            lowestHp = Math.Min(lowestHp, (int)game.state.party.Min(a => 100f * a.hp / a.maxHp));
                        }
                        FinishStory(game); Require(game.state.mode == "world" || floor == 100 && game.state.mode == "clear", "100-floor combat failed at " + floor);
                    }
                    if (game.state.mode == "clear") break;
                }
                if (game.state.mode == "clear") break;
                Require(Vector2.Distance(new Vector2(game.state.px, game.state.py), goal) < .002f, "100-floor route stuck at " + floor);
                if (game.state.Current.tiles[cell] == 4)
                {
                    Call(game, "RecoverParty"); rests++; game.state.mode = "town";
                    int tier = floor >= 51 ? 3 : floor >= 21 ? 2 : 1;
                    for (int p = 0; p < 5; p++) for (int kind = 0; kind < 3; kind++)
                    {
                        var a = game.state.party[p]; int current = (int)Call(game, "GearTier", a, kind);
                        if (current < tier && (bool)Call(game, "Buy", kind + 3, tier)) Call(game, "Equip", p, kind, tier);
                    }
                    game.state.mode = "world";
                }
            }
            report.AppendLine(floor + "," + floorBattles + "," + floorRounds + "," + game.state.level + "," + lowestHp + "," + (int)game.state.party.Min(a => 100f * a.hp / a.maxHp) + "," + game.state.gold);
            if (floor < 100) game.state.NextFloor();
        }
        Require(game.state.mode == "clear" && game.state.party.All(a => a.hp > 0), "100-floor clear failed");
        string reportDirectory = Path.Combine(Directory.GetCurrentDirectory(), "Checks"); Directory.CreateDirectory(reportDirectory);
        File.WriteAllText(Path.Combine(reportDirectory, "balance-seed" + seed + "-difficulty" + difficulty + ".csv"), report.ToString());
        if (seed == 2027 && difficulty == 0) File.WriteAllText(Path.Combine(reportDirectory, "balance-100floors.csv"), report.ToString());
        Debug.Log("BALANCE_100_FLOORS: seed=" + seed + ", difficulty=" + difficulty + ", battles=" + battles + ", rounds=" + rounds + ", normalMean=" + ((float)normalRounds / (battles - 10)).ToString("F1") + ", bossMean=" + (bossRounds / 10f).ToString("F1") + ", rests=" + rests + ", finalLevel=" + game.state.level);
    }
}


