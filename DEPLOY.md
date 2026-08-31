# Putting it online

The site is static: three files in `docs/` served by GitHub Pages, refreshed twice a day by a
GitHub Actions job that runs the scraper and commits the result. Nothing to pay for, nothing
to keep alive, no server to patch.

```
GitHub Actions (twice daily)  →  python scrape.py  →  commit docs/events.json + .ics
                                                       ↓
                            GitHub Pages serves docs/  →  https://<you>.github.io/<repo>/
```

## 1. Check the sources first

Do this before publishing anything. A source that returns nothing is better found now than
by a neighbour who trusted the page.

```bash
pip install -r requirements.txt
python probe.py --all
python scrape.py --dry-run
```

Fix `sources.yml` until `--dry-run` reports events for each source you care about, then run
`python scrape.py` once for real so `docs/` holds live data rather than the sample.

## 2. Push it

The repository must be **public** — GitHub Pages on a private repository requires a paid
plan. Nothing sensitive lives here: the API key goes in Actions secrets, not in the code.

```bash
git init && git add . && git commit -m "Agenda du quartier"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

## 3. Turn on Pages

Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/docs` → Save.

The URL appears on that page within a minute or two: `https://<you>.github.io/<repo>/`.

## 4. Add the API key, only if you use `method: llm`

Settings → Secrets and variables → Actions → New repository secret → name it
`ANTHROPIC_API_KEY`. Secrets are not readable from a public repository and are not exposed to
workflows triggered by forks. Set a spending limit on the key: a runaway loop on a page with
hundreds of events is the realistic failure mode, not an attacker.

If every source resolves to `ics`, `wordpress` or `jsonld`, skip this step entirely. The
scraper runs fine without the key and simply never reaches the `llm` rung.

## 5. Run it once by hand

Actions → Update events → Run workflow. Watch it go green, then check that the run summary
shows a sensible event count and that your page reflects it.

From then on it runs at 05:00 and 16:00 UTC. GitHub's scheduler is best-effort and often
runs late, sometimes by half an hour or more — irrelevant for a calendar of neighbourhood
events, but do not treat the timestamp as exact.

## 6. Subscribe

Open the published page and use **S'abonner à tout le calendrier**, or paste
`https://<you>.github.io/<repo>/events.ics` into your calendar app's "add by URL" field.
New events then arrive on their own, at whatever refresh interval your calendar app uses.

## Optional: your own domain

Buy a `.be` domain, then Settings → Pages → Custom domain. GitHub writes a `CNAME` file into
`docs/` and asks your registrar for a DNS record. Tick "Enforce HTTPS" once the certificate
is issued. A domain reads better on a flyer than a `github.io` URL, and it means you can move
the hosting later without breaking anyone's calendar subscription.

## When it breaks

It will break: these are small volunteer-run sites that get redesigned without warning. The
page is built to make that visible rather than to fail quietly.

| Symptom | What it means | What to do |
|---|---|---|
| Red banner: "dernière mise à jour il y a N jours" | The workflow has not committed in over 48 h | Actions tab — look for a failed or disabled run |
| "Aucun événement trouvé pour X" under the calendar | That site changed and its method no longer matches | `python probe.py <url>`, change the method |
| Workflow failed, log says every source returned nothing | Usually a network blip, occasionally all sites redesigned at once | Re-run it; the published calendar was not overwritten |
| Scheduled runs stopped after about two months | GitHub disables cron on repositories with no recent activity. Whether the bot's own commits count as activity is not something I would rely on | Push any commit, or press Run workflow, to re-arm it |
| Events appear with wrong dates | An `llm` source guessed a year, or a date format was read day-first when it was month-first | Prefer `ics`/`jsonld` for that source if at all possible |

Watch the first week's commits. A one-line diff every day means it works; a diff that empties
half the calendar means a source broke.

## Being visible about what this is

If you share the URL beyond a few neighbours, put a line in the footer saying the page is an
automatic collection, who runs it, and how to ask to be removed. Organisations are generally
glad to be listed and much less glad to discover it by accident. A short mail to the three
venues before you publish costs nothing and turns a scraper into a collaboration — it is also
the most likely route to someone simply handing you an `.ics` feed.
