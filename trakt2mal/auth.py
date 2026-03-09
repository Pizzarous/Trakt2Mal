"""OAuth2 authentication for Trakt (device flow) and MAL (PKCE)."""
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

TRAKT_CLIENT_ID = os.getenv("TRAKT_CLIENT_ID")
TRAKT_CLIENT_SECRET = os.getenv("TRAKT_CLIENT_SECRET")
MAL_CLIENT_ID = os.getenv("MAL_CLIENT_ID")
MAL_CLIENT_SECRET = os.getenv("MAL_CLIENT_SECRET")

TOKENS_FILE = "tokens.json"
MAL_REDIRECT_URI = "http://localhost:8080/callback"


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

def load_tokens() -> dict:
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE) as f:
            return json.load(f)
    return {}


def save_tokens(tokens: dict) -> None:
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


# ---------------------------------------------------------------------------
# Trakt — device flow
# ---------------------------------------------------------------------------

def trakt_device_auth() -> dict:
    """Run Trakt device-code flow and persist tokens. Returns token dict."""
    resp = requests.post(
        "https://api.trakt.tv/oauth/device/code",
        json={"client_id": TRAKT_CLIENT_ID},
    )
    resp.raise_for_status()
    data = resp.json()

    print("\nTrakt Authentication")
    print(f"  Visit : {data['verification_url']}")
    print(f"  Code  : {data['user_code']}")
    print("  Waiting for authorization...", flush=True)

    interval = data.get("interval", 5)
    deadline = time.time() + data.get("expires_in", 600)

    while time.time() < deadline:
        time.sleep(interval)
        token_resp = requests.post(
            "https://api.trakt.tv/oauth/device/token",
            json={
                "code": data["device_code"],
                "client_id": TRAKT_CLIENT_ID,
                "client_secret": TRAKT_CLIENT_SECRET,
            },
        )
        if token_resp.status_code == 200:
            td = token_resp.json()
            tokens = load_tokens()
            tokens["trakt"] = {
                "access_token": td["access_token"],
                "refresh_token": td["refresh_token"],
                "expires_at": time.time() + td["expires_in"],
            }
            save_tokens(tokens)
            print("  Trakt authentication successful!")
            return tokens["trakt"]
        elif token_resp.status_code == 400:
            continue  # authorization pending
        elif token_resp.status_code == 409:
            raise RuntimeError("Trakt: code already used.")
        elif token_resp.status_code == 410:
            raise RuntimeError("Trakt: code expired.")
        elif token_resp.status_code == 418:
            raise RuntimeError("Trakt: authorization denied by user.")

    raise RuntimeError("Trakt: device authentication timed out.")


def _trakt_refresh(refresh_token: str) -> dict:
    resp = requests.post(
        "https://api.trakt.tv/oauth/token",
        json={
            "refresh_token": refresh_token,
            "client_id": TRAKT_CLIENT_ID,
            "client_secret": TRAKT_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return resp.json()


def get_trakt_token() -> str:
    """Return a valid Trakt access token, refreshing or re-authing as needed."""
    tokens = load_tokens()
    trakt = tokens.get("trakt", {})

    if not trakt.get("access_token"):
        return trakt_device_auth()["access_token"]

    if trakt.get("expires_at", 0) < time.time() + 3600:
        td = _trakt_refresh(trakt["refresh_token"])
        tokens["trakt"] = {
            "access_token": td["access_token"],
            "refresh_token": td["refresh_token"],
            "expires_at": time.time() + td["expires_in"],
        }
        save_tokens(tokens)
        return td["access_token"]

    return trakt["access_token"]


# ---------------------------------------------------------------------------
# MAL — OAuth2 PKCE
# ---------------------------------------------------------------------------

_mal_callback_code: str | None = None


class _MALCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _mal_callback_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _mal_callback_code = params["code"][0]
            body = b"<h1>Authorization successful! You can close this tab.</h1>"
            self.send_response(200)
        else:
            body = b"<h1>Error: no authorization code received.</h1>"
            self.send_response(400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass  # suppress server logs


def mal_pkce_auth() -> dict:
    """Run MAL PKCE OAuth2 flow and persist tokens. Returns token dict."""
    global _mal_callback_code
    _mal_callback_code = None

    # MAL uses plain PKCE — code_challenge == code_verifier
    code_verifier = secrets.token_urlsafe(64)[:128]
    state = secrets.token_urlsafe(16)

    auth_url = (
        "https://myanimelist.net/v1/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={MAL_CLIENT_ID}"
        f"&redirect_uri={MAL_REDIRECT_URI}"
        f"&state={state}"
        f"&code_challenge={code_verifier}"
        f"&code_challenge_method=plain"
    )

    print("\nMAL Authentication")
    print("  Opening browser for MAL authorization...")
    webbrowser.open(auth_url)
    print(f"  If the browser did not open, visit:\n  {auth_url}")
    print("  Waiting for callback on http://localhost:8080 ...", flush=True)

    server = HTTPServer(("localhost", 8080), _MALCallbackHandler)
    server.timeout = 120
    server.handle_request()

    if not _mal_callback_code:
        raise RuntimeError("MAL: no authorization code received (timed out?).")

    resp = requests.post(
        "https://myanimelist.net/v1/oauth2/token",
        data={
            "client_id": MAL_CLIENT_ID,
            "client_secret": MAL_CLIENT_SECRET,
            "code": _mal_callback_code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": MAL_REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    td = resp.json()

    tokens = load_tokens()
    tokens["mal"] = {
        "access_token": td["access_token"],
        "refresh_token": td["refresh_token"],
        "expires_at": time.time() + td["expires_in"],
    }
    save_tokens(tokens)
    print("  MAL authentication successful!")
    return tokens["mal"]


def _mal_refresh(refresh_token: str) -> dict:
    resp = requests.post(
        "https://myanimelist.net/v1/oauth2/token",
        data={
            "client_id": MAL_CLIENT_ID,
            "client_secret": MAL_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return resp.json()


def get_mal_token() -> str:
    """Return a valid MAL access token, refreshing or re-authing as needed."""
    tokens = load_tokens()
    mal = tokens.get("mal", {})

    if not mal.get("access_token"):
        return mal_pkce_auth()["access_token"]

    if mal.get("expires_at", 0) < time.time() + 3600:
        td = _mal_refresh(mal["refresh_token"])
        tokens["mal"] = {
            "access_token": td["access_token"],
            "refresh_token": td["refresh_token"],
            "expires_at": time.time() + td["expires_in"],
        }
        save_tokens(tokens)
        return td["access_token"]

    return mal["access_token"]


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------

def setup_auth(trakt_only: bool = False, mal_only: bool = False) -> None:
    if not mal_only:
        trakt_device_auth()
    if not trakt_only:
        mal_pkce_auth()
