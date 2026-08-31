"""TEMP diagnostic: dig into the sources that came back partial or empty.

- Fuse / Sounds Jazz Club / BRASS: found events but kept=0 - print the
  actual dates extract() returned, before the window filter, to see if
  they're just outside horizon_days or parsed with a wrong year.
- WIELS / Park Poétik: found=0 despite promising signals in the earlier
  discovery pass - run jsonld and llm separately (extract() only reports
  the last rung's error) to see what each actually returns/raises.
- Kaaitheater: try method=browser directly (same Drupal stack as
  Pianofabriek/Ten Weyngaert, which both needed it).

Writes nothing; only prints.
"""
import yaml

from extract import extract, fetch, fetch_rendered, parse_jsonld, parse_llm

cfg = yaml.safe_load(open("sources.yml", encoding="utf-8"))
defaults = cfg["defaults"]
by_name = {s["name"]: s for s in cfg["sources"]}

print("=" * 78)
print("1. Dates for sources that found events but kept none")
print("=" * 78)
for name in ["Fuse", "Sounds Jazz Club", "BRASS"]:
    src = by_name[name]
    events, method, note = extract(src, defaults)
    print(f"\n{name} ({method}, {len(events)} found):")
    for e in sorted(events, key=lambda e: e["start"])[:8]:
        print(f"    {e['start'][:10]}  {e['title'][:60]}")
    if len(events) > 8:
        print(f"    ... and {len(events) - 8} more")

print()
print("=" * 78)
print("2. WIELS and Park Poetik - jsonld and llm run separately")
print("=" * 78)
for name in ["WIELS", "Park Poétik"]:
    src = by_name[name]
    url = src["url"]
    tz = defaults["timezone"]
    print(f"\n{name}  ->  {url}")
    try:
        html = fetch(url, defaults.get("respect_robots", True))
        print(f"  fetched {len(html)} chars")
    except Exception as exc:  # noqa: BLE001
        print(f"  fetch ERROR: {type(exc).__name__}: {exc}")
        continue
    try:
        evs = parse_jsonld(html, name, url, tz)
        print(f"  jsonld -> {len(evs)} events")
        for e in evs[:3]:
            print(f"    {e['start'][:10]}  {e['title'][:60]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  jsonld ERROR: {type(exc).__name__}: {exc}")
    try:
        evs = parse_llm(html, name, url, tz, defaults["llm_model"])
        print(f"  llm -> {len(evs)} events")
        for e in evs[:5]:
            print(f"    {e['start'][:10]}  {e['title'][:60]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  llm ERROR: {type(exc).__name__}: {exc}")

print()
print("=" * 78)
print("3. Kaaitheater via method=browser")
print("=" * 78)
src = dict(by_name["Kaaitheater"])
src["method"] = "browser"
events, method, note = extract(src, defaults)
print(f"Kaaitheater (browser) -> {len(events)} events" + (f"  [{note}]" if note else ""))
for e in sorted(events, key=lambda e: e["start"])[:8]:
    print(f"    {e['start'][:10]}  {e['title'][:60]}")

print()
print("=" * 78)
print("4. Le Senghor retry (was a ConnectTimeout last run)")
print("=" * 78)
src = by_name["Le Senghor"]
events, method, note = extract(src, defaults)
print(f"Le Senghor ({method}) -> {len(events)} events" + (f"  [{note}]" if note else ""))
for e in sorted(events, key=lambda e: e["start"])[:5]:
    print(f"    {e['start'][:10]}  {e['title'][:60]}")
