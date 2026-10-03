# Data-licence compliance report

Generated 2026-10-03 by scripts/compliance/audit.py

**0 hard findings** across 0 files, **4217 warnings** across 1463 files.

## Sources in use

- **RDW open data (Nationaal Parkeer Register tariffs, garage register)**: 1371 file(s). Licence: Creative Commons Zero (CC0). Terms: https://www.rdw.nl/over-rdw/dienstverlening/open-data/bijsluiter
- **NDW / DOT-NL charging point register (opendata.ndw.nu)**: 6 file(s). Licence: CC0 per ndw.nu/copyright ('tenzij anders vermeld'); attribution kept. Terms: https://www.ndw.nu/copyright
- **OpenStreetMap public tile server (tile.openstreetmap.org)**: 1298 file(s). Licence: Tiles: OSMF Tile Usage Policy; data: ODbL. Terms: https://operations.osmfoundation.org/policies/tiles/
- **Photon geocoder (photon.komoot.io), OSM data**: 2 file(s). Licence: Fair use; underlying data ODbL (attribution to OpenStreetMap). Terms: https://photon.komoot.io/
- **Open Charge Map API (api.openchargemap.io)**: 1 file(s). Licence: Data CC BY-SA 4.0 (per OCM; terms page is JS-rendered, re-verify by hand). Terms: https://openchargemap.org/site/about/terms
- **CBS / Statistics Netherlands**: 62 file(s). Licence: CC BY 4.0. Terms: https://www.cbs.nl/en-gb/about-us/website/copyright
- **Stad Gent open data (data.stad.gent real-time parking)**: 1 file(s). Licence: UNVERIFIED: dataset pages state their own licence (usually Modellicentie Gratis Hergebruik / CC0). Terms: https://data.stad.gent/
- **PDOK Locatieserver (Kadaster) address and postcode search**: 1 file(s). Licence: Open data (BAG, CC0); PDOK asks for fair use and attribution. Terms: https://www.pdok.nl/voorwaarden
- **Google AdSense on EU visitors: consent + privacy notice (AVG/ePrivacy, Google EU user consent policy)**: 1458 file(s). Licence: policy. Terms: https://www.google.com/about/company/user-consent-policy/
- **Affiliate links must be disclosed (Reclamecode Social Media & Influencer Marketing, Google rel=sponsored)**: 1461 file(s). Licence: policy. Terms: https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links
- **Google Analytics 4 (Consent Mode v2: no cookies before consent)**: 1 file(s). Licence: policy. Terms: https://support.google.com/analytics/answer/9976101
- **Google Fonts loaded from Google servers (IP transfer; German courts have fined this under GDPR)**: 1460 file(s). Licence: policy. Terms: https://developers.google.com/fonts/faq/privacy

## Findings

### [WARN] adsense_consent: confirm the GDPR consent message is PUBLISHED in AdSense > Privacy & messaging; without it personalised ads in the EEA breach Google's policy and the AVG
1458 file(s): 50five-storing.html, about.html, all-cities.html, allego-storing.html, amsterdam-cheap-parking.html, amsterdam-parking-tourist.html, amsterdam-pr-guide.html, amsterdam.html, belgium-parking.html, blog.html, bp-pulse-storing.html, breda.html ... +1446 more
> e.g. `never-pay-parking-amsterdam.html`: …async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2889604222343187" crossorigin="anonymous">…

### [WARN] google_fonts: fonts are fetched from Google on every visit; self-hosting removes the transfer
1460 file(s): 404.html, 50five-storing.html, about.html, all-cities.html, allego-storing.html, amsterdam-cheap-parking.html, amsterdam-parking-tourist.html, amsterdam-pr-guide.html, amsterdam.html, belgium-parking.html, blog.html, bp-pulse-storing.html ... +1448 more
> e.g. `never-pay-parking-amsterdam.html`: …ay-parking-amsterdam"> <link rel="preconnect" href="https://fonts.googleapis.com"> <link rel="preconnect" href="https://fonts.gstatic.com" c…

### [WARN] osm_tiles: site is ad-funded and serves 330+ map pages from the volunteer OSM tile server; the policy allows this but can cut access without notice. Consider CARTO basemaps or self-hosted tiles.
1298 file(s): belgium-parking.html, de/garage/013-tivoli-tilburg.html, de/garage/albert-cuyp-amsterdam.html, de/garage/amc-p2-amsterdam.html, de/garage/amphia-ziekenhuis-locatie-langendijk-breda.html, de/garage/amphia-ziekenhuis-locatie-molengracht-breda.html, de/garage/amsterdam-centrum-amsterdam.html, de/garage/amsterdamse-bos-hoofdentree-amsterdam.html, de/garage/antarctica-amsterdam.html, de/garage/artis-amsterdam.html, de/garage/badhuisstraat-the-hague.html, de/garage/benthuizerstraat-rotterdam.html ... +1286 more
> e.g. `map.html`: …false}).setView([52.20, 5.30], 8); L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution:'&copy; <a href="https://…

### [WARN] photon: geocoder appears to fire on every keystroke without a debounce; be fair to the free service (>=300 ms debounce, min 3 chars)
1 file(s): ev-map.js
> e.g. `ev-map.js`: …l.addEventListener('change', syncWindow); $('#evKwh').addEventListener('input', repriceAll); updateSession(); if (narrow()) { var d = $('#evWin…

## Terms pages

- rdw: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://www.rdw.nl/over-rdw/dienstverlening/open-data/bijsluiter)
- ndw: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://www.ndw.nu/copyright)
- osm_tiles: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://operations.osmfoundation.org/policies/tiles/)
- photon: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://photon.komoot.io/)
- ocm: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://openchargemap.org/site/about/terms)
- cbs: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain (_ssl.c:1000)> (https://www.cbs.nl/en-gb/about-us/website/copyright)
- gent: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://data.stad.gent/)
- pdok: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://www.pdok.nl/voorwaarden)
- adsense_consent: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://www.google.com/about/company/user-consent-policy/)
- affiliate_disclosure: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links)
- ga4: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://support.google.com/analytics/answer/9976101)
- google_fonts: fetch failed: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)> (https://developers.google.com/fonts/faq/privacy)

## What each source allows

- **rdw**: 2026-09-28. Bijsluiter: 'Als onderdeel van Creative Commons Zero is het bij hergebruik niet toegestaan te vermelden dat de gegevens afkomstig zijn van de RDW en is het niet toegestaan het logo of de huisstijl van de RDW te gebruiken in de ontwikkelde toepassingen.' Naming RDW as the source is FORBIDDEN, as is any RDW logo or house style. Describing the data as 'the national parking register (NPR)' without naming RDW is fine.
- **ndw**: 2026-09-28. 'Tenzij anders vermeld is op de inhoud van deze website de Creative Commons Zero (CC0) verklaring van toepassing.' No dataset-specific licence found on opendata.ndw.nu or docs.ndw.nu/faq/DOT-NL. We attribute NDW / DOT-NL anyway, which is safe under CC0 and required under CC-BY. Images are NOT CC0.
- **osm_tiles**: 2026-09-28. Attribution must be '(c) OpenStreetMap contributors' visibly on the map; pages must send a valid Referer (no restrictive Referrer-Policy); never send no-cache; bulk/offline use forbidden; commercial use tolerated but 'access may be withdrawn at any point'.
- **photon**: 2026-09-28. 'You can use the API for your project, but please be fair - extensive usage will be throttled. We do not guarantee for the availability.' OSM data needs '(c) OpenStreetMap contributors' near the results.
- **ocm**: 2026-09-28. Terms page could not be fetched as text (single-page app). OCM publishes its data under CC BY-SA 4.0: attribute 'Open Charge Map' with a link; any redistributed derivative must stay share-alike. API key must be sent.
- **cbs**: 2026-09-28. CC BY 4.0; 'Statistics Netherlands is cited as the source'; must not imply CBS endorses the derivative work; logos and photos excluded.
- **gent**: 2026-09-28. The portal's general terms page only covers the website ('persoonlijke en niet-commerciele doeleinden, mits bronvermelding'); per-dataset licences were not fetchable. Attribution to Stad Gent is required under every plausible reading, so it is enforced here. TODO: open the parking dataset page and record its licence.
- **pdok**: 2026-09-28. Free, keyless, CORS-enabled geocoder on Dutch government data. Used only on visitor-triggered searches (Enter or Go), never per keystroke. Credited in the map footer.
