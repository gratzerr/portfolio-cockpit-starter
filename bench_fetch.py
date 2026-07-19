#!/usr/bin/env python3
"""Fetch daily close series for the benchmark ETFs (SPY, QQQ, XBI, All-World).
Uses yfinance (handles Yahoo's cookie/crumb handshake — plain HTTP gets blocked).
Keeps the old bench.json entries on failure. Output: {SYM: [[date, close], ...]}."""
import json, os, warnings, datetime
warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "bench.json")
BASE = ["SPY", "QQQ", "VWCE.DE"]
def all_syms():
    syms = list(BASE)
    try:
        extra = json.load(open(os.path.join(ROOT, "site_state.json"))).get("benchmarks", [])
        for s in extra:
            s = s.strip().upper()
            if s and s not in syms: syms.append(s)
    except Exception: pass
    return syms
SINCE = "2021-12-30"

def _fresh(path, hours):
    """Freshness via an in-file timestamp — file mtimes are useless on CI checkouts."""
    try:
        import time
        ts = json.load(open(path)).get("_ts")
        return ts and time.time() - ts < hours * 3600
    except Exception:
        return False

def _stamp(d):
    import time
    d["_ts"] = int(time.time()); return d


def fetch(sym):
    import yfinance as yf
    out = []
    try:
        d = yf.download(sym, start=SINCE, interval="1d", progress=False, auto_adjust=True)
        closes = d["Close"][sym] if hasattr(d["Close"], "columns") else d["Close"]
        for idx, c in closes.items():
            if c == c:  # not NaN
                out.append([idx.strftime("%Y-%m-%d"), round(float(c), 4)])
    except Exception:
        pass
    if len(out) > 20:
        return out
    # bulk download can fail silently for DAYS (runner throttling) -> Ticker.history
    h = yf.Ticker(sym).history(start=SINCE, interval="1d", auto_adjust=True)["Close"]
    return [[i.strftime("%Y-%m-%d"), round(float(c), 4)] for i, c in h.items() if c == c]

def _tail_merge(sym, old_ser):
    """Freshen a stale series cheaply: append the last ~10 daily closes."""
    import yfinance as yf
    h = yf.Ticker(sym).history(period="10d", auto_adjust=True)["Close"]
    ser = list(old_ser); last = ser[-1][0] if ser else "0000"
    for i, c in h.items():
        d = i.strftime("%Y-%m-%d")
        if d > last and c == c:
            ser.append([d, round(float(c), 4)])
    return ser

WATCH_OUT = os.path.join(ROOT, "watch.json")
def watch_syms():
    try:
        return [s.strip().upper() for s in
                json.load(open(os.path.join(ROOT, "site_state.json"))).get("watchlist", []) if s.strip()]
    except Exception:
        return []

WATCH_META = os.path.join(ROOT, "watch_meta.json")
def _fast_meta(sym):
    """Fundamentals for the watchlist row (Seeking-Alpha-style columns)."""
    import yfinance as yf
    fi = yf.Ticker(sym).fast_info
    def g(k):
        try:
            v = fi[k]
            return round(float(v), 4) if v is not None else None
        except Exception:
            return None
    return {"mcap": g("market_cap"), "vol": g("last_volume"),
            "avgVol": g("three_month_average_volume"), "shares": g("shares"),
            "hi52": g("year_high"), "lo52": g("year_low")}

def fetch_watch(missing_only):
    """Watchlist quotes live in their own file so they never show up as benchmark chips."""
    old = {}
    try: old = json.load(open(WATCH_OUT))
    except Exception: pass
    meta = {}
    try: meta = json.load(open(WATCH_META))
    except Exception: pass
    want = watch_syms()
    syms = want
    if missing_only:
        # a symbol is "missing" if its series OR its meta is absent — a failed
        # fast_info call would otherwise never be retried
        syms = [s for s in want if len(old.get(s, [])) < 20 or s not in meta]
        if not syms: return
    res = {k: v for k, v in old.items() if k in want}   # drop removed tickers
    meta = {k: v for k, v in meta.items() if k in want}
    for sym in syms:
        try: s = fetch(sym)
        except Exception: s = []
        if len(s) > 20: res[sym] = s
        elif sym in old and len(old[sym]) > 20: res[sym] = old[sym]
        else: print(f"watch: {sym} FAILED")
        try: meta[sym] = _fast_meta(sym)
        except Exception: pass
    json.dump(res, open(WATCH_OUT, "w"))
    json.dump(meta, open(WATCH_META, "w"))
    if res: print("watch.json:", {k: len(v) for k, v in res.items()})

FUND_OUT = os.path.join(ROOT, "fund.json")
def _fundamentals(sym):
    import yfinance as yf
    info = yf.Ticker(sym).info
    def g(*keys):
        for k in keys:
            v = info.get(k)
            if v not in (None, "", 0): return v
        return None
    return {"mcap": g("marketCap"), "shares": g("sharesOutstanding"),
            "hi52": g("fiftyTwoWeekHigh"), "lo52": g("fiftyTwoWeekLow"),
            "pe": g("trailingPE", "forwardPE"), "peg": g("trailingPegRatio", "pegRatio"),
            "ps": g("priceToSalesTrailing12Months"), "ev": g("enterpriseValue"),
            "divRate": g("dividendRate"), "divYield": g("dividendYield")}

def fund_tickers():
    syms = set(watch_syms())
    try:
        for h in json.load(open(os.path.join(ROOT, "pp.json"))).get("holdings", []):
            tk = (h.get("tk") or h.get("ticker") or "").strip().upper()
            if tk and len(tk) <= 10: syms.add(tk)   # skip option OCC symbols
    except Exception: pass
    try:  # research tickers the owner looked up (saReq queue) get estimates too
        for s in json.load(open(os.path.join(ROOT, "site_state.json"))).get("saReq", []):
            s = s.strip().upper()
            if s and len(s) <= 10: syms.add(s)
    except Exception: pass
    return sorted(syms)

def fetch_fund():
    """Slow-moving fundamentals (PE/PEG/PS/EV/mcap/dividend). Refresh only when
    fund.json is missing or >6h old — .info is heavy and rate-limited."""
    if _fresh(FUND_OUT, 6):
        return
    old = {}
    try: old = json.load(open(FUND_OUT))
    except Exception: pass
    res = dict(old)
    for sym in fund_tickers():
        try: res[sym] = _fundamentals(sym)
        except Exception: pass
    if res:
        json.dump(_stamp(res), open(FUND_OUT, "w"))
        print("fund.json:", len(res), "tickers")

EST_OUT = os.path.join(ROOT, "estimates.json")
def _estimates(sym):
    import yfinance as yf
    t = yf.Ticker(sym)
    out = {}
    def df2d(df, keep):
        d = {}
        for per in ("0q", "+1q", "0y", "+1y"):
            if per in df.index:
                row = df.loc[per]
                d[per] = {k: (None if row.get(k) != row.get(k) else round(float(row[k]), 4))
                          for k in keep if k in row}
        return d
    try: out["rev"] = df2d(t.revenue_estimate, ["avg", "low", "high", "growth", "numberOfAnalysts"])
    except Exception: pass
    try: out["eps"] = df2d(t.earnings_estimate, ["avg", "low", "high", "growth", "numberOfAnalysts"])
    except Exception: pass
    try:
        pt = t.analyst_price_targets
        out["tgt"] = {k: round(float(v), 2) for k, v in pt.items() if v is not None}
    except Exception: pass
    return out

def fetch_estimates():
    """Analyst consensus (current + next FY — all Yahoo offers for free). 12h gate;
    tickers still missing from the file (fresh saReq research lookups) skip the gate."""
    old = {}
    try: old = json.load(open(EST_OUT))
    except Exception: pass
    want = fund_tickers()
    fresh = _fresh(EST_OUT, 12)
    syms = [s for s in want if s not in old] if fresh else want
    if not syms:
        return
    res = dict(old)
    for sym in syms:
        try:
            e = _estimates(sym)
            if e: res[sym] = e
        except Exception: pass
    if res:
        json.dump(_stamp(res), open(EST_OUT, "w"))
        print("estimates.json:", len(res), "tickers")

def main():
    old = {}
    try: old = json.load(open(OUT))
    except Exception: pass
    # MISSING_ONLY=1: fast path for the minute loop — only fetch symbols the
    # owner just added that have no series yet (new benchmark lands within a minute)
    missing_only = os.environ.get("MISSING_ONLY") == "1"
    syms = all_syms()
    if missing_only:
        want = syms
        syms = [s for s in want if len(old.get(s, [])) < 20]
        # freshen series older than the last US trading day (incl. today's partial
        # bar once the market opened — keeps benchmarks in sync with the live engine)
        now = datetime.datetime.utcnow(); d = now.date()
        if now.hour * 60 + now.minute < 13 * 60 + 35: d -= datetime.timedelta(days=1)
        while d.weekday() >= 5: d -= datetime.timedelta(days=1)
        stale_before = d.isoformat()
        res = dict(old); changed = False
        for s2 in want:
            ser = old.get(s2, [])
            if len(ser) >= 20 and ser[-1][0] < stale_before:
                try:
                    ns = _tail_merge(s2, ser)
                    if ns != ser: res[s2] = ns; changed = True
                except Exception: pass
        if not syms:
            if changed:
                json.dump(res, open(OUT, "w"))
                print("bench tail-merged:", {k: v[-1][0] for k, v in res.items()})
            return
    else:
        res = {}
    for sym in syms:
        try:
            s = fetch(sym)
        except Exception as e:
            s = []
        if len(s) > 20:  # >20 not >200: newly listed tickers have short histories
            res[sym] = s
        elif sym in old and len(old[sym]) > 20:
            res[sym] = old[sym]; print(f"bench: {sym} fetch failed -> alte Serie behalten")
        else:
            print(f"bench: {sym} FAILED")
    json.dump(res, open(OUT, "w"))
    print("bench.json:", {k: len(v) for k, v in res.items()})

if __name__ == "__main__":
    main()
    fetch_watch(os.environ.get("MISSING_ONLY") == "1")
    try: fetch_fund()
    except Exception as e: print("fund fetch skipped:", e)
    try: fetch_estimates()
    except Exception as e: print("estimates skipped:", e)
