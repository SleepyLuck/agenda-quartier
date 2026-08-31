# Agenda du quartier

One page showing every event from the neighbourhood organisations you follow: a month grid,
a day-by-day agenda, a link back to the original page, and a one-click `.ics` download with a
reminder built in. A scraper runs on a schedule and writes two static files — no server to keep alive.

```
sources.yml  →  scrape.py  →  docs/events.json   (the page reads this)
                             docs/events.ics     (subscribe from your calendar app)
```

## Run it locally

```bash
pip install -r requirements.txt
python scrape.py                      # writes docs/events.json + docs/events.ics
cd docs && python -m http.server 8000 # then open http://localhost:8000
```

Opening `docs/index.html` straight from disk will not work: the browser blocks `fetch` on
`file://`. Always serve the folder.

`python make_sample.py` restores the demo dataset if you want the page populated before your
first real run.

## Add a source

Edit `sources.yml`:

```yaml
  - name: Maison de quartier
    url: https://theirsite.be/agenda/
    method: auto        # auto | ics | wordpress | jsonld | llm
    colour: "#E8336D"   # optional
```

`auto` tries four strategies in order and stops at the first that returns events:

| Method | What it needs | Reliability |
|---|---|---|
| `ics` | the site publishes an `.ics` feed | exact; use it whenever it exists |
| `wordpress` | The Events Calendar plugin (`/wp-json/tribe/events/v1/events`) | exact when present |
| `jsonld` | `schema.org/Event` in a `<script type="application/ld+json">` | exact when present |
| `llm` | `ANTHROPIC_API_KEY` set | works on anything, occasionally wrong |

A fifth method, `browser`, is **not** part of `auto` — set it explicitly per source. It renders
the page with headless Chromium (via Playwright) before extraction, for agendas where the
events are injected by JavaScript after load and the plain HTML has nothing in it — `probe.py`
will show ~0 date-like strings in that case. It then runs the same `jsonld`/`llm` extraction
against the rendered page, so it still needs `ANTHROPIC_API_KEY` unless the rendered page
happens to carry ld+json. It's slower (a real browser launch per source) and CI needs an extra
`playwright install --with-deps chromium` step — reach for it only when `probe.py` confirms
the other four genuinely can't see the data.

Before adding a site, check for the free options: open the page source and search for
`ld+json`, try `<site>/wp-json/tribe/events/v1/events`, and look for a "subscribe"/"iCal"
link on the agenda page. Each one you find is one source that will never silently drift.

Set `enabled: false` on an entry to keep it in the file but skip it during a run.

### Check a site first

```bash
python probe.py https://theirsite.be/agenda/   # one site
python probe.py --all                          # every url in sources.yml
```

`probe.py` writes nothing. It reports what robots.txt says, what the server actually
returns, which CMS is behind the page, and which of the four methods would work — including
whether the dates are injected by JavaScript, in which case no rung will see them and you
need to find the underlying feed instead.

`python scrape.py --dry-run` then prints what each source returned, still writing nothing.

## Categories

Every event is filed under one of a fixed set of categories (Music, Culture & Arts, Film &
Cinema, Markets & Fairs, Civic & Local Politics, and so on — see `CATEGORIES` in `extract.py`
for the full list). A model classifies each new event from its title and description; this
needs `ANTHROPIC_API_KEY` set, same as the `llm` extraction method. Without a key, everything
files under "Other" rather than failing the run.

Classification only costs an API call for events not seen on a previous run — `scrape.py`
reads the category already assigned in the last published `docs/events.json` and reuses it, so
a normal twice-daily refresh only classifies whatever's new. Categories double as an ICS
`CATEGORIES` entry (alongside the source organisation) and as a filter in the page's sidebar.

## Tags, translation and images

Each event also gets zero or more tags from a fixed list (Free, Kids, Family, Evening, Late
Night, Outdoor, Drop-in, Registration Required, Live, Dance, Food & Drink, Activism,
Sustainability, Accessible, Recurring — see `TAGS` in `extract.py`). `free`/`evening`/`late-night`
are worked out from the event's own time and a free-text regex; `recurring` is also set
automatically for anything spanning 3+ days (an exhibition, not a single date). The rest come
from the same kind of cached, title/description-only model call as categories.

Titles, descriptions and locations are translated to English before classification (again
cached by event, so a repeat run only translates what's new) — proper nouns and venue names are
left alone. Without `ANTHROPIC_API_KEY` set, tagging falls back to just the deterministic tags
and translation is skipped entirely (events stay in their original language) rather than
failing the run.

Per-event images come through automatically wherever the source page structures them (schema.org
`image`, or The Events Calendar's WordPress API); for sources scraped by the `llm` rung, where
the image is stripped along with the rest of the markup before the text ever reaches the model,
each event instead falls back to that page's own `og:image` — a real photo rather than a blank
placeholder, just not a unique one per event.

## Publish it

See **DEPLOY.md** for the full walkthrough. Short version: push to a public GitHub repo, turn
on Pages from `main` / `/docs`, and the included workflow refreshes the calendar twice a day.
The page is then at `https://<you>.github.io/<repo>/` and the feed at `.../events.ics`.

The page warns you when it goes stale: a red banner if no update has landed in 48 hours, and
a line naming any source that returned nothing on the last run.

## Reminders

Two paths, both ending in your own calendar rather than in the browser:

- **Ajouter à mon agenda** downloads a single `.ics` containing a `VALARM` set to the lead
  time chosen in the header. Apple Calendar and Thunderbird honour that alarm. Google
  Calendar tends to apply your own default notification instead of the one in the file —
  verify on your setup rather than trusting the file.
- **S'abonner à tout le calendrier** subscribes your calendar app to `events.ics`, so new
  events appear on their own. Google Calendar refreshes external feeds slowly and on its own
  schedule; Apple Calendar lets you set the interval.

A web page cannot fire a notification for you once it is closed, so there is deliberately no
in-page reminder system.

## Being a good neighbour about it

`robots.txt` is respected by default and requests are spaced 1.5 s apart. Once a day is
plenty. If an organisation asks you not to index them, drop the entry from `sources.yml`.
Displaying a title, date and link back is normal practice; republishing full descriptions of
someone's programme is a different question, so keep the link prominent.

## Files

| File | Role |
|---|---|
| `sources.yml` | your list of organisations and global settings |
| `extract.py` | the four extraction strategies |
| `scrape.py` | orchestration, filtering, JSON and ICS writing |
| `docs/index.html` | the whole front end, no build step |
| `probe.py` | check a site before adding it |
| `.github/workflows/update.yml` | twice-daily refresh and commit |
| `DEPLOY.md` | going live, and what to do when a source breaks |
