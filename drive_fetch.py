#!/usr/bin/env python3
"""Download the newest depot.xml the service account can see (= the PP folder the
owner shared with cockpit-actions@...). Skips the download when the file hasn't
changed since the last call (state kept next to the output file).
Usage: drive_fetch.py [outpath]"""
import json, os, subprocess, sys
from sa_token import access_token

def main(out):
    tok=access_token()
    q="name = 'depot.xml' and trashed = false"
    r=subprocess.run(["curl","-s","-G","https://www.googleapis.com/drive/v3/files",
        "--data-urlencode",f"q={q}",
        "--data-urlencode","fields=files(id,name,size,modifiedTime)",
        "--data-urlencode","orderBy=modifiedTime desc",
        "-H","Authorization: Bearer "+tok],capture_output=True,text=True)
    files=json.loads(r.stdout or "{}").get("files",[])
    files=[f for f in files if int(f.get("size",0))>1_000_000]
    if not files:
        raise SystemExit("drive_fetch: no depot.xml visible — folder not shared with the service account yet?")
    f=files[0]
    state=out+".mtime"
    last=open(state).read().strip() if os.path.exists(state) else ""
    if f["modifiedTime"]==last and os.path.exists(out):
        print(f"drive_fetch: unchanged ({f['modifiedTime']})"); return
    subprocess.run(["curl","-s","-o",out,
        f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media",
        "-H","Authorization: Bearer "+tok],check=True)
    open(state,"w").write(f["modifiedTime"])
    print(f"drive_fetch: {f['name']} {f['size']}B modified {f['modifiedTime']} -> {out}")

if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "depot_cloud.xml")
