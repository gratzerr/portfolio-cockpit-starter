#!/usr/bin/env python3
"""Prefetch SEC XBRL series for holdings + watchlist tickers into rs_prefetch.json.
The research tab opens these tickers INSTANTLY (no client-side SEC round-trips).
Mirrors the client's rsSeries logic: raw entries (frames are too sparse), latest
filing wins per (start,end), quarters derived by differencing YTD chains, weighted-
average share counts never diffed. Refreshes when the file is older than 12h.
"""
import json, os, time, datetime, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "rs_prefetch.json")
UA = {"User-Agent": "PortfolioCockpit contact@portfolio-cockpit.app"}

CONCEPTS = {  # group -> (taxonomy, [tag fallbacks], unit, instant, kind)
    "revenue": ("us-gaap", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"], "USD", 0, ""),
    "costRev": ("us-gaap", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"], "USD", 0, ""),
    "grossProfit": ("us-gaap", ["GrossProfit"], "USD", 0, ""),
    "opInc": ("us-gaap", ["OperatingIncomeLoss"], "USD", 0, ""),
    "netInc": ("us-gaap", ["NetIncomeLoss"], "USD", 0, ""),
    "eps": ("us-gaap", ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"], "USD/shares", 0, ""),
    "ocf": ("us-gaap", ["NetCashProvidedByUsedInOperatingActivities",
                        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], "USD", 0, ""),
    "capex": ("us-gaap", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "USD", 0, ""),
    "rnd": ("us-gaap", ["ResearchAndDevelopmentExpense"], "USD", 0, ""),
    "sga": ("us-gaap", ["SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense"], "USD", 0, ""),
    "cash": ("us-gaap", ["CashAndCashEquivalentsAtCarryingValue",
                         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], "USD", 1, ""),
    "shares": ("us-gaap", ["WeightedAverageNumberOfDilutedSharesOutstanding",
                           "WeightedAverageNumberOfSharesOutstandingBasic"], "shares", 0, "avg"),
    "divPaid": ("us-gaap", ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"], "USD", 0, ""),
    "receivables": ("us-gaap", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"], "USD", 1, ""),
    "inventory": ("us-gaap", ["InventoryNet"], "USD", 1, ""),
    "totalAssets": ("us-gaap", ["Assets"], "USD", 1, ""),
    "totalLiab": ("us-gaap", ["Liabilities"], "USD", 1, ""),
    "ltDebt": ("us-gaap", ["LongTermDebtNoncurrent", "LongTermDebt"], "USD", 1, ""),
    "buyback": ("us-gaap", ["PaymentsForRepurchaseOfCommonStock"], "USD", 0, ""),
}

def tickers():
    out = []
    try:
        for h in json.load(open(os.path.join(ROOT, "pp.json"))).get("holdings", []):
            tk = (h.get("ticker") or "").strip().upper()
            if tk and len(tk) <= 10: out.append(tk)
    except Exception: pass
    try:
        st = json.load(open(os.path.join(ROOT, "site_state.json")))
        # saReq: research tickers the owner looked up — prefetching them makes
        # their next visit instant instead of a minute of client proxy round-trips
        for s in st.get("watchlist", []) + st.get("saReq", []):
            s = s.strip().upper()
            if s and s not in out: out.append(s)
    except Exception: pass
    return out

def cik_of(tk):
    try:
        m = json.load(open(os.path.join(ROOT, "cik.json")))
        return m.get(tk.upper())
    except Exception:
        return None

def fetch_concept(cik, tax, tag):
    u = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{tax}/{tag}.json"
    req = urllib.request.Request(u, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=15))

def qk(d):
    return d[:4] + "Q" + str((int(d[5:7]) + 2) // 3)

def series(j, unit, instant, no_derive):
    units = j.get("units", {})
    arr = units.get(unit) or (list(units.values())[0] if units else [])
    best = {}
    for e in arr:
        if e.get("val") is None or not e.get("end"): continue
        k = (e.get("start") or "I") + "|" + e["end"]
        if k not in best or (e.get("filed") or "") > (best[k].get("filed") or ""):
            best[k] = e
    entries = list(best.values())
    q, a = {}, {}
    if instant:
        seen = {}
        for e in entries:
            k = qk(e["end"])
            if k not in seen or e["end"] > seen[k]["end"]: seen[k] = e
        for k in sorted(seen):
            q[k] = seen[k]["val"]; a[k[:4]] = seen[k]["val"]
    else:
        def dur(e):
            return (datetime.date.fromisoformat(e["end"]) - datetime.date.fromisoformat(e["start"])).days
        for e in entries:
            d = dur(e)
            if 75 < d < 100: q[qk(e["end"])] = e["val"]
            elif 340 < d < 380: a[e["end"][:4]] = e["val"]
        if not no_derive:
            by_start = {}
            for e in entries:
                if 75 < dur(e) < 380: by_start.setdefault(e["start"], []).append(e)
            for lst in by_start.values():
                lst.sort(key=lambda e: e["end"])
                for i in range(1, len(lst)):
                    k = qk(lst[i]["end"])
                    if k in q: continue
                    span = (datetime.date.fromisoformat(lst[i]["end"]) - datetime.date.fromisoformat(lst[i-1]["end"])).days
                    if 75 < span < 100: q[k] = lst[i]["val"] - lst[i-1]["val"]
    rnd = lambda v: round(v, 4) if isinstance(v, float) else v
    return {"q": [[k, rnd(q[k])] for k in sorted(q)], "a": [[k, rnd(a[k])] for k in sorted(a)]}

def merge(sers):
    q, a = {}, {}
    for s in sers:
        for k, v in s["q"]:
            if k not in q: q[k] = v
        for k, v in s["a"]:
            if k not in a: a[k] = v
    return {"q": [[k, q[k]] for k in sorted(q)], "a": [[k, a[k]] for k in sorted(a)]}

def main():
    old = {}
    try: old = json.load(open(OUT))
    except Exception: pass
    want = tickers()
    fresh = old.get("_ts") and time.time() - old["_ts"] < 12 * 3600
    # "_skip" marks tickers known to yield nothing (IFRS filers like NVO, no CIK)
    # so the minute loop doesn't hammer SEC retrying them; full refresh resets it
    skip = old.get("_skip", {}) if fresh else {}
    todo = [t for t in want if t not in old and t not in skip] if fresh else want
    if not todo: return
    res = {k: v for k, v in old.items() if k != "_ts"} if fresh else {}
    res["_skip"] = skip
    for tk in todo:
        cik = cik_of(tk)
        if not cik:
            skip[tk] = 1
            continue
        data = {}
        for key, (tax, tags, unit, inst, kind) in CONCEPTS.items():
            parts = []
            for t in tags:
                try:
                    parts.append(series(fetch_concept(cik, tax, t), unit, inst, kind == "avg"))
                except Exception:
                    continue
                time.sleep(0.12)   # SEC fair-use pacing
            if parts:
                data[key] = merge(parts)
        if data.get("revenue") or data.get("netInc"):
            res[tk] = data
        elif tk in old:
            res[tk] = old[tk]
        else:
            skip[tk] = 1
    if res:
        res["_ts"] = int(time.time())
        json.dump(res, open(OUT, "w"), separators=(",", ":"))
        print(f"rs_prefetch.json: {len(res)} tickers, {os.path.getsize(OUT)//1024}KB")

if __name__ == "__main__":
    main()
