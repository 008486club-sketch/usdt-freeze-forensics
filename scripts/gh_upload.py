#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub API 批量上传 usdt-freeze-forensics 仓库文件"""
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.parse

TOKEN = sys.argv[1]
REPO = "008486club-sketch/usdt-freeze-forensics"
LOCAL_DIR = "/home/admin/yuezhi_tong/usdt-freeze-forensics"
API = "https://api.github.com"

# 排除文件
SKIP = {".git", "__pycache__", "boss_report.md", "friend_report.md"}

def api_request(method, path, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}

def get_sha(path):
    """获取远程文件 sha（存在则返回，不存在返回 None）"""
    enc = urllib.parse.quote(path, safe="/")
    status, data = api_request("GET", f"/repos/{REPO}/contents/{enc}")
    if status == 200:
        return data.get("sha")
    return None

def upload_file(local_path, repo_path):
    """上传单个文件（存在则更新）"""
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    body = {"message": f"upload {repo_path}", "content": content}
    sha = get_sha(repo_path)
    if sha:
        body["sha"] = sha
    enc = urllib.parse.quote(repo_path, safe="/")
    status, data = api_request("PUT", f"/repos/{REPO}/contents/{enc}", body)
    if status in (200, 201):
        print(f"  ✅ {repo_path}")
        return True
    print(f"  ❌ {repo_path}: {data.get('message', status)}")
    return False

def walk_and_upload():
    ok = True
    count = 0
    for root, dirs, files in os.walk(LOCAL_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fn in sorted(files):
            if fn in SKIP or fn.endswith(".pyc"):
                continue
            local_path = os.path.join(root, fn)
            rel = os.path.relpath(local_path, LOCAL_DIR).replace(os.sep, "/")
            if rel.startswith(".git/"):
                continue
            if not upload_file(local_path, rel):
                ok = False
            count += 1
            time.sleep(0.3)  # 避免限流
    return ok, count

if __name__ == "__main__":
    print("开始上传到", REPO)
    ok, count = walk_and_upload()
    print(f"\n完成: {count} 个文件", "✅" if ok else "⚠️ 部分失败")
    sys.exit(0 if ok else 1)
