#!/usr/bin/env python3
"""Mint a Google OAuth access token from the Firebase CLI's stored refresh token.
Used by the pipeline (Firestore writes) and setup scripts. The refresh token lives in
~/.config/configstore/firebase-tools.json (created by `firebase login` on this Mac).
Client id/secret below are the Firebase CLI's PUBLIC installed-app credentials."""
import json, os, subprocess, sys

CFG = os.path.expanduser("~/.config/configstore/firebase-tools.json")
CID = "563584335869-fgrhgmd47bqnekij5i8b5pr03ho849e6.apps.googleusercontent.com"
CSECRET = "j9iVZfS8kkCEFUPaAeJV0sAi"

def access_token():
    rt = json.load(open(CFG))["tokens"]["refresh_token"]
    r = subprocess.run(["curl","-s","https://oauth2.googleapis.com/token",
        "-d","client_id="+CID,"-d","client_secret="+CSECRET,
        "-d","refresh_token="+rt,"-d","grant_type=refresh_token"],
        capture_output=True,text=True,check=True)
    j = json.loads(r.stdout)
    if "access_token" not in j:
        raise SystemExit("token exchange failed (no access_token in response)")
    return j["access_token"]

if __name__=="__main__":
    print(access_token())
