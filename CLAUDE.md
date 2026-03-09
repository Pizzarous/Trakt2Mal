# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Trakt2Mal — a tool to sync watch history/data from [Trakt](https://trakt.tv) to [MyAnimeList](https://myanimelist.net).

One-way sync: Trakt → MAL. Reads watch history from Trakt, maps entries to MAL IDs, and updates MAL list status/episode counts/ratings.

## Stack

- Python 3
- Dependencies: `requests`, `python-dotenv` (see `requirements.txt`)
- No framework; plain scripts

## Architecture

```
main.py                  CLI entry point (argparse)
trakt2mal/
  auth.py                OAuth flows for Trakt and MAL
  trakt.py               Trakt API client
  mal.py                 MAL API client
  mapper.py              Trakt->MAL ID mapping (uses local DB files)
  sync.py                Core sync logic
overrides.json           Manual episode-range overrides for split-season shows
_run/                    Batch files for easy execution (see below)
```

## Commands

```
python main.py                              # sync once (default)
python main.py sync --dry-run              # preview changes without writing
python main.py sync --dry-run --verbose    # preview all entries (including in-sync)
python main.py sync --dry-run --unmatched  # show unmatched entries
python main.py sync --schedule 6h          # repeat every 6h
python main.py auth                        # authenticate both services
python main.py auth --trakt                # re-auth Trakt only
python main.py auth --mal                  # re-auth MAL only
python main.py update-db                   # download latest ID mapping DB
python main.py lookup <slug>               # find Trakt ID for a show
python main.py lookup --movie <slug>       # find Trakt ID for a movie
```

## _run/ Batch Files

| File | Description |
|---|---|
| `1-install.bat` | Install Python dependencies (`pip install -r requirements.txt`) |
| `2-auth.bat` | Authenticate both Trakt and MAL |
| `3-preview.bat` | Dry run - show planned changes |
| `4-preview-verbose.bat` | Dry run - show all entries including in-sync |
| `5-preview-unmatched.bat` | Dry run - show entries with no mapping |
| `6-sync.bat` | Run sync once |
| `7-sync-scheduled.bat` | Run sync every 6 hours (Ctrl+C to stop) |
| `8-update-db.bat` | Download latest Trakt->MAL mapping DB |
| `9-lookup.bat` | Look up a Trakt ID by slug (prompts for input) |

Authentication tokens are stored locally and persist across runs. Only re-auth if tokens expire or you switch accounts.

## Key Behaviours

- **DB update on every sync**: `run_sync()` calls `update_db()` at the start of each run.
- **Dropped protection**: If a MAL entry is marked `dropped`, the sync skips it entirely.
- **Episode range overrides**: `overrides.json` maps `(trakt_id, season)` to one or more MAL entries with explicit episode ranges. Used for shows where Trakt combines multiple MAL cours into one season. Episode numbers are normalized: ep N in range `[start, end]` maps to ep `N - (start - 1)` on MAL.

## MAL API Notes

- Fields must be explicit: `fields=num_episodes,list_status{num_episodes_watched,score,status}`
- `list_status` alone does NOT return `num_episodes_watched` - sub-fields must be listed explicitly.
- Inside `list_status`, the key is `num_episodes_watched` (not `num_watched_episodes`).
- Always verify raw API responses before assuming field names. Never assume.

## Overrides (overrides.json)

Manual mappings for split-season shows. Each entry has:
- `trakt_id` + `season`: identifies the Trakt show/season
- `mal_id`: the target MAL entry
- `episode_range`: `[start, end]` - which Trakt episode numbers map to this MAL entry

Multiple overrides for the same `(trakt_id, season)` split one Trakt season across multiple MAL entries.
