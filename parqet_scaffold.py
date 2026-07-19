#!/usr/bin/env python3
"""Parqet-Modus (Stufe 1, ohne Portfolio Performance): baut portfolio.json aus einem
OEFFENTLICHEN Parqet-Portfolio. Danach liefert der Client-Live-Layer der App die
Werte/Gewinne pro Position sekundenaktuell direkt von Parqet.

Nutzung:  python3 parqet_scaffold.py <parqet-portfolio-id>
Die ID steht im Parqet-Share-Link: app.parqet.com/p/<ID>  (Portfolio muss auf
"oeffentlich" stehen). Engine-Features (TTWROR-Kurve, FIFO-Trading-Bilanz, Payments)
gibt es in diesem Modus nicht — dafuer braucht es Portfolio Performance (depot.xml).
"""
import json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))

def main(pid):
    req = urllib.request.Request(
        "https://api.parqet.com/v1/portfolios/assemble?useInclude=true&include=xirr&include=ttwror",
        data=json.dumps({"portfolioIds": [pid], "timeframe": "max", "currency": "USD"}).encode(),
        headers={"Content-Type": "application/json"})
    j = json.load(urllib.request.urlopen(req, timeout=30))
    perf = j.get("performance", {}) or {}
    holdings = []
    for h in j.get("holdings", []):
        pos = h.get("position") or {}
        if not pos or pos.get("currentValue", 0) <= 0: continue
        asset = h.get("asset") or {}
        sec = h.get("sharedAsset") or {}
        tk = (asset.get("identifier") or sec.get("symbol") or h.get("assetType") or "?")
        name = sec.get("name") or asset.get("identifier") or tk
        perf_h = (h.get("performance") or {}).get("unrealized") or {}
        entry = {"pid": h.get("_id"), "ticker": str(tk)[:10].upper(), "name": name,
                 "assetType": "cash" if h.get("assetType") == "cash" else "security",
                 "value": round(pos.get("currentValue", 0)),
                 "unrealizedReturn": round(perf_h.get("returnNet", 0) * 1, 1) if perf_h else 0,
                 "totalGainNet": round(perf_h.get("gainNet", 0)) if perf_h else 0,
                 "thesis": "", "ySym": str(tk)[:10].upper(), "gquery": name,
                 "links": {"stocktwits": f"https://stocktwits.com/symbol/{tk}",
                           "finviz": f"https://finviz.com/quote.ashx?t={tk}"}}
        holdings.append(entry)
    out = {"asOf": (j.get("updatedAt") or "")[:10], "currency": "USD", "source": "parqet",
           "portfolioId": pid,
           "totalValue": round(sum(h["value"] for h in holdings)),
           "cashValue": round(sum(h["value"] for h in holdings if h["assetType"] == "cash")),
           "netGainUnrealized": round(perf.get("unrealized", {}).get("gainNet", 0)) if perf else 0,
           "unrealizedReturn": 0, "izf": round(perf.get("xirr", 0) * 100, 2) if perf.get("xirr") else 0,
           "ttwror": round(perf.get("ttwror", 0) * 100, 2) if perf.get("ttwror") else 0,
           "holdings": holdings}
    json.dump(out, open(os.path.join(ROOT, "portfolio.json"), "w"), ensure_ascii=False, indent=1)
    print(f"portfolio.json: {len(holdings)} Positionen, Gesamtwert ${out['totalValue']:,}")
    print("Hinweis: Feld-Namen der Parqet-API koennen abweichen — nach dem ersten Lauf")
    print("portfolio.json pruefen (ticker/name plausibel?) und ggf. nachjustieren.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Nutzung: python3 parqet_scaffold.py <parqet-portfolio-id>")
    main(sys.argv[1])
