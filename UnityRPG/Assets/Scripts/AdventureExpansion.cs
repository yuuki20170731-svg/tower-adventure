using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        public bool suppressSave;
        public string saveDirectoryOverride;
        int activeSlot = 1;
        bool bagOpen, slotsOpen, drawingExpansion;
        int bagTab, bagActor, itemTarget, confirmSlot;
        string[] slotSummaries = new string[4];
        bool[] slotAvailable = new bool[4];
        static readonly string[] ItemNames = { "薬草", "魔水", "蘇生の羽" };
        static readonly int[] ItemPrices = { 20, 35, 90 };
        static readonly string[] GearNames = { "武器", "防具", "魔導具" };
        static readonly int[] GearPrices = { 60, 180, 480 };
        static readonly string[] BossNames = { "星鎧の番人", "影牙の獣", "偽令の衛兵", "根の歌い手", "記憶炉の守り", "星守の鏡", "氷書の司書", "反照の機関", "竜門の番兵", "アビス" };
        static readonly string[] BossImages = { "boss", "enemy_wolf", "enemy_knight", "enemy_witch", "enemy_golem", "boss", "enemy_witch", "enemy_golem", "enemy_dragon", "boss_final" };
        string BossArt(int floor) { return BossImages[(floor - 1) / 10]; }
        bool Modal { get { return journalOpen || combosOpen || bagOpen || slotsOpen || settingsOpen; } }
        string SlotPath(int slot)
        {
            string directory = string.IsNullOrEmpty(saveDirectoryOverride) ? Application.persistentDataPath : saveDirectoryOverride;
            return Path.Combine(directory, slot == 0 ? "adventure-auto.json" : slot == 1 ? "adventure-v1.json" : "adventure-slot" + slot + ".json");
        }
        void AutoSave()
        {
            if (suppressSave || state == null || state.mode == "over") return;
            try { state.savedAt = DateTime.UtcNow.ToString("o"); AdventureSave.Write(SlotPath(0), state); }
            catch (Exception e) { notice = "自動保存できませんでした: " + e.Message; }
        }
        void OpenSlots()
        {
            slotsOpen = true; journalOpen = combosOpen = bagOpen = settingsOpen = false; pointerDirection = Vector2.zero; confirmSlot = 0;
            RefreshSlots();
        }
        void RefreshSlots()
        {
            for (int i = 0; i < 4; i++)
            {
                slotAvailable[i] = false;
                try {
                    if (!File.Exists(SlotPath(i)) && !File.Exists(SlotPath(i) + ".bak")) { slotSummaries[i] = "空きスロット"; continue; }
                    bool backup; var s = AdventureSave.Read(SlotPath(i), out backup); DateTime time;
                    string date = DateTime.TryParse(s.savedAt, null, System.Globalization.DateTimeStyles.RoundtripKind, out time) ? time.ToLocalTime().ToString("yyyy/MM/dd HH:mm") : "以前のセーブ（日時なし）";
                    string mode = s.mode == "story" ? "会話中" : s.mode == "battle" ? "戦闘中 / " + (s.round + 1) + "ターン目" : s.mode == "town" ? "補給地点" : s.mode == "clear" ? "踏破済み" : s.mode == "over" ? "全滅" : "探索中";
                    slotSummaries[i] = s.floor + "階 / Lv " + s.level + " / " + mode + " / " + s.gold + "G\n" + date + " / プレイ " + (int)(s.playSeconds / 60) + "分" + (backup ? " / バックアップ復旧" : "");
                    slotAvailable[i] = true;
                } catch (Exception) { slotSummaries[i] = "読み込めません。別の枠・自動保存を選んでください。"; }
            }
        }
        void RememberSlot(int slot)
        {
            if (slot == 0) return;
            activeSlot = slot;
            if (string.IsNullOrEmpty(saveDirectoryOverride) && !suppressSave) PlayerPrefs.SetInt("AdventureSlot", slot);
        }
        void Tutorial(string step) { if (!state.flags.Contains("help:" + step)) state.flags.Add("help:" + step); }
        string TutorialText()
        {
            if (state.flags.Contains("help:skip")) return "";
            if (!state.flags.Contains("help:move")) return "操作案内 1 / WASDで歩こう。\nShiftを押すとダッシュできる。";
            if (!state.flags.Contains("help:talk")) return "操作案内 2 / 会話の印を探そう。\n近くでE。選んだ言葉で返答が変わる。";
            if (!state.flags.Contains("help:battle")) return "操作案内 3 / 歩くと敵に出会う。\n仲間の行動を予約し、Enterで実行。";
            if (!state.flags.Contains("help:combo")) return ComboUnlocked(0) ? "操作案内 4 / 戦闘で連携技を選ぼう。\n参加者以外の仲間にも行動を予約。" : "操作案内 4 / 仲間の願いを叶えよう。\n記録Jで確認し、習得後は連携技へ。";
            return "";
        }
        int AttackStat(Actor a) { return (a.attack + a.weapon * 5 + state.workshop[0] * 2) * (a.slow > 0 ? 3 : 4) / 4; }
        int DefenseStat(Actor a) { return a.defense + a.armor * 3 + state.workshop[1] * 2 + (state.flags.Contains("ward:" + state.floor) ? 6 : 0); }
        int SkillCost(Actor a, SkillEntry k) { return Math.Max(1, k.cost - a.charm * 2 - (a.charm > 0 && a.charmEffect == 2 && state.mode == "battle" && state.round == 0 ? 2 : 0)); }
        int SpellPower(Actor a, SkillEntry k) { return k.power + a.attack / 2 + a.charm * 6 + state.workshop[2] * 4; }
        int HealPower(Actor a, SkillEntry k) { return (k.heal + a.attack / 2 + a.charm * 8 + state.workshop[2] * 4) * (a.charm > 0 && a.charmEffect == 1 ? 120 : 100) / 100; }
        int GearTier(Actor a, int kind) { return kind == 0 ? a.weapon : kind == 1 ? a.armor : a.charm; }
        void Equip(int actor, int kind, int tier)
        {
            if (state.mode == "battle" || actor < 0 || actor >= 5 || kind < 0 || kind > 2 || tier < 0 || tier > 3) return;
            var a = state.party[actor]; int old = GearTier(a, kind); if (old == tier) return;
            int index = kind * 3 + tier - 1;
            if (tier > 0 && state.gearOwned[index] == 0) return;
            if (tier > 0) state.gearOwned[index]--;
            if (old > 0) state.gearOwned[kind * 3 + old - 1]++;
            if (kind == 0) a.weapon = tier; else if (kind == 1) a.armor = tier; else a.charm = tier;
            Message(a.name + "の" + GearNames[kind] + "を変更した。基礎能力は保持される。");
        }
        bool Buy(int kind, int tier)
        {
            if (state.mode != "town" || kind < 0 || kind > 5 || kind >= 3 && (tier < 1 || tier > 3)) return false;
            int price = kind < 3 ? ItemPrices[kind] : GearPrices[tier - 1];
            int index = kind < 3 ? kind : (kind - 3) * 3 + tier - 1;
            var owned = kind < 3 ? state.items : state.gearOwned;
            if (state.gold < price || owned[index] >= 99 || (kind >= 3 && tier > (state.floor >= 51 ? 3 : state.floor >= 21 ? 2 : 1))) return false;
            state.gold -= price; owned[index]++; Message("購入した。残り " + state.gold + "G。"); return true;
        }
        int ReservedItems(int item, int exceptActor = -1)
        { return state.orders.Where((o, p) => p != exceptActor && state.party[p].hp > 0 && o.action == 5 && o.skill == "item:" + item).Count(); }
        bool ItemUseful(int item, int recipient)
        {
            var a = state.party[recipient];
            return item == 2 ? a.hp == 0 : a.hp > 0 && (item == 0 ? a.hp < a.maxHp || a.poison > 0 : a.mp < a.maxMp);
        }
        bool UseItem(int item, int recipient)
        {
            if (state.items[item] <= 0 || !ItemUseful(item, recipient)) return false;
            state.items[item]--; var a = state.party[recipient];
            state.itemsUsed++;
            if (item == 0) { int before = a.hp; a.hp = Math.Min(a.maxHp, a.hp + Math.Max(65, a.maxHp * 35 / 100)); a.poison = 0; AddFx(true, recipient, "+" + (a.hp - before), 1); }
            if (item == 1) { int before = a.mp; a.mp = Math.Min(a.maxMp, a.mp + Math.Max(25, a.maxMp * 30 / 100)); AddFx(true, recipient, "MP＋" + (a.mp - before), 1); }
            if (item == 2) { a.hp = Math.Max(1, a.maxHp / 2); a.poison = a.slow = 0; AddFx(true, recipient, "蘇生", 1); }
            Message(ItemNames[item] + " → " + a.name); return true;
        }
        void SelectItem(int item)
        {
            if (!ItemUseful(item, itemTarget)) { notice = "効果のある対象を選んでください。蘇生の羽は戦闘不能の仲間に使えます。"; return; }
            if (state.mode != "battle") { UseItem(item, itemTarget); return; }
            if (state.party[selected].hp <= 0 || state.items[item] <= ReservedItems(item, selected)) return;
            if (state.combo > 0 && ComboActors(state.combo - 1).Contains(selected)) CancelCombo();
            state.orders[selected] = new Order { action = 5, skill = "item:" + item, target = itemTarget };
            for (int i = 1; i <= 5; i++) { int p = (selected + i) % 5; if (state.party[p].hp > 0 && state.orders[p].action == 0) { selected = p; break; } }
            bagOpen = false;
        }
        string BossIntent()
        {
            if (state.enemies.Count > 0 && state.enemies[0].hp <= 0) return "守護者は倒れた。残った護衛を倒そう。";
            int band = state.floor / 10 - 1, phase = state.round % 3;
            string[] preparations = { "力を溜める。次は全体大技！", "低HPの仲間を狙う。回復や盾で備えよう。", "盾を構える。通常攻撃半減、魔法は有効。", "毒の種を溜める。次は防御で毒を避ける。", "MPを吸う準備。次は防御で吸収を軽減。", "記憶を回復する。魔法攻撃で回復を阻止。", "凍気を溜める。次は防御で弱体を防ぐ。", "魔法を反射する。通常攻撃で攻めよう。", "護衛を呼ぶ。全体攻撃で数を減らそう。", "星を集める。半分以下では大技が強化！" };
            string[] attacks = { "全体大技！ 全員防御で軽減。", "傷ついた仲間へ飛びかかる！", "盾を投げる！ 防御で受け止めよう。", "全体毒攻撃！ 防御・薬草で対処。", "全体攻撃＋MP吸収！ 防御で軽減。", "鏡の大技！ 防御して反撃を待つ。", "全体攻撃＋攻撃低下！ 防御で防ぐ。", "機関の大技！ 防御して反照が消えるのを待つ。", "番兵の大技！ 護衛にも注意。", "星の奔流！ 防御と回復を優先。" };
            return BossNames[band] + " / " + (phase == 0 ? preparations[band] : phase == 1 ? attacks[band] : "大技後の隙！ 与えるダメージ1.5倍。");
        }
        void EnemyTurn(Actor e, int comboUsed)
        {
            bool boss = state.bossBattle && ReferenceEquals(e, state.enemies[0]); int band = state.floor / 10 - 1, phase = state.round % 3;
            int role = boss ? 0 : NormalRole(e);
            if (role == 1 && phase != 1)
            {
                var wounded = state.enemies.Where(a => a.hp > 0 && a.hp < a.maxHp * .75f).OrderBy(a => (float)a.hp / a.maxHp).FirstOrDefault();
                if (wounded != null) { int heal = Math.Min(Math.Max(8, wounded.maxHp / 10), wounded.maxHp - wounded.hp); wounded.hp += heal; AddFx(false, state.enemies.IndexOf(wounded), "+" + heal, 1); Message(e.name + "が味方を " + heal + " 回復。回復役を先に狙おう。"); return; }
            }
            if (role == 3 && phase == 0) { Message(EnemyIntent(e)); AddFx(false, state.enemies.IndexOf(e), "溜め", 2); return; }
            if (boss && phase == 0)
            {
                if (band == 5) { int heal = state.orders.Any(o => o.action == 3) ? 0 : e.maxHp / 20; e.hp = Math.Min(e.maxHp, e.hp + heal); AddFx(false, 0, heal == 0 ? "阻止" : "+" + heal, 1); Message(heal == 0 ? "魔法で鏡の回復を阻止した！" : "鏡が記憶を回復した。"); }
                if (band == 8 && state.enemies.Count(a => a.hp > 0) < 3) { state.enemies.Add(new Actor("竜門の護衛", "enemy_knight", EnemyHealth(45 + state.floor * 2), 0, EnemyAttack(12 + state.floor / 4), 5)); Message("竜門の護衛が現れた！"); }
                Message(BossIntent()); return;
            }
            var living = state.party.Where(a => a.hp > 0).ToArray(); if (living.Length == 0) return;
            Actor single = comboUsed == 1 && state.party[1].hp > 0 ? state.party[1] : boss && band == 1 ? living.OrderBy(a => (float)a.hp / a.maxHp).First() : living[(state.round + state.floor) % living.Length];
            var victims = boss && phase == 1 && band != 1 && band != 2 ? living : new[] { single };
            AddFx(false, state.enemies.IndexOf(e), "攻撃", 2);
            foreach (var victim in victims)
            {
                float factor = boss && phase == 1 ? band == 1 ? 2f : 1.6f : 1f;
                if (role == 3 && phase == 1) factor = 1.4f;
                if (boss && band == 9 && e.hp < e.maxHp / 2) factor *= 1.2f;
                int damage = Math.Max(1, (int)(e.attack * factor) - DefenseStat(victim));
                bool magic = role == 1 || e.image == "enemy_ghoul" || boss && (band == 4 || band == 5 || band == 6 || band == 7 || band == 9);
                if (magic && victim.armor > 0 && victim.armorEffect == 2) damage = Math.Max(1, damage * 80 / 100);
                if (victim.guarding) damage = Math.Max(1, damage / (comboUsed == 1 && state.flags.Contains("path_gald_team") && ReferenceEquals(victim, state.party[1]) ? 5 : 4));
                victim.hp = Math.Max(0, victim.hp - damage); int index = state.party.IndexOf(victim); AddFx(true, index, "−" + damage, 0); Message(e.name + " → " + victim.name + " " + damage);
                if (boss && phase == 1)
                {
                    if (band == 3 && !victim.guarding) GivePoison(victim, 3);
                    if (band == 4 || band == 9) { int lost = Math.Min(victim.mp, victim.guarding ? 3 : band == 9 ? 6 : 12); victim.mp -= lost; AddFx(true, index, "MP−" + lost, 2); }
                    if (band == 6 && !victim.guarding) victim.slow = 2;
                }
                if (role == 4 && phase == 1 && !victim.guarding) GivePoison(victim, 2);
            }
        }
        class CombatFx { public bool ally, played; public int index, kind; public string text; public float start; }
        readonly List<CombatFx> combatFx = new List<CombatFx>();
        float effectEnd; bool battleEffects;
        AudioSource effectAudio;
        AudioClip[] effectSounds;
        Texture2D glow;
        bool EffectsBusy { get { return Application.isPlaying && Time.unscaledTime < effectEnd || TransitionBusy; } }
        void InitEffects()
        {
            effectAudio = gameObject.AddComponent<AudioSource>(); effectAudio.volume = .18f; effectSounds = new AudioClip[3];
            for (int k = 0; k < 3; k++) { int count = 6600; var samples = new float[count]; for (int i = 0; i < count; i++) { float t = i / 44100f; samples[i] = Mathf.Sin(t * (k == 0 ? 160 : k == 1 ? 660 : 390) * Mathf.PI * 2) * Mathf.Exp(-t * 28); } effectSounds[k] = AudioClip.Create("battle-" + k, count, 1, 44100, false); effectSounds[k].SetData(samples, 0); }
            glow = new Texture2D(64, 64); var colors = new Color[4096]; for (int y = 0; y < 64; y++) for (int x = 0; x < 64; x++) colors[y * 64 + x] = new Color(1, 1, 1, Mathf.Clamp01(1 - Vector2.Distance(new Vector2(x, y), new Vector2(31.5f, 31.5f)) / 32)); glow.SetPixels(colors); glow.Apply();
        }
        void AddFx(bool ally, int index, string text, int kind)
        {
            if (!Application.isPlaying || reducedEffects) return;
            if (!EffectsBusy) { combatFx.Clear(); effectEnd = Time.unscaledTime; battleEffects = state.mode == "battle"; }
            float start = combatFx.Count == 0 ? Time.unscaledTime : combatFx.Last().start + .085f;
            combatFx.Add(new CombatFx { ally = ally, index = index, text = text, kind = kind, start = start }); effectEnd = start + .65f;
        }
        void PlayEffects()
        { foreach (var fx in combatFx) if (!fx.played && Time.unscaledTime >= fx.start) { fx.played = true; if (effectAudio != null) effectAudio.PlayOneShot(effectSounds[Math.Min(2, fx.kind)]); } }
        float FxMotion(bool ally, int index)
        { return combatFx.Where(f => f.ally == ally && f.index == index && Time.unscaledTime >= f.start && Time.unscaledTime < f.start + .4f).Sum(f => Mathf.Sin((Time.unscaledTime - f.start) * 35) * (f.kind == 2 ? 10 : 4)); }
        void DrawEffects()
        {
            if (!EffectsBusy) return;
            foreach (var fx in combatFx)
            {
                float age = Time.unscaledTime - fx.start; if (age < 0 || age > .65f) continue;
                float x = fx.ally ? battleEffects ? 104 + fx.index * 102 : 176 + fx.index * 313 : 589 + 528f / state.enemies.Count * (fx.index + .5f);
                float y = fx.ally ? battleEffects ? 461 : 168 : 455;
                Color color = fx.kind == 0 ? new Color(1, .4f, .32f) : fx.kind == 1 ? Teal : fx.kind == 3 ? new Color(1, .57f, .18f) : fx.kind == 4 ? new Color(.55f, .8f, 1) : fx.kind == 5 ? new Color(.73f, .44f, 1) : Gold;
                var previous = GUI.color; GUI.color = new Color(color.r, color.g, color.b, (1 - age / .65f) * .8f);
                GUI.DrawTexture(new Rect(x - 65, y - 60, 130, 120), glow);
                if (fx.kind == 0) { var matrix = GUI.matrix; GUIUtility.RotateAroundPivot(-35, new Vector2(x, y)); GUI.DrawTexture(new Rect(x - 50, y - 2, 100, 5), Texture2D.whiteTexture); GUI.matrix = matrix; }
                if (fx.kind >= 3)
                {
                    for (int spark = 0; spark < 7; spark++)
                    {
                        float angle = spark * Mathf.PI * 2 / 7 + age * 2;
                        float radius = 18 + age * 65;
                        GUI.DrawTexture(new Rect(x + Mathf.Cos(angle) * radius - 5, y + Mathf.Sin(angle) * radius - age * 25 - 5, 10, 10), glow);
                    }
                    if (fx.kind == 4) { var matrix = GUI.matrix; GUIUtility.RotateAroundPivot(25, new Vector2(x, y)); GUI.DrawTexture(new Rect(x - 3, y - 57, 6, 110), Texture2D.whiteTexture); GUI.matrix = matrix; }
                }
                GUI.color = previous; var old = headingStyle.normal.textColor; var alignment = headingStyle.alignment; bool wrap = headingStyle.wordWrap;
                headingStyle.normal.textColor = color; headingStyle.alignment = TextAnchor.MiddleCenter; headingStyle.wordWrap = false;
                Text(Mathf.Max(30, x - 80), y - 32 - age * 60, 160, 45, fx.text, headingStyle);
                headingStyle.normal.textColor = old; headingStyle.alignment = alignment; headingStyle.wordWrap = wrap;
            }
        }
    }
}



