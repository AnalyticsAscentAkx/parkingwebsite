/* The site's motion and interaction layer, one file, five parts:
     1. reveal     sections, cards and tables ease in on scroll, siblings staggered
     2. count-up   big numbers in stat tiles count once when first seen
     3. header     shadow once the page has scrolled
     4. tables     click-to-sort, in-cell bars, best value marked, filter box
     5. sparks     the homepage motes, behind every hero surface
   Progressive: without JavaScript, or with "reduce motion" on, nothing is
   ever hidden and nothing moves. The live map pages keep parts 1 and 2 off. */
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

/* ---- Data tables: sort by clicking a header, in-cell bars, the best value
   in each column marked, a filter box on long tables, sticky headers.
   Applies to any table with a header row and at least four body rows.
   Purely additive: without this script the tables are plain and complete. */
(function () {
  var lang = (document.documentElement.lang || 'en').slice(0, 2);
  var LOW_IS_BEST = /price|prijs|tarief|tariff|cost|kost|rate|median|mediaan|fine|boete|€|eur|per (hour|uur|day|dag|24)|1 h|3 h|24 h|first hour|eerste uur|hours$|uur$|24 hours|24 uur|stay|\bfee\b/i;
  var SKIP = /^#$|^rank|^order|year|januar|^stay$|^city$|^stad$|^garage$|^name|^naam|^municipality|^gemeente|^operator|^zone|^area|^type|^tip|^pre-book|^hours$|^paid hours|^evening|window|venster|gebührenpflichtig|plage|^day$|^dag$|^tag$|^jour$|^parkhaus$|^parking$|heures/i;

  function parseNum(txt) {
    var t = txt.replace(/ /g, ' ').trim();
    if (!t || /^(n\/a|-|—|free|gratis|none|no |yes|ja|nee)/i.test(t)) return /^(free|gratis)$/i.test(t) ? 0 : null;
    var m = t.match(/-?[\d.,]+/); if (!m) return null;
    var s = m[0];
    if (lang === 'nl') { s = s.replace(/\./g, '').replace(',', '.'); }
    else { if (/,\d{1,2}$/.test(s) && !/\.\d/.test(s)) s = s.replace(',', '.'); else s = s.replace(/,/g, ''); }
    var v = parseFloat(s); return isNaN(v) ? null : v;
  }

  function enhance(table) {
    var thead = table.tHead, tbody = table.tBodies[0];
    if (!thead || !tbody || tbody.rows.length < 4) return;
    var ths = [].slice.call(thead.rows[thead.rows.length - 1].cells);
    var rows = [].slice.call(tbody.rows).filter(function (r) { return r.cells.length === ths.length; });
    if (rows.length < 4) return;
    table.classList.add('dt');

    var cols = ths.map(function (th, i) {
      var vals = rows.map(function (r) { return parseNum(r.cells[i].textContent); });
      var n = vals.filter(function (v) { return v !== null; }).length;
      var numeric = n >= Math.max(3, rows.length * 0.7);
      var label = th.textContent.trim();
      var skip = SKIP.test(label) || /^\d{4}$/.test(rows[0].cells[i].textContent.trim());
      return { i: i, numeric: numeric, skip: skip, lowBest: LOW_IS_BEST.test(label), vals: vals, label: label };
    });

    /* bars and best marks */
    cols.forEach(function (c) {
      if (!c.numeric || c.skip) return;
      var nums = c.vals.filter(function (v) { return v !== null; });
      var max = Math.max.apply(null, nums), min = Math.min.apply(null, nums);
      if (max === min) return;
      var best = c.lowBest ? min : max;
      rows.forEach(function (r, k) {
        var v = c.vals[k], td = r.cells[c.i];
        if (v === null) return;
        td.classList.add('dt-num');
        td.style.setProperty('--bar', (max > 0 ? Math.max(3, v / max * 100) : 0).toFixed(1) + '%');
        if (v === best) { td.classList.add('dt-best'); td.title = lang === 'nl' ? (c.lowBest ? 'Laagste in deze kolom' : 'Hoogste in deze kolom') : (c.lowBest ? 'Lowest in this column' : 'Highest in this column'); }
      });
    });

    /* sortable headers */
    var order = rows.slice();
    ths.forEach(function (th, i) {
      var c = cols[i];
      th.classList.add('dt-sort'); th.tabIndex = 0; th.setAttribute('role', 'button'); th.setAttribute('aria-sort', 'none');
      th.title = lang === 'nl' ? 'Klik om te sorteren' : 'Click to sort';
      var dir = 0;
      function sort() {
        dir = dir === 1 ? -1 : 1;
        ths.forEach(function (o) { if (o !== th) { o.setAttribute('aria-sort', 'none'); o.classList.remove('is-asc', 'is-desc'); } });
        th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        th.classList.toggle('is-asc', dir === 1); th.classList.toggle('is-desc', dir === -1);
        var sorted = order.slice().sort(function (a, b) {
          var ia = order.indexOf(a), ib = order.indexOf(b);
          if (c.numeric) {
            var va = c.vals[ia], vb = c.vals[ib];
            if (va === null && vb === null) return 0; if (va === null) return 1; if (vb === null) return -1;
            return (va - vb) * dir;
          }
          return a.cells[i].textContent.trim().localeCompare(b.cells[i].textContent.trim(), lang) * dir;
        });
        sorted.forEach(function (r) { tbody.appendChild(r); });
        if (window.track) window.track('table_sort', { column: c.label, dir: dir === 1 ? 'asc' : 'desc', page: location.pathname });
      }
      th.addEventListener('click', sort);
      th.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); } });
    });

    /* filter box on long tables */
    if (rows.length >= 12) {
      var wrap = table.parentNode, box = document.createElement('input');
      box.type = 'search'; box.className = 'dt-filter'; box.setAttribute('aria-label', lang === 'nl' ? 'Filter rijen' : 'Filter rows');
      box.placeholder = (lang === 'nl' ? 'Filter ' : 'Filter ') + rows.length + (lang === 'nl' ? ' rijen…' : ' rows…');
      wrap.parentNode.insertBefore(box, wrap);
      var count = document.createElement('div'); count.className = 'dt-count'; wrap.parentNode.insertBefore(count, wrap);
      box.addEventListener('input', function () {
        var q = box.value.trim().toLowerCase(), shown = 0;
        rows.forEach(function (r) { var on = !q || r.textContent.toLowerCase().indexOf(q) !== -1; r.hidden = !on; if (on) shown++; });
        count.textContent = q ? (lang === 'nl' ? shown + ' van ' + rows.length + ' rijen' : shown + ' of ' + rows.length + ' rows') : '';
      });
    }
  }

  function init() {
    var tables = document.querySelectorAll('.tbl-wrap table, .tw table, .ea-wrap table, .pi-wrap table, .prose table');
    var seen = []; [].forEach.call(tables, function (t) { if (seen.indexOf(t) === -1) { seen.push(t); try { enhance(t); } catch (e) {} } });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

/* ---- Sparks: the homepage's drifting motes, as a shared component.
   Any hero-like surface gets a canvas behind its content. Palette-coloured,
   ~30 fps, paused when off-screen or in a hidden tab, skipped entirely when
   the visitor prefers reduced motion. Density scales with the surface. */
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var HERO = '[data-fx], .hero, .ph, .lh, .ch, .ghead, .fine-hero, .pi-hero, .ea-hero, .ev-hero, .city-hero, .page-hero';
  var hosts = [].slice.call(document.querySelectorAll(HERO))
    .filter(function (h) { return !h.querySelector('canvas') && h.getBoundingClientRect().height > 120; });
  if (!hosts.length) return;

  function luminance(el) {
    var bg = getComputedStyle(el).backgroundColor, m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(bg);
    if (!m || /rgba\(0, 0, 0, 0\)/.test(bg)) { var p = el.parentNode; return p && p !== document ? luminance(p) : 1; }
    return (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
  }

  hosts.forEach(function (host) {
    var dark = luminance(host) < 0.5;
    var cols = dark ? ['54,95,234', '255,188,66', '22,132,91'] : ['35,55,198', '234,88,12', '22,132,91'];
    var alpha = dark ? [0.25, 0.4] : [0.10, 0.22];
    host.classList.add('fx-host');
    var c = document.createElement('canvas'); c.className = 'fx-canvas'; c.setAttribute('aria-hidden', 'true');
    host.insertBefore(c, host.firstChild);
    var ctx = c.getContext('2d'); if (!ctx) return;
    var W, H, P = [], R = [], run = true, last = 0, N = 24;
    function size() { var r = host.getBoundingClientRect(); W = c.width = Math.max(1, Math.floor(r.width)); H = c.height = Math.max(1, Math.floor(r.height)); N = Math.max(14, Math.min(60, Math.round(W * H / 9000))); }
    function spawn() { return { x: Math.random() * W, y: H + 10, vy: .2 + Math.random() * .5, vx: (Math.random() - .5) * .22, r: 1 + Math.random() * 2, a: alpha[0] + Math.random() * (alpha[1] - alpha[0]), c: cols[Math.random() * cols.length | 0], life: 0, burst: 220 + Math.random() * 420 }; }
    size(); for (var k = 0; k < N; k++) { var p0 = spawn(); p0.y = Math.random() * H; P.push(p0); }
    var rs; window.addEventListener('resize', function () { clearTimeout(rs); rs = setTimeout(size, 120); });
    function frame(t) {
      requestAnimationFrame(frame);
      if (!run || t - last < 33) return; last = t;
      ctx.clearRect(0, 0, W, H);
      while (P.length < N) P.push(spawn());
      for (var i = 0; i < P.length; i++) {
        var p = P[i]; p.y -= p.vy; p.x += p.vx; p.life++;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.283); ctx.fillStyle = 'rgba(' + p.c + ',' + p.a + ')'; ctx.fill();
        if (p.life > p.burst || p.y < -10) { if (p.y > 0 && Math.random() < .5) R.push({ x: p.x, y: p.y, r: 2, c: p.c, a: dark ? .5 : .28 }); P[i] = spawn(); }
      }
      for (var j = R.length - 1; j >= 0; j--) {
        var q = R[j]; q.r += 1.6; q.a -= .018;
        ctx.beginPath(); ctx.arc(q.x, q.y, q.r, 0, 6.283); ctx.strokeStyle = 'rgba(' + q.c + ',' + Math.max(q.a, 0) + ')'; ctx.lineWidth = 1.2; ctx.stroke();
        if (q.a <= 0) R.splice(j, 1);
      }
    }
    if ('IntersectionObserver' in window) new IntersectionObserver(function (e) { run = e[0].isIntersecting && !document.hidden; }, { threshold: .05 }).observe(c);
    document.addEventListener('visibilitychange', function () { run = !document.hidden; });
    requestAnimationFrame(frame);
  });
})();

/* ---- Language switch: every page offers all four languages. A page with a
   real translation links straight to it (declared by its hreflang links);
   otherwise the visitor lands on that language's home page. Sits at the far
   right of the header, before the menu button. */
(function () {
  var LANGS = ['en', 'nl', 'de', 'fr'];
  var NAMES = { en: 'English', nl: 'Nederlands', de: 'Deutsch', fr: 'Français' };
  var HOME = { en: '/', nl: '/nl/', de: '/de/', fr: '/fr/' };
  var here = (document.documentElement.lang || 'en').slice(0, 2);
  if (LANGS.indexOf(here) === -1) here = 'en';
  var navIn = document.querySelector('nav.nav .nav-in');
  if (!navIn || document.querySelector('.nav-lang-wrap')) return;

  var twin = {};
  [].forEach.call(document.querySelectorAll('link[rel="alternate"][hreflang]'), function (l) {
    var code = l.getAttribute('hreflang');
    if (LANGS.indexOf(code) !== -1) twin[code] = l.getAttribute('href');
  });

  var wrap = document.createElement('div');
  wrap.className = 'nav-lang-wrap';
  var btn = document.createElement('a');
  btn.className = 'nav-lang'; btn.href = twin[here] || HOME[here];
  btn.textContent = here.toUpperCase();
  btn.setAttribute('aria-haspopup', 'true'); btn.setAttribute('aria-expanded', 'false');
  btn.title = { nl: 'Kies een taal', de: 'Sprache wählen', fr: 'Choisir une langue' }[here] || 'Choose a language';
  var drop = document.createElement('div');
  drop.className = 'drop nav-lang-drop';
  LANGS.forEach(function (code) {
    var a = document.createElement('a');
    a.href = twin[code] || HOME[code];
    a.hreflang = code; a.lang = code;
    a.textContent = NAMES[code];
    if (code === here) a.setAttribute('aria-current', 'true');
    a.addEventListener('click', function () { if (window.track) window.track('language_switch', { from: here, to: code, exact: !!twin[code] }); });
    drop.appendChild(a);
  });
  wrap.appendChild(btn); wrap.appendChild(drop);
  navIn.insertBefore(wrap, navIn.querySelector('.menu-btn') || null);

  function open(on) { wrap.classList.toggle('is-open', on); btn.setAttribute('aria-expanded', on ? 'true' : 'false'); }
  var t;
  wrap.addEventListener('mouseenter', function () { clearTimeout(t); open(true); });
  wrap.addEventListener('mouseleave', function () { t = setTimeout(function () { open(false); }, 260); });
  btn.addEventListener('click', function (e) { e.preventDefault(); open(!wrap.classList.contains('is-open')); });
  btn.addEventListener('focus', function () { open(true); });
  document.addEventListener('click', function (e) { if (!e.target.closest('.nav-lang-wrap')) open(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') open(false); });
})();

/* ---- Menus: on a mouse, panels open on hover and stay open for a moment
   after the pointer leaves, so a diagonal move never closes them. On touch
   and narrow screens the top item toggles its panel like an accordion; a
   second tap on an already open item follows its link. */
(function () {
  var items = [].slice.call(document.querySelectorAll('nav.nav .has-drop'));
  if (!items.length) return;
  var narrow = function () { return window.matchMedia('(max-width: 768px)').matches; };
  var coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  var timers = new Map();
  function open(li) { items.forEach(function (o) { if (o !== li) close(o); }); li.classList.add('is-open'); li.querySelector('a').setAttribute('aria-expanded', 'true'); }
  function close(li) { li.classList.remove('is-open'); li.querySelector('a').setAttribute('aria-expanded', 'false'); }
  items.forEach(function (li) {
    var a = li.querySelector(':scope > a'); a.setAttribute('aria-haspopup', 'true'); a.setAttribute('aria-expanded', 'false');
    li.addEventListener('mouseenter', function () { if (narrow()) return; clearTimeout(timers.get(li)); open(li); });
    li.addEventListener('mouseleave', function () { if (narrow()) return; timers.set(li, setTimeout(function () { close(li); }, 260)); });
    li.addEventListener('focusin', function () { if (!narrow()) open(li); });
    li.addEventListener('focusout', function (e) { if (!narrow() && !li.contains(e.relatedTarget)) close(li); });
    a.addEventListener('click', function (e) {
      if (!(narrow() || coarse)) return;               /* mouse users: the tab is a link */
      if (li.classList.contains('is-open')) return;   /* second tap follows the link */
      e.preventDefault(); open(li);
    });
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('nav.nav')) items.forEach(close); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') items.forEach(close); });
})();


/* ---- Mobile menu: make it closeable by more than one target.
   The panel is absolutely positioned inside the sticky header, so any
   positioning slip paints it over the button that closes it and the visitor
   is stuck with a menu they cannot dismiss. That happened. The css is fixed,
   but one fragile tap target is a bad single point of failure on a phone, so
   the menu now also closes on an outside tap, on Escape, on following a link,
   and when the viewport grows back to desktop.

   The button keeps its inline onclick: it is baked into 1,458 pages and still
   does the toggling. This only adds ways out. ---- */
(function () {
  var panel = document.getElementById('navLinks');
  var btn = document.querySelector('.menu-btn');
  if (!panel || !btn) return;

  function shut() {
    if (!panel.classList.contains('open')) return;
    panel.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
  }

  btn.setAttribute('aria-expanded', panel.classList.contains('open') ? 'true' : 'false');
  // The inline handler flips the class; mirror it for screen readers.
  btn.addEventListener('click', function () {
    setTimeout(function () {
      btn.setAttribute('aria-expanded',
        panel.classList.contains('open') ? 'true' : 'false');
    }, 0);
  });

  // Tapping anywhere off the header closes it.
  document.addEventListener('click', function (e) {
    if (!panel.classList.contains('open')) return;
    if (e.target.closest('.menu-btn')) return;
    if (!e.target.closest('#navLinks')) shut();
  });

  // Following a link should not leave the menu open behind it, which matters
  // for in-page anchors where no navigation repaints the header.
  panel.addEventListener('click', function (e) {
    var a = e.target.closest('a');
    if (a && !a.closest('.has-drop > a')) shut();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') shut();
  });

  // Rotating to landscape can cross the breakpoint and strand the open class.
  var mq = window.matchMedia('(min-width:769px)');
  (mq.addEventListener ? mq.addEventListener.bind(mq, 'change')
                       : mq.addListener.bind(mq))(function (e) {
    if (e.matches) shut();
  });
})();
