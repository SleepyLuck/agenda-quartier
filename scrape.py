"""Read sources.yml, collect events, write docs/events.json and docs/events.ics.

    python scrape.py            # normal run
    python scrape.py --dry-run  # print a report, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dateutil import parser as dateparser

from extract import extract

ROOT = Path(__file__).parent
OUT = ROOT / "docs"

# Riso-ink palette, assigned in order to sources without an explicit colour.
PALETTE = ["#E8336D", "#1B6FE0", "#00937A", "#E07A00",
           "#7B49D6", "#C0392B", "#0F8CA8", "#8A7500"]


def load_config() -> tuple[dict, list[dict]]:
    cfg = yaml.safe_load((ROOT / "sources.yml").read_text(encoding="utf-8"))
    return cfg.get("defaults", {}) or {}, cfg.get("sources", []) or []


def within_window(iso: str, tz: str, past_days: int, horizon_days: int) -> bool:
    now = datetime.now(ZoneInfo(tz))
    try:
        dt = dateparser.parse(iso)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return (now - timedelta(days=past_days)) <= dt <= (now + timedelta(days=horizon_days))


def ics_stamp(iso: str, all_day: bool, tz: str) -> str:
    dt = dateparser.parse(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    if all_day:
        return f";VALUE=DATE:{dt.strftime('%Y%m%d')}"
    return f":{dt.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}"


def ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> str:
    """RFC 5545: no content line longer than 75 octets."""
    out, current = [], line
    while len(current.encode()) > 73:
        cut = 73
        while len(current[:cut].encode()) > 73:
            cut -= 1
        out.append(current[:cut])
        current = " " + current[cut:]
    out.append(current)
    return "\r\n".join(out)


def build_ics(events: list[dict], tz: str, alarm_minutes: int = 120) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//neighbourhood-events//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Neighbourhood events",
             f"X-WR-TIMEZONE:{tz}"]
    now = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}@neighbourhood-events",
            f"DTSTAMP:{now}",
            "DTSTART" + ics_stamp(ev["start"], ev["all_day"], tz),
        ]
        if ev.get("end"):
            lines.append("DTEND" + ics_stamp(ev["end"], ev["all_day"], tz))
        lines.append(fold("SUMMARY:" + ics_escape(ev["title"])))
        if ev.get("location"):
            lines.append(fold("LOCATION:" + ics_escape(ev["location"])))
        body = ev.get("description", "")
        if ev.get("url"):
            lines.append(fold("URL:" + ev["url"]))
            if body:
                body = body + "\n" + ev["url"]
        if body:
            lines.append(fold("DESCRIPTION:" + ics_escape(body)))
        lines.append(fold("CATEGORIES:" + ics_escape(ev["source"])))
        if not ev["all_day"]:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                      f"TRIGGER:-PT{alarm_minutes}M",
                      fold("DESCRIPTION:" + ics_escape(ev["title"])), "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    defaults, sources = load_config()
    tz = defaults.get("timezone", "Europe/Brussels")
    delay = float(defaults.get("request_delay_seconds", 1.5))
    horizon = int(defaults.get("horizon_days", 120))
    past = int(defaults.get("keep_past_days", 1))

    all_events: dict[str, dict] = {}
    report, source_meta = [], []

    for i, src in enumerate(sources):
        colour = src.get("colour") or PALETTE[i % len(PALETTE)]
        if not src.get("enabled", True):
            print(f"{src['name']:<38} skipped (enabled: false)")
            continue
        events, method, note = extract(src, defaults)
        kept = 0
        for ev in events:
            if not within_window(ev["start"], tz, past, horizon):
                continue
            ev["colour"] = colour
            all_events.setdefault(ev["uid"], ev)
            kept += 1
        source_meta.append({"name": src["name"], "url": src["url"],
                            "colour": colour, "count": kept, "method": method})
        report.append({"source": src["name"], "method": method,
                       "found": len(events), "kept": kept, "note": note})
        print(f"{src['name']:<38} {method:<10} found={len(events):<4} kept={kept}"
              + (f"  [{note}]" if note else ""))
        time.sleep(delay)

    events = sorted(all_events.values(), key=lambda e: e["start"])
    payload = {
        "generated": datetime.now(ZoneInfo(tz)).isoformat(),
        "timezone": tz,
        "sources": source_meta,
        "report": report,
        "events": events,
    }

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
        return 0

    OUT.mkdir(exist_ok=True)
    (OUT / "events.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "events.ics").write_text(build_ics(events, tz), encoding="utf-8")
    print(f"\n{len(events)} events -> docs/events.json + docs/events.ics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
