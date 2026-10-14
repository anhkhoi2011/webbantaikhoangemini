# -*- coding: utf-8 -*-
"""
GitHub Auto Deployer for webbantaikhoangemini
Tự động tạo repo webbantaikhoangemini và push toàn bộ mã nguồn lên GitHub của bạn
"""
import sys
import os
import subprocess
import urllib.request
import urllib.error
import json

REPO_NAME = "webbantaikhoangemini"
GITHUB_USER = "anhkhoi2011"
GIT_EXE = r"C:\Users\Admin\MinGit\cmd\git.exe"

def ensure_repo_created(token):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MinGit-CRM-Deployer"
    }
    
    # 1. Kiểm tra repo đã tồn tại chưa
    check_url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}"
    req = urllib.request.Request(check_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"✓ Repository '{REPO_NAME}' đã tồn tại trên GitHub.")
            return True
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"Lỗi kiểm tra repo: {e}")
            return False
            
    # 2. Nếu chưa có thì tự động tạo mới
    print(f"⚡ Đang tự động tạo mới repository '{REPO_NAME}' trên GitHub...")
    create_url = "https://api.github.com/user/repos"
    payload = json.dumps({
        "name": REPO_NAME,
        "description": "Hệ thống Bán Tài Khoản Google Gemini Pro 18 Tháng Tự Động & CRM Doanh Nghiệp",
        "private": False,
        "has_issues": True,
        "has_projects": True,
        "has_wiki": False
    }).encode("utf-8")
    
    req_create = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req_create) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✓ Tạo thành công repository: {data.get('html_url')}")
            return True
    except Exception as err:
        print(f"❌ Không thể tạo repository: {err}")
        return False

def push_code(token):
    cwd = os.path.dirname(os.path.abspath(__file__))
    remote_url = f"https://{GITHUB_USER}:{token}@github.com/{GITHUB_USER}/{REPO_NAME}.git"
    
    # Cấu hình remote origin
    subprocess.run([GIT_EXE, "remote", "remove", "origin"], cwd=cwd, capture_output=True)
    subprocess.run([GIT_EXE, "remote", "add", "origin", remote_url], cwd=cwd, check=True)
    
    # Push branch main
    print(f"🚀 Đang đẩy toàn bộ mã nguồn lên branch 'main' của https://github.com/{GITHUB_USER}/{REPO_NAME}...")
    res = subprocess.run([GIT_EXE, "push", "-u", "origin", "main", "--force"], cwd=cwd, capture_output=True, text=True)
    
    if res.returncode == 0:
        print(f"\n🎉 THÀNH CÔNG RỰC RỠ!")
        print(f"👉 Toàn bộ mã nguồn đã được tải lên: https://github.com/{GITHUB_USER}/{REPO_NAME}")
        return True
    else:
        print(f"❌ Lỗi khi push: {res.stderr}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    else:
        token = input("Nhập GitHub Personal Access Token (PAT) của bạn: ").strip()
        
    if not token:
        print("Vui lòng cung cấp GitHub Token!")
        sys.exit(1)
        
    if ensure_repo_created(token):
        push_code(token)
