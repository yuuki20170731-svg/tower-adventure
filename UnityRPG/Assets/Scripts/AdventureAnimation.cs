using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        struct WalkPoint { public Vector2 position; public float distance; public int facing; }
        readonly List<WalkPoint> walkTrail = new List<WalkPoint>();
        AdventureState walkingState;
        int walkingFloor, facing;
        float walkDistance, lastWalkTime = -10, nextFootstep;
        static int WalkFacing(Vector2 delta) { return Mathf.Abs(delta.x) > Mathf.Abs(delta.y) ? delta.x < 0 ? 3 : 1 : delta.y < 0 ? 2 : 0; }
        void EnsureWalk(Vector2 position)
        {
            if (walkingState == state && walkingFloor == state.floor && walkTrail.Count > 0 && Vector2.Distance(walkTrail[walkTrail.Count - 1].position, position) < 1) return;
            walkingState = state; walkingFloor = state.floor; walkDistance = 0; facing = 0; lastWalkTime = -10; nextFootstep = .4f;
            walkTrail.Clear(); walkTrail.Add(new WalkPoint { position = position });
        }
        void AdvanceWalk(Vector2 before, Vector2 after)
        {
            EnsureWalk(before); var delta = after - before;
            walkDistance += delta.magnitude; facing = WalkFacing(delta); lastWalkTime = Time.unscaledTime;
            walkTrail.Add(new WalkPoint { position = after, distance = walkDistance, facing = facing });
            while (walkTrail.Count > 2 && walkTrail[1].distance < walkDistance - 4) walkTrail.RemoveAt(0);
            if (Application.isPlaying && walkDistance >= nextFootstep)
            { nextFootstep = walkDistance + .4f; if (effectAudio != null) effectAudio.PlayOneShot(effectSounds[0], .12f); }
        }
        WalkPoint FollowPoint(float distance)
        {
            if (distance <= walkTrail[0].distance) return walkTrail[0];
            for (int i = 1; i < walkTrail.Count; i++) if (walkTrail[i].distance >= distance)
            {
                var a = walkTrail[i - 1]; var b = walkTrail[i];
                return new WalkPoint { position = Vector2.Lerp(a.position, b.position, Mathf.InverseLerp(a.distance, b.distance, distance)), distance = distance, facing = b.facing };
            }
            return walkTrail[walkTrail.Count - 1];
        }
        void WalkArt(int actor, int direction, int step, Rect rect)
        {
            Texture2D atlas;
            if (!textures.TryGetValue("party_walk_hd", out atlas)) { Art(state.party[actor].image, rect); return; }
            int column = (direction == 2 ? 4 : direction == 1 || direction == 3 ? 2 : 0) + step % 2;
            var uv = new Rect(column / 6f, 1 - (actor + 1) / 5f, 1 / 6f, 1 / 5f);
            if (direction == 3) { uv.x += uv.width; uv.width = -uv.width; }
            GUI.DrawTextureWithTexCoords(rect, atlas, uv);
        }
        void DrawWorldActors(float ox, float oy, float size)
        {
            EnsureWalk(new Vector2(state.px, state.py));
            bool moving = !Modal && menu == "" && Time.unscaledTime - lastWalkTime < .14f;
            // Follow the path actually walked, so companions cannot cut through walls.
            var actors = new List<KeyValuePair<int, WalkPoint>>();
            int rank = 0;
            for (int i = 0; i < 5; i++)
            {
                if (state.party[i].hp <= 0) continue;
                float distance = walkDistance - rank++ * .75f;
                if (distance < 0 && i != 0) continue;
                actors.Add(new KeyValuePair<int, WalkPoint>(i, FollowPoint(Mathf.Max(0, distance))));
            }
            foreach (var entry in actors.OrderBy(a => a.Value.position.y).ThenByDescending(a => a.Key))
            {
                int actor = entry.Key; var point = entry.Value;
                float x = ox + point.position.x * size, y = oy + point.position.y * size;
                int step = moving ? Mathf.FloorToInt(point.distance / .22f) % 2 : 0;
                float bob = moving && !reducedEffects ? Mathf.Sin(point.distance * Mathf.PI / .22f) * 1.3f : 0;
                Fill(new Rect(x - 13, y - 2, 26, 6), new Color(0, 0, 0, .3f));
                if (moving && !reducedEffects) Fill(new Rect(x - 8, y + 4, 3, 2), new Color(.8f, .75f, .6f, .35f));
                WalkArt(actor, point.facing, step, new Rect(x - 32, y - 52 + bob, 64, 52));
            }
            int cell = NearbyObject();
            if (cell >= 0)
            {
                float x = ox + (cell % AdventureState.Width + .5f) * size, y = oy + (cell / AdventureState.Width) * size;
                Fill(new Rect(x - 10, y - 16, 20, 20), Ink); Text(x - 6, y - 18, 24, 25, "E", cardStyle);
            }
        }
        float ActionMotion(bool ally, int index)
        {
            if (reducedEffects || Modal) return 0;
            var fx = combatFx.LastOrDefault(f => f.ally == ally && f.index == index && (f.text == "攻撃" || f.text == "魔法" || f.text == "祈り") && Time.unscaledTime >= f.start && Time.unscaledTime < f.start + .5f);
            return fx == null ? 0 : Mathf.Sin((Time.unscaledTime - fx.start) / .5f * Mathf.PI);
        }
        void DrawBattleActors()
        {
            for (int i = 0; i < 5; i++)
            {
                var a = state.party[i]; float motion = ActionMotion(true, i), x = 52 + i * 102;
                float breath = reducedEffects || Modal || a.hp <= 0 ? 0 : Mathf.Sin(Time.unscaledTime * 2.5f + i) * 1.5f;
                Fill(new Rect(x + 21, 554, 60, 7), new Color(0, 0, 0, .28f));
                if (state.mode == "battle" && selected == i) Fill(new Rect(x + 21, 558, 60, 3), Gold);
                var rect = new Rect(x + motion * 32 + FxMotion(true, i), 422 - motion * 5 + breath, 105, 134);
                var matrix = GUI.matrix; var color = GUI.color;
                if (a.hp <= 0) { GUI.color = new Color(.6f, .6f, .6f, .7f); rect.y = 464; rect.height = 90; GUIUtility.RotateAroundPivot(65, rect.center); }
                else GUIUtility.RotateAroundPivot(motion * 8, new Vector2(rect.center.x, rect.yMax));
                WalkArt(i, 1, motion > .3f ? 1 : 0, rect); GUI.matrix = matrix; GUI.color = color;
                Fill(new Rect(x + 8, 573, 98, 29), new Color(.025f, .045f, .075f, .9f));
                Text(x + 16, 574, 90, 30, i == 0 ? "勇者" : CompanionNames[i - 1], cardStyle);
                if (a.hp > 0 && GUI.Button(new Rect(x, 421, 100, 145), GUIContent.none, GUIStyle.none)) { selected = i; skillScroll = Vector2.zero; }
                if (a.guarding && a.hp > 0) { Fill(new Rect(x + 84, 475, 4, 47), Gold); Fill(new Rect(x + 13, 374, 75, 29), Ink); Text(x + 24, 373, 64, 32, "防御", cardStyle); }
            }
        }
        void LivingEnemyArt(string key, Rect rect, int index)
        {
            float motion = ActionMotion(false, index);
            float breath = reducedEffects || Modal ? 0 : Mathf.Sin(Time.unscaledTime * 2 + index) * 2;
            rect.x -= motion * 28; rect.y += breath;
            var matrix = GUI.matrix; GUIUtility.RotateAroundPivot(-motion * 7, new Vector2(rect.center.x, rect.yMax));
            Art(key, rect); GUI.matrix = matrix;
        }
    }
}
