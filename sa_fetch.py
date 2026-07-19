#!/usr/bin/env python3
"""Multi-year analyst estimates via RapidAPI "Seeking Alpha Finance" (Tipsters).
Writes sa_estimates.json {TK:{eps:[[label,est,yoyPct,None,low,high,n]],rev:[...]},_ts}
— the exact shape rsEstimatesSA() renders (SA-style annual consensus tables).

Endpoints (verified live 2026-07-15):
  /v1/search/searches?query=TK                       -> symbols[].id (ticker_id)
  /v1/symbols/estimated/estimates?estimates_type=
      estimates_annual_consensus_eps_estimates       -> eps mean/low/high/#analysts per fiscalyear
      estimates_annual_consensus_revenue_estimates   -> revenue mean/low/high/#analysts
  Payload: {"estimates":{"<tid>":{"<metric>":{"<rel>":[{"dataitemvalue":..,"period":{"fiscalyear":..}}]}}}}
  Transient "424 General client error, try again" happens -> retry.

Call discipline (Basic plan = 500 req/month HARD limit):
  - weekly full refresh of holdings+watchlist+saReq (7d gate via in-file _ts)
  - tickers missing from the file are fetched any cycle (on-demand research adds)
  - sa_budget.json counts every HTTP call; hard stop at MAX_CALLS_PER_MONTH
Without RAPIDAPI_KEY in the env the script exits silently (seed data stays)."""
import json, os, time, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "sa_estimates.json")
IDS = os.path.join(ROOT, "sa_ids.json")          # SYM -> SA ticker_id (static, cached forever)
BUDGET = os.path.join(ROOT, "sa_budget.json")    # {"month":"YYYY-MM","used":N}
DEBUG_RAW = os.path.join(ROOT, "sa_api_raw.json")  # last unparseable payload, for diagnosis
HOST = "seeking-alpha-finance.p.rapidapi.com"
MAX_CALLS_PER_MONTH = 400                        # head-room under the 500 hard limit
REFRESH_DAYS = 7
ALIAS = {"PINK.V": "PYNKF"}                      # portfolio symbol -> SA symbol

def _budget():
    m = datetime.datetime.utcnow().strftime("%Y-%m")
    b = {"month": m, "used": 0}
    try:
        j = json.load(open(BUDGET))
        if j.get("month") == m: b = j
    except Exception: pass
    return b

def _spend(b):
    b["used"] = b.get("used", 0) + 1
    json.dump(b, open(BUDGET, "w"))

def _get(path, params, key, b, tries=3):
    import requests
    for i in range(tries):
        _spend(b)
        try:
            r = requests.get(f"https://{HOST}{path}", params=params, timeout=60,
                             headers={"x-rapidapi-host": HOST, "x-rapidapi-key": key})
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403, 429):   # auth/quota: retrying won't help
                raise RuntimeError(f"HTTP {r.status_code}")
        except Exception:
            if i == tries - 1: raise
        time.sleep(3)
    raise RuntimeError("no 200 after retries")

def wanted():
    out = []
    try:
        for h in json.load(open(os.path.join(ROOT, "pp.json"))).get("holdings", []):
            tk = (h.get("ticker") or "").strip().upper()
            if tk and len(tk) <= 10 and tk not in out: out.append(tk)
    except Exception: pass
    try:
        st = json.load(open(os.path.join(ROOT, "site_state.json")))
        for s in st.get("watchlist", []) + st.get("saReq", []):
            s = s.strip().upper()
            if s and len(s) <= 10 and s not in out: out.append(s)
    except Exception: pass
    return out

def ticker_id(sym, ids, key, b):
    if sym in ids: return ids[sym]
    j = _get("/v1/search/searches", {"query": sym}, key, b)
    tid = None
    # symbols[]: {"id":578851,"type":"symbol","url":"/symbol/ONDS","slug":"onds",
    #             "name":"<b>ONDS</b>"} — match via slug/url, name carries HTML tags
    for s in (j.get("symbols") or []):
        if str(s.get("type")) != "symbol" or s.get("id") is None: continue
        if (str(s.get("slug") or "").upper() == sym.upper()
                or str(s.get("url") or "").upper() == "/SYMBOL/" + sym.upper()):
            try: tid = int(s["id"]); break
            except (TypeError, ValueError): pass
    if tid:
        ids[sym] = tid
        json.dump(ids, open(IDS, "w"))
    else:
        print(f"sa_fetch: no ticker_id for {sym}")
    return tid

MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def _by_year(payload, tid, metric, ends=None):
    """metric dict {rel:[{dataitemvalue, period.fiscalyear}]} -> {year: float};
    optionally records the fiscal period END label (SA shows 'Jan 2027' for NVDA)."""
    out = {}
    for arr in (payload.get("estimates", {}).get(str(tid), {}).get(metric, {}) or {}).values():
        for e in arr:
            try:
                y = int(e["period"]["fiscalyear"]); v = float(e["dataitemvalue"])
            except (KeyError, TypeError, ValueError): continue
            out[y] = v
            if ends is not None:
                try:
                    d = str(e["period"]["periodenddate"])
                    ends[y] = MON[int(d[5:7])] + " " + d[:4]
                except (KeyError, TypeError, ValueError, IndexError): pass
    return out

def _table(payload, tid, prefix):
    ends = {}
    mean = _by_year(payload, tid, prefix + "_consensus_mean", ends)
    low = _by_year(payload, tid, prefix + "_consensus_low")
    high = _by_year(payload, tid, prefix + "_consensus_high")
    num = _by_year(payload, tid, prefix + "_num_of_estimates")
    actual = _by_year(payload, tid, prefix + "_actual")
    y_now = datetime.date.today().year
    rows = []
    for y in sorted(y for y in mean if y >= y_now):
        base = actual.get(y - 1, mean.get(y - 1))   # YoY vs prior actual, else prior estimate
        yoy = round((mean[y] / base - 1) * 100, 2) if base not in (None, 0) and base * base > 0 else None
        if base is not None and base < 0 and mean[y] is not None:
            yoy = round((mean[y] - base) / abs(base) * 100, 2)   # loss shrinking = improvement
        n = num.get(y)
        rows.append([ends.get(y, "Dec %d" % y), round(mean[y], 4), yoy, None,
                     low.get(y), high.get(y), int(n) if n is not None else None])
    return rows

def _sa_shares(sym, key, b):
    """SA's own share count (fully diluted — what their FWD Price/Sales uses;
    Yahoo 'sharesOutstanding' is materially lower for multi-class caps like WGS)."""
    j = _get("/v1/symbols/metrics", {"category": "shares", "ticker_slug": sym.lower()}, key, b)
    best = None
    def scan(o):
        nonlocal best
        if isinstance(o, dict):
            v = o.get("value")
            if isinstance(v, (int, float)) and 1e5 < v < 1e13 and best is None:
                best = float(v)
            for x in o.values(): scan(x)
        elif isinstance(o, list):
            for x in o: scan(x)
    scan(j)
    if best is None:
        json.dump({sym + ":shares": j}, open(DEBUG_RAW, "w"))
    return best

def main():
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not key: return
    cur = {}
    try: cur = json.load(open(OUT))
    except Exception: pass
    want = wanted()
    stale = time.time() - cur.get("_ts", 0) > REFRESH_DAYS * 86400
    todo = want if stale else [t for t in want if t not in cur]
    if not todo: return
    b = _budget()
    ids = {}
    try: ids = json.load(open(IDS))
    except Exception: pass
    changed = False
    for tk in todo:
        if MAX_CALLS_PER_MONTH - b.get("used", 0) < 5:
            print("sa_fetch: monthly call budget exhausted — stopping"); break
        sa_sym = ALIAS.get(tk, tk)
        try:
            tid = ticker_id(sa_sym, ids, key, b)
            if not tid: continue
            eps_p = _get("/v1/symbols/estimated/estimates",
                         {"estimates_type": "estimates_annual_consensus_eps_estimates",
                          "ticker_id": tid}, key, b)
            rev_p = _get("/v1/symbols/estimated/estimates",
                         {"estimates_type": "estimates_annual_consensus_revenue_estimates",
                          "ticker_id": tid}, key, b)
            eps = _table(eps_p, tid, "eps_normalized")
            rev = _table(rev_p, tid, "revenue")
            if eps or rev:
                cur[tk] = {"eps": eps, "rev": rev}
                try:
                    sh = _sa_shares(sa_sym, key, b)
                    if sh: cur[tk]["sh"] = sh
                except Exception: pass
                if tk in ALIAS: cur[ALIAS[tk]] = cur[tk]
                changed = True
                print(f"sa_fetch: {tk} eps={len(eps)} rev={len(rev)} sh={cur[tk].get('sh')}")
            else:
                print(f"sa_fetch: {tk} returned no annual rows (kept old data)")
        except Exception as e:
            print(f"sa_fetch: {tk} failed: {e}")
            if "429" in str(e):   # provider quota gone — poison the budget and stop wasting calls
                b["used"] = MAX_CALLS_PER_MONTH
                json.dump(b, open(BUDGET, "w"))
                break
        time.sleep(0.5)   # stay well under 5 req/s
    if changed or (stale and todo):
        cur["_ts"] = int(time.time())
        json.dump(cur, open(OUT, "w"), separators=(",", ":"))
        print(f"sa_estimates.json: {len([k for k in cur if not k.startswith('_')])} tickers, budget used {b.get('used')}/{MAX_CALLS_PER_MONTH}")

if __name__ == "__main__":
    main()
