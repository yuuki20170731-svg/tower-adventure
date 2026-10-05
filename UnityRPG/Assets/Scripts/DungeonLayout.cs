using System;
using System.Collections.Generic;
using System.Linq;

namespace TowerAdventure
{
    public static class DungeonLayout
    {
        static readonly int[] ChapterRooms = { 4, 6, 3, 5, 3, 3, 2, 2, 4, 2 };
        public static FloorState Generate(int number, int seed)
        {
            int w = AdventureState.Width, h = AdventureState.Height;
            var rng = new Random(unchecked(seed + number * 7919));
            var floor = new FloorState { number = number, tiles = Enumerable.Repeat(1, w * h).ToArray(), explored = new bool[w * h] };
            var stack = new Stack<int>();
            int first = (1 + rng.Next(h / 2) * 2) * w + 1 + rng.Next(w / 2) * 2;
            floor.tiles[first] = 0; stack.Push(first);
            int[] offsets = { -2, 2, -2 * w, 2 * w };
            while (stack.Count > 0)
            {
                int current = stack.Peek();
                var candidates = offsets.Select(d => current + d).Where(i => i >= 0 && i < w * h && i % w > 0 && i % w < w - 1 && i / w > 0 && i / w < h - 1 && Math.Abs(i % w - current % w) + Math.Abs(i / w - current / w) == 2 && floor.tiles[i] == 1).ToArray();
                if (candidates.Length == 0) { stack.Pop(); continue; }
                int next = candidates[rng.Next(candidates.Length)];
                floor.tiles[next] = floor.tiles[(current + next) / 2] = 0; stack.Push(next);
            }
            // Open small rooms, always touching the connected maze.
            for (int room = 0; room < ChapterRooms[(number - 1) / 10]; room++)
            {
                int x = 2 + rng.Next(w - 4), y = 2 + rng.Next(h - 4);
                for (int yy = y - 1; yy <= y + 1; yy++) for (int xx = x - 1; xx <= x + 1; xx++) floor.tiles[yy * w + xx] = 0;
            }
            int a = first, b = first, longest = -1;
            foreach (int cell in Enumerable.Range(0, floor.tiles.Length).Where(i => floor.tiles[i] == 0))
            {
                int[] distances = Distances(floor, cell); int distance = distances.Max();
                if (distance > longest || (distance == longest && rng.Next(2) == 0))
                { longest = distance; a = cell; b = Farthest(distances, rng); }
            }
            floor.entrance = a; floor.stairs = b;
            floor.tiles[floor.entrance] = 9; floor.tiles[floor.stairs] = 5;
            var path = Path(floor, floor.entrance, floor.stairs);
            if (number % 10 == 0)
            {
                int boss = path[Math.Max(1, path.Count - 3)]; floor.tiles[boss] = 8;
            }
            if (number == 1 || number % 3 == 0 || number % 5 == 0 || number % 10 == 9)
            {
                int rest = path[Math.Max(1, path.Count - (number % 10 == 0 ? 7 : 5))]; floor.tiles[rest] = 4;
            }
            Place(floor, rng, 7);
            Place(floor, rng, 10); // A memory landmark; companion quests use it when available.
            if (number % 10 == 3) Place(floor, rng, 13);
            if (number % 3 == 0) Place(floor, rng, 11);
            if (number % 4 == 0) Place(floor, rng, 12);
            for (int i = 0; i < 2 + rng.Next(3); i++) Place(floor, rng, 3);
            // Doors are opened by contact, so every generated route stays traversable.
            for (int i = 0; i < 2; i++) Place(floor, rng, 6);
            return floor;
        }
        static void Place(FloorState floor, Random rng, int tile)
        {
            var available = Enumerable.Range(0, floor.tiles.Length).Where(i => floor.tiles[i] == 0 && Math.Abs(i % AdventureState.Width - floor.entrance % AdventureState.Width) + Math.Abs(i / AdventureState.Width - floor.entrance / AdventureState.Width) > 2).ToArray();
            if (available.Length > 0) floor.tiles[available[rng.Next(available.Length)]] = tile;
        }
        static int Farthest(int[] distances, Random rng)
        {
            int max = distances.Max(); var candidates = Enumerable.Range(0, distances.Length).Where(i => distances[i] == max).ToArray();
            return candidates[rng.Next(candidates.Length)];
        }
        public static int[] Distances(FloorState floor, int start)
        {
            int[] distances = Enumerable.Repeat(-1, floor.tiles.Length).ToArray();
            var queue = new Queue<int>(); distances[start] = 0; queue.Enqueue(start);
            while (queue.Count > 0)
            {
                int cell = queue.Dequeue();
                foreach (int next in Neighbors(cell)) if (floor.tiles[next] != 1 && distances[next] < 0)
                { distances[next] = distances[cell] + 1; queue.Enqueue(next); }
            }
            return distances;
        }
        public static IEnumerable<int> Neighbors(int cell)
        {
            int w = AdventureState.Width, h = AdventureState.Height, x = cell % w, y = cell / w;
            if (x > 0) yield return cell - 1;
            if (x < w - 1) yield return cell + 1;
            if (y > 0) yield return cell - w;
            if (y < h - 1) yield return cell + w;
        }
        public static List<int> Path(FloorState floor, int start, int end)
        {
            var distances = Distances(floor, start); var path = new List<int>();
            if (distances[end] < 0) return path;
            for (int cell = end; ; )
            {
                path.Add(cell); if (cell == start) break;
                int distance = distances[cell]; cell = Neighbors(cell).First(i => distances[i] == distance - 1);
            }
            path.Reverse(); return path;
        }
    }
}



