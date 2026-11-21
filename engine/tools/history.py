#!/usr/bin/env python3
"""All-history datasets from the Claudromos sync: every run with its area and course, race comparisons,
weight and VO2 max. GPS digests are cached in activities/gps_digest.json, so later runs only read new files.

Usage: python3 -I garmin_history.py --root <Garmin dir> --out <dir>
Needs: fitdecode (pip install fitdecode)

Outputs (CSV):
  runs_all.csv      id, date, year, month, name, type, surface, race, km, minutes, pace_s_per_km,
                    gap_s_per_km (grade-adjusted, Minetti energy cost, moving time), moving_min, gain_m,
                    gain_per_km, avg_hr, area, place, course_id
  courses.csv       course_id, course, km, gain_m, attempts, races, first, last
  course_runs.csv   course_id, course, date, name, race, km, minutes, pace_s_per_km, gain_m, avg_hr,
                    behind_best_min, coverage_pct
  weight_all.csv    date, weight_kg
  vo2max.csv        date, vo2max   (from health/vo2max once the sync has fetched it)
  race_candidates.csv  runs named like races but not tagged as races in Garmin Connect
  settings_changes.csv copy of <root>/settings_changes.csv (date, setting, from, to, date_basis, note)

Config (all optional, in <root>/config/):
  areas.json      named boxes where the runs go; detected from GPS and written on first run if missing
  overrides.json  {"exclude": [activity ids], "extra_races": [activity ids]}
  race_words.json list of regex words marking likely races in run names (default: common EN/RO words)
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import xml.etree.ElementTree as ET

DEFAULT_RACE_WORDS = [r"cros", r"crosul", r"semi", r"maraton", r"marathon", r"skyrace", r"sky race", r"ultra",
                      r"x3", r"race", r"cupa", r"\d+\s?k\b", r"forest run", r"challenge", r"trophy", r"trofeul",
                      r"stairs run", r"half", r"10k"]
AREAS = []                    # [(name, lat min, lat max, lon min, lon max)], from config/areas.json
HOME = None                   # (name, lat min, lat max, lon min, lon max): "near home" box for runs outside every area
AREA_MIN_SHARE = 0.35
RACE_WORDS = None


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def jsave(path, obj, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, **kw)
    os.replace(path + ".tmp", path)


def detect_areas(runs, max_areas=8):
    """Areas from where the runs actually go: runs are grouped by the ~1 km grid cell of their centre point,
    busy cells next to each other are joined, and each group's box covers the middle 80% of its runs' tracks.
    Names are placeholders ("Area 1 near 44.470, 26.080") for the athlete or the coach to rename."""
    gps_runs = [r for r in runs if r["_track"] and r["type"] != "treadmill_running"]
    cells = {}
    for r in gps_runs:
        la = sum(p[0] for p in r["_track"]) / len(r["_track"])
        lo = sum(p[1] for p in r["_track"]) / len(r["_track"])
        cells.setdefault((int(la * 100 // 1), int(lo * 100 // 1)), []).append(r)
    need = max(5, round(0.02 * len(gps_runs)))

    def mid80(vals):
        vals = sorted(vals)
        return vals[int(0.1 * (len(vals) - 1))], vals[int(0.9 * (len(vals) - 1))]

    def box(g):
        return mid80([p[0] for r in g for p in r["_track"]]) + mid80([p[1] for r in g for p in r["_track"]])

    def overlap(a, b):   # share of the smaller box covered by the other
        h = max(0.0, min(a[1], b[1]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[2], b[2]))
        small = min((a[1] - a[0]) * (a[3] - a[2]), (b[1] - b[0]) * (b[3] - b[2])) or 1e-12
        return h / small

    # each busy centre cell is a candidate; candidates whose route boxes mostly overlap are the same place
    groups = [rs for rs in cells.values() if len(rs) >= need]
    merged = True
    while merged:
        merged = False
        boxes = [box(g) for g in groups]
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if overlap(boxes[i], boxes[j]) >= 0.5:
                    groups[i] = groups[i] + groups[j]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    groups.sort(key=lambda g: -len(g))

    areas = []
    for i, g in enumerate(groups[:max_areas], 1):
        la0, la1 = mid80([p[0] for r in g for p in r["_track"]])
        lo0, lo1 = mid80([p[1] for r in g for p in r["_track"]])
        areas.append({"name": f"Area {i} near {(la0 + la1) / 2:.3f}, {(lo0 + lo1) / 2:.3f}",
                      "lat": [round(la0, 4), round(la1, 4)], "lon": [round(lo0, 4), round(lo1, 4)],
                      "runs": len(g), "detected": True})
    home = None
    if areas:
        pad = 0.08
        home = {"name": "Near home, other",
                "lat": [round(min(a["lat"][0] for a in areas) - pad, 3), round(max(a["lat"][1] for a in areas) + pad, 3)],
                "lon": [round(min(a["lon"][0] for a in areas) - pad, 3), round(max(a["lon"][1] for a in areas) + pad, 3)]}
    return {"areas": areas, "home": home, "min_share": AREA_MIN_SHARE,
            "note": "Detected automatically. Rename areas, adjust boxes or delete entries; set \"home\" to null to drop it."}


def load_areas(path, runs):
    global AREAS, HOME, AREA_MIN_SHARE
    cfg = jload(path)
    if cfg is None:
        cfg = detect_areas(runs)
        jsave(path, cfg, indent=2)
        print(f"Detected {len(cfg['areas'])} areas, written to {path}")
    AREAS = [(a["name"], a["lat"][0], a["lat"][1], a["lon"][0], a["lon"][1]) for a in cfg.get("areas", [])]
    h = cfg.get("home")
    if h is None and cfg.get("home_box"):          # early hand-written format
        b = cfg["home_box"]
        h = {"name": cfg.get("home_name", "Near home, other"), "lat": b[:2], "lon": b[2:]}
    HOME = (h["name"], h["lat"][0], h["lat"][1], h["lon"][0], h["lon"][1]) if h else None
    AREA_MIN_SHARE = cfg.get("min_share", AREA_MIN_SHARE)


SEMI = 180 / 2 ** 31


def hav(a, b):
    R = 6371000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def read_records(path):
    """(lat, lon, t_s, dist_m, alt_m) per record; any of the last three may be None."""
    out = []
    if path.endswith(".fit"):
        import fitdecode
        t0 = None
        with fitdecode.FitReader(path) as fr:
            for f in fr:
                if not (isinstance(f, fitdecode.FitDataMessage) and f.name == "record"):
                    continue
                g = lambda k: f.get_value(k) if f.has_field(k) else None
                ts = g("timestamp")
                if ts is None:
                    continue
                t0 = t0 or ts
                la, lo = g("position_lat"), g("position_long")
                alt = g("enhanced_altitude")
                alt = g("altitude") if alt is None else alt
                out.append((la * SEMI if la is not None else None, lo * SEMI if lo is not None else None,
                            (ts - t0).total_seconds(), g("distance"), alt))
    elif path.endswith(".gpx"):
        for p in ET.parse(path).getroot().iter():
            if p.tag.endswith("trkpt"):
                out.append((float(p.get("lat")), float(p.get("lon")), None, None, None))
    return out


def minetti(i):
    """Energy cost of running at grade i (J/kg/m), Minetti et al. 2002; 3.6 on the flat."""
    i = max(-0.45, min(0.45, i))
    return 155.4 * i ** 5 - 30.4 * i ** 4 - 43.3 * i ** 3 + 46.3 * i ** 2 + 19.5 * i + 3.6


def grade_adjusted(recs):
    """(GAP s/km, moving minutes) from records with distance, time and altitude; None if missing."""
    pts = [(t, d, a) for _, _, t, d, a in recs if t is not None and d is not None]
    if len(pts) < 20:
        return None, None
    alts = [a for _, _, a in pts]
    if sum(a is not None for a in alts) < len(alts) * 0.8:
        return None, None
    sm = []                                   # 5-point rolling median of altitude
    for k in range(len(pts)):
        win = sorted(a for a in alts[max(0, k - 2):k + 3] if a is not None)
        sm.append(win[len(win) // 2] if win else None)
    eq = moving = 0.0
    last = 0
    for k in range(1, len(pts)):
        dd = pts[k][1] - pts[last][1]
        if dd < 25 and k < len(pts) - 1:
            continue
        dt = pts[k][0] - pts[last][0]
        if dd > 0 and dt > 0 and sm[k] is not None and sm[last] is not None:
            moving += min(dt, dd / 0.8)       # stops count only as a very slow walk
            eq += dd * minetti((sm[k] - sm[last]) / dd) / 3.6
        last = k
    if eq < 500 or moving <= 0:
        return None, None
    return round(moving / (eq / 1000)), round(moving / 60, 1)


def simplify(pts, step=100):
    out, last = [], None
    for p in pts:
        if last is None or hav(last, p) >= step:
            out.append((round(p[0], 5), round(p[1], 5)))
            last = p
    return out


DIGEST_VERSION = 2


def digest(path):
    recs = read_records(path)
    pts = [(la, lo) for la, lo, *_ in recs if la is not None and lo is not None]
    gap, moving = grade_adjusted(recs)
    out = {"v": DIGEST_VERSION, "n": len(pts), "gap_s_per_km": gap, "moving_min": moving}
    if pts:
        out.update(start=[round(pts[0][0], 5), round(pts[0][1], 5)],
                   centroid=[round(sum(p[0] for p in pts) / len(pts), 5), round(sum(p[1] for p in pts) / len(pts), 5)],
                   track=simplify(pts))
    return out


def area_shares(track):
    """Share of the (100 m spaced) track inside each area."""
    out = {}
    for name, a, b, c, d in AREAS:
        k = sum(1 for la, lo in track if a <= la <= b and c <= lo <= d)
        if k:
            out[name] = k / len(track)
    return out


def coverage(a, b, tol=120):
    """Share of track a's points within tol metres of track b (coarse grid lookup)."""
    if not a or not b:
        return 0.0
    grid = {}
    for p in b:
        grid.setdefault((round(p[0] * 200), round(p[1] * 200)), []).append(p)   # ~400 m cells
    hit = 0
    for p in a:
        gx, gy = round(p[0] * 200), round(p[1] * 200)
        near = (q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((gx + dx, gy + dy), ()))
        if any(hav(p, q) <= tol for q in near):
            hit += 1
    return hit / len(a)


def clean_name(n):
    return re.sub(r"\s+", " ", (n or "").strip())


def main(root, out, areas_path=None):
    global RACE_WORDS
    os.makedirs(out, exist_ok=True)
    conf = os.path.join(root, "config")
    cfg = jload(os.path.join(conf, "overrides.json")) or jload(os.path.join(root, ".sync", "overrides.json")) or {}
    words = jload(os.path.join(conf, "race_words.json")) or DEFAULT_RACE_WORDS
    RACE_WORDS = re.compile(r"\b(" + "|".join(words) + ")", re.I)
    exclude = {str(x) for x in cfg.get("exclude", [])}
    extra_races = {str(x) for x in cfg.get("extra_races", [])}
    index = jload(os.path.join(root, "activities", "index.json"))
    cache_p = os.path.join(root, "activities", "gps_digest.json")
    cache = jload(cache_p, {})

    runs = []
    new = 0
    for aid, r in index.items():
        if aid in exclude or "run" not in (r.get("type") or ""):
            continue
        s = jload(os.path.join(root, r["summary"]), {})
        if r.get("fit") and cache.get(aid, {}).get("v") != DIGEST_VERSION:
            try:
                cache[aid] = digest(os.path.join(root, r["fit"]))
            except Exception as e:  # a corrupt file shouldn't stop the rest
                cache[aid] = {"n": 0, "error": repr(e)}
            new += 1
            if new % 100 == 0:
                jsave(cache_p, cache)
                print(f"digested {new}")
        g = cache.get(aid, {"n": 0})
        km = (r.get("distance_m") or 0) / 1000
        mins = (r.get("duration_s") or 0) / 60
        st = g.get("start") or ([s.get("startLatitude"), s.get("startLongitude")] if s.get("startLatitude") else None)
        area = ""
        tagged = r.get("event_type") == "race" or aid in extra_races
        runs.append({
            "id": aid, "date": r["date"], "year": r["date"][:4], "month": r["date"][:7],
            "name": clean_name(r.get("name")), "type": r.get("type"),
            "surface": {"trail_running": "trail", "treadmill_running": "treadmill"}.get(r.get("type"), "road"),
            "race": "yes" if tagged else ("likely" if RACE_WORDS.search(r.get("name") or "") else "no"),
            "km": round(km, 2), "minutes": round(mins, 1),
            "pace_s_per_km": round(mins * 60 / km) if km >= 0.5 else "",
            "gain_m": round(r.get("elevation_gain_m") or 0),
            "gain_per_km": round((r.get("elevation_gain_m") or 0) / km, 1) if km >= 0.5 else "",
            "avg_hr": round(r["avg_hr"]) if r.get("avg_hr") else "",
            "gap_s_per_km": g.get("gap_s_per_km") or "", "moving_min": g.get("moving_min") or "",
            "area": area, "place": s.get("locationName") or "", "course_id": "",
            "_start": st, "_track": g.get("track") or [],
        })
    jsave(cache_p, cache)
    runs.sort(key=lambda x: x["date"])
    load_areas(areas_path or os.path.join(conf, "areas.json"), runs)
    for x in runs:
        shares = area_shares(x["_track"])
        if shares:
            name, share = max(shares.items(), key=lambda kv: kv[1])
            if share >= AREA_MIN_SHARE:
                x["area"] = name
        if not x["area"]:
            st = x["_start"]
            if x["type"] == "treadmill_running" or not st:
                x["area"] = "Treadmill / no GPS"
            elif HOME and HOME[1] <= st[0] <= HOME[2] and HOME[3] <= st[1] <= HOME[4]:
                x["area"] = HOME[0]
            else:
                x["area"] = "Away"

    # --- courses: group races by start (within 3 km) and distance (within 12%); then add every run that
    # covers the same route (both tracks overlap at least 80%).
    races = [x for x in runs if x["race"] == "yes" and x["_start"] and x["_track"]]
    groups = []
    for x in races:
        for g in groups:
            ref = g[0]
            if hav(ref["_start"], x["_start"]) < 3000 and abs(x["km"] - ref["km"]) <= 0.12 * ref["km"] \
                    and coverage(x["_track"], ref["_track"]) >= 0.6:
                g.append(x)
                break
        else:
            groups.append([x])
    courses, course_runs = [], []
    for i, g in enumerate(sorted(groups, key=lambda g: g[-1]["date"], reverse=True), 1):
        ref = max(g, key=lambda x: len(x["_track"]))
        cid = f"C{i:02d}"
        members = []
        for x in runs:
            if not x["_track"] or not x["_start"] or hav(ref["_start"], x["_start"]) > 3000:
                continue
            if abs(x["km"] - ref["km"]) > 0.15 * ref["km"]:
                continue
            c1, c2 = coverage(x["_track"], ref["_track"]), coverage(ref["_track"], x["_track"])
            if min(c1, c2) >= 0.8 or x in g:
                members.append((x, round(100 * min(c1, c2))))
        if len(members) < 1:
            continue
        name = clean_name(g[-1]["name"])
        best = min(m[0]["minutes"] for m in members if m[0]["race"] == "yes")
        for x, cov in members:
            x["course_id"] = x["course_id"] or cid
            course_runs.append({"course_id": cid, "course": name, "date": x["date"], "name": x["name"],
                                "race": x["race"], "km": x["km"], "minutes": x["minutes"],
                                "pace_s_per_km": x["pace_s_per_km"], "gain_m": x["gain_m"], "avg_hr": x["avg_hr"],
                                "behind_best_min": round(x["minutes"] - best, 1), "coverage_pct": cov})
        courses.append({"course_id": cid, "course": name, "km": round(ref["km"], 1), "gain_m": ref["gain_m"],
                        "attempts": len(members), "races": sum(1 for m in members if m[0]["race"] == "yes"),
                        "first": min(m[0]["date"] for m in members), "last": max(m[0]["date"] for m in members)})

    def write(name, rows, cols):
        with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    run_cols = ["id", "date", "year", "month", "name", "type", "surface", "race", "km", "minutes", "pace_s_per_km",
                "gap_s_per_km", "moving_min", "gain_m", "gain_per_km", "avg_hr", "area", "place", "course_id"]
    write("runs_all.csv", runs, run_cols)
    write("courses.csv", courses, ["course_id", "course", "km", "gain_m", "attempts", "races", "first", "last"])
    write("course_runs.csv", sorted(course_runs, key=lambda r: (r["course_id"], r["date"])),
          ["course_id", "course", "date", "name", "race", "km", "minutes", "pace_s_per_km", "gain_m", "avg_hr",
           "behind_best_min", "coverage_pct"])
    write("race_candidates.csv", [x for x in runs if x["race"] == "likely"],
          ["id", "date", "name", "km", "minutes", "gain_m", "place"])

    wrows = []
    wp = os.path.join(root, "weight", "weight.csv")
    if os.path.exists(wp):
        wrows = [{"date": r["date"], "weight_kg": r["weight_kg"]} for r in csv.DictReader(open(wp, encoding="utf-8")) if r["weight_kg"]]
    write("weight_all.csv", wrows, ["date", "weight_kg"])

    vo2 = {}
    for p in sorted(glob.glob(os.path.join(root, "health", "vo2max", "*.json"))):
        for day, recs in jload(p, {}).items():
            for rec in recs:
                for k in ("generic", "running"):
                    v = (rec.get(k) or {}) if isinstance(rec.get(k), dict) else {}
                    val = v.get("vo2MaxPreciseValue") or v.get("vo2MaxValue")
                    if val:
                        vo2[day] = round(float(val), 1)
                val = rec.get("vo2MaxPreciseValue") or rec.get("vo2MaxValue")
                if val and day not in vo2:
                    vo2[day] = round(float(val), 1)
    for p in sorted(glob.glob(os.path.join(root, "health", "vo2max", "raw", "*.json"))):
        data = jload(p)
        for rec in data if isinstance(data, list) else []:
            for k in ("generic", "running"):
                v = rec.get(k) if isinstance(rec.get(k), dict) else {}
                day = v.get("calendarDate")
                val = v.get("vo2MaxPreciseValue") or v.get("vo2MaxValue")
                if day and val:
                    vo2[day[:10]] = round(float(val), 1)
    write("vo2max.csv", [{"date": d, "vo2max": v} for d, v in sorted(vo2.items())], ["date", "vo2max"])

    cp = os.path.join(root, "settings_changes.csv")      # watch settings that shift Garmin's estimates (max HR...)
    changes = list(csv.DictReader(open(cp, encoding="utf-8"))) if os.path.exists(cp) else []
    write("settings_changes.csv", changes, ["date", "setting", "from", "to", "date_basis", "note"])

    from collections import Counter
    print(f"{len(runs)} runs ({new} newly digested), areas {dict(Counter(x['area'] for x in runs))}")
    print(f"{len(courses)} race courses, {len(course_runs)} course runs, "
          f"{sum(1 for x in runs if x['race'] == 'likely')} race candidates, {len(wrows)} weigh-ins, {len(vo2)} VO2 max days")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--areas", help="areas file (default <root>/config/areas.json; created by detection if missing)")
    a = ap.parse_args()
    main(a.root, a.out, a.areas)
