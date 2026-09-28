/* Charger map for parkingnetherlands.com.

   80k chargers is roughly 6 MB of JSON, so nothing is embedded in the page.
   Data lives in 0.1 degree tiles under /ev-data and only the tiles covering
   the current viewport are fetched. That keeps a national dataset on a static
   CDN with no server behind it.

   Two modes, switched on zoom:
     overview  town circles, sized by charger count
     detail    individual chargers, loaded per tile
   The list always mirrors exactly what the map is showing. */
(function () {
  'use strict';

  var DATA = '/ev-data';
  var DETAIL_ZOOM = 12;
  var MAX_MARKERS = 1200;     // beyond this the map reads as noise anyway
  var $ = function (s) { return document.querySelector(s); };

  var map, cities = [], tariffs = {}, meta = {};
  var tiles = {}, tileFailures = {}, layer, cityLayer, markers = {};
  var selected = null, mode = 'overview', sortKey = 'reliable';
  var rowsShown = [], moveTimer = null;

  /* Station record is positional, which roughly halves the tile size:
     0 id, 1 name, 2 operator, 3 lat, 4 lon, 5 kW, 6 points,
     7 uptime, 8 price per kWh, 9 parking area id, 10 points down now */
  var ID = 0, NAME = 1, CPO = 2, LAT = 3, LON = 4, KW = 5,
      PTS = 6, UP = 7, PPK = 8, AREA = 9, DOWN = 10;

  /* ------------------------------------------------------------ helpers */
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function stamp(d) {
    return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) +
           pad(d.getHours()) + pad(d.getMinutes());
  }
  function parseStamp(s) {
    if (!s || s.length !== 12) return null;
    var d = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8),
                     +s.slice(8, 10), +s.slice(10, 12));
    return isNaN(d.getTime()) ? null : d;
  }
  function toInput(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
           'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function money(v) { return '€' + v.toFixed(2); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function grade(up, down) {
    if (down > 0) return 'bad';
    if (up == null) return 'none';
    return up >= 97 ? 'ok' : up >= 90 ? 'warn' : 'bad';
  }
  function colour(g) {
    return g === 'ok' ? '#059669' : g === 'warn' ? '#D97706'
         : g === 'bad' ? '#DC2626' : '#7C8DB5';
  }

  /* ------------------------------------------------------------ pricing */
  /* Parking is only charged for the minutes that fall inside a paid window,
     which is why an evening stop can cost less than an afternoon one at the
     same bay. */
  function parkCost(areaId, arrive, leave) {
    var w = tariffs[areaId];
    if (!w || !w.length) return null;
    var total = 0, cursor = new Date(arrive.getTime());
    var guard = 0;
    while (cursor < leave && guard++ < 40) {
      var day0 = new Date(cursor.getTime()); day0.setHours(0, 0, 0, 0);
      var next = new Date(day0.getTime()); next.setDate(next.getDate() + 1);
      var segEnd = leave < next ? leave : next;
      var dow = cursor.getDay() === 0 ? 7 : cursor.getDay();
      for (var i = 0; i < w.length; i++) {
        if (w[i][0] !== dow) continue;
        var ws = new Date(day0.getTime() + w[i][1] * 60000);
        var we = new Date(day0.getTime() + w[i][2] * 60000);
        var s = cursor > ws ? cursor : ws;
        var e = segEnd < we ? segEnd : we;
        if (e > s) total += w[i][3] * ((e - s) / 3600000);
      }
      cursor = segEnd;
    }
    return total;
  }

  function priceOf(st, w) {
    var park = st[AREA] ? parkCost(st[AREA], w.a, w.l) : null;
    var charge = st[PPK] != null ? st[PPK] * w.kwh : null;
    if (park == null && charge == null) return null;
    return { park: park, charge: charge, total: (park || 0) + (charge || 0) };
  }

  function currentWindow() {
    var a = parseStamp($('#evArrive').dataset.stamp) || new Date();
    var l = parseStamp($('#evLeave').dataset.stamp) || new Date(a.getTime() + 7200000);
    return { a: a, l: l, kwh: parseFloat($('#evKwh').value) || 20 };
  }

  /* -------------------------------------------------------------- tiles */
  function neededTiles(b) {
    var out = [];
    var x0 = Math.floor(b.getWest() / 0.1), x1 = Math.floor(b.getEast() / 0.1);
    var y0 = Math.floor(b.getSouth() / 0.1), y1 = Math.floor(b.getNorth() / 0.1);
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > 80) return out;   // too wide to be useful
    for (var x = x0; x <= x1; x++) {
      for (var y = y0; y <= y1; y++) out.push(x + '_' + y);
    }
    return out;
  }

  function loadTiles(keys, done) {
    var pending = 0;
    keys.forEach(function (k) {
      if (tiles[k] !== undefined && !tileFailures[k]) return;
      tiles[k] = null;
      delete tileFailures[k];
      pending++;
      fetch(DATA + '/cells/' + k + '.json')
        .then(function (r) {
          if (!r.ok) throw new Error('Tile request failed');
          return r.json();
        })
        .then(function (rows) {
          tiles[k] = rows || [];
        })
        .catch(function () {
          tiles[k] = [];
          tileFailures[k] = true;
        })
        .then(function () {
          if (--pending === 0) done();
        });
    });
    if (pending === 0) done();
  }

  /* ------------------------------------------------------------- render */
  function refresh() {
    if (!map) return;
    var b = map.getBounds();
    mode = map.getZoom() >= DETAIL_ZOOM ? 'detail' : 'overview';
    $('#evHint').textContent = 'Each circle is a town; larger circles have more locations. Select a town to zoom in.';
    $('#evHint').classList.toggle('is-on', mode === 'overview');
    var sorts = document.querySelector('.ev-sort');
    if (sorts) sorts.hidden = mode !== 'detail';
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = mode !== 'detail';   // colour only means status up close

    if (mode === 'overview') {
      if (layer) { map.removeLayer(layer); layer = null; }
      drawCities(b);
    } else {
      if (cityLayer) { map.removeLayer(cityLayer); cityLayer = null; }
      loadTiles(neededTiles(b), function () { drawStations(map.getBounds()); });
    }
  }

  function scheduleRefresh() {
    clearTimeout(moveTimer);
    moveTimer = setTimeout(refresh, 140);
  }

  function drawCities(b) {
    var shown = [];
    for (var i = 0; i < cities.length && shown.length < 400; i++) {
      if (b.contains([cities[i].lat, cities[i].lon])) shown.push(cities[i]);
    }
    if (cityLayer) map.removeLayer(cityLayer);
    cityLayer = L.layerGroup();
    shown.forEach(function (c) {
      var m = L.circleMarker([c.lat, c.lon], {
        radius: Math.max(6, Math.min(26, Math.sqrt(c.n) * 1.5)),
        weight: 1.5, color: '#fff', fillColor: '#2337C6', fillOpacity: .62
      });
      m.bindTooltip(esc(c.name) + ': ' + c.n.toLocaleString() + ' locations',
                    { direction: 'top' });
      m.on('click', function () { map.setView([c.lat, c.lon], 13); });
      cityLayer.addLayer(m);
    });
    cityLayer.addTo(map);
    listCities(shown);
  }

  function drawStations(b) {
    var rows = [];
    for (var k in tiles) {
      var t = tiles[k];
      if (!t) continue;
      for (var i = 0; i < t.length; i++) {
        if (b.contains([t[i][LAT], t[i][LON]])) {
          rows.push(t[i]);
          if (rows.length >= MAX_MARKERS) break;
        }
      }
      if (rows.length >= MAX_MARKERS) break;
    }

    if (layer) map.removeLayer(layer);
    layer = L.layerGroup();
    markers = {};
    var w = currentWindow();
    rows.forEach(function (st) {
      var m = L.circleMarker([st[LAT], st[LON]], {
        radius: 6, weight: 2, color: '#fff',
        fillColor: colour(grade(st[UP], st[DOWN])), fillOpacity: .95
      });
      m.on('click', function () { select(st[ID], true); });
      m.bindPopup(popup(st, w));
      markers[st[ID]] = m;
      layer.addLayer(m);
    });
    layer.addTo(map);
    listStations(rows, w);
  }

  function popup(st, w) {
    var p = priceOf(st, w);
    return '<b>' + esc(st[NAME]) + '</b><br>' +
      esc(st[CPO] || 'Operator not published') + '<br>' +
      (st[KW] ? st[KW] + ' kW, ' : '') + st[PTS] + ' charge point' +
      (st[PTS] === 1 ? '' : 's') +
      (p ? '<br><b>' + money(p.total) + '</b> for this window' : '') +
      (st[DOWN] > 0 ? '<br><span style="color:#DC2626">' + st[DOWN] +
        ' reported out of order</span>' : '');
  }

  /* --------------------------------------------------------------- list */
  function listCities(rows) {
    rows = rows.slice().sort(function (a, b) { return b.n - a.n; });
    rowsShown = rows;
    $('#evMode').textContent = 'Towns in view';
    $('#evCount').textContent = rows.length.toLocaleString() +
      (rows.length === 1 ? ' town' : ' towns');
    $('#evRows').innerHTML = rows.length ? rows.map(function (c, i) {
      return '<div class="ev-row" role="option" tabindex="0" data-i="' + i + '" data-kind="city">' +
        '<div><div class="ev-name">' + esc(c.name) + '</div>' +
        '<div class="ev-meta"><span>' + c.n.toLocaleString() + ' locations</span>' +
        '<span>' + c.e.toLocaleString() + ' points</span>' +
        (c.kw ? '<span class="ev-kw">up to ' + c.kw + ' kW</span>' : '') +
        '</div></div><span class="ev-price is-unpriced">View chargers</span></div>';
    }).join('') : empty('No towns in view', 'Pan the map or zoom out.');
    bindRows();
  }

  function listStations(rows, w) {
    rows = rows.slice();
    rows.forEach(function (st) { st._p = priceOf(st, w); });
    rows.sort(function (a, b) {
      if (sortKey === 'cheap') {
        return (a._p ? a._p.total : Infinity) - (b._p ? b._p.total : Infinity);
      }
      if (sortKey === 'fast') return (b[KW] || 0) - (a[KW] || 0);
      if ((a[DOWN] > 0) !== (b[DOWN] > 0)) return a[DOWN] > 0 ? 1 : -1;
      return (b[UP] == null ? -1 : b[UP]) - (a[UP] == null ? -1 : a[UP]);
    });
    rowsShown = rows;

    $('#evMode').textContent = 'Chargers in view';
    $('#evCount').textContent = rows.length.toLocaleString() +
      (rows.length === 1 ? ' charger' : ' chargers') +
      (rows.length >= MAX_MARKERS ? ', zoom in for the rest' : '') +
      (neededTiles(b).some(function (k) { return tileFailures[k]; })
        ? ' · Some map areas could not load; move the map to retry.' : '');

    $('#evRows').innerHTML = rows.length ? rows.map(function (st, i) {
      var g = grade(st[UP], st[DOWN]);
      var price = st._p
        ? '<span class="ev-price">' + money(st._p.total) + '<small>' +
          (st._p.charge != null && st._p.park != null ? 'charge and park'
            : st._p.charge != null ? 'charging only' : 'parking only') + '</small></span>'
        : '<span class="ev-price is-unpriced">No published price</span>';
      return '<div class="ev-row" role="option" tabindex="0" data-i="' + i +
        '" data-kind="station" data-id="' + esc(st[ID]) + '"' +
        (selected === st[ID] ? ' aria-selected="true"' : '') + '>' +
        '<div><div class="ev-name">' + esc(st[NAME]) + '</div>' +
        '<div class="ev-meta"><span>' + esc(st[CPO] || 'Operator not published') + '</span>' +
        (st[KW] ? '<span class="ev-kw">' + st[KW] + ' kW</span>' : '') +
        '<span class="ev-up" data-g="' + g + '">' +
          (st[DOWN] > 0 ? st[DOWN] + ' out of order'
           : st[UP] == null ? 'No history yet' : st[UP].toFixed(1) + '% uptime') +
        '</span></div>' +
        '</div>' + price + '</div>';
    }).join('') : empty('No chargers in view', 'Pan the map or zoom out.');
    bindRows();
  }

  function empty(title, body) {
    return '<div class="ev-empty"><b>' + title + '</b>' + body + '</div>';
  }

  /* ---------------------------------------------------------- selection */
  function select(id, fromMap) {
    selected = id;
    var all = document.querySelectorAll('.ev-row');
    for (var i = 0; i < all.length; i++) {
      var on = all[i].dataset.id === String(id);
      all[i].setAttribute('aria-selected', on ? 'true' : 'false');
      if (on && fromMap) all[i].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    if (!fromMap && markers[id]) {
      map.panTo(markers[id].getLatLng());
      markers[id].openPopup();
    }
  }

  function activate(el) {
    if (el.dataset.kind === 'city') {
      var c = rowsShown[+el.dataset.i];
      if (c) map.setView([c.lat, c.lon], 13);
      return;
    }
    select(el.dataset.id, false);
  }

  function bindRows() {
    var all = document.querySelectorAll('.ev-row');
    Array.prototype.forEach.call(all, function (el, i) {
      el.onclick = function () { activate(el); };
      el.onkeydown = function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(el); }
        else if (e.key === 'ArrowDown' && all[i + 1]) { e.preventDefault(); all[i + 1].focus(); }
        else if (e.key === 'ArrowUp' && all[i - 1]) { e.preventDefault(); all[i - 1].focus(); }
      };
    });
  }

  /* --------------------------------------------------------------- init */
  function syncWindow() {
    var a = $('#evArrive'), l = $('#evLeave');
    var ad = new Date(a.value), ld = new Date(l.value);
    if (isNaN(ad.getTime()) || isNaN(ld.getTime()) || ld <= ad) return;
    a.dataset.stamp = stamp(ad);
    l.dataset.stamp = stamp(ld);
    if (window.history.replaceState) {
      window.history.replaceState({}, '',
        location.pathname + '?arriving=' + stamp(ad) + '&leaving=' + stamp(ld));
    }
    if (mode === 'detail') drawStations(map.getBounds());
  }

  function search(q) {
    var original = (q || '').trim();
    q = original.toLowerCase();
    if (!q) return;
    var hit = null;
    for (var i = 0; i < cities.length; i++) {
      var n = cities[i].name.toLowerCase();
      if (n === q) { hit = cities[i]; break; }
      if (!hit && n.indexOf(q) !== -1) hit = cities[i];
    }
    if (hit) {
      map.setView([hit.lat, hit.lon], 13);
      scheduleRefresh();
    } else {
      rowsShown = [];
      $('#evMode').textContent = 'Town search';
      $('#evCount').textContent = 'No town found for “' + original + '”. Try another spelling.';
      $('#evRows').innerHTML = empty('No matching town', 'Try a broader part of the town name.');
    }
  }

  function boot() {
    var q = new URLSearchParams(location.search);
    var now = new Date();
    now.setMinutes(Math.floor(now.getMinutes() / 15) * 15, 0, 0);
    var arrive = parseStamp(q.get('arriving')) || now;
    var leave = parseStamp(q.get('leaving')) || new Date(arrive.getTime() + 7200000);

    var a = $('#evArrive'), l = $('#evLeave');
    a.value = toInput(arrive); a.dataset.stamp = stamp(arrive);
    l.value = toInput(leave);  l.dataset.stamp = stamp(leave);
    a.addEventListener('change', syncWindow);
    l.addEventListener('change', syncWindow);
    $('#evKwh').addEventListener('input', function () {
      if (mode === 'detail') drawStations(map.getBounds());
    });

    var sorts = document.querySelectorAll('.ev-sort button');
    Array.prototype.forEach.call(sorts, function (btn) {
      btn.onclick = function () {
        sortKey = btn.dataset.sort;
        Array.prototype.forEach.call(sorts, function (b2) {
          b2.setAttribute('aria-pressed', b2 === btn ? 'true' : 'false');
        });
        if (mode === 'detail') drawStations(map.getBounds());
      };
    });

    var box = $('#evSearch');
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); search(box.value); }
    });
    $('#evGo').onclick = function () { search(box.value); };

    map = L.map('evmap', { scrollWheelZoom: true }).setView([52.15, 5.3], 8);
    window.__evMap = map;                       // the mobile tabs resize it
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19
    }).addTo(map);
    map.on('moveend zoomend', scheduleRefresh);
    refresh();
  }

  function stat(id, v) {
    var el = document.getElementById(id);
    if (el) el.textContent = v;
  }

  function json(path) {
    return fetch(DATA + path).then(function (r) {
      if (!r.ok) throw new Error(path);
      return r.json();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    Promise.all([json('/cities.json'), json('/tariffs.json'), json('/meta.json')])
      .then(function (res) {
        cities = res[0]; tariffs = res[1]; meta = res[2];
        stat('statStations', (meta.stations || 0).toLocaleString());
        stat('statCities', (meta.cities || 0).toLocaleString());
        stat('statDays', meta.days_measured
          ? meta.days_measured.toLocaleString() + ' days' : 'Not available');

        var css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
        document.head.appendChild(css);
        var js = document.createElement('script');
        js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
        js.onload = boot;
        js.onerror = function () {
          $('#evRows').innerHTML = empty('The map could not load',
            'Check your connection and reload the page.');
        };
        document.head.appendChild(js);
      })
      .catch(function () {
        $('#evRows').innerHTML = empty('Charger data did not load',
          'Reload the page to try again.');
      });
  });
})();
