#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动化回归测试：启动 server，打真实 HTTP 请求，验证响应。
用法：python test_api.py
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8765"
WEBUI = Path(__file__).parent

passed = 0
failed = 0


def call(method, path, body=None):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return None, str(e)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {detail}")


def wait_for_server(timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        code, _ = call("GET", "/api/config")
        if code == 200:
            return True
        time.sleep(0.5)
    return False


def main():
    print("=== 启动 server ===")
    proc = subprocess.Popen(
        ["python", "server.py"],
        cwd=str(WEBUI),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if not wait_for_server():
            print("❌ Server 未启动")
            return 1

        print("\n=== 测试 GET /api/config ===")
        code, data = call("GET", "/api/config")
        check("状态码 200", code == 200)
        check("含 owner", isinstance(data, dict) and "owner" in data)
        check("含 repos", isinstance(data, dict) and "repos" in data)
        check("含 gears", isinstance(data, dict) and "gears" in data)
        repo_count = len(data.get("repos", {}))
        check(f"仓库数 = 14", repo_count == 14, f"实际 {repo_count}")

        print("\n=== 测试 GET /api/status ===")
        code, data = call("GET", "/api/status")
        check("状态码 200", code == 200)
        check("含 14 个仓库", isinstance(data, dict) and len(data) == 14)

        print("\n=== 测试 GET /api/repo-info/<普通仓库> ===")
        code, data = call("GET", "/api/repo-info/computer-engineering")
        check("状态码 200", code == 200)
        check("有 epub 字段", "epub" in data)
        check("有 csv 字段", "csv" in data)
        check("有 tasks 字段(空)", data.get("tasks") == [])

        print("\n=== 测试 GET /api/repo-info/<任务仓库> ===")
        code, data = call("GET", "/api/repo-info/applied-foreign-lang")
        check("状态码 200", code == 200)
        tasks = data.get("tasks", [])
        check("有 2 个任务", len(tasks) == 2, f"实际 {len(tasks)}")
        if tasks:
            t0 = tasks[0]
            for key in ["id", "label", "lang", "cron", "batch_size", "total", "progress"]:
                check(f"任务字段 {key}", key in t0)

        print("\n=== 测试 GET /api/health-all ===")
        code, data = call("GET", "/api/health-all")
        check("状态码 200", code == 200)
        check("含 14 个仓库健康数据", isinstance(data, dict) and len(data) == 14)
        # 检查第一个仓库的字段
        first = next(iter(data.values()))
        for key in ["actions", "git", "progress", "feed", "network", "level", "suggestions"]:
            check(f"健康字段 {key}", key in first)

        print("\n=== 测试 POST /api/task-config (dry) ===")
        # 拿当前配置
        code, cfg = call("GET", "/api/config")
        original = cfg["repos"]["applied-foreign-lang"]["tasks"][0]

        # 改 batch_size 为原值（无副作用）
        code, resp = call("POST", "/api/task-config/applied-foreign-lang/study-en", {
            "batch_size": original["batch_size"]
        })
        check("状态码 200", code == 200)
        check("返回 ok=True", resp and resp.get("ok") is True)

        print("\n=== 测试 GET /api/preview-task ===")
        code, data = call("GET", "/api/preview-task/applied-foreign-lang/study-en?from=0&count=3")
        check("状态码 200", code == 200)
        check("返回 3 条", isinstance(data, list) and len(data) == 3)
        if data:
            check("每条有 index/title", "index" in data[0] and "title" in data[0])

        print(f"\n=== 汇总 ===")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        return 0 if failed == 0 else 1

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())