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
  }
})();
