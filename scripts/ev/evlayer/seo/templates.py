"""Shared chrome. Kept byte-identical to the rest of the site so an EV page
never reads as bolted on."""
import html
import re
import unicodedata

from .. import config

ADSENSE = "ca-pub-2889604222343187"


def slug(text: str) -> str:
    """Lowercase, ASCII-folded, hyphenated. IDs never appear in visible URL text."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = t.encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)[:70]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


NAV = """<nav class="nav"><div class="nav-in">
<a href="/" class="logo"><div class="logo-mark"></div><span class="logo-text">Parking Netherlands</span></a>
<ul class="nav-links" id="navLinks">
  <li class="has-drop"><a href="/all-cities">Cities</a>
    <div class="drop">
      <a href="/amsterdam">Amsterdam</a><a href="/rotterdam">Rotterdam</a><a href="/the-hague">The Hague</a><a href="/utrecht">Utrecht</a><a href="/eindhoven">Eindhoven</a>
      <div class="drop-div"></div>
      <a href="/groningen">Groningen</a><a href="/haarlem">Haarlem</a><a href="/leiden">Leiden</a><a href="/delft">Delft</a><a href="/maastricht">Maastricht</a><a href="/breda">Breda</a>
      <div class="drop-div"></div>
      <a href="/all-cities">All cities</a>
    </div>
  </li>
  <li><a href="/search">Search</a></li>
  <li><a href="/map">Map</a></li>
  <li><a href="/ev-charging">Chargers</a></li>
  <li><a href="/schiphol">Schiphol</a></li>
  <li class="has-drop"><a href="/free-parking">Guides</a>
    <div class="drop">
      <a href="/free-parking">Free parking</a><a href="/street-parking">Street parking</a><a href="/long-term-parking">Long-term parking</a><a href="/parking-tips-netherlands">Parking tips</a><a href="/ev-parking">EV charging</a><a href="/parking-apps">Parking apps</a><a href="/parking-fines">Fines guide</a>
      <div class="drop-div"></div>
      <a href="/about">About this site</a>
    </div>
  </li>
  <li><a href="/blog">Blog</a></li>
  <li><a href="https://www.paypal.com/qrcodes/managed/f2e1981d-0f0e-43ca-862f-4393ef678450?utm_source=consweb_more" class="nav-cta" target="_blank" rel="noopener">Support</a></li>
</ul>
<button class="menu-btn" onclick="document.getElementById('navLinks').classList.toggle('open')" aria-label="Menu">&#9776;</button>
</div></nav>"""

# RDW publishes as CC-0 but its terms forbid naming RDW as the source, so the
# parking half is credited to nobody. NDW must be credited. The two rules run
# in opposite directions, which is exactly why this string is built once here.
FOOTER = """<footer class="footer"><div class="wrap">
  <div class="foot-grid">
    <div class="foot-brand">
      <a href="/" class="logo"><div class="logo-mark"></div><span class="logo-text">Parking Netherlands</span></a>
      <p>Independent parking comparison for the Netherlands. Official data, no bookings pushed, no paywall.</p>
      <div class="credit">Built &amp; maintained by <a href="https://analyticascent.com" target="_blank" rel="noopener">Analytics Ascent</a></div>
    </div>
    <div class="foot-col"><h4>Cities</h4><a href="/amsterdam">Amsterdam</a><a href="/rotterdam">Rotterdam</a><a href="/the-hague">The Hague</a><a href="/utrecht">Utrecht</a><a href="/schiphol">Schiphol</a><a href="/all-cities">All cities</a></div>
    <div class="foot-col"><h4>Tools</h4><a href="/search">Parking search</a><a href="/map">Interactive map</a><a href="/ev-charging">Charger reliability</a><a href="/garage/">Garage directory</a></div>
    <div class="foot-col"><h4>Guides</h4><a href="/free-parking">Free parking</a><a href="/parking-apps">Parking apps</a><a href="/parking-fines">Fines guide</a><a href="/ev-parking">EV parking</a><a href="/about">About</a></div>
  </div>
  <div class="foot-bottom">
    <span>&copy; 2026 Parking Netherlands - an <a href="https://analyticascent.com" target="_blank" rel="noopener" style="color:var(--sig)">Analytics Ascent</a> project</span>
    <span class="foot-pill">LAADPUNTDATA: NDW / DOT-NL</span>
    <span>Not affiliated with any operator</span>
  </div>
</div></footer>"""


def head(title: str, description: str, canonical: str, jsonld: str = "",
         indexable: bool = True, extra_css: str = "") -> str:
    robots = "index, follow" if indexable else "noindex, follow"
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE}" crossorigin="anonymous"></script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/site.css">
<link rel="stylesheet" href="/ev.css">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/svg+xml" href="/favicon.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:image" content="{config.SITE_URL}/og-image.png">
<meta name="robots" content="{robots}">
{ld}{extra_css}
</head>
<body>
{NAV}"""


TAIL = f"""{FOOTER}
</body>
</html>"""
