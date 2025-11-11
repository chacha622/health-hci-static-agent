# -*- coding: utf-8 -*-
"""
Health-HCI PhD Agent (综合方案C)
- 学术站点（EURAXESS / FindAPhD / jobs.ac.uk / Academic Positions / Academic Transfer / PhDpositions.dk / Jobbnorge / OeAD / Scholarship Cafe / SIGCHI / ETH CDHI）
- 社交站点（Twitter via Nitter RSS、LinkedIn via RSSHub(公开搜索)）
- 统一输出: public/data/latest.json
- 仅输出“新增或更新”的Top10（含CSV片段），并保留全量items
- 自动生成“摘要 summary + 匹配评分 + 关键词 + 合作/基金判定 + 近半年研究方向线索 + 代表论文(可选)”
"""

import os, re, json, csv, time, math, hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
import feedparser
import requests

# ---------- 可自定义偏好 ----------
PROFILE_KEYWORDS = [
    # 你的画像关键词（可与前端localStorage合并，这里用于服务器侧评分）
    "health hci", "digital health", "medical ux", "patient experience",
    "health communication", "information design", "assistive", "human-centered ai",
    "clinical", "hospital", "health informatics", "patient engagement", "ai chatbot"
]

REGION_PREFER = ["Australia", "Switzerland", "Netherlands", "Finland", "Sweden", "Norway", "Denmark", "Austria", "Germany", "UK", "Ireland", "France", "Italy", "Spain"]
SCORE_KEYWORD_HIT = 8
SCORE_TITLE_HIT = 10
SCORE_REGION_BONUS = 5
SCORE_FUNDED_BONUS = 15
SCORE_SOCIAL_BONUS = 4   # 社交源信号加分

# 搜索关键词（Twitter/LinkedIn）
SOCIAL_QUERIES = [
    '("phd position" OR "phd studentship") (health OR HCI OR "digital health" OR UX OR "human-centered AI")',
    '("phd" AND "human-computer interaction") (health OR medical OR clinical)'
]

# Nitter / RSSHub 可换镜像（可配环境变量）
NITTER_BASE = os.getenv("NITTER_BASE", "https://nitter.net")
RSSHUB_BASE = os.getenv("RSSHUB_BASE", "https://rsshub.app")  # 公共RSSHub镜像，若失效可更换

# 代表论文API（可选）：Semantic Scholar（无需token，但频率受限）
USE_SEMANTIC_SCHOLAR = True
SEM_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"


# ---------- 工具 ----------
def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()

def safe_get(url, timeout=15, headers=None):
    try:
        r = requests.get(url, timeout=timeout, headers=headers or {"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            return r.text
        return ""
    except Exception:
        return ""

def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", "ignore")).hexdigest()

def text_clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "", flags=re.S)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def score_item(item, social=False):
    title = (item.get("title") or "").lower()
    desc  = (item.get("description") or item.get("summary") or "").lower()
    where = (item.get("location") or "").lower()
    funding = (item.get("funding") or "").lower()
    score = 0
    for kw in PROFILE_KEYWORDS:
        k = kw.lower()
        if k in title:       score += SCORE_TITLE_HIT
        if k in desc:        score += SCORE_KEYWORD_HIT
    for rg in REGION_PREFER:
        if rg.lower() in where: score += SCORE_REGION_BONUS
    if any(tag in funding for tag in ["full", "funded", "stipend", "studentship", "scholarship"]):
        score += SCORE_FUNDED_BONUS
    if social:
        score += SCORE_SOCIAL_BONUS
    return score

def detect_collab(text):
    """简单规则：合作机构/医院关键词"""
    keys = ["hospital", "clinic", "nhs", "health service", "medical center", "institute", "industry", "company", "partner", "collaboration", "研究所", "医院", "企业", "产学研", "industry partner"]
    t = (text or "").lower()
    hit = [k for k in keys if k in t]
    return bool(hit), list(set(hit))

def detect_funding(text):
    t = (text or "").lower()
    # 简单判断
    if any(w in t for w in ["fully funded", "full funding", "studentship", "stipend", "scholarship", "tuition fee offset", "tuition waiver"]):
        return "Funded/Studentship/Stipend (detected)"
    if "self-funded" in t:
        return "Self-funded (detected)"
    return "TBD"

def extract_deadline(text):
    t = text_clean(text or "")
    # 常见截止日期模式
    m = re.search(r"(deadline|apply by|closing date)[^\d]*(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{1,2}-\d{1,2})", t, flags=re.I)
    return m.group(2) if m else "Rolling"

def make_summary(item):
    parts = []
    if item.get("university"): parts.append(item["university"])
    if item.get("lab"): parts.append(item["lab"])
    if item.get("supervisor"): parts.append(f"Supervisor: {item['supervisor']}")
    if item.get("keywords"): parts.append("Keywords: " + ", ".join(item["keywords"][:6]))
    if item.get("funding"): parts.append(f"Funding: {item['funding']}")
    if item.get("eligibility"): parts.append(f"Eligibility: {item['eligibility']}")
    if item.get("collab"): parts.append("Collab: " + ", ".join(item["collab"]))
    if item.get("deadline"): parts.append(f"Deadline: {item['deadline']}")
    return " | ".join(parts)

def try_papers(query, limit=2):
    """选做：根据标题/导师/学校拼接一个搜索，返回高热度代表论文（近五年优先）"""
    if not USE_SEMANTIC_SCHOLAR: return []
    try:
        q = quote_plus(query)
        url = f"{SEM_SCHOLAR_API}?query={q}&limit=5&fields=title,year,authors,citationCount,url"
        js = requests.get(url, timeout=12).json()
        if not js or "data" not in js: return []
        papers = sorted(js["data"], key=lambda x:(x.get("year",0), x.get("citationCount",0)), reverse=True)
        out = []
        for p in papers[:limit]:
            title = p.get("title","")
            cites = p.get("citationCount",0)
            year  = p.get("year","")
            url   = p.get("url","")
            out.append(f"{title} ({year}, cites={cites}) {url}")
        return out
    except Exception:
        return []

# ---------- 抓取器实现 ----------

def parse_rss(url, tag_name, social=False):
    items = []
    try:
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = text_clean(getattr(e, "title", ""))
            link  = getattr(e, "link", "")
            summ  = text_clean(getattr(e, "summary", "") or getattr(e, "description", ""))
            item = {
                "id": md5(link or title),
                "title": title,
                "link": link,
                "description": summ,
                "source": tag_name,
                "social": social,
            }
            # 轻量抽取
            item["funding"] = detect_funding(title + " " + summ)
            item["deadline"] = extract_deadline(title + " " + summ)
            # 尝试抽取地点/大学/导师（简单规则，可后续加站点模板）
            m_uni = re.search(r"(University|Universität|Université|Universiteit|University of [A-Z][a-z]+)", title + " " + summ)
            item["university"] = m_uni.group(0) if m_uni else ""
            m_sup = re.search(r"(Prof\.?\s*[A-Z][a-zA-Z\-]+|Dr\.?\s*[A-Z][a-zA-Z\-]+)", summ)
            item["supervisor"] = m_sup.group(0) if m_sup else ""
            # 关键词
            kws = []
            for kw in PROFILE_KEYWORDS:
                if kw.lower() in (title + " " + summ).lower(): kws.append(kw)
            item["keywords"] = sorted(list(set(kws)))
            # 合作
            flag, hits = detect_collab(summ)
            item["collab"] = hits if flag else []
            # 匹配评分
            item["score"] = score_item(item, social=social)
            # 代表论文（用标题+大学做查询）
            if item["university"]:
                item["papers"] = try_papers(f"{item['university']} {title}")[:2]
            else:
                item["papers"] = []
            item["summary"] = make_summary(item)
            items.append(item)
    except Exception:
        pass
    return items

def parse_html_list(url, tag_name, pattern=r'<a\s+href="([^"]+)"[^>]*>(.*?)</a >', base=None):
    """简单HTML解析（Scholarship Cafe 等），只做关键词筛选"""
    html = safe_get(url, timeout=15)
    items = []
    for m in re.finditer(pattern, html, flags=re.I|re.S):
        link = m.group(1)
        title = text_clean(m.group(2))
        if base and link.startswith("/"): link = base + link
        text = title.lower()
        if not any(kw in text for kw in ["phd", "studentship"]): 
            continue
        if not any(kw in text for kw in ["health","medical","clinic","hci","ux","assistive","human-centered","digital"]):
            continue
        item = {
            "id": md5(link or title),
            "title": title,
            "link": link,
            "description": "",
            "source": tag_name,
            "social": False,
            "funding": "TBD",
            "deadline": "Rolling",
            "university": "",
            "supervisor": "",
            "keywords": [],
            "collab": [],
        }
        item["score"] = score_item(item)
        item["papers"] = []
        item["summary"] = make_summary(item)
        items.append(item)
    return items

def gather_sources():
    out = []

    # --- 学术/官方 ---
    # ETH CDHI
    out += parse_rss("https://www.c4dhi.org/feed/", "ETH CDHI")

    # FindAPhD: RSS(示例关键词)
    faphd_qs = [
        "health%20HCI", "digital%20health%20UX", "assistive%20technology%20HCI",
        "human-centred%20AI%20health", "medical%20UX"
    ]
    for q in faphd_qs:
        out += parse_rss(f"https://www.findaphd.com/phds/rss/?Keywords={q}", "FindAPhD")

    # EURAXESS（支持RSS，使用关键词）
    eur_qs = [
        "digital%20health%20PhD", "human-computer%20interaction%20health",
        "assistive%20technology%20PhD"
    ]
    for q in eur_qs:
        out += parse_rss(f"https://euraxess.ec.europa.eu/rss/calls?keywords={q}", "EURAXESS")

    # jobs.ac.uk
    out += parse_rss("https://www.jobs.ac.uk/search/?keywords=phd+health+HCI&sort=relevance&format=rss", "jobs.ac.uk")

    # Academic Positions
    out += parse_rss("https://academicpositions.com/find-jobs/rss?positions=phd&keywords=health%20HCI%20digital%20health%20UX", "Academic Positions")

    # Academic Transfer（NL）
    out += parse_rss("https://www.academictransfer.com/en/search-rss/?keywords=phd%20digital%20health%20hci", "Academic Transfer")

    # PhDpositions.dk（DK）
    out += parse_rss("https://www.phd-positions.dk/rss/?s=health%20HCI", "PhDpositions.dk")

    # Jobbnorge（NO）
    out += parse_rss("https://www.jobbnorge.no/en/search?SearchText=PhD%20health%20HCI&format=rss", "Jobbnorge")

    # OeAD（AT）
    out += parse_rss("https://oead.at/en/rss", "OeAD Jobs")  # 全量，靠关键词筛选

    # Scholarship Cafe（HTML）
    out += parse_html_list("https://www.scholarshipscafe.com/search/label/PhD", "Scholarship Cafe", base="https://www.scholarshipscafe.com")

    # SIGCHI (job/announce feed镜像)
    out += parse_rss(f"{NITTER_BASE}/SIGCHI/rss", "SIGCHI")

    # --- 社交 ---
    for q in SOCIAL_QUERIES:
        url = f"{NITTER_BASE}/search/rss?f=tweets&q={quote_plus(q)}"
        out += parse_rss(url, "Twitter", social=True)

    # LinkedIn（RSSHub公开搜索，可能限流，失败会返回空）
    # 示例：/linkedin/jobs/search/PhD%20health%20HCI
    try:
        ln_url = f"{RSSHUB_BASE}/linkedin/jobs/search/{quote_plus('PhD health HCI digital health')}"
        out += parse_rss(ln_url, "LinkedIn", social=True)
    except Exception:
        pass

    return out

# ---------- 主流程 ----------
def main():
    items = gather_sources()

    # 清洗/过滤（确保健康/HCI相关）
    filtered = []
    for it in items:
        text = (it.get("title","") + " " + it.get("description","")).lower()
        if any(k in text for k in ["health","medical","clinic","hci","human-computer","ux","assistive","human-centered"]):
            filtered.append(it)

    # 去重（按link或title）
    uniq = []
    seen = set()
    for it in filtered:
        key = it.get("link") or it.get("title")
        k = md5(key)
        if k in seen: 
            continue
        seen.add(k)
        uniq.append(it)

    # 读取上一轮（用于“只提示新增/更新”）
    latest_path = os.path.join("public","data","latest.json")
    prev = {}
    if os.path.exists(latest_path):
        try:
            prev = json.load(open(latest_path,"r",encoding="utf-8"))
        except Exception:
            prev = {}

    prev_ids = set()
    if prev and "items" in prev:
        for p in prev["items"]:
            prev_ids.add(p.get("id") or md5(p.get("link","")))

    # 标记新增/更新
    for it in uniq:
        it["is_new"] = (it["id"] not in prev_ids)

    # 排序：是否资助/分数/时间（RSS通常按时间）
    def funded_rank(x):
        f = (x.get("funding") or "").lower()
        return 1 if any(w in f for w in ["funded","stipend","studentship","scholarship","full"]) else 0
    uniq_sorted = sorted(uniq, key=lambda x:(funded_rank(x), x.get("score",0)), reverse=True)

    # 生成Top10（只展示新增/更新优先）
    top_new = [x for x in uniq_sorted if x.get("is_new")] or uniq_sorted
    top10 = top_new[:10]

    # CSV片段
    csv_lines = [["University","Lab/School","Supervisor(s)","Topic keywords","Location","Funding/Stipend","Eligibility (International OK?)","Deadline","Link","Source"]]
    def csv_cell(x):
        return [
            x.get("university",""),
            x.get("lab",""),
            x.get("supervisor",""),
            ", ".join(x.get("keywords",[])[:8]),
            x.get("location",""),
            x.get("funding",""),
            x.get("eligibility",""),
            x.get("deadline",""),
            x.get("link",""),
            x.get("source",""),
        ]
    for r in top10:
        csv_lines.append(csv_cell(r))
    csv_text = "\n".join([",".join(['"'+c.replace('"','""')+'"' for c in row]) for row in csv_lines])

    data = {
        "generated_at": utcnow_iso(),
        "total_items": len(uniq_sorted),
        "by_source": {},
        "top10_new_or_updated": top10,
        "csv_block": csv_text,
        "items": uniq_sorted
    }

    # 统计各源数量
    by = {}
    for it in uniq_sorted:
        by[it["source"]] = by.get(it["source"],0)+1
    data["by_source"] = by

    os.makedirs(os.path.dirname(latest_path), exist_ok=True)
    with open(latest_path,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[fetch_all] wrote {latest_path} items: {len(uniq_sorted)}; new: {sum(1 for x in uniq_sorted if x.get('is_new'))}")
    for k,v in sorted(by.items(), key=lambda x:-x[1]):
        print(f"  - {k:22s}: {v}")

if __name__ == "__main__":
    main()
