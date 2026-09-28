"""Registry of every external data source the site uses, with the licence
terms that bind us and the checks that prove we honour them.

Each entry is a plain dict so the audit stays readable by a non-programmer:

  key          short id
  name         what it is
  licence      licence name as published
  terms_url    where the terms live (fetched + hashed by `audit.py --fetch`)
  verified     date a human read the terms, plus the clause that matters
  uses         regex; a page "uses" the source when its HTML/JS matches
  require      list of (regex, message) that MUST appear on every using page
  forbid       list of (regex, message) that must NOT appear anywhere public
  advise       list of (regex, message) that yield a WARNING, not a failure

Severity: a failed `require` or a matched `forbid` is a HARD finding and
blocks the daily auto-publish. `advise` is reported only.

Where a licence could not be confirmed from a fetchable page the entry says
so in `verified`, and the check is written to be safe under either reading.
"""

SOURCES = [
    {
        "key": "rdw",
        "name": "RDW open data (Nationaal Parkeer Register tariffs, garage register)",
        "licence": "Creative Commons Zero (CC0)",
        "terms_url": "https://www.rdw.nl/over-rdw/dienstverlening/open-data/bijsluiter",
        "verified": (
            "2026-09-28. Bijsluiter: 'Als onderdeel van Creative Commons Zero is het bij "
            "hergebruik niet toegestaan te vermelden dat de gegevens afkomstig zijn van de "
            "RDW en is het niet toegestaan het logo of de huisstijl van de RDW te gebruiken "
            "in de ontwikkelde toepassingen.' Naming RDW as the source is FORBIDDEN, as is "
            "any RDW logo or house style. Describing the data as 'the national parking "
            "register (NPR)' without naming RDW is fine."
        ),
        # Every page that shows tariff/garage data derived from the register.
        "uses": r"rdw-data\.js|RDW_DATA|npropendata|opendata\.rdw\.nl|national parking register|NPR\b",
        "require": [],
        "forbid": [
            # Any public statement naming RDW. Code identifiers are exempt (see IDENT_ALLOW).
            (r"(?-i:\bRDW\b)", "names RDW as the data source (forbidden by RDW's CC0 bijsluiter)"),
            (r"opendata\.rdw\.nl|npropendata\.rdw\.nl", "links to the RDW portal as the source"),
            (r'<img[^>]+src="[^"]*rdw[^"]*"', "uses an RDW image/logo"),
        ],
        "advise": [],
    },
    {
        "key": "ndw",
        "name": "NDW / DOT-NL charging point register (opendata.ndw.nu)",
        "licence": "CC0 per ndw.nu/copyright ('tenzij anders vermeld'); attribution kept",
        "terms_url": "https://www.ndw.nu/copyright",
        "verified": (
            "2026-09-28. 'Tenzij anders vermeld is op de inhoud van deze website de Creative "
            "Commons Zero (CC0) verklaring van toepassing.' No dataset-specific licence found "
            "on opendata.ndw.nu or docs.ndw.nu/faq/DOT-NL. We attribute NDW / DOT-NL anyway, "
            "which is safe under CC0 and required under CC-BY. Images are NOT CC0."
        ),
        "uses": r"ev-data/|ev-map\.js|opendata\.ndw\.nu",
        "require": [(r"NDW", "must credit NDW / DOT-NL for charging point data")],
        "forbid": [(r'<img[^>]+src="[^"]*ndw[^"]*"', "reuses an NDW image (images are excluded from CC0)")],
        "advise": [],
    },
    {
        "key": "osm_tiles",
        "name": "OpenStreetMap public tile server (tile.openstreetmap.org)",
        "licence": "Tiles: OSMF Tile Usage Policy; data: ODbL",
        "terms_url": "https://operations.osmfoundation.org/policies/tiles/",
        "verified": (
            "2026-09-28. Attribution must be '(c) OpenStreetMap contributors' visibly on the "
            "map; pages must send a valid Referer (no restrictive Referrer-Policy); never "
            "send no-cache; bulk/offline use forbidden; commercial use tolerated but 'access "
            "may be withdrawn at any point'."
        ),
        "uses": r"tile\.openstreetmap\.org",
        "require": [
            (r"OpenStreetMap</a>\s*contributors|OpenStreetMap contributors",
             "tile attribution must read '(c) OpenStreetMap contributors' (not 'OSM')"),
            (r"openstreetmap\.org/copyright", "attribution must link openstreetmap.org/copyright"),
        ],
        "forbid": [
            (r'<meta\s+name="referrer"\s+content="(no-referrer|same-origin)"',
             "blocks the Referer header the tile policy requires"),
            (r"Cache-Control['\"]?\s*[:=]\s*['\"]?no-cache", "sends no-cache to the tile server"),
        ],
        "advise": [
            (r"tile\.openstreetmap\.org",
             "site is ad-funded and serves 330+ map pages from the volunteer OSM tile server; "
             "the policy allows this but can cut access without notice. Consider CARTO "
             "basemaps or self-hosted tiles."),
        ],
    },
    {
        "key": "photon",
        "name": "Photon geocoder (photon.komoot.io), OSM data",
        "licence": "Fair use; underlying data ODbL (attribution to OpenStreetMap)",
        "terms_url": "https://photon.komoot.io/",
        "verified": (
            "2026-09-28. 'You can use the API for your project, but please be fair - extensive "
            "usage will be throttled. We do not guarantee for the availability.' OSM data "
            "needs '(c) OpenStreetMap contributors' near the results."
        ),
        "uses": r"photon\.komoot\.io",
        "require": [(r"OpenStreetMap", "geocoded results derive from OSM; attribution required")],
        "forbid": [],
        "advise": [
            (r"addEventListener\(['\"]input['\"][^)]*\)\s*(?![\s\S]{0,400}(setTimeout|debounce))",
             "geocoder appears to fire on every keystroke without a debounce; be fair to the "
             "free service (>=300 ms debounce, min 3 chars)"),
        ],
    },
    {
        "key": "ocm",
        "name": "Open Charge Map API (api.openchargemap.io)",
        "licence": "Data CC BY-SA 4.0 (per OCM; terms page is JS-rendered, re-verify by hand)",
        "terms_url": "https://openchargemap.org/site/about/terms",
        "verified": (
            "2026-09-28. Terms page could not be fetched as text (single-page app). OCM "
            "publishes its data under CC BY-SA 4.0: attribute 'Open Charge Map' with a link; "
            "any redistributed derivative must stay share-alike. API key must be sent."
        ),
        "uses": r"api\.openchargemap\.io",
        "require": [
            (r'href="https?://(www\.)?openchargemap\.org[^"]*"[^>]*>[^<]*Open ?Charge ?Map',
             "must credit 'Open Charge Map' with a link"),
            (r"api\.openchargemap\.io/[^'\"]*[?&]key=", "API calls must carry an API key"),
        ],
        "forbid": [],
        "advise": [],
    },
    {
        "key": "cbs",
        "name": "CBS / Statistics Netherlands",
        "licence": "CC BY 4.0",
        "terms_url": "https://www.cbs.nl/en-gb/about-us/website/copyright",
        "verified": (
            "2026-09-28. CC BY 4.0; 'Statistics Netherlands is cited as the source'; must not "
            "imply CBS endorses the derivative work; logos and photos excluded."
        ),
        "uses": r"\bCBS\b|Statistics Netherlands|opendata\.cbs\.nl",
        "require": [(r"Statistics Netherlands|\bCBS\b", "must cite CBS / Statistics Netherlands as source")],
        "forbid": [(r"endorsed by (CBS|Statistics Netherlands)|CBS[- ]approved", "implies CBS endorsement")],
        "advise": [],
    },
    {
        "key": "gent",
        "name": "Stad Gent open data (data.stad.gent real-time parking)",
        "licence": "UNVERIFIED: dataset pages state their own licence (usually Modellicentie Gratis Hergebruik / CC0)",
        "terms_url": "https://data.stad.gent/",
        "verified": (
            "2026-09-28. The portal's general terms page only covers the website ('persoonlijke "
            "en niet-commerciele doeleinden, mits bronvermelding'); per-dataset licences were "
            "not fetchable. Attribution to Stad Gent is required under every plausible reading, "
            "so it is enforced here. TODO: open the parking dataset page and record its licence."
        ),
        "uses": r"data\.stad\.gent",
        "require": [(r"Stad Gent|stad\.gent", "must credit Stad Gent for the live Ghent data")],
        "forbid": [],
        "advise": [],
    },
    {
        "key": "pdok",
        "name": "PDOK Locatieserver (Kadaster) address and postcode search",
        "licence": "Open data (BAG, CC0); PDOK asks for fair use and attribution",
        "terms_url": "https://www.pdok.nl/voorwaarden",
        "verified": (
            "2026-09-28. Free, keyless, CORS-enabled geocoder on Dutch government data. Used only "
            "on visitor-triggered searches (Enter or Go), never per keystroke. Credited in the map footer."
        ),
        "uses": r"api\.pdok\.nl",
        "require": [(r"PDOK|Kadaster", "must credit PDOK / Kadaster for address search")],
        "forbid": [],
        "advise": [],
    },
]

# Legal / regulatory checks that are not tied to a single data source.
POLICIES = [
    {
        "key": "adsense_consent",
        "name": "Google AdSense on EU visitors: consent + privacy notice (AVG/ePrivacy, Google EU user consent policy)",
        "terms_url": "https://www.google.com/about/company/user-consent-policy/",
        "uses": r"adsbygoogle",
        "require": [
            (r'href="/privacy"', "page must link a privacy/cookie notice"),
            (r"googlefc", "page must offer a 'privacy choices' control that reopens the consent message"),
        ],
        "forbid": [],
        "advise": [
            # The consent banner itself is switched on in the AdSense console (Privacy &
            # messaging) and is served through adsbygoogle.js, so it cannot be verified
            # from the source. Record the date it was published in state.json to silence.
            (r"adsbygoogle", "confirm the GDPR consent message is PUBLISHED in AdSense > Privacy & messaging; "
                             "without it personalised ads in the EEA breach Google's policy and the AVG"),
        ],
        "severity": "HARD",
    },
    {
        "key": "affiliate_disclosure",
        "name": "Affiliate links must be disclosed (Reclamecode Social Media & Influencer Marketing, Google rel=sponsored)",
        "terms_url": "https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links",
        "uses": r"affiliates\.js|rel=\"sponsored|parkos\.|bol\.com/|awin1\.com|tradedoubler",
        "require": [
            (r"commission|affiliate link|we may earn|compensat", "affiliate placement without a visible disclosure"),
        ],
        "forbid": [],
        "advise": [],
        "severity": "HARD",
    },
    {
        "key": "ga4",
        "name": "Google Analytics 4 (Consent Mode v2: no cookies before consent)",
        "terms_url": "https://support.google.com/analytics/answer/9976101",
        "uses": r"googletagmanager\.com/gtag|GA4_ID = 'G-",
        "require": [(r"consent'\s*,\s*'default'", "GA4 must set Consent Mode defaults to denied before config")],
        "forbid": [],
        "advise": [],
        "severity": "HARD",
    },
    {
        "key": "google_fonts",
        "name": "Google Fonts loaded from Google servers (IP transfer; German courts have fined this under GDPR)",
        "terms_url": "https://developers.google.com/fonts/faq/privacy",
        "uses": r"fonts\.googleapis\.com",
        "require": [],
        "forbid": [],
        "advise": [(r"fonts\.googleapis\.com", "fonts are fetched from Google on every visit; self-hosting removes the transfer")],
        "severity": "WARN",
    },
]

# Code identifiers that contain a source name but are not statements to users.
# They are stripped before the forbid patterns run.
IDENT_ALLOW = [
    r"RDW_DATA", r"addRDWMarkers", r"rdw-data\.js", r"layers\.rdw", r"vis\.rdw", r"['\"]rdw['\"]",
    # RDW named as the vehicle authority in the fines guide, not as a data source.
    r"Dutch RDW \(vehicle authority\)",
]

# Public files the audit reads. Everything else (scripts, data, git) is skipped.
PUBLIC_GLOBS = ["*.html", "**/*.html", "*.js", "sitemap.xml", "_redirects"]
SKIP_DIRS = {".git", "scripts", "node_modules", "ev-data", "data"}
