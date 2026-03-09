# Trakt2Mal

Sync your anime watch history from [Trakt](https://trakt.tv) to [MyAnimeList](https://myanimelist.net). One-way sync: Trakt → MAL.

## Setup

**1. Install dependencies**

```
_run/1-install.bat
```

Or manually: `pip install -r requirements.txt`

**2. Configure credentials**

Copy `.env.example` to `.env` and fill in your API keys:

```env
TRAKT_CLIENT_ID=...
TRAKT_CLIENT_SECRET=...
MAL_CLIENT_ID=...
MAL_CLIENT_SECRET=...
```

**3. Authenticate**

```
_run/2-auth.bat
```

This opens browser flows for both Trakt and MAL. Tokens are saved locally and persist across runs — you only need to do this once (or if tokens expire).

## Usage

Double-click any batch file in `_run/`:

| File                      | What it does                                      |
| ------------------------- | ------------------------------------------------- |
| `1-install.bat`           | Install Python dependencies                       |
| `2-auth.bat`              | Authenticate both Trakt and MAL                   |
| `3-preview.bat`           | Show planned changes without applying them        |
| `4-preview-verbose.bat`   | Show all entries, including those already in sync |
| `5-preview-unmatched.bat` | Show entries that have no Trakt→MAL mapping       |
| `6-sync.bat`              | Apply sync to MAL                                 |
| `7-sync-scheduled.bat`    | Sync every 6 hours continuously (Ctrl+C to stop)  |
| `8-update-db.bat`         | Download the latest Trakt→MAL ID mapping database |
| `9-lookup.bat`            | Look up a show's Trakt ID by its slug             |

### Command Line

```bash
python main.py sync                        # sync once
python main.py sync --dry-run              # preview changes
python main.py sync --dry-run --verbose    # preview everything
python main.py sync --schedule 6h          # repeat every 6 hours
python main.py auth                        # authenticate both services
python main.py update-db                   # update mapping database
python main.py lookup solo-leveling        # find Trakt ID for a show
python main.py lookup --movie spirited-away
```

## How It Works

1. Fetches your watch history from Trakt (shows + movies)
2. Maps each Trakt entry to a MAL ID using the [Anime Offline Database](https://github.com/manami-project/anime-offline-database)
3. Compares episode counts and status against your MAL list
4. Updates MAL entries that are out of sync

### Split-Season Overrides

Some anime are split across multiple MAL entries but grouped as one season on Trakt (e.g. a 24-episode Trakt season maps to two 12-episode MAL entries). These are handled via `overrides.json`, which maps Trakt episode ranges to specific MAL entries.

### Dropped Shows

If a show is marked as `dropped` on MAL, the sync will never overwrite it. Mark shows as dropped on MAL to permanently exclude them from syncing.

## Notes

- The mapping database is updated automatically at the start of every sync.
- Only anime tracked on Trakt with a matching MAL entry will be synced.
- Ratings are synced along with episode counts (can be disabled with `--no-ratings`).
