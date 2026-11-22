#!/usr/bin/env python3
"""Build a demo dashboard from made-up data, so people can see Claudromos without a Garmin account.

Usage: python3 demo.py [--out demo/claudromos-demo.html] [--seed 7]

Everything here is invented: a runner with about four years of running in five areas, three yearly races,
weigh-ins, VO2 max, a 26-week plan that started three weeks ago, and a few body notes. Dates are relative
to the day it is built, so countdowns and "this week" always look current.
"""
import argparse
import datetime as dt
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "dashboards", "claudromos.template.html")
ZONES = [118, 131, 145, 159, 173]          # zone 1-5 floors, made up (max 188, resting 48, % of HR reserve)

AREAS = [  # name, surface, typical km, gain per km, pace offset s/km
    ("Riverside Park", "road", 10, 3, 0),
    ("City Forest", "trail", 12, 14, 25),
    ("Stadium Track", "road", 7, 1, -10),
    ("Old Town Streets", "road", 8, 6, 5),
    ("Hill Loop", "trail", 15, 30, 45),
]
RACES = [  # name, month, day, km, gain, surface
    ("Spring Half Marathon", 4, 20, 21.1, 60, "road"),
    ("Autumn 10K", 10, 12, 10.0, 25, "road"),
    ("Forest Trail 25K", 6, 8, 25.0, 950, "trail"),
]


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def zone_split(avg_hr, seconds, rnd):
    """Spread a run's seconds over zones around its average HR."""
    sd = 7
    out = [0.0] * 5
    for _ in range(40):
        hr = rnd.gauss(avg_hr, sd)
        z = sum(1 for f in ZONES[1:] if hr >= f)
        out[z] += seconds / 40
    return [round(v) for v in out]


def make(seed, today):
    rnd = random.Random(seed)
    start = monday(today) - dt.timedelta(weeks=4 * 52)
    runs, rid = [], 1000000
    fitness = lambda d: min(1.0, (d - start).days / (3.2 * 365))      # 0 → 1 over the first three years

    def add(day, name, area, surface, km, pace, gain, hr, race=False, kind=None):
        nonlocal rid
        rid += 1
        minutes = km * pace / 60
        grade = gain / max(km, 0.1)
        gap = pace - grade * 1.6 if surface == "trail" else pace
        cad = round(rnd.gauss(171 if race else 166, 3) - (8 if surface == "trail" else 0))
        zs = zone_split(hr, minutes * 60, rnd)
        runs.append({
            "id": str(rid), "date": day.isoformat(), "year": str(day.year), "month": day.strftime("%Y-%m"),
            "name": name, "garmin_name": name if race else ("City Trail Running" if surface == "trail" else "City Running"),
            "type": kind or ("trail_running" if surface == "trail" else "treadmill_running" if surface == "treadmill" else "running"),
            "surface": surface, "race": "yes" if race else "no", "km": round(km, 2), "minutes": round(minutes, 1),
            "pace_s_per_km": round(pace), "gap_s_per_km": round(gap), "moving_min": round(minutes, 1), "gain_m": round(gain),
            "gain_per_km": round(gain / km, 1), "avg_hr": hr, "avg_cadence": cad,
            "z1_s": zs[0], "z2_s": zs[1], "z3_s": zs[2], "z4_s": zs[3], "z5_s": zs[4],
            "area": area, "place": "Demo City", "course_id": ""})

    d = start
    while d <= today:
        wk = (d - start).days // 7
        f = fitness(d)
        season = 0.85 if d.month in (12, 1) else 1.0
        target = (28 + 17 * f) * season * (0.75 if wk % 4 == 3 else 1.0) * rnd.uniform(0.9, 1.1)
        days = sorted(rnd.sample(range(6), 3)) + [6]                   # three weekday runs and a Sunday long run
        long_km = min(22, target * 0.38)
        rest = (target - long_km) / 3
        for i, wd in enumerate(days):
            day = d + dt.timedelta(days=wd)
            if day > today:
                break
            if wd == 6:
                area = rnd.choice(["Riverside Park", "City Forest", "Hill Loop"])
                km = long_km * rnd.uniform(0.9, 1.1)
            else:
                area = rnd.choice(["Riverside Park", "Riverside Park", "Stadium Track", "Old Town Streets", "City Forest"])
                km = rest * rnd.uniform(0.8, 1.2)
            name, surface, _, gpk, off = next(a for a in AREAS if a[0] == area)
            quality = wd != 6 and i == 1 and rnd.random() < 0.6
            easy = 350 - 25 * f + off + rnd.gauss(0, 8)
            pace = easy - (55 if quality else 0)
            hr = round(rnd.gauss(152 if quality else 139 - 3 * f, 3))
            add(day, area, area, surface, km, pace, km * gpk * rnd.uniform(0.8, 1.2), hr)
        d += dt.timedelta(weeks=1)

    for y in range(start.year, today.year + 1):
        for name, m, day_, km, gain, surface in RACES:
            day = dt.date(y, m, day_)
            if start <= day <= today:
                f = fitness(day)
                pace = (290 - 22 * f if km < 15 else 300 - 22 * f) + (gain / km) * 5.5 + rnd.gauss(0, 5)
                add(day, name, "Away" if surface == "trail" else "Riverside Park", surface, km, pace, gain,
                    round(rnd.gauss(166, 2)), race=True)
    # one hike, three weeks ago
    hike = today - dt.timedelta(days=19)
    add(hike, "Mountain hike", "Away", "trail", 14.2, 1250, 980, 112)
    runs.sort(key=lambda r: r["date"])

    # race courses: every edition of a race, plus Riverside Park training runs on the 10K route
    courses, course_runs = [], []
    for i, (name, *_rest) in enumerate(RACES, 1):
        cid = f"C{i}"
        rs = [r for r in runs if r["name"] == name]
        if not rs:
            continue
        extra = [r for r in runs if name == "Autumn 10K" and r["area"] == "Riverside Park" and r["race"] == "no"
                 and 9.5 <= r["km"] <= 10.5][-6:]
        best = min(r["minutes"] for r in rs)
        for r in sorted(rs + extra, key=lambda r: r["date"]):
            r["course_id"] = cid
            course_runs.append({"course_id": cid, "course": name, "date": r["date"], "name": r["name"], "race": r["race"],
                                "km": r["km"], "minutes": r["minutes"], "pace_s_per_km": r["pace_s_per_km"],
                                "gain_m": r["gain_m"], "avg_hr": r["avg_hr"],
                                "behind_best_min": round(r["minutes"] * rs[0]["km"] / r["km"] - best, 1), "coverage_pct": 100})
        courses.append({"course_id": cid, "course": name, "km": rs[0]["km"], "gain_m": rs[0]["gain_m"],
                        "attempts": len(rs) + len(extra), "races": len(rs), "first": rs[0]["date"], "last": rs[-1]["date"]})

    weight, vo2 = [], []
    d = start
    while d <= today:
        f = fitness(d)
        if rnd.random() < 0.3:
            weight.append({"date": d.isoformat(), "weight_kg": round(77.5 - 3.5 * f + 0.8 * math.sin(d.timetuple().tm_yday / 58) + rnd.gauss(0, 0.3), 1)})
        if rnd.random() < 0.8:
            vo2.append({"date": d.isoformat(), "vo2max": round(49 + 4 * f + rnd.gauss(0, 0.4) - (0.8 if d > today - dt.timedelta(days=200) else 0), 1)})
        d += dt.timedelta(days=1)
    changes = [{"date": (today - dt.timedelta(days=200)).isoformat(), "setting": "max_hr_default", "from": 192, "to": 188,
                "date_basis": "sync", "note": "Demo: max HR setting lowered"}]

    plan_start = monday(today) - dt.timedelta(weeks=3)
    half = plan_start + dt.timedelta(weeks=21, days=6)
    trail = plan_start + dt.timedelta(weeks=25, days=5)
    plan = {"start": plan_start.isoformat(),
            "phases": [{"weeks": [1, 8], "km": [40, 46], "focus": "Base: easy volume, one hill session, long run 16 → 20 km"},
                       {"weeks": [9, 16], "km": [46, 54], "focus": "Threshold build; trail long run every second weekend"},
                       {"weeks": [17, 21], "km": [52, 52], "hours": [5, 6], "focus": "Half-specific long runs; hills midweek"},
                       {"weeks": [22, 22], "km": [32, 32], "focus": "Taper; Spring Half on Sunday"},
                       {"weeks": [23, 24], "hours": [6, 7], "gain_m": [1200, 1600], "focus": "Trail block: long climbs and descents"},
                       {"weeks": [25, 26], "hours": [4, 3], "focus": "Taper and trail race"}],
            "lighter_weeks": [{"week": 4, "km": 34, "note": "recovery"}, {"week": 8, "km": 35, "note": "recovery"},
                              {"week": 12, "km": 38, "note": "recovery"}, {"week": 17, "km": 40, "note": "recovery"}],
            "races": [{"name": "Spring Half", "date": half.isoformat()}, {"name": "Trail 25K", "date": trail.isoformat()}]}
    plan_md = f"""# Demo plan: Spring Half + Forest Trail 25K

This is a made-up plan for the demo runner. Your own plan goes in `config/plan.md`; the coach can write it for you.

## Goals

| Race | Date | Target |
|---|---|---|
| Spring Half Marathon | {half.strftime('%d %b %Y')} | 1:38 |
| Forest Trail 25K | {trail.strftime('%d %b %Y')} | 2:50 |

## Phases

| Weeks | Focus | Volume |
|---|---|---|
| 1–8 | Base: easy volume, one hill session | 40–46 km |
| 9–16 | Threshold build; trail long run every second weekend | 46–54 km |
| 17–21 | Half-specific long runs | 52 km or 5–6 h |
| 22 | Taper, half marathon on Sunday | 32 km |
| 23–24 | Trail block | 6–7 h, 1,200–1,600 m climbing |
| 25–26 | Taper and trail race | 4 → 3 h |

## Weekly skeleton

- **Quality:** threshold 3 × 3 km at half-marathon pace minus 10 s, or hill repeats.
- **Easy runs:** two, in zone 2.
- **Long run:** Sunday.
- **Strength:** twice a week, 20 minutes.

## Rules

- Increase weekly volume by no more than about 10%.
- Lighter weeks: 4, 8, 12 and 17.
- A body note twice in four weeks means an easy week.
"""
    journal = [{"date": (today - dt.timedelta(days=11)).isoformat(), "body_part": "calf", "severity": 2, "note": "Left calf tight after the track session"},
               {"date": (today - dt.timedelta(days=3)).isoformat(), "body_part": "calf", "severity": 3, "note": "Calf tight again on the long run"}]
    areas = [a[0] for a in AREAS]
    return {"runs_all": runs, "courses": courses, "course_runs": course_runs, "weight_all": weight, "vo2max": vo2,
            "settings_changes": changes, "weeks": [], "runs": [], "flags": [], "journal": journal,
            "meta": {"athlete": "Demo runner", "built": dt.datetime.now().astimezone().isoformat(timespec="minutes"),
                     "last_sync": dt.datetime.now().astimezone().isoformat(timespec="minutes"), "has_plan": True,
                     "plan": plan, "zones": ZONES, "plan_md": plan_md, "areas": areas, "demo": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(HERE)), "demo", "claudromos-demo.html"))
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    data = make(a.seed, dt.date.today())
    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*__CLAUDROMOS_DATA__*/null", blob, 1)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Demo dashboard: {a.out} ({len(data['runs_all'])} runs, all made up)")


if __name__ == "__main__":
    main()
