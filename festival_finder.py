"""Seed list of Brussels umbrella / aggregator calendars worth checking for
other organisations' events (find-related-sites-instructions.md section 1,
"other umbrella programmes").

    python festival_finder.py --calendar            -> print every seed, one per line
    python festival_finder.py --calendar --new      -> print only the ones not in known_sources.txt

This is a curated, hand-maintained list (plus lexicon.AGGREGATOR_HINTS), not
a crawler: these are places that *list other people's events*, so a hit here
is a lead to follow (go find what it links to), not a source to scrape
directly unless it itself passes probe.py's checks.
"""
from __future__ import annotations
import sys

from lexicon import AGGREGATOR_HINTS

# Hand-curated umbrella / open-days / heritage-day / festival-of-festivals pages,
# beyond the per-site aggregator hints already in lexicon.py.
SEEDS = [
    "https://www.quefaire.be/",
    "https://agenda.brussels/",
    "https://www.bruzz.be/agenda",
    "https://visit.brussels/en/agenda",
    "https://www.openmonumenten.be/",
    "https://www.journeesdupatrimoine.brussels/",
    "https://www.heritagedays.brussels/",
    "https://stuut.info/",
    "https://bxl.demosphere.net/",
    "https://www.saintgillesculture.brussels/agenda",
    "https://cultuurkuur.be/agenda",
    "https://www.cultuurnet.be/",
    "https://www.pointculture.be/agenda",
    "https://www.brusselsdesignweek.com/",
    "https://www.cityzeum.com/bruxelles",
    "https://www.1010.brussels/agenda",
]

# AGGREGATOR_HINTS mixes real browsable calendar pages with bare platform
# names (eventbrite, meetup.com) that aren't a single crawlable "umbrella
# page" on their own -- only keep hints that look like a specific site/path.
_GENERIC_PLATFORMS = {"eventbrite", "meetup.com", "ra.co", "allevents.in"}
SEEDS += [f"https://{h}" for h in AGGREGATOR_HINTS if h not in _GENERIC_PLATFORMS]


def _known_keys(path: str = "known_sources.txt") -> set[str]:
    try:
        return set(open(path, encoding="utf-8").read().split())
    except FileNotFoundError:
        return set()


def calendars(only_new: bool = False) -> list[str]:
    seeds = sorted({u.rstrip("/") for u in SEEDS})
    if not only_new:
        return seeds
    import known_sources as K
    keys = _known_keys()
    return [u for u in seeds if not K.is_known(u, keys)]


def main(argv: list[str]) -> int:
    if "--calendar" not in argv:
        print(__doc__)
        return 1
    for u in calendars(only_new="--new" in argv):
        print(u)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
