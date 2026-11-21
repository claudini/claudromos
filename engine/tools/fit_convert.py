#!/usr/bin/env python3
"""Convert a Garmin FIT activity to GPX (Garmin TrackPointExtension: hr, cad per leg) and/or a records CSV.

Usage: python3 -I fit_convert.py <in.fit> [--gpx out.gpx] [--csv out.csv]
Needs: pip install fitdecode
GPX output matches what the running-coach skill's GPX loader expects.
CSV columns: time_utc, lat, lon, ele_m, dist_m, speed_ms, hr, cad_spm, power_w, temp_c
"""
import argparse
import csv
import datetime as dt
import sys
from xml.sax.saxutils import escape

import fitdecode

SEMI = 180.0 / 2 ** 31


def val(frame, *names):
    for n in names:
        if frame.has_field(n):
            v = frame.get_value(n)
            if v is not None:
                return v
    return None


def load(path):
    recs, sport, name = [], None, None
    with fitdecode.FitReader(path) as fr:
        for f in fr:
            if not isinstance(f, fitdecode.FitDataMessage):
                continue
            if f.name == "sport":
                sport = val(f, "sport")
                name = val(f, "name")
            elif f.name == "record":
                t = val(f, "timestamp")
                if t is None:
                    continue
                lat, lon = val(f, "position_lat"), val(f, "position_long")
                cad = val(f, "cadence")
                frac = val(f, "fractional_cadence") or 0
                recs.append({
                    "time": t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc),
                    "lat": lat * SEMI if lat is not None else None,
                    "lon": lon * SEMI if lon is not None else None,
                    "ele": val(f, "enhanced_altitude", "altitude"),
                    "dist": val(f, "distance"),
                    "speed": val(f, "enhanced_speed", "speed"),
                    "hr": val(f, "heart_rate"),
                    "cad_leg": (cad + frac) if cad is not None else None,   # FIT running cadence is per leg
                    "power": val(f, "power"),
                    "temp": val(f, "temperature"),
                })
    return recs, sport, name


def write_gpx(recs, out, name):
    pts = [r for r in recs if r["lat"] is not None and r["lon"] is not None]
    with open(out, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<gpx version="1.1" creator="fit_convert" xmlns="http://www.topografix.com/GPX/1/1" '
                'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">\n'
                f'<metadata><name>{escape(name or "")}</name>'
                f'<time>{pts[0]["time"].strftime("%Y-%m-%dT%H:%M:%SZ") if pts else ""}</time></metadata>\n'
                f'<trk><name>{escape(name or "")}</name><trkseg>\n')
        for r in pts:
            ext = ""
            if r["hr"] is not None or r["cad_leg"] is not None:
                ext = "<extensions><gpxtpx:TrackPointExtension>"
                if r["hr"] is not None:
                    ext += f"<gpxtpx:hr>{int(r['hr'])}</gpxtpx:hr>"
                if r["cad_leg"] is not None:
                    ext += f"<gpxtpx:cad>{int(round(r['cad_leg']))}</gpxtpx:cad>"
                ext += "</gpxtpx:TrackPointExtension></extensions>"
            ele = f"<ele>{r['ele']:.1f}</ele>" if r["ele"] is not None else "<ele>0</ele>"
            f.write(f'<trkpt lat="{r["lat"]:.7f}" lon="{r["lon"]:.7f}">{ele}'
                    f'<time>{r["time"].strftime("%Y-%m-%dT%H:%M:%SZ")}</time>{ext}</trkpt>\n')
        f.write("</trkseg></trk></gpx>\n")
    return len(pts)


def write_csv(recs, out):
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "lat", "lon", "ele_m", "dist_m", "speed_ms", "hr", "cad_spm", "power_w", "temp_c"])
        for r in recs:
            w.writerow([r["time"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                        f"{r['lat']:.7f}" if r["lat"] is not None else "",
                        f"{r['lon']:.7f}" if r["lon"] is not None else "",
                        "" if r["ele"] is None else round(r["ele"], 1),
                        "" if r["dist"] is None else round(r["dist"], 1),
                        "" if r["speed"] is None else round(r["speed"], 3),
                        "" if r["hr"] is None else r["hr"],
                        "" if r["cad_leg"] is None else round(r["cad_leg"] * 2),
                        "" if r["power"] is None else r["power"],
                        "" if r["temp"] is None else r["temp"]])
    return len(recs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("fit")
    ap.add_argument("--gpx")
    ap.add_argument("--csv")
    a = ap.parse_args()
    recs, sport, name = load(a.fit)
    if not recs:
        sys.exit("No records in file")
    print(f"{len(recs)} records, sport={sport}, {recs[0]['time']} to {recs[-1]['time']}")
    if a.gpx:
        print(f"GPX: {write_gpx(recs, a.gpx, name)} points -> {a.gpx}")
    if a.csv:
        print(f"CSV: {write_csv(recs, a.csv)} rows -> {a.csv}")
