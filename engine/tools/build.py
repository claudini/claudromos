#!/usr/bin/env python3
"""Rebuild everything the dashboards read, from the synced files.

Usage: python3 -X utf8 -I build.py --root <data folder>

1. history.py  -> <root>/.claudromos/out/: runs_all, courses, course_runs, weight_all, vo2max,
                  race_candidates, settings_changes (CSV)
2. review.py   -> <root>/.claudromos/out/: weeks, runs, weight, flags (CSV; plan targets if config/plan.json)
3. dashboard   -> <root>/dashboards/claudromos.html: the template with all CSVs embedded, so the page
                  opens offline by double-click (browsers block a local page from reading files beside it)

The sync runs this after any sync that brings new data. Needs fitdecode (pip install fitdecode).
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)          # -I leaves the script's folder off sys.path

import history  # noqa: E402
import review   # noqa: E402

DATASETS = ["runs_all", "courses", "course_runs", "weight_all", "vo2max", "settings_changes",
            "weeks", "runs", "flags"]
NUM = re.compile(r"^-?\d+(\.\d+)?$")


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if isinstance(v, str) and NUM.match(v) and not (len(v) > 1 and v.startswith("0") and "." not in v):
                r[k] = float(v) if "." in v else int(v)
    return rows


def read_text(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def athlete_name(root):
    p = os.path.join(root, "athlete.md")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for line in f:
                m = re.match(r"#\s*Athlete:\s*(.+)", line)
                if m and "<" not in m.group(1):
                    return m.group(1).strip()
    return ""


def build_dashboard(root, out):
    tpl = os.path.join(os.path.dirname(HERE), "dashboards", "claudromos.template.html")
    with open(tpl, encoding="utf-8") as f:
        page = f.read()
    status = {}
    sp = os.path.join(root, "status.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8-sig") as f:
            status = json.load(f)
    data = {name: read_csv(os.path.join(out, name + ".csv")) for name in DATASETS}
    data["journal"] = read_csv(os.path.join(root, "journal.csv"))
    data["meta"] = {"athlete": athlete_name(root), "built": dt.datetime.now().astimezone().isoformat(timespec="minutes"),
                    "last_sync": status.get("last_success") or status.get("last_run"),
                    "has_plan": os.path.exists(os.path.join(root, "config", "plan.json")),
                    "plan": history.jload(os.path.join(root, "config", "plan.json")),
                    "zones": history.zone_floors(root),
                    "plan_md": read_text(os.path.join(root, "config", "plan.md")),
                    "areas": [a["name"] for a in (history.jload(os.path.join(root, "config", "areas.json"), {}) or {}).get("areas", [])]}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*__CLAUDROMOS_DATA__*/null", blob, 1)
    dest = os.path.join(root, "dashboards", "claudromos.html")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest + ".tmp", "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(dest + ".tmp", dest)
    return dest, sum(len(v) for k, v in data.items() if k != "meta")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", help="CSV folder (default <root>/.claudromos/out)")
    ap.add_argument("--no-html", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(a.root))
    out = a.out or os.path.join(root, ".claudromos", "out")
    history.main(root, out)
    review.export(root, out)
    if not a.no_html:
        dest, n = build_dashboard(root, out)
        print(f"Dashboard: {dest} ({n} rows)")


if __name__ == "__main__":
    main()
