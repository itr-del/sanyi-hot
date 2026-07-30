#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sanyi-hot 监控信源管理员脚本
用于人工复核 SSL 证书失败的政府网站

用法：
  # 查看待复核列表
  python3 approve_monitors.py list

  # 批准某个域名（跳过 SSL 验证）
  python3 approve_monitors.py approve www.sanming.gov.cn

  # 批量批准
  python3 approve_monitors.py approve www.sanming.gov.cn www.xxx.gov.cn

  # 查看已批准列表
  python3 approve_monitors.py trusted

  # 撤销批准
  python3 approve_monitors.py revoke www.sanming.gov.cn
"""
import json
import os
import sys
from datetime import datetime

SITE_DIR = os.environ.get("SANYI_SITE_DIR", "/var/www/sanyi-hot")
PENDING_FILE = os.path.join(SITE_DIR, "monitors-pending.json")
TRUSTED_FILE = os.path.join(SITE_DIR, "monitors-trusted.json")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def list_pending():
    pending = load_json(PENDING_FILE, [])
    if not pending:
        print("✅ 没有待复核的网站")
        return
    print(f"📋 待复核网站（{len(pending)} 个）：")
    for i, item in enumerate(pending, 1):
        print(f"  {i}. {item.get('name', '未知')} ({item.get('url', '')})")
        print(f"     错误：{item.get('error', '')}")
        print(f"     时间：{item.get('time', '')}")


def list_trusted():
    trusted = load_json(TRUSTED_FILE, [])
    if not trusted:
        print("✅ 没有已批准的网站")
        return
    print(f"✓ 已批准网站（{len(trusted)} 个，将跳过 SSL 验证）：")
    for i, item in enumerate(trusted, 1):
        print(f"  {i}. {item.get('name', '未知')} ({item.get('url', '')})")
        print(f"     批准时间：{item.get('approved_at', '')}")


def approve(domains):
    trusted = load_json(TRUSTED_FILE, [])
    pending = load_json(PENDING_FILE, [])
    trusted_urls = {t["url"] for t in trusted}

    approved = []
    for domain in domains:
        found = None
        for p in pending:
            if domain in p.get("url", ""):
                found = p
                break

        if not found:
            found = {
                "name": domain,
                "url": f"https://{domain}" if not domain.startswith("http") else domain,
                "error": "手动批准",
                "time": ""
            }

        if found["url"] in trusted_urls:
            print(f"⚠️  {found['url']} 已经在批准列表中")
            continue

        found["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trusted.append(found)
        approved.append(found["url"])
        print(f"✅ 已批准：{found['name']} ({found['url']})")

    if approved:
        save_json(TRUSTED_FILE, trusted)
        print(f"\n✓ 共批准 {len(approved)} 个网站，下次抓取将跳过 SSL 验证")


def revoke(domains):
    trusted = load_json(TRUSTED_FILE, [])
    original_len = len(trusted)
    for domain in domains:
        trusted = [t for t in trusted if domain not in t.get("url", "")]

    if len(trusted) < original_len:
        save_json(TRUSTED_FILE, trusted)
        print(f"✅ 已撤销 {original_len - len(trusted)} 个网站的批准")
    else:
        print("⚠️ 没有找到匹配的网站")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    domains = sys.argv[2:]

    if action == "list":
        list_pending()
    elif action == "trusted":
        list_trusted()
    elif action == "approve":
        if not domains:
            print("❌ 请指定要批准的域名，例如：")
            print("   python3 approve_monitors.py approve www.sanming.gov.cn")
            sys.exit(1)
        approve(domains)
    elif action == "revoke":
        if not domains:
            print("❌ 请指定要撤销的域名")
            sys.exit(1)
        revoke(domains)
    else:
        print(f"❌ 未知命令：{action}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
