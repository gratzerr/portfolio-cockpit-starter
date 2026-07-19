#!/usr/bin/env python3
"""Access token for the cockpit-actions service account (GitHub Actions & local tests).
Key file path from $SA_KEY, default ./sa_key.json. Scopes cover Drive-read + Firestore."""
import os
SCOPES=["https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/datastore"]
def access_token():
    from google.oauth2 import service_account
    import google.auth.transport.requests
    path=os.environ.get("SA_KEY") or os.path.join(os.path.dirname(os.path.abspath(__file__)),"sa_key.json")
    creds=service_account.Credentials.from_service_account_file(path,scopes=SCOPES)
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token
if __name__=="__main__":
    access_token(); print("sa token ok")
