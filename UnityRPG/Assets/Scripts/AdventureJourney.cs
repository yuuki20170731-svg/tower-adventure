using System;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        static readonly string[] CompanionNames = { "ガルド", "ミナ", "リナ", "テオ" };
        static readonly string[] QuestKeys = { "gald", "mina", "rina", "theo" };
        static readonly int[] QuestFloors = { 12, 22, 42, 52 };
        static readonly string[] QuestTitles = { "届けられなかった名札", "妹の押し花", "森へ帰る道", "研究者の責任" };
        static readonly string[] ComboNames = { "盾と矢", "祈りの星灯り", "森の一斉射", "五人の灯り" };
        float chatterUntil, nextChatter;
        string chatterText = "", chatterPortrait = "";
        bool journalOpen, combosOpen, drawingJourneyOverlay;
        Vector2 journalScroll;
        int journalTab;

        bool QuestDone(int i) { return state.flags.Contains("quest_" + QuestKeys[i] + "_done"); }
        int AvailableQuest() { return Enumerable.Range(0, 4).Where(i => state.floor >= QuestFloors[i] && !QuestDone(i)).DefaultIfEmpty(-1).First(); }
        void AddJourneyStories()
        {
            string[] discoveries = {
                "壁の陰に、十階で見つけた名札と同じ紋章の箱があった。中には子供たちの名札と、ガルド宛ての手紙。『門の外で待っています』。ガルドは膝をつく。「俺を待っていたのか。誰も助からなかったと、決めつけていた」",
                "水路の奥で、花を挟んだ妹の手帳を見つけた。『姉さんは自分の痛みを隠す。今度は私が手を握りたい』。ミナはページを閉じられない。「あの子にまで、心配をかけてたんだね」",
                "折れた道標の裏に、母の歌と同じ模様がある。リナが瓦礫をどけると、谷へ続く避難路の地図が現れた。「森に戻れる人がいる。私たちの通った道を、次の人にも残そう」",
                "研究室の装置には、テオ自身の署名があった。燃料槽の向こうから、人の名前が聞こえる。「僕が改良した式だ。止めるだけじゃ、閉じ込めた人を返せない。今ここで、逆向きの式を書こう」"
            };
            string[] actions = { "名札を拾い、手紙の宛先を書き直す", "手帳を乾かし、ミナの言葉も書き添える", "道標を直して、帰り道を刻む", "装置を守りながら、逆転の式を完成させる" };
            string[] replies = {
                "ガルドは一枚ずつ名札を並べ、名前を声に出した。「数じゃない。一人ずつだ。俺の盾は、これから生きて帰る人のために使う」リナが隣に立つ。「盾の後ろからなら、私も遠くまで狙えるよ」",
                "ミナは初めて、手帳に自分の弱音を書いた。「私も、助けてほしかった」。テオが静かに杖を置く。「祈りと僕の灯りを重ねよう。今度は、君自身も守れるように」",
                "リナが最後の印を刻むと、道標に緑の光が戻った。「迷ったらここへ。私が残した矢印だから、外さないよ」。ガルドが笑う。「次は俺たちが、帰る人の目印になる番だな」",
                "逆転した装置から光が流れ、人の声が一つずつ解けていった。テオは自分の署名を消さない。「僕がしたことは残す。その隣に、直したことも書く」。四人は、最後の計算が終わるまで彼のそばにいた。"
            };
            string[] personalReplies = { "ガルドは君の手を握る。『俺の背中を、預けていいか。お前の言葉で、盾を上げる理由ができた』", "ミナは手帳を君に見せる。『私も頼るね。二人の灯りなら、もっと遠くへ届くと思う』", "リナは矢筒を軽く叩く。『私の帰り道を一緒に作ってくれた。次は、君の進みたい場所まで狙うよ』", "テオは眼鏡を外して答える。『僕のしたことを知っても、隣にいてくれた。君の選択を、僕も支えたい』" };
            var extra = new System.Collections.Generic.List<StoryNode>();
            for (int i = 0; i < 4; i++)
            {
                string id = "quest_" + QuestKeys[i];
                extra.Add(new StoryNode { id = id, chapter = "仲間の物語 / " + QuestTitles[i], speaker = CompanionNames[i], portrait = PartyArt[i + 1], text = discoveries[i], choices = new[] {
                    new StoryChoice { text = actions[i], effect = "compassion+2", next = id + "_reply" },
                    new StoryChoice { text = "仲間と手分けして、確実に仕上げる", effect = "honor+2", next = id + "_team" },
                    new StoryChoice { text = "今は探索に戻る。手掛かりは記録しておく", effect = "story_flag=hint_" + QuestKeys[i] }
                } });
                for (int branch = 0; branch < 2; branch++) extra.Add(new StoryNode {
                    id = id + (branch == 0 ? "_reply" : "_team"), chapter = "仲間の物語 / " + QuestTitles[i], speaker = CompanionNames[i], portrait = PartyArt[i + 1],
                    text = (branch == 0 ? "君は仲間の隣にしゃがみ、作業を始めた。\n\n" : "ガルドは周囲を守り、リナは先を確かめ、ミナとテオが手掛かりを整える。五人で、取り残された願いを形にした。\n\n") + replies[i] + (branch == 0 ? "\n\n" + personalReplies[i] + " 連携の威力・回復が強化される。" : "\n\n五人は作業を終え、誰が何を引き受けるかを決めた。『一人で抱えなくていい。これからも分け合おう』。連携の守り・効率・支援が強化される。"),
                    choices = new[] { new StoryChoice { text = "約束を交わす / 連携技「" + ComboNames[i] + "」を習得・強化", effect = "story_flag=quest_" + QuestKeys[i] + "_done|story_flag=bond_" + QuestKeys[i] + "|story_flag=path_" + QuestKeys[i] + (branch == 0 ? "_personal" : "_team") } }
                });
            }
            extra.Add(new StoryNode { id = "side_risk", chapter = "寄り道 / 封印された宝箱", speaker = "リナ", portrait = "ally_archer", text = "「鍵穴から、嫌な気配がするね。開ければ守り手が来る。でも、中の報酬は普通の箱より良さそう」。封印の向こうで何かが動く。今のHPとMPを確かめてから決めよう。", choices = new[] {
                new StoryChoice { text = "守り手と戦い、報酬を得る（勝利時、金貨と全員の最大MP＋2）", effect = "journey=risk" },
                new StoryChoice { text = "封印を解かず、探索に戻る" }
            } });
            extra.Add(new StoryNode { id = "side_traveler", chapter = "寄り道 / 立ち止まった旅人", speaker = "ミナ", portrait = "ally_priest", text = "壁にもたれた旅人は、帰り道を見失っていた。「まだ歩ける。でも、どこへ行けばいいのか……」。ミナが顔をのぞき込む。「一緒に地図を見よう。補給も少し分けられるよ」", choices = new[] {
                new StoryChoice { text = "30Gで補給を分ける（全員HP・MP回復、旅人を救助）", effect = "journey=supply" },
                new StoryChoice { text = "入口への道を教える（救助、入口までの経路を地図に記録）", effect = "journey=guide" },
                new StoryChoice { text = "あとで戻る" }
            } });
            extra.Add(new StoryNode { id = "side_memory", chapter = "寄り道 / 記憶の灯り", speaker = "テオ", portrait = "ally_mage", text = "小さな灯りから、誰かの暮らしの声がする。鍋の音、子供を呼ぶ名前、帰りを待つ歌。テオは灯りを両手で包む。「大きな歴史だけじゃない。こんな日々も、返していこう」", choices = new[] {
                new StoryChoice { text = "名前を記録し、灯りを解放する（全員MP＋8、地図の一部を開く）", effect = "journey=memory" },
                new StoryChoice { text = "今はそっとしておく" }
            } });
            story = story.Concat(extra).Concat(LandmarkStories()).ToArray();
        }
        void StartSideEvent(int cell)
        {
            int tile = state.Current.tiles[cell]; int quest = AvailableQuest();
            state.journeyCell = cell;
            if (tile == 13) { BeginStory("landmark_" + ((state.floor - 1) / 10)); return; }
            BeginStory(tile == 10 && quest >= 0 ? "quest_" + QuestKeys[quest] : tile == 10 ? "side_memory" : tile == 11 ? "side_risk" : "side_traveler");
        }
        bool ApplyJourneyEffect(string effect)
        {
            if (!effect.StartsWith("journey=")) return true;
            string kind = effect.Substring(8);
            if (kind == "ward" && state.gold < WardPrice()) { notice = "防護の修復には " + WardPrice() + "G必要です。地図の読み取りは無料です。"; return false; }
            if (kind == "supply" && state.gold < 30) { notice = "補給には30G必要です。道案内なら金貨は不要です。"; return false; }
            state.journeyOutcome = kind;
            return true;
        }
        void FinishJourneyEvent()
        {
            int cell = state.journeyCell;
            string kind = state.journeyOutcome ?? ""; state.journeyOutcome = "";
            bool quest = state.storyId.StartsWith("quest_") && QuestKeys.Any(k => state.storyId.StartsWith("quest_" + k) && state.flags.Contains("quest_" + k + "_done"));
            bool validCell = cell >= 0 && cell < state.Current.tiles.Length && state.Current.tiles[cell] >= 10;
            if (kind.Length == 0 && !quest) return;
            if (validCell) state.Current.tiles[cell] = 0;
            state.journeyCell = -1;
            if (kind == "risk") { BeginBattle(validCell ? cell : state.y * AdventureState.Width + state.x, false); state.rewardBattle = true; foreach (var enemy in state.enemies) { enemy.maxHp = enemy.maxHp * 5 / 4; enemy.hp = enemy.maxHp; enemy.attack += 3; } return; }
            if (kind == "supply") { state.gold -= 30; RecoverParty(); }
            if (kind == "ward") { state.gold -= WardPrice(); state.flags.Add("ward:" + state.floor); }
            if (kind == "survey") { foreach (int step in DungeonLayout.Path(state.Current, state.y * AdventureState.Width + state.x, state.Current.stairs)) state.Current.explored[step] = true; state.flags.Add("survey:" + state.floor); }
            if (kind == "ward" || kind == "survey") RecordDialogue("テオ", kind == "ward" ? "この階の防護が戻った。五人とも守り＋6だ。階を離れるまで続くよ。" : "階段までの道を記録したよ。迷った時に地図を見て。道中の敵には気を付けよう。");
            if (kind == "guide") foreach (int step in DungeonLayout.Path(state.Current, state.y * AdventureState.Width + state.x, state.Current.entrance)) state.Current.explored[step] = true;
            if (kind == "guide" || kind == "supply") { state.flags.Add("rescued:" + state.floor); state.personality[2] = Math.Min(100, state.personality[2] + 2); }
            if (kind == "memory")
            {
                foreach (var actor in state.party) actor.mp = Math.Min(actor.maxMp, actor.mp + 8);
                int[] distances = DungeonLayout.Distances(state.Current, state.y * AdventureState.Width + state.x);
                for (int i = 0; i < distances.Length; i++) if (distances[i] >= 0 && distances[i] <= 7) state.Current.explored[i] = true;
                state.flags.Add("memory:" + state.floor);
            }
            Message(quest ? "仲間の願いを叶え、連携技を習得した。旅の記録で確認できる。" : "寄り道の成果を旅の記録に残した。");
            if (!quest) React("rescue");
        }
        void RecoverParty() { foreach (var a in state.party) { a.hp = a.maxHp; a.mp = a.maxMp; a.poison = a.slow = 0; AddFx(true, state.party.IndexOf(a), "全回復", 1); } state.ResetEncounter(); }
        void React(string situation)
        {
            if (Time.unscaledTime < nextChatter) return;
            int variant = Math.Abs((state.floor + state.encounterCount + state.chatterCount++) % 3);
            string[] lines; int speaker;
            switch (situation)
            {
                case "chest": speaker = 2; lines = new[] { "開ける前に罠を見てね。私の勘より、鍵穴を信じよう。", "分け前は帰ってから。今は五人で使おう。", "宝より、無事に持って帰れる方が大事だよ。" }; break;
                case "hurt": speaker = 1; lines = new[] { "平気って言わなくていいよ。次の休憩で、私にも頼って。", "その傷、隠さないで。帰るまでが冒険だから。", "今は立ち止まってもいい。あなたを置いては進まないよ。" }; break;
                case "boss": speaker = 0; lines = new[] { "五人そろってるな。盾の傷より、そっちを確かめたい。", "乗り越えたな。強かったからじゃない。支え合えたからだ。", "深呼吸しよう。勝った後ほど、足元を見るんだ。" }; break;
                case "victory": speaker = 0; lines = new[] { "全員いるな。次の道へ進もう。", "傷があれば隠すなよ。休める場所を探そう。", "勝った後も周りを見よう。盾はまだ下ろさない。" }; break;
                case "rest": speaker = 3; lines = new[] { "計算も休憩しよう。温かいものを飲んでから考えるよ。", "みんなの声が聞こえる。今の灯りは、それで十分だ。", "次の道を地図に書いておこう。焦る必要はないよ。" }; break;
                case "floor": speaker = 2; lines = new[] { "入口を覚えた。次は階段だね。私が先を見るよ。", "ここは匂いが違う。前の階の思い込みは置いていこう。", "遠くへ行く前に周りを見よう。寄り道も、道のうち。" }; break;
                case "promise": speaker = 0; lines = new[] { "約束したからな。今度は、言葉の通りに動く。", "記録にも残してくれ。俺たちが選んだことだ。", "仲間に頼るのも、守ることの一つなんだな。" }; break;
                default: speaker = 1; lines = new[] { "誰かの帰り道を作れたね。私たちの道も、きっと続いてる。", "小さな声も聞き逃したくない。助けられてよかった。", "この出来事も手帳に書くね。忘れたくないから。" }; break;
            }
            chatterText = CompanionNames[speaker] + "「" + lines[variant] + "」"; chatterPortrait = PartyArt[speaker + 1];
            chatterUntil = Time.unscaledTime + 9; nextChatter = Time.unscaledTime + 18;
            Message(chatterText);
            RecordDialogue(CompanionNames[speaker], lines[variant]);
        }
        bool ComboUnlocked(int i) { return QuestDone(i) || i == 0 && state.flags.Contains("help:talk") && state.flags.Contains("help:battle"); }
        int ComboCost(int i) { return i == 3 ? 10 : state.flags.Contains("path_" + QuestKeys[i] + "_team") && (i == 1 || i == 2) ? 5 : 6; }
        int[] ComboActors(int i) { return i == 0 ? new[] { 1, 3 } : i == 1 ? new[] { 2, 4 } : i == 2 ? new[] { 0, 3 } : new[] { 0, 1, 2, 3, 4 }; }
        int ComboDamage(int i)
        {
            int damage = ComboActors(i).Sum(p => AttackStat(state.party[p])) + (i == 3 ? 45 : 18) + (state.flags.Contains("path_" + QuestKeys[i] + "_personal") ? i == 3 ? 30 : 12 : 0);
            if (i >= 2) damage = Math.Max(1, damage * 75 / 100);
            return state.bossBattle && state.round % 3 == 2 ? damage * 3 / 2 : damage;
        }
        int ComboHeal(int i) { return i == 3 ? 35 + (state.flags.Contains("path_theo_team") ? 20 : 0) : 45 + (state.flags.Contains("path_mina_personal") ? 15 : 0); }
        string ComboCondition(int i)
        {
            if (!ComboUnlocked(i)) return "仲間の専用イベントで習得";
            if (state.round < state.comboReadyRound) return "次のターンから再使用できます";
            if (ComboActors(i).Any(p => state.party[p].hp == 0)) return "参加者の蘇生が必要";
            return ComboActors(i).Any(p => state.party[p].mp < ComboCost(i)) ? "参加者のMPが不足" : "参加者の行動をまとめて予約 / 実行前に変更できます";
        }
        bool CanCombo(int i) { return state.round >= state.comboReadyRound && ComboUnlocked(i) && ComboActors(i).All(p => state.party[p].hp > 0 && state.party[p].mp >= ComboCost(i)); }
        void QueueCombo(int i)
        {
            if (!CanCombo(i)) return;
            Tutorial("combo"); CancelCombo(); state.combo = i + 1; state.comboTarget = target;
            foreach (int p in ComboActors(i)) state.orders[p] = new Order { action = 2 };
            selected = Enumerable.Range(0, 5).FirstOrDefault(p => state.party[p].hp > 0 && state.orders[p].action == 0);
            combosOpen = false; Message("連携「" + ComboNames[i] + "」を予約。" + (i == 1 ? "味方全員を回復。" : i >= 2 ? "敵全体が対象。" : "対象は敵" + (state.comboTarget + 1) + "。"));
        }
        void QueueAllAttacks()
        {
            CancelCombo();
            if (state.enemies[target].hp <= 0) CycleTarget(1);
            for (int i = 0; i < 5; i++) state.orders[i] = new Order { action = state.party[i].hp > 0 ? 1 : 0, target = target };
            Message("全員の攻撃を予約した。実行前に個別の行動を変えられる。");
        }
        void QueueAllGuards()
        {
            if (state.mode != "battle") return;
            CancelCombo();
            for (int p = 0; p < 5; p++) state.orders[p] = new Order { action = state.party[p].hp > 0 ? 2 : 0 };
            Message("全員の防御を予約した。必要な仲間は回復や道具へ変更できます。");
        }
        void CancelCombo()
        {
            if (state.combo > 0) foreach (int p in ComboActors(state.combo - 1)) state.orders[p] = new Order();
            state.combo = 0;
        }
        int ResolveCombo()
        {
            if (state.combo == 0) return 0;
            int i = state.combo - 1; state.combo = 0;
            if (!CanCombo(i)) { Message("連携のHP・MP条件が変わったため、防御に切り替えた。"); return 0; }
            state.combosUsed++;
            state.comboReadyRound = state.round + 2;
            foreach (int p in ComboActors(i)) { state.party[p].mp -= ComboCost(i); state.party[p].guarding = false; }
            if (i == 0) state.party[1].guarding = true;
            if (i == 1 || i == 3) foreach (var ally in state.party.Where(a => a.hp > 0)) { ally.hp = Math.Min(ally.maxHp, ally.hp + ComboHeal(i)); ally.poison = 0; }
            if (i != 1)
            {
                int hit = state.comboTarget < state.enemies.Count && state.enemies[state.comboTarget].hp > 0 ? state.comboTarget : state.enemies.FindIndex(e => e.hp > 0);
                if (hit >= 0)
                {
                    var victims = i >= 2 ? state.enemies.Where(e => e.hp > 0).ToArray() : new[] { state.enemies[hit] };
                    int damage = ComboDamage(i);
                    foreach (var e in victims) { e.hp = Math.Max(0, e.hp - damage); AddFx(false, state.enemies.IndexOf(e), "−" + damage, 0); }
                    Message("連携「" + ComboNames[i] + "」！ " + (victims.Length > 1 ? "敵全体" : "敵") + "に " + damage + " ダメージ。");
                }
            }
            if (i == 1 || i == 3) Message("連携の灯りで味方全員を回復し、毒を解除した。");
            return i + 1;
        }
        string Objective()
        {
            if (state.floor % 10 == 0 && !state.Current.bossDefeated) return "守護者を倒し、塔の記憶を確かめよう。";
            int quest = AvailableQuest();
            return quest >= 0 ? CompanionNames[quest] + "の手掛かりを探そう。\n水色の記憶の灯り / 休憩地点で相談。" : "周囲を探索して、遠くの階段を探そう。";
        }
        void DrawJourneyOverlay()
        {
            drawingJourneyOverlay = true;
            if (journalOpen) { DrawJournal(); drawingJourneyOverlay = false; return; }
            if (combosOpen && state.mode == "battle")
            {
                Panel(new Rect(330, 270, 940, 626)); Text(360, 288, 870, 44, state.round < state.comboReadyRound ? "連携は次のターンから再使用できます" : "連携技 / 使用後は1ターン準備が必要", headingStyle);
                string[] detail = {
                    "ガルド＋リナ / 各MP6 / 単体 " + ComboDamage(0) + " / ガルドが引きつけて防御",
                    "ミナ＋テオ / 各MP" + ComboCost(1) + " / 全員HP" + ComboHeal(1) + "回復＋毒解除（蘇生不可）",
                    "勇者＋リナ / 各MP" + ComboCost(2) + " / 敵全体 " + ComboDamage(2) + "（全体威力75%）",
                    "五人 / 各MP10 / 敵全体 " + ComboDamage(3) + " / 全員HP" + ComboHeal(3) + "回復＋毒解除"
                };
                for (int i = 0; i < 4; i++)
                    if (Action(new Rect(360, 350 + i * 112, 880, 100), (ComboUnlocked(i) ? ComboNames[i] + (state.flags.Contains("path_" + QuestKeys[i] + "_personal") ? " / 個人の約束" : state.flags.Contains("path_" + QuestKeys[i] + "_team") ? " / 五人の約束" : "") : "未習得 / " + QuestTitles[i]) + "\n" + detail[i] + "\n" + ComboCondition(i), CanCombo(i))) QueueCombo(i);
                if (Action(new Rect(1010, 818, 230, 42), "閉じる")) combosOpen = false;
            }
            drawingJourneyOverlay = false;
        }
        void DrawJournal()
        {
            Panel(new Rect(180, 270, 1240, 626)); Text(210, 288, 920, 46, "旅の記録  /  " + state.floor + "階", headingStyle);
            if (Action(new Rect(1170, 292, 220, 42), "閉じる [J]")) journalOpen = false;
            string[] tabs = { "目的と仲間", "物語の記録", "遊び方", "会話履歴", "冒険の成果" };
            for (int i = 0; i < tabs.Length; i++) if (Action(new Rect(210 + i * 235, 351, 222, 42), tabs[i], true, journalTab == i)) { journalTab = i; journalScroll = Vector2.zero; }
            if (journalTab == 3) { DrawDialogueHistory(); return; }
            string text;
            if (journalTab == 0)
            {
                text = "次の目的\n" + Objective() + "\n\n仲間の願いと連携技\n";
                for (int i = 0; i < 4; i++) text += CompanionNames[i] + "：" + QuestTitles[i] + "\n" + (QuestDone(i) ? "達成 / 「" + ComboNames[i] + "」習得" + (state.flags.Contains("path_" + QuestKeys[i] + "_personal") ? " / 個人の約束（威力・回復）" : state.flags.Contains("path_" + QuestKeys[i] + "_team") ? " / 五人の約束（守り・効率・支援）" : "") : state.flags.Contains("hint_" + QuestKeys[i]) ? "手掛かり発見 / 記憶の灯りか休憩地点で続ける" : state.floor >= QuestFloors[i] ? "手掛かりを探せる / 記憶の灯りか休憩地点へ" : QuestFloors[i] + "階以降で手掛かりを探す") + (state.flags.Contains("bond_" + QuestKeys[i]) ? " / 約束を交わした" : "") + "\n\n";
                if (!QuestDone(0) && ComboUnlocked(0)) text += "ガルド＋リナの基礎連携「盾と矢」は使用可。専用イベントで強化できます。\n\n";
                text += "解放した記憶 " + state.flags.Count(f => f.StartsWith("memory:")) + " / 救助した旅人 " + state.flags.Count(f => f.StartsWith("rescued:"));
            }
            else if (journalTab == 1)
            {
                var read = story.Where(n => state.flags.Contains("seen:" + n.id) && (n.id.StartsWith("reveal_") || n.id.StartsWith("quest_") && (n.id.EndsWith("_reply") || n.id.EndsWith("_team"))));
                text = string.Join("\n\n────────\n\n", read.Select(n => n.chapter + "\n" + n.text));
                if (text.Length == 0) text = "まだ章の記録はありません。探索会話で仲間を知り、10階の守護者を越えると塔の秘密が明らかになります。";
            }
            else if (journalTab == 4) text = ProgressSummary();
            else text = "探索：WASD / 矢印で移動、Shiftでダッシュ。近くでEを押して調べる。\n金：階段 / 緑：補給 / 赤：守護者 / 水色：記憶 / 紫：危険な宝箱 / 白：旅人。\n\n寄り道は任意。封印の宝箱は戦闘に勝つと金貨と最大MPを獲得。逃走した時は再挑戦できる。旅人への道案内は金貨不要。\n\n戦闘：仲間と敵を選び、全員に行動を予約してEnter。連携技は専用イベントで習得。参加者の行動をまとめて予約し、残る仲間の行動も選ぶ。別の行動に変更すると連携予約は解除される。\n\n守護者は準備→固有攻撃→隙の順。種類によって盾・反射・回復・護衛があります。予告を見て対処。「盾と矢」のガルド以外は防御しないため、使うタイミングに注意。\n\nヒールは戦闘不能を蘇生できない。補給地点では全員が無料で回復・復活。\n\nJ：記録帳（開いている間は探索と戦闘入力を停止） / F5：保存 / F9：再開 / F11：全画面。会話途中と戦闘予約も保存できる。";
            if (journalTab == 2) { text = "追加の案内：連携は使用後1ターン準備。通常敵の盾は仲間をかばいます。魔法・連携で突破。橙の装置では地図かこの階の防護を選択。51階の工房で五人を永続強化。Bでどうぐと装備。薬草はHP65＋毒解除、魔水はMP25、蘇生の羽は戦闘不能の仲間を復帰。店は補給地点で利用し、買った装備は装備タブで装着。\nボスはそれぞれ固有行動があります。画面上の予告を確認してください。保存枠は手動3枠＋自動保存。F5/F9は選んだ手動枠を使用。\n\n" + text; if (Action(new Rect(884, 292, 270, 42), state.flags.Contains("help:skip") ? "操作案内を再表示" : "操作案内を終了")) { if (state.flags.Contains("help:skip")) state.flags.Remove("help:skip"); else Tutorial("skip"); } }
            float height = Math.Max(425, bodyStyle.CalcHeight(new GUIContent(text), 1130));
            journalScroll = GUI.BeginScrollView(new Rect(210, 415, 1180, 450), journalScroll, new Rect(0, 0, 1130, height));
            GUI.Label(new Rect(0, 0, 1130, height), text, bodyStyle); GUI.EndScrollView();
        }
    }
}










