"""Run the real extraction pipeline for ONE named source and show why its
events were kept or dropped - use this when a run report shows found > 0
but kept = 0 (scrape.py drops anything outside the configured date window).

    python inspect_source.py "<source name>"

Prints every event extract() returned, its parsed start/end, and whether
within_window() -- the exact check scrape.py applies before an event reaches
the published count -- would keep it.
"""
from __future__ import annotations
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from extract import extract
from scrape import within_window


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    name = argv[1]
    cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
    defaults = cfg.get("defaults", {})
    src = next((s for s in cfg["sources"] if s["name"] == name), None)
    if not src:
        print(f"no source named {name!r} in sources.yml")
        return 2
    tz = defaults.get("timezone", "Europe/Brussels")
    horizon = int(defaults.get("horizon_days", 120))
    past = int(defaults.get("keep_past_days", 1))
    now = datetime.now(ZoneInfo(tz))
    print(f"now = {now.isoformat()}  window = now-{past}d .. now+{horizon}d\n")

    events, method, note, error_class = extract(src, defaults)
    print(f"method={method}  error_class={error_class!r}  note={note!r}")
    print(f"{len(events)} event(s) found:\n")
    for e in events:
        ok = within_window(e["start"], tz, past, horizon)
        print(f"{'KEEP' if ok else 'DROP'}  start={e['start']}  end={e.get('end')}  | {e['title'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
