param([switch]$Apply)

$root = "E:\2_Assets\E2_1 RSS"
$masterFile = Join-Path $root "_master\repos.json"

$master = Get-Content $masterFile -Raw -Encoding UTF8 | ConvertFrom-Json
$owner = $master.owner
$defaults = $master.defaults

$SQ = [char]39

foreach ($repoName in $master.repos.PSObject.Properties.Name) {
    $repoCfg = $master.repos.$repoName
    $repoPath = Join-Path $root $repoName

    if (-not (Test-Path $repoPath)) {
        Write-Host "[SKIP] $repoName not found"
        continue
    }

    Write-Host "== $repoName =="

    $isTaskRepo = $false
    if ($repoCfg.PSObject.Properties.Name -contains "tasks") {
        if ($repoCfg.tasks -and $repoCfg.tasks.Count -gt 0) {
            $isTaskRepo = $true
        }
    }

    if ($isTaskRepo) {
        foreach ($task in $repoCfg.tasks) {
            $taskId  = $task.id
            $wfFile  = $task.workflow
            $cronVal = $task.cron
            $ymlPath = Join-Path $repoPath ".github\workflows\$wfFile"

            Write-Host "  [$taskId] $wfFile -> cron: $cronVal"

            if ($Apply) {
                if (Test-Path $ymlPath) {
                    $text = Get-Content $ymlPath -Raw -Encoding UTF8
                    $pattern = "(?m)^\s*- cron: .*$"
                    $replacement = "    - cron: ${SQ}$cronVal${SQ}"
                    $text = $text -replace $pattern, $replacement
                    [System.IO.File]::WriteAllText($ymlPath, $text, [System.Text.UTF8Encoding]::new($false))
                    Write-Host "  [UPDATE] $wfFile"
                } else {
                    Write-Host "  [MISS] $wfFile"
                }
            }
        }
    } else {
        $feedTitle = if ($repoCfg.feed.title) { $repoCfg.feed.title } else { $repoName }
        $feedDesc  = if ($repoCfg.feed.description) { $repoCfg.feed.description } else { "" }
        $rssSize   = if ($repoCfg.feed.rss_size) { $repoCfg.feed.rss_size } else { $defaults.feed.rss_size }
        $speed     = if ($repoCfg.epub.reading_speed) { $repoCfg.epub.reading_speed } else { $defaults.epub.reading_speed }
        $hasHeader = if ($null -ne $repoCfg.csv.has_header) { $repoCfg.csv.has_header } else { $defaults.csv.has_header }
        $srcFile   = if ($repoCfg.csv.source_file) { $repoCfg.csv.source_file } else { $defaults.csv.source_file }

        $config = [ordered]@{
            feed = [ordered]@{
                title       = $feedTitle
                description = $feedDesc
                link        = "https://github.com/$owner/$repoName"
                rss_size    = $rssSize
            }
            epub = [ordered]@{
                reading_speed  = $speed
                image_base_url = "https://raw.githubusercontent.com/$owner/$repoName/main/image/"
            }
            csv = [ordered]@{
                source_file = $srcFile
                has_header  = $hasHeader
            }
        }

        $configJson = $config | ConvertTo-Json -Depth 6
        $configPath = Join-Path $repoPath "config\config.json"

        Write-Host "  config -> $configPath"

        $epubCron = if ($repoCfg.cron.epub) { $repoCfg.cron.epub } else { "0 0 * * 1" }
        $csvCron  = if ($repoCfg.cron.csv)  { $repoCfg.cron.csv }  else { "0 0 * * 4" }

        $epubYml = Join-Path $repoPath ".github\workflows\epub-to-rss.yml"
        $csvYml  = Join-Path $repoPath ".github\workflows\csv-to-rss.yml"

        Write-Host "  epub cron -> $epubCron"
        Write-Host "  csv  cron -> $csvCron"

        if ($Apply) {
            New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null
            [System.IO.File]::WriteAllText($configPath, $configJson, [System.Text.UTF8Encoding]::new($false))
            Write-Host "  [WRITE] config.json"

            foreach ($pair in @(@($epubYml, $epubCron), @($csvYml, $csvCron))) {
                $yml = $pair[0]
                $newCron = $pair[1]
                if (Test-Path $yml) {
                    $text = Get-Content $yml -Raw -Encoding UTF8
                    $pattern = "(?m)^\s*- cron: .*$"
                    $replacement = "    - cron: ${SQ}$newCron${SQ}"
                    $text = $text -replace $pattern, $replacement
                    [System.IO.File]::WriteAllText($yml, $text, [System.Text.UTF8Encoding]::new($false))
                    Write-Host "  [UPDATE] $(Split-Path $yml -Leaf)"
                }
            }
        }
    }
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "=== Dry-run done. No file written. ==="
    Write-Host "Run:  .\sync.ps1 -Apply"
} else {
    Write-Host ""
    Write-Host "=== Sync done. ==="
}