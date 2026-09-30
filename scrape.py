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

from extract import (CATEGORIES, TAGS, TIME_CACHE_VERSION, classify_categories,
                      classify_tags, enrich_missing_times, extract, translate_events)

ROOT = Path(__file__).parent
OUT = ROOT / "docs"

# Riso-ink palette, assigned in order to sources without an explicit colour.
PALETTE = ["#E8336D", "#1B6FE0", "#00937A", "#E07A00",
           "#7B49D6", "#C0392B", "#0F8CA8", "#8A7500"]


def load_config() -> tuple[dict, list[dict]]:
    cfg = yaml.safe_load((ROOT / "sources.yml").read_text(encoding="utf-8"))
    return cfg.get("defaults", {}) or {}, cfg.get("sources", []) or []


def _previous_payload() -> dict:
    path = OUT / "events.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _previous_events() -> list[dict]:
    return _previous_payload().get("events", [])


def load_category_cache() -> dict[str, str]:
    """uid -> category id, from the previously published events.json, so a run only
    asks the LLM to classify events it hasn't seen before."""
    return {e["uid"]: e["category"] for e in _previous_events() if e.get("category")}


def load_tag_cache() -> dict[str, list[str]]:
    """uid -> tag id list, from the previously published events.json."""
    return {e["uid"]: e["tags"] for e in _previous_events() if e.get("tags")}


def load_translation_cache() -> dict[str, dict]:
    """uid -> already-translated {title, description, location}, from the
    previously published events.json, so a run only pays to translate events
    it hasn't seen before. Only events actually marked `translated` count -
    otherwise, the very first run after adding translation would mistake
    every event's original-language text for already-done work and never
    translate it."""
    return {e["uid"]: {"title": e.get("title", ""), "description": e.get("description", ""),
                        "location": e.get("location", "")}
            for e in _previous_events() if e.get("translated")}


def load_time_cache() -> dict[str, dict]:
    """uid -> {start, all_day}, for events whose detail page has already been
    checked for a time (successfully or not) - see enrich_missing_times().
    Only trusts entries stamped with the current TIME_CACHE_VERSION, so a fix
    to the time-extraction logic invalidates stale cached results (a bare
    `time_checked: true` from before versioning existed doesn't match either,
    so it's treated as unchecked too) instead of replaying old garbage forever."""
    return {e["uid"]: {"start": e["start"], "all_day": e["all_day"]}
            for e in _previous_events() if e.get("time_checked") == TIME_CACHE_VERSION}


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
    tag_by_id = {t["id"]: t["label"] for t in TAGS}
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
        cats = [ev["source"]]
        cat_meta = next((c for c in CATEGORIES if c["id"] == ev.get("category")), None)
        if cat_meta:
            cats.append(cat_meta["label"])
        cats += [tag_by_id[t] for t in ev.get("tags", []) if t in tag_by_id]
        lines.append(fold("CATEGORIES:" + ics_escape(",".join(cats))))
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

    # Carry-forward: a source that fails outright this run (site down, robots
    # changed, billing) shouldn't make its events vanish from the page - keep
    # showing whatever it last actually delivered, marked stale, until it
    # recovers. Indexed by source name against the previously PUBLISHED
    # payload, not this run's in-progress one.
    prev_payload = _previous_payload()
    prev_events_by_source: dict[str, list[dict]] = {}
    for e in prev_payload.get("events", []):
        prev_events_by_source.setdefault(e.get("source", ""), []).append(e)
    prev_source_meta_by_name = {s["name"]: s for s in prev_payload.get("sources", [])}
    today_iso = datetime.now(ZoneInfo(tz)).date().isoformat()

    all_events: dict[str, dict] = {}
    report, source_meta = [], []
    # Set on the first billing/auth failure from the API itself - every other
    # llm/browser source this run is doomed the same way, so stop paying for
    # (and logging) 15+ more identical failures. See extract()'s skip_llm.
    billing_broken = False

    for i, src in enumerate(sources):
        colour = src.get("colour") or PALETTE[i % len(PALETTE)]
        if not src.get("enabled", True):
            print(f"{src['name']:<38} skipped (enabled: false)")
            continue
        events, method, note, error_class = extract(src, defaults, skip_llm=billing_broken)
        if error_class == "billing":
            billing_broken = True
        kept = 0
        for ev in events:
            if not within_window(ev["start"], tz, past, horizon):
                continue
            ev["colour"] = colour
            all_events.setdefault(ev["uid"], ev)
            kept += 1

        carried = 0
        stale = False
        last_ok = today_iso
        if kept == 0:
            prev_meta = prev_source_meta_by_name.get(src["name"], {})
            prev_last_ok = prev_meta.get("last_ok")
            if prev_events_by_source.get(src["name"]) or prev_last_ok:
                stale = True
                last_ok = prev_last_ok or (prev_payload.get("generated", today_iso) or today_iso)[:10]
                for ev in prev_events_by_source.get(src["name"], []):
                    if not within_window(ev["start"], tz, past, horizon):
                        continue
                    ev = dict(ev)
                    ev["colour"] = colour
                    ev["stale"] = True
                    all_events.setdefault(ev["uid"], ev)
                    carried += 1
            else:
                stale = False
                last_ok = None

        source_meta.append({"name": src["name"], "url": src["url"], "colour": colour,
                            "count": kept + carried, "method": method,
                            "stale": stale, "last_ok": last_ok})
        report.append({"source": src["name"], "method": method, "found": len(events),
                       "kept": kept, "carried": carried, "stale": stale,
                       "error_class": error_class, "note": note})
        line = f"{src['name']:<38} {method:<10} found={len(events):<4} kept={kept}"
        if carried:
            line += f"  carried={carried} (stale since {last_ok})"
        if error_class:
            line += f"  [{error_class}] {note}"
        elif note:
            line += f"  [{note}]"
        print(line)
        time.sleep(delay)

    events = sorted(all_events.values(), key=lambda e: e["start"])
    model = defaults.get("llm_model", "claude-haiku-4-5")
    # Several listing pages state a date but no time at all (confirmed live,
    # not a parsing bug) - the event's own detail page usually has it.
    listing_urls = {src["url"] for src in sources}
    enrich_missing_times(events, tz, defaults.get("respect_robots", True), delay,
                          listing_urls, load_time_cache())
    # Translate first so categorising/tagging both work from the same clean
    # English text as the published page, instead of a mix of languages.
    translate_events(events, model, load_translation_cache())
    classify_categories(events, model, load_category_cache())
    classify_tags(events, model, load_tag_cache())
    payload = {
        "generated": datetime.now(ZoneInfo(tz)).isoformat(),
        "timezone": tz,
        "sources": source_meta,
        "categories": CATEGORIES,
        "tags": TAGS,
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
