# Task for Claude Code: find NEW websites that post events like the ones in the photos, and add their events

Context: Bart gave Claude (in the claude.ai chat) about 60 photos and screenshots of posters, flyers and web pages (36 photos, then batches of 7 and 16 screenshots, then 2 Brussels Design Week screenshots). They are summarised in the table below, grouped by the kind of event. The scraper is now much better (the key must be valid first: check the last run's report shows no `billing` errors). Goal: find sites we do NOT have yet that post similar events, check them, and add what they list to the repository.

## 0. Hard rules

| Rule | Detail |
|---|---|
| Never redo known sites | Before researching or adding anything, build the known set: `python known_sources.py build` (reads sources.yml, seed_sources.yml, new_sources.yml, all_sources.yml, source_seeds.yml, sources_inventory.yml, instagram_accounts.yml, manual_events.yml; known_sources.txt is a ready copy). Pipe every candidate URL through `python known_sources.py filter urls.txt`. Anything it drops is already covered: do not probe, add or re-report it. |
| Shared hosts | Known-ness on Instagram, Facebook, Eventbrite, Luma, Meetup, Linktree is per account/organiser, not per host. An Eventbrite event page alone is not a source: find its organiser page. |
| No Instagram or Facebook scraping | They are follow-by-hand. New handles go in instagram_accounts.yml (tier C, `evidence` filled in). Events from posts go through instagram_intake.py. |
| robots.txt and firewalls | Respect them. If a site is blocked, log it as blocked and move on. Never work around it. |
| Cost | Deterministic first (`probe.py`, `discovery.py`, `source_finder.py score`). Use the model only on a site that passed the checks in section 3. |
| No guesses | An event with no date is not added. A missing time means all-day; a missing place stays empty. Put the evidence in `verification`. |
| Privacy | No personal names or phone numbers from flyers or captions go into any file. |

## 1. What the photos showed (the target types)

Neighbourhood focus: Saint-Gilles first, then Forest, Ixelles, Anderlecht, Marolles / Brussels centre. Prefer events within 120 days.

| Group | What the photos showed | Already found, so skip (examples) | Look for similar |
|---|---|---|---|
| Theatre and performing arts | Théâtre National, Le Rideau, Les Tanneurs, The Bridge, CRUSH festival, Théâtre des Martyrs, Festival des Libertés | theatrenational.be, lerideau.brussels, lestanneurs.be, thebridge.brussels, festivalcrush.be, theatre-martyrs.be, varia.be, bellone.be, halles.be, lesrichesclaires.be | Small Brussels theatres, dance houses, cultural centres, student theatres, theatre festivals |
| Poetry and literature | Midis de la Poésie (13 poster-only sessions), Maison poème, Maison du Livre, Goûter poésie, book clubs | midisdelapoesie.be, maisonpoeme.be, lamaisondulivre.be | Bookshop events, libraries, slam and open-mic nights, publishers' event pages, poetry collectives |
| Festivals, heritage, design | FTI, ANTE, Brussels Design Week (Circularium, GROW), Habrÿs open day | ftifestival.be, ante.brussels, designweek.brussels, circularium.be, nonante-neuf.org | Heritage days, gallery weekends, open studios, tiers-lieux open days, other umbrella programmes (use `festival_finder.py --calendar`) |
| Activism, climate, civic | Critical Mass, Chahut talks (conférences gesticulées), Lire et Écrire, Startmoment Samen Tegen Armoede, XR, Climate Drinks, World Cleanup Day, Amnesty | criticalmass.brussels, conferences-gesticulees.net, lire-et-ecrire.be, bxl.demosphere.net, extinctionrebellion.be, stuut.info | Collectives' own agenda pages, union and association agendas, ATTAC / CNCD / CADTM / GRESEA type organisations, commune participation pages |
| Neighbourhood and markets | Vide-grenier Rue du Monténégro (poster only), brocantes (Van Meenen, Altitude Cent), Mazette, Habrÿs | brocantes1060.be, quefaire.be, brocabrac.fr, brocantes.be, forest.brussels, chechette.be, mazette.brussels | Commune event calendars, comités de quartier, repair cafés, giveboxes, street-party organisers, parish and school fairs |
| Social and English-language | Sidesplitters comedy, Amnesty pub quiz, Sketchbook Club, TEF Talks, Climate Drinks, The Bridge | sidesplittersbrussels.com, englishcomedybrussels.com, meetup groups already listed | Other English comedy, language exchanges, expat meetups, game nights |
| Nightlife | Latin Clubbing, drum and bass night | latinclubbing.be, carre.be, ra.co venue pages already listed | Collectives and club agendas in Saint-Gilles, Forest, Ixelles |
| Workshops and creative | Mazette engraving (4 dates), Martyrs observation drawing, FTI Fashion Factory | mazette.brussels, theatre-martyrs.be | Printmaking, ceramics, sewing and craft studios, art-school short courses |
| Art spaces | Surgir / Brasserie Atlas "Nourrir les débris" (4 poster-only dates), WIELS, Marais Wiels | wiels.org, kmplt.org, brusselsartistrun.net | Artist-run spaces, gallery agendas, BARN network |
| Talks and professional | TEF Talks, Startmoment, Lire et Écrire meeting | welzijnszorg.be, lire-et-ecrire.be | Association conference pages, university and think-tank public events |

The table is from Claude's notes and event file, not a fresh look at each photo; no per-photo list exists.

## 2. Priority gaps (poster-only events with no web source yet)

Try these first; each one that gets a real page becomes a verified event.

| Event | Date | What is missing |
|---|---|---|
| Nourrir les débris (Surgir / Brasserie Atlas) | 8, 10 and 29 Oct | any web page; check Atlas's Facebook page (hand), ra.co/clubs/176243, BARN newsletter |
| Vide-grenier Rue du Monténégro | 1 Nov | not on the commune PDF, brocantes1060, quefaire or brocabrac |
| Startmoment Samen Tegen Armoede 2026 | 23 Oct | only 2024 and 2025 pages exist |
| Mazette engraving | 18 Nov, 16 Dec, 20 Jan | only 21 Oct is on mazette.brussels |
| Midis de la Poésie sessions | autumn 2026 | midisdelapoesie.be/75e-saison/ was blocked for Claude in chat; try from here |
| GROW Material Thinking (Forest) | 1-4 Oct | GROW's own site or Instagram not found |
| XR Teamup calendar | ongoing | public link not known. Take External events only, never Internal |
| Amnesty pub quiz, TEF Talks | unknown | organiser pages not found |

## 3. Procedure

1. `python known_sources.py build`.
2. Generate queries: `python source_finder.py queries --month "<current month year>" --family <family>` for each group above. Add the group's keywords in French, Dutch and English plus the target communes.
3. Collect candidate URLs (search results, outbound links from aggregators such as bxl.demosphere.net and stuut.info, "partners / supported by" links on event pages, organiser links in newsletters via `source_finder.py harvest`). Write them one per line to `candidates.txt`, then `python known_sources.py filter candidates.txt > new_candidates.txt`.
4. For each remaining candidate: `python probe.py <url>` and `python source_finder.py score <url>`. A site passes only if ALL are true: robots allows it; it lists at least 3 upcoming dated events; the events are in the target communes or the site scores 2 or more on neighbourhood; it matches one of the groups above; it is not known.
5. Passing sites: add to sources.yml with the method probe recommends (follow the comments' conventions) and run the scraper once to confirm events appear. Sites that pass the checks but that the scraper cannot read: add to new_sources.yml as candidates with a note, and add the events you can read to manual_events.yml with `verification`.
6. Failing sites: do not add. Log them (section 4) so they are not re-checked.
7. Re-run `python known_sources.py build` at the end so the next run skips everything found now.

Limits per run: at most 8 new sites per group; stop a group after 20 candidates checked with no pass.

## 4. Output

- `new_sites_report.yml`: one entry per checked candidate: url, group, verdict (added / candidate / failed / blocked), method, events found, reason.
- New events in the repository (via the scraper or manual_events.yml), each with a `verification` line.
- Updated sources.yml / new_sources.yml / instagram_accounts.yml.
- A short summary: sites added, sites that failed and why, priority gaps resolved, and anything still unverified.

## 5. Check before finishing

- No added site appears in known_sources.txt from before the run.
- Every new event has a date, a source URL and a `verification` line.
- Run the tests: `python -m pytest test_known_sources.py test_discovery.py test_festival_finder.py test_instagram_intake.py test_keyword_classify.py`.
