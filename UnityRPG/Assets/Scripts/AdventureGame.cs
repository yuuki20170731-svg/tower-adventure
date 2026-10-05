using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame : MonoBehaviour
    {
        public AdventureState state;
        EnemyEntry[] catalog;
        SkillEntry[] skills;
        StoryNode[] story;
        readonly Dictionary<string, Texture2D> textures = new Dictionary<string, Texture2D>();
        readonly List<string> log = new List<string>();
        AudioSource music;
        Font font;
        string musicName, notice = "", menu = "title";
        int selected, target, healTarget; Vector2 skillScroll;
        const string Axes = "勇気,道徳,慈愛,名誉,欲,機転";
        public string SavePath { get { return SlotPath(activeSlot); } }
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        { if (FindFirstObjectByType<AdventureGame>() == null) new GameObject("Tower Adventure").AddComponent<AdventureGame>(); }
        void Awake()
        {
            catalog = JsonUtility.FromJson<EnemyCatalog>(Resources.Load<TextAsset>("Data/enemies").text).entries;
            skills = JsonUtility.FromJson<SkillCatalog>(Resources.Load<TextAsset>("Data/skills").text).entries;
            story = JsonUtility.FromJson<StoryCatalog>(Resources.Load<TextAsset>("Data/story").text).story_paths;
            AddJourneyStories(); InitEffects(); activeSlot = Mathf.Clamp(PlayerPrefs.GetInt("AdventureSlot", 1), 1, 3);
            foreach (var t in Resources.LoadAll<Texture2D>("Art")) { t.filterMode = FilterMode.Bilinear; textures[t.name] = t; }
            font = Font.CreateDynamicFontFromOSFont(new[] { "Yu Gothic", "Meiryo", "Noto Sans CJK JP", "Arial" }, 24);
            music = gameObject.AddComponent<AudioSource>(); music.loop = true; InitPreferences(); InitAmbience();
#if UNITY_EDITOR || DEVELOPMENT_BUILD
            StartVisualCheckIfRequested();
#endif
        }
        void Update()
        {
            string track = state == null ? "title" : state.mode == "battle" ? "battle" : state.mode == "clear" ? "victory" : "world_adventure";
            if (track != musicName) { musicName = track; music.clip = Resources.Load<AudioClip>("Audio/" + track); if (music.clip != null) music.Play(); }
            PlayEffects();
            UpdateAmbience();
            if (Input.GetKeyDown(KeyCode.P)) { settingsOpen = !settingsOpen; journalOpen = combosOpen = bagOpen = slotsOpen = false; pointerDirection = Vector2.zero; }
            if (state != null && menu == "" && !Modal && state.mode != "over" && state.mode != "clear") state.playSeconds += Mathf.Min(Time.unscaledDeltaTime, .25f);
            if (Input.GetKeyDown(KeyCode.F11)) Screen.fullScreen = !Screen.fullScreen;
            if (Input.GetKeyDown(KeyCode.Escape)) { journalOpen = combosOpen = bagOpen = slotsOpen = settingsOpen = false; pointerDirection = Vector2.zero; }
            if (state == null) return;
            if (Input.GetKeyDown(KeyCode.F5)) Save();
            if (Input.GetKeyDown(KeyCode.F9)) Load();
            if (Input.GetKeyDown(KeyCode.Escape)) { journalOpen = combosOpen = bagOpen = slotsOpen = false; pointerDirection = Vector2.zero; }
            if (Input.GetKeyDown(KeyCode.B) && !settingsOpen && state.mode != "over" && state.mode != "clear") { if (bagOpen) bagOpen = false; else OpenBag(); }
            if (Input.GetKeyDown(KeyCode.J) && !settingsOpen) { journalOpen = !journalOpen; combosOpen = bagOpen = slotsOpen = false; pointerDirection = Vector2.zero; }
            if (menu != "" || Modal || EffectsBusy) return;
            if (state.mode == "world")
            {
                Vector2 direction = new Vector2((Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow) ? 1 : 0) - (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow) ? 1 : 0),
                    (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow) ? 1 : 0) - (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow) ? 1 : 0));
                if (direction == Vector2.zero) direction = pointerDirection;
                bool running = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
                MoveFree(direction.normalized * (running ? 4.8f : 3f) * Mathf.Min(Time.deltaTime, .1f));
                if (state.mode == "world" && Input.GetKeyDown(KeyCode.E)) Interact();
            }
            else if (state.mode == "battle")
            {
                if (Input.GetKeyDown(KeyCode.LeftArrow)) selected = (selected + 4) % 5;
                if (Input.GetKeyDown(KeyCode.RightArrow)) selected = (selected + 1) % 5;
                if (Input.GetKeyDown(KeyCode.Q)) CycleTarget(-1);
                if (Input.GetKeyDown(KeyCode.E)) CycleTarget(1);
                if (Input.GetKeyDown(KeyCode.Alpha1)) Queue(1, null);
                if (Input.GetKeyDown(KeyCode.Alpha2)) Queue(2, null);
                if (Input.GetKeyDown(KeyCode.R)) RepeatOrders();
                if (Input.GetKeyDown(KeyCode.G)) QueueAllGuards();
                if (Input.GetKeyDown(KeyCode.Return)) Resolve();
            }
            else if (state.mode == "story" && Input.GetKeyDown(KeyCode.Space)) forceReveal = true;
        }
        void NewGame() { combatFx.Clear(); effectEnd = 0; journalOpen = combosOpen = bagOpen = slotsOpen = settingsOpen = false; retryState = null; nextChatter = chatterUntil = 0; state = AdventureState.New(Environment.TickCount); state.difficulty = newDifficulty; menu = ""; log.Clear(); selected = target = 0; }
        void Save()
        {
            if (state == null || suppressSave || state.mode == "over") return;
            state.savedAt = DateTime.UtcNow.ToString("o");
            try { AdventureSave.Write(SavePath, state); notice = "スロット " + activeSlot + " にセーブしました。"; }
            catch (Exception e) { notice = "保存できませんでした: " + e.Message; Debug.LogException(e); }
        }
        void Load() { LoadFrom(SavePath); }
        void LoadFrom(string path)
        {
            try
            {
                bool recovered; var candidate = AdventureSave.Read(path, out recovered);
                if (candidate.mode == "story" && !story.Any(n => n.id == candidate.storyId)) throw new InvalidDataException("会話が見つかりません。");
                if (candidate.orders.Any(o => o != null && (o.action == 3 || o.action == 4) && !skills.Any(k => k.name == o.skill))) throw new InvalidDataException("予約魔法が見つかりません。");
                string[] oldNames = { "スライム", "ゴブリン", "ウルフ", "スケルトン", "ゴーレム", "グール", "ナイト", "ウィッチ", "オーク", "ドラゴン" };
                string[] newImages = { "enemy_slime", "enemy_goblin", "enemy_wolf", "enemy_skeleton", "enemy_golem", "enemy_ghoul", "enemy_knight", "enemy_witch", "enemy_orc", "enemy_dragon" };
                foreach (var e in candidate.enemies) { int artIndex = Array.IndexOf(oldNames, e.name); if (artIndex >= 0) e.image = newImages[artIndex]; else if (candidate.bossBattle && ReferenceEquals(e, candidate.enemies[0])) e.image = BossArt(candidate.floor); else if (e.name == "竜門の護衛") e.image = "enemy_knight"; }
                combatFx.Clear(); effectEnd = 0; journalOpen = combosOpen = bagOpen = slotsOpen = false; storyScroll = Vector2.zero; nextChatter = chatterUntil = 0; pointerDirection = Vector2.zero;
                state = candidate; retryState = null; settingsOpen = false; menu = ""; selected = target = healTarget = 0; log.Clear();
                notice = recovered ? "バックアップから復旧しました。" : "冒険を再開しました。";
            }
            catch (Exception e) { notice = "読み込めませんでした: " + e.Message; }
        }
        void Message(string text) { log.Add(text); if (log.Count > 6) log.RemoveAt(0); }
        void BeginBattle(int cell, bool boss)
        {
            retryState = JsonUtility.ToJson(state);
            previousOrders = null; animatedBars.Clear();
            if (boss) AutoSave();
            state.combo = 0; state.rewardBattle = false; combosOpen = false;
            state.comboReadyRound = 0;
            state.battleCell = cell; state.bossBattle = boss; state.round = 0; state.mode = "battle";
            state.enemies.Clear(); selected = target = 0;
            int band = (state.floor - 1) / 10;
            var names = new[] { "スライム", "ゴブリン", "ウルフ", "スケルトン", "ゴーレム", "グール", "ナイト", "ウィッチ", "オーク", "ドラゴン" };
            var encounterRng = new System.Random(unchecked(state.seed + state.floor * 7919 + state.encounterCount * 31));
            int count = boss ? 1 : 1 + encounterRng.Next(Math.Min(3, 1 + band / 3));
            if (!boss && band >= 3 && state.encounterCount % 3 == 0) count = Math.Max(2, count);
            int previousSpecies = -1;
            for (int i = 0; i < count; i++)
            {
                int species = boss ? Math.Min(9, band) : Math.Min(9, Math.Max(0, band + encounterRng.Next(state.floor < 6 ? 2 : 3)));
                if (!boss) { var pool = EncounterSpecies[band]; species = pool[(encounterRng.Next(pool.Length) + i) % pool.Length]; if (i > 0 && species == previousSpecies) species = pool[(Array.IndexOf(pool, species) + 1) % pool.Length]; }
                var entry = catalog.First(e => e.name == names[species]);
                int hp = EnemyHealth(boss ? 260 + state.floor * 30 : entry.hp * 3 / 2 + state.floor * 3);
                string art = "enemy_" + new[] { "slime", "goblin", "wolf", "skeleton", "golem", "ghoul", "knight", "witch", "orc", "dragon" }[species];
                state.enemies.Add(new Actor(boss ? BossNames[band] : entry.name, boss ? BossArt(state.floor) : art, hp, 0, EnemyAttack(boss ? 12 + state.floor * 3 / 5 : entry.attack + state.floor / 2), entry.defense));
                previousSpecies = species;
            }
            ResetOrders(); Message(boss ? "守護者が立ちはだかった。大技の予告に注意！" : "敵が現れた。全員の行動を予約しよう。");
            ShowMoment(boss ? "守護者との戦い" : "敵と遭遇", boss ? BossNames[band] : "仲間の行動を選ぼう", true);
        }
        void ResetOrders() { state.orders = Enumerable.Range(0, 5).Select(i => new Order()).ToList(); }
        void CycleTarget(int delta)
        {
            if (state.enemies.Count == 0) return;
            for (int i = 0; i < state.enemies.Count; i++)
            { target = (target + delta + state.enemies.Count) % state.enemies.Count; if (state.enemies[target].hp > 0) return; }
        }
        bool AllowedSkill(Actor actor, SkillEntry skill)
        { return skill.unlock <= state.level && (skill.heal > 0 ? actor.name == "勇者" || actor.name == "僧侶" : actor.name == "勇者" || actor.name == "魔法使い"); }
        void Queue(int action, SkillEntry skill)
        {
            var actor = state.party[selected]; if (actor.hp <= 0) return;
            if (skill != null && (!AllowedSkill(actor, skill) || actor.mp < SkillCost(actor, skill))) return;
            if (action == 4 && !HealUseful(healTarget)) { notice = "回復が必要な生存中の仲間を選んでください。戦闘不能には蘇生の羽を使います。"; return; }
            if (action != 2 && action != 4 && state.enemies[target].hp <= 0) CycleTarget(1);
            if (state.combo > 0 && ComboActors(state.combo - 1).Contains(selected)) CancelCombo();
            state.orders[selected] = new Order { action = action, target = action == 4 ? healTarget : target, skill = skill == null ? null : skill.name };
            for (int i = 1; i <= 5; i++) { int next = (selected + i) % 5; if (state.party[next].hp > 0 && state.orders[next].action == 0) { selected = next; break; } }
        }
        public void Resolve()
        {
            if (state.mode != "battle" || EffectsBusy || Modal) return;
            if (state.party.Where((a, i) => a.hp > 0 && state.orders[i].action == 0).Any()) { notice = "生きている仲間全員の行動を予約してください。"; return; }
            Tutorial("battle"); notice = "";
            RememberOrders();
            state.turnsTaken++;
            foreach (var a in state.party) a.guarding = false;
            for (int i = 0; i < 5; i++) if (state.party[i].hp > 0 && state.orders[i].action == 2) state.party[i].guarding = true;
            foreach (var a in state.party) if (a.hp > 0 && a.poison > 0) { int damage = Math.Max(3, a.maxHp / 20); a.hp = Math.Max(0, a.hp - damage); a.poison--; AddFx(true, state.party.IndexOf(a), "毒−" + damage, 0); }
            int comboUsed = ResolveCombo();
            for (int i = 0; i < 5; i++)
            {
                if (comboUsed > 0 && ComboActors(comboUsed - 1).Contains(i)) continue;
                var a = state.party[i]; if (a.hp <= 0) continue;
                var o = state.orders[i]; if (o.action == 0) continue;
                if (o.action == 2) { Message(a.name + "は防御。"); continue; }
                if (o.action == 5) { if (!UseItem(int.Parse(o.skill.Substring(5)), o.target)) Message("対象の状態が変わったため、どうぐを使わなかった。"); continue; }
                AddFx(true, i, o.action == 4 ? "祈り" : o.action == 3 ? "魔法" : "攻撃", o.action == 4 ? 1 : 2);
                SkillEntry skill = o.action == 3 || o.action == 4 ? skills.First(k => k.name == o.skill) : null;
                if (skill != null) { if (a.mp < SkillCost(a, skill)) continue; a.mp -= SkillCost(a, skill); }
                if (o.action == 4)
                {
                    var ally = state.party[o.target]; if (ally.hp <= 0) { Message("ヒールは戦闘不能を蘇生できない。"); continue; }
                    int healed = Math.Min(HealPower(a, skill), ally.maxHp - ally.hp); ally.hp += healed; AddFx(true, o.target, "+" + healed, 1); Message(a.name + " → " + ally.name + " HP +" + healed); continue;
                }
                int hit = state.enemies[o.target].hp > 0 ? o.target : state.enemies.FindIndex(e => e.hp > 0); if (hit < 0) break;
                if (!state.bossBattle && skill == null && state.round % 3 == 0)
                {
                    int cover = state.enemies.FindIndex(e => e.hp > 0 && NormalRole(e) == 2);
                    if (cover >= 0 && cover != hit) { Message(state.enemies[cover].name + "が仲間をかばった。魔法は直接狙える。"); hit = cover; }
                }
                var enemy = state.enemies[hit]; int defense = a.weapon > 0 && a.weaponEffect == 1 ? enemy.defense / 2 : enemy.defense;
                int damage = Math.Max(1, (skill == null ? AttackStat(a) - defense : SpellPower(a, skill)));
                if (!IsRootBoss(enemy) && NormalRole(enemy) == 2 && state.round % 3 == 0 && skill == null) damage = Math.Max(1, damage * (a.weapon > 0 && a.weaponEffect == 1 ? 80 : 55) / 100);
                if (state.bossBattle && state.round % 3 == 2) damage = damage * 3 / 2;
                if (state.bossBattle && ReferenceEquals(enemy, state.enemies[0]) && state.round % 3 == 0 && state.floor == 30 && skill == null) damage = Math.Max(1, damage / 2);
                if (state.bossBattle && ReferenceEquals(enemy, state.enemies[0]) && state.round % 3 == 0 && state.floor == 80 && skill != null) { int reflected = Math.Max(1, damage / 3); a.hp = Math.Max(0, a.hp - reflected); AddFx(true, i, "反射−" + reflected, 0); damage /= 2; }
                int magicKind = skill == null ? 0 : skill.name.Contains("ポイズン") ? 5 : skill.name.Contains("雷") || skill.name.Contains("サンダー") ? 4 : 3;
                AddFx(false, hit, "−" + damage, magicKind); enemy.hp = Math.Max(0, enemy.hp - damage); Message(a.name + " → " + enemy.name + " " + damage);
                if (enemy.hp == 0 && skill == null && a.weapon > 0 && a.weaponEffect == 2) { a.mp = Math.Min(a.maxMp, a.mp + 3); AddFx(true, i, "吸魔＋3", 2); }
                // Deterministic status rolls survive mid-battle reloads.
                if (skill != null && new System.Random(unchecked(state.seed + state.floor * 1009 + state.round * 31 + i)).NextDouble() < skill.poison_chance) enemy.poison = 3;
                if (skill != null && new System.Random(unchecked(state.seed + state.round * 433 + i)).NextDouble() < skill.paralyze_chance) enemy.guarding = true;
            }
            foreach (var e in state.enemies.ToArray())
            {
                if (e.hp <= 0) continue;
                if (e.poison > 0) { int tick = Math.Max(3, e.maxHp / 12); e.hp = Math.Max(0, e.hp - tick); e.poison--; AddFx(false, state.enemies.IndexOf(e), "毒−" + tick, 0); }
                if (e.hp <= 0) continue;
                if (e.guarding) { e.guarding = false; Message(e.name + "は麻痺で動けない。"); continue; }
                EnemyTurn(e, comboUsed);
            }
            foreach (var a in state.party) if (a.slow > 0) a.slow--;
            if (state.enemies.Any(e => e.hp > 0) && state.party.Any(a => a.hp > 0 && a.hp < a.maxHp * .35f)) React("hurt");
            if (state.enemies.All(e => e.hp <= 0))
            {
                state.battlesWon++;
                if (state.bossBattle) { state.Current.defeated.Add(state.battleCell); state.Current.tiles[state.battleCell] = 0; }
                state.ResetEncounter();
                if (state.bossBattle) state.Current.bossDefeated = true;
                int oldLevel = state.level, rewardGold = 15 + state.floor * 4, rewardExp = 15 + state.floor * 3;
                state.gold += rewardGold; state.experience += rewardExp;
                while (state.experience >= state.level * 35)
                {
                    state.experience -= state.level * 35; state.level++;
                    foreach (var a in state.party) { a.maxHp += 9; a.hp = Math.Min(a.maxHp, a.hp + 25); a.attack += 3; a.defense += 1; a.maxMp += 4; a.mp = Math.Min(a.maxMp, a.mp + 10); }
                    Message("レベル " + state.level + "！ 新しい魔法を確認しよう。");
                }
                foreach (var a in state.party.Where(a => a.hp > 0)) a.mp = Math.Min(a.maxMp, a.mp + (state.bossBattle ? 8 : 3));
                state.personality[0] = Math.Min(100, state.personality[0] + 1); state.mode = "world"; Message("勝利！ 宝箱と補給地点を探そう。");
                if (state.rewardBattle) { int extra = 80 + state.floor * 5; state.gold += extra; rewardGold += extra; foreach (var a in state.party) { a.maxMp += 2; a.mp = Math.Min(a.maxMp, a.mp + 2); } state.rewardBattle = false; Message("封印の宝箱を獲得！ 金貨と全員の最大MP＋2。"); }
                state.goldEarned += rewardGold;
                ShowMoment(state.level > oldLevel ? "勝利！ レベル " + state.level + " に成長" : "勝利！", "+" + rewardGold + " G  /  経験値 +" + rewardExp + "  /  MP回復");
                React(state.bossBattle ? "boss" : state.party.Any(a => a.hp < a.maxHp * .35f) ? "hurt" : "victory");
                if (state.bossBattle) BossConversation();
            }
            else if (state.party.All(a => a.hp <= 0)) state.mode = "over";
            else { state.round++; ResetOrders(); }
        }
        void Choose(StoryChoice choice)
        {
            if (state == null || state.mode != "story" || choice == null) return;
            var said = story.FirstOrDefault(n => n.id == state.storyId);
            if (said == null || !said.choices.Contains(choice)) return;
            foreach (string effect in (choice.effect ?? "").Split('|')) if (!ApplyJourneyEffect(effect)) return;
            storyScroll = Vector2.zero;
            string[] axes = { "bravery", "morality", "compassion", "honor", "greed", "cunning" };
            foreach (var effect in (choice.effect ?? "").Split('|'))
            {
                for (int i = 0; i < axes.Length; i++) if (effect.StartsWith(axes[i]))
                { int delta; if (int.TryParse(effect.Substring(axes[i].Length), out delta)) state.personality[i] = Math.Max(-100, Math.Min(100, state.personality[i] + delta)); }
                if (effect.StartsWith("story_flag=")) { string flag = effect.Substring(11); if (!state.flags.Contains(flag)) state.flags.Add(flag); }
                if (effect.StartsWith("stat_type=") && state.build == "balanced")
                {
                    state.build = effect.Substring(10);
                    if (state.build == "attack") state.party[0].attack += 5;
                    if (state.build == "defense") state.party[0].defense += 4;
                    if (state.build == "magic") { state.party[0].maxMp += 20; state.party[0].mp += 20; }
                }
            }
            RecordDialogue(said.speaker, said.text, choice.text);
            if (!state.flags.Contains("seen:" + state.storyId)) state.flags.Add("seen:" + state.storyId);
            if (choice.next == "__ENDING__") { state.mode = "clear"; state.storyExploration = false; AutoSave(); }
            else if (!string.IsNullOrEmpty(choice.next) && story.Any(n => n.id == choice.next)) state.storyId = choice.next;
            else FinishStory();
        }
        string OrderText(int i)
        {
            if (state.party[i].hp <= 0) return "戦闘不能";
            if (state.combo > 0 && ComboActors(state.combo - 1).Contains(i)) return "連携：" + ComboNames[state.combo - 1] + (state.combo == 1 ? " → 敵" + (state.comboTarget + 1) : "");
            var o = state.orders[i]; if (o.action == 0) return "未予約";
            if (o.action == 5) return ItemNames[int.Parse(o.skill.Substring(5))] + " → " + state.party[o.target].name;
            return o.action == 2 ? "防御" : (o.action == 1 ? "攻撃" : o.skill) + " → " + (o.action == 4 ? state.party[o.target].name : "敵" + (o.target + 1));
        }
    }
}
















