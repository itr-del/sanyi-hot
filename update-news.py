#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三医改革热点观察 — 服务端新闻聚合脚本
仅使用 Python 标准库，无需安装任何第三方依赖。

功能：
  1. 通过 rss2json 免费接口聚合 Google News 上的"三医改革"相关新闻；
  2. 去重、分类（医疗/医保/医药/综合）、计算热度指数；
  3. 原子化写入 data.json，供网页优先读取（对国内访客最稳定）；
  4. 全部来源失败时写入内置演示数据，保证网页永远有内容可显示。

用法（由 cron 每 15 分钟调用一次，也可手动执行）：
  python3 update-news.py
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# ---------- 配置 ----------
SITE_DIR = os.environ.get("SANYI_SITE_DIR", "/var/www/sanyi-hot")
DATA_FILE = os.path.join(SITE_DIR, "data.json")
RSS_API = "https://api.rss2json.com/v1/api.json?rss_url="
QUERIES = ["三医改革", "医保改革", "药品集采", "医疗改革 公立医院"]
TIMEOUT = 15
UA = "Mozilla/5.0 (X11; Linux x86_64) SanyiHotNews/1.0"

CST = timezone(timedelta(hours=8))

# ---------- 内置演示数据（抓取全部失败时兜底） ----------
DEMO = [
    {"t": "三明医改经验推广现场推进会召开 部署下一阶段协同治理重点任务", "s": "会议肯定三明在医疗、医保、医药协同治理上的成效，要求各地因地制宜学习推广，健全\u201c三医\u201d协同发展和治理机制。", "src": "新华社", "h": 2, "c": "医疗", "heat": 97, "url": "https://www.gov.cn"},
    {"t": "第十一批国家组织药品集中采购中选结果全面落地执行", "s": "本批集采覆盖55种药品，中选价格平均降幅超五成，医保基金与群众用药负担进一步减轻。", "src": "人民日报", "h": 5, "c": "医药", "heat": 94, "url": "http://www.people.com.cn"},
    {"t": "DRG/DIP支付方式改革三年行动收官 统筹地区实现全覆盖", "s": "全国所有统筹地区均已开展DRG或DIP实际付费，医疗机构精细化运营管理意识明显增强。", "src": "国家医保局", "h": 8, "c": "医保", "heat": 92, "url": "https://www.nhsa.gov.cn"},
    {"t": "国家医保药品目录调整工作方案公布 创新药准入通道再优化", "s": "新版目录调整进一步优化评审规则，对符合条件的创新药实行谈判准入，惠及更多罕见病与肿瘤患者。", "src": "央视新闻客户端", "h": 11, "c": "医保", "heat": 90, "url": "https://www.cctv.com"},
    {"t": "公立医院医疗服务价格动态调整试点扩围至21个省份", "s": "试点地区建立以技术劳务价值为导向的价格形成机制，重点提高诊疗、手术、护理等项目价格。", "src": "健康报", "h": 15, "c": "医疗", "heat": 88, "url": "https://www.jkb.com.cn"},
    {"t": "医保基金飞行检查实现全国统筹地区全覆盖 守护群众\u201c救命钱\u201d", "s": "今年飞行检查聚焦骨科、血液净化、心血管内科等重点领域，运用大数据筛查精准锁定疑点。", "src": "中国医疗保险", "h": 19, "c": "医保", "heat": 86, "url": "https://www.nhsa.gov.cn"},
    {"t": "紧密型县域医共体建设提质扩面 基层就诊率稳步提升", "s": "全国县域医共体实现全覆盖，优质医疗资源下沉基层，群众就近就医获得感明显增强。", "src": "新华社", "h": 24, "c": "医疗", "heat": 84, "url": "https://www.gov.cn"},
    {"t": "创新药械多元支付保障机制试点启动 商保目录衔接提速", "s": "试点地区探索基本医保、商业健康险、医疗救助等多层次支付衔接，为高值创新药械建立可持续保障通道。", "src": "经济日报", "h": 28, "c": "医药", "heat": 82, "url": "http://www.ce.cn"},
    {"t": "跨省异地就医直接结算新增5种门诊慢特病病种", "s": "高血压、糖尿病等慢特病门诊费用跨省直接结算范围进一步扩大，备案流程持续简化。", "src": "光明日报", "h": 33, "c": "医保", "heat": 80, "url": "https://www.gmw.cn"},
    {"t": "集中带量采购中选药品质量监管专项行动方案印发", "s": "药监部门将对中选企业实施全覆盖监督检查和不良反应重点监测，确保\u201c降价不降质\u201d。", "src": "国家药监局", "h": 38, "c": "医药", "heat": 78, "url": "https://www.nmpa.gov.cn"},
    {"t": "公立医院薪酬制度改革试点深化 薪酬总量核定机制完善", "s": "试点医院探索年薪制与协议工资制，薪酬分配向临床一线、关键岗位倾斜。", "src": "健康报", "h": 44, "c": "医疗", "heat": 76, "url": "https://www.jkb.com.cn"},
    {"t": "长期护理保险制度试点城市扩围 失能评估标准实现统一", "s": "长护险试点城市新增15个，全国统一的失能等级评估标准落地，重度失能人员护理需求得到制度性保障。", "src": "人民日报", "h": 50, "c": "医保", "heat": 74, "url": "http://www.people.com.cn"},
    {"t": "国家医学中心与区域医疗中心建设扩容 优质资源下沉加速", "s": "新一批国家区域医疗中心项目落地中西部，重点补齐肿瘤、心血管、儿科等专科短板。", "src": "新华社", "h": 56, "c": "医疗", "heat": 72, "url": "https://www.gov.cn"},
    {"t": "药品追溯码医保结算扫码应用全面推开 基金监管更精准", "s": "定点医药机构结算时须扫描药品追溯码，实现\u201c一物一码\u201d全程可追溯，有效防范回流药等违规行为。", "src": "国家医保局", "h": 62, "c": "医药", "heat": 70, "url": "https://www.nhsa.gov.cn"},
    {"t": "分级诊疗信息化平台上线运行 双向转诊流程全面再造", "s": "平台打通上下级医疗机构信息系统，转诊申请、床位预约、结果互认一键完成。", "src": "央视新闻客户端", "h": 68, "c": "医疗", "heat": 68, "url": "https://www.cctv.com"},
    {"t": "中医药传承创新发展综合改革试点正式启动", "s": "试点地区将在中医药服务价格、医保支付、人才培养等方面先行先试，推动中西医协同发展。", "src": "光明日报", "h": 74, "c": "医疗", "heat": 66, "url": "https://www.gmw.cn"},
]

# ---------- 分类与热度 ----------
def categorize(text):
    if re.search(r"药|集采|耗材|药械|仿制|药监|招采|追溯码", text):
        return "医药"
    if re.search(r"医保|支付|DRG|DIP|异地就医|基金|长护|护理保险|结算|目录调整|商保|保险", text):
        return "医保"
    if re.search(r"医院|医疗|卫健|诊疗|医共体|分级|薪酬|医学中心|医改|三明|中医药|医师|卫生", text):
        return "医疗"
    return "综合"

HEAT_RULES = [
    (re.compile(r"三医|三明|医改"), 6), (re.compile(r"集采|带量采购"), 6),
    (re.compile(r"医保"), 5), (re.compile(r"DRG|DIP|支付方式"), 5),
    (re.compile(r"创新药|药械"), 5), (re.compile(r"基金|监管"), 4),
    (re.compile(r"分级诊疗|医共体"), 4), (re.compile(r"价格|薪酬"), 4),
    (re.compile(r"长护|护理保险"), 3), (re.compile(r"异地就医|结算"), 3),
]
AUTHORITATIVE = re.compile(r"新华|人民日报|央视|政府网|经济日报|光明日报")

def calc_heat(title, pub_dt, src):
    now = datetime.now(timezone.utc)
    hours = max(0.0, (now - pub_dt).total_seconds() / 3600.0)
    base = max(18.0, 95.0 - hours * 1.15)
    boost = 0
    for rx, v in HEAT_RULES:
        if rx.search(title):
            boost += v
    boost = min(boost, 12)
    w = 1.06 if AUTHORITATIVE.search(src) else 1.0
    return max(5, min(99, round((base + boost) * w)))

# ---------- 抓取 ----------
def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))

def fetch_rss(query):
    rss = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
           + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
    data = http_get_json(RSS_API + urllib.parse.quote(rss, safe=""))
    if data.get("status") != "ok":
        raise RuntimeError("rss2json status not ok")
    return data.get("items", [])

def parse_pub(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"&[^;]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def collect():
    raw = []
    ok_sources = 0
    for q in QUERIES:
        try:
            items = fetch_rss(q)
            raw.extend(items)
            ok_sources += 1
        except Exception as e:
            print("[warn] query %r failed: %s" % (q, e), file=sys.stderr)
    if ok_sources == 0 or len(raw) < 3:
        raise RuntimeError("too few items fetched (%d)" % len(raw))

    seen, out = set(), []
    for it in raw:
        title = (it.get("title") or "").strip()
        src = (it.get("author") or "").strip()
        m = re.match(r"^(.*)\s+-\s+([^-]+)$", title)
        if m:
            title = m.group(1).strip()
            if not src:
                src = m.group(2).strip()
        if not title:
            continue
        key = title[:22]
        if key in seen:
            continue
        seen.add(key)
        pub = parse_pub(it.get("pubDate") or "")
        desc = strip_html(it.get("description"))[:110]
        out.append({
            "t": title,
            "s": desc or "点击标题查看原文详情。",
            "src": src or "公开新闻源",
            "c": categorize(title + desc),
            "heat": calc_heat(title, pub, src),
            "url": it.get("link") or "#",
            "d": pub.astimezone(CST).isoformat(),
        })
    out.sort(key=lambda x: x["heat"], reverse=True)
    return out[:40]

def demo_items():
    now = datetime.now(CST)
    items = []
    for x in DEMO:
        d = now - timedelta(hours=x["h"])
        items.append({"t": x["t"], "s": x["s"], "src": x["src"], "c": x["c"],
                      "heat": x["heat"], "url": x["url"], "d": d.isoformat()})
    items.sort(key=lambda i: i["heat"], reverse=True)
    return items

# ---------- 写入（原子化，避免网页读到半个文件） ----------
def write_data(items, live):
    now = datetime.now(CST)
    payload = {
        "ts": int(time.time() * 1000),
        "updated": now.strftime("%m-%d %H:%M"),
        "live": live,
        "items": items,
    }
    os.makedirs(SITE_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)

def main():
    try:
        items = collect()
        write_data(items, live=True)
        print("[ok] live data written: %d items -> %s" % (len(items), DATA_FILE))
    except Exception as e:
        print("[error] live fetch failed: %s" % e, file=sys.stderr)
        # 若已有较新的 data.json（2 小时内），保留不动；否则写入演示数据兜底
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                prev = json.load(f)
            if time.time() * 1000 - prev.get("ts", 0) < 2 * 3600 * 1000:
                print("[ok] kept recent data.json")
                return
        except Exception:
            pass
        write_data(demo_items(), live=False)
        print("[ok] demo data written -> %s" % DATA_FILE)

if __name__ == "__main__":
    main()
