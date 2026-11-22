#!/usr/bin/env python3
"""Training-log analysis over the ~/Garmin sync folder (activities/index.json, weight/weight.csv, status.json).

Usage:
  python3 -I garmin_review.py weekly --root <Garmin dir> [--week-ending YYYY-MM-DD] [--json out.json]
  python3 -I garmin_review.py runs   --root <Garmin dir> --from YYYY-MM-DD [--to YYYY-MM-DD]
  python3 -I garmin_review.py export --root <Garmin dir> --out <dir>   (weeks/runs/weight/flags CSVs for the dashboard)

Weeks run Monday to Sunday. Volume comes from Garmin's activity summaries (timer time, distance, gain).
Plan targets mirror "Training plan 2027" in the Running project (week 1 starts Mon 16 Nov 2026);
the project doc is the source of truth if they differ.
"""
import argparse
import csv
import datetime as dt
import json
import os
import statistics

RUN_TYPES = {"running", "trail_running", "treadmill_running", "track_running", "street_running",
             "ultra_run", "virtual_run", "indoor_running"}
PLAN = None   # loaded from <root>/config/plan.json by load(); None = no plan, weeks are reported without targets


def load_plan(root):
    """config/plan.json: {"start": "YYYY-MM-DD", "lighter_week_every": 4, "lighter_weeks_until": 22,
    "phases": [{"weeks": [1, 7], "km": [35, 45], "hours": [6, 8], "focus": "..."}]}"""
    p = os.path.join(root, "config", "plan.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8-sig") as f:
        plan = json.load(f)
    plan["_start"] = dt.date.fromisoformat(plan["start"])
    return plan


def load(root):
    global PLAN
    PLAN = load_plan(root)
    with open(os.path.join(root, "activities", "index.json"), encoding="utf-8-sig") as f:
        idx = json.load(f)
    acts = []
    for aid, a in idx.items():
        a = dict(a, id=aid)
        a["day"] = dt.date.fromisoformat(a["date"])
        a["km"] = (a.get("distance_m") or 0) / 1000
        a["h"] = (a.get("duration_s") or 0) / 3600
        a["gain"] = a.get("elevation_gain_m") or 0
        a["is_run"] = a.get("type") in RUN_TYPES
        acts.append(a)
    acts.sort(key=lambda a: a.get("start_local") or a["date"])
    # display names from the history tool (default names replaced by the area), when it has run
    names_p = os.path.join(root, ".claudromos", "out", "runs_all.csv")
    if os.path.exists(names_p):
        with open(names_p, encoding="utf-8", newline="") as f:
            names = {r["id"]: r["name"] for r in csv.DictReader(f) if r.get("name")}
        for a in acts:
            a["name"] = names.get(a["id"], a.get("name"))
    weight = []
    wp = os.path.join(root, "weight", "weight.csv")
    if os.path.exists(wp):
        for r in csv.DictReader(open(wp, encoding="utf-8")):
            if r.get("weight_kg"):
                weight.append((dt.date.fromisoformat(r["date"]), float(r["weight_kg"])))
    status = {}
    sp = os.path.join(root, "status.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8-sig") as f:
            status = json.load(f)
    return acts, weight, status


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def week_stats(acts, start):
    end = start + dt.timedelta(days=6)
    runs = [a for a in acts if a["is_run"] and start <= a["day"] <= end]
    other = [a for a in acts if not a["is_run"] and start <= a["day"] <= end]
    km = sum(a["km"] for a in runs)
    return {
        "week_start": start.isoformat(), "runs": len(runs), "km": round(km, 1),
        "hours": round(sum(a["h"] for a in runs), 2), "gain_m": round(sum(a["gain"] for a in runs)),
        "long_run_km": round(max((a["km"] for a in runs), default=0), 1),
        "trail_runs": sum(1 for a in runs if a["type"] == "trail_running"),
        "races": [a["name"] for a in runs if a.get("event_type") == "race"],
        "other_activities": len(other),
        "_runs": runs,
    }


def plan_for(week_start):
    if not PLAN:
        return {"week": None, "focus": "No plan set (config/plan.json)"}
    w = (week_start - PLAN["_start"]).days // 7 + 1
    if w < 1:
        return {"week": w, "focus": f"Before plan start ({PLAN['start']})"}
    every, until = PLAN.get("lighter_week_every"), PLAN.get("lighter_weeks_until", 10 ** 6)
    for ph in PLAN.get("phases", []):
        a, b = ph["weeks"]
        if a <= w <= b:
            k0, k1 = ph.get("km") or (None, None)
            km = None
            if k0 is not None:
                km = k0 if a == b else k0 + (k1 - k0) * (w - a) / (b - a)
            lw = {x["week"]: x for x in PLAN.get("lighter_weeks", [])}
            if w in lw:
                km = lw[w].get("km", km)
            return {"week": w, "phase": f"weeks {a}–{b}", "focus": ph.get("focus", "") + (f" (lighter week: {lw[w]['note']})" if w in lw and lw[w].get("note") else ""),
                    "target_km": round(km, 1) if km is not None else None,
                    "target_km_range": [k0, k1] if k0 is not None else None,
                    "target_hours": ph.get("hours"),
                    "lighter_week_expected": (w in lw) if PLAN.get("lighter_weeks") else (bool(every) and w % every == 0 and w <= until)}
    return {"week": w, "focus": "After the plan"}


def pace(sec_per_km):
    if not sec_per_km:
        return "—"
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}/km"


def fmt_h(h):
    m = int(round(h * 60))
    return f"{m // 60}:{m % 60:02d}"


def weekly(root, week_ending, out_json, quiet=False):
    acts, weight, status = load(root)
    if week_ending is None:
        today = dt.date.today()
        week_ending = monday(today) - dt.timedelta(days=1)       # last completed Sunday
    this_start = monday(week_ending)
    weeks = [week_stats(acts, this_start - dt.timedelta(weeks=i)) for i in range(11, -1, -1)]
    cur, prev = weeks[-1], weeks[-2]
    prior4 = weeks[-5:-1]
    base = statistics.mean(w["km"] for w in prior4) if prior4 else 0
    acwr = round(cur["km"] / base, 2) if base else None
    plan = plan_for(this_start)

    flags = []
    if not status.get("ok", True):
        flags.append(f"Sync failing: {status.get('error_code')}: {status.get('error')}")
    ls = status.get("last_success")
    if ls:
        age_h = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ls)).total_seconds() / 3600
        if age_h > 24:
            flags.append(f"Last successful sync was {age_h:.0f} h ago; data may be incomplete")
    if prev["km"] and cur["km"] > prev["km"] * 1.10:
        flags.append(f"Volume up {100 * (cur['km'] / prev['km'] - 1):.0f}% on last week (plan rule: about 10% max)")
    if acwr and acwr > 1.3:
        flags.append(f"Acute:chronic ratio {acwr} (this week vs 4-week average {base:.1f} km), above 1.3")
    if plan.get("target_km") and cur["km"] < plan["target_km"] * 0.75 and not plan.get("lighter_week_expected"):
        flags.append(f"{cur['km']} km is well under the plan's ~{plan['target_km']} km")
    if plan.get("lighter_week_expected") and prior4 and cur["km"] > max(w["km"] for w in prior4):
        flags.append("Plan expects a lighter week (every 4th week, about −25%), but this was the biggest of the last 5")
    if cur["runs"] == 0:
        flags.append("No runs recorded this week")

    wt = None
    if weight:
        last = weight[-1]
        ago = [w for w in weight if w[0] <= last[0] - dt.timedelta(days=28)]
        wt = {"latest_kg": last[1], "date": last[0].isoformat(),
              "change_4w_kg": round(last[1] - ago[-1][1], 1) if ago else None,
              "entries": len(weight)}

    runs = []
    for a in cur["_runs"]:
        runs.append({"date": a["date"], "name": a["name"], "type": a["type"], "event": a.get("event_type"),
                     "km": round(a["km"], 2), "time": fmt_h(a["h"]),
                     "pace": pace(a["h"] * 3600 / a["km"]) if a["km"] else "—",
                     "gain_m": round(a["gain"]), "avg_hr": a.get("avg_hr"), "fit": a.get("fit")})

    result = {
        "week_start": cur["week_start"], "week_end": week_ending.isoformat(), "plan": plan,
        "this_week": {k: v for k, v in cur.items() if k != "_runs"}, "runs": runs,
        "previous_week_km": prev["km"], "four_week_avg_km": round(base, 1), "acwr": acwr,
        "history": [{k: v for k, v in w.items() if k != "_runs"} for w in weeks],
        "weight": wt, "flags": flags, "sync": status,
    }
    if out_json:
        json.dump(result, open(out_json, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    if quiet:
        return result
    # ---- markdown
    p = plan
    tgt = (f"~{p['target_km']} km" if p.get("target_km") else
           f"{p['target_hours'][0]}–{p['target_hours'][1]} h" if p.get("target_hours") else "—")
    print(f"## Week {cur['week_start']} → {week_ending} ({'plan week ' + str(p['week']) + ': ' if p.get('week') else ''}{p.get('focus')})\n")
    print(f"- Runs {cur['runs']}, **{cur['km']} km**, {fmt_h(cur['hours'])} h, +{cur['gain_m']} m, "
          f"long run {cur['long_run_km']} km. Plan target {tgt}"
          + (" (lighter week expected)" if p.get("lighter_week_expected") else ""))
    print(f"- Previous week {prev['km']} km; 4-week average {base:.1f} km; acute:chronic {acwr}")
    if wt:
        ch = f", {wt['change_4w_kg']:+.1f} kg over 4 weeks" if wt["change_4w_kg"] is not None else ""
        print(f"- Weight {wt['latest_kg']} kg on {wt['date']}{ch}")
    print("\n**Flags:** " + ("; ".join(flags) if flags else "none"))
    print("\n| Date | Run | km | Time | Pace | Gain | Avg HR |\n|---|---|---|---|---|---|---|")
    for r in runs:
        tag = " (race)" if r["event"] == "race" else ""
        print(f"| {r['date']} | {r['name']}{tag} | {r['km']} | {r['time']} | {r['pace']} | {r['gain_m']} m | {r['avg_hr'] or '—'} |")
    print("\n| Week of | Runs | km | Time | Gain | Long |\n|---|---|---|---|---|---|")
    for w in weeks:
        print(f"| {w['week_start']} | {w['runs']} | {w['km']} | {fmt_h(w['hours'])} | {w['gain_m']} m | {w['long_run_km']} |")
    return result


def export(root, out_dir, weeks_back=26, runs_days=56):
    """Write weeks.csv, runs.csv, weight.csv, flags.csv for the dashboard."""
    os.makedirs(out_dir, exist_ok=True)
    acts, weight, status = load(root)
    today = dt.date.today()
    last_done = monday(today) - dt.timedelta(days=1)
    cur_start = monday(today)
    with open(os.path.join(out_dir, "weeks.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["week_start", "complete", "runs", "km", "hours", "gain_m", "long_run_km",
                    "plan_week", "target_km", "target_hours", "lighter_week", "focus"])
        for i in range(weeks_back - 1, -1, -1):
            ws = cur_start - dt.timedelta(weeks=i)
            st = week_stats(acts, ws)
            p = plan_for(ws)
            th = p.get("target_hours")
            w.writerow([ws.isoformat(), "yes" if ws <= monday(last_done) else "no", st["runs"], st["km"],
                        st["hours"], st["gain_m"], st["long_run_km"], p["week"] if (p["week"] or 0) >= 1 else "",
                        p.get("target_km") if p.get("target_km") is not None else "",
                        f"{th[0]}-{th[1]}" if th else "", "yes" if p.get("lighter_week_expected") else "no",
                        p.get("focus", "")])
    with open(os.path.join(out_dir, "runs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "name", "type", "race", "km", "minutes", "pace_s_per_km", "pace", "gain_m", "avg_hr"])
        for a in reversed(acts):
            if a["is_run"] and a["day"] >= today - dt.timedelta(days=runs_days):
                spk = a["h"] * 3600 / a["km"] if a["km"] else None
                w.writerow([a["date"], (a["name"] or "").strip(), a["type"], "yes" if a.get("event_type") == "race" else "no",
                            round(a["km"], 2), round(a["h"] * 60, 1), round(spk) if spk else "", pace(spk),
                            round(a["gain"]), a.get("avg_hr") or ""])
    with open(os.path.join(out_dir, "weight.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "weight_kg"])
        for d, kg in weight:
            w.writerow([d.isoformat(), kg])
    res = weekly(root, last_done, None, quiet=True)
    with open(os.path.join(out_dir, "flags.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["week_start", "flag"])
        for fl in res["flags"]:
            w.writerow([res["week_start"], fl])
    print(f"Exported to {out_dir}: weeks to {cur_start}, last complete week {monday(last_done)}, "
          f"{len(res['flags'])} flags, sync ok={status.get('ok')}")


def runs_list(root, frm, to):
    acts, _, _ = load(root)
    to = to or dt.date.today()
    print("| Date | Run | Type | km | Time | Pace | Gain | Avg HR | FIT |\n|---|---|---|---|---|---|---|---|---|")
    for a in acts:
        if frm <= a["day"] <= to:
            print(f"| {a['date']} | {a['name']} | {a['type']}{' (race)' if a.get('event_type') == 'race' else ''} | "
                  f"{a['km']:.2f} | {fmt_h(a['h'])} | {pace(a['h'] * 3600 / a['km']) if a['km'] else '—'} | "
                  f"{a['gain']:.0f} m | {a.get('avg_hr') or '—'} | {a.get('fit')} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["weekly", "runs", "export"])
    ap.add_argument("--out")
    ap.add_argument("--root", required=True)
    ap.add_argument("--week-ending")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "weekly":
        weekly(a.root, dt.date.fromisoformat(a.week_ending) if a.week_ending else None, a.json)
    elif a.cmd == "export":
        export(a.root, a.out)
    else:
        runs_list(a.root, dt.date.fromisoformat(a.frm), dt.date.fromisoformat(a.to) if a.to else None)
