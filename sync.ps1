param([switch]$Apply)

$root = "E:\2_Assets\E2_1 RSS"
$masterFile = Join-Path $root "_master\repos.json"
if (-not (Test-Path $masterFile)) {
    $masterFile = Join-Path $root "_epub_csv_master\repos.json"
}
if (-not (Test-Path $masterFile)) {
    $masterFile = "E:\2_Assets\E2_1 RSS\_epub_csv_master\repos.json"
}

$master = Get-Content $masterFile -Raw -Encoding UTF8 | ConvertFrom-Json
$owner = $master.owner
$defaults = $master.defaults
$SQ = [char]39

foreach ($repoName in $master.repos.PSObject.Properties.Name) {
    $repoCfg = $master.repos.$repoName
    $repoPath = Join-Path $root $repoName

    if (-not (Test-Path $repoPath)) { continue }
    Write-Host "== $repoName ==" -ForegroundColor Cyan

    $isTaskRepo = $false
    if ($repoCfg.PSObject.Properties.Name -contains "tasks" -and $repoCfg.tasks -and $repoCfg.tasks.Count -gt 0) { $isTaskRepo = $true }

    if ($isTaskRepo) {
        foreach ($task in $repoCfg.tasks) {
            $wfFile  = $task.workflow
            $cronVal = $task.cron
            $ymlPath = Join-Path $repoPath ".github\workflows\$wfFile"
            Write-Host "  [$($task.id)] $wfFile -> cron: $cronVal"
            if ($Apply -and (Test-Path $ymlPath)) {
                $text = Get-Content $ymlPath -Raw -Encoding UTF8
                $pattern = "(?m)^\s*- cron: .*$"
                $replacement = "    - cron: ${SQ}$cronVal${SQ}"
                $text = $text -replace $pattern, $replacement
                [System.IO.File]::WriteAllText($ymlPath, $text, [System.Text.UTF8Encoding]::new($false))
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
            feed = [ordered]@{ title = $feedTitle; description = $feedDesc; link = "https://github.com/$owner/$repoName"; rss_size = $rssSize }
            epub = [ordered]@{ reading_speed = $speed; image_base_url = "https://raw.githubusercontent.com/$owner/$repoName/main/image/" }
            csv = [ordered]@{ source_file = $srcFile; has_header = $hasHeader }
        }
        $configPath = Join-Path $repoPath "config\config.json"
        $epubCron = if ($repoCfg.cron.epub) { $repoCfg.cron.epub } else { "0 0 * * 1" }
        $csvCron  = if ($repoCfg.cron.csv)  { $repoCfg.cron.csv }  else { "0 0 * * 4" }

        Write-Host "  epub cron -> $epubCron | csv cron -> $csvCron"
        if ($Apply) {
            New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null
            [System.IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 6), [System.Text.UTF8Encoding]::new($false))
            foreach ($pair in @(@("epub-to-rss.yml", $epubCron), @("csv-to-rss.yml", $csvCron))) {
                $yml = Join-Path $repoPath ".github\workflows\$($pair[0])"
                if (Test-Path $yml) {
                    $text = Get-Content $yml -Raw -Encoding UTF8
                    $pattern = "(?m)^\s*- cron: .*$"
                    $replacement = "    - cron: ${SQ}$($pair[1])${SQ}"
                    $text = $text -replace $pattern, $replacement
                    [System.IO.File]::WriteAllText($yml, $text, [System.Text.UTF8Encoding]::new($false))
                }
            }
        }
    }
}