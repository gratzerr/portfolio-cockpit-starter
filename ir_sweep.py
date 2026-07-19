#!/usr/bin/env python3
"""Deterministic IR/newswire sweep — no agent, no prompts. Runs every few minutes.
Fetches Google News RSS per holding, keeps only IR/press-release items, prepends
new ones to research/<TICKER>.json, then rebuilds + pushes. One command, fully auto.
"""
import json, os, re, subprocess, datetime, html, urllib.parse
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"

# newswire / IR distribution channels — these are the real press-release sources
WIRE = ("globenewswire", "businesswire", "prnewswire", "accesswire", "stocktitan",
        "newsfilecorp", "einpresswire", "prweb", "ir.", "investor.")
PR_VERBS = re.compile(r"\b(announce|announces|announced|reports|reported|provides update|"
    r"to present|presents|doses first patient|prices|closes|completes|receives|grants?|"
    r"initiat|enrolls|appoints|names|launches|submits|files|awarded|secures)\b", re.I)
# law-firm class-action / "investor alert" spam that floods the biotech wires — drop it
JUNK = re.compile(r"shareholder (notice|alert|rights|deadline)|reminds (investors|shareholders)|"
    r"class action|claimsfiler|faruqi|rosen law|pomerantz|bragar|kaskela|levi\s*&|"
    r"encourages investors|investigation (on behalf|of)|lead plaintiff|law offices|"
    r"deadline alert|lawsuit|morning (medical )?update|roundup|weekly recap|week in review", re.I)

# mega caps drown the feed in secondhand coverage — accept ONLY true newswire press
# releases for these (no PR-verb fallback), and skip multi-story digest headlines
MEGA = {"NVO"}
AGGREGATOR = ("ad-hoc-news", "marketscreener", "investing.com", "finanznachrichten")

def fetch_rss(company):
    q = urllib.parse.quote(f'"{company}"') + "%20when:1d"
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        r = subprocess.run(["curl", "-s", "-m", "20", "-H", f"User-Agent: {UA}", url],
                           capture_output=True, text=True, check=True)
        return r.stdout
    except Exception:
        return ""

def parse_items(xml_text):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        src_el = it.find("source")
        src_name = (src_el.text or "").strip() if src_el is not None else ""
        src_url = (src_el.get("url") or "") if src_el is not None else ""
        # Google News title is "Headline - Source"; strip the trailing source
        headline = re.sub(r"\s+-\s+[^-]+$", "", title).strip() if " - " in title else title
        # date
        try:
            dt = datetime.datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S").date().isoformat()
        except Exception:
            dt = datetime.date.today().isoformat()
        out.append({"headline": html.unescape(headline), "url": link, "date": dt,
                    "source": src_name or "News", "src_url": src_url})
    return out

def is_ir(item, ir_domain, company, ticker=""):
    h = item["headline"]
    if JUNK.search(h):
        return False
    # the company name (or first word of it) should be in the headline — avoid tangential mentions
    first = company.split()[0].lower()
    if first not in h.lower():
        return False
    blob = (item["src_url"] + " " + item["source"]).lower()
    if any(a in blob for a in AGGREGATOR):
        return False
    if ticker in MEGA:
        # strict: real company press releases only — must come off a newswire, must lead
        # with the company (not mention it mid-digest), no multi-story headlines
        if ";" in h or not h.lower().startswith(first):
            return False
        return any(w in blob for w in WIRE)
    if any(w in blob for w in WIRE):
        return True
    if ir_domain and ir_domain.split("//")[-1].split("/")[0].replace("www.", "") in blob:
        return True
    return bool(PR_VERBS.search(h))

def norm(h):
    return re.sub(r"[^a-z0-9]", "", h.lower())[:40]

def main():
    port = json.load(open(os.path.join(ROOT, "portfolio.json"), encoding="utf-8"))
    secs = [h for h in port["holdings"] if h.get("assetType") in ("security", "option")]  # option = cover the underlying
    changed = []
    for h in secs:
        tk = h["ticker"]; company = h.get("gquery") or h.get("name") or tk
        ir_domain = (h.get("links") or {}).get("ir", "")
        rf = os.path.join(ROOT, "research", f"{tk}.json")
        try:
            data = json.load(open(rf, encoding="utf-8"))
        except Exception:
            data = {"ticker": tk, "news": [], "catalysts": [], "pulse": ""}
        seen = {norm(n.get("headline", "")) for n in data.get("news", [])}
        items = [it for it in parse_items(fetch_rss(company)) if is_ir(it, ir_domain, company, tk)]
        new = []
        for it in items:
            k = norm(it["headline"])
            if not k or k in seen:
                continue
            seen.add(k)
            new.append({"date": it["date"], "headline": it["headline"],
                        "source": it["source"], "url": it["url"], "summary": ""})
        if new:
            data["news"] = (new + data.get("news", []))[:10]
            json.dump(data, open(rf, "w", encoding="utf-8"), ensure_ascii=False)
            changed.append(tk)
    if changed:
        if os.environ.get("NO_PUSH"):   # cloud runner: the workflow commits afterwards
            print("new IR (no push):", ", ".join(changed))
        else:
            subprocess.run(["bash", os.path.join(ROOT, "push_site.sh"), "IR sweep"], check=False)
            print("new IR:", ", ".join(changed))
    else:
        print("no new IR")

if __name__ == "__main__":
    main()
