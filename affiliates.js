/* ---------------------------------------------------------------------------
   Affiliate wiring. ONE place to manage every partner programme.

   HOW IT WORKS
   A link anywhere on the site written as

     <a data-aff="parkos" href="https://www.parkos.com/netherlands/schiphol-airport/">Compare Schiphol parking</a>

   already works today as a plain link to the partner. The moment you paste the
   programme's tracking id below, this script appends that programme's tracking
   parameter to every matching link, across the whole site, with no page edits.
   Links are always given rel="sponsored nofollow noopener" and target="_blank",
   which is what Google requires for paid links, and the footer carries the
   site-wide disclosure.

   TO ACTIVATE A PROGRAMME
     1. Apply at the signup url below and wait for approval (usually 1-5 days).
     2. Copy the publisher/campaign id the network gives you.
     3. Paste it into `id` for that programme. Nothing else to change.
   Leave `id` empty and the link simply points at the partner, untracked and
   unpaid, so the site stays honest and functional while applications are open.

   PROGRAMMES, WHAT THEY PAY, WHERE THEY ARE USED
   ---------------------------------------------------------------------------
   parkos      Airport parking comparison. TradeTracker NL, about 8% of the
               booking value, 15-day cookie. Used on the Schiphol and
               long-term parking pages.
               Signup: https://eu.parkos.com/affiliate-signup.html
               Network: https://tradetracker.com/publisher/  (search "Parkos")
               Param: TradeTracker rewrites the url, so once approved paste the
               affiliate id and set `mode:'tt'` to use their deeplink format.

   parclick    City parking pre-booking across Europe, strong in NL city
               centres. Own affiliate programme, recurring commission when the
               same customer rebooks. Rate is agreed per publisher.
               Signup: https://parclick.com/partnership/affiliate

   mobian      Dutch city parking pre-booking; this is the platform the
               competitor parkeren-amsterdam.com monetises with. Partner
               programme by direct agreement, campaign id in the url.
               Contact: https://www.mobian.global/  (partnerships)

   travelcard  Charge card and fuel card for the Netherlands and Europe, over
               300,000 charge points. Awin, pays per approved application, so
               it converts on a sign-up rather than a session.
               Signup: https://ui.awin.com/merchant-profile/25584 (join via Awin)

   easypark    Street parking app, referral programme.
   parkmobile  Street parking app (Yellowbrick), referral programme.
   parkbee     Pre-booked city garages.
   bol         bol.com Partner, for parking discs and EV cables.

   NOTE No charge point operator (Vattenfall, Allego, Shell Recharge, Fastned)
   pays a publisher commission for a charging session, and Tesla's referral
   scheme is owner-to-owner for car purchases, not a publisher programme. The
   money in charging is in charge cards and subscriptions, which is why
   travelcard is the charging programme wired up here.
--------------------------------------------------------------------------- */
(function () {
  // >>> PASTE YOUR IDs HERE, ONE LINE EACH, THEN SAVE AND PUSH <<<
  var AFF = {
    parkos:     { id: '', param: 'campaign' },
    parclick:   { id: '', param: 'utm_source', extra: { utm_medium: 'affiliate' } },
    mobian:     { id: '', param: 'campaign',   extra: { utm_source: 'parkingnetherlands.com', utm_medium: 'referral' } },
    travelcard: { id: '', param: 'awc' },
    easypark:   { id: '', param: 'ref' },
    parkmobile: { id: '', param: 'ref' },
    parkbee:    { id: '', param: 'ref' },
    bol:        { id: '', param: 'Referrer' }
  };

  function decorate(a) {
    var cfg = AFF[a.getAttribute('data-aff')];
    if (!cfg) return;
    // compliance and UX, whether or not an id is set
    a.setAttribute('target', '_blank');
    var rel = a.getAttribute('rel') || '';
    ['sponsored', 'nofollow', 'noopener'].forEach(function (r) { if (rel.indexOf(r) === -1) rel += ' ' + r; });
    a.setAttribute('rel', rel.trim());
    a.addEventListener('click', function () {
      if (window.track) window.track('affiliate_click', { programme: a.getAttribute('data-aff'), live: !!cfg.id, page: location.pathname });
    });
    if (!cfg.id || !a.href) return;
    try {
      var u = new URL(a.href);
      if (!u.searchParams.get(cfg.param)) u.searchParams.set(cfg.param, cfg.id);
      if (cfg.extra) Object.keys(cfg.extra).forEach(function (k) { if (!u.searchParams.get(k)) u.searchParams.set(k, cfg.extra[k]); });
      a.href = u.toString();
    } catch (e) { /* leave the href untouched if it will not parse */ }
  }

  function run() { Array.prototype.forEach.call(document.querySelectorAll('a[data-aff]'), decorate); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
