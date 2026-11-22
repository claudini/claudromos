<!-- claudromos:generated - the installer refreshes this file -->
# Claudromos data folder

Your Garmin data, synced by Claudromos every 3 hours and at login, plus your coach profile. Code and docs: https://github.com/claudini/claudromos

## Open the dashboard

Double-click `dashboards/claudromos.html`. It's rebuilt after every sync that brings new data; reload the page to see it.

## Yours to edit

| File | What it is |
| --- | --- |
| `athlete.md` | Your coach profile: goals, HR settings, races, rules, preferences |
| `journal.csv` | Body notes (date, body part, severity 1–5, note); the coach adds lines when you mention a symptom |
| `config/plan.json` | Your plan: start date, phases with weekly targets, races |
| `config/areas.json` | The areas you run in; rename "Area 1 near …" to real names |
| `config/overrides.json` | Activities to exclude, untagged races, races-only courses, default-name renaming |

## Written by the sync (don't edit)

- `activities/`: `index.json` plus, per year, each activity's summary (`.json`) and original `.fit` file
- `weight/weight.csv`: date, weight_kg, body_fat_pct, muscle_mass_kg
- `health/`: daily VO2 max, HRV, sleep, steps and more (sync scope "all"); `snapshots/` has current settings
- `settings_changes.csv`: HR setting changes (max, resting, zone method)
- `status.json`: last sync; `error_code` `KEY_REJECTED` means the API key expired
- `logs/sync.log`: one line per sync and rebuild
- `.claudromos/`: the engine, its settings and the CSVs the dashboard is built from

## Commands

macOS: `bash ~/Claudromos/.claudromos/install.sh <option>`
Windows: `powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\Claudromos\.claudromos\install.ps1 <option>`

Options: `sync`, `rebuild`, `update-key`, `config`, `scope runs|all`, `history 1m|1y|3y|all`, `schedule` (macOS), `diagnose`, `uninstall`.

To sync now, ask your coach or use the `sync` option.
