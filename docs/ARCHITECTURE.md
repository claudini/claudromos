# Architecture

Claudromos is four things: the code in this repo, the install on each runner's computer, the dashboards, and the coach.

## How data flows

```
Garmin watch → Garmin Connect
      │  Personal API (read-only; the runner's key, 24-hour token)
      ▼
sync.py on the runner's computer ── every 3 h, at login, or when the trigger file is touched
      │  writes raw files: activities + FIT, weight, health data, HR settings log
      ▼
~/Claudromos (data folder)
      │  after any sync that brings new data:
      ▼
build.py → history.py + review.py → CSVs in .claudromos/out/
      │
      ├─► dashboards/claudromos.html   (offline page, data embedded)
      │        └─► optional private Claude artifact (phone view, refreshed by the weekly review)
      │
      └─► Coach: Claude (claudromos-coach skill + scheduled tasks), or Copilot / Gemini (AGENTS.md)
              reads athlete.md, config/, journal.csv and the CSVs; writes body notes to journal.csv
```

## The repo

```
claudromos/
├── README.md                  install (zip first, git second), commands, settings
├── TODO.md
├── docs/                      ARCHITECTURE.md (this file), DASHBOARD.md, ONBOARDING.md
├── install.sh                 macOS: migrate from ~/Garmin, venv, Keychain key, launchd schedule
├── install.ps1                Windows: venv, DPAPI-encrypted key, Task Scheduler (every 15 min + at logon)
├── engine/
│   ├── sync.py                standard library only; curl on macOS, urllib on Windows
│   ├── tools/
│   │   ├── build.py           runs the two tools below, then fills in the dashboard template
│   │   ├── history.py         all runs: GAP, areas, courses/races, HR zones, cadence, weight, VO2 max
│   │   ├── review.py          weekly totals against plan.json; runs list; text reviews
│   │   └── fit_convert.py     FIT → GPX/CSV for single-run analysis
│   └── dashboards/
│       └── claudromos.template.html   Training + History tabs, plain JS/SVG, no libraries
└── coach/
    ├── AGENTS.md              coach instructions for Copilot (VS Code) and Gemini CLI
    └── claudromos-coach/      the Claude skill
        ├── SKILL.md           reads athlete.md first; body notes; safety
        ├── references/        data.md · analysis.md · weekly-review.md · onboarding.md
        └── assets/athlete.template.md
```

Branches: `main` is stable for everyone; `dev` is where changes land first and is tested on one install before merging.

## On each computer (~/Claudromos)

| Path | Owner | What it is |
| --- | --- | --- |
| `athlete.md` | runner | Coach profile: goals, HR settings, races, rules, quirks |
| `journal.csv` | runner (via coach) | Body notes: date, body part, severity, note |
| `config/plan.json` | runner | Plan start, phases, targets, races |
| `config/areas.json` | auto, then runner | Areas detected from GPS, renamed by hand |
| `config/overrides.json` | runner | Excluded imports, extra races, races-only courses, default-name renaming |
| `config/race_words.json` | runner (optional) | Words that mark a likely race in a run's name |
| `activities/`, `weight/`, `health/` | sync | Raw Garmin data: summaries, FIT files, daily health |
| `settings_changes.csv` | sync | HR setting changes seen in the daily snapshot |
| `status.json`, `logs/` | sync | Last result and history of syncs and rebuilds |
| `dashboards/claudromos.html` | build | The offline dashboard |
| `.claudromos/` | installer | Engine copy, venv, key (Windows), config, state, `out/` CSVs, coach skill copy, trigger file |
| `AGENTS.md`, `.github/`, `.gemini/` | installer | Coach setup for other assistants (left alone once the runner edits it) |

None of the personal files belong in the repo.

## Key design choices

- **Plain files only:** JSON, CSV and FIT, with no database or server. Any tool can read the data, and nothing breaks if Claude isn't there.
- **Incremental sync:** coverage tracking means only gaps and the last 3 days are fetched. Extending the history fetches only the older part, and an interrupted sync resumes.
- **Rebuild only on change:** the sync compares the data and config files by content, so a sync with no new data doesn't rebuild anything.
- **One dashboard, two places:** the same HTML file works offline on the computer and as an optional private Claude artifact for the phone.
- **Personal settings live only in the data folder.** The code stays generic: areas come from GPS, race words and plan are config, and the coach reads `athlete.md`.
- **The key never touches a file or a chat:** it lives in the macOS Keychain, or is encrypted per user on Windows (DPAPI), and is passed to curl through stdin.
- **HR zones from the FIT heart rate and the current zone settings,** so weeks from different years compare even after the zones change.

## Claude around it

- **Skill:** `claudromos-coach`, uploaded as a zip of `coach/claudromos-coach`.
- **Scheduled tasks** (optional, on the runner's computer): a weekly review that syncs, reviews against the plan and refreshes the phone artifact; an evening check that reviews that day's run.
- **Chats:** keep one for building Claudromos and one per runner for training and plan feedback; both read the same files.
