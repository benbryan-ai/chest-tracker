using System.Text.Json;
using ChestCounter;

// chest-scan [--json] [--timeout SECONDS] [replay or folder]...
//
// Reads Fortnite replay files (read-only) and says how many chests were opened, dug up or broken in each.
// With no path it reads Fortnite's own replay folder. The Chest Tracker app runs this with --json.
const string Usage = "usage: chest-scan [--json] [--timeout SECONDS] [replay or folder]...";

L.Set("en");

var paths = new List<string>();
var json = false;
var timeoutSeconds = 180;
for (var i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--json":
            json = true;
            break;
        case "--timeout" when i + 1 < args.Length && int.TryParse(args[i + 1], out var seconds) && seconds > 0:
            timeoutSeconds = seconds;
            i++;
            break;
        case "-h" or "--help":
            Console.WriteLine(Usage);
            return 0;
        default:
            if (args[i].StartsWith("--"))
            {
                Console.Error.WriteLine(Usage);
                return 2;
            }
            paths.Add(args[i]);
            break;
    }
}

if (paths.Count == 0)
{
    paths.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FortniteGame", "Saved", "Demos"));
}

var files = paths
    .SelectMany(p => Directory.Exists(p) ? Directory.GetFiles(p, "*.replay") : new[] { p })
    .Select(p => new FileInfo(p))
    .OrderBy(f => f.LastWriteTimeUtc)
    .ToList();

var results = files.Select(f => Scan(f, TimeSpan.FromSeconds(timeoutSeconds))).ToList();

Console.OutputEncoding = new System.Text.UTF8Encoding(false);
if (json)
{
    Console.WriteLine(JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true }));
}
else
{
    Console.WriteLine($"{"replay",-52} {"status",-10} {"chests",6} {"opened",6} {"broken",6}  notes");
    foreach (var r in results)
    {
        var note = r.Message ?? (r.CountsAsMatch == false ? r.WhyNot : "");
        Console.WriteLine($"{r.File,-52} {r.Status,-10} {r.Chests,6} {r.Opened,6} {r.Broken,6}  {note}");
    }
    Console.WriteLine($"{results.Count(r => r.Status == "ok")} of {results.Count} replays read, {results.Where(r => r.Status == "ok").Sum(r => r.Chests)} chests");
}
return 0;

static ScanResult Scan(FileInfo file, TimeSpan timeout)
{
    var result = new ScanResult { File = file.Name };
    try
    {
        if (!file.Exists)
        {
            result.Status = "error";
            result.Message = "File not found.";
            return result;
        }
        if (ReplayHeaderProbe.IsLive(file.FullName) == true)
        {
            result.Status = "live";
            result.Message = "Fortnite is still recording this match.";
            return result;
        }
        if (ReplayHeaderProbe.KeyMissing(file.FullName))
        {
            result.Status = "incomplete";
            result.Message = "The replay has no decryption key (Fortnite closed before the match ended).";
            return result;
        }

        byte[] bytes;
        using (var fs = new FileStream(file.FullName, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        {
            bytes = new byte[fs.Length];
            fs.ReadExactly(bytes);
        }

        MatchRecord? match = null;
        Exception? failure = null;
        var worker = new Thread(() =>
        {
            try
            {
                using var ms = new MemoryStream(bytes, writable: false);
                // A replay saved on a PC is its player's: the replay's owner is the one counted.
                match = new ReplayAnalyzer().Analyze(ms, file.Name, "");
            }
            catch (Exception e)
            {
                failure = e;
            }
        })
        {
            IsBackground = true,
            Priority = ThreadPriority.BelowNormal,
            Name = "ReplayAnalysis",
        };
        worker.Start();
        if (!worker.Join(timeout))
        {
            result.Status = "error";
            result.Message = "Reading the replay took too long.";
            return result;
        }
        if (failure != null || match == null)
        {
            result.Status = "error";
            result.Message = failure?.Message ?? "The replay couldn't be read.";
            return result;
        }

        result.Status = "ok";
        result.StartUtc = match.MatchStartUtc?.ToString("o");
        result.DurationSeconds = match.DurationSeconds;
        result.Player = match.PlayerName;
        result.Playlist = match.Playlist;
        result.Map = match.Map;
        result.Custom = match.IsCustomMatch;
        result.CountsAsMatch = GameModes.Counts(match);
        result.WhyNot = GameModes.WhyNot(match);
        result.Chests = match.Chests.Count;
        result.Broken = match.Chests.Count(c => c.Destroyed);
        result.Opened = result.Chests - result.Broken;
        result.Kinds = match.Chests.GroupBy(c => L.Name(ChestKinds.Canonical(c.Kind))).ToDictionary(g => g.Key, g => g.Count());
        result.VehicleLootUnexplained = match.UnrecordedVehicleLoot;
        result.TeamChests = match.TeamChestsOpened;
        return result;
    }
    catch (Exception e)
    {
        result.Status = "error";
        result.Message = e.Message;
        return result;
    }
}

internal sealed class ScanResult
{
    public string File { get; set; } = "";
    /// <summary>ok, live (still being recorded), incomplete (no key) or error.</summary>
    public string Status { get; set; } = "error";
    public string? Message { get; set; }
    public string? StartUtc { get; set; }
    public int? DurationSeconds { get; set; }
    public string? Player { get; set; }
    public string? Playlist { get; set; }
    public string? Map { get; set; }
    public bool Custom { get; set; }
    /// <summary>Chest Counter's own rule: regular Battle Royale on this season's map.</summary>
    public bool? CountsAsMatch { get; set; }
    public string? WhyNot { get; set; }
    /// <summary>Opened, dug up or broken by the replay's player.</summary>
    public int Chests { get; set; }
    public int Opened { get; set; }
    public int Broken { get; set; }
    public Dictionary<string, int>? Kinds { get; set; }
    /// <summary>Loot piles along the player's drives with no recorded chest: the real count may be higher.</summary>
    public int VehicleLootUnexplained { get; set; }
    public int TeamChests { get; set; }
}
