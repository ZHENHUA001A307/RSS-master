#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, subprocess, sys, time, urllib.request, urllib.error, os
from pathlib import Path

BASE = "http://127.0.0.1:8767"
WEBUI = Path(__file__).parent
MASTER = WEBUI.parent
ROOT = MASTER.parent
REPOS_JSON = MASTER / "repos.json"
TEST_REPO = "computer-engineering"
TEST_TASK_REPO = "applied-foreign-lang"
YML_PATH = ROOT / TEST_REPO / ".github" / "workflows" / "epub-to-rss.yml"
TASK_YML_PATH = ROOT / TEST_TASK_REPO / ".github" / "workflows" / "study_en.yml"

passed, failed = 0, 0
original_repos_json = ""

def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": f"HTTP {e.code}"}
    except Exception as e:
        return None, str(e)

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1; print(f"  [PASS] {name}")
    else:
        failed += 1; print(f"  [FAIL] {name} {detail}")

def wait_for_server(timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        code, _ = call("GET", "/api/config")
        if code == 200: return True
        time.sleep(0.5)
    return False

def setup():
    global original_repos_json
    if REPOS_JSON.exists():
        original_repos_json = REPOS_JSON.read_text(encoding="utf-8")
        cfg = json.loads(original_repos_json)
        # 强制重置测试靶子的状态，确保测试可以顺利进行
        cfg["repos"][TEST_REPO]["cron"] = {"epub": "0 0 * * 1,2,4", "csv": "0 0 * * 1,2,4"}
        
        cfg["repos"][TEST_TASK_REPO]["tasks"].append({
            "id": "test-del-task", "label": "Test Del", "type": "llm", 
            "workflow": "test.yml", "cron": "0 0 1 2 *", 
            "input_file": "corpus/test.csv", "progress_file": "progress/test.txt"
        })
        REPOS_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def teardown():
    if original_repos_json:
        REPOS_JSON.write_text(original_repos_json, encoding="utf-8")
        print("✅ 测试环境已恢复")

def main():
    setup()
    import socket
    print("=== 检查端口 8767 ===")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 8767))
        s.close()
        print("  [OK] 端口可用")
    except socket.error:
        print("  [WARN] 端口被占用，请手动关闭之前的 server.py 进程！")
        return 1

    print("=== 启动 server ===")
    proc = subprocess.Popen(["python", "server.py"], cwd=str(WEBUI), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        if not wait_for_server():
            print("❌ Server 无法启动，可能端口 8767 被占用！")
            return 1
            
        print("\n[1/7] 基础 API 验证...")
        code, cfg = call("GET", "/api/config")
        check("GET /api/config 成功", code == 200)
        
        print("\n[2/7] 档位切换测试 (0 档)...")
        code, resp = call("POST", "/api/apply-gear", {"gear": "0"})
        check("apply-gear(0) 成功", resp.get("ok") is True, str(resp))
        code, cfg = call("GET", "/api/config")
        check("cron 变更为 0 0 1 2 *", cfg["repos"][TEST_REPO]["cron"]["epub"] == "0 0 1 2 *")
        if YML_PATH.exists():
            yml_content = YML_PATH.read_text(encoding="utf-8")
            check("YAML 已被注释", "# schedule: (disabled)" in yml_content, f"实际内容:\n{yml_content[:200]}")
        else:
            check("YAML 文件存在", False, f"找不到 {YML_PATH}")

        print("\n[3/7] 档位切换测试 (2 档)...")
        code, resp = call("POST", "/api/apply-gear", {"gear": "2"})
        check("apply-gear(2) 成功", resp.get("ok") is True, str(resp))
        code, cfg = call("GET", "/api/config")
        check("cron 恢复为 0 0 * * 1,2,4", cfg["repos"][TEST_REPO]["cron"]["epub"] == "0 0 * * 1,2,4")
        if YML_PATH.exists():
            check("YAML 恢复 schedule", "# schedule: (disabled)" not in YML_PATH.read_text(encoding="utf-8"))

        print("\n[4/7] 任务配置修改测试...")
        code, resp = call("POST", f"/api/task-config/{TEST_TASK_REPO}/study-en", {"batch_size": 99, "cron": "0 0 * * 7"})
        check("修改任务成功", resp.get("ok") is True)
        code, cfg = call("GET", "/api/config")
        task = next((t for t in cfg["repos"][TEST_TASK_REPO]["tasks"] if t["id"] == "study-en"), {})
        check("batch_size 变为 99", task.get("batch_size") == 99)
        if TASK_YML_PATH.exists():
            check("YAML BATCH_SIZE 变为 99", "BATCH_SIZE: 99" in TASK_YML_PATH.read_text(encoding="utf-8"))

        print("\n[5/7] 任务进度重置测试...")
        code, resp = call("POST", f"/api/task-progress/{TEST_TASK_REPO}/study-en", {"value": 0})
        check("重置进度成功", resp.get("ok") is True)
        code, cfg = call("GET", "/api/repo-info/" + TEST_TASK_REPO)
        task = next((t for t in cfg.get("tasks", []) if t["id"] == "study-en"), {})
        check("任务进度变为 0", task.get("progress") == 0)

        print("\n[6/7] 删除任务测试 (删除 LLM 任务)...")
        code, resp = call("POST", f"/api/delete-csv-task/{TEST_TASK_REPO}/test-del-task")
        check("删除任务接口成功", resp.get("ok") is True)
        code, cfg = call("GET", "/api/config")
        tasks = cfg["repos"][TEST_TASK_REPO]["tasks"]
        check("任务已从配置中移除", not any(t["id"] == "test-del-task" for t in tasks))

        print("\n[7/7] 书籍重建测试...")
        code, resp = call("POST", f"/api/books/{TEST_REPO}/rebuild-manifest")
        check("重建 manifest 成功", resp.get("ok") is True)

        print(f"\n=== 测试汇总 ===")
        print(f"通过: {passed} / 失败: {failed}")
        return 0 if failed == 0 else 1
        
    finally:
        teardown()
        proc.terminate()
        try: proc.wait(timeout=3)
        except: proc.kill()

if __name__ == "__main__":
    sys.exit(main())