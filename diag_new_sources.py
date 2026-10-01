"""TEMP diagnostic: probe the batch of candidate sources the user proposed
for sources.yml, plus the domains already confirmed by hand while building
manual_events.yml (for the same organisations under a different URL), so
we can tell which domain is the real one before adding anything.

Per the user's own instructions: run probe.py on each, keep only those
that return events, and never bypass a firewall/robots block.

Writes nothing; only prints.
"""
import probe

candidates = [
    # --- user's "verified via search" batch ---
    ("Saint-Gilles Culture (agenda)", "https://culture.stgilles.brussels/"),
    ("La Maison du Livre", "https://www.lamaisondulivre.be/agenda/"),
    ("La Bellone", "https://www.bellone.be/"),
    ("Les Riches-Claires", "https://www.lesrichesclaires.be/"),
    ("Les Tanneurs", "https://www.lestanneurs.be/"),
    ("Le Rideau", "https://www.rideaudebruxelles.be/"),
    ("CRUSH festival (user's URL)", "https://www.crushfestival.be/"),
    ("FTI Brussel", "https://www.ftifestival.be/programma/brussel"),
    ("The Bridge Theatre (user's URL)", "https://www.thebridgetheatre.be/"),
    # --- domains already confirmed by hand for the same orgs (manual_events.yml) ---
    ("CRUSH festival (manual data's URL)", "https://festivalcrush.be/en/"),
    ("The Bridge Theatre (manual data's URL)", "https://thebridge.brussels/copenhagen"),
    ("Midis de la Poesie (manual data's URL)", "https://midisdelapoesie.be/nos-evenements/programmation"),
    # --- user's "unverified" batch ---
    ("Midis de la Poesie (user's URL)", "https://www.midisdelapoesie.be/"),
    ("Varia", "https://www.variaworks.be/"),
    ("Theatre de la Vie", "https://www.theatredelavie.be/"),
    ("Halles de Schaerbeek", "https://www.halles.be/"),
    ("Theatre National", "https://www.theatrenational.be/"),
    ("Theatre Royal du Parc", "https://www.theatreduparc.be/"),
    ("Nourrir Bruxelles", "https://www.nourrir-bruxelles.be/"),
    ("AXOSO", "https://axoso.club/"),
]

for name, url in candidates:
    print(f"\n\n########## {name} ##########")
    try:
        probe.probe(url)
    except Exception as exc:  # noqa: BLE001
        print(f"  probe ERROR: {type(exc).__name__}: {exc}")
