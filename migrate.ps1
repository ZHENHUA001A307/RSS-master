$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
param([switch]$Apply)

$root = "E:\2_Assets\E2_1 RSS"
$skipRepos = @("applied-foreign-lang", "_master")

# Dual-mode repos: CSV initial progress (EPUB progress comes from progress.txt)
$csvInitialProgress = @{
    "computer-engineering" = 10
    "story-post"           = 33
}

Get-ChildItem $root -Directory | Where-Object {
    $skipRepos -notcontains $_.Name -and
    (Test-Path (Join-Path $_.FullName ".git"))
} | ForEach-Object {
    $repo = $_
    $rname = $repo.Name
    Write-Host "== $rname ==" -ForegroundColor Cyan

    $booksDir   = Join-Path $repo.FullName "books"
    $booksLong  = Join-Path $repo.FullName "books_long"
    $booksShort = Join-Path $repo.FullName "books_short"
    $dataDir    = Join-Path $repo.FullName "data"

    # 0. merge books_long/books_short -> books
    if ((Test-Path $booksLong) -or (Test-Path $booksShort)) {
        Write-Host "  [MERGE] books_long/books_short -> books"
        if ($Apply) {
            New-Item -ItemType Directory -Force -Path $booksDir | Out-Null
            foreach ($src in @($booksLong, $booksShort)) {
                if (Test-Path $src) {
                    Get-ChildItem $src -File | ForEach-Object {
                        $dstFile = Join-Path $booksDir $_.Name
                        if (Test-Path $dstFile) {
                            Write-Host "    [CONFLICT] $($_.Name) already exists, skipping" -ForegroundColor Red
                        } else {
                            Move-Item $_.FullName $dstFile
                        }
                    }
                    Remove-Item $src -Recurse -Force
                }
            }
        }
    }

    # 1. data dir
    if ($Apply) { New-Item -ItemType Directory -Force -Path $dataDir | Out-Null }

    # 2. CSV migration
    $csvCandidates = @("manga.csv", "source.csv", "links.csv")
    $foundCsv = $null
    foreach ($c in $csvCandidates) {
        $p = Join-Path $repo.FullName $c
        if (Test-Path $p) { $foundCsv = $p; break }
    }
    if ($foundCsv) {
        $target = Join-Path $dataDir "source.csv"
        Write-Host "  [CSV] $foundCsv -> $target"
        if ($Apply) { Move-Item -Path $foundCsv -Destination $target -Force }
    }

    # 3. detect modes
    $epubCount = 0
    if (Test-Path $booksDir) {
        $epubCount = (Get-ChildItem $booksDir -Filter *.epub -ErrorAction SilentlyContinue).Count
    }
    $hasEpub = $epubCount -gt 0
    $hasCsv  = (Test-Path (Join-Path $dataDir "source.csv")) -or ($foundCsv -ne $null)

    $epubProgressPath = Join-Path $repo.FullName "progress.epub.json"
    $csvProgressPath  = Join-Path $dataDir "progress.csv.txt"

    # 4. progress.txt migration
    $oldProgress = Join-Path $repo.FullName "progress.txt"
    if (Test-Path $oldProgress) {
        $val = (Get-Content $oldProgress -Raw).Trim()
        Write-Host "  [progress.txt] value = $val"

        if ($hasCsv -and $hasEpub) {
            # dual: progress.txt -> EPUB
            if (Test-Path $epubProgressPath) {
                Write-Host "    [SKIP] $epubProgressPath already exists" -ForegroundColor Yellow
            } else {
                Write-Host "    [dual] EPUB -> $epubProgressPath (last_index = $val)"
                if ($Apply) {
                    [System.IO.File]::WriteAllText($epubProgressPath, (@{ last_index = [int]$val } | ConvertTo-Json), $utf8NoBom)
                }
            }

            $csvInit = $csvInitialProgress[$rname]
            if ($null -ne $csvInit) {
                if (Test-Path $csvProgressPath) {
                    Write-Host "    [SKIP] $csvProgressPath already exists" -ForegroundColor Yellow
                } else {
                    Write-Host "    [dual] CSV  -> $csvProgressPath (value = $csvInit)"
                    if ($Apply) { Set-Content -Path $csvProgressPath -Value $csvInit -Encoding ASCII }
                }
            }
            if ($Apply) { Remove-Item $oldProgress }
        }
        elseif ($hasCsv) {
            if (Test-Path $csvProgressPath) {
                Write-Host "    [SKIP] $csvProgressPath already exists" -ForegroundColor Yellow
            } else {
                Write-Host "    [CSV]  -> $csvProgressPath"
                if ($Apply) { Move-Item $oldProgress $csvProgressPath -Force }
            }
            if ($Apply -and (Test-Path $oldProgress)) { Remove-Item $oldProgress }
        }
        elseif ($hasEpub) {
            if (Test-Path $epubProgressPath) {
                Write-Host "    [SKIP] $epubProgressPath already exists" -ForegroundColor Yellow
            } else {
                Write-Host "    [EPUB] -> $epubProgressPath (last_index = $val)"
                if ($Apply) {
                    @{ last_index = [int]$val } | ConvertTo-Json | Set-Content $epubProgressPath -Encoding UTF8
                    Remove-Item $oldProgress
                }
            }
        }
        else {
            Write-Host "    [SKIP] unknown mode, keeping progress.txt" -ForegroundColor Yellow
        }
    }
    else {
        # no progress.txt
        if ($hasCsv -and $hasEpub) {
            $csvInit = $csvInitialProgress[$rname]
            if ($null -eq $csvInit) { $csvInit = 0 }
            if (-not (Test-Path $csvProgressPath)) {
                Write-Host "  [dual] init CSV=$csvInit -> $csvProgressPath"
                if ($Apply) { Set-Content -Path $csvProgressPath -Value $csvInit -Encoding ASCII }
            }
            if (-not (Test-Path $epubProgressPath)) {
                Write-Host "  [dual] init EPUB=0 -> $epubProgressPath"
                if ($Apply) {
                    [System.IO.File]::WriteAllText($epubProgressPath, (@{ last_index = 0 } | ConvertTo-Json), $utf8NoBom)
                }
            }
        }
        elseif ($hasCsv) {
            if (-not (Test-Path $csvProgressPath)) {
                Write-Host "  [CSV] no progress.txt, init 0 -> $csvProgressPath"
                if ($Apply) { Set-Content -Path $csvProgressPath -Value "0" -Encoding ASCII }
            }
        }
        elseif ($hasEpub) {
            if (-not (Test-Path $epubProgressPath)) {
                Write-Host "  [EPUB] no progress.txt, init 0 -> $epubProgressPath"
                if ($Apply) {
                    @{ last_index = 0 } | ConvertTo-Json | Set-Content $epubProgressPath -Encoding UTF8
                }
            }
        }
    }

    # 5. build manifest
    if (Test-Path $booksDir) {
        $epubs = Get-ChildItem $booksDir -Filter *.epub | Sort-Object Name
        if ($epubs.Count -gt 0) {
            $manifest = @()
            $i = 1
            foreach ($e in $epubs) {
                $manifest += [ordered]@{
                    index = $i
                    file  = $e.Name
                    title = $e.Name
                }
                $i++
            }
            $manifestPath = Join-Path $booksDir "manifest.json"
            Write-Host "  [manifest] $($epubs.Count) epub -> $manifestPath"
            if ($Apply) {
                [System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 4), $utf8NoBom)
            }
        }
    }
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "=== Dry-run done. No file written. ===" -ForegroundColor Yellow
    Write-Host "Run:  .\migrate.ps1 -Apply" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "=== Migration done. ===" -ForegroundColor Green
}