# RSS Manager - STATUS

**Last updated**: 2026-11-07
**Rollback anchor**: `a80c8bf` (pre-fix baseline)

## Overview
- Purpose: Manage RSS learning repositories (EPUB/CSV to RSS)
- Entry: webui\server.py -> http://127.0.0.1:8767
- Start: python webui\server.py  (or double-click webui\start.bat)

## Key paths
| Purpose | Path |
|---|---|
| Workspace root | E:\2_Assets\E2_1 RSS |
| Web UI | RSS-master-main\webui |
| Config | RSS-master-main\repos.json |
| Sync script | RSS-master-main\sync.ps1 |
| Tests | RSS-master-main\webui\test_all.py |
| Archive | RSS-master-main\_archive |

## Done
- 2026-11-07 Fixed server.py P0/P1 (11 places): push timeout, hardcoded root, mkdir, empty workflow, gear task branch, write_json lock, GET safe default, health feed, health yellow
- 2026-11-07 repos.json: added bbc-6-minutes-english to all 5 gears
- 2026-11-07 Cleanup: removed bak2/bak3/test_api.py, archived migrate.ps1
- 2026-11-07 Track test_all.py (was ignored by webui/test_*.py rule)

## TODO
- [ ] slugify fallback for CJK labels (index.html, low)
- [ ] health_check.suggestions fill (server.py, low)
- [ ] _net_cache lock (server.py, low)

## Requirements
- Windows + PowerShell 7+
- Python 3.x
- gh CLI (for health check)
- git

## Commands
- Start:    python webui\server.py
- Test:     python webui\test_all.py
- Rollback: git -C "E:\2_Assets\E2_1 RSS\RSS-master-main" reset --hard a80c8bf

## Notes
- .gitignore ignores webui/*.bak*, webui/*.broken, webui/test_*.py
- test_all.py has ! exception in .gitignore
- Gear switch overwrites cron fields; git commit first