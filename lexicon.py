"""Keyword lists (FR / NL / EN) used by discovery.py. Edit here, not in the logic.

Everything is lower-case; matching is done on accent-stripped lower-case text unless noted.
Each list comes from wording seen on the real pages/posters of this neighbourhood
(theatrenational.be, lerideau.brussels, thebridge.brussels, mazette.brussels,
ftifestival.be, wiels.org, maisonpoeme.be, flyers) -- extend it when a source is missed.
"""

MONTHS = {
    # FR
    "janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4, "avr": 4,
    "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9,
    "octobre": 10, "oct": 10, "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
    # NL
    "januari": 1, "jan": 1, "februari": 2, "feb": 2, "maart": 3, "mrt": 3, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "aug": 8, "oktober": 10, "okt": 10,
    # EN
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12, "sep": 9,
}

WEEKDAYS = {  # Monday = 0
    "lundi": 0, "lun": 0, "mardi": 1, "mercredi": 2, "mer": 2, "jeudi": 3, "jeu": 3,
    "vendredi": 4, "ven": 4, "samedi": 5, "sam": 5, "dimanche": 6, "dim": 6,
    "maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3, "vrijdag": 4, "zaterdag": 5,
    "zondag": 6, "ma": 0, "di": 1, "wo": 2, "do": 3, "vr": 4, "za": 5, "zo": 6,
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2, "thursday": 3,
    "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

# Words that mean "this is an event page / an events listing" -----------------------------
AGENDA_WORDS = [
    "agenda", "programme", "programmation", "prog", "calendrier", "evenements", "evenement",
    "a l'affiche", "spectacles", "saison", "billetterie", "activites", "sorties",
    "programma", "kalender", "activiteiten", "evenementen", "voorstellingen", "wat is er te doen",
    "events", "what's on", "whats-on", "calendar", "schedule", "shows", "exhibitions", "tickets",
]

EVENT_TYPE_WORDS = [  # words that, near a date, make a block an event
    "vernissage", "finissage", "exposition", "expo", "atelier", "stage", "concert", "spectacle",
    "projection", "conference", "rencontre", "balade", "visite", "brocante", "vide-grenier",
    "braderie", "festival", "soiree", "lecture", "slam", "scene ouverte", "bal", "jam",
    "cine-club", "ciné-club", "conte", "gouter", "marche", "repair cafe", "troc", "bourse",
    "tentoonstelling", "voorstelling", "lezing", "rondleiding", "workshop", "opening",
    "optreden", "feest", "markt", "rommelmarkt", "inloop", "buurtfeest", "wandeling",
    "exhibition", "show", "screening", "talk", "tour", "performance", "party", "open mic",
    "opening night", "book club", "bookclub", "jam session", "quiz", "tasting",
]

# Navigation / boilerplate to ignore when scoring links ------------------------------------
LINK_EXCLUDE = [
    "contact", "mentions-legales", "mentions legales", "privacy", "cookies", "cookie", "newsletter",
    "jobs", "emploi", "vacatures", "presse", "press", "boutique", "shop", "panier", "cart",
    "login", "connexion", "account", "faq", "plan-du-site", "sitemap", "accessibilite",
    "conditions", "terms", "disclaimer", "equipe", "team", "partenaires", "partners", "donate",
    "faire-un-don", "soutenir", "mailto:", "tel:", "javascript:", "#",
]
LISTING_NOISE = ["/tag/", "/category/", "/categorie/", "/author/", "/feed", "?s=", "/page/", "?paged="]

EVENT_PATH_SEGMENTS = [
    "spectacle", "spectacles", "evenement", "evenements", "event", "events", "activite",
    "activites", "activities", "activity", "agenda", "programme", "programmation", "programma",
    "concert", "concerts", "atelier", "ateliers", "exposition", "expositions", "expo", "stage",
    "stages", "workshop", "workshops", "film", "films", "seance", "seances", "evenementen",
    "voorstelling", "voorstellingen", "tentoonstelling", "kalender", "show", "shows", "saison",
    "prog", "whats-on", "calendar",
]

PAGINATION_WORDS = [
    "suivant", "page suivante", "plus d'evenements", "voir plus", "charger plus", "afficher plus",
    "volgende", "meer evenementen", "meer laden", "toon meer", "next", "next page", "load more",
    "show more", "more events", "older", "mois suivant", "volgende maand", "next month",
]

# Money / booking / audience ------------------------------------------------------------------
FREE_WORDS = [
    "gratuit", "entree libre", "entree gratuite", "acces libre", "gratis", "vrije toegang",
    "gratis toegang", "free entry", "free admission", "free entrance", "free event", "free",
]
PAY_WHAT_WORDS = [
    "prix libre", "participation libre", "p.a.f", "paf", "prijs naar keuze", "pay what you want",
    "pay-what-you-can", "donation", "contribution libre", "chapeau",
]
BOOKING_WORDS = [
    "reservation obligatoire", "sur reservation", "reservation souhaitee", "reservation conseillee",
    "inscription obligatoire", "inscription", "s'inscrire", "billetterie", "reserver", "reservez",
    "inschrijving verplicht", "inschrijven", "reserveren", "reservatie", "boeken", "tickets",
    "book now", "register", "registration required", "booking essential", "rsvp",
]
SOLD_OUT_WORDS = ["complet", "sold out", "uitverkocht", "epuise", "plus de places", "geen plaatsen meer"]
CANCELLED_WORDS = ["annule", "reporte", "afgelast", "uitgesteld", "geannuleerd", "cancelled", "canceled", "postponed"]
RECURRING_WORDS = [
    "tous les", "toutes les", "chaque", "hebdomadaire", "mensuel", "le premier", "1er jeudi",
    "elke", "iedere", "wekelijks", "maandelijks", "every", "weekly", "monthly", "each",
]
AUDIENCE_KIDS = ["enfants", "kids", "jeune public", "famille", "family", "gezin", "kinderen", "familie", "ados", "teens"]
AUDIENCE_ADULTS = ["adultes", "18+", "16+", "volwassenen", "adults only", "+18"]
ACCESSIBLE_WORDS = ["pmr", "accessible", "toegankelijk", "wheelchair", "rolstoel", "langue des signes", "gebarentaal", "surtitr", "ondertitel"]
OUTDOOR_WORDS = ["en plein air", "dehors", "exterieur", "buiten", "outdoor", "open air", "parc", "place ", "jardin", "tuin", "rue "]

# Field labels used by venues on their event pages ---------------------------------------------
LABELS = {
    "venue": ["lieu", "ou", "adresse", "salle", "locatie", "waar", "plaats", "venue", "where", "address", "location"],
    "date": ["date", "dates", "quand", "datum", "when", "dag", "jour"],
    "time": ["heure", "horaire", "horaires", "uur", "tijd", "time", "doors", "debut", "start", "aanvang", "porte"],
    "price": ["tarif", "tarifs", "prix", "prijs", "tarief", "price", "tickets", "entree", "paf"],
    "duration": ["duree", "duur", "duration", "length"],
    "language": ["langue", "taal", "language", "surtitrage", "ondertiteling"],
    "age": ["age", "leeftijd", "public", "doelgroep", "kids", "audience"],
    "organiser": ["organisateur", "organisation", "organisatie", "een organisatie van", "presente par", "organised by", "organized by", "avec le soutien", "met steun"],
}

# Ticketing / event platforms found around Brussels (domain fragments) -------------------------
TICKET_PLATFORMS = {
    "utick.net": "utick", "ticketmatic.com": "ticketmatic", "billetweb.fr": "billetweb",
    "eventbrite.": "eventbrite", "weezevent.com": "weezevent", "yurplan.com": "yurplan",
    "helloasso.com": "helloasso", "ticketmaster.": "ticketmaster", "tickettailor.com": "tickettailor",
    "eventix.": "eventix", "ticketgang.com": "ticketgang", "xceed.me": "xceed", "ra.co": "resident-advisor",
    "meetup.com": "meetup", "fienta.com": "fienta", "pretix.eu": "pretix", "ticketscript": "ticketscript",
    "uitdatabank.be": "uitdatabank", "uitinvlaanderen.be": "uitinvlaanderen", "lyveevents": "lyve",
    "secutix": "secutix", "reservation.mazette": "native-reservation", "lepointdevente": "lepointdevente",
    "tickets.": "tickets-subdomain", "shop.": "shop-subdomain",
}
SOCIAL_DOMAINS = {
    "instagram.com": "instagram", "facebook.com": "facebook", "fb.com": "facebook",
    "x.com": "x", "twitter.com": "x", "linkedin.com": "linkedin", "youtube.com": "youtube",
    "vimeo.com": "vimeo", "mastodon.": "mastodon", "bsky.app": "bluesky", "substack.com": "substack",
    "linktr.ee": "linktree", "beacons.ai": "linktree", "tiktok.com": "tiktok", "t.me": "telegram",
    "whatsapp.com": "whatsapp", "flickr.com": "flickr", "soundcloud.com": "soundcloud",
}
# Aggregators that are worth watching because small venues post there (verify per site) ---------
AGGREGATOR_HINTS = [
    "agenda.brussels", "quefaire.be", "spectable.be", "uitinvlaanderen.be", "bruzz.be/agenda",
    "brusselstimes.com/art-culture", "cityzeum.com", "allevents.in", "eventbrite", "meetup.com",
    "pointculture.be", "ra.co", "saintgillesculture.brussels", "culture.ixelles.be", "bx1.be",
]

# Page-builder / calendar-plugin fingerprints (substring in raw HTML -> recommended method) ------
FINGERPRINTS = {
    "tribe-events": "wordpress (The Events Calendar REST: /wp-json/tribe/events/v1/events)",
    "tribe_events": "wordpress (The Events Calendar)",
    "mec-event": "wordpress (Modern Events Calendar: look for ?feed / ical export)",
    "eventon": "wordpress (EventON)",
    "wp-content/plugins/the-events-calendar": "wordpress (The Events Calendar)",
    "wp-json": "wordpress (try /wp-json/wp/v2/ custom post types: event, evenement, spectacle)",
    "squarespace": "squarespace (append ?format=json to listing URL)",
    "static.squarespace.com": "squarespace (append ?format=json)",
    "wixstatic.com": "wix (events often in app JSON / needs render)",
    "webflow": "webflow (static; selector recipe)",
    "__next_data__": "next.js (read <script id=__NEXT_DATA__> JSON)",
    "__nuxt__": "nuxt (read window.__NUXT__ JSON)",
    "data-reactroot": "react (render or find XHR)",
    "drupal": "drupal (selector recipe; /rss.xml often exists)",
    "typo3": "typo3 (selector recipe)",
    "joomla": "joomla (selector recipe)",
    "calendar.google.com": "embedded google calendar (use its public ics link)",
}
