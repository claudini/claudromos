# Onboarding: creating athlete.md

Run this when the data folder has no `athlete.md`, or the athlete asks to set it up again.

1. Start from `assets/athlete.template.md` in this skill.
2. Fill what the data already shows, without asking:
   - watch model (from FIT `device_info` or the activity summaries) and HR source
   - weekly volume over the last 12 weeks, usual easy pace, recent races and their figures
   - HR settings from `health/snapshots/heart_rate_zones.json`
   - the areas detected in `config/areas.json`
3. Ask only for what the data can't show, in one message, and say every item is optional:
   - name and preferred language
   - goal races with dates and targets
   - where the training plan lives, if there is one
   - rules or limits to respect (injuries, days off, no early runs)
   - fuelling preferences (brands, caffeine)
   - how they like feedback (short or detailed)
4. Show the draft, then write it to `D/athlete.md` through the device tools once they agree.

`athlete.md` stays on the athlete's computer (and in their own private repo if they keep one). It is never committed to the shared claudromos repo.

## What belongs in athlete.md

Facts the coach needs to judge a run or a week: goals, plan, physiology settings, reference performances, places, constraints, preferences. Leave out anything the athlete doesn't want a coach to consider. Health details go in only if the athlete asks for them to be taken into account.
