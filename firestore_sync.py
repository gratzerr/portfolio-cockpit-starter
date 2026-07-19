#!/usr/bin/env python3
"""Firestore bridge for the cockpit pipeline.
  pull : read portfolios/main -> site_state.json {name, public} (creates the doc on first run)
  push : upload data.json (built by build.py) into the doc's `data` field
Auth: owner OAuth token minted from the Firebase CLI login on this Mac (gtoken.py).
As project owner this bypasses security rules — visitors go through the rules."""
import json, os, sys, subprocess, datetime

def access_token():
    """Cloud runners use the service-account key (SA_KEY env or ./sa_key.json);
    the Mac falls back to the Firebase-CLI login (gtoken)."""
    sa = os.environ.get("SA_KEY") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_key.json")
    if os.path.exists(sa):
        os.environ.setdefault("SA_KEY", sa)
        from sa_token import access_token as sa_at
        return sa_at()
    from gtoken import access_token as gt_at
    return gt_at()

ROOT = os.path.dirname(os.path.abspath(__file__))
# instance config (starter-kit): cockpit_config.json overrides the Rafael defaults
try:
    _icfg = json.load(open(os.path.join(ROOT, "cockpit_config.json")))
except Exception:
    _icfg = {}
_PROJECT = _icfg.get("firebaseProjectId", "portfolio-cockpit-rg")
DOC = f"https://firestore.googleapis.com/v1/projects/{_PROJECT}/databases/(default)/documents/portfolios/main"
OWNER = _icfg.get("ownerEmail", "rafael.gratzer@gmail.com")

def req(method, url, body=None, tok=None):
    cmd = ["curl","-s","-X",method,url,"-H","Authorization: Bearer "+tok]
    if body is not None:
        cmd += ["-H","Content-Type: application/json","--data-binary","@-"]
        r = subprocess.run(cmd, input=json.dumps(body), capture_output=True, text=True)
    else:
        r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout or "{}")

def pull():
    tok = access_token()
    j = req("GET", DOC, tok=tok)
    if "fields" not in j:                       # first run: create the doc
        body = {"fields":{
            "owner":{"stringValue":OWNER},
            "name":{"stringValue":_icfg.get("portfolioName", "Rafael's Portfolio")},
            "public":{"booleanValue":True},
            "data":{"stringValue":""}}}
        j = req("PATCH", DOC, body, tok)
        if "fields" not in j:
            print("firestore pull: create failed:", str(j)[:200]); return
        print("firestore: created portfolios/main")
    f = j["fields"]
    bench = [v.get("stringValue","") for v in f.get("benchmarks",{}).get("arrayValue",{}).get("values",[]) if v.get("stringValue")]
    watch = [v.get("stringValue","") for v in f.get("watchlist",{}).get("arrayValue",{}).get("values",[]) if v.get("stringValue")]
    sareq = [v.get("stringValue","") for v in f.get("saReq",{}).get("arrayValue",{}).get("values",[]) if v.get("stringValue")]
    state = {"name": f.get("name",{}).get("stringValue","Rafael's Portfolio"),
             "public": f.get("public",{}).get("booleanValue", True),
             "benchmarks": bench, "watchlist": watch, "saReq": sareq}
    json.dump(state, open(os.path.join(ROOT,"site_state.json"),"w"))
    print(f"firestore pull: name={state['name']!r} public={state['public']}")

def push():
    tok = access_token()
    data = open(os.path.join(ROOT,"data.json"), encoding="utf-8").read()
    body = {"fields":{
        "data":{"stringValue":data},
        "updated":{"stringValue":datetime.datetime.utcnow().isoformat()+"Z"}}}
    j = req("PATCH", DOC+"?updateMask.fieldPaths=data&updateMask.fieldPaths=updated", body, tok)
    ok = "fields" in j
    print("firestore push:", "ok" if ok else ("FAILED "+str(j)[:200]), f"({len(data)//1024} KB)")

if __name__ == "__main__":
    (pull if (sys.argv[1:2] or ["pull"])[0]=="pull" else push)()
