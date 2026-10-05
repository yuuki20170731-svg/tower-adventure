using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;

namespace TowerAdventure
{
    public static class AdventureSave
    {
        public static void Validate(AdventureState s)
        {
            if (s == null || s.version != 2 || s.difficulty < 0 || s.difficulty > 2 || s.floor < 1 || s.floor > 100 || s.x < 0 || s.x >= AdventureState.Width || s.y < 0 || s.y >= AdventureState.Height ||
                s.party == null || s.party.Count != 5 || s.party.Any(a => a == null || a.maxHp <= 0 || a.hp < 0 || a.hp > a.maxHp || a.mp < 0 || a.mp > a.maxMp || a.weapon < 0 || a.weapon > 3 || a.armor < 0 || a.armor > 3 || a.charm < 0 || a.charm > 3 || a.slow < 0 || a.slow > 2) ||
                s.items == null || s.items.Length != 3 || s.items.Any(i => i < 0 || i > 99) || s.gearOwned == null || s.gearOwned.Length != 9 || s.gearOwned.Any(i => i < 0 || i > 99) || float.IsNaN(s.playSeconds) || float.IsInfinity(s.playSeconds) || s.playSeconds < 0 || s.level < 1 || s.experience < 0 || s.gold < 0 || s.round < 0 || s.combo < 0 || s.combo > 4 || (s.combo > 0 && (s.mode != "battle" || s.comboTarget < 0 || (s.enemies == null || s.comboTarget >= s.enemies.Count))) || s.personality == null || s.personality.Length != 6 || s.personality.Any(p => p < -100 || p > 100) || s.flags == null || s.floors == null || s.Current == null ||
                s.floors.Any(f => f == null || f.number < 1 || f.number > 100 || f.tiles == null || f.tiles.Length != AdventureState.Width * AdventureState.Height || f.explored == null || f.explored.Length != f.tiles.Length || f.defeated == null || f.tiles.Any(t => t < 0 || t > 13) || f.entrance < 0 || f.entrance >= f.tiles.Length || f.stairs < 0 || f.stairs >= f.tiles.Length || f.entrance == f.stairs || f.tiles[f.stairs] != 5) ||
                s.floors.Select(f => f.number).Distinct().Count() != s.floors.Count || s.orders == null || s.enemies == null || s.enemies.Any(a => a == null || a.maxHp <= 0 || a.hp < 0 || a.hp > a.maxHp) || !new[] { "world", "story", "battle", "town", "over", "clear" }.Contains(s.mode) ||
                (s.mode == "battle" && (s.enemies.Count == 0 || s.orders.Count != 5 || s.orders.Any(o => o == null || o.action < 0 || o.action > 5 || (o.action != 0 && (o.target < 0 || o.target >= (o.action == 4 || o.action == 5 ? s.party.Count : s.enemies.Count)))))))
                throw new InvalidDataException("セーブの形式または内容が不正です。");
            if (s.orders.Any(o => o != null && o.action == 5 && !new[] { "item:0", "item:1", "item:2" }.Contains(o.skill))) throw new InvalidDataException("どうぐの予約が不正です。");
            if (s.workshop == null || s.workshop.Length != 3 || s.workshop.Any(v => v < 0 || v > 3) || s.comboReadyRound < 0 || s.comboReadyRound > s.round + 2) throw new InvalidDataException("工房または連携の準備状態が不正です。");
            if (s.party.Any(a => a.weaponEffect < 0 || a.weaponEffect > 2 || a.armorEffect < 0 || a.armorEffect > 2 || a.charmEffect < 0 || a.charmEffect > 2) || s.history == null || s.history.Count > 1000 || s.history.Any(h => h == null || h.floor < 1 || h.floor > 100 || h.speaker == null || h.speaker.Length > 200 || h.text == null || h.text.Length > 20000 || h.choice == null || h.choice.Length > 2000) || s.statsStartFloor < 1 || s.statsStartFloor > 100 || s.battlesWon < 0 || s.turnsTaken < 0 || s.chestsOpened < 0 || s.itemsUsed < 0 || s.combosUsed < 0 || s.goldEarned < 0)
                throw new InvalidDataException("特殊効果または冒険の記録が不正です。");
            if (float.IsNaN(s.px) || float.IsInfinity(s.px) || float.IsNaN(s.py) || float.IsInfinity(s.py) || s.px < 0 || s.py < 0 || s.px >= AdventureState.Width || s.py >= AdventureState.Height || (int)s.px != s.x || (int)s.py != s.y || s.Current.tiles[s.y * AdventureState.Width + s.x] == 1 || float.IsNaN(s.encounterDistance) || float.IsInfinity(s.encounterDistance) || s.encounterDistance < 0 || float.IsNaN(s.nextEncounterDistance) || float.IsInfinity(s.nextEncounterDistance) || s.nextEncounterDistance < 1 || s.encounterCount < 0)
                throw new InvalidDataException("位置またはエンカウント状態が不正です。");
        }
        public static void Write(string path, AdventureState s)
        {
            Validate(s);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string temp = path + ".tmp";
            byte[] bytes = Encoding.UTF8.GetBytes(JsonUtility.ToJson(s, true));
            using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
            { stream.Write(bytes, 0, bytes.Length); stream.Flush(true); }
            if (File.Exists(path)) File.Replace(temp, path, path + ".bak");
            else File.Move(temp, path);
        }
        public static AdventureState Read(string path, out bool recovered)
        {
            recovered = false;
            try { return ReadOne(path); }
            catch (Exception ex) when (ex is IOException || ex is ArgumentException)
            {
                if (!File.Exists(path + ".bak")) throw;
                var s = ReadOne(path + ".bak"); recovered = true; return s;
            }
        }
        static AdventureState ReadOne(string path)
        {
            string json = File.ReadAllText(path); var s = JsonUtility.FromJson<AdventureState>(json);
            if (s != null) { if (!json.Contains("\"statsStartFloor\"")) s.statsStartFloor = s.floor; s.Upgrade(); }
            Validate(s); return s;
        }
    }
}






