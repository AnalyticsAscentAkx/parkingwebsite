/* ---------------------------------------------------------------------------
   Affiliate link wiring — ONE place to manage every affiliate program.

   HOW IT WORKS
   Any link on the site written as e.g.
     <a data-aff="parkos" href="https://www.parkos.com/schiphol-airport-parking/"
        target="_blank" rel="sponsored nofollow noopener">Book Schiphol parking</a>
   works as a plain link today. Once you paste your affiliate ID below, this
   script appends the program's tracking parameter to every matching link
   automatically — no page edits needed.

   TO ACTIVATE: sign up for the program, then fill in the `id` string below.
   Leave it '' and the link just points to the normal destination.

   Every affiliate link keeps rel="sponsored nofollow" (Google's requirement for
   paid/affiliate links) and opens in a new tab.
--------------------------------------------------------------------------- */
(function () {
  // >>> PASTE YOUR AFFILIATE IDs HERE <<<
  var AFF = {
    parkos:     { id: '', param: 'campaign' },   // Parkos / airport parking
    bol:        { id: '', param: 'Referrer'  },  // bol.com Partner (parkeerschijf etc.)
    easypark:   { id: '', param: 'ref'       },  // EasyPark referral
    parkmobile: { id: '', param: 'ref'       },  // Parkmobile / Yellowbrick referral
    parkbee:    { id: '', param: 'ref'       }   // ParkBee pre-book
  };

  function decorate(a) {
    var key = a.getAttribute('data-aff');
    var cfg = AFF[key];
    if (!cfg) return;
    // compliance + UX, whether or not an id is set
    a.setAttribute('target', '_blank');
    var rel = (a.getAttribute('rel') || '');
    ['sponsored', 'nofollow', 'noopener'].forEach(function (r) {
      if (rel.indexOf(r) === -1) rel += ' ' + r;
    });
    a.setAttribute('rel', rel.trim());
    // add tracking param only once we have an id
    if (cfg.id && a.href) {
      try {
        var u = new URL(a.href);
        if (!u.searchParams.get(cfg.param)) {
          u.searchParams.set(cfg.param, cfg.id);
          a.href = u.toString();
        }
      } catch (e) { /* leave href untouched on parse failure */ }
    }
  }

  function run() { document.querySelectorAll('a[data-aff]').forEach(decorate); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else { run(); }
})();
