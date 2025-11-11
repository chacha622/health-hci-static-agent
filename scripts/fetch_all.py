# -*- coding: utf-8 -*-
"""
Health-HCI PhD Agent v3 (学术源 + 社交源)
- 学术源：ETH CDHI / FindAPhD / EURAXESS / jobs.ac.uk / Academic Positions /
         Academic Transfer / PhDpositions.dk / Jobbnorge / OeAD / Scholarship Cafe / SIGCHI
- 社交源：Twitter via Nitter RSS / LinkedIn via RSSHub（公开搜索）
- 输出：public/data/latest.json（含 top10 + csv_block + by_source + items 全量）
- 新增：大学识别增强 / 资助&合作推断 / ai_summary / 代表论文(可选) / 匹配评分基线
"""

import os, re, json, hashlib
from urllib.parse import quote_plus
from datetime import datetime, timezone
import requests, feedparser

# ========== 偏好与常量 ==========
PROFILE_KEYWORDS = [
    "health hci","digital health","medical ux","patient experience",
    "health communication","information design","assistive","human-centered ai",
    "health informatics","patient engagement","ai chatbot","clinical","hospital"
]
REGION_PREFER = ["Australia","Switzerland","Netherlands","Finland","Sweden","Norway","Denmark","Austria","Germany","UK","Ireland","France","Italy","Spain"]
BASE_SCORE_ACADEMIC = 10       # 学术源基础分
BASE_SCORE_SOCIAL   = 4        # 社交源基础分
SCORE_TITLE_HIT     = 10
SCORE_DESC_HIT      = 8
SCORE_REGION_BONUS  = 5
SCORE_FUNDED_BONUS  = 15

SOCIAL_QUERIES = [
    '("phd position" OR "phd studentship") (health OR HCI OR "digital health" OR UX OR "human-centered AI")',
    '("phd" AND "human-computer interaction") (health OR medical OR clinical)'
]
NITTER_BASE = os.getenv("NITTER_BASE", "https://nitter.net")
RSSHUB_BASE = os.getenv("RSSHUB_BASE", "https://rsshub.app")

USE_SEMANTIC_SCHOLAR = True
SEM_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

# 覆盖欧洲+澳洲主流高校名，便于弱文本时识别
UNIVERSITY_HINTS = [
  # Switzerland
  "ETH Zurich","EPFL","University of Zurich","University of Bern","University of Basel","University of Geneva","University of Lausanne",
  # Nordics
  "KTH Royal Institute of Technology","Chalmers University of Technology","Lund University","Uppsala University","Aalto University",
  "University of Helsinki","University of Oslo","NTNU","UiT","University of Bergen","Technical University of Denmark","University of Copenhagen",
  # Netherlands
  "Delft University of Technology","Eindhoven University of Technology","University of Twente","University of Amsterdam","Leiden University",
  "Radboud University","Wageningen University","Utrecht University","VU Amsterdam",
  # DACH
  "LMU Munich","Technical University of Munich","RWTH Aachen","University of Freiburg","Heidelberg University","University of Hamburg",
  "University of Vienna","TU Wien","University of Graz",
  # UK / Ireland
  "University of Oxford","University of Cambridge","Imperial College London","University College London","UCL","University of Edinburgh",
  "University of Glasgow","University of Manchester","Trinity College Dublin","University of Birmingham","University of Leeds","University of Bristol",
  # Australia
  "ETH CDHI","University of Melbourne","Monash University","RMIT University","University of Sydney","UNSW","University of Queensland",
  "University of Adelaide","University of Technology Sydney","University of Western Australia"
]

def md5(s): return hashlib.md5((s or "").encode("utf-8","ignore")).hexdigest()
def now_iso(): return datetime.now(timezone.utc).isoformat()

def http_get(url, timeout=18, headers=None):
    try:
        r = requests.get(url, timeout=timeout, headers=headers or {"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200: return r.text
    except Exception:
        pass
    return ""

def clean_text(s):
    s = re.sub(r"<[^>]+>", " ", s or "", flags=re.S)
    return re.sub(r"\s+", " ", s).strip()

def try_semantic_papers(query, limit=2):
    if not USE_SEMANTIC_SCHOLAR: return []
    try:
        url = f"{SEM_SCHOLAR_API}?query={quote_plus(query)}&limit=5&fields=title,year,authors,citationCount,url"
        js = requests.get(url, timeout=12).json()
        if not js or "data" not in js: return []
        data = sorted(js["data"], key=lambda x:(x.get("year",0), x.get("citationCount",0)), reverse=True)
        out=[]
        for p in data[:limit]:
            out.append(f"{p.get('title','')} ({p.get('year','')}, cites={p.get('citationCount',0)}) {p.get('url','')}")
        return out
    except Exception:
        return []

def detect_university(text):
    t = text.lower()
    for u in UNIVERSITY_HINTS:
        if u.lower() in t: return u
    # 兜底：常见 “University of X”
    m = re.search(r"(University of [A-Z][A-Za-z\- ]+)", text)
    return m.group(1) if m else ""

def detect_funding(text, source):
    t = text.lower()
    if any(w in t for w in ["fully funded","full funding","studentship","stipend","scholarship","tuition waiver","tuition fee offset"]):
        return "Funded/Studentship/Stipend (detected)"
    if "self-funded" in t: return "Self-funded (detected)"
    # 对典型源做友好推断（FindAPhD/EURAXESS/jobs.ac.uk/Academic Positions 等常见 funded）
    if source in {"FindAPhD","EURAXESS","jobs.ac.uk","Academic Positions","Academic Transfer","Jobbnorge"}:
        return "Often funded on these portals (check details)"
    return "TBD"

def detect_deadline(text):
    m = re.search(r"(deadline|apply by|closing date)[^\d]*(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{1,2}-\d{1,2})", text, flags=re.I)
    return m.group(2) if m else "Rolling"

def detect_collab(text):
    keys = ["hospital","clinic","nhs","health service","medical center","institute","industry","company",
            "partner","collaboration","研究所","医院","企业","产学研"]
    t = text.lower()
    hits = sorted({k for k in keys if k in t})
    return (len(hits)>0), hits

def calc_score(item, social=False, source=""):
    base = BASE_SCORE_SOCIAL if social else BASE_SCORE_ACADEMIC
    title = (item.get("title") or "").lower()
    desc  = (item.get("description") or "").lower()
    where = (item.get("location") or "").lower()
    funding = (item.get("funding") or "").lower()
    score = base
    for kw in PROFILE_KEYWORDS:
        k = kw.lower()
        if k in title: score += SCORE_TITLE_HIT
        if k in desc:  score += SCORE_DESC_HIT
    for rg in REGION_PREFER:
        if rg.lower() in (where or ""): score += SCORE_REGION_BONUS
    if any(w in funding for w in ["funded","stipend","studentship","scholarship","full"]):
        score += SCORE_FUNDED_BONUS
    # 轻微偏向 ETH / EPFL / KTH 等
    uni = (item.get("university") or "").lower()
    if any(u.lower() in uni for u in ["eth","epfl","kth","aalto","tudelft","imperial","oxford","cambridge"]):
        score += 5
    return score

def make_summary(item):
    parts=[]
    if item.get("university"): parts.append(item["university"])
    if item.get("lab"): parts.append(item["lab"])
    if item.get("supervisor"): parts.append(f"Supervisor: {item['supervisor']}")
    if item.get("keywords"): parts.append("Keywords: " + ", ".join(item["keywords"][:6]))
    if item.get("funding"): parts.append(f"Funding: {item['funding']}")
    if item.get("eligibility"): parts.append(f"Eligibility: {item['eligibility']}")
    if item.get("collab"): parts.append("Collab: " + ", ".join(item["collab"]))
    if item.get("deadline"): parts.append(f"Deadline: {item['deadline']}")
    return " | ".join(parts)

def ai_summary(item):
    """模板式智能摘要（轻量，不依赖外部LLM）"""
    uni = item.get("university") or "University"
    sup = item.get("supervisor") or "Supervisor TBD"
    kws = ", ".join(item.get("keywords",[])[:5]) or "health HCI / digital health"
    fund = item.get("funding") or "Funding TBD"
    coll = ("; collaboration with " + ", ".join(item.get("collab"))) if item.get("collab") else ""
    src  = item.get("source") or "source"
    return f"PhD at {uni} — {kws}. {fund}{coll}. {sup}. ({src})"

# ========== RSS/HTML 抽取 ==========
def parse_rss(url, tag_name, social=False):
    items=[]
    feed = feedparser.parse(url)
    for e in feed.entries:
        title = clean_text(getattr(e,"title",""))
        link  = getattr(e,"link","")
        summ  = clean_text(getattr(e,"summary","") or getattr(e,"description",""))
        raw   = (title + " " + summ)
        item = {
            "id": md5(link or title),
            "title": title,
            "link": link,
            "description": summ,
            "source": tag_name,
            "social": social,
        }
        # 识别大学/导师/关键词/资助/截止/合作
        item["university"]  = detect_university(raw)
        m_sup = re.search(r"(Prof\.?\s*[A-Z][A-Za-z\-]+|Dr\.?\s*[A-Z][A-Za-z\-]+)", summ)
        item["supervisor"]  = m_sup.group(0) if m_sup else ""
        kws=[]
        for kw in PROFILE_KEYWORDS:
            if kw.lower() in raw.lower(): kws.append(kw)
        item["keywords"]    = sorted(list(set(kws)))
        item["funding"]     = detect_funding(raw, tag_name)
        item["deadline"]    = detect_deadline(raw)
        has_coll, hits      = detect_collab(raw)
        item["collab"]      = hits if has_coll else []
        item["eligibility"] = ""  # 可后续针对站点模板增强
        item["location"]    = ""  # 若站点有专门字段，可扩展
        # 分数与摘要
        item["score"]       = calc_score(item, social=social, source=tag_name)
        item["summary"]     = make_summary(item)
        item["ai_summary"]  = ai_summary(item)
        # 代表论文（尽量不阻塞）
        if item["university"]:
            try:
                item["papers"] = try_semantic_papers(f"{item['university']} {title}")[:2]
            except Exception:
                item["papers"]=[]
        else:
            item["papers"]=[]
        items.append(item)
    return items

def parse_html_simple(url, tag_name, base=None,
                      pattern=r'<a\s+href="([^"]+)"[^>]*>(.*?)</a >'):
    html = http_get(url, timeout=15)
    items=[]
    for m in re.finditer(pattern, html, flags=re.I|re.S):
        lnk = m.group(1); ttl = clean_text(m.group(2))
        if base and lnk.startswith("/"): lnk = base + lnk
        t = (ttl or "").lower()
        if not any(k in t for k in ["phd","studentship"]): continue
        if not any(k in t for k in ["health","medical","clinic","hci","ux","assistive","human-centered","digital"]): continue
        raw = ttl
        it = {
            "id": md5(lnk or ttl),
            "title": ttl,
            "link": lnk,
            "description": "",
            "source": tag_name,
            "social": False,
        }
        it["university"]  = detect_university(raw)
        it["supervisor"]  = ""
        it["keywords"]    = []
        it["funding"]     = detect_funding(raw, tag_name)
        it["deadline"]    = "Rolling"
        it["collab"]      = []
        it["eligibility"] = ""
        it["location"]    = ""
        it["score"]       = calc_score(it, social=False, source=tag_name)
        it["summary"]     = make_summary(it)
        it["ai_summary"]  = ai_summary(it)
        it["papers"]      = []
        items.append(it)
    return items

# ========== 聚合所有数据源 ==========
def gather_sources():
    out=[]

    # --- 学术站 ---
    out += parse_rss("https://www.c4dhi.org/feed/", "ETH CDHI")
    # FindAPhD（带关键词的RSS）
    for q in ["health%20HCI","digital%20health%20UX","assistive%20technology%20HCI",
              "human-centred%20AI%20health","medical%20UX"]:
        out += parse_rss(f"https://www.findaphd.com/phds/rss/?Keywords={q}", "FindAPhD")
    # EURAXESS
    for q in ["digital%20health%20PhD","human-computer%20interaction%20health","assistive%20technology%20PhD"]:
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
    # OeAD（AT，全量RSS，靠关键词过滤）
    out += parse_rss("https://oead.at/en/rss", "OeAD Jobs")
    # Scholarship Cafe（HTML 简单抓）
    out += parse_html_simple("https://www.scholarshipscafe.com/search/label/PhD", "Scholarship Cafe", base="https://www.scholarshipscafe.com")
    # SIGCHI via Nitter（SIGCHI 主页RSS）
    out += parse_rss(f"{NITTER_BASE}/SIGCHI/rss", "SIGCHI")

    # --- 社交 ---
    for q in SOCIAL_QUERIES:
        out += parse_rss(f"{NITTER_BASE}/search/rss?f=tweets&q={quote_plus(q)}", "Twitter", social=True)
    try:
        out += parse_rss(f"{RSSHUB_BASE}/linkedin/jobs/search/{quote_plus('PhD health HCI digital health')}", "LinkedIn", social=True)
    except Exception:
        pass

    return out

# ========== 主流程 ==========
def main():
    items = gather_sources()

    # 只保留健康/HCI相关
    filtered=[]
    for it in items:
        text = (it.get("title","") + " " + it.get("description","")).lower()
        if any(k in text for k in ["health","medical","clinic","hci","human-computer","ux","assistive","human-centered","digital"]):
            filtered.append(it)

    # 去重（按链接或标题）
    uniq, seen = [], set()
    for it in filtered:
        key = md5(it.get("link") or it.get("title"))
        if key in seen: continue
        seen.add(key)
        uniq.append(it)

    # 读取上一轮，做“新增/更新”标记
    latest_path = os.path.join("public","data","latest.json")
    prev_ids=set()
    if os.path.exists(latest_path):
        try:
            prev = json.load(open(latest_path,"r",encoding="utf-8"))
            for p in prev.get("items",[]):
                prev_ids.add(p.get("id") or md5(p.get("link","")))
        except Exception:
            pass
    for it in uniq:
        it["is_new"] = (it.get("id") not in prev_ids)

    # 排序（资助优先 + 分数）
    def funded_rank(x):
        f = (x.get("funding") or "").lower()
        return 1 if any(w in f for w in ["funded","stipend","studentship","scholarship","full"]) else 0
    uniq_sorted = sorted(uniq, key=lambda x:(funded_rank(x), x.get("score",0)), reverse=True)

    # Top10（优先新增）
    top_new = [x for x in uniq_sorted if x.get("is_new")] or uniq_sorted
    top10 = top_new[:10]

    # CSV
    csv_rows = [["University","Lab/School","Supervisor(s)","Topic keywords","Location","Funding/Stipend","Eligibility (International OK?)","Deadline","Link","Source"]]
    def row(x):
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
    for r in top10: csv_rows.append(row(r))
    csv_text = "\n".join([",".join(['"'+c.replace('"','""')+'"' for c in row]) for row in csv_rows])

    # 统计来源
    by = {}
    for it in uniq_sorted:
        by[it["source"]] = by.get(it["source"],0)+1

    data = {
        "generated_at": now_iso(),
        "total_items": len(uniq_sorted),
        "by_source": by,
        "top10_new_or_updated": top10,
        "csv_block": csv_text,
        "items": uniq_sorted
    }

    os.makedirs(os.path.dirname(latest_path), exist_ok=True)
    with open(latest_path,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[fetch_all] wrote {latest_path} items: {len(uniq_sorted)}; new: {sum(1 for x in uniq_sorted if x.get('is_new'))}")
    for k,v in sorted(by.items(), key=lambda x:-x[1]):
        print(f"  - {k:22s}: {v}")

if __name__ == "__main__":
    main()
