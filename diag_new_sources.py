"""TEMP diagnostic: probe every candidate in new_sources.yml and
seed_sources.yml (two batches of sources.yml candidates, not yet added).

Per the user's own instructions: run probe.py on each, keep only those that
return events, and never bypass a firewall/robots block.

Writes nothing; only prints.
"""
import yaml

import probe

candidates = []
for path in ("new_sources.yml", "seed_sources.yml"):
    candidates += yaml.safe_load(open(path, encoding="utf-8")) or []

for src in candidates:
    print(f"\n\n########## {src['name']} ##########")
    try:
        probe.probe(src["url"])
    except Exception as exc:  # noqa: BLE001
        print(f"  probe ERROR: {type(exc).__name__}: {exc}")
