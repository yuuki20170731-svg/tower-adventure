using System;
using UnityEngine;

namespace TowerAdventure
{
    public partial class AdventureGame
    {
        AudioSource ambience;
        AudioClip[] ambientClips;
        int ambientChapter = -1;
        // Measured row edges in the generated atlas; scenes have slightly unequal heights.
        static readonly int[] ChapterRows = { 0, 202, 404, 604, 804, 1024 };
        float ambientVolume = .12f;
        void InitAmbience()
        {
            ambience = gameObject.AddComponent<AudioSource>(); ambience.loop = true; ambience.volume = 0;
            ambientVolume = Mathf.Clamp01(PlayerPrefs.GetFloat("AdventureAmbient", .12f));
            ambientClips = new AudioClip[10];
            const int rate = 22050, count = rate * 8;
            for (int chapter = 0; chapter < 10; chapter++)
            {
                var samples = new float[count]; var random = new System.Random(71 + chapter); float smooth = 0;
                for (int i = 0; i < count; i++)
                {
                    float t = i / (float)rate; smooth = smooth * .96f + ((float)random.NextDouble() * 2 - 1) * .04f;
                    float envelope = Mathf.Clamp01(Mathf.Min(t, 8 - t) * 3);
                    float sound = smooth * (.6f + .3f * Mathf.Sin(t * Mathf.PI / 2));
                    if (chapter == 1 || chapter == 3) { float chirp = t % 2; sound += Mathf.Sin(t * 11000 + Mathf.Sin(t * 35) * 15) * Mathf.Exp(-chirp * 12) * .07f; }
                    else if (chapter == 6) sound += Mathf.Sin(t * 4700 + Mathf.Sin(t * 4) * 30) * .012f + smooth * .7f;
                    else if (chapter == 7) sound += Mathf.Sin(t * 150 * Mathf.PI) * (.02f + .04f * Mathf.Pow(Mathf.Max(0, Mathf.Cos(t * Mathf.PI)), 8));
                    else if (chapter == 4 || chapter == 9) sound += Mathf.Sin(t * (chapter == 9 ? 110 : 220) * Mathf.PI) * .035f;
                    else sound += Mathf.Sin(t * (30 + chapter * 5) * Mathf.PI) * .015f;
                    samples[i] = sound * envelope;
                }
                ambientClips[chapter] = AudioClip.Create("chapter-ambience-" + chapter, count, 1, rate, false); ambientClips[chapter].SetData(samples, 0);
            }
        }
        void UpdateAmbience()
        {
            if (ambience == null) return;
            if (state == null || menu == "title") { if (ambience.isPlaying) ambience.Stop(); ambientChapter = -1; return; }
            int chapter = (state.floor - 1) / 10;
            if (ambientChapter != chapter) { ambientChapter = chapter; ambience.clip = ambientClips[chapter]; ambience.volume = 0; ambience.Play(); }
            float target = ambientVolume * (state.mode == "battle" ? .3f : state.mode == "clear" ? .5f : 1);
            ambience.volume = Mathf.MoveTowards(ambience.volume, target, Time.unscaledDeltaTime * .25f);
        }
        bool DrawChapterBackground(Rect rect, bool floorOnly = false)
        {
            Texture2D atlas;
            if (state == null || menu == "title" || !textures.TryGetValue("chapters_hd", out atlas)) return false;
            int chapter = (state.floor - 1) / 10;
            int row = chapter / 2;
            var uv = new Rect(chapter % 2 * .5f + 2f / 1536, 1 - (ChapterRows[row + 1] - 2f) / 1024, .5f - 4f / 1536, (ChapterRows[row + 1] - ChapterRows[row] - 4f) / 1024);
            if (floorOnly) uv.height *= .28f;
            float sourceAspect = atlas.width * uv.width / (atlas.height * uv.height), targetAspect = rect.width / rect.height;
            if (sourceAspect > targetAspect) { float width = uv.width * targetAspect / sourceAspect; uv.x += (uv.width - width) / 2; uv.width = width; }
            else { float height = uv.height * sourceAspect / targetAspect; uv.y += (uv.height - height) / 2; uv.height = height; }
            GUI.DrawTextureWithTexCoords(rect, atlas, uv); return true;
        }
    }
}
