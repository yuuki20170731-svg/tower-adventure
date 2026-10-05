using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        string momentTitle, momentDetail;
        float momentStart = -10, momentEnd = -10, transitionEnd = -10;
        AdventureState momentState, barState, repeatState;
        int momentFloor, repeatRound;
        Order[] previousOrders;
        readonly Dictionary<Vector3, float> animatedBars = new Dictionary<Vector3, float>();
        int pickupCell = -1, pickupFloor;
        float pickupStart;
        bool TransitionBusy { get { return Application.isPlaying && momentState == state && state != null && momentFloor == state.floor && !reducedEffects && Time.unscaledTime < transitionEnd; } }
        void ShowMoment(string title, string detail, bool transition = false)
        {
            if (!Application.isPlaying) return;
            momentTitle = title; momentDetail = detail; momentState = state; momentFloor = state.floor;
            momentStart = Mathf.Max(Time.unscaledTime, effectEnd); momentEnd = momentStart + (reducedEffects ? 1.4f : 2.1f);
            if (transition && !reducedEffects)
            { combatFx.Clear(); effectEnd = 0; battleEffects = false; momentStart = Time.unscaledTime; momentEnd = momentStart + 1.3f; transitionEnd = momentStart + .35f; }
        }
        float DisplayBar(Rect rect, float target)
        {
            if (barState != state) { animatedBars.Clear(); barState = state; }
            var key = new Vector3(rect.x, rect.y, rect.width); float shown;
            if (!animatedBars.TryGetValue(key, out shown) || reducedEffects || !Application.isPlaying) shown = target;
            else if (Event.current.type == EventType.Repaint && !Modal) shown = Mathf.MoveTowards(shown, target, Time.unscaledDeltaTime * 2.5f);
            animatedBars[key] = shown; return shown;
        }
        void RememberOrders()
        {
            repeatState = state; repeatRound = state.round;
            previousOrders = state.orders.Select(o => new Order { action = o.action, target = o.target, skill = o.skill }).ToArray();
            if (state.combo > 0) foreach (int actor in ComboActors(state.combo - 1)) previousOrders[actor].action = 0;
        }
        bool CanRepeat { get { return repeatState == state && previousOrders != null && state.mode == "battle" && state.round > repeatRound; } }
        void RepeatOrders()
        {
            if (!CanRepeat || Modal || EffectsBusy) return;
            CancelCombo(); ResetOrders(); int enemy = state.enemies.FindIndex(e => e.hp > 0);
            for (int p = 0; p < 5; p++)
            {
                var a = state.party[p]; var old = previousOrders[p]; if (a.hp <= 0 || old.action < 1 || old.action > 4) continue;
                var skill = old.action >= 3 ? skills.FirstOrDefault(s => s.name == old.skill) : null;
                if (old.action >= 3 && (skill == null || !AllowedSkill(a, skill) || a.mp < SkillCost(a, skill))) continue;
                int target = old.target;
                if (old.action == 4) { if (!HealUseful(target)) continue; }
                else if (old.action != 2 && (target < 0 || target >= state.enemies.Count || state.enemies[target].hp <= 0)) target = enemy;
                state.orders[p] = new Order { action = old.action, target = target, skill = old.skill };
            }
            selected = Enumerable.Range(0, 5).FirstOrDefault(p => state.party[p].hp > 0 && state.orders[p].action == 0);
            notice = "前の行動を予約しました。MP不足・道具・連携は選び直してください。実行前に変更できます。";
        }
        void PickupFeedback(int cell, int gold, string item)
        {
            if (!Application.isPlaying) return;
            pickupCell = cell; pickupFloor = state.floor; pickupStart = Time.unscaledTime;
            ShowMoment("宝箱を開けた", "+" + gold + " G  /  " + item);
            effectAudio.PlayOneShot(effectSounds[1], .6f);
        }
        void DrawFeedback()
        {
            if (momentState != state || state == null || menu != "" || Modal) return;
            float now = Time.unscaledTime;
            if (!reducedEffects && state.mode == "world" && pickupFloor == state.floor && pickupCell >= 0 && now - pickupStart < .8f)
            {
                float t = (now - pickupStart) / .8f;
                float x = 78 + (pickupCell % AdventureState.Width + .5f) * 54, y = 289 + (pickupCell / AdventureState.Width + .5f) * 54;
                for (int i = 0; i < 8; i++)
                { float angle = i * Mathf.PI / 4; Fill(new Rect(x + Mathf.Cos(angle) * (12 + t * 28), y + Mathf.Sin(angle) * (8 + t * 20) - t * 30, 4, 4), new Color(1, .8f, .3f, 1 - t)); }
            }
            if (TransitionBusy) Fill(new Rect(0, 0, 1600, 1000), new Color(.01f, .025f, .05f, Mathf.Clamp01((transitionEnd - now) / .35f) * .75f));
            if (momentFloor != state.floor || now < momentStart || now >= momentEnd) return;
            if (state.mode != "world" && !TransitionBusy) return;
            var color = GUI.color;
            float alpha = reducedEffects ? 1 : Mathf.Min(1, (now - momentStart) / .15f, (momentEnd - now) / .3f);
            GUI.color = new Color(color.r, color.g, color.b, alpha);
            Panel(new Rect(175, 794, 750, 91), true);
            Text(197, 801, 708, 35, momentTitle, headingStyle); Text(197, 844, 708, 31, momentDetail, cardStyle);
            GUI.color = color;
        }
    }
}
