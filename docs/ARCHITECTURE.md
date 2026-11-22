# Claudromos: structure and architecture

Claudromos has four parts: the code (this repo), the install on each runner's computer, the dashboard, and the coach.

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
      │        └─► optional private Claude artifact (phone view)
      │
      └─► Coach: Claude (claudromos-coach skill + scheduled tasks), or Copilot / Gemini (AGENTS.md)
              reads athlete.md, config/, journal.csv and the CSVs; writes body notes to journal.csv
```

## The repo

```
claudromos/
├── README.md                  install (zip first, git second), commands, settings
├── TODO.md
├── docs/                      this file, ONBOARDING.md
├── install.sh                 macOS: migrate from ~/Garmin, venv, Keychain key, launchd schedule
├── install.ps1                Windows: venv, DPAPI-encrypted key, Task Scheduler (every 15 min + at logon)
├── engine/
│   ├── sync.py                standard library only; curl on macOS, urllib on Windows
│   ├── DATA_README.md         copied into each data folder as README.md
│   ├── tools/
│   │   ├── build.py           runs the two tools below, then fills in the dashboard template
│   │   ├── history.py         all runs: GAP, areas, courses/races, HR zones, cadence, weight, VO2 max
│   │   ├── review.py          weekly totals against plan.json; runs list; text reviews
│   │   └── fit_convert.py     FIT → GPX/CSV for single-run analysis
│   └── dashboards/
│       └── claudromos.template.html   Training + History tabs, plain JS/SVG, no libraries
└── coach/
    ├── AGENTS.md              coach instructions for GitHub Copilot (VS Code) and Gemini CLI
    └── claudromos-coach/      the Claude skill
        ├── SKILL.md           reads athlete.md first; body notes; safety
        ├── references/        data.md · analysis.md · weekly-review.md · onboarding.md
        └── assets/athlete.template.md
```

Branches: `main` is stable for everyone; `dev` is where changes land first.

## On each computer (`~/Claudromos`)

| Path | Owner | What it is |
| --- | --- | --- |
| `athlete.md` | runner | Coach profile: goals, HR settings, races, rules, quirks |
| `journal.csv` | runner (via coach) | Body notes: date, body part, severity, note |
| `config/plan.json` | runner | Plan start, phases, targets, races |
| `config/areas.json` | auto, then runner | Areas detected from GPS; rename them |
| `config/overrides.json` | runner | Excluded imports, extra races, races-only courses, default-name renaming |
| `activities/`, `weight/`, `health/` | sync | Raw Garmin data: summaries, FIT files, daily health |
| `settings_changes.csv` | sync | HR setting changes seen in the daily snapshot |
| `status.json`, `logs/` | sync | Last result and history of syncs and rebuilds |
| `dashboards/claudromos.html` | build | The offline dashboard |
| `README.md` | installer | What is in the folder and the everyday commands |
| `.claudromos/` | installer | Engine copy, venv, key (Windows), config, state, `out/` CSVs, coach skill copy, trigger file |
| `AGENTS.md`, `.github/`, `.gemini/` | installer | Coach setup for other assistants (left alone once the runner edits it) |

Nothing personal goes into the repo.

## Design choices

- **Plain files only**: JSON, CSV and FIT; no database, no server. Any tool can read the data, and nothing breaks if Claude isn't there.
- **Incremental sync**: per-type coverage tracking fetches only gaps plus the last 3 days. Extending the history fetches only the older part; an interrupted sync resumes.
- **Rebuild only on change**: the sync fingerprints the data and config files by content.
- **One dashboard, two places**: the same self-contained HTML opens offline and can be published as a private Claude artifact for phone access.
- **Personal settings live only in the data folder**: areas come from GPS, race words and plan are config, the coach reads `athlete.md`.
- **The key never touches a file in plain text or a chat**: macOS Keychain, or Windows DPAPI per user; passed to curl on stdin.
- **HR zones from the FIT heart rate and the current zones**, so every year is comparable whatever the watch settings were then.

## Claude around it

- **Skill**: `claudromos-coach`, uploaded as a zip from `coach/claudromos-coach`.
- **Scheduled tasks** (optional, on the runner's computer): a weekly review that syncs, reviews against the plan and refreshes the phone artifact; an evening check that reviews that day's run.
- **Chats**: one for training and plan feedback; any other chat for building Claudromos. All of them read the same files.
