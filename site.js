/* Shared motion and small interactions for every page.
   Progressive: without JavaScript, or with "reduce motion" on, nothing is
   ever hidden and nothing moves. The map pages are left alone. */
(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var nav = document.querySelector('nav.nav');

  /* Header gains a shadow once the page has scrolled under it. */
  if (nav) {
    var onScroll = function () { nav.classList.toggle('is-scrolled', window.scrollY > 8); };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  if (reduce || !('IntersectionObserver' in window)) return;
  if (document.querySelector('#evApp, #evmap, .leaflet-container')) return;   /* live map pages */

  /* 1. Sections and cards ease in as they enter the viewport, siblings in a
        short stagger. The class is added here, so pages render fully
        without this script. */
  var SEL = '.sec > .ct > *, .sec > .wrap > *, .card, .tbl-wrap, .tw, .glist-wrap, .pi-stat, .pi-hero > *, ' +
            '.abox, .faq-item, .city-card, .pk, .prose > *, .gwrap > h2, .gwrap > p, .gwrap > .tbl-wrap, ' +
            '.gwrap > .card, .gwrap > header, .pi-wrap > h2, .pi-wrap > p, .pi-wrap > .tbl-wrap, .pi-wrap > pre, article > *';
  var els = [].slice.call(document.querySelectorAll(SEL)).filter(function (el) {
    if (el.closest('nav, footer, .hero, .rv')) return false;          /* no nesting, no chrome */
    if (el.querySelector('#gmap, #map, canvas, iframe')) return false;   /* maps and embeds keep their geometry */
    var r = el.getBoundingClientRect();
    return r.height > 0 && r.height < 1600;
  });
  if (els.length > 500) return;

  var byParent = new Map();
  els.forEach(function (el) {
    var n = byParent.get(el.parentNode) || 0;
    byParent.set(el.parentNode, n + 1);
    el.style.setProperty('--rv-d', Math.min(n, 5) * 70 + 'ms');
    el.classList.add('rv');
  });

  function settle(el) {
    el.classList.remove('rv', 'is-in');
    el.style.removeProperty('--rv-d');
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var el = e.target;
      io.unobserve(el);
      el.classList.add('is-in');
      setTimeout(function () { settle(el); }, 1100);
      countUp(el);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
  els.forEach(function (el) { io.observe(el); });
  /* Safety net: a few seconds after load, anything still unseen is revealed
     anyway, so a stalled observer or an unusual viewport never hides text. */
  window.addEventListener('load', function () {
    setTimeout(function () {
      els.forEach(function (el) { if (el.classList.contains('rv') && !el.classList.contains('is-in')) { io.unobserve(el); el.classList.add('is-in'); setTimeout(function () { settle(el); }, 1100); } });
    }, 3500);
  });

  /* 2. Big numbers in stat tiles count up the first time they are seen. */
  var NUM = '.pi-stat b, .hstat .n, .qbv, .ev-figure b, .city-card .lead .n, .counter';
  function countUp(scope) {
    var targets = scope.matches(NUM) ? [scope] : [].slice.call(scope.querySelectorAll(NUM));
    targets.forEach(function (el) {
      if (el.dataset.counted) return;
      el.dataset.counted = '1';
      var txt = el.textContent.trim();
      var m = /^([^\d]*)(\d[\d.,]*)(.*)$/.exec(txt);
      if (!m || txt.length > 14) return;
      var raw = m[2], prefix = m[1], suffix = m[3];
      var thousands = /\d,\d{3}(\D|$)/.test(raw) && !/,\d{1,2}$/.test(raw);
      var dec = 0, val;
      if (thousands) { val = parseFloat(raw.replace(/,/g, '')); }
      else if (/,\d{1,2}$/.test(raw)) { dec = raw.split(',')[1].length; val = parseFloat(raw.replace(',', '.')); }
      else { val = parseFloat(raw); var d = raw.split('.')[1]; dec = d ? d.length : 0; }
      if (isNaN(val)) return;
      var comma = !thousands && /,\d{1,2}$/.test(raw);
      var t0 = null, dur = 900;
      function fmt(v) {
        var s = v.toFixed(dec);
        if (thousands) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        if (comma) s = s.replace('.', ',');
        return prefix + s + suffix;
      }
      function step(ts) {
        if (t0 === null) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur), e = 1 - Math.pow(1 - p, 3);
        el.textContent = fmt(val * e);
        if (p < 1) requestAnimationFrame(step); else el.textContent = txt;
      }
      requestAnimationFrame(step);
    });
  }
})();
