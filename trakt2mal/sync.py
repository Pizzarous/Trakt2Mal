"""Core sync logic: Trakt → MAL."""

from datetime import datetime

from .mal import get_anime_details, get_my_anime_status, get_my_list, update_anime
from .mapper import lookup_movie, lookup_show, update_db
from .trakt import get_ratings, get_watched_movies, get_watched_shows


def _link(text: str, url: str) -> str:
    """OSC 8 terminal hyperlink (works in Windows Terminal, VS Code, iTerm2)."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


# Status priority (higher = more "advanced" on MAL)
_STATUS_PRIORITY = {
    "plan_to_watch": 0,
    "watching": 1,
    "on_hold": 1,
    "dropped": 1,
    "completed": 2,
}


def _determine_status(watched: int, total: int) -> str:
    if watched == 0:
        return "plan_to_watch"
    if total and watched >= total:
        return "completed"
    return "watching"


def _build_rating_maps(ratings_data: dict) -> tuple[dict, dict, dict]:
    """
    Returns:
        show_ratings   : {trakt_id → rating}
        season_ratings : {(trakt_id, season) → rating}
        movie_ratings  : {trakt_id → rating}
    """
    show_ratings: dict[int, int] = {}
    season_ratings: dict[tuple[int, int], int] = {}
    movie_ratings: dict[int, int] = {}

    for e in ratings_data.get("shows", []):
        show_ratings[e["show"]["ids"]["trakt"]] = e["rating"]

    for e in ratings_data.get("seasons", []):
        key = (e["show"]["ids"]["trakt"], e["season"]["number"])
        season_ratings[key] = e["rating"]

    for e in ratings_data.get("movies", []):
        movie_ratings[e["movie"]["ids"]["trakt"]] = e["rating"]

    return show_ratings, season_ratings, movie_ratings


def _get_total_episodes(mal_id: int, mal_list: dict) -> int:
    """Return total episode count, using cached list data when possible."""
    cached = mal_list.get(mal_id)
    if cached and cached["num_episodes"]:
        return cached["num_episodes"]
    details = get_anime_details(mal_id)
    return (details or {}).get("num_episodes", 0)


class _Stats:
    def __init__(self):
        self.updated = self.skipped = self.unmapped = self.errors = 0

    def __str__(self):
        return (
            f"{self.updated} updated, {self.skipped} skipped, "
            f"{self.unmapped} unmapped, {self.errors} errors"
        )


def run_sync(
    dry_run: bool = False,
    sync_ratings: bool = True,
    show_unmatched: bool = False,
    verbose: bool = False,
) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = " (DRY RUN)" if dry_run else ""
    print(f"\n[{ts}] Starting Trakt → MAL sync{tag}")

    # ------------------------------------------------------------------ fetch
    print("Updating mapping DB...")
    update_db()

    print("Fetching Trakt watched shows...")
    watched_shows = get_watched_shows()
    print(f"  {len(watched_shows)} shows")

    print("Fetching Trakt watched movies...")
    watched_movies = get_watched_movies()
    print(f"  {len(watched_movies)} movies")

    show_ratings: dict = {}
    season_ratings: dict = {}
    movie_ratings: dict = {}
    if sync_ratings:
        print("Fetching Trakt ratings...")
        show_ratings, season_ratings, movie_ratings = _build_rating_maps(get_ratings())

    print("Fetching current MAL list...")
    mal_list = get_my_list()
    print(f"  {len(mal_list)} entries on MAL")

    stats = _Stats()

    # ------------------------------------------------------------------ shows
    print("\n— Shows —")
    for show_entry in watched_shows:
        show = show_entry["show"]
        trakt_id: int = show["ids"]["trakt"]
        title: str = show.get("title", str(trakt_id))

        trakt_slug: str = show["ids"].get("slug", str(trakt_id))

        for season_data in show_entry.get("seasons", []):
            season_num: int = season_data["number"]
            if season_num == 0:
                continue  # skip specials

            mappings = lookup_show(trakt_id, season_num)
            if not mappings:
                stats.unmapped += 1
                if show_unmatched:
                    print(f"  UNMATCHED {title} S{season_num} (trakt_id={trakt_id})")
                continue

            all_played = [
                e["number"]
                for e in season_data.get("episodes", [])
                if e.get("plays", 0) > 0
            ]

            for mapping in mappings:
                mal_id: int = mapping["mal_id"]
                ep_range: list[int] | None = mapping["episode_range"]

                # Filter episodes to the relevant range (if any)
                if ep_range:
                    start, end = ep_range
                    played_in_range = [n for n in all_played if start <= n <= end]
                    # Normalize to MAL episode numbers (ep 13 in range [13,25] → ep 1)
                    offset = start - 1
                    watched_eps = (
                        max(played_in_range) - offset if played_in_range else 0
                    )
                else:
                    watched_eps = max(all_played) if all_played else 0

                if watched_eps == 0:
                    stats.skipped += 1
                    continue

                try:
                    total_eps = _get_total_episodes(mal_id, mal_list)
                except Exception as exc:
                    print(
                        f"  ERROR fetching details for {title} S{season_num} (MAL {mal_id}): {exc}"
                    )
                    stats.errors += 1
                    continue

                if mal_id in mal_list:
                    current = mal_list[mal_id]
                else:
                    current = get_my_anime_status(mal_id)
                    mal_list[mal_id] = current  # cache for reuse
                current_watched = current.get("num_watched_episodes", 0)
                current_status = current.get("status", "")

                if current_status == "dropped":
                    stats.skipped += 1
                    continue

                new_watched = max(watched_eps, current_watched)
                new_status = _determine_status(new_watched, total_eps)

                # Never downgrade status (e.g. completed → watching)
                if _STATUS_PRIORITY.get(current_status, 0) > _STATUS_PRIORITY.get(
                    new_status, 0
                ):
                    new_status = current_status

                # Rating: prefer season-level, fall back to show-level
                score: int | None = None
                if sync_ratings:
                    score = season_ratings.get(
                        (trakt_id, season_num)
                    ) or show_ratings.get(trakt_id)

                if (
                    new_watched == current_watched
                    and new_status == current_status
                    and (score is None or score == current.get("score", 0))
                ):
                    stats.skipped += 1
                    if verbose:
                        range_str = (
                            f" eps {ep_range[0]}-{ep_range[1]}" if ep_range else ""
                        )
                        score_str = (
                            f", score={current.get('score')}"
                            if current.get("score")
                            else ""
                        )
                        trakt_url = _link(
                            "Trakt",
                            f"https://trakt.tv/shows/{trakt_slug}/seasons/{season_num}",
                        )
                        mal_url = _link(
                            f"MAL {mal_id}", f"https://myanimelist.net/anime/{mal_id}"
                        )
                        print(
                            f"  [OK] {title} S{season_num}{range_str} [{trakt_url}] [{mal_url}]: {current_watched} eps, {current_status}{score_str}"
                        )
                    continue

                range_str = f" eps {ep_range[0]}-{ep_range[1]}" if ep_range else ""
                score_str = f", score={score}" if score else ""
                prefix = "[DRY RUN] " if dry_run else ""
                trakt_url = _link(
                    "Trakt", f"https://trakt.tv/shows/{trakt_slug}/seasons/{season_num}"
                )
                mal_url = _link(
                    f"MAL {mal_id}", f"https://myanimelist.net/anime/{mal_id}"
                )
                print(
                    f"  {prefix}{title} S{season_num}{range_str} [{trakt_url}] [{mal_url}]: "
                    f"{current_watched}→{new_watched} eps, {new_status}{score_str}"
                )

                try:
                    update_anime(
                        mal_id, new_watched, new_status, score=score, dry_run=dry_run
                    )
                    stats.updated += 1
                except Exception as exc:
                    print(f"  ERROR updating {title} S{season_num}: {exc}")
                    stats.errors += 1

    # ----------------------------------------------------------------- movies
    print("\n— Movies —")
    for movie_entry in watched_movies:
        movie = movie_entry["movie"]
        trakt_id = movie["ids"]["trakt"]
        trakt_slug = movie["ids"].get("slug", str(trakt_id))
        title = movie.get("title", str(trakt_id))

        mal_id = lookup_movie(trakt_id)
        if not mal_id:
            stats.unmapped += 1
            if show_unmatched:
                print(f"  UNMATCHED {title} (trakt_id={trakt_id})")
            continue

        if mal_id in mal_list:
            current = mal_list[mal_id]
        else:
            current = get_my_anime_status(mal_id)
            mal_list[mal_id] = current  # cache for reuse
        current_status = current.get("status", "")
        score = movie_ratings.get(trakt_id) if sync_ratings else None

        trakt_url = _link("Trakt", f"https://trakt.tv/movies/{trakt_slug}")
        mal_url = _link(f"MAL {mal_id}", f"https://myanimelist.net/anime/{mal_id}")

        if current_status == "completed":
            if score is None or score == current.get("score", 0):
                stats.skipped += 1
                if verbose:
                    score_str = (
                        f", score={current.get('score')}"
                        if current.get("score")
                        else ""
                    )
                    print(
                        f"  [OK] {title} [{trakt_url}] [{mal_url}]: completed{score_str}"
                    )
                continue
            prefix = "[DRY RUN] " if dry_run else ""
            print(
                f"  {prefix}{title} [{trakt_url}] [{mal_url}]: update score → {score}"
            )
            try:
                update_anime(
                    mal_id,
                    current.get("num_watched_episodes", 1),
                    "completed",
                    score=score,
                    dry_run=dry_run,
                )
                stats.updated += 1
            except Exception as exc:
                print(f"  ERROR updating {title}: {exc}")
                stats.errors += 1
            continue

        try:
            total_eps = _get_total_episodes(mal_id, mal_list) or 1
        except Exception as exc:
            print(f"  ERROR fetching details for {title} (MAL {mal_id}): {exc}")
            stats.errors += 1
            continue

        score_str = f", score={score}" if score else ""
        prefix = "[DRY RUN] " if dry_run else ""
        print(f"  {prefix}{title} [{trakt_url}] [{mal_url}]: completed{score_str}")

        try:
            update_anime(mal_id, total_eps, "completed", score=score, dry_run=dry_run)
            stats.updated += 1
        except Exception as exc:
            print(f"  ERROR updating {title}: {exc}")
            stats.errors += 1

    print(f"\nDone: {stats}")
