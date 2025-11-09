#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, re, os, sys
from datetime import date, datetime
from urllib.parse import quote_plus

import feedparser

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "public", "data", "latest.json")

SOURCES = [
    {"name": "ETH CDHI", "region": "Switzerland", "type": "rss", "url": "https://www.c4dhi.org/feed/"},
    {"name": "FindAPhD: digital health HCI", "region": "Global", "type": "rss", "url": "https://www.findaphd.com/phds/rss/?keywords=" + quote_plus("digital health HCI")},
    {"name": "FindAPhD: health communication", "region": "Global", "type": "rss", "url": "https://www.findaphd.com/phds/rss/?keywords=" + quote_plus("health communication HCI")},
    {"name": "EURAXESS: digital health", "region": "Europe", "type": "rss", "url": "https://euraxess.ec.europa.eu/rss?search_api_fulltext=" + quote_plus("digital health PhD") + "&sort_by=search_api_relevance"},
    {"name": "EURAXESS: HCI", "region": "Europe", "type": "rss", "url": "https://euraxess.ec.europa.eu/rss?search_api_fulltext=" + quote_plus("human-computer interaction PhD") + "&sort_by=search_api_relevance"},
    {"name": "jobs.ac.uk: HCI health PhD", "region": "UK/Europe", "type": "rss", "url": "https://www.jobs.ac.uk/search/?keywords=" + quote_plus("PhD HCI health") + "&sort=score&format=rss"},
    {"name": "SIGCHI (Twitter RSS mirror)", "region": "Global", "type": "rss", "url": "https://nitter.net/SIGCHI/rss"}
]

KEYWORDS = {
    "must_any": ["health","digital health","medical","patient","clinical","care","assistive"],
    "hci_any": ["HCI","human-computer interaction","UX","human-centred","human-centered","interaction design","human-AI"],
    "funding_any": ["funded","fully funded","studentship","scholarship","stipend","tuition waiver"],
    "collab_any": ["hospital","clinical partner","NHS","industry partner","industry collaboration","health service"],
    "profile_keywords": [
        "health communication","digital health","doctor patient communication",
        "AI chatbot","conversational agent","self management","patient engagement",
        "health informatics","behavioral health","explainable AI","human AI collaboration",
        "medical terminology explanation","clinical UX","care pathway","patient experience",
        "AI for health","information design","communication design","information visualization",
        "data storytelling"
    ]
}

UNIV_RE = re.compile(r"(ETH Zürich|ETH Zurich|University of Melbourne|TU Delft|KTH|Aalto|DTU|UCL|UCD|Cardiff|TUM|RWTH|EPFL|UZH|Monash|UNSW)", re.I)

def _has_any(text, arr):
    if not text: return False
    t = text.lower()
    return any(k.lower() in t for k in arr)

def _hits(text, arr):
    if not text: return []
    t = text.lower()
    return [k for k in arr if k.lower() in t]

def _extract_deadline(text):
    if not text: return ""
    m = re.search(r"(\b20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b)", text)
    return m.group(1) if m else ""

def _score(item):
    t = (item.get("raw") or "").lower()
    s = 0
    if "eth zürich" in t or "eth zurich" in t: s += 40
    elif "university of melbourne" in t or " melbourne " in t: s += 30
    else: s += 20
    if "funding mentioned" in (item.get("funding") or ""): s += 20
    if "collaboration mentioned" in (item.get("collaboration") or "").lower(): s += 10
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", item.get("deadline","") or "")
    if m:
        from datetime import date
        y,mn,d = map(int, m.groups())
        try:
            delta = (date(y,mn,d) - date.today()).days
            if 0 <= delta <= 30: s += 10
        except: pass
    if (item.get("profile_hits") or "").strip(): s += 20
    return s

def fetch_all():
    items = []
    for src in SOURCES:
        d = feedparser.parse(src["url"])
        for e in d.entries[:80]:
            title = e.get("title","")
            summary = e.get("summary","")
            link = e.get("link","")
            txt = " ".join([title, summary])
            univ_m = UNIV_RE.search(txt)
            deadline = _extract_deadline(txt)
            obj = {
                "source": src["name"],
                "region": src["region"],
                "title": title,
                "summary": summary,
                "link": link,
                "raw": txt,
                "university": univ_m.group(1) if univ_m else src["name"],
                "funding": "Funding mentioned" if _has_any(txt, KEYWORDS["funding_any"]) else "",
                "collaboration": "Industry/Hospital collaboration mentioned" if _has_any(txt, KEYWORDS["collab_any"]) else "",
                "deadline": deadline,
            }
            if not (_has_any(txt, KEYWORDS["must_any"]) and _has_any(txt, KEYWORDS["hci_any"])):
                continue
            obj["profile_hits"] = ", ".join(_hits(txt, KEYWORDS["profile_keywords"]))
            obj["match_score"] = _score(obj)
            obj["match_reason"] = ("Profile match: " + obj["profile_hits"]) if obj["profile_hits"] else ""
            items.append(obj)
    items.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    # de-dup by link
    seen, out = set(), []
    for it in items:
        lk = it.get("link","")
        if lk and lk in seen: continue
        seen.add(lk); out.append(it)
    return out[:200]

def main():
    items = fetch_all()
    data = {"generated_at": datetime.utcnow().isoformat() + "Z", "count": len(items), "items": items}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[fetch] wrote", OUT_PATH, "items:", len(items))

if __name__ == "__main__":
    main()
