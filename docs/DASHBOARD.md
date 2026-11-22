# Dashboard

`~/Claudromos/dashboards/claudromos.html` is one offline page with three tabs: **Training**, **History** and **Plan**. Double-click it to open; reload after a sync to see new data.

## How it's built

- After any sync that brings new data or a changed setting, `build.py` runs `history.py` and `review.py`, which write CSVs to `.claudromos/out/`. It then copies `.claudromos/dashboards/claudromos.template.html` with all the data written into the page, so it works without a server or internet.
- The header shows the sync the page was built from and when it was built.
- The same file can be published as a private Claude artifact for phone access (the weekly review refreshes it).
- Charts are plain SVG; hover any bar, point or line for its numbers.

## Definitions used throughout

| Term | Meaning |
| --- | --- |
| Run | Any activity whose type contains "running" (road, trail, treadmill), minus ids in `exclude` |
| Race | Tagged as a race in Garmin Connect, or listed in `extra_races` |
| Surface | trail = Garmin's trail running type; treadmill; everything else road |
| Hike | A non-race trail activity slower than 15:00/km overall or with an average cadence under 100 spm |
| GAP | Grade-adjusted pace: each 25 m of the track is scaled by Minetti's energy cost of running at that gradient, so a hilly run compares with a flat one; stops count only as a slow walk |
| Area | Where a run happened: the named area holding at least 35% of its track (`config/areas.json`), else "near home, other", "Away" or "Treadmill / no GPS" |
| Run name | Garmin's default names ("Bucharest Running") are shown as the area the run was in; races and names you chose stay as they are (`rename_default_names`) |
| HR zones | Garmin's current zone floors (Default sport, from the daily settings snapshot) applied to the heart rate in each run's FIT file. Below zone 1 counts as zone 1. Gaps over 10 s count as 10 s. Using today's zones for every year keeps old and new weeks comparable |
| Week | Monday to Sunday |

## Training tab

### Header cards

| Card | Shows |
| --- | --- |
| Week N of M | Plan week (from `config/plan.json` `start`), plan start date and the phase's focus. Before the start: days to the plan start |
| Days to … | One card per race in `plan.json` `races` |
| This week so far | km, dates and number of runs, with the plan's target for the week |
| Last week | km and the long run of the last complete week |
| Load | km in the last 7 days ÷ the weekly average of the last 28 days |
| Weight | Latest weigh-in and the change over the 4 weeks before it |

### Flags

Checked live, so they appear during the week, not only after it:

- This week more than 15% over the plan's km target.
- This week is a planned lighter week.
- Ramp: this week already more than 10% above last week.
- Load ratio above 1.3.
- Last week under 80% of its target.
- A run since last Monday that looks like a hike (counted for time and climbing, not pace).
- A body part noted twice or more in `journal.csv` within 4 weeks.
- Any body note from the last 7 days.

### Body notes

`journal.csv` entries from the last 8 weeks: date, body part, severity (1–5, optional), note. The coach adds a line whenever you mention a symptom.

### Weekly volume against the plan

- 26 weeks back to the end of the plan, switchable between **km**, **hours** and **climbing**.
- Solid bars: done. Faint bar with ▲: this week so far.
- Black ticks: the plan's target for the week, faint for weeks ahead. Targets run linearly from the first to the last value of each phase (`km`, `hours`, `gain_m` in `plan.json`).
- Grey bands: planned lighter weeks (`lighter_week_every`, up to `lighter_weeks_until`).
- Dashed lines: plan start, and race weeks (orange).
- Red dot: a body note that week.

### Time in heart-rate zones

Each week as a 100% bar: **easy** (zones 1–2), **zone 3**, **hard** (zones 4–5), with a dashed line at 80% easy. Hover for the minutes. The zone floors in use are listed in the legend.

### Weight

Weigh-ins over the last 26 weeks.

### Runs, last 8 weeks

| Column | Meaning |
| --- | --- |
| Surface | road, trail, treadmill or hike, plus "race" |
| Pace | Actual pace on road; GAP on trail |
| Avg HR | With the zone it falls in |
| Easy | Share of the run's time in zones 1–2 |
| Cadence | Average running cadence (steps per minute) from Garmin's summary |

## History tab

### Totals

Runs, distance, hours, elevation gain, races and the first run.

### Volume by year

Runs, km (road, trail, races), trail share of training km (races left out), hours, gain, median road pace and median trail GAP. Click a year to see its months.

### Volume by month

Stacked road, trail and race km. Click a legend item to hide it.

### Elevation by year

Total climbing per year.

### Average pace by month

Median pace of non-race runs of 3 km or more, in months with at least 2 such runs; trail uses GAP. Road races are drawn as dots. Faster is higher. Each series can be switched off.

### Usual runs: pace and effort by area

- Per area and quarter, for non-race runs of 3 km or more, in quarters with at least 2 runs.
- Switch between **pace** (GAP weighted by distance: total time ÷ total distance), **average HR** (weighted by time) and **efficiency** (metres covered per heartbeat; higher is fitter).
- The status table compares the last 6 months with the 12 months before, area by area. A pace change counts from 5 s/km, an HR change from 2 bpm:

| Pace | HR | Status |
| --- | --- | --- |
| faster | same | Faster at the same effort |
| faster | lower | Faster, and easier effort |
| faster | higher | Faster, but working harder |
| same | lower | Same pace, easier effort |
| same | same | Maintaining |
| same | higher | Same pace, working harder |
| slower | lower | Slower, but easier effort |
| slower | same | Getting slower |
| slower | higher | Slower and working harder |

### VO2 max

Garmin's daily estimate, with dashed lines at HR setting changes (from `settings_changes.csv`), which shift the estimate.

### Weight

Every weigh-in.

### Correlation does not imply causation

Any two monthly metrics on one chart with two axes: road pace, trail GAP, distance, average HR, average cadence, VO2 max (monthly mean), weight (monthly mean). Pace, HR and cadence use non-race runs, at least 2 in the month.

### Race progress

Pick a race course to see every attempt: races and training runs on the same route (both tracks overlap at least 80%). Time is shown against the fastest race on the course; a minus means faster. Courses listed in `races_only_courses` show races only.

### All race courses

Every course with its distance, gain, attempts, races and first and last dates. Races share a course when they start within 3 km of each other, differ by at most 12% in distance and overlap in route.

## Plan tab

### Week by week

Every plan week from `config/plan.json`: dates, the phase's focus (with lighter-week notes and race days), the target (km, hours, climbing), what you did, a status (on target within −20%/+15%, over, under, in progress) and the number of body notes. The current week is highlighted.

### The plan document

`config/plan.md` rendered as a page: headings, lists, tables, bold and links. If the plan lives elsewhere (a Claude Project doc, say), the coach keeps this copy and `plan.json` in step when it changes.

## Settings that change the dashboard

| File | Affects |
| --- | --- |
| `config/plan.json` | Week cards, targets, lighter weeks (`lighter_weeks` list or `lighter_week_every`), race countdowns and markers, flags, the Plan tab's weeks |
| `config/plan.md` | The Plan tab's document |
| `config/areas.json` | Area names, usual runs, run names |
| `config/overrides.json` | Excluded activities, extra races, races-only courses, default-name renaming |
| `config/race_words.json` | Which run names count as likely races |
| `journal.csv` | Body notes, their flags and chart dots |
| Garmin HR zone settings | Zone floors for time in zones and the zone shown per run |
