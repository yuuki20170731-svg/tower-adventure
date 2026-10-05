using System;
using System.Collections.Generic;
using UnityEngine;

namespace TowerAdventure
{
    [Serializable] public class Actor
    {
        public string name, image;
        public int hp, maxHp, mp, maxMp, attack, defense, poison;
        public bool guarding;
        public int weapon, armor, charm, slow;
        public int weaponEffect, armorEffect, charmEffect;
        public Actor(string name, string image, int hp, int mp, int attack, int defense)
        { this.name = name; this.image = image; this.hp = maxHp = hp; this.mp = maxMp = mp; this.attack = attack; this.defense = defense; }
    }
    [Serializable] public class Order { public int action, target; public string skill; }
    [Serializable] public class DialogueRecord { public int floor; public string speaker, text, choice; }
    [Serializable] public class FloorState
    {
        public int number, entrance, stairs;
        public int[] tiles;
        public bool[] explored;
        public List<int> defeated = new List<int>();
        public bool bossDefeated, conversationDone;
    }
    [Serializable] public class AdventureState
    {
        public const int Width = 17, Height = 11;
        public int version = 2, seed, floor = 1, x = 1, y = 1, gold, level = 1, experience;
        public string storyReturnMode = "world";
        public bool storyExploration;
        public int journeyCell = -1, combo, comboTarget, chatterCount;
        public string journeyOutcome = "";
        public bool rewardBattle;
        public int[] items = { 3, 2, 1 };
        public int[] gearOwned = new int[9];
        public int[] workshop = new int[3];
        public int comboReadyRound;
        public string savedAt;
        public float playSeconds;
        public int difficulty; // 0: standard (including older saves), 1: story, 2: tactical
        public List<DialogueRecord> history = new List<DialogueRecord>();
        public int battlesWon, turnsTaken, chestsOpened, itemsUsed, combosUsed, goldEarned, statsStartFloor = 1;
        public string mode = "story", storyId = "start", build = "balanced";
        public int[] personality = new int[6];
        public List<string> flags = new List<string>();
        public List<Actor> party = new List<Actor>();
        public List<FloorState> floors = new List<FloorState>();
        public List<Actor> enemies = new List<Actor>();
        public List<Order> orders = new List<Order>();
        public int battleCell, round;
        public bool bossBattle;
        public float px, py, encounterDistance, nextEncounterDistance;
        public int encounterCount;
        public FloorState Current { get { return floors.Find(f => f != null && f.number == floor); } }
        public static AdventureState New(int seed)
        {
            var s = new AdventureState { seed = seed };
            s.party.Add(new Actor("勇者", "player", 100, 40, 18, 5));
            s.party.Add(new Actor("戦士", "ally_warrior", 90, 20, 16, 6));
            s.party.Add(new Actor("僧侶", "ally_priest", 65, 48, 9, 3));
            s.party.Add(new Actor("弓使い", "ally_archer", 75, 30, 14, 4));
            s.party.Add(new Actor("魔法使い", "ally_mage", 60, 55, 10, 2));
            s.floors.Add(Generate(1, seed));
            s.Arrive();
            return s;
        }
        public static FloorState Generate(int floor, int seed) { return DungeonLayout.Generate(floor, seed); }
        public void Reveal()
        {
            for (int yy = Math.Max(0, y - 3); yy <= Math.Min(Height - 1, y + 3); yy++)
                for (int xx = Math.Max(0, x - 3); xx <= Math.Min(Width - 1, x + 3); xx++) Current.explored[yy * Width + xx] = true;
        }
        public void Arrive()
        {
            x = Current.entrance % Width; y = Current.entrance / Width;
            px = x + .5f; py = y + .5f; ResetEncounter(); Reveal();
        }
        public void ResetEncounter()
        {
            encounterDistance = 0;
            nextEncounterDistance = 20 + new System.Random(unchecked(seed + floor * 1237 + encounterCount * 3253)).Next(11);
        }
        public void Upgrade()
        {
            if (history == null) history = new List<DialogueRecord>();
            if (statsStartFloor <= 0) statsStartFloor = floor;
            if (items == null) items = new[] { 3, 2, 1 };
            if (gearOwned == null) gearOwned = new int[9];
            if (workshop == null) workshop = new int[3];
            if (version != 1) return;
            if (floors == null) { version = 2; return; }
            foreach (var f in floors)
            {
                if (f == null || f.tiles == null || f.tiles.Length != Width * Height) continue;
                f.entrance = Width + 1; f.stairs = Array.IndexOf(f.tiles, 5);
                for (int i = 0; i < f.tiles.Length; i++) if (f.tiles[i] == 2) f.tiles[i] = 0;
                if (f.tiles[f.entrance] == 0) f.tiles[f.entrance] = 9;
            }
            px = x + .5f; py = y + .5f; ResetEncounter(); version = 2;
        }
        public void NextFloor()
        {
            floor++;
            if (Current == null) floors.Add(Generate(floor, seed));
            Arrive();
        }
    }
    [Serializable] public class EnemyCatalog { public EnemyEntry[] entries; }
    [Serializable] public class EnemyEntry { public string name, image, desc, skill; public int hp, attack, defense, exp; }
    [Serializable] public class SkillCatalog { public SkillEntry[] entries; }
    [Serializable] public class SkillEntry { public string name, desc; public int cost, power, heal, unlock; public float poison_chance, paralyze_chance; }
    [Serializable] public class StoryCatalog { public StoryNode[] story_paths; }
    [Serializable] public class StoryNode { public string id, text, speaker, portrait, chapter; public StoryChoice[] choices; }
    [Serializable] public class StoryChoice { public string text, next, effect; }
}








