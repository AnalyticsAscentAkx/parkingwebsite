/* Site analytics. Silent until an id is filled in below.

   Two options, either or both:
   - Cloudflare Web Analytics: cookieless, no consent banner needed, free
     with the Pages site. Dashboard -> Analytics & Logs -> Web Analytics ->
     add site -> copy the token into CF_TOKEN.
   - Google Analytics 4: fuller funnels and custom events. Create a GA4
     property, copy the "G-XXXXXXX" measurement id into GA4_ID. Cookies
     are only set after consent (Consent Mode v2, tied to the AdSense
     consent message).

   The map calls window.track(name, params) at the moments that matter:
   search, near_me, mode (parking/chargers), select (pin or row),
   directions, filter, sort. Everything else is page views. */
(function () {
  /* Analytics Ascent property, web stream "Website 2026" (stream 15873454280),
     created 2026-09-29 because the original stream's tag was never served by
     Google (404). Keep this id; never swap in an id from another account. */
  var GA4_ID = 'G-8HSXXMY89K';
  var TAG_LOADER_ID = '';   // set only if Google again serves the loader under a different primary id
  var CF_TOKEN = '';      // e.g. '0123456789abcdef0123456789abcdef'

  var queue = [];
  window.track = function (name, params) { queue.push([name, params || {}]); };

  if (CF_TOKEN) {
    var cf = document.createElement('script');
    cf.defer = true;
    cf.src = 'https://static.cloudflareinsights.com/beacon.min.js';
    cf.setAttribute('data-cf-beacon', JSON.stringify({ token: CF_TOKEN }));
    document.head.appendChild(cf);
  }

  if (GA4_ID) {
    window.dataLayer = window.dataLayer || [];
    function gtag() { window.dataLayer.push(arguments); }
    window.gtag = gtag;
    // No cookies until the visitor says yes; the AdSense consent message updates this.
    gtag('consent', 'default', {
      ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
      analytics_storage: 'denied', wait_for_update: 500
    });
    gtag('js', new Date());
    gtag('config', GA4_ID, { anonymize_ip: true, send_page_view: true });
    var g = document.createElement('script');
    g.async = true;
    g.src = 'https://www.googletagmanager.com/gtag/js?id=' + (TAG_LOADER_ID || GA4_ID);
    document.head.appendChild(g);
    window.track = function (name, params) { gtag('event', name, params || {}); };
    queue.forEach(function (q) { window.track(q[0], q[1]); });
    queue = [];

    /* ---- Consent.

       Without this the tag denied its own consent forever and nothing ever
       granted it: measured over 3 to 28 September 2026, Search Console
       counted 58 clicks and GA4 recorded 1 session. Analytics saw 2% of real
       visits. Cookieless pings alone only feed Google's modelling, which
       needs roughly a thousand daily users before it reports anything, and
       this site gets about two clicks a day.

       Refusing is exactly as easy as accepting, which the ePrivacy rules
       require and which is also the only honest way to ask. The choice is
       remembered for six months. Cloudflare Web Analytics keeps counting
       either way: it is cookieless and needs no permission, so declining
       costs the site nothing it truly needs. ---- */
    var KEY = 'pn_consent_v1', MAXAGE = 15552000000;  // six months

    function apply(granted) {
      gtag('consent', 'update', {
        analytics_storage: granted ? 'granted' : 'denied',
        ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied'
      });
    }

    function remember(granted) {
      try {
        localStorage.setItem(KEY, JSON.stringify({ g: granted, t: Date.now() }));
      } catch (e) {}
    }

    var saved = null;
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) {
        var o = JSON.parse(raw);
        if (o && typeof o.g === 'boolean' && Date.now() - (o.t || 0) < MAXAGE) saved = o.g;
      }
    } catch (e) {}

    if (saved !== null) { apply(saved); }
    else { document.addEventListener('DOMContentLoaded', ask); }

    function ask() {
      var b = document.createElement('div');
      b.className = 'pn-consent';
      b.setAttribute('role', 'dialog');
      b.setAttribute('aria-label', 'Cookie choice');
      b.innerHTML =
        '<p>We count visits with a cookieless tool that needs no permission. '
        + 'May we also use Google Analytics, which sets a cookie, to see which '
        + 'pages actually help you? <a href="/privacy">How we handle data</a>.</p>'
        + '<div class="pn-consent-btns">'
        + '<button type="button" data-a="no">No thanks</button>'
        + '<button type="button" data-a="yes" class="pn-yes">Allow</button>'
        + '</div>';
      b.addEventListener('click', function (e) {
        var t = e.target.closest('button[data-a]');
        if (!t) return;
        var yes = t.dataset.a === 'yes';
        apply(yes); remember(yes);
        b.classList.add('pn-consent-out');
        setTimeout(function () { b.remove(); }, 260);
      });
      document.body.appendChild(b);
      requestAnimationFrame(function () { b.classList.add('pn-consent-in'); });
    }
  }
})();
