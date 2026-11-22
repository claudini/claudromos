# Onboarding a new runner

A new runner goes through four stages: about 15 minutes of setup, a wait for the first sync, then a conversation with the coach. The gaps at the end are what to improve next.

## 1. Before installing

- **GitHub:** create an account and accept the invite to the private repo.
- **Garmin:** sign in to the Garmin Connect Developer Program (personal access) and create a Personal API key.
- **Python:** on a Mac, run `xcode-select --install` once if it isn't there. On Windows, `winget install Python.Python.3.12`.

## 2. Install (about 5 minutes, then the first sync runs)

1. Download the zip from GitHub and unzip it.
2. Run the installer in Terminal or PowerShell. It asks three things:
   - what to sync: runs and weight, or all data
   - how far back: 1 month, 1 year, 3 years or all
   - the API key, pasted with hidden input
3. It sets up everything else on its own:
   - copies the engine into `~/Claudromos`
   - creates the Python environment
   - stores the key securely
   - schedules the sync (every 3 hours and at login)
   - runs the first sync
4. **The first sync takes about a second per activity:** roughly 20–30 minutes for 1,000 runs, longer with "all". The only progress shown is the log file.

## 3. First look at the dashboard

Double-click `~/Claudromos/dashboards/claudromos.html`.

- **History** works straight away: volume, pace, elevation, VO2 max, weight and race progress.
- **Areas** are detected from GPS but appear as "Area 1 near 44.47, 26.08" until someone renames them.
- **Training** shows weekly volume, zones and runs, but no targets, countdowns or plan start until there's a `plan.json`.

## 4. Coach setup (in Claude)

1. In the Claude desktop app, connect the `Claudromos` folder.
2. Upload the `claudromos-coach` skill zip.
3. Say **"set me up"**. The coach reads their data and fills in the watch, weekly volume, paces, races, HR settings and areas. It then asks one message's worth of questions (goals, plan, rules, fuelling, feedback style), writes their `athlete.md` and shows it to them.
4. Optionally: scheduled weekly and evening reviews, and a phone-view artifact.

People on Copilot or Gemini skip this stage: they open the folder in VS Code or run `gemini` there, and `AGENTS.md` takes over.

## Where it's rough today

| Gap | Effect |
| --- | --- |
| Onboarding doesn't name the areas | "Area 1 near …" until edited by hand |
| Onboarding doesn't create `plan.json` or race dates | No targets, countdowns or plan-start marker |
| Terminal required, private GitHub repo | A hurdle for non-technical runners |
| First sync shows no progress | Looks stuck for 20+ minutes |
| Skill uploaded as a zip, by hand, after every update | Easy to fall behind the engine |
| Windows never run end to end | First Windows user is the tester |
| Claude desktop app needed for folder access | Phone-only users can't use the coach |

## Next improvements

- Name the areas from OpenStreetMap during onboarding.
- Build `plan.json`, with race dates, from whatever plan the runner shares (a doc, a PDF or a description).
- Show a "Getting started" checklist on the dashboard until both exist.
- Then test the whole flow on a fresh Windows install.
