"""MyAnimeList API v2 client."""
import time

import requests

from .auth import get_mal_token

BASE_URL = "https://api.myanimelist.net/v2"

_WRITE_DELAY = 0.5  # seconds between write requests


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_mal_token()}"}


def get_my_list() -> dict[int, dict]:
    """
    Fetch the authenticated user's full anime list.

    Returns a dict keyed by MAL anime ID:
        {
            mal_id: {
                "status": "watching" | "completed" | ...,
                "num_watched_episodes": int,
                "score": int,           # 0 = no score
                "num_episodes": int,    # total episodes (0 = unknown)
            }
        }
    """
    results = []
    offset = 0

    while True:
        resp = requests.get(
            f"{BASE_URL}/users/@me/animelist",
            headers=_headers(),
            params={
                "fields": "num_episodes,list_status{num_episodes_watched,score,status}",
                "limit": 1000,
                "offset": offset,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results.extend(data["data"])

        if not data.get("paging", {}).get("next"):
            break
        offset += 1000
        time.sleep(0.3)

    out: dict[int, dict] = {}
    for entry in results:
        node = entry["node"]
        ls = entry.get("list_status", {})
        out[node["id"]] = {
            "status": ls.get("status", ""),
            "num_watched_episodes": ls.get("num_episodes_watched", 0),
            "score": ls.get("score", 0),
            "num_episodes": node.get("num_episodes", 0),
        }
    return out


def get_anime_details(mal_id: int) -> dict | None:
    """Fetch anime node fields. Returns None if not found."""
    resp = requests.get(
        f"{BASE_URL}/anime/{mal_id}",
        headers=_headers(),
        params={"fields": "num_episodes,status"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def update_anime(
    mal_id: int,
    num_watched_episodes: int,
    status: str,
    score: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Update (or create) a MAL list entry. Returns the payload sent."""
    payload = {
        "num_watched_episodes": num_watched_episodes,
        "status": status,
    }
    if score:
        payload["score"] = score

    if dry_run:
        return payload

    resp = requests.patch(
        f"{BASE_URL}/anime/{mal_id}/my_list_status",
        headers=_headers(),
        data=payload,
    )
    resp.raise_for_status()
    time.sleep(_WRITE_DELAY)
    return resp.json()
