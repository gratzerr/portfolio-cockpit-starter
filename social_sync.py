#!/usr/bin/env python3
"""Fetch latest Stocktwits posts per holding (server-side via jina proxy) and write
social.json — baked into the page by build.py so the social feed is filled instantly
on open. The client's live sweep then keeps it fresh. Run by the hourly job."""
import json, os, subprocess, time

ROOT = os.path.dirname(os.path.abspath(__file__))
ST_SYM = {"PINK": "PYNKF"}

port = json.load(open(os.path.join(ROOT, "portfolio.json"), encoding="utf-8"))
tickers = [h["ticker"] for h in port["holdings"] if h.get("assetType") in ("security", "option")]  # option = underlying's stream

old = {}
try:
    old = json.load(open(os.path.join(ROOT, "social.json"), encoding="utf-8"))
except Exception:
    pass

out = dict(old)  # keep last known posts for tickers that fail this run
for tk in tickers:
    sym = ST_SYM.get(tk, tk)
    try:
        r = subprocess.run(["curl", "-s", "-m", "20",
            f"https://r.jina.ai/https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"],
            capture_output=True, text=True, check=True)
        t = r.stdout
        i = t.find('{"symbol"')
        if i < 0:
            continue
        d = json.loads(t[i:])
        msgs = []
        for m in d.get("messages", []):
            body = (m.get("body") or "").strip()
            if body.count("$") > 4 or len(body) < 8:
                continue
            msgs.append({"ticker": tk, "user": (m.get("user") or {}).get("username"),
                "body": body, "time": m.get("created_at"),
                "sentiment": ((m.get("entities") or {}).get("sentiment") or {}).get("basic"),
                "likes": (m.get("likes") or {}).get("total") or 0})
        if msgs:
            out[tk] = msgs[:15]
    except Exception:
        pass
    time.sleep(1.5)

json.dump(out, open(os.path.join(ROOT, "social.json"), "w", encoding="utf-8"))
n = sum(len(v) for v in out.values())
print(f"social.json: {len(out)} tickers, {n} posts")
