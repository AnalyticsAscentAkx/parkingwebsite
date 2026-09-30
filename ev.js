/* EV charger layer: map, table, and live charge+park pricing.
   Reads window.EV_DATA, written into each page by the generator.
   Pricing runs client-side so changing the window re-prices instantly and the
   page stays fully static, which is what keeps it crawlable and free to host. */
(function () {
  'use strict';
  var D = window.EV_DATA;
  if (!D) return;

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var rows = D.stations || [];
  var selected = null, map = null, markers = {}, sortKey = 'reliable';

  /* ------------------------------------------------------------ pricing */
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function stamp(d) {
    return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) +
           pad(d.getHours()) + pad(d.getMinutes());
  }
  function parseStamp(s) {
    if (!s || s.length !== 12) return null;
    var d = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8),
                     +s.slice(8, 10), +s.slice(10, 12));
    return isNaN(d) ? null : d;
  }
  function toLocalInput(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
           'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  /* Parking is charged only for the minutes that fall inside a paid window,
     which is why an evening stay can cost less than an afternoon one. */
  function parkCost(windows, arrive, leave) {
    if (!windows || !windows.length) return null;
    var total = 0, cursor = new Date(arrive);
    while (cursor < leave) {
      var dayStart = new Date(cursor); dayStart.setHours(0, 0, 0, 0);
      var nextDay = new Date(dayStart); nextDay.setDate(nextDay.getDate() + 1);
      var segEnd = leave < nextDay ? leave : nextDay;
      var dow = cursor.getDay() === 0 ? 7 : cursor.getDay();
      for (var i = 0; i < windows.length; i++) {
        var w = windows[i];
        if (w[0] !== dow) continue;
        var ws = new Date(dayStart.getTime() + w[1] * 60000);
        var we = new Date(dayStart.getTime() + w[2] * 60000);
        if (we <= ws) we = new Date(we.getTime() + 86400000);
        var s = cursor > ws ? cursor : ws;
        var e = segEnd < we ? segEnd : we;
        if (e > s) total += w[3] * ((e - s) / 3600000);
      }
      cursor = segEnd;
    }
    return total;
  }

  function priceRow(st, arrive, leave, kwh) {
    var mins = Math.max(0, Math.round((leave - arrive) / 60000));
    var park = parkCost(st.pw, arrive, leave);
    var charge = (st.ppk != null) ? st.ppk * kwh + (st.fee || 0) : null;
    if (charge == null && park == null) return null;
    return { park: park, charge: charge, total: (charge || 0) + (park || 0), mins: mins };
  }

  /* -------------------------------------------------------------- render */
  function grade(u) {
    if (u == null) return 'none';
    return u >= 97 ? 'ok' : (u >= 90 ? 'warn' : 'bad');
  }

  function strip(hist) {
    if (!hist || !hist.length) {
      return '<div class="ev-strip">' +
             Array(30).join('<i data-g="none"></i>') + '</div>';
    }
    var out = '';
    for (var i = 0; i < hist.length; i++) {
      var v = hist[i];
      out += '<i data-g="' + (v == null ? 'none' : grade(v)) +
             '" style="height:' + (v == null ? 22 : Math.max(14, v)) + '%"></i>';
    }
    return '<div class="ev-strip">' + out + '</div>';
  }

  function money(v) { return '€' + v.toFixed(2); }

  function render() {
    var arrive = parseStamp($('#evArrive').dataset.stamp) || new Date();
    var leave = parseStamp($('#evLeave').dataset.stamp) || new Date(+arrive + 7200000);
    var kwh = parseFloat($('#evKwh').value) || 20;

    var list = rows.slice();
    list.forEach(function (st) { st._p = priceRow(st, arrive, leave, kwh); });
    list.sort(function (a, b) {
      if (sortKey === 'cheap') {
        var ap = a._p ? a._p.total : Infinity, bp = b._p ? b._p.total : Infinity;
        return ap - bp;
      }
      if (sortKey === 'fast') return (b.kw || 0) - (a.kw || 0);
      return (b.up == null ? -1 : b.up) - (a.up == null ? -1 : a.up);
    });

    var html = list.map(function (st) {
      var g = grade(st.up);
      var price = st._p
        ? '<span class="ev-price">' + money(st._p.total) +
          '<small>' + (st._p.charge != null ? 'charge + park' : 'parking only') + '</small></span>'
        : '<span class="ev-price is-unpriced">No published price</span>';
      return '<div class="ev-row" role="option" tabindex="0" data-id="' + st.id + '"' +
        (selected === st.id ? ' aria-selected="true"' : '') + '>' +
        '<div><div class="ev-name">' +
          (st.url ? '<a href="' + st.url + '">' + st.n + '</a>' : st.n) + '</div>' +
          '<div class="ev-meta"><span>' + (st.cpo || 'Operator not published') + '</span>' +
          (st.kw ? '<span class="ev-kw">' + st.kw + ' kW</span>' : '') +
          '<span class="ev-up" data-g="' + g + '">' +
            (st.up == null ? 'No history yet' : st.up.toFixed(1) + '% uptime') + '</span></div>' +
          strip(st.h) +
        '</div>' + price + '</div>';
    }).join('');

    $('#evRows').innerHTML = html || '<div class="ev-empty"><b>No chargers here yet</b>' +
      'This city has no chargers in the national register, or they are not published.</div>';
    $('#evCount').textContent = list.length + (list.length === 1 ? ' charger' : ' chargers');
    bindRows();
  }

  /* ----------------------------------------------------------- selection */
  function select(id, fromMap) {
    selected = id;
    var all = document.querySelectorAll('.ev-row');
    for (var i = 0; i < all.length; i++) {
      var on = all[i].dataset.id === id;
      all[i].setAttribute('aria-selected', on ? 'true' : 'false');
      if (on && fromMap) all[i].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    if (!fromMap && map && markers[id]) {
      map.panTo(markers[id].getLatLng(), { animate: true });
      markers[id].openPopup();
    }
  }

  function bindRows() {
    var all = document.querySelectorAll('.ev-row');
    for (var i = 0; i < all.length; i++) {
      all[i].onclick = function (e) {
        if (e.target.tagName === 'A') return;
        select(this.dataset.id, false);
      };
      all[i].onkeydown = function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(this.dataset.id, false); }
      };
    }
  }

  /* ---------------------------------------------------------------- map */
  function initMap() {
    var css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    var js = document.createElement('script');
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload = function () {
      var pts = rows.filter(function (s) { return s.lat; });
      map = L.map('evmap', { scrollWheelZoom: false });
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        { attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(map);
      if (!pts.length) { map.setView([52.1, 5.3], 7); return; }
      pts.forEach(function (st) {
        var g = grade(st.up);
        var col = g === 'ok' ? '#059669' : g === 'warn' ? '#D97706'
                : g === 'bad' ? '#DC2626' : '#94A3B8';
        var m = L.circleMarker([st.lat, st.lon], {
          radius: 7, color: '#fff', weight: 2, fillColor: col, fillOpacity: .95
        }).addTo(map);
        m.bindPopup('<b>' + st.n + '</b><br>' + (st.cpo || '') +
          (st.up != null ? '<br>' + st.up.toFixed(1) + '% uptime' : '<br>No history yet') +
          (st.url ? '<br><a href="' + st.url + '">Details and cost</a>' : ''));
        m.on('click', function () { select(st.id, true); });
        markers[st.id] = m;
      });
      map.fitBounds(pts.map(function (s) { return [s.lat, s.lon]; }), { padding: [30, 30] });
    };
    document.head.appendChild(js);
  }

  /* --------------------------------------------------------------- init */
  function syncWindow(push) {
    var a = $('#evArrive'), l = $('#evLeave');
    var ad = new Date(a.value), ld = new Date(l.value);
    if (isNaN(ad) || isNaN(ld) || ld <= ad) return;
    a.dataset.stamp = stamp(ad);
    l.dataset.stamp = stamp(ld);
    render();
    if (push && window.history.replaceState) {
      window.history.replaceState({}, '',
        location.pathname + '?arriving=' + stamp(ad) + '&leaving=' + stamp(ld));
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var q = new URLSearchParams(location.search);
    var now = new Date(); now.setMinutes(Math.floor(now.getMinutes() / 15) * 15, 0, 0);
    var arrive = parseStamp(q.get('arriving')) || now;
    var leave = parseStamp(q.get('leaving')) || new Date(+arrive + 7200000);

    var a = $('#evArrive'), l = $('#evLeave');
    a.value = toLocalInput(arrive); a.dataset.stamp = stamp(arrive);
    l.value = toLocalInput(leave);  l.dataset.stamp = stamp(leave);

    a.addEventListener('change', function () { syncWindow(true); });
    l.addEventListener('change', function () { syncWindow(true); });
    $('#evKwh').addEventListener('input', render);

    var sorts = document.querySelectorAll('.ev-sort button');
    for (var i = 0; i < sorts.length; i++) {
      sorts[i].onclick = function () {
        sortKey = this.dataset.sort;
        for (var j = 0; j < sorts.length; j++) {
          sorts[j].setAttribute('aria-pressed', sorts[j] === this ? 'true' : 'false');
        }
        render();
      };
    }
    render();
    if (document.getElementById('evmap')) {
      if ('IntersectionObserver' in window) {
        var o = new IntersectionObserver(function (e) {
          if (e[0].isIntersecting) { initMap(); o.disconnect(); }
        }, { rootMargin: '250px' });
        o.observe(document.getElementById('evmap'));
      } else initMap();
    }
  });
})();
