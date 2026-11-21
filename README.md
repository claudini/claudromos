# Claudromos

Your running data, on your own computer, with a coach that reads it.

Claudromos syncs your Garmin data through the Garmin Connect Personal API to a folder on your Mac or Windows PC, rebuilds an offline dashboard whenever new data arrives, and comes with a Claude skill that analyses your runs, reviews your training weeks and helps with race targets, pacing and fuelling.

*Dromos* is Greek for a run, a race, or the racecourse itself.

## What you get

- **Sync** every 3 hours: every activity with its original FIT file, weigh-ins, and optionally everything else the API offers (VO2 max, HRV, sleep, daily summaries, HR zone settings).
- **Dashboard** at `Claudromos/dashboards/claudromos.html`: double-click to open, works offline.
  - Training: last and current week, flags, weekly volume against your plan, weight, recent runs.
  - History: totals, volume by year and month (road, trail, races), elevation, pace by month (trail grade-adjusted), pace in the areas you usually run, VO2 max with HR setting changes, VO2 max against road pace, weight, a Versus chart for any two metrics, race comparisons.
- **Coach**: the `claudromos-coach` skill for Claude reads your data and your own `athlete.md` profile.

Your data stays on your computer. Nothing is uploaded unless you ask Claude to.

## Install

### 1. Get a Garmin Personal API key

Sign in to Garmin Connect, open the Personal API key page (Garmin Connect Developer Program, personal access) and create a key. You'll paste it once into the installer; it is never shown, logged or sent anywhere but Garmin.

### 2. Run the installer

Get the code with git (below), or without git: [download the zip](https://github.com/claudini/claudromos/archive/refs/heads/main.zip) (you need access to the repo and to be signed in to GitHub) and unzip it to `src/claudromos` in your home folder.

Don't put the code in `~/Claudromos` or `~/claudromos`: that is the data folder, and macOS treats the two names as the same folder.

**macOS**

```
xcode-select --install          # once, if Python isn't there yet
git clone https://github.com/claudini/claudromos.git ~/src/claudromos
cd ~/src/claudromos
bash install.sh
```

**Windows** (PowerShell)

```
winget install Python.Python.3.12   # once, if Python isn't installed
git clone https://github.com/claudini/claudromos.git $env:USERPROFILE\src\claudromos
cd $env:USERPROFILE\src\claudromos
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer asks what to sync (runs and weight, or everything) and how far back (1 month, 1 year, 3 years, all), asks for the key, schedules the sync and runs the first one. A full history takes a while: about a second per activity.

### 3. Set up the coach

1. In the Claude desktop app, connect your `Claudromos` folder (+ menu, Add folder).
2. Add the skill: zip `coach/claudromos-coach` and upload it in Claude's settings (Capabilities, Skills).
3. Tell Claude "set me up". It reads your data, fills in what it can (watch, weekly volume, paces, races, HR settings, the areas you run in) and asks only for goals, plan and preferences. The result is `Claudromos/athlete.md`, yours to edit.

Optional: ask Claude to schedule a weekly review and an evening run check (prompts in `coach/claudromos-coach/references/weekly-review.md`), or to publish your dashboard as a private Claude artifact so you can open it on your phone.

## Everyday commands

Run them from the `Claudromos/.claudromos` folder, or from the repo.

| macOS | Windows | What it does |
| --- | --- | --- |
| `bash install.sh sync` | `... install.ps1 sync` | Sync now |
| `bash install.sh rebuild` | `... install.ps1 rebuild` | Rebuild the dashboard now |
| `bash install.sh update-key` | `... install.ps1 update-key` | Replace an expired key |
| `bash install.sh config` | `... install.ps1 config` | Choose again what to sync and how far back |
| `bash install.sh scope runs\|all` | `... install.ps1 scope runs\|all` | Change what is synced |
| `bash install.sh history 1m\|1y\|3y\|all` | `... install.ps1 history ...` | Change how far back (only the older part is fetched) |
| `bash install.sh diagnose` | `... install.ps1 diagnose` | Test the key (status codes only) |
| `bash install.sh uninstall` | `... install.ps1 uninstall` | Stop syncing and remove the key; data stays |

To update, `git pull` in the repo and run the installer again. Your data, key and settings are kept.

## Your settings

All optional, in `Claudromos/config/`:

| File | What it holds |
| --- | --- |
| `areas.json` | The areas you run in. Detected from your GPS tracks on the first build, named "Area 1 near ..." until you (or Claude) rename them |
| `plan.json` | Your training plan's phases and weekly targets, for the Training tab and weekly reviews |
| `overrides.json` | `exclude`: activity ids to ignore (an old import); `extra_races`: races your watch never tagged |
| `race_words.json` | Words that mark a likely race in a run's name |

`athlete.md` (in the data folder) is your profile for the coach. None of these files belong in the repo.

## Folder layout

```
Claudromos/
  athlete.md            your coach profile
  config/               your settings (above)
  activities/           summaries and original FIT files, by year
  weight/  health/      weigh-ins; daily health data (scope "all")
  dashboards/           claudromos.html
  settings_changes.csv  HR setting changes seen by the sync
  status.json  logs/    last sync result; sync log
  .claudromos/          engine: sync.py, tools/, venv, config.json, state.json, out/ (CSVs)
```

## How it works

- `engine/sync.py`: standard-library Python. Fetches a 24-hour token with your key, fills any gaps in the stored history, re-checks the last 3 days, and after any sync with new data runs `tools/build.py`. On macOS it uses the system `curl` (Apple's Python can't do the TLS Garmin needs); on Windows it uses Python's own HTTPS.
- `engine/tools/history.py`: every run with grade-adjusted pace (Minetti energy cost), its area and race course; race comparisons; weight; VO2 max.
- `engine/tools/review.py`: weekly totals against `plan.json`, flags, recent runs.
- `engine/tools/build.py`: runs both and writes the dashboard with the data embedded in the page.
- The key: macOS login Keychain (service `claudromos-garmin`); Windows DPAPI, readable only by your Windows account on that PC.

Garmin's API only reads: workouts can't be pushed to the watch.

## Moving from the earlier "Garmin sync" setup

Run `bash install.sh` from the repo. It offers to move `~/Garmin` to `~/Claudromos`, carries over the key, settings and sync state, and replaces the old schedule. Then connect `~/Claudromos` in the Claude desktop app in place of `~/Garmin`.
