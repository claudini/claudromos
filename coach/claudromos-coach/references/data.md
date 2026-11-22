# Data, tools and sync

`D` below is the athlete's data folder (see SKILL.md). Reach it with the `mcp__remote-devices__` tools. When `device_bash` is present it is mounted at `$HOME/mnt/<folder name>`; otherwise stage the files you need with `device_stage_files` (they land under `/mnt/user-data/uploads/<folder name>/`) and work in the cloud workspace.

Installs from before the Claudromos rename keep the engine in `D/.sync/` with tools named `garmin_review.py` and `garmin_history.py`, and their config in `D/.sync/`. Check which layout is present before running anything.

## Layout

| Path | Contents |
|---|---|
| `athlete.md` | The athlete's profile, goals, plan pointer and preferences |
| `journal.csv` | Body notes: `date,body_part,severity,note` (see SKILL.md) |
| `config/plan.json` | Plan: `start`, `phases` (weeks, km, hours, gain_m, focus), `lighter_week_every`, `races` (name, date); used by the dashboard and review tool (optional) |
| `config/areas.json` | Named areas (bounding boxes) the athlete runs in |
| `config/overrides.json` | `exclude`: activity ids to ignore; `extra_races`: races the watch never tagged |
| `activities/index.json` | One record per activity: `date`, `start_local`, `name`, `type`, `event_type` (`race` or other), `distance_m`, `duration_s`, `elevation_gain_m`, `avg_hr`, `summary`, `fit` |
| `activities/YYYY/<date>_<id>_<name>.fit` | Original FIT file: GPS, altitude, HR, cadence, temperature per second |
| `activities/YYYY/<...>.json` | Watch vendor's summary (splits, HR zones, training effect, cadence, max HR) |
| `weight/weight.csv` | `date, weight_kg, body_fat_pct, muscle_mass_kg` |
| `health/<name>/<YYYY>.json` | Daily health data, `{date: [records]}`: VO2 max, HRV, sleep, resting HR and more |
| `health/snapshots/` | Latest profile settings and HR zones |
| `settings_changes.csv` | HR setting changes: `date, setting, from, to, date_basis, note` |
| `status.json` | Last sync: `ok`, `error_code`, `last_run`, `last_success`, counts, warnings |
| `logs/sync.log` | One line per sync |
| `.claudromos/` | Engine: `sync.py`, `tools/`, installers, `config.json`, `state.json`, `out/` (CSVs) |
| `dashboards/claudromos.html` | Offline dashboard (Training and History tabs) with the data embedded; rebuilt after each sync with new data |

FIT cadence is per leg; multiply by 2 for steps per minute. Some hikes are recorded as trail runs: count them in time and gain, but say so when they distort km or pace.

## Fresh data

The computer syncs every 3 hours and soon after `.claudromos/trigger` is touched: at once on macOS (launchd watches the file), within 15 minutes on Windows (the scheduled task checks every 15 minutes).

1. Note `last_run` in `status.json`, then touch the trigger (`touch $HOME/mnt/<folder>/.claudromos/trigger` in `device_bash`).
2. Poll `status.json` every 10 s until `last_run` changes: up to 2 minutes on macOS. On Windows, poll every 30 s for up to 16 minutes, or carry on with the data there if the question doesn't need the newest run. If it doesn't, the computer may be asleep or the schedule not installed; carry on with the data there and say how old it is.
3. If `ok` is false:
   - `KEY_REJECTED`: the API key expired or was deleted. The athlete creates a new key and runs the installer's `update-key` option (below). Never ask for the key.
   - `NETWORK`: usually transient; try again later.
   - Anything else: read the last lines of `logs/sync.log`.

Installer options (macOS: `bash D/.claudromos/install.sh <option>` in Terminal; Windows: `powershell -ExecutionPolicy Bypass -File D\.claudromos\install.ps1 <option>`): `sync`, `rebuild`, `config`, `scope runs|all`, `history 1m|1y|3y|all`, `update-key`, `diagnose`, `uninstall`. Updates come from the athlete's clone of the repo: `git pull`, then the installer with no option.

## Tools

The engine rebuilds the CSVs in `.claudromos/out/` and the dashboard after any sync that brings new data, so they are usually current. To run the tools yourself (needs `pip install fitdecode`; add `-X utf8` on Windows):

```
T=<D>/.claudromos/tools
python3 -I $T/build.py --root <D>                      # everything: CSVs into .claudromos/out and the dashboard
python3 -I $T/history.py --root <D> --out <dir>        # runs_all, courses, course_runs, weight_all, vo2max, race_candidates, settings_changes
python3 -I $T/review.py weekly --root <D> [--week-ending YYYY-MM-DD] [--json wk.json]
python3 -I $T/review.py runs --root <D> --from YYYY-MM-DD [--to YYYY-MM-DD]
python3 -I $T/review.py export --root <D> --out <dir>  # weeks, runs, weight, flags for the training dashboard
python3 -I $T/fit_convert.py <file.fit> --gpx run.gpx --csv run.csv
```

Keep your own scripts outside the staged uploads folder. The GPX from `fit_convert.py` loads with the parser in `analysis.md` unchanged; its CSV already has steps per minute.

`history.py` details: grade-adjusted pace uses Minetti's energy cost on 25 m segments; a run belongs to an area when at least 35% of its track is inside the area's box; races start within 3 km and differ by at most 12% in distance to share a course, and training runs join a course at 80% route overlap both ways.

## Dashboards

`D/dashboards/claudromos.html` is self-contained: the build writes the data into the page, so it opens offline by double-click. If the athlete says it looks stale:

1. Check `status.json` (`rebuild` should be `ok`) and the end of `logs/sync.log` for a "Rebuild failed" line.
2. Rebuild: the installer's `rebuild` option, or `build.py` yourself.
3. If a chart is wrong for everyone, fix `engine/dashboards/claudromos.template.html` in the repo, not the athlete's copy.

### The same dashboard in Claude (phone access)

If `athlete.md` names a Claude artifact for the dashboard, refresh it after a rebuild (the weekly review does this):

1. Stage `D/dashboards/claudromos.html` with `device_stage_files`.
2. Republish it to that artifact with the artifact tool's file publish (`as: index.html`), passing the live version from a fresh read of the artifact.
3. Say in one line that the phone view is updated. The artifact is private to the athlete unless they share it.

If there is no artifact yet and the athlete wants one, publish the file as a new artifact titled "Claudromos" and add its link to `athlete.md` under Setup.

## Changing engine files

After changing a file in the cloud workspace, copy it to `/mnt/user-data/outputs/`, wait a few seconds, `device_commit_files` it into `D/.claudromos/`, then confirm the size with `device_list_dir`: a commit right after writing can send the previous version. Changes that every user needs belong in the shared repo.

The watch APIs only read: workouts can't be pushed to the watch.
