# Onboarding a new runner

Today's flow: about 15 minutes of setup, a wait for the first sync, then a conversation with the coach.

## 1. Before installing

- **GitHub**: create an account and accept the invite to the private repo.
- **Garmin**: sign in to the Garmin Connect Developer Program (personal access) and create a Personal API key.
- **Python**: macOS `xcode-select --install` (once, if Python isn't there); Windows `winget install Python.Python.3.12`.

## 2. Install (about 5 minutes, then the first sync)

1. Download the zip from GitHub and unzip it.
2. Run the installer in Terminal or PowerShell. It asks three things:
   - what to sync: runs and weight, or all data
   - how far back: 1 month, 1 year, 3 years or all
   - the API key, pasted with hidden input
3. It then copies the engine into `~/Claudromos`, creates the Python environment, stores the key securely, schedules the sync (every 3 hours and at login) and runs the first sync.
4. The first sync takes about a second per activity: roughly 20–30 minutes for 1,000 runs, longer with "all". Progress is only in `logs/sync.log`.

## 3. First look at the dashboard

Double-click `~/Claudromos/dashboards/claudromos.html`.

- **History** works straight away: volume, pace, elevation, VO2 max, weight, race progress.
- **Areas** are detected from GPS but named "Area 1 near 44.47, 26.08" until renamed.
- **Training** shows weekly volume, zones and runs, but no targets, countdowns or plan start until there is a `config/plan.json`.

## 4. Coach setup (Claude)

1. In the Claude desktop app, connect the `Claudromos` folder.
2. Upload the `claudromos-coach` skill zip.
3. Say "set me up". The coach reads the data and fills in what it can (watch, weekly volume, paces, races, HR settings, areas), asks one message's worth of questions (goals, plan, rules, fuelling, feedback style), writes `athlete.md` and shows it.
4. Optional: scheduled weekly and evening reviews; a phone-view artifact.

With GitHub Copilot or Gemini CLI instead: open the folder in VS Code or run `gemini` in it; `AGENTS.md` does the same job.

## Where it's rough today

| Gap | Effect |
| --- | --- |
| Onboarding doesn't name the areas | "Area 1 near …" until edited by hand |
| Onboarding doesn't create `plan.json` or race dates | No targets, countdowns or plan-start marker |
| Terminal required, private GitHub repo | A hurdle for non-technical runners |
| First sync shows no progress | Looks stuck for 20+ minutes |
| Skill uploaded as a zip by hand, after every update | Easy to fall behind the engine |
| Windows never run end to end | First Windows user is the tester |
| Claude desktop app needed for folder access | Phone-only users can't use the coach |

Next improvements (see `TODO.md`): name areas from OpenStreetMap during onboarding, build `plan.json` with race dates from whatever plan the runner shares, and show a "Getting started" checklist on the dashboard until both exist.
