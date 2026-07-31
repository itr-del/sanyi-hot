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
import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

# ---------- 配置 ----------
SITE_DIR = os.environ.get("SANYI_SITE_DIR", "/var/www/sanyi-hot")
DATA_FILE = os.path.join(SITE_DIR, "data.json")
RSS_API = "https://api.rss2json.com/v1/api.json?rss_url="
QUERIES = ["三医改革", "医保改革", "药品集采", "医疗改革 公立医院"]
TIMEOUT = 5
UA = "Mozilla/5.0 (X11; Linux x86_64) SanyiHotNews/1.0"
# 国内服务器无法访问 Google News，默认跳过 Google News 抓取，仅使用监控信源
SKIP_GOOGLE = os.environ.get("SANYI_SKIP_GOOGLE", "1") == "1"

CST = timezone(timedelta(hours=8))

# ---------- 医疗改革领域关键词（用于过滤新闻） ----------
MEDICAL_REFORM_KEYWORDS = re.compile(
    r"三医|医改|医保|医疗|医药|集采|带量采购|药品|耗材|DRG|DIP|支付方式|"
    r"公立医院|分级诊疗|医共体|基层医疗|家庭医生|远程医疗|互联网\+医疗|"
    r"医保基金|异地就医|门诊慢特病|长期护理|护理保险|商业健康险|"
    r"创新药|药械|药品追溯|药监|药企|制药|仿制药|一致性评价|"
    r"医疗服务价格|诊疗费|手术费|护理费|薪酬改革|绩效|"
    r"医学中心|区域医疗|国家医学|临床|专科|"
    r"中医药|中西医|中医|中药|"
    r"三明|福建|青海|玉树|国药|"
    r"卫健委|卫生健康|卫生|"
    r"药品目录|医保目录|谈判准入|"
    r"药品集采|耗材集采|器械集采|"
    r"医保支付|医保结算|医保报销|"
    r"医疗信息化|电子病历|健康档案|"
    r"互联网医院|在线问诊|远程会诊|"
    r"健康中国|健康老龄化|"
    r"医联体|医共体|专科联盟|"
    r"医师|护士|药师|技师|"
    r"处方|药品|医院|诊所|"
    r"患者|就诊|住院|门诊|"
    r"体检|健康|预防|保健|"
    r"公共卫生|应急|防控|疫情|"
    r"医疗质量|医疗安全|医疗纠纷|"
    r"医疗技术|医疗设备|医疗耗材|"
    r"医疗机构|医疗市场|医疗产业|"
    r"医疗保险|医疗救助|医疗福利|"
    r"医疗改革|医疗体系|医疗制度|"
    r"医疗卫生|卫生事业|卫生工作|"
    r"卫生政策|卫生规划|卫生投入|"
    r"卫生人才|卫生队伍|卫生管理|"
    r"卫生服务|卫生保障|卫生监督|"
    r"卫生宣传|健康教育|健康促进|"
    r"爱国卫生|卫生城市|卫生县|"
    r"卫生防疫|卫生监督|卫生检验|"
    r"卫生科研|卫生教育|卫生培训|"
    r"卫生统计|卫生信息|卫生档案|"
    r"卫生财务|卫生装备|卫生房建|"
    r"卫生国际合作|卫生外事|"
    r"中医|中药|民族医|"
    r"中西医结合|中医现代化|"
    r"针灸|推拿|拔罐|艾灸|"
    r"草药|方剂|成药|饮片|"
    r"药膳|食疗|养生|保健|"
    r"康复|理疗|疗养|"
    r"老年|老年病|老年医学|"
    r"妇幼|妇女|儿童|"
    r"精神|心理|神经|"
    r"传染|感染|防疫|疫苗|"
    r"慢性病|慢病|高血压|糖尿病|"
    r"肿瘤|癌症|放疗|化疗|"
    r"心脑血管|心脏|血管|脑|"
    r"呼吸|肺|哮喘|慢阻肺|"
    r"消化|胃肠|肝|胆|胰|"
    r"泌尿|肾|透析|移植|"
    r"血液|贫血|白血病|淋巴瘤|"
    r"内分泌|甲状腺|糖尿病|"
    r"风湿|免疫|关节|骨|"
    r"皮肤|性病|梅毒|艾滋|"
    r"眼科|耳鼻喉|口腔|"
    r"创伤|骨折|关节|脊柱|"
    r"麻醉|疼痛|重症|急救|"
    r"影像|检验|病理|超声|"
    r"药学|临床药学|药物|"
    r"护理|护士|护工|"
    r"营养|膳食|肠内|肠外|"
    r"医保|新农合|城居保|"
    r"大病|重病|罕见病|"
    r"残疾|康复|辅助器具|"
    r"职业病|尘肺|中毒|"
    r"放射|核|电离|"
    r"环境|污染|生态|"
    r"职业|劳动|用工|社保|"
    r"生育|避孕|流产|不孕|"
    r"口腔|牙科|正畸|种植|"
    r"美容|整形|微整|"
    r"体检|筛查|早癌|基因|"
    r"精准|个体|靶向|免疫|"
    r"细胞|干细胞|再生|"
    r"基因|测序|编辑|治疗|"
    r"AI|人工智能|大数据|云计算|"
    r"机器人|手术|导航|辅助|"
    r"可穿戴|监测|物联网|"
    r"区块链|电子|身份|"
    r"互联网\+医疗|在线医疗|远程|"
    r"医联|医共|医体|"
    r"分级|双向|转诊|"
    r"家庭|签约|履约|"
    r"村医|乡村|乡镇|社区|"
    r"诊所|门诊部|医务室|卫生站|"
    r"医院|中心|卫生院|"
    r"专科|综合|中医|中西医|"
    r"三级|二级|一级|"
    r"床|住院|出院|转科|"
    r"手术|操作|治疗|"
    r"检查|检验|影像|病理|"
    r"药|处方|煎|服|"
    r"收费|结账|报销|"
    r"病历|记录|签字|"
    r"知情|同意|保密|"
    r"伦理|审查|监管|"
    r"感染|消毒|隔离|"
    r"废物|污水|处理|"
    r"安全|保卫|消防|"
    r"设备|器械|耗材|"
    r"采购|招标|中标|"
    r"物流|配送|存储|"
    r"维护|保养|校准|"
    r"计量|质控|标准|"
    r"培训|考核|继续|"
    r"档案|图书|情报|"
    r"科研|课题|论文|成果|"
    r"教学|实习|规培|"
    r"学术|会议|论坛|"
    r"交流|合作|援外|"
    r"义诊|扶贫|支援|"
    r"宣传|科普|义诊|"
    r"创建|评审|复审|"
    r"年报|统计|分析|"
    r"预算|决算|审计|"
    r"收费|价格|调整|"
    r"成本|核算|控制|"
    r"效率|效益|质量|"
    r"满意|投诉|改进|"
    r"患者|职工|社会|"
    r"领导|班子|队伍|"
    r"党建|廉政|行风|"
    r"文化|品牌|形象|"
    r"荣誉|奖励|先进|"
    r"责任|担当|作为|"
    r"改革|创新|发展|"
    r"稳定|和谐|平安|"
    r"学习|教育|培训|"
    r"贯彻|落实|执行|"
    r"组织|领导|协调|"
    r"宣传|引导|教育|"
    r"激励|约束|容错|"
    r"监督|检查|考核|"
    r"问责|追责|处分|"
)

def is_medical_reform_related(text):
    """判断新闻是否与医疗改革领域相关"""
    if not text:
        return False
    # 核心关键词（必须匹配至少一个）
    core_keywords = re.compile(
        r"三医|医改|医保|医疗|医药|集采|带量采购|药品|耗材|DRG|DIP|支付方式|"
        r"公立医院|分级诊疗|医共体|基层医疗|家庭医生|远程医疗|互联网\+医疗|"
        r"医保基金|异地就医|门诊慢特病|长期护理|护理保险|商业健康险|"
        r"创新药|药械|药品追溯|药监|药企|制药|仿制药|一致性评价|"
        r"医疗服务价格|诊疗费|手术费|护理费|薪酬改革|绩效|"
        r"医学中心|区域医疗|国家医学|临床|专科|"
        r"中医药|中西医|中医|中药|"
        r"三明|福建|青海|玉树|国药|"
        r"卫健委|卫生健康|卫生|"
        r"药品目录|医保目录|谈判准入|"
        r"医保支付|医保结算|医保报销|"
        r"医疗信息化|电子病历|健康档案|"
        r"互联网医院|在线问诊|远程会诊|"
        r"健康中国|健康老龄化|"
        r"医联体|医共体|专科联盟|"
        r"医师|护士|药师|技师|"
        r"处方|药品|医院|诊所|"
        r"患者|就诊|住院|门诊|"
        r"体检|健康|预防|保健|"
        r"公共卫生|应急|防控|疫情|"
        r"医疗质量|医疗安全|医疗纠纷|"
        r"医疗技术|医疗设备|医疗耗材|"
        r"医疗机构|医疗市场|医疗产业|"
        r"医疗保险|医疗救助|医疗福利|"
        r"医疗改革|医疗体系|医疗制度|"
        r"医疗卫生|卫生事业|卫生工作|"
        r"卫生政策|卫生规划|卫生投入|"
        r"卫生人才|卫生队伍|卫生管理|"
        r"卫生服务|卫生保障|卫生监督|"
        r"卫生宣传|健康教育|健康促进|"
        r"爱国卫生|卫生城市|卫生县|"
        r"卫生防疫|卫生监督|卫生检验|"
        r"卫生科研|卫生教育|卫生培训|"
        r"卫生统计|卫生信息|卫生档案|"
        r"卫生财务|卫生装备|卫生房建|"
        r"卫生国际合作|卫生外事|"
        r"中医|中药|民族医|"
        r"中西医结合|中医现代化|"
        r"针灸|推拿|拔罐|艾灸|"
        r"草药|方剂|成药|饮片|"
        r"药膳|食疗|养生|保健|"
        r"康复|理疗|疗养|"
        r"老年|老年病|老年医学|"
        r"妇幼|妇女|儿童|"
        r"精神|心理|神经|"
        r"传染|感染|防疫|疫苗|"
        r"慢性病|慢病|高血压|糖尿病|"
        r"肿瘤|癌症|放疗|化疗|"
        r"心脑血管|心脏|血管|脑|"
        r"呼吸|肺|哮喘|慢阻肺|"
        r"消化|胃肠|肝|胆|胰|"
        r"泌尿|肾|透析|移植|"
        r"血液|贫血|白血病|淋巴瘤|"
        r"内分泌|甲状腺|糖尿病|"
        r"风湿|免疫|关节|骨|"
        r"皮肤|性病|梅毒|艾滋|"
        r"眼科|耳鼻喉|口腔|"
        r"创伤|骨折|关节|脊柱|"
        r"麻醉|疼痛|重症|急救|"
        r"影像|检验|病理|超声|"
        r"药学|临床药学|药物|"
        r"护理|护士|护工|"
        r"营养|膳食|肠内|肠外|"
        r"医保|新农合|城居保|"
        r"大病|重病|罕见病|"
        r"残疾|康复|辅助器具|"
        r"职业病|尘肺|中毒|"
        r"放射|核|电离|"
        r"环境|污染|生态|"
        r"职业|劳动|用工|社保|"
        r"生育|避孕|流产|不孕|"
        r"口腔|牙科|正畸|种植|"
        r"美容|整形|微整|"
        r"体检|筛查|早癌|基因|"
        r"精准|个体|靶向|免疫|"
        r"细胞|干细胞|再生|"
        r"基因|测序|编辑|治疗|"
        r"AI|人工智能|大数据|云计算|"
        r"机器人|手术|导航|辅助|"
        r"可穿戴|监测|物联网|"
        r"区块链|电子|身份|"
        r"互联网\+医疗|在线医疗|远程|"
        r"医联|医共|医体|"
        r"分级|双向|转诊|"
        r"家庭|签约|履约|"
        r"村医|乡村|乡镇|社区|"
        r"诊所|门诊部|医务室|卫生站|"
        r"医院|中心|卫生院|"
        r"专科|综合|中医|中西医|"
        r"三级|二级|一级|"
        r"床|住院|出院|转科|"
        r"手术|操作|治疗|"
        r"检查|检验|影像|病理|"
        r"药|处方|煎|服|"
        r"收费|结账|报销|"
        r"病历|记录|签字|"
        r"知情|同意|保密|"
        r"伦理|审查|监管|"
        r"感染|消毒|隔离|"
        r"废物|污水|处理|"
        r"安全|保卫|消防|"
        r"设备|器械|耗材|"
        r"采购|招标|中标|"
        r"物流|配送|存储|"
        r"维护|保养|校准|"
        r"计量|质控|标准|"
        r"培训|考核|继续|"
        r"档案|图书|情报|"
        r"科研|课题|论文|成果|"
        r"教学|实习|规培|"
        r"学术|会议|论坛|"
        r"交流|合作|援外|"
        r"义诊|扶贫|支援|"
        r"宣传|科普|义诊|"
        r"创建|评审|复审|"
        r"年报|统计|分析|"
        r"预算|决算|审计|"
        r"收费|价格|调整|"
        r"成本|核算|控制|"
        r"效率|效益|质量|"
        r"满意|投诉|改进|"
        r"患者|职工|社会|"
        r"领导|班子|队伍|"
        r"党建|廉政|行风|"
        r"文化|品牌|形象|"
        r"荣誉|奖励|先进|"
        r"责任|担当|作为|"
        r"改革|创新|发展|"
        r"稳定|和谐|平安|"
        r"学习|教育|培训|"
        r"贯彻|落实|执行|"
        r"组织|领导|协调|"
        r"宣传|引导|教育|"
        r"激励|约束|容错|"
        r"监督|检查|考核|"
        r"问责|追责|处分|"
    )
    return bool(core_keywords.search(text))

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

def resolve_url(url, max_retries=3):
    """跟踪 Google News 包装链接的重定向，获取真实新闻 URL。
    优先通过 HTTP 重定向解析（服务器在海外时有效），
    失败时尝试 base64 解码（不依赖网络，适用于大陆服务器）。
    如果所有策略失败返回 None，调用方应过滤掉该条目。"""
    if not url or "news.google.com/rss/articles/" not in url:
        return url

    # 策略1: 通过 HEAD 请求获取重定向 Location（不跟随重定向）
    for attempt in range(max_retries):
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    raise urllib.error.HTTPError(newurl, code, msg, headers, fp)
            opener = urllib.request.build_opener(NoRedirect)
            req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
            opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                real = e.headers.get("Location", "")
                if real and not real.startswith("https://news.google.com"):
                    return real
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
                continue
        break

    # 策略2: 跟随重定向获取最终 URL
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            final_url = resp.geturl()
            if final_url and not final_url.startswith("https://news.google.com"):
                return final_url
    except Exception:
        pass

    # 策略3: 尝试 base64 解码 Google News 文章 ID（不依赖网络）
    try:
        match = re.search(r"/articles/([A-Za-z0-9_-]+)$", url)
        if match:
            encoded = match.group(1)
            # 尝试多种解码方式
            for prefix in ["", "CBMi", "CBMiq", "CBMiK2", "CBMiK", "CBM"]:
                if prefix and not encoded.startswith(prefix):
                    continue
                rest = encoded[len(prefix):] if prefix else encoded
                for padding in ["", "=", "=="]:
                    try:
                        padded = rest.replace("-", "+").replace("_", "/") + padding
                        decoded = base64.b64decode(padded)
                        # 查找 URL 模式
                        url_match = re.search(b"(https?://[^\\s\\x00-\\x1f]+)", decoded)
                        if url_match:
                            real = url_match.group(1).decode("utf-8", errors="ignore")
                            if real and not real.startswith("https://news.google.com"):
                                return real
                    except Exception:
                        continue
    except Exception:
        pass

    # 所有策略失败
    return None

def collect():
    if SKIP_GOOGLE:
        print("[info] skip google news (SANYI_SKIP_GOOGLE=1)", file=sys.stderr)
        return []
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
        url = resolve_url(it.get("link") or "#")
        if url is None:
            print("[warn] failed to resolve Google News URL, skipping: %s" % it.get("link"), file=sys.stderr)
            continue
        out.append({
            "t": title,
            "s": desc or "点击标题查看原文详情。",
            "src": src or "公开新闻源",
            "c": categorize(title + desc),
            "heat": calc_heat(title, pub, src),
            "url": url,
            "d": pub.astimezone(CST).isoformat(),
        })
    out.sort(key=lambda x: x["heat"], reverse=True)
    out = [i for i in out if is_medical_reform_related(i["t"])]
    return out[:40]

# ---------- 监控信源（自定义网站/RSS/微信公众号） ----------
MONITORS_FILE = os.path.join(SITE_DIR, "monitors.json")

def load_monitors():
    """读取管理员配置的监控信源列表"""
    try:
        with open(MONITORS_FILE, encoding="utf-8") as f:
            mons = json.load(f)
        return [m for m in mons if m.get("enabled", True)]
    except Exception:
        return []

class LinkExtractor(HTMLParser):
    """从 HTML 页面提取文章链接和标题"""
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []
        self._in_a = False
        self._href = ""
        self._text = ""
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            href = d.get("href", "")
            if href and not href.startswith(("javascript:", "#", "mailto:")):
                self._in_a = True
                self._href = href
                self._text = ""
    def handle_data(self, data):
        if self._in_a:
            self._text += data
    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            title = self._text.strip()
            if title and len(title) > 4:
                url = urllib.parse.urljoin(self.base_url, self._href)
                self.links.append({"title": title, "url": url})

def fetch_rss_direct(url, source_name):
    """直接解析 RSS/Atom XML feed（不经过 rss2json）"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        xml_data = resp.read()
    root = ET.fromstring(xml_data)
    items = []
    # 支持 RSS 2.0 和 Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    # RSS 2.0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = strip_html(item.findtext("description") or "")[:110]
        pub_str = item.findtext("pubDate") or ""
        if title and link:
            pub = parse_pub(pub_str) if pub_str else datetime.now(timezone.utc)
            items.append({
                "t": title, "s": desc or "点击标题查看原文。",
                "src": source_name, "c": categorize(title + desc),
                "heat": calc_heat(title, pub, source_name),
                "url": link, "d": pub.astimezone(CST).isoformat()
            })
    # Atom
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href", "") if link_el is not None else ""
        desc = strip_html(entry.findtext("{http://www.w3.org/2005/Atom}summary") or "")[:110]
        pub_str = entry.findtext("{http://www.w3.org/2005/Atom}published") or entry.findtext("{http://www.w3.org/2005/Atom}updated") or ""
        if title and link:
            pub = parse_pub(pub_str) if pub_str else datetime.now(timezone.utc)
            items.append({
                "t": title, "s": desc or "点击标题查看原文。",
                "src": source_name, "c": categorize(title + desc),
                "heat": calc_heat(title, pub, source_name),
                "url": link, "d": pub.astimezone(CST).isoformat()
            })
    return items[:15]

def fetch_web_list(url, source_name):
    """解析政府/新闻网站的列表页，提取文章标题和链接"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        html = resp.read().decode("utf-8", "ignore")
    parser = LinkExtractor(url)
    parser.feed(html)
    items = []
    seen_urls = set()
    seen_titles = set()
    
    # 获取源站域名，只保留同域链接
    base_domain = urllib.parse.urlparse(url).netloc.lower()
    
    def is_same_domain(href):
        """判断链接是否属于同一域名"""
        if href.startswith(("javascript:", "#", "mailto:")):
            return False
        parsed = urllib.parse.urlparse(href)
        link_domain = parsed.netloc.lower()
        if not link_domain:
            return True
        return link_domain == base_domain
    
    def is_article_link(href, title):
        """判断是否为文章页链接"""
        if any(skip in href.lower() for skip in ["faxing", "javascript", "logo", "banner", "index.html", "/col/"]):
            return False
        if re.search(r"/art/\d{4}/", href) or re.search(r"/\d{4}/\d{4}/", href):
            return True
        if len(title) < 6 or len(title) > 100:
            return False
        nav_keywords = ["首页", "返回", "更多", "新闻", "关于我们", "联系我们", "友情链接", "网站地图"]
        if any(kw in title for kw in nav_keywords):
            return False
        return True
    
    # 收集文章链接
    article_links = []
    for link_info in parser.links:
        href = link_info.get("url", "")
        title = link_info["title"]
        if not is_same_domain(href):
            continue
        if is_article_link(href, title):
            article_links.append((href, title))
    
    # 去重
    seen_urls_dedup = set()
    unique_links = []
    for href, title in article_links:
        if href not in seen_urls_dedup:
            seen_urls_dedup.add(href)
            unique_links.append((href, title))
    article_links = unique_links[:12]
    
    print(f"[DBG] 健康报: article_links count={len(article_links)}")
    for idx, (link_url, title) in enumerate(article_links):
        if link_url in seen_urls:
                    continue
        seen_urls.add(link_url)
        
        real_title = None
        try:
            req = urllib.request.Request(link_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                page_html = resp.read().decode("utf-8", "ignore")
            title_match = re.search(r'<title[^>]*>(.*?)</title>', page_html, re.I|re.S)
            if title_match:
                raw_title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                raw_title = re.split(r'[－——]{1,2}.*$', raw_title)[0].strip()
                raw_title = re.split(r'_+.*$', raw_title)[0].strip()
                raw_title = re.split(r'\s*[-|]\s*[^-|]+$', raw_title)[0].strip()
                parts = raw_title.split()
                if len(parts) > 2 and all(len(p) <= 10 for p in parts[:2]):
                    raw_title = ' '.join(parts[2:]).strip()
                if raw_title and 8 <= len(raw_title) <= 100:
                    real_title = raw_title
        except Exception:
            pass
        
        if not real_title:
            real_title = title if len(title) >= 8 else None
            if real_title:
                real_title = re.sub(r'[-_—|].*$', '', real_title).strip()
                real_title = re.split(r'[－——]{1,2}.*$', real_title)[0].strip()
            if real_title and (len(real_title) < 8 or len(real_title) > 100):
                real_title = None
        
        if not real_title:
            continue
        if real_title in seen_titles:
            continue
        seen_titles.add(real_title)
        
        if not re.search(r"[\u4e00-\u9fff]{4,}", real_title):
            continue
        if not is_medical_reform_related(real_title):
            continue
        
        pub = datetime.now(timezone.utc)
        items.append({
            "t": real_title, "s": "来源：" + source_name + "，点击标题查看原文。",
            "src": source_name, "c": categorize(real_title),
            "heat": calc_heat(real_title, pub, source_name),
            "url": link_url, "d": pub.astimezone(CST).isoformat()
        })
        if len(items) >= 15:
            break
    
    # 如果详情页抓取失败，尝试直接用链接文本
    if len(items) < 5:
        for link_info in parser.links:
            title = link_info["title"]
            link_url = link_info["url"]
            if not title or not link_url or link_url in seen_urls:
                continue
            if len(title) < 6 or len(title) > 100:
                continue
            if not re.search(r"[\u4e00-\u9fff]{4,}", title):
                continue
            if any(skip in link_url for skip in ["faxing", "javascript", "#", "logo", "banner"]):
                continue
            seen_urls.add(link_url)
            items.append({
                "t": title, "s": "来源：" + source_name + "，点击标题查看原文。",
                "src": source_name, "c": categorize(title),
                "heat": calc_heat(title, datetime.now(timezone.utc), source_name),
                "url": link_url, "d": datetime.now(CST).isoformat()
            })
            if len(items) >= 15:
                break
    return items


def collect_monitors():
    """抓取所有已启用的监控信源"""
    mons = load_monitors()
    if not mons:
        return []
    all_items = []
    for m in mons:
        name = m.get("name", "自定义信源")
        mtype = m.get("type", "rss")
        url = m.get("url", "")
        if not url:
            continue
        try:
            if mtype in ("rss", "wechat"):
                items = fetch_rss_direct(url, name)
            else:
                items = fetch_web_list(url, name)
            # 对 RSS 源也进行医疗改革领域过滤
            if mtype in ("rss", "wechat"):
                filtered = [i for i in items if is_medical_reform_related(i["t"])]
                print("[monitor] %s (%s): %d items (filtered from %d)" % (name, mtype, len(filtered), len(items)))
                items = filtered
            else:
                print("[monitor] %s (%s): %d items" % (name, mtype, len(items)))
            all_items.extend(items)
        except Exception as e:
            print("[warn] monitor %s failed: %s" % (name, e), file=sys.stderr)
    return all_items

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
    # 先抓取监控信源（独立于 Google News，国内服务器也能抓政府网站）
    monitor_items = collect_monitors()

    try:
        items = collect()
        # 合并监控信源结果（去重）
        seen_urls = set(x["url"] for x in items)
        for mi in monitor_items:
            if mi["url"] not in seen_urls:
                items.append(mi)
                seen_urls.add(mi["url"])
        items.sort(key=lambda x: x["heat"], reverse=True)
        write_data(items[:60], live=True)
        print("[ok] live data written: %d items (google=%d, monitors=%d) -> %s" % (
            len(items[:60]), len(items) - len(monitor_items), len(monitor_items), DATA_FILE))
    except Exception as e:
        print("[error] google news fetch failed: %s" % e, file=sys.stderr)
        # Google News 失败但监控信源有数据时，仍然使用监控信源数据
        if monitor_items:
            monitor_items.sort(key=lambda x: x["heat"], reverse=True)
            write_data(monitor_items[:40], live=True)
            print("[ok] monitor-only data written: %d items -> %s" % (len(monitor_items[:40]), DATA_FILE))
            return
        # 全部失败：若已有较新的 data.json（2 小时内），保留不动；否则写入演示数据兜底
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
