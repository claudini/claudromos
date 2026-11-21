# Analysis methods

Every claim about a run comes from numbers computed from the file, never from eyeballing or assumption. Be direct, including when a goal is unrealistic. Use the athlete's units and tone from `athlete.md`.

## 1. Parse the file

Activity files are too large to read whole. Parse them with a script; do not page through them. For a FIT file, convert it first with `fit_convert.py` (see `data.md`); the GPX it writes loads with the parser below.

- GPX from Garmin and from `fit_convert.py` carries `hr` and `cad` in `TrackPointExtension`. Cadence there is per leg: multiply by 2 for steps/min.
- Points are irregular (smart recording), so weight every average by the time gap between points.
- Distance: haversine between consecutive points.
- Elevation gain and loss: accumulate only changes larger than 2 m from the last reference, to suppress noise.
- Stopped time: gaps where speed is under 0.5 m/s.
- Read the activity name, type and start time from the header.

```python
import math, datetime as dt, xml.etree.ElementTree as ET
NS = {'g': 'http://www.topografix.com/GPX/1/1',
      't': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1'}

def hav(a, b):
    R = 6371000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def load(path):
    P = []
    for p in ET.parse(path).getroot().iterfind('.//g:trkpt', NS):
        t = dt.datetime.fromisoformat(p.find('g:time', NS).text.replace('Z', '+00:00'))
        hr, cad = p.find('.//t:hr', NS), p.find('.//t:cad', NS)
        P.append([float(p.get('lat')), float(p.get('lon')), float(p.find('g:ele', NS).text), t,
                  int(hr.text) if hr is not None else None,
                  int(cad.text) * 2 if cad is not None else None])
    T = [(p[3] - P[0][3]).total_seconds() for p in P]
    d = [0.0]
    for i in range(1, len(P)):
        d.append(d[-1] + hav(P[i - 1], P[i]))
    return P, T, d
```

Run Python with `-I` on uploaded files and keep scripts in a separate directory from the uploads.

## 2. Standard analysis

Compute and report:

- Distance, elapsed time, stopped time, gain and loss, high point and where it is.
- Average pace and time-weighted average heart rate.
- Per-km splits: pace, average and max HR, cadence, metres up and down.
- A 2-minute timeline (HR, cadence, speed, elevation change) to see how the race unfolded.
- Time in each 10 bpm heart rate band.
- Gradient bands, using 200 m segments: steep up (over 8%), up (3–8%), flat, down (3–8%), steep down (over 8%). For each band give distance, time, pace, average HR, running cadence and share of time running. For climbs also give vertical speed in m/h.
- First half against second half, and the last 2–3 km against the rest, to judge pacing and finish effort.

Interpret the result against `athlete.md` (goals, reference races, known quirks) and against what the runner said about the day (effort, shoes, pain, conditions). Say where the data confirms their account and where it does not.

## 3. Heart rate sanity check

Optical wrist sensors produce false readings. Before trusting any spike or dip, print the point-by-point data around it and test:

- **Onset:** does it start within seconds of a hike-to-run transition or a cadence change?
- **Effort mismatch:** is HR 25+ bpm higher than at the same pace and gradient elsewhere in the same run?
- **Rise rate:** a jump of 30 bpm in about 30 seconds at easy pace is not physiological.
- **Recovery rate:** a fall of 35+ bpm in about 30 seconds on stopping is too fast.
- **Dips:** HR far below the surrounding level while climbing is also an artifact.

If several hold, call it an artifact, say so plainly, and report averages with those windows excluded alongside the recorded figure. Check whether the same pattern appears in the runner's other files; that strengthens the call. Note that it cannot be proven from the file alone.

## 4. Comparing races

- **Different courses:** compare by gradient band (pace, HR, m/h), not by total time. For a rough overall figure use effort distance: km plus gain in metres divided by 100. Say that surface, season and conditions differ.
- **Same course:** align the tracks. Map each point of one run to the nearest point of the reference run with a forward-only search window (about 400 m), then compare time and HR between fixed course landmarks: bottom and top of each climb, the summit, the finish.
- **Late or early watch start:** find where the short track begins on the reference course, compare only the shared stretch, and estimate the missing part from the reference run. Label that total as an estimate.
- Report where the time went, section by section, and separate fitness from execution: same climb time at the same HR means fitness is unchanged, whatever the finish time says.

## 5. Estimating a target

Build the estimate from demonstrated performance, section by section:

1. Baseline: the best recent run on that course or the closest equivalent.
2. Remove avoidable losses: stops, a known equipment problem, an eased finish.
3. Add only gains the files support, for example a climbing rate or descent pace already achieved in another race at a sustainable HR.

Give a realistic target, a stretch and a floor, and name the assumption carrying the most weight. When the runner asks for more than the data supports, compute what it would demand (m/h on climbs, min/km on descents, likely HR) and say whether it is current fitness or a training goal. Offer a middle option.

## 6. Race strategy

Deliver a section table: split, cumulative time and how to run each section. Splits must sum exactly to the target. Then add:

- Heart rate range and cap for climbs.
- A fallback rule tied to an early checkpoint (time or HR at the top of the first climb) that switches to the safer plan.
- Descent guidance: cadence target from the runner's own best descending data.
- Equipment or other fixes for whatever cost time before.
- A short preparation checklist of things the plan depends on.

## 7. Fuelling

- Work out what the runner took last time in grams of carbohydrate per hour and ml of fluid per hour.
- Look up the carbohydrate content of the named products before quoting it; do not rely on memory. Cite the product page.
- Usual guidance: 30–60 g per hour for 1–2.5 hours, 60–90 g per hour for 2.5–6 hours, with a glucose-plus-fructose mix above 60 g per hour. Verify against a current source when it matters.
- Build a timed schedule that fits the course: eat on climbs while hiking, not on descents. Show carbs per item and the hourly total.
- Respect the choices in `athlete.md` and anything stated since, such as brand or no caffeine.
- Cover fluid and sodium, and state what is unknown (for example aid station locations).
- Higher intakes need gut training: say how many rehearsal runs and at what intensity.

For disordered-eating signs or medical symptoms (chest pain, fainting, unusual breathlessness), do not give numeric targets; recommend seeing a doctor.

## 8. Estimating max heart rate

Use this when `athlete.md` has no reliable max HR, or the athlete asks to check it. Never derive it from one reading.

1. Take every race from the last 3–4 years plus the 10 training runs with the highest recorded HR.
2. For each, compute the raw max and the best rolling 30 s, 60 s and 5 min averages, the HR change in the 30 s before and after the peak, pace and climb in the 2 minutes before it, and how closely HR tracks cadence at the best 60 s.
3. Exclude a peak if HR rose 30+ bpm in about 30 s, fell 35+ bpm in 30 s, sat within 4 of steps per minute (cadence lock), or came where pace and gradient don't explain it (a descent, an easy stretch).
4. The credible 60 s averages are a floor for max HR. Report their range and median, give a likely max and a conservative lower bound, and suggest a setting at or just below the evidence.
5. Explain what the setting changes on the watch (HR zones, and for Garmin the VO2 max estimate), and log the change in `athlete.md` once the athlete has made it.

## 9. Saving the plan

When asked to save or share a plan, create a document, not a chat message: target and basis, pacing table, race rules, nutrition table, preparation checklist, then a reference table of past races and sources. Keep kilometre marks tied to one named track and say which.