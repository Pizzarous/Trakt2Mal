#!/usr/bin/env python3
"""
Trakt2Mal — sync Trakt watch history to MyAnimeList.

Usage
-----
  python main.py                        # sync once (default)
  python main.py sync --dry-run         # preview without writing
  python main.py sync --no-ratings      # skip rating sync
  python main.py sync --schedule 6h     # repeat every 6 hours (Ctrl+C to stop)
  python main.py auth                   # authenticate both services
  python main.py auth --trakt           # re-auth Trakt only
  python main.py auth --mal             # re-auth MAL only
  python main.py update-db              # download latest ID mapping DB
  python main.py lookup solo-leveling   # find Trakt ID for a show
  python main.py lookup --movie spirited-away  # find Trakt ID for a movie
"""
import argparse
import sys
import time
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_interval(value: str) -> int:
    """Parse '6h' / '30m' / '1d' / '90s' into seconds."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = value[-1].lower()
    if unit not in units:
        raise argparse.ArgumentTypeError(
            f"Unknown time unit '{unit}'. Use s / m / h / d  (e.g. 6h, 30m, 1d)."
        )
    try:
        amount = int(value[:-1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid interval '{value}'.")
    return amount * units[unit]


def _human_interval(seconds: int) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trakt2mal",
        description="Sync Trakt watch history to MyAnimeList (one-way).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # sync
    sync_p = sub.add_parser("sync", help="Sync Trakt → MAL (default action)")
    sync_p.add_argument(
        "--dry-run", action="store_true",
        help="Print planned changes without writing to MAL",
    )
    sync_p.add_argument(
        "--no-ratings", action="store_true",
        help="Skip syncing ratings",
    )
    sync_p.add_argument(
        "--schedule", metavar="INTERVAL", type=_parse_interval,
        help="Repeat on a schedule, e.g. 6h, 30m, 1d (Ctrl+C to stop)",
    )
    sync_p.add_argument(
        "--unmatched", action="store_true",
        help="Print entries that have no Trakt→MAL mapping",
    )
    sync_p.add_argument(
        "--verbose", action="store_true",
        help="Print all matched entries, including those already in sync",
    )

    # auth
    auth_p = sub.add_parser("auth", help="Authenticate with Trakt and/or MAL")
    auth_p.add_argument("--trakt", action="store_true", help="Re-authenticate Trakt only")
    auth_p.add_argument("--mal", action="store_true", help="Re-authenticate MAL only")

    # update-db
    sub.add_parser("update-db", help="Download latest Trakt→MAL ID mapping database")

    # lookup
    lookup_p = sub.add_parser("lookup", help="Find the Trakt ID for a show or movie by its slug")
    lookup_p.add_argument("slug", help="Trakt slug, e.g. solo-leveling")
    lookup_p.add_argument("--movie", action="store_true", help="Look up a movie instead of a show")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # No subcommand → default to a single sync
    if args.command is None:
        from trakt2mal.sync import run_sync
        run_sync()
        return

    if args.command == "auth":
        from trakt2mal.auth import setup_auth
        setup_auth(trakt_only=args.trakt, mal_only=args.mal)
        return

    if args.command == "update-db":
        from trakt2mal.mapper import update_db
        update_db()
        return

    if args.command == "lookup":
        from trakt2mal.trakt import lookup_slug
        media_type = "movies" if args.movie else "shows"
        result = lookup_slug(args.slug, media_type)
        if not result:
            print(f"Not found: {args.slug}")
            return
        ids = result.get("ids", {})
        print(f"Title    : {result.get('title')}")
        print(f"Trakt ID : {ids.get('trakt')}")
        print(f"Slug     : {ids.get('slug')}")
        print(f"TMDB     : {ids.get('tmdb')}")
        print(f"TVDB     : {ids.get('tvdb')}")
        return

    if args.command == "sync":
        from trakt2mal.sync import run_sync

        kwargs = dict(dry_run=args.dry_run, sync_ratings=not args.no_ratings, show_unmatched=args.unmatched, verbose=args.verbose)

        if args.schedule:
            label = _human_interval(args.schedule)
            print(f"Scheduled mode — syncing every {label}. Press Ctrl+C to stop.")
            try:
                while True:
                    run_sync(**kwargs)
                    print(f"Next sync in {label}.")
                    time.sleep(args.schedule)
            except KeyboardInterrupt:
                print("\nStopped.")
        else:
            run_sync(**kwargs)


if __name__ == "__main__":
    main()
