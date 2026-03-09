"""
ID mapping: Trakt ID (+ season) → MAL ID.

Priority order (highest first):
  1. overrides.json  — your local edits, supports episode-range splits
  2. db/tv.json      — downloaded from rensetsu/db.trakt.anitrakt
  3. db/movies.json  — same source

Run `python main.py update-db` to refresh the downloaded DB.
"""
import json
import os

import requests

_ROOT = os.path.join(os.path.dirname(__file__), "..")
DB_DIR = os.path.join(_ROOT, "db")
TV_JSON = os.path.join(DB_DIR, "tv.json")
MOVIES_JSON = os.path.join(DB_DIR, "movies.json")
OVERRIDES_FILE = os.path.join(_ROOT, "overrides.json")

_TV_URL = "https://raw.githubusercontent.com/rensetsu/db.trakt.anitrakt/main/db/tv.json"
_MOVIES_URL = "https://raw.githubusercontent.com/rensetsu/db.trakt.anitrakt/main/db/movies.json"

# A "show mapping" dict returned by lookup_show:
#   {"mal_id": int, "episode_range": [start, end] | None}
# episode_range=None means "all episodes in the season"
ShowMapping = dict

# In-memory caches
_tv_map: dict[tuple[int, int], list[ShowMapping]] | None = None
_movies_map: dict[int, int] | None = None


def update_db() -> None:
    """Download the latest mapping files from GitHub and clear in-memory caches."""
    global _tv_map, _movies_map
    os.makedirs(DB_DIR, exist_ok=True)
    for url, path, label in (
        (_TV_URL, TV_JSON, "TV shows"),
        (_MOVIES_URL, MOVIES_JSON, "Movies"),
    ):
        print(f"Downloading {label} mapping DB...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"  {len(resp.json())} entries → {path}")
    _tv_map = None
    _movies_map = None


def _load_overrides() -> tuple[dict, dict]:
    """
    Returns (show_overrides, movie_overrides).

    show_overrides  : {(trakt_id, season): [ShowMapping, ...]}
    movie_overrides : {trakt_id: mal_id}
    """
    show_ov: dict[tuple[int, int], list[ShowMapping]] = {}
    movie_ov: dict[int, int] = {}

    if not os.path.exists(OVERRIDES_FILE):
        return show_ov, movie_ov

    with open(OVERRIDES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    for e in data.get("shows", []):
        key = (int(e["trakt_id"]), int(e["season"]))
        ep_range = e.get("episode_range")  # [start, end] or absent
        show_ov.setdefault(key, []).append(
            {
                "mal_id": int(e["mal_id"]),
                "episode_range": ep_range,
            }
        )

    for e in data.get("movies", []):
        movie_ov[int(e["trakt_id"])] = int(e["mal_id"])

    return show_ov, movie_ov


def _ensure_tv() -> dict[tuple[int, int], list[ShowMapping]]:
    global _tv_map
    if _tv_map is not None:
        return _tv_map

    # Base DB
    if not os.path.exists(TV_JSON):
        print("TV mapping DB not found — downloading...")
        update_db()
    with open(TV_JSON, encoding="utf-8") as f:
        data = json.load(f)

    _tv_map = {}
    for e in data:
        if not (e.get("trakt_id") and e.get("mal_id")):
            continue
        key = (int(e["trakt_id"]), int(e["season"]))
        _tv_map[key] = [{"mal_id": int(e["mal_id"]), "episode_range": None}]

    # Overrides take full priority — they replace the DB entry entirely
    show_ov, _ = _load_overrides()
    _tv_map.update(show_ov)

    return _tv_map


def _ensure_movies() -> dict[int, int]:
    global _movies_map
    if _movies_map is not None:
        return _movies_map

    if not os.path.exists(MOVIES_JSON):
        print("Movies mapping DB not found — downloading...")
        update_db()
    with open(MOVIES_JSON, encoding="utf-8") as f:
        data = json.load(f)

    _movies_map = {
        int(e["trakt_id"]): int(e["mal_id"])
        for e in data
        if e.get("trakt_id") and e.get("mal_id")
    }

    _, movie_ov = _load_overrides()
    _movies_map.update(movie_ov)

    return _movies_map


def lookup_show(trakt_id: int, season: int) -> list[ShowMapping]:
    """
    Return a list of MAL mappings for a Trakt show + season.

    Each entry: {"mal_id": int, "episode_range": [start, end] | None}
      - episode_range=None  → covers all episodes in the season
      - episode_range=[a,b] → covers Trakt episodes a..b (1-indexed, inclusive)

    Returns an empty list if the show/season is not mapped.
    """
    return _ensure_tv().get((trakt_id, season), [])


def lookup_movie(trakt_id: int) -> int | None:
    """Return MAL ID for a Trakt movie, or None if unmapped."""
    return _ensure_movies().get(trakt_id)
