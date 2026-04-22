#!/usr/bin/env python3
"""
GitHub App helper for jsem-crab bot.
Handles JWT auth + access token generation + API helpers.
"""
import time
import jwt
import json
import sys
import urllib.request
import base64

APP_ID = "3470027"
PRIVATE_KEY_PATH = "/home/crab/.ssh/gh-jsem-crab-app.pem"


def get_jwt():
    with open(PRIVATE_KEY_PATH) as f:
        private_key = f.read()
    return jwt.encode(
        {"iat": int(time.time()), "exp": int(time.time()) + 600, "iss": APP_ID},
        private_key,
        algorithm="RS256",
    )


def get_installations():
    jwt_token = get_jwt()
    req = urllib.request.Request(
        "https://api.github.com/app/installations",
        headers={"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github.v3+json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def get_access_token(installation_id=None):
    if installation_id is None:
        installs = get_installations()
        if not installs:
            raise RuntimeError("No installations found — is the GitHub App installed?")
        # Use the first installation (or pick by ID if specified)
        if isinstance(installation_id, int):
            inst = next((i for i in installs if i["id"] == installation_id), installs[0])
        else:
            inst = installs[0]
        installation_id = inst["id"]
    
    jwt_token = get_jwt()
    req = urllib.request.Request(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["token"]


def get_file_content(repo, path, token):
    """Fetch file from GitHub and return (content_base64, sha) or (None, sha) if binary."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            if isinstance(data, list):
                return None, None  # Directory listing
            content = data.get("content", "")
            if content:
                # content may be base64 or plain
                try:
                    return base64.b64decode(content.replace("\n", "")), data["sha"]
                except Exception:
                    return content.encode(), data["sha"]
            return None, data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise


def commit_file(repo, path, message, content_bytes, token, sha=None):
    """Create or update a file in a GitHub repo. Pass sha=None for new files."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
    }
    if sha:
        payload["sha"] = sha
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)
        content = result.get("content", {})
        return content.get("html_url", result.get("message", "OK"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "token"
    
    if cmd == "token":
        print(get_access_token())
    
    elif cmd == "installations":
        for inst in get_installations():
            print(f"ID: {inst['id']} | Account: {inst.get('account', {}).get('login', '?')}")
    
    elif cmd == "repos":
        token = get_access_token()
        url = "https://api.github.com/installation/repositories?per_page=100"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            for r in data.get("repositories", []):
                print(r["full_name"])
    
    elif cmd == "commit" and len(sys.argv) >= 5:
        _, _, repo, path, message = sys.argv
        # Read from stdin for content
        content = sys.stdin.read().encode()
        token = get_access_token()
        _, sha = get_file_content(repo, path, token)
        url = commit_file(repo, path, message, content, token, sha)
        print(url)
    
    else:
        print(f"Usage: {sys.argv[0]} [token|installations|repos|commit <repo> <path> <message>]")
        print("  token          — print fresh access token")
        print("  installations — list all app installations")
        print("  repos         — list accessible repos")
        print("  commit        — read content from stdin, commit to <repo>/<path>")
