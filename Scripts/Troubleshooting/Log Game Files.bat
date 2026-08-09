@echo off
setlocal
title File Troubleshooting Tool
cd /d "%~dp0"

set "BAT_PATH=%~f0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$raw = Get-Content -LiteralPath $env:BAT_PATH -Raw; $parts = [regex]::Split($raw, '(?m)^:POWERSHELL\r?$', 2); if ($parts.Count -lt 2) { throw 'Could not locate embedded PowerShell script.' }; & ([scriptblock]::Create($parts[1]))"

set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
    echo.
    echo ============================================================
    echo ERROR: The troubleshooting tool encountered an error.
    echo ============================================================
    echo.
    echo PowerShell exited with error code %ERR%.
    echo.
    pause
)

exit /b %ERR%

:POWERSHELL

$ErrorActionPreference = "Stop"

$batPath = $env:BAT_PATH
$root = [System.IO.Path]::GetDirectoryName($batPath)
$launcher = [System.IO.Path]::Combine($root, "launcher.exe")
$output = [System.IO.Path]::Combine($root, "file_hashes.csv")

Write-Host ""
Write-Host "FILE TROUBLESHOOTING TOOL" -ForegroundColor Cyan
Write-Host "=========================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This tool will recursively log all files in your game folder to a CSV."
Write-Host "The CSV will contain each file's path, modified time, and SHA-1 hash."
Write-Host ""
Write-Host "This may cause heavy disk activity while the files are being read."
Write-Host "No existing files will be modified."
Write-Host ""
Write-Host "Once finished, we'll open:"
Write-Host "  1. The completed CSV file"
Write-Host "  2. Pastebin.com"
Write-Host ""
Write-Host "You'll then copy and paste the FULL contents of the CSV into Pastebin"
Write-Host "and click `"Create New Paste`" at the bottom of the page."
Write-Host ""

if (-not [System.IO.File]::Exists($launcher)) {
    Write-Host "ERROR: launcher.exe was not found beside this file." -ForegroundColor Red
    Write-Host ""
    Write-Host "Place this BAT file directly beside launcher.exe and run it again."
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Scanning for files..."
Write-Host ""

$source = @'
using System;
using System.IO;
using System.Text;
using System.Linq;
using System.Security.Cryptography;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

public sealed class FileHashRecord
{
    public string Path;
    public string Modified;
    public string Sha1;
}

public sealed class HashProgress
{
    public int Completed;
    public int Failed;
    public volatile bool Finished;
    public int Total;

    public ConcurrentBag<FileHashRecord> Results =
        new ConcurrentBag<FileHashRecord>();

    public int GetCompleted()
    {
        return Interlocked.CompareExchange(ref Completed, 0, 0);
    }

    public int GetFailed()
    {
        return Interlocked.CompareExchange(ref Failed, 0, 0);
    }
}

public static class FileHasher
{
    public static HashProgress Start(
        string root,
        string output,
        string batPath)
    {
        string rootPrefix =
            root.TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;

        string[] files =
            Directory.GetFiles(
                root,
                "*",
                SearchOption.AllDirectories)
            .Where(path =>
                !string.Equals(
                    path,
                    output,
                    StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(
                    path,
                    batPath,
                    StringComparison.OrdinalIgnoreCase))
            .ToArray();

        HashProgress progress = new HashProgress();
        progress.Total = files.Length;

        Task.Factory.StartNew(() =>
        {
            try
            {
                int workers =
                    Math.Min(
                        32,
                        Math.Max(
                            4,
                            Environment.ProcessorCount * 2));

                ParallelOptions options =
                    new ParallelOptions
                    {
                        MaxDegreeOfParallelism = workers
                    };

                Parallel.ForEach(
                    files,
                    options,
                    path =>
                    {
                        try
                        {
                            FileInfo info =
                                new FileInfo(path);

                            string hash;

                            using (SHA1 sha1 = SHA1.Create())
                            using (FileStream stream =
                                new FileStream(
                                    path,
                                    FileMode.Open,
                                    FileAccess.Read,
                                    FileShare.ReadWrite |
                                    FileShare.Delete,
                                    1024 * 1024,
                                    FileOptions.SequentialScan))
                            {
                                byte[] bytes =
                                    sha1.ComputeHash(stream);

                                StringBuilder sb =
                                    new StringBuilder(40);

                                for (
                                    int i = 0;
                                    i < bytes.Length;
                                    i++)
                                {
                                    sb.Append(
                                        bytes[i].ToString("x2"));
                                }

                                hash = sb.ToString();
                            }

                            string relative =
                                path.StartsWith(
                                    rootPrefix,
                                    StringComparison.OrdinalIgnoreCase)
                                ? path.Substring(rootPrefix.Length)
                                : path;

                            progress.Results.Add(
                                new FileHashRecord
                                {
                                    Path = relative,
                                    Modified =
                                        info.LastWriteTime.ToString(
                                            "yyyy-MM-ddTHH:mm:ss"),
                                    Sha1 = hash
                                });
                        }
                        catch
                        {
                            Interlocked.Increment(
                                ref progress.Failed);
                        }
                        finally
                        {
                            Interlocked.Increment(
                                ref progress.Completed);
                        }
                    });
            }
            finally
            {
                progress.Finished = true;
            }
        });

        return progress;
    }

    public static void WriteCsv(
        HashProgress progress,
        string output)
    {
        FileHashRecord[] records =
            progress.Results
            .OrderBy(
                x => x.Path,
                StringComparer.OrdinalIgnoreCase)
            .ToArray();

        using (StreamWriter writer =
            new StreamWriter(
                output,
                false,
                new UTF8Encoding(false)))
        {
            writer.WriteLine(
                "\"path\",\"modified\",\"sha1\"");

            foreach (
                FileHashRecord record in records)
            {
                writer.Write('"');
                writer.Write(Escape(record.Path));
                writer.Write("\",\"");

                writer.Write(Escape(record.Modified));
                writer.Write("\",\"");

                writer.Write(Escape(record.Sha1));
                writer.WriteLine('"');
            }
        }
    }

    private static string Escape(string value)
    {
        if (value == null)
            return "";

        return value.Replace("\"", "\"\"");
    }
}
'@

Add-Type -TypeDefinition $source -Language CSharp

$progress = [FileHasher]::Start(
    $root,
    $output,
    $batPath
)

if ($progress.Total -eq 0) {
    Write-Host "ERROR: No files were found." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Found $($progress.Total) files."
Write-Host ""
Write-Host "Hashing files..."
Write-Host ""

$startTime = [DateTime]::Now
$barWidth = 30

while (-not $progress.Finished) {
    $completed = $progress.GetCompleted()
    $total = $progress.Total
    $elapsed = [DateTime]::Now - $startTime

    if ($completed -gt 0 -and $elapsed.TotalSeconds -gt 0) {
        $rate = $completed / $elapsed.TotalSeconds
        $remaining = $total - $completed

        if ($rate -gt 0) {
            $eta = [TimeSpan]::FromSeconds(
                $remaining / $rate
            )

            if ($eta.TotalHours -ge 1) {
                $etaText =
                    "{0:00}:{1:00}:{2:00}" -f `
                    [int]$eta.TotalHours,
                    $eta.Minutes,
                    $eta.Seconds
            }
            else {
                $etaText =
                    "{0:00}:{1:00}" -f `
                    $eta.Minutes,
                    $eta.Seconds
            }
        }
        else {
            $etaText = "Calculating..."
        }
    }
    else {
        $etaText = "Calculating..."
    }

    $percent = [int](
        ($completed / $total) * 100
    )

    $filled = [int](
        ($completed / $total) * $barWidth
    )

    if ($filled -gt $barWidth) {
        $filled = $barWidth
    }

    $empty = $barWidth - $filled

    $bar =
        ("#" * $filled) +
        ("-" * $empty)

    $status =
        "`rHashing: [$bar] " +
        "$percent%  " +
        "$completed/$total files  " +
        "ETA: $etaText"

    Write-Host `
        $status.PadRight(110) `
        -NoNewline

    Start-Sleep -Milliseconds 100
}

$completed = $progress.GetCompleted()

$bar = "#" * $barWidth

$status =
    "`rHashing: [$bar] " +
    "100%  " +
    "$completed/$($progress.Total) files  " +
    "ETA: 00:00"

Write-Host `
    $status.PadRight(110) `
    -NoNewline

Write-Host ""

[FileHasher]::WriteCsv(
    $progress,
    $output
)

$logged = $progress.Results.Count
$failed = $progress.GetFailed()

Write-Host ""
Write-Host "Finished!" -ForegroundColor Green
Write-Host ""
Write-Host "Logged $logged files to:"
Write-Host $output
Write-Host ""

if ($failed -gt 0) {
    Write-Host `
        "WARNING: $failed file(s) could not be read and were not included." `
        -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "The CSV and Pastebin.com will now be opened."
Write-Host ""
Write-Host "In the CSV:"
Write-Host "  1. Press Ctrl+A to select ALL of the text."
Write-Host "  2. Press Ctrl+C to copy it."
Write-Host ""
Write-Host "Then in Pastebin:"
Write-Host "  3. Paste the full contents into the large text box."
Write-Host "  4. Click `"Create New Paste`" at the bottom of the page."
Write-Host ""

Start-Process `
    notepad.exe `
    -ArgumentList "`"$output`""

Start-Process "https://pastebin.com/"

Write-Host ""
Read-Host "Press Enter when you're finished to close this window"

exit 0
