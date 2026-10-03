"""Run the real extraction pipeline for ONE named source and show why its
events were kept or dropped - use this when a run report shows found > 0
but kept = 0 (scrape.py drops anything outside the configured date window).

    python inspect_source.py "<source name>"               # what extract() returns today
    python inspect_source.py "<source name>" --blocks       # every repeated-listing candidate on the page
    python inspect_source.py "<source name>" --rendered     # same as the plain run, but after JS runs (Playwright)

--blocks helps when the page has more than one repeated block (e.g. an
"upcoming" list and a separate "past events" archive) and the wrong one
might be winning. --rendered helps when the plain-fetched HTML looks like
a stale/static fallback that doesn't match what a real browser shows.
"""
from __future__ import annotations
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

import discovery as D
from extract import extract, fetch, fetch_rendered
from scrape import within_window


def _load(name: str):
    cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
    defaults = cfg.get("defaults", {})
    src = next((s for s in cfg["sources"] if s["name"] == name), None)
    return src, defaults


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    name = argv[1]
    src, defaults = _load(name)
    if not src:
        print(f"no source named {name!r} in sources.yml")
        return 2
    tz = defaults.get("timezone", "Europe/Brussels")
    horizon = int(defaults.get("horizon_days", 120))
    past = int(defaults.get("keep_past_days", 1))
    now = datetime.now(ZoneInfo(tz))
    today = now.date()
    print(f"now = {now.isoformat()}  window = now-{past}d .. now+{horizon}d\n")

    if "--blocks" in argv:
        html = fetch(src["url"], src.get("respect_robots", defaults.get("respect_robots", True)))
        blocks = D.find_listing_blocks(html, today)
        print(f"{len(blocks)} repeated-listing candidate(s) (best first):\n")
        for b in blocks:
            print(f"parent={b['parent']}  item={b['item']}  items={b['items']}  "
                  f"with_date={b['with_date']}  with_link={b['with_link']}  with_future={b['with_future']}")
            print(f"  sample: {b['sample']}\n")
        return 0

    if "--rendered" in argv:
        html = fetch_rendered(src["url"], src.get("respect_robots", defaults.get("respect_robots", True)))
        events = D.extract_recipe_events(html, src["url"], today)
        print(f"{len(events)} event(s) from the RENDERED page's best recipe block:\n")
        for e in events:
            ok = within_window(e["start"] + (f"T{e['time']}" if e.get("time") else ""), tz, past, horizon)
            print(f"{'KEEP' if ok else 'DROP'}  start={e['start']}  end={e.get('end')}  | {e['title'][:70]}")
        return 0

    events, method, note, error_class = extract(src, defaults)
    print(f"method={method}  error_class={error_class!r}  note={note!r}")
    print(f"{len(events)} event(s) found:\n")
    for e in events:
        ok = within_window(e["start"], tz, past, horizon)
        print(f"{'KEEP' if ok else 'DROP'}  start={e['start']}  end={e.get('end')}  | {e['title'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
