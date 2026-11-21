# Weekly review

Weeks run Monday to Sunday unless `athlete.md` says otherwise. Review the last complete week unless asked for another.

1. Get fresh data (`data.md`), then run `review.py weekly` for the week.
2. Read the plan for that week: the plan doc or `config/plan.json` named in `athlete.md`, plus the rules in `athlete.md` (ramp limits, lighter weeks, taper and descent rules, what to skip first).
3. Report in this order:
   1. Verdict in one or two sentences.
   2. The week against the plan: km or hours, long run, gain, number of runs, and whether the key sessions happened, judged from names, paces and gain.
   3. Flags from the script.
   4. Weight trend, if there is a new weigh-in.
   5. Next week's focus from the plan, with one concrete adjustment if the data calls for it.
4. For a race, long run or mountain run in the week, add a short section using `analysis.md`: gradient bands, climb rate in m/h, steep-descent pace and cadence. Compare it with the reference races in `athlete.md`.

## Heart rate

Use HR for trends at the same pace and terrain. Run the artifact checks in `analysis.md` before trusting a spike. If `athlete.md` says easy runs go by effort, judge them by pace and the athlete's notes, not by zone time.

## When nobody is watching

A scheduled review has no one to answer questions. Take the most reasonable reading, say which at the top, and send anything the athlete must read through the notification or message tool the session offers.

## Example scheduled-task prompt

> Run my Claudromos weekly review with the claudromos-coach skill: sync first, review last week against my plan, and send me the verdict and next week's focus.

An evening check works the same way:

> With the claudromos-coach skill, check whether I ran today. If I did, sync and give me a three-line review of the run. If I didn't, do nothing.
