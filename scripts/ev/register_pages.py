#!/usr/bin/env python3
"""After laadpaal.build(): sitemap entries, clean-URL redirects, and the link
blocks on /ev-charging for every generated Dutch page. Idempotent."""
import datetime, glob, re, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
today = datetime.date.today().isoformat()
cities = sorted(p.stem for p in ROOT.glob('laadpaal-*.html'))
ops = sorted(p.stem for p in ROOT.glob('*-storing.html'))
sm = (ROOT / 'sitemap.xml').read_text(); rd = (ROOT / '_redirects').read_text(); added = 0
for p in cities + ops:
    if f'/{p}</loc>' not in sm:
        sm = sm.replace('</urlset>', f'  <url><loc>https://parkingnetherlands.com/{p}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>\n</urlset>'); added += 1
    if f'/{p}.html' not in rd:
        rd += f'/{p}.html      /{p}      301\n'
(ROOT / 'sitemap.xml').write_text(sm); (ROOT / '_redirects').write_text(rd)
def name(p):
    t = p.replace('laadpaal-', '').replace('-storing', '').replace('-', ' ').title()
    return t.replace('S Hertogenbosch', "'s-Hertogenbosch").replace('Aan Den', 'aan den').replace('Ijssel', 'IJssel').replace('Bv', 'BV')
block = ('<!-- nl-pages -->\n  <h3 id="per-stad">Laadpalen per stad (Nederlands)</h3>\n  <p>Prijs per kWh per exploitant, storingen en snelladers, per stad:</p>\n  <div class="ev-citylinks">'
         + ''.join(f'<a href="/{p}" hreflang="nl">{name(p)}</a>' for p in cities) + '</div>\n'
         '  <h3 id="storingen">Storingen per exploitant (Nederlands)</h3>\n  <div class="ev-citylinks">'
         + ''.join(f'<a href="/{p}" hreflang="nl">{name(p)} storing</a>' for p in ops) + '</div>\n<!-- /nl-pages -->\n')
h = (ROOT / 'ev-charging.html').read_text()
if '<!-- nl-pages -->' in h:
    h = re.sub(r'<!-- nl-pages -->.*?<!-- /nl-pages -->\n', block, h, flags=re.S)
else:
    h = re.sub(r'\n  <h3 id="per-stad">.*?  <p>Parking guides for the same cities:</p>', '\n' + block + '  <p>Parking guides for the same cities:</p>', h, count=1, flags=re.S)
(ROOT / 'ev-charging.html').write_text(h)
print(f"registered {len(cities)} city pages, {len(ops)} operator pages; sitemap +{added}, urls {sm.count('<url>')}")
