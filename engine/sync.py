#!/usr/bin/env python3
"""Claudromos sync: Garmin Connect data into a local folder via the Garmin Personal API.

Runs on macOS and Windows with the standard library only.
Data folder: $CLAUDROMOS_DIR, default ~/Claudromos. Engine files live in <data>/.claudromos/.

Settings in .claudromos/config.json:
  scope   "runs": activities (summary + original FIT) and weight.
          "all":  also full activity records and workouts, daily health ranges (daily summaries, sleep,
                  HRV, VO2 max, steps, stress, hydration, Body Battery, wellness activities, weight goals)
                  and daily snapshots (profile settings, HR zones, fitness age, activity types).
  history "1m" | "1y" | "3y" | "all": how far back the first sync goes; extending it later fetches only
          the older part.
  tools_python  optional path to the Python that runs tools/build.py after a sync with new data.

The API key is never written in plain text or logged:
  macOS:   login Keychain, service "claudromos-garmin" (older installs: "garmin-personal-api").
  Windows: .claudromos/key.dpapi, encrypted for the current Windows user (PowerShell ConvertFrom-SecureString).

Layout written under the data folder:
  activities/index.json                     one record per activity (id -> summary + file paths)
  activities/YYYY/<date>_<id>_<name>.json   Garmin's activity summary (.details.json, .workouts.json with scope all)
  activities/YYYY/<date>_<id>_<name>.fit    original FIT file
  weight/weight.json, weight/weight.csv     raw entries; date, weight_kg, body_fat_pct, muscle_mass_kg
  health/<name>/<YYYY>.json                 {date: [records]} per endpoint (scope all); raw/ if undated
  health/snapshots/<name>.json              latest profile settings, HR zones, fitness age, activity types
  settings_changes.csv                      HR setting changes seen by the daily snapshot
  status.json                               result of the last run (ok / error_code / warnings)
  logs/sync.log                             one line per run

Usage: python3 sync.py [diagnose | rebuild]
"""
import csv
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile

BASE = "https://personal.connectapi.garmin.com"
TOKEN_URL = BASE + "/personalapitoken-service/personal-api/personal-api-key/token"
ROOT = os.path.expanduser(os.environ.get("CLAUDROMOS_DIR", "~/Claudromos"))
ENGINE = os.path.join(ROOT, ".claudromos")
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
KEYCHAIN_SERVICES = ("claudromos-garmin", "garmin-personal-api")   # new name first, then the pre-Claudromos one
OVERLAP_DAYS = 3          # re-check the last few days to catch late uploads
PAGE = 99                 # API maximum page size
UA = "claudromos/1.0"


class SyncError(Exception):
    def __init__(self, code, msg, status=None):
        super().__init__(msg)
        self.code = code
        self.status = status


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def log(msg):
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    line = f"{now_iso()} {msg}"
    print(line)
    with open(os.path.join(ROOT, "logs", "sync.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- auth / http

def _dpapi_unprotect(blob):
    """Decrypt a Windows DPAPI blob for the current user (what PowerShell's ConvertFrom-SecureString writes)."""
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(blob, len(blob))
    src_b, out = BLOB(len(blob), buf), BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src_b), None, None, None, None, 0, ctypes.byref(out)):
        raise SyncError("NO_KEY", "Could not decrypt the stored API key (stored by another Windows user?). "
                                  "Run the installer with update-key.")
    data = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return data


def get_key():
    env = os.environ.get("GARMIN_API_KEY")
    if env:
        return env.strip()
    if IS_WIN:
        path = os.path.join(ENGINE, "key.dpapi")
        try:
            hexblob = open(path, encoding="utf-8-sig").read().strip()
        except FileNotFoundError:
            raise SyncError("NO_KEY", "No API key stored. Run install.ps1 update-key")
        return _dpapi_unprotect(bytes.fromhex(hexblob)).decode("utf-16-le").strip()
    for svc in KEYCHAIN_SERVICES:
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", svc,
                            "-a", os.environ.get("USER", ""), "-w"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    raise SyncError("NO_KEY", "API key not found in the Keychain. Run: bash install.sh update-key")


CURL = "/usr/bin/curl"   # macOS curl supports TLS 1.3; Apple's Python/LibreSSL build does not


def _q(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _curl_once(method, url, headers, data, timeout):
    """One request via curl. Config goes through stdin so the key/token never appear in the process list."""
    with tempfile.TemporaryDirectory() as td:
        body_f, hdr_f = os.path.join(td, "body"), os.path.join(td, "headers")
        cfg = [f"url = {_q(url)}", f"request = {_q(method)}", f"output = {_q(body_f)}",
               f"dump-header = {_q(hdr_f)}", f"max-time = {int(timeout)}", "silent", "show-error",
               'write-out = "%{http_code}"']
        cfg += [f"header = {_q(f'{k}: {v}')}" for k, v in headers.items()]
        if data is not None:
            cfg.append('data-binary = ""')
        r = subprocess.run([CURL, "-K", "-"], input="\n".join(cfg) + "\n", capture_output=True, text=True)
        if r.returncode < 0 or r.returncode == 130:     # curl stopped by Ctrl+C: stop the whole sync
            raise KeyboardInterrupt
        if r.returncode != 0:
            return None, (r.stderr or f"curl exit {r.returncode}").strip()
        code = int((r.stdout.strip() or "0")[-3:])
        body = open(body_f, "rb").read() if os.path.exists(body_f) else b""
        hdrs = {}
        if os.path.exists(hdr_f):
            block = open(hdr_f, errors="replace").read().strip().split("\r\n\r\n")[-1]
            for line in block.splitlines()[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    hdrs[k.strip().lower()] = v.strip()
        return (code, body, hdrs), None


def _urllib_once(method, url, headers, data, timeout):
    """One request via urllib (python.org and Windows builds have a current OpenSSL)."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}), None
    except urllib.error.HTTPError as e:
        return (e.code, e.read() or b"", {k.lower(): v for k, v in (e.headers or {}).items()}), None
    except Exception as e:  # network, TLS, timeout
        return None, repr(e)


def _request_once(method, url, headers, data, timeout):
    # Apple's own Python is built on LibreSSL and fails Garmin's TLS; macOS curl works.
    if IS_MAC and os.path.exists(CURL):
        return _curl_once(method, url, headers, data, timeout)
    return _urllib_once(method, url, headers, data, timeout)


def http(method, url, headers=None, data=None, timeout=90, retries=3):
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    last = (0, b"", {})
    for attempt in range(retries):
        res, err = _request_once(method, url, h, data, timeout)
        if res is None:
            if attempt == retries - 1:
                raise SyncError("NETWORK", f"Network error: {err}")
            time.sleep(15 * (attempt + 1))
            continue
        code, body, hdrs = res
        last = res
        if code == 429 or code >= 500:
            wait = int(hdrs.get("retry-after") or 0) or 15 * (attempt + 1)
            log(f"HTTP {code} on {urllib.parse.urlparse(url).path}; retrying in {wait}s")
            time.sleep(wait)
            continue
        return code, body, hdrs
    return last


def get_token(key):
    status, body, _ = http("POST", TOKEN_URL, {"Authorization": f"ApiKey {key}"}, data=b"")
    if status in (401, 403):
        snippet = body[:300].decode("utf-8", "replace").replace(key, "<key>")
        kinds = sorted({"letters" if c.isalpha() else "digits" if c.isdigit() else repr(c) for c in key})
        log(f"Token refused: HTTP {status}; response: {snippet!r}; key length {len(key)}, "
            f"characters: {', '.join(kinds)}")
        raise SyncError("KEY_REJECTED",
                        f"Garmin refused the API key (HTTP {status}); it has probably expired or been deleted. "
                        "Create a new key in Garmin Connect, then run the installer with update-key")
    if status != 200:
        log(f"Token request: HTTP {status}; response: {body[:300].decode('utf-8', 'replace').replace(key, '<key>')!r}")
        raise SyncError("TOKEN_FAILED", f"Token request failed with HTTP {status}")
    text = body.decode("utf-8", "replace").strip()
    try:
        j = json.loads(text)
    except json.JSONDecodeError:
        j = None
    if isinstance(j, dict):
        for k in ("access_token", "accessToken", "token"):
            if isinstance(j.get(k), str):
                return j[k]
        raise SyncError("TOKEN_FORMAT", f"Unexpected token response, keys: {sorted(j)}")
    if isinstance(j, str):
        return j
    if text and " " not in text:
        return text
    raise SyncError("TOKEN_FORMAT", "Unexpected token response format")


def api(token, path, params=None, raw=False):
    url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    headers = {"Authorization": f"Bearer {token}"}
    status, body, _ = http("GET", url, headers)
    if status == 401:
        raise SyncError("TOKEN_REJECTED", f"HTTP 401 on {path}")
    if status in (204, 404):
        return None
    if status != 200:
        raise SyncError("API", f"HTTP {status} on {path}: {body[:200].decode('utf-8', 'replace')!r}", status)
    if raw:
        return body
    return json.loads(body) if body.strip() else None


# ---------------------------------------------------------------- config & coverage

SCOPES = ("runs", "all")
HISTORIES = {"1m": 30, "1y": 365, "3y": 3 * 365 + 1, "all": None}


def load_config():
    cfg = {"scope": "runs", "history": "1y"}
    cfg.update(load_json(os.path.join(ENGINE, "config.json"), {}))
    cfg["scope"] = os.environ.get("GARMIN_SCOPE", cfg["scope"])
    cfg["history"] = os.environ.get("GARMIN_HISTORY", cfg["history"])
    if cfg["scope"] not in SCOPES or cfg["history"] not in HISTORIES:
        raise SyncError("CONFIG", f"Bad config {cfg}; scope must be runs|all, history 1m|1y|3y|all")
    return cfg


def earliest_activity_date(token, state):
    if state.get("earliest_activity"):
        return dt.date.fromisoformat(state["earliest_activity"])
    page = api(token, "/activitylist-service/activities/search/activities",
               {"start": 0, "limit": 1, "sortOrder": "asc"}) or []
    d = dt.date.fromisoformat(page[0]["startTimeLocal"][:10]) if page else dt.date.today()
    state["earliest_activity"] = d.isoformat()
    return d


def history_start(cfg, token, state, today):
    days = HISTORIES[cfg["history"]]
    if days is None:
        return earliest_activity_date(token, state)
    return today - dt.timedelta(days=days)


def migrate_state(state):
    """Version 1 kept only *_synced_until and always backfilled 365 days."""
    cov = state.setdefault("coverage", {})
    for name in ("activities", "weight"):
        until = state.pop(f"{name}_synced_until", None)
        if until and name not in cov:
            cov[name] = [(dt.date.fromisoformat(until) - dt.timedelta(days=365)).isoformat(), until]


def ranges_to_fetch(state, name, start, today):
    """Older history not yet covered, plus a short overlap with the newest data."""
    cov = state.get("coverage", {}).get(name)
    if not cov:
        return [(start, today)]
    f, u = dt.date.fromisoformat(cov[0]), dt.date.fromisoformat(cov[1])
    out = []
    if start < f:
        out.append((start, f - dt.timedelta(days=1)))
    out.append((max(f, u - dt.timedelta(days=OVERLAP_DAYS)), today))
    return out


def mark_covered(state, name, start, today):
    cov = state.setdefault("coverage", {}).get(name)
    f = min(start, dt.date.fromisoformat(cov[0])) if cov else start
    state["coverage"][name] = [f.isoformat(), today.isoformat()]


# ---------------------------------------------------------------- activities

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "activity").lower()).strip("-")[:40] or "activity"


def extract_fit(blob, folder, base):
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            pick = [n for n in names if n.lower().endswith(".fit")] or names
            ext = os.path.splitext(pick[0])[1].lower() or ".bin"
            data = z.read(pick[0])
    else:
        data = blob
        ext = ".fit" if blob[8:12] == b".FIT" else ".bin"
    path = os.path.join(folder, base + ext)
    with open(path, "wb") as f:
        f.write(data)
    return os.path.relpath(path, ROOT)


MAX_FIT_ATTEMPTS = 5


def download_fit(token, aid, folder, base):
    """Original file for an activity, or None (failure is retried on later runs)."""
    try:
        blob = api(token, f"/download-service/files/activity/{aid}", raw=True)
        if not blob:
            log(f"Activity {aid}: Garmin has no file for it")
            return None
        return extract_fit(blob, folder, base)
    except SyncError as e:
        if e.code in ("TOKEN_REJECTED", "NETWORK"):
            raise
        log(f"Could not download the file for activity {aid}: {e}")
    except (zipfile.BadZipFile, OSError) as e:
        log(f"Could not unpack the file for activity {aid}: {e!r}")
    return None


def key_of(d, field):
    v = d.get(field)
    return v.get("typeKey") if isinstance(v, dict) else v


def sync_activities(token, state, start, scope):
    idx_path = os.path.join(ROOT, "activities", "index.json")
    index = load_json(idx_path, {})
    today = dt.date.today()

    found = []
    for a_from, a_to in ranges_to_fetch(state, "activities", start, today):
        offset = 0
        while True:
            page = api(token, "/activitylist-service/activities/search/activities",
                       {"startDate": a_from.isoformat(), "endDate": a_to.isoformat(),
                        "start": offset, "limit": PAGE, "sortOrder": "asc"}) or []
            found += page
            if len(page) < PAGE:
                break
            offset += PAGE
    if found:
        log(f"Activities: {len(found)} listed, downloading new ones")

    new = 0
    for a in found:
        aid = str(a.get("activityId"))
        if index.get(aid, {}).get("fit"):
            continue
        day = (a.get("startTimeLocal") or "")[:10] or today.isoformat()
        base = f"{day}_{aid}_{slug(a.get('activityName'))}"
        folder = os.path.join(ROOT, "activities", day[:4])
        os.makedirs(folder, exist_ok=True)
        summary_path = os.path.join(folder, base + ".json")
        save_json(summary_path, a)
        fit_rel = download_fit(token, aid, folder, base)
        index[aid] = {
            "date": day,
            "start_local": a.get("startTimeLocal"),
            "name": a.get("activityName"),
            "type": key_of(a, "activityType"),
            "event_type": key_of(a, "eventType"),
            "distance_m": a.get("distance"),
            "duration_s": a.get("duration"),
            "elevation_gain_m": a.get("elevationGain"),
            "avg_hr": a.get("averageHR"),
            "summary": os.path.relpath(summary_path, ROOT),
            "fit": fit_rel,
            "synced_at": now_iso(),
        }
        new += 1
        if new % 25 == 0:
            log(f"Activities: {new} downloaded so far")
        save_json(idx_path, index)   # save as we go so an interrupted backfill resumes
        time.sleep(1)
    mark_covered(state, "activities", start, today)

    # Retry files that failed before, whatever their date; give up after MAX_FIT_ATTEMPTS
    # (manual entries have no file at all).
    retried = 0
    for aid, rec in index.items():
        if rec.get("fit") or rec.get("fit_missing") or retried >= 25:
            continue
        rec["fit_attempts"] = rec.get("fit_attempts", 1) + 1
        base = os.path.join(ROOT, rec["summary"])[:-len(".json")]
        rec["fit"] = download_fit(token, aid, os.path.dirname(base), os.path.basename(base))
        if rec["fit"]:
            log(f"Activity {aid}: file downloaded on retry")
        elif rec["fit_attempts"] >= MAX_FIT_ATTEMPTS:
            rec["fit_missing"] = True
            log(f"Activity {aid}: no file after {MAX_FIT_ATTEMPTS} attempts; not trying again")
        retried += 1
        time.sleep(1)

    details = 0
    if scope == "all":                # full activity record (laps, splits, metadata) and workouts
        for aid, rec in sorted(index.items(), key=lambda kv: kv[1].get("start_local") or ""):
            if rec.get("details"):
                continue
            base = os.path.join(ROOT, rec["summary"])[:-len(".json")]
            try:
                save_json(base + ".details.json", api(token, f"/activity-service/activity/{aid}"))
                w = api(token, f"/activity-service/activity/{aid}/workouts")
                if w:
                    save_json(base + ".workouts.json", w)
                rec["details"] = os.path.relpath(base + ".details.json", ROOT)
                details += 1
            except SyncError as e:
                if e.code == "TOKEN_REJECTED":
                    raise
                log(f"Could not get details for activity {aid}: {e}")
            if details and details % 50 == 0:
                save_json(idx_path, index)
                log(f"Activity details: {details} so far")
            time.sleep(0.5)
    save_json(idx_path, index)
    return new, len(index), details


# ---------------------------------------------------------------- weight

def kg(v):
    if v is None:
        return ""
    return round(v / 1000, 2) if v > 500 else round(v, 2)   # Garmin usually reports grams


def sync_weight(token, state, start):
    path = os.path.join(ROOT, "weight", "weight.json")
    entries = {str(e.get("timestampGMT") or e.get("date")): e for e in load_json(path, [])}
    today = dt.date.today()
    for w_from, w_to in ranges_to_fetch(state, "weight", start, today):
        cur = w_from
        while cur <= w_to:
            end = min(cur + dt.timedelta(days=363), w_to)      # API max is 364 days inclusive
            for e in api(token, f"/weight-service/weight/all/{cur}/{end}") or []:
                entries[str(e.get("timestampGMT") or e.get("date"))] = e
            cur = end + dt.timedelta(days=1)

    rows = sorted(entries.values(), key=lambda e: (e.get("calendarDate") or "", e.get("timestampGMT") or 0))
    save_json(path, rows)
    with open(os.path.join(ROOT, "weight", "weight.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "weight_kg", "body_fat_pct", "muscle_mass_kg"])
        for e in rows:
            w.writerow([e.get("calendarDate"), kg(e.get("weight")), e.get("bodyFat") or "", kg(e.get("muscleMass"))])
    mark_covered(state, "weight", start, today)
    return len(rows)


# ---------------------------------------------------------------- health (scope "all")

# name, path ({start}/{end} in the path, or startDate/endDate query), max days per request (None: undocumented)
RANGE_ENDPOINTS = [
    ("daily_summaries", "/usersummary-service/v2/dailysummaries", 364),
    ("sleep", "/sleep-service/sleep/dailySleepSummariesByDate", 31),
    ("hrv", "/hrv-service/hrv/daily/{start}/{end}", None),
    ("vo2max", "/metrics-service/metrics/maxmet/daily/{start}/{end}", None),
    ("steps", "/usersummary-service/stats/steps/daily/{start}/{end}", 28),
    ("stress", "/usersummary-service/stats/stress/daily/{start}/{end}", 28),
    ("hydration", "/usersummary-service/stats/hydration/daily/{start}/{end}", 31),
    ("body_battery", "/wellness-service/wellness/bodyBattery/reports/daily", 31),
    ("wellness_activities", "/wellnessactivity-service/activity/summary/range/{start}/{end}", None),
    ("weight_goals", "/goal-service/goal/user/effective/weightgoal/{start}/{end}", None),
]
SNAPSHOTS = [
    ("profile_settings", "/userprofile-service/userprofile/settings", None),
    ("heart_rate_zones", "/biometric-service/heartRateZones/v2", None),
    ("fitness_age", "/fitnessage-service/fitnessage/v2/{today}", None),
    ("activity_types", "/activity-service/activity/activityTypes/simple", None),
]
SHRINK = {364: 91, 91: 28, 28: 7}
DATE_KEYS = ("calendarDate", "summaryDate", "date", "startDate", "calendarDateString",
             "startTimestampLocal", "startTimeLocal", "startTimeGMT")


def records_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if lists:
            return max(lists, key=len)
    return None


def rec_date(r, depth=0):
    """A record's date, looking one level into nested objects (VO2 max nests it under "generic")."""
    if not isinstance(r, dict):
        return None
    for k in DATE_KEYS:
        v = r.get(k)
        if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
            return v[:10]
    if depth == 0:
        for v in r.values():
            d = rec_date(v, 1) if isinstance(v, dict) else None
            if d:
                return d
    return None


def store_health(name, data, a, b):
    """Merge dated records into health/<name>/<year>.json ({date: [records]}); else keep the raw answer."""
    if data in (None, [], {}) or (isinstance(data, dict) and all(v in (None, [], {}) for v in data.values())):
        return 0
    folder = os.path.join(ROOT, "health", name)
    recs = records_of(data)
    if recs and all(rec_date(r) for r in recs):
        by_date = {}
        for r in recs:
            lst = by_date.setdefault(rec_date(r), [])
            if r not in lst:
                lst.append(r)
        for year in sorted({d[:4] for d in by_date}):
            p = os.path.join(folder, f"{year}.json")
            cur = load_json(p, {})
            for d, lst in by_date.items():
                if d[:4] == year:
                    cur[d] = lst
            save_json(p, dict(sorted(cur.items())))
        return len(recs)
    save_json(os.path.join(folder, "raw", f"{a}_{b}.json"), data)
    return 1


ZONE_FIELDS = (("maxHeartRateUsed", "max_hr"), ("restingHeartRateUsed", "resting_hr"),
               ("lactateThresholdHeartRateUsed", "lactate_threshold_hr"), ("trainingMethod", "zone_method"))


def log_zone_changes(new, today):
    """Append changes to max/resting HR or zone method (per sport) to <data>/settings_changes.csv.
    Garmin's VO2 max and zone times shift with these, so the dashboards mark them."""
    old = load_json(os.path.join(ROOT, "health", "snapshots", "heart_rate_zones.json"), None)
    if not isinstance(old, list) or not isinstance(new, list):
        return
    before = {z.get("sport"): z for z in old if isinstance(z, dict)}
    rows = []
    for z in new:
        if not isinstance(z, dict):
            continue
        sport = (z.get("sport") or "default").lower()
        p = before.get(z.get("sport"))
        if p is None:
            if z.get("maxHeartRateUsed"):
                rows.append([today.isoformat(), f"max_hr_{sport}", "", z.get("maxHeartRateUsed"), "sync",
                             f"New {sport} zone set seen by the sync"])
            continue
        for key, label in ZONE_FIELDS:
            if p.get(key) != z.get(key):
                rows.append([today.isoformat(), f"{label}_{sport}", p.get(key), z.get(key), "sync",
                             "Seen by the daily sync; changed in Garmin Connect since the previous day's check"])
    after = {z.get("sport") for z in new if isinstance(z, dict)}
    for sp, p in before.items():
        if sp not in after:
            name = (sp or "default").lower()
            rows.append([today.isoformat(), f"max_hr_{name}", p.get("maxHeartRateUsed"), "removed", "sync",
                         f"{name.capitalize()} zone set switched off; activities fall back to the Default zones"])
    if not rows:
        return
    path = os.path.join(ROOT, "settings_changes.csv")
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new_file:
            w.writerow(["date", "setting", "from", "to", "date_basis", "note"])
        w.writerows(rows)
    for r in rows:
        log(f"Setting change logged: {r[1]} {r[2]} -> {r[3]}")


def sync_health(token, state, start, warnings):
    today = dt.date.today()
    sizes = state.setdefault("chunk_size", {})
    counts = {}
    for name, path, max_days in RANGE_ENDPOINTS:
        size = sizes.get(name) or max_days or 364
        n = calls = 0
        try:
            for r_from, r_to in ranges_to_fetch(state, name, start, today):
                cur = r_from
                while cur <= r_to:
                    end = min(cur + dt.timedelta(days=size - 1), r_to)
                    if "{start}" in path:
                        p, params = path.format(start=cur, end=end), None
                    else:
                        p, params = path, {"startDate": cur.isoformat(), "endDate": end.isoformat()}
                    try:
                        data = api(token, p, params)
                    except SyncError as e:
                        if e.status in (400, 413, 422) and size in SHRINK:
                            size = sizes[name] = SHRINK[size]
                            log(f"{name}: range too long, retrying with {size}-day requests")
                            continue
                        raise
                    n += store_health(name, data, cur, end)
                    calls += 1
                    if calls % 25 == 0:
                        log(f"{name}: through {end}")
                    cur = end + dt.timedelta(days=1)
                    time.sleep(0.5)
            mark_covered(state, name, start, today)
        except SyncError as e:
            if e.code in ("TOKEN_REJECTED", "NETWORK"):
                raise
            warnings.append(f"{name}: {e}")
            log(f"WARNING {name}: {e}")
        counts[name] = n
    if state.get("snapshots_on") != today.isoformat():
        for name, path, _ in SNAPSHOTS:
            try:
                data = api(token, path.format(today=today))
                if name == "heart_rate_zones" and data is not None:
                    log_zone_changes(data, today)
                if data is not None:
                    save_json(os.path.join(ROOT, "health", "snapshots", f"{name}.json"), data)
            except SyncError as e:
                if e.code in ("TOKEN_REJECTED", "NETWORK"):
                    raise
                warnings.append(f"{name}: {e}")
        state["snapshots_on"] = today.isoformat()
    return counts


# ---------------------------------------------------------------- diagnose

def diagnose():
    """Try header/body variants against the token endpoint; print status codes only, never the key or token."""
    key = get_key()
    variants = [
        ("POST", f"ApiKey {key}", None, {}),
        ("POST", f"ApiKey {key}", b"", {}),
        ("POST", f"ApiKey {key}", b"{}", {"Content-Type": "application/json"}),
        ("POST", f"ApiKey [{key}]", None, {}),
        ("POST", f"apikey {key}", None, {}),
        ("POST", f"Bearer {key}", None, {}),
        ("POST", key, None, {}),
        ("GET", f"ApiKey {key}", None, {}),
    ]
    labels = ["ApiKey <key>, no body", "ApiKey <key>, empty body", "ApiKey <key>, JSON body",
              "ApiKey [<key>]", "apikey <key> (lowercase)", "Bearer <key>", "<key> only", "GET ApiKey <key>"]
    secrets = {key}
    for label, (method, auth, data, extra) in zip(labels, variants):
        res, err = _request_once(method, TOKEN_URL, {"User-Agent": UA, "Accept": "application/json",
                                                  "Authorization": auth, **extra}, data, 60)
        if res is None:
            print(f"{label:28} network error: {err}")
            continue
        code, body, hdrs = res
        text = body[:200].decode("utf-8", "replace")
        for s in secrets:
            text = text.replace(s, "<key>")
        if code == 200:
            text = "(token returned, not shown)"
        hint = {k: v for k, v in hdrs.items() if k in ("www-authenticate", "content-type", "server", "cf-ray")}
        print(f"{label:28} HTTP {code}  {hint}  {text!r}")
        time.sleep(1)
    print(f"\nKey: {len(key)} characters, {key.count('.')} dots")


# ---------------------------------------------------------------- rebuild

def rebuild(cfg, reason):
    """Run tools/build.py (CSVs + HTML dashboard) with the tools Python; never fails the sync."""
    build = os.path.join(ENGINE, "tools", "build.py")
    if not os.path.exists(build):
        return "no tools installed"
    py = cfg.get("tools_python") or sys.executable
    try:
        r = subprocess.run([py, "-X", "utf8", "-I", build, "--root", ROOT], capture_output=True, text=True, timeout=1800)
    except Exception as e:
        log(f"Rebuild failed to start: {e!r}")
        return "failed"
    if r.returncode != 0:
        log(f"Rebuild failed: {(r.stderr or r.stdout).strip()[-400:]}")
        return "failed"
    log(f"Rebuilt dashboards ({reason}): {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'ok'}")
    return "ok"


def data_fingerprint():
    """What the dashboards depend on besides new activities: weight, HR settings log, config."""
    import hashlib    # content, not modification time: the sync rewrites weight.csv on every run
    parts = []
    for rel in ("weight/weight.csv", "settings_changes.csv", "config/areas.json", "config/plan.json",
                "config/overrides.json", "config/race_words.json", "athlete.md"):
        try:
            with open(os.path.join(ROOT, rel), "rb") as f:
                parts.append(f"{rel}:{hashlib.md5(f.read()).hexdigest()}")
        except FileNotFoundError:
            pass
    return "|".join(parts)


# ---------------------------------------------------------------- main

def main():
    os.makedirs(ENGINE, exist_ok=True)
    lock = open(os.path.join(ENGINE, "lock"), "w")
    try:
        if IS_WIN:
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another sync is running; exiting.")
        return 0

    state_path = os.path.join(ENGINE, "state.json")
    state = load_json(state_path, {})
    migrate_state(state)
    status = {"last_run": now_iso(), "ok": False}
    warnings = []
    try:
        cfg = load_config()
        status.update(scope=cfg["scope"], history=cfg["history"])
        token = get_token(get_key())
        today = dt.date.today()
        start = history_start(cfg, token, state, today)
        status["history_from"] = start.isoformat()
        n_new, n_total, n_det = sync_activities(token, state, start, cfg["scope"])
        save_json(state_path, state)
        status.update(new_activities=n_new, total_activities=n_total)
        w_start = dt.date(2008, 1, 1) if cfg["history"] == "all" else start
        n_w = sync_weight(token, state, w_start)
        save_json(state_path, state)
        status.update(weight_entries=n_w)
        if cfg["scope"] == "all":
            status["activity_details_fetched"] = n_det
            status["health_records"] = sync_health(token, state, start, warnings)
        status["ok"] = True
        fp = data_fingerprint()
        if n_new or n_det or fp != state.get("built_fingerprint") or not state.get("built_ok"):
            reason = f"{n_new} new activities" if n_new else "changed data or config"
            status["rebuild"] = rebuild(cfg, reason)
            state["built_ok"] = status["rebuild"] in ("ok", "no tools installed")
            state["built_fingerprint"] = data_fingerprint()
        if warnings:
            status["warnings"] = warnings
        state["last_success"] = status["last_run"]
        extra = f", health {sum(status['health_records'].values())} records" if cfg["scope"] == "all" else ""
        log(f"OK ({cfg['scope']}, from {start}): {n_new} new activities ({n_total} total), "
            f"{n_w} weight entries{extra}" + (f"; {len(warnings)} warnings" if warnings else ""))
    except SyncError as e:
        status.update(error_code=e.code, error=str(e))
        log(f"ERROR {e.code}: {e}")
    except KeyboardInterrupt:
        status.update(error_code="STOPPED", error="Stopped by the user")
        log("Stopped by the user (Ctrl+C); the next sync resumes where this one stopped")
    except Exception as e:  # keep a record of anything unexpected
        status.update(error_code="UNEXPECTED", error=repr(e))
        log(f"ERROR UNEXPECTED: {e!r}")
    status["last_success"] = state.get("last_success")
    save_json(state_path, state)
    save_json(os.path.join(ROOT, "status.json"), status)
    return 0 if status["ok"] else 1


def due():
    """For schedulers that can't watch a file (Windows Task Scheduler runs this every 15 min with --if-due):
    sync when the trigger file was touched since the last run, or the last run is 3 hours old."""
    st = load_json(os.path.join(ROOT, "status.json"), {})
    try:
        last = dt.datetime.fromisoformat(st["last_run"]).timestamp()
    except (KeyError, ValueError):
        return True
    try:
        if os.path.getmtime(os.path.join(ENGINE, "trigger")) > last:
            return True
    except OSError:
        pass
    return time.time() - last >= 3 * 3600 - 60


if __name__ == "__main__":
    if "--root" in sys.argv:                       # same as CLAUDROMOS_DIR, for schedulers without env vars
        i = sys.argv.index("--root")
        ROOT = os.path.abspath(os.path.expanduser(sys.argv[i + 1]))
        ENGINE = os.path.join(ROOT, ".claudromos")
        del sys.argv[i:i + 2]
    if "--if-due" in sys.argv:
        sys.argv.remove("--if-due")
        if not due():
            sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        diagnose()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        print(rebuild(load_config(), "requested"))
        sys.exit(0)
    sys.exit(main())
