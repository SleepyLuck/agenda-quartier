"""TEMP diagnostic: probe every candidate in new_sources.yml (the corrected
URL list - v1 of this batch had a wrong Le Rideau domain and wrong domains
for CRUSH festival / The Bridge Theatre / Midis de la Poesie, now fixed).

Per the user's own instructions: run probe.py on each, keep only those that
return events, and never bypass a firewall/robots block.

Writes nothing; only prints.
"""
import yaml

import probe

candidates = yaml.safe_load(open("new_sources.yml", encoding="utf-8")) or []

for src in candidates:
    print(f"\n\n########## {src['name']} ##########")
    try:
        probe.probe(src["url"])
    except Exception as exc:  # noqa: BLE001
        print(f"  probe ERROR: {type(exc).__name__}: {exc}")
