"""Compare the just-written docs/events.json against the previously
COMMITTED one (git HEAD) and refuse to publish a real regression.

The scheduled workflow runs this after "Collect events" (which has already
overwritten the working copy of docs/events.json) and before "Commit
updated calendar". scrape.py's own carry-forward logic already keeps a
single failed source from going dark, so this is the last line of defence
for a systemic problem - a missing/corrupted cache, a bug that empties
everything despite individual sources reporting success, or the very first
run after events.json itself is reset.

Exit 0: safe to commit. Exit 1: restores docs/events.json and events.ics to
the committed version and explains why, so "Commit updated calendar" (which
only runs if this step succeeds) never sees the bad data.

    python check_regression.py

Env overrides:
    REGRESSION_MIN_RATIO      default 0.6  - new total must be >= this
                                              fraction of the previous total
    REGRESSION_MAX_NEWLY_DARK default 3    - max sources allowed to go from
                                              kept>0 last run to nothing
                                              (kept+carried==0) this run
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
MIN_RATIO = float(os.environ.get("REGRESSION_MIN_RATIO", "0.6"))
MAX_NEWLY_DARK = int(os.environ.get("REGRESSION_MAX_NEWLY_DARK", "3"))


def _load_committed() -> dict:
    """The payload as it exists at git HEAD - i.e. before this run touched
    anything - not the working copy scrape.py just overwrote on disk."""
    try:
        raw = subprocess.run(
            ["git", "show", "HEAD:docs/events.json"],
            capture_output=True, text=True, check=True, cwd=ROOT,
        ).stdout
    except subprocess.CalledProcessError:
        return {}  # no committed copy yet (first-ever run) - nothing to regress from
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def check(old: dict, new: dict) -> list[str]:
    """Pure comparison, kept separate from git/filesystem so it's unit-testable."""
    old_total = len(old.get("events", []))
    new_total = len(new.get("events", []))
    old_report = {r["source"]: r for r in old.get("report", [])}
    new_report = {r["source"]: r for r in new.get("report", [])}

    newly_dark = sorted(
        name for name, r in old_report.items()
        if r.get("kept", 0) > 0
        and new_report.get(name, {}).get("kept", 0) + new_report.get(name, {}).get("carried", 0) == 0
    )

    reasons = []
    if new_total == 0 and old_total > 0:
        reasons.append(f"every source returned nothing (was {old_total} events, now 0)")
    elif old_total > 0 and new_total < MIN_RATIO * old_total:
        reasons.append(
            f"total dropped to {new_total} from {old_total} events "
            f"({new_total / old_total:.0%}, below the {MIN_RATIO:.0%} floor)"
        )
    if len(newly_dark) > MAX_NEWLY_DARK:
        reasons.append(
            f"{len(newly_dark)} previously-working sources now have nothing at all "
            f"(max allowed: {MAX_NEWLY_DARK}): {', '.join(newly_dark)}"
        )
    return reasons


def main() -> int:
    old = _load_committed()
    new_path = ROOT / "docs" / "events.json"
    new = json.loads(new_path.read_text(encoding="utf-8"))

    reasons = check(old, new)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if reasons:
        lines = ["## Regression guard: refusing to publish this run", ""]
        lines += [f"- {r}" for r in reasons]
        lines.append("")
        lines.append(f"Previous: {len(old.get('events', []))} events. "
                      f"This run: {len(new.get('events', []))} events.")
        lines.append("")
        lines.append("docs/events.json and docs/events.ics have been reverted to the "
                      "last committed version - nothing bad will be pushed.")
        text = "\n".join(lines)
        print(text)
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        subprocess.run(
            ["git", "checkout", "HEAD", "--", "docs/events.json", "docs/events.ics"],
            cwd=ROOT, check=False,
        )
        return 1

    msg = (f"Regression guard: OK - {len(new.get('events', []))} events "
           f"({len(old.get('events', []))} previously)")
    print(msg)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
