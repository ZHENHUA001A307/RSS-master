#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import http.server, json, os, re, subprocess, sys, threading, time, urllib.parse, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

WEBUI = Path(__file__).parent
MASTER = WEBUI.parent
ROOT = MASTER.parent
REPOS_JSON = MASTER / "repos.json"
HOST = "127.0.0.1"
PORT = 8767

_lock = threading.Lock()
_utf8 = "utf-8"
_net_cache = {"ms": None, "time": 0}

def read_json(path, default=None):
    try: return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        if default is not None: return default
        raise

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding=_utf8)

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=_utf8)

def run_ps(cmd, timeout=300):
    import tempfile, os
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(cmd)
            temp_path = f.name

        full = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", temp_path]
        # 彻底去掉 cwd 参数，继承父进程（已在 main() 中 os.chdir）
        r = subprocess.run(full, capture_output=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as ex:
        return -1, "", str(ex)
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass


def git_status(name):
    p = ROOT / name
    if not (p / ".git").exists(): return {"exists": False, "ahead": 0, "local": 0, "branch": ""}
    try:
        ahead = subprocess.run(["git", "-C", str(p), "rev-list", "--count", "@{u}..HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or "0"
        local = subprocess.run(["git", "-C", str(p), "status", "--porcelain"], capture_output=True, text=True, timeout=10).stdout
        branch = subprocess.run(["git", "-C", str(p), "branch", "--show-current"], capture_output=True, text=True, timeout=10).stdout.strip()
        return {"exists": True, "ahead": int(ahead) if ahead.isdigit() else 0, "local": len([l for l in local.splitlines() if l.strip()]), "branch": branch}
    except Exception as e:
        return {"exists": True, "ahead": 0, "local": 0, "branch": "", "error": str(e)}

def repo_info(name):
    p = ROOT / name
    info = {"exists": p.exists() and (p / ".git").exists(), "epub": {"total": 0, "progress": 0, "disabled": 0}, "csv": {"total": 0, "progress": 0}, "tasks": []}
    if not info["exists"]: return info

    cfg = read_json(REPOS_JSON, {})
    repo_cfg = cfg.get("repos", {}).get(name, {})

    if "tasks" in repo_cfg and repo_cfg["tasks"]:
        for task in repo_cfg["tasks"]:
            tid = task.get("id", "")
            input_rel = task.get("input_file", "")
            progress_rel = task.get("progress_file", "")
            total, progress = 0, 0
            if input_rel and (p / input_rel).exists():
                try: total = max(0, len([l for l in (p / input_rel).read_text(encoding="utf-8-sig").splitlines() if l.strip()]) - 1)
                except: pass
            if progress_rel and (p / progress_rel).exists():
                try: progress = int((p / progress_rel).read_text(encoding="ascii").strip() or 0)
                except: pass
            
            info["tasks"].append({
                "id": tid, "label": task.get("label", tid), "lang": task.get("lang", ""), 
                "cron": task.get("cron", ""), "batch_size": task.get("batch_size", 0), 
                "total": total, "progress": progress, "type": task.get("type", "llm")
            })
        return info

    mf = p / "books" / "manifest.json"
    if mf.exists():
        try: info["epub"]["total"] = len(read_json(mf, []))
        except: pass
    dis = p / "books" / "disabled.json"
    if dis.exists():
        try: info["epub"]["disabled"] = len(read_json(dis, []))
        except: pass
    ep = p / "progress.epub.json"
    if ep.exists():
        try: info["epub"]["progress"] = read_json(ep, {}).get("last_index", 0)
        except: pass
    src = p / "data" / "source.csv"
    if src.exists():
        try: info["csv"]["total"] = max(0, len([l for l in src.read_text(encoding="utf-8-sig").splitlines() if l.strip()]) - 1)
        except: pass
    cp = p / "data" / "progress.csv.txt"
    if cp.exists():
        try: info["csv"]["progress"] = int(cp.read_text(encoding="ascii").strip() or 0)
        except: pass
    return info

def write_progress(name, mode, value):
    p = ROOT / name
    value = int(value)
    if mode == "epub": write_json(p / "progress.epub.json", {"last_index": value}); return True
    if mode == "csv": write_text(p / "data" / "progress.csv.txt", str(value)); return True
    return False

def write_task_progress(name, task_id, value):
    p = ROOT / name
    cfg = read_json(REPOS_JSON, {})
    for task in cfg.get("repos", {}).get(name, {}).get("tasks", []):
        if task.get("id") == task_id:
            progress_rel = task.get("progress_file", "")
            if not progress_rel: return False
            target = p / progress_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(int(value)), encoding=_utf8)
            return True
    return False

def list_books(name):
    p = ROOT / name / "books"
    enabled = read_json(p / "manifest.json", []) if (p / "manifest.json").exists() else []
    disabled = read_json(p / "disabled.json", []) if (p / "disabled.json").exists() else []
    disk_files = {f.name for f in p.iterdir() if f.suffix.lower() == ".epub"} if p.exists() else set()
    manifest_files = {it.get("file") for it in enabled}
    disabled_files = {it.get("file") for it in disabled}
    orphans = [{"file": f, "title": f} for f in sorted(disk_files - manifest_files - disabled_files)]
    return {"enabled": enabled, "disabled": disabled, "orphans": orphans}

def rebuild_manifest(name):
    p = ROOT / name / "books"
    if not p.exists(): return False, "books 目录不存在"
    epubs = sorted([f for f in p.iterdir() if f.suffix.lower() == ".epub"], key=lambda f: f.name)
    write_json(p / "manifest.json", [{"index": i, "file": e.name, "title": e.name} for i, e in enumerate(epubs, 1)])
    return True, f"重建 {len(epubs)} 条"

def reorder_books(name, file_order):
    p = ROOT / name / "books"
    write_json(p / "manifest.json", [{"index": i, "file": fname, "title": fname} for i, fname in enumerate(file_order, 1)])
    return True

def disable_book(name, fname):
    p = ROOT / name / "books"
    mf = read_json(p / "manifest.json", []) if (p / "manifest.json").exists() else []
    dis = read_json(p / "disabled.json", []) if (p / "disabled.json").exists() else []
    new_mf = [it for it in mf if it.get("file") != fname]
    if len(new_mf) == len(mf): return False, "书不在启用列表"
    dis.append({"file": fname, "title": fname})
    for i, it in enumerate(new_mf, 1): it["index"] = i
    write_json(p / "manifest.json", new_mf); write_json(p / "disabled.json", dis)
    return True, ""

def enable_book(name, fname):
    p = ROOT / name / "books"
    if not (p / fname).exists(): return False, f"文件不存在: {fname}"
    mf = read_json(p / "manifest.json", []) if (p / "manifest.json").exists() else []
    dis = read_json(p / "disabled.json", []) if (p / "disabled.json").exists() else []
    if any(it.get("file") == fname for it in mf): return False, "书已在启用列表"
    mf.append({"index": len(mf) + 1, "file": fname, "title": fname})
    write_json(p / "manifest.json", mf); write_json(p / "disabled.json", [it for it in dis if it.get("file") != fname])
    return True, ""

def enable_all_orphans(name):
    p = ROOT / name / "books"
    mf = read_json(p / "manifest.json", []) if (p / "manifest.json").exists() else []
    dis = read_json(p / "disabled.json", []) if (p / "disabled.json").exists() else []
    disk_files = {f.name for f in p.iterdir() if f.suffix.lower() == ".epub"} if p.exists() else set()
    orphans = sorted(disk_files - {it.get("file") for it in mf} - {it.get("file") for it in dis})
    for fname in orphans: mf.append({"index": len(mf) + 1, "file": fname, "title": fname})
    write_json(p / "manifest.json", mf)
    return True, f"加入 {len(orphans)} 本"

def delete_book(name, fname):
    p = ROOT / name / "books"
    dis = read_json(p / "disabled.json", []) if (p / "disabled.json").exists() else []
    new_dis = [it for it in dis if it.get("file") != fname]
    if len(new_dis) == len(dis): return False, "书不在搁置列表"
    target = p / fname
    if target.exists():
        try: target.unlink()
        except Exception as e: return False, f"删文件失败: {e}"
    write_json(p / "disabled.json", new_dis)
    return True, ""

def preview(name, mode, from_index, count=5):
    p = ROOT / name; result = []
    if mode == "epub":
        mf = p / "books" / "manifest.json"
        if not mf.exists(): return result
        for item in read_json(mf, []):
            if item.get("index", 0) >= from_index:
                result.append({"index": item["index"], "title": item.get("title", item["file"])})
                if len(result) >= count: break
    elif mode == "csv":
        src = p / "data" / "source.csv"
        if not src.exists(): return result
        for i, line in enumerate(src.read_text(encoding="utf-8-sig").splitlines()):
            if i >= from_index and line.strip():
                result.append({"index": i, "title": line.split(",", 1)[0].strip().strip('"')})
                if len(result) >= count: break
    return result

def preview_task(name, task_id, from_index, count=5):
    p = ROOT / name; result = []
    cfg = read_json(REPOS_JSON, {})
    for task in cfg.get("repos", {}).get(name, {}).get("tasks", []):
        if task.get("id") == task_id:
            input_rel = task.get("input_file", "")
            if input_rel and (p / input_rel).exists():
                for i, line in enumerate((p / input_rel).read_text(encoding="utf-8-sig").splitlines()):
                    if i >= from_index and line.strip():
                        result.append({"index": i, "title": line.split(",", 1)[0].strip().strip('"')})
                        if len(result) >= count: break
            break
    return result

def update_task_config(name, task_id, fields):
    p = ROOT / name
    cfg = read_json(REPOS_JSON, {})
    repo_cfg = cfg.get("repos", {}).get(name, {})
    tasks = repo_cfg.get("tasks", [])
    target = next((t for t in tasks if t.get("id") == task_id), None)
    if not target: return False, '任务不存在', []

    for k in ['label', 'lang', 'cron', 'batch_size', 'slice_mode', 'input_file', 'progress_file', 'prompt_file', 'model_name']:
        if k in fields: target[k] = fields[k]

    write_json(REPOS_JSON, cfg)
    
    _wf = target.get('workflow', '')
    if not _wf:
        return False, f'task {task_id} workflow field is empty', []
    yml_path = p / '.github' / 'workflows' / _wf
    if not yml_path.exists(): return False, 'workflow 文件不存在', []

    ytext = yml_path.read_text(encoding='utf-8')
    if 'cron' in fields:
        ytext = re.sub(r"(?m)^(\s*- cron: )'[^']*'", lambda m: m.group(1) + "'" + fields['cron'] + "'", ytext)

    env_map = {'lang': 'LANG_CN', 'input_file': 'INPUT_FILE', 'progress_file': 'PROGRESS_FILE', 'prompt_file': 'PROMPT_FILE', 'slice_mode': 'SLICE_MODE', 'model_name': 'MODEL_NAME'}
    for f, env in env_map.items():
        if f in fields:
            ytext = re.sub(r'(?m)^(\s*' + env + r':\s*)(?:"[^"]*"|.*)$', r'\g<1>"' + fields[f] + '"', ytext)

    if 'batch_size' in fields:
        ytext = re.sub(r'(?m)^(\s*BATCH_SIZE:\s*)\d+(.*)$', r'\g<1>' + str(fields['batch_size']) + r'\g<2>', ytext)

    yml_path.write_text(ytext, encoding='utf-8')
    return True, f'已保存 {task_id}', []

def create_csv_task(name, fields):
    p = ROOT / name
    task_id = fields.get("id", "").strip()
    if not task_id or not re.match(r"^[a-z0-9][a-z0-9-]*$", task_id): return False, "ID 格式不正确", []
    cfg = read_json(REPOS_JSON, {})
    repo_cfg = cfg.get("repos", {}).get(name, {})
    tasks = repo_cfg.get("tasks", [])
    if any(t.get("id") == task_id for t in tasks): return False, "任务 id 已存在", []

    tpl_path = Path(__file__).parent / "templates" / "task-csv.yml.template"
    if not tpl_path.exists(): return False, "模板文件不存在", []

    tpl = tpl_path.read_text(encoding="utf-8")
    tpl = tpl.replace("__ID__", task_id).replace("__CRON__", fields.get("cron", "")).replace("__LANG__", fields.get("lang", ""))
    tpl = tpl.replace("__INPUT_FILE__", fields.get("input_file", "")).replace("__PROGRESS_FILE__", fields.get("progress_file", ""))

    (p / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    yml_path = p / ".github" / "workflows" / ("task-" + task_id + ".yml")
    if yml_path.exists(): return False, "workflow 文件已存在", []
    yml_path.write_text(tpl, encoding="utf-8")

    tasks.append({
        "id": task_id, "label": fields.get("label", ""), "lang": fields.get("lang", ""), "type": "csv",
        "workflow": "task-" + task_id + ".yml", "cron": fields.get("cron", ""),
        "input_file": fields.get("input_file", ""), "progress_file": fields.get("progress_file", "")
    })
    repo_cfg["tasks"] = tasks
    cfg["repos"][name] = repo_cfg
    write_json(REPOS_JSON, cfg)
    return True, "已创建", []

def delete_csv_task(name, task_id):
    p = ROOT / name
    cfg = read_json(REPOS_JSON, {})
    repo_cfg = cfg.get("repos", {}).get(name, {})
    tasks = repo_cfg.get("tasks", [])
    target = next((t for t in tasks if t.get("id") == task_id), None)
    if not target: return False, "任务不存在", []

    yml_path = p / ".github" / "workflows" / target.get("workflow", "task-" + task_id + ".yml")
    if yml_path.exists():
        dis_dir = p / ".github" / "workflows" / ".disabled"
        dis_dir.mkdir(parents=True, exist_ok=True)
        yml_path.rename(dis_dir / yml_path.name)

    repo_cfg["tasks"] = [t for t in tasks if t.get("id") != task_id]
    cfg["repos"][name] = repo_cfg
    write_json(REPOS_JSON, cfg)
    return True, "已删除", []

def apply_gear(gear):
    cfg = read_json(REPOS_JSON, {})
    if gear not in cfg.get("gears", {}):
        return False, "档位不存在"

    gear_map = cfg["gears"][gear]
    
    for name, repo_cfg in cfg["repos"].items():
        # 区分普通仓库和任务仓库
        is_task = "tasks" in repo_cfg and isinstance(repo_cfg["tasks"], list)
        
        if not is_task:
            # 处理普通仓库，防御性创建 cron 字典
            if "cron" not in repo_cfg or not isinstance(repo_cfg["cron"], dict):
                repo_cfg["cron"] = {}
            for mode in ["epub", "csv"]:
                old_cron = repo_cfg["cron"].get(mode, "")
                if old_cron == "0 0 1 1 *": continue
                if gear == "0":
                    repo_cfg["cron"][mode] = "0 0 1 2 *"
                else:
                    val = gear_map.get(name, {}).get(mode) if isinstance(gear_map.get(name), dict) else gear_map.get(name, old_cron)
                    if val: repo_cfg["cron"][mode] = val
        else:
            # 处理任务仓库
            repo_gear = gear_map.get(name)
            for task in repo_cfg["tasks"]:
                tid = task.get("id")
                old_cron = task.get("cron", "")
                if old_cron == "0 0 1 1 *": continue
                if gear == "0":
                    task["cron"] = "0 0 1 2 *"
                elif isinstance(repo_gear, dict) and tid in repo_gear:
                    task["cron"] = repo_gear[tid]

    cfg["current_gear"] = gear
    write_json(REPOS_JSON, cfg)
    code, out, err = run_ps(r".\sync.ps1 -Apply")
    state_out = apply_enabled_state()
    
    if code != 0:
        return False, f"sync.ps1 执行失败:\n{out}\n{err}"
    return True, out + "\n" + state_out


def apply_enabled_state():
    cfg = read_json(REPOS_JSON, {})
    output = []
    
    for name, repo_cfg in cfg.get("repos", {}).items():
        wf_cron = {}
        if "tasks" in repo_cfg:
            for t in repo_cfg["tasks"]:
                wf_cron[t.get("workflow")] = t.get("cron", "")
        else:
            wf_cron["epub-to-rss.yml"] = repo_cfg.get("cron", {}).get("epub", "")
            wf_cron["csv-to-rss.yml"] = repo_cfg.get("cron", {}).get("csv", "")

        for wf, current_cron in wf_cron.items():
            if not wf: continue
            path = ROOT / name / ".github" / "workflows" / wf
            if not path.exists(): continue
            
            text = path.read_text(encoding="utf-8")
            is_disabled = current_cron in ["0 0 1 2 *", "0 0 1 1 *"]
            
            if is_disabled:
                text = re.sub(r'^(\s*)schedule:\s*$', r'\1# schedule: (disabled)', text, flags=re.M)
                text = re.sub(r'^(\s*)(- cron:)', r'\1# \2', text, flags=re.M)
                output.append(f"[DISABLED] {name}/{wf}")
            else:
                # 先解注释
                text = re.sub(r'^(\s*)#\s*schedule:\s*\(disabled\)', r'\1schedule:', text, flags=re.M)
                text = re.sub(r'^(\s*)#\s*(- cron:)', r'\1\2', text, flags=re.M)
                # 再替换正确的 cron 值
                if current_cron:
                    text = re.sub(r"^(\s*- cron: )'[^']*'", lambda m: m.group(1) + "'" + current_cron + "'", text, flags=re.M)
                output.append(f"[ENABLED] {name}/{wf}")

            path.write_text(text, encoding="utf-8")
            
    return "\n".join(output)

def sync_progress(name):
    p = ROOT / name
    if not (p / ".git").exists(): return False, "非 git 仓库"
    subprocess.run(["git", "-C", str(p), "fetch", "origin", "main"], capture_output=True, timeout=60)
    cfg = read_json(REPOS_JSON, {})
    files = [t.get("progress_file") for t in cfg.get("repos", {}).get(name, {}).get("tasks", [])] if "tasks" in cfg.get("repos", {}).get(name, {}) else ["progress.epub.json", "data/progress.csv.txt"]
    ok_files = []
    for f in files:
        if not f: continue
        if subprocess.run(["git", "-C", str(p), "cat-file", "-e", f"origin/main:{f}"], capture_output=True).returncode == 0:
            if subprocess.run(["git", "-C", str(p), "checkout", "origin/main", "--", f], capture_output=True, timeout=30).returncode == 0:
                ok_files.append(f)
    return (True, "已同步") if ok_files else (False, "无进度文件")

def check_network():
    if _net_cache["ms"] and time.time() - _net_cache["time"] < 60: return _net_cache["ms"]
    try:
        start = time.time()
        if subprocess.run(["gh", "api", "rate_limit"], capture_output=True, timeout=15).returncode == 0:
            _net_cache["ms"] = int((time.time() - start) * 1000); _net_cache["time"] = time.time()
            return _net_cache["ms"]
    except: pass
    return None

def health_check(name, net_ms=None):
    p = ROOT / name
    res = {"actions": {"ok": None, "msg": ""}, "git": {"ok": None, "msg": "", "ahead": 0, "behind": 0, "dirty": 0}, "progress": {"ok": None, "msg": "", "tasks": []}, "feed": {"ok": None, "msg": ""}, "network": {"ok": net_ms is not None and net_ms < 3000, "msg": str(net_ms) + "ms" if net_ms else "超时"}, "level": "green", "suggestions": []}
    if not (p / ".git").exists(): return res

    try:
        r = subprocess.run(["gh", "run", "list", "--repo", f"ZHENHUA001A307/{name}", "--limit", "1", "--json", "conclusion,workflowName"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and json.loads(r.stdout or "[]"):
            latest = json.loads(r.stdout)[0]
            res["actions"]["ok"] = latest["conclusion"] == "success"
            res["actions"]["msg"] = f"{latest['workflowName']} ({latest['conclusion']})"
    except: pass

    try:
        r = subprocess.run(["git", "-C", str(p), "rev-list", "--left-right", "--count", "@{u}...HEAD"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split()
            res["git"]["behind"], res["git"]["ahead"] = int(parts[0]), int(parts[1])
        res["git"]["dirty"] = len([l for l in subprocess.run(["git", "-C", str(p), "status", "--porcelain"], capture_output=True, text=True).stdout.splitlines() if l.strip()])
        res["git"]["ok"] = res["git"]["ahead"] == 0 and res["git"]["behind"] == 0 and res["git"]["dirty"] == 0
        res["git"]["msg"] = "干净" if res["git"]["ok"] else f"未推:{res['git']['ahead']} 落后:{res['git']['behind']} 未提交:{res['git']['dirty']}"
    except: pass

    try:
        _feed = p / "feed.xml"
        res["feed"]["ok"] = _feed.exists()
        res["feed"]["msg"] = "exists" if _feed.exists() else "missing"
    except: pass

    try:
        cfg = read_json(REPOS_JSON, {})
        repo_cfg = cfg.get("repos", {}).get(name, {})
        is_diff = False
        
        wfs = [t.get("progress_file") for t in repo_cfg.get("tasks", [])] if "tasks" in repo_cfg else ["progress.epub.json", "data/progress.csv.txt"]
        for f in wfs:
            if not f: continue
            lp = p / f
            lv = lp.read_text(encoding="utf-8-sig").strip() if lp.exists() else "0"
            r = subprocess.run(["git", "-C", str(p), "show", f"origin/main:{f}"], capture_output=True, text=True)
            rv = r.stdout.strip() if r.returncode == 0 else "0"
            diff = lv != rv
            if diff: is_diff = True
            res["progress"]["tasks"].append({"label": f, "local": lv, "remote": rv, "diff": diff})
        
        res["progress"]["ok"] = not is_diff
        res["progress"]["msg"] = "不一致" if is_diff else "一致"
    except: pass

    _checks = [res["actions"]["ok"], res["git"]["ok"], res["progress"]["ok"]]
    if any(ok is False for ok in _checks):
        res["level"] = "red"
    elif any(ok is None for ok in _checks):
        res["level"] = "yellow"
    else:
        res["level"] = "green"
    return res

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        try:
            if isinstance(body, str): body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError): pass

    def _json(self, obj, code=200): self._send(code, json.dumps(obj, ensure_ascii=False))
    def _read_body(self):
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n).decode("utf-8") if n else ""
    def _parts(self): return [p for p in urllib.parse.urlparse(self.path).path.split("/") if p]

    def do_GET(self):
        parts = self._parts()
        if not parts:
            self._send(200, (Path(__file__).parent / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8"); return
        if parts == ["api", "config"]:
            self._json(read_json(REPOS_JSON, {"owner": "", "current_gear": "0", "defaults": {}, "gears": {}, "repos": {}})); return
        if parts == ["api", "status"]:
            _c = read_json(REPOS_JSON, {"repos": {}})
            self._json({name: git_status(name) for name in _c.get("repos", {})}); return
        if len(parts) == 3 and parts[1] == "repo-info": self._json(repo_info(parts[2])); return
        if len(parts) == 3 and parts[1] == "books": self._json(list_books(parts[2])); return
        if len(parts) == 4 and parts[1] == "preview": 
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._json(preview(parts[2], parts[3], int(q.get("from", ["0"])[0]), int(q.get("count", ["5"])[0]))); return
        if len(parts) == 4 and parts[1] == "preview-task":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._json(preview_task(parts[2], parts[3], int(q.get("from", ["0"])[0]), int(q.get("count", ["5"])[0]))); return
        if parts == ["api", "health-all"]:
            nm = check_network()
            self._json({n: health_check(n, nm) for n in read_json(REPOS_JSON).get("repos", {})}); return
        self._send(404, "not found")

    def do_POST(self):
        parts = self._parts(); body = self._read_body()
        try:
            if parts == ["api", "config"]: write_json(REPOS_JSON, json.loads(body)); self._json({"ok": True}); return
            if parts == ["api", "apply"]:
                c, o, e = run_ps(r".\sync.ps1 -Apply")
                self._json({"ok": c == 0, "output": o + "\n" + (apply_enabled_state() if c == 0 else "")}); return
            if parts == ["api", "apply-gear"]:
                ok, msg = apply_gear(json.loads(body).get("gear")); self._json({"ok": ok, "output": msg}); return
            if parts == ["api", "push"]:
                try:
                    script = self._push_script().replace("__ROOT__", str(ROOT))
                    c, o, e = run_ps(script, timeout=600)
                    self._json({"ok": c == 0, "output": o + "\n" + e})
                except Exception as ex:
                    self._json({"ok": False, "error": f"Push 异常: {str(ex)}"}, 500)
                return
            if len(parts) == 4 and parts[1] == "task-config":
                ok, msg, w = update_task_config(parts[2], parts[3], json.loads(body)); self._json({"ok": ok, "output": msg, "warnings": w}); return
            if len(parts) == 3 and parts[1] == "create-csv-task":
                ok, msg, w = create_csv_task(parts[2], json.loads(body)); self._json({"ok": ok, "output": msg, "warnings": w}); return
            if len(parts) == 4 and parts[1] == "delete-csv-task":
                ok, msg, w = delete_csv_task(parts[2], parts[3]); self._json({"ok": ok, "output": msg, "warnings": w}); return
            if len(parts) == 4 and parts[1] == "trigger-task":
                cfg = read_json(REPOS_JSON, {}); wf = next((t["workflow"] for t in cfg.get("repos", {}).get(parts[2], {}).get("tasks", []) if t["id"] == parts[3]), "")
                r = subprocess.run(["gh", "workflow", "run", wf, "--repo", f"ZHENHUA001A307/{parts[2]}"], capture_output=True, text=True)
                self._json({"ok": r.returncode == 0, "output": r.stdout}); return
            if len(parts) == 3 and parts[1] == "progress":
                self._json({"ok": write_progress(parts[2], json.loads(body).get("mode"), json.loads(body).get("value"))}); return
            if len(parts) == 4 and parts[1] == "task-progress":
                self._json({"ok": write_task_progress(parts[2], parts[3], json.loads(body).get("value"))}); return
            if len(parts) == 3 and parts[1] == "sync-progress":
                ok, msg = sync_progress(parts[2]); self._json({"ok": ok, "output": msg}); return
            if parts == ["api", "sync-progress-all"]:
                cfg = read_json(REPOS_JSON, {})
                out = [f"[{('OK' if (o := sync_progress(n))[0] else 'FAIL')}] {n}: {o[1]}" for n in cfg.get("repos", {})]
                self._json({"ok": True, "output": "\n".join(out), "summary": f"完成"}); return
            if len(parts) == 4 and parts[1] == "books":
                if parts[3] == "rebuild-manifest": ok, msg = rebuild_manifest(parts[2]); self._json({"ok": ok, "output": msg}); return
                if parts[3] == "reorder": reorder_books(parts[2], json.loads(body).get("files", [])); self._json({"ok": True}); return
                if parts[3] == "disable": ok, msg = disable_book(parts[2], json.loads(body).get("file")); self._json({"ok": ok, "output": msg}); return
                if parts[3] == "enable": ok, msg = enable_book(parts[2], json.loads(body).get("file")); self._json({"ok": ok, "output": msg}); return
                if parts[3] == "enable-all-orphans": ok, msg = enable_all_orphans(parts[2]); self._json({"ok": ok, "output": msg}); return
                if parts[3] == "delete": ok, msg = delete_book(parts[2], json.loads(body).get("file")); self._json({"ok": ok, "output": msg}); return
            self._send(404, "not found")
        except Exception as e: self._json({"ok": False, "error": str(e)}, 500)

    def _push_script(self):
        return r'''
$root = "__ROOT__"
Get-ChildItem -Path "$root" -Directory | Where-Object { (Test-Path "$($_.FullName)\.git") -and -not (Test-Path "$($_.FullName)\webui\server.py") } | ForEach-Object {
    $p = $_.FullName
    Write-Host "== $($_.Name) =="
    if ((Test-Path "$p\.git\rebase-merge") -or (Test-Path "$p\.git\rebase-apply")) { git -C $p rebase --abort 2>$null }
    git -C $p add -A
    git -C $p commit -m "Update from webui" 2>$null
    git -C $p pull --rebase origin main 2>$null
    if ($LASTEXITCODE -ne 0) {
        git -C $p rebase --abort 2>$null
        git -C $p push --force origin main 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "  [FORCED]" } else { Write-Host "  [FAIL]" }
    } else {
        git -C $p push 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "  [PUSHED]" } else { Write-Host "  [FAIL]" }
    }
}
'''


def main():
    os.chdir(str(MASTER))
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"RSS 管理工具已启动: http://{HOST}:{PORT}")
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()

if __name__ == "__main__": main()