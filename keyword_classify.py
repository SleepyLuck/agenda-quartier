"""Classify a candidate source's text into the event-type groups used by the
'find related sites' hunt (find-related-sites-instructions.md section 1).

    python keyword_classify.py "<text>"        -> matching group ids, best first

Each group has a small FR/NL/EN keyword list drawn from the group's own
description in the instructions. Matching is substring-on-lowercased-text,
so it is deliberately permissive: a site can match more than one group
(e.g. a cultural centre is both 'theatre-performing' and 'workshops-creative').
Scoring is just a keyword hit count per group; it is meant to steer a human
or a probe.py follow-up, not to be the final word on its own.
"""
from __future__ import annotations
import re
import sys

GROUPS: dict[str, list[str]] = {
    "theatre-performing": [
        "theatre", "théâtre", "theater", "danse", "dance", "dans", "spectacle", "spectacles",
        "compagnie", "choregraphie", "chorégraphie", "piece de theatre", "pièce", "saison culturelle",
        "scene", "scène", "toneel", "podiumkunsten", "voorstelling", "performing arts",
    ],
    "poetry-literature": [
        "poesie", "poésie", "poezie", "poetry", "slam", "litterature", "littérature", "literatuur",
        "literature", "librairie", "bookshop", "boekhandel", "book club", "bookclub", "auteur",
        "ecrivain", "écrivain", "schrijver", "lecture publique", "open mic", "goûter poésie",
    ],
    "festival-heritage-design": [
        "festival", "patrimoine", "heritage", "erfgoed", "design", "journees du patrimoine",
        "journées du patrimoine", "open monumentendag", "biennale", "triennale", "open studios",
        "ateliers ouverts", "open atelierdagen", "tiers-lieu", "tiers lieu", "derde plek",
    ],
    "activism-climate-civic": [
        "climat", "climate", "klimaat", "militant", "activisme", "activism", "activisme",
        "associatif", "association", "vzw", "asbl", "collectif", "syndicat", "union",
        "manifestation", "betoging", "pauvrete", "pauvreté", "armoede", "droits humains",
        "human rights", "mensenrechten", "ecologie", "écologie", "critical mass", "cadtm", "attac",
    ],
    "neighbourhood-markets": [
        "brocante", "vide-grenier", "braderie", "rommelmarkt", "marche aux puces",
        "marché aux puces", "vlooienmarkt", "quartier", "buurt", "comite de quartier",
        "comité de quartier", "wijkcomite", "repair cafe", "repair café", "giveaway", "give-box",
        "troc", "bourse aux vetements", "bourse aux vêtements", "fete de quartier", "fête de quartier",
        "buurtfeest", "commune", "gemeente",
    ],
    "social-english": [
        "comedy", "stand-up", "stand up", "open mic", "pub quiz", "quiz night", "language exchange",
        "expat", "meetup", "social club", "game night", "board games", "sketchbook club",
        "english-speaking", "english speaking", "anglophone",
    ],
    "nightlife": [
        "clubbing", "club night", "dj set", "dj-set", "soiree clubbing", "soirée clubbing",
        "dancefloor", "dance floor", "techno", "house music", "drum and bass", "nightclub",
        "discotheque", "discothèque", "fuif", "party night", "rave",
    ],
    "workshops-creative": [
        "atelier", "workshop", "stage de", "cours de", "ceramique", "céramique", "gravure",
        "couture", "sewing", "naaien", "dessin", "tekenen", "drawing", "artisanat", "ambacht",
        "craft", "ecole d'art", "école d'art", "kunstschool",
    ],
    "art-spaces": [
        "galerie", "gallery", "galerij", "artiste", "artist-run", "espace d'art", "art space",
        "exposition", "tentoonstelling", "exhibition", "atelier d'artiste", "artist studio",
        "vernissage", "finissage", "curateur", "curator",
    ],
    "talks-professional": [
        "conference", "conférence", "lezing", "talk", "keynote", "seminaire", "séminaire",
        "colloque", "symposium", "table ronde", "panel discussion", "debat", "débat",
        "think tank", "universite", "université", "universiteit", "professional network",
    ],
}


def classify(text: str, top_n: int = 3) -> list[tuple[str, int]]:
    """Return [(group_id, hit_count), ...] sorted by hit count desc, dropping zero-score groups."""
    t = text.lower()
    scores = []
    for group, words in GROUPS.items():
        n = sum(1 for w in words if w in t)
        if n:
            scores.append((group, n))
    scores.sort(key=lambda gs: gs[1], reverse=True)
    return scores[:top_n]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    text = " ".join(argv[1:])
    hits = classify(text, top_n=len(GROUPS))
    if not hits:
        print("no group matched")
        return 0
    for group, n in hits:
        print(f"{group}\t{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
