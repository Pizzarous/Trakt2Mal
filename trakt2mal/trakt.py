"""Trakt API v3 client."""

import os

import requests
from dotenv import load_dotenv

from .auth import get_trakt_token

load_dotenv()

TRAKT_CLIENT_ID = os.getenv("TRAKT_CLIENT_ID")
BASE_URL = "https://api.trakt.tv"


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "3",
        "trakt-api-key": TRAKT_CLIENT_ID,
        "Authorization": f"Bearer {get_trakt_token()}",
    }


def get_watched_shows() -> list[dict]:
    """Return all watched shows with full per-season/episode data."""
    resp = requests.get(f"{BASE_URL}/sync/watched/shows", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def get_watched_movies() -> list[dict]:
    """Return all watched movies."""
    resp = requests.get(f"{BASE_URL}/sync/watched/movies", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def lookup_slug(slug: str, media_type: str = "shows") -> dict | None:
    """
    Resolve a Trakt slug to its full IDs object.

    media_type: "shows" or "movies"
    Returns the API response dict, or None if not found.
    """
    resp = requests.get(
        f"{BASE_URL}/{media_type}/{slug}",
        headers=_headers(),
        params={"extended": "full"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_ratings() -> dict[str, list]:
    """Return ratings keyed by type: 'shows', 'seasons', 'movies'."""
    result = {}
    for type_ in ("shows", "seasons", "movies"):
        resp = requests.get(f"{BASE_URL}/sync/ratings/{type_}", headers=_headers())
        resp.raise_for_status()
        result[type_] = resp.json()
    return result
