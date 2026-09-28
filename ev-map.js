/* Charger map for parkingnetherlands.com.

   80k chargers is roughly 6 MB of JSON, so nothing is embedded in the page.
   Data lives in 0.1 degree tiles under /ev-data and only the tiles covering
   the current viewport are fetched. That keeps a national dataset on a static
   CDN with no server behind it.

   Two modes, switched on zoom:
     overview  town circles, sized by charger count
     detail    individual chargers, loaded per tile

   The flow is search -> compare what is in view -> inspect one -> act.
   The list mirrors the map; a selected charger opens a card over the map.
   Panning does not silently change the list: a "Search this area" button
   appears and the visitor decides when results update. Zooming refreshes. */
(function () {
  'use strict';

  var DATA = '/ev-data';
  var DETAIL_ZOOM = 12;
  var MAX_MARKERS = 1200;     // beyond this the map reads as noise anyway
  var TOWN_ROWS = 400;        // list cap in overview; the map draws every town
  var FAST_KW = 50;
  var PIN_ZOOM = 14;          // from here each priced charger shows its price on the pin
  var $ = function (s) { return document.querySelector(s); };
  function track(n, p) { if (window.track) window.track(n, p); }

  var map, cities = [], tariffs = {}, meta = {};
  var tiles = {}, tileFailures = {}, layer, cityLayer, markers = {}, byId = {};
  var selected = null, mode = 'overview', sortKey = 'reliable';
  var filters = { fast: false, faulty: false, free: false, cheap: false, pr: false, garage: false, open: false, card: false };
  var showMode = 'chargers', places = null, placeLayer = null;
  /* Fast-charging hubs (150 kW+) wear the operator's badge: initial on the
     brand colour. Names are the operators' own; no logo files are copied. */
  var hubs = null, hubLayer = null;
  var BRANDS = [
    [/fastned/i, 'F', '#FFE500', '#111'], [/tesla/i, 'T', '#E31937', '#fff'],
    [/shell/i, 'S', '#FBCE07', '#DD1D21'], [/bp pulse|\bbp\b/i, 'bp', '#009900', '#fff'],
    [/ionity/i, 'I', '#0A0A3C', '#fff'], [/allego/i, 'A', '#0F2E8C', '#fff'],
    [/total ?energies/i, 'TE', '#E2001A', '#fff'], [/vattenfall/i, 'V', '#2071B5', '#FFDA00'],
    [/spirii/i, 'Sp', '#1DB5B5', '#fff'], [/powergo/i, 'PG', '#00A651', '#fff'],
    [/e-?flux/i, 'EF', '#2B2B2B', '#fff'], [/eneco/i, 'E', '#E60012', '#fff'],
    [/ubitricity/i, 'U', '#0060A8', '#fff'], [/lidl/i, 'L', '#0050AA', '#FFF000'],
    [/tango/i, 'Ta', '#1E88E5', '#fff'], [/tanx/i, 'Tx', '#7B1FA2', '#fff'],
    [/nxt/i, 'N', '#333', '#fff'], [/alva/i, 'Al', '#00897B', '#fff'], [/equans/i, 'Eq', '#004B8D', '#fff'],
    [/qwello/i, 'Q', '#6A1B9A', '#fff'], [/50five/i, '5', '#FF6F00', '#fff'], [/laadnet/i, 'Ln', '#0277BD', '#fff']
  ];
  function brand(cpo) {
    for (var i = 0; i < BRANDS.length; i++) if (BRANDS[i][0].test(cpo || '')) return BRANDS[i];
    var t = (cpo || '?').replace(/[^A-Za-z0-9 ]/g, '').trim();
    return [null, (t.split(/\s+/).map(function (w) { return w[0]; }).join('').slice(0, 2) || '?').toUpperCase(), '#17243A', '#fff'];
  }
  function hubIcon(cpo, kw, faulty, price) {
    var b = brand(cpo);
    return L.divIcon({ className: 'ev-hubwrap', iconSize: null, iconAnchor: [0, 0],
      html: '<span class="ev-hub' + (faulty ? ' is-faulty' : '') + '" style="background:' + b[2] + ';color:' + b[3] + '" title="' + esc(cpo) + ', up to ' + kw + ' kW">' + esc(b[1]) + '</span>' +
            (price ? '<span class="ev-hubprice">' + price + '</span>' : '') +
            '<small class="ev-hubkw">' + kw + ' kW</small>' });
  }
  function isHub(st) { return st[KW] >= 150; }
  var origin = null;          // where the visitor is, or the address they searched
  function distKm(lat, lon) {
    if (!origin) return null;
    var dLat = (lat - origin[0]) * 111.32, dLon = (lon - origin[1]) * 68.0;
    return Math.sqrt(dLat * dLat + dLon * dLon);
  }
  function distLabel(km) {
    if (km == null) return '';
    var walk = Math.max(1, Math.round(km * 1000 / 80));
    return (km < 1 ? Math.round(km * 1000) + ' m' : km.toFixed(1) + ' km') + ' · ~' + walk + ' min walk';
  }
  function setOrigin(ll) {
    origin = ll;
    var near = document.querySelector('.ev-sort button[data-sort="near"]');
    if (near) { near.hidden = false; }
    if (sortKey !== 'near') {
      sortKey = 'near';
      Array.prototype.forEach.call(document.querySelectorAll('.ev-sort button'), function (b) {
        b.setAttribute('aria-pressed', b.dataset.sort === 'near' ? 'true' : 'false');
      });
    }
  }
  function isApple() { return /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent); }
  function directions(lat, lon) {
    var g = 'https://www.google.com/maps/dir/?api=1&destination=' + lat + ',' + lon;
    var a = 'https://maps.apple.com/?daddr=' + lat + ',' + lon + '&dirflg=d';
    return isApple()
      ? '<a class="ev-card-btn is-primary" target="_blank" rel="noopener" href="' + a + '">Apple Maps</a><a class="ev-card-btn" target="_blank" rel="noopener" href="' + g + '">Google Maps</a>'
      : '<a class="ev-card-btn is-primary" target="_blank" rel="noopener" href="' + g + '">Directions</a>';
  }
  var rowsShown = [], moveTimer = null, zoomed = false, hovered = null;

  /* Station record is positional, which roughly halves the tile size:
     0 id, 1 name, 2 operator, 3 lat, 4 lon, 5 kW, 6 points,
     7 uptime, 8 price per kWh, 9 parking area id, 10 points down now,
     11 price source: 0 this charger's tariff, 1 operator's usual rate,
        2 national median (operator publishes nothing) */
  var ID = 0, NAME = 1, CPO = 2, LAT = 3, LON = 4, KW = 5,
      PTS = 6, UP = 7, PPK = 8, AREA = 9, DOWN = 10, SRC = 11,
      ACC = 12, FLAGS = 13, PLUGS = 14;
  /* 12 where the post stands (S street, L lot, G garage, U underground,
     D driveway, M motorway); 13 flags: 1 customers only, 2 not 24/7,
     4 no charging when closed, 8 DC fast plug, 16 pay by card, 32 cable
     attached; 14 plug types as text. */
  var ACCESS_NAME = { S: 'On the street', L: 'In a car park', G: 'In a parking garage', U: 'In an underground garage', D: 'On a driveway', M: 'Along the motorway' };
  function restricted(st) { return ((st[FLAGS] || 0) & 7) !== 0; }
  function accessNotes(st) {
    var f = st[FLAGS] || 0, notes = [];
    if (f & 1) notes.push('customers only');
    if (f & 2) notes.push('not open 24/7');
    if (f & 4) notes.push('no charging when closed');
    if (st[ACC] === 'G' || st[ACC] === 'U') notes.push('garage, may be behind a barrier');
    else if (st[ACC] === 'L' && (f & 1)) notes.push('private car park');
    return notes;
  }
  function srcNote(st, short) {
    var s = st[SRC] || 0;
    if (s === 1) return short ? 'operator\u2019s usual rate' : 'No tariff is published for this charger; this is the operator\u2019s usual rate elsewhere.';
    if (s === 2) return short ? 'typical NL rate' : 'This operator publishes no tariffs; the national median is used.';
    return '';
  }

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
  function hhmm(d) { return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
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
    return g === 'ok' ? '#16845B' : g === 'warn' ? '#D97706'
         : g === 'bad' ? '#DC2626' : '#7C8DB5';
  }
  function narrow() { return window.innerWidth <= 900; }
  /* On phones the results are a bottom sheet over the map: peek, full, or
     hidden while a card is open. Desktop ignores the state. */
  function sheet(state) {
    var app = $('#evApp');
    if (!app) return;
    app.dataset.sheet = state;
    if (state === 'full' && window.__evMap) setTimeout(function () { window.__evMap.invalidateSize(); }, 300);
  }
  function sheetToggle() { sheet($('#evApp').dataset.sheet === 'full' ? 'peek' : 'full'); }
  /* Charging price graded against the national spread: p10-p90 is 0.28-0.63
     around a 0.41 median, so under 0.36 is cheap and over 0.50 is dear. */
  function ppkGrade(ppk) {
    if (ppk == null) return 'none';
    return ppk < 0.36 ? 'lo' : ppk > 0.50 ? 'hi' : 'mid';
  }
  function parkGrade(p) {
    if (!p || p.park == null) return 'none';
    return p.park === 0 ? 'lo' : p.park > 6 ? 'hi' : 'mid';
  }
  function reportedAt() {
    if (!meta.generated) return 'at the last data refresh';
    var d = new Date(meta.generated);
    if (isNaN(d.getTime())) return 'at the last data refresh';
    return 'on ' + d.getDate() + ' ' +
      ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()] +
      ' at ' + hhmm(d);
  }

  /* ------------------------------------------------------------ pricing */
  /* Parking is charged only for the minutes inside a paid window, and those
     minutes are priced by the zone's fare ladder: duration bands with a step
     size, the way the meter does it. A first free half hour or a 12-hour
     ticket therefore come out right instead of being multiplied by hours. */
  function ladderCost(parts, minutes) {
    var total = 0;
    for (var i = 0; i < parts.length; i++) {
      var start = parts[i][0], end = parts[i][1], step = Math.max(parts[i][2], 1), amount = parts[i][3];
      if (minutes <= start) break;
      var covered = Math.min(minutes, end) - start;
      if (covered > 0) total += Math.ceil(covered / step) * amount;
    }
    return total;
  }

  function parkCost(areaId, arrive, leave) {
    var t = tariffs[areaId];
    if (!t || !t.w || !t.w.length) return null;
    var paid = {}, cursor = new Date(arrive.getTime());
    var guard = 0;
    while (cursor < leave && guard++ < 40) {
      var day0 = new Date(cursor.getTime()); day0.setHours(0, 0, 0, 0);
      var next = new Date(day0.getTime()); next.setDate(next.getDate() + 1);
      var segEnd = leave < next ? leave : next;
      var dow = cursor.getDay() === 0 ? 7 : cursor.getDay();
      /* Windows can overlap (an hourly tariff and an avondkaart both cover
         19:00-24:00). Walk the day in 15-minute slots and charge each slot
         to the cheapest product that covers it, never to two at once. */
      var slot = new Date(cursor.getTime());
      while (slot < segEnd) {
        var slotEnd = new Date(Math.min(slot.getTime() + 900000, segEnd.getTime()));
        var minute = (slot - day0) / 60000, best = null, bestRate = Infinity;
        for (var i = 0; i < t.w.length; i++) {
          if (t.w[i][0] !== dow || minute < t.w[i][1] || minute >= t.w[i][2]) continue;
          var code = t.w[i][3], rate = t.f[code] ? ladderCost(t.f[code], 60) : Infinity;
          if (rate < bestRate) { bestRate = rate; best = code; }
        }
        if (best) paid[best] = (paid[best] || 0) + (slotEnd - slot) / 60000;
        slot = slotEnd;
      }
      cursor = segEnd;
    }
    var total = 0, any = false;
    for (var code in paid) {
      any = true;
      var ladder = t.f[code];
      if (ladder) total += ladderCost(ladder, paid[code]);
    }
    return any ? total : 0;
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

  /* The assumed session, spelled out wherever a price appears. */
  function sessionLabel(w, short) {
    var hours = Math.round((w.l - w.a) / 360000) / 10;
    var h = (hours % 1 === 0 ? hours.toFixed(0) : hours.toFixed(1)) + ' h';
    if (short) return 'est. ' + w.kwh + ' kWh + ' + h;
    return w.kwh + ' kWh and a ' + h + ' stop, ' + hhmm(w.a) + ' to ' + hhmm(w.l);
  }

  function updateSession() {
    var w = currentWindow(), el = $('#evSession'), sm = $('#evSessionSummary');
    if (el) { el.textContent = 'Estimates for ' + sessionLabel(w, true).replace('est. ', '') + ' \u00b7 * operator\u2019s usual rate'; el.title = 'Estimates assume ' + sessionLabel(w, false) + '. An asterisk means no tariff is published for that charger and the operator\u2019s usual rate is used.'; }
    if (sm) sm.textContent = w.kwh + ' kWh \u00b7 ' + hhmm(w.a) + '\u2013' + hhmm(w.l) + ' \u00b7 change';
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
          rows.forEach(function (st) { byId[st[ID]] = st; });
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
    if (showMode === 'parking') { refreshParking(b); return; }
    $('#evHint').textContent = 'Circles are towns, badges are fast-charging hubs (150 kW+). Select one to zoom in.';
    $('#evHint').classList.toggle('is-on', mode === 'overview');
    var sorts = document.querySelector('.ev-sort');
    if (sorts) sorts.hidden = mode !== 'detail';
    syncChips(mode === 'detail');
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = mode !== 'detail' || !!selected;   // colour only means status up close
    $('#evArea').hidden = true;
    legend(mode === 'detail' && (map.getZoom() >= PIN_ZOOM + 1) ? 'pins' : 'dots');

    if (mode === 'overview') {
      if (layer) { map.removeLayer(layer); layer = null; }
      drawCities(b);
      updateMetaNational();
    } else {
      if (cityLayer) { map.removeLayer(cityLayer); cityLayer = null; }
      if (hubLayer) { map.removeLayer(hubLayer); hubLayer = null; }
      loadTiles(neededTiles(b), function () { drawStations(map.getBounds()); });
    }
  }

  function scheduleRefresh() {
    clearTimeout(moveTimer);
    moveTimer = setTimeout(refresh, 140);
  }

  /* A pan in detail mode offers, rather than forces, a new result set. */
  function onMoveEnd() {
    updateUrl();
    if (zoomed || mode === 'overview') { zoomed = false; scheduleRefresh(); return; }
    $('#evArea').hidden = false;
  }

  function drawCities(b) {
    var inView = [];
    for (var i = 0; i < cities.length; i++) {
      if (b.contains([cities[i].lat, cities[i].lon])) inView.push(cities[i]);
    }
    if (cityLayer) map.removeLayer(cityLayer);
    cityLayer = L.layerGroup();
    inView.forEach(function (c) {
      var m = L.circleMarker([c.lat, c.lon], {
        radius: Math.max(5, Math.min(26, Math.sqrt(c.n) * 1.5)),
        weight: 1.5, color: '#fff', fillColor: '#365FEA', fillOpacity: .62
      });
      m.bindTooltip(esc(c.name) + ': ' + c.n.toLocaleString() + ' locations',
                    { direction: 'top' });
      m.on('click', function () { map.setView([c.lat, c.lon], 13); });
      cityLayer.addLayer(m);
    });
    cityLayer.addTo(map);
    drawHubs(b);
    listCities(inView, 'Towns in view');
  }

  function drawHubs(b) {
    if (hubLayer) { map.removeLayer(hubLayer); hubLayer = null; }
    function draw() {
      hubLayer = L.layerGroup();
      var z = map.getZoom();
      hubs.forEach(function (h) {
        if (!b.contains([h[3], h[4]])) return;
        // far out, only the real hubs: many points or very high power
        if (z < 8 && (h[6] || 0) < 8 && h[5] < 350) return;
        if (z < 10 && (h[6] || 0) < 4 && h[5] < 300) return;
        var m = L.marker([h[3], h[4]], { icon: hubIcon(h[2], h[5], h[7] > 0, null), riseOnHover: true });
        m.bindTooltip(esc(h[1]) + ' · ' + esc(h[2]) + ' · ' + h[6] + ' points', { direction: 'top', opacity: .95 });
        m.on('click', function () { map.setView([h[3], h[4]], 15); });
        hubLayer.addLayer(m);
      });
      hubLayer.addTo(map);
    }
    if (hubs) { draw(); return; }
    json('/hubs.json').then(function (rows) { hubs = rows; if (mode === 'overview') draw(); }).catch(function () { hubs = []; });
  }

  function stationRows(b) {
    var w = currentWindow(), rows = [];
    for (var k in tiles) {
      var t = tiles[k];
      if (!t) continue;
      for (var i = 0; i < t.length; i++) {
        var st = t[i];
        if (!b.contains([st[LAT], st[LON]])) continue;
        st._p = priceOf(st, w);
        rows.push(st);
        if (rows.length >= MAX_MARKERS) break;
      }
      if (rows.length >= MAX_MARKERS) break;
    }
    var totals = rows.filter(function (s) { return s._p; }).map(function (s) { return s._p.total; }).sort(function (a, b) { return a - b; });
    var median = totals.length ? totals[Math.floor(totals.length / 2)] : null;
    return rows.filter(function (st) {
      if (filters.fast && !(st[KW] >= FAST_KW)) return false;
      if (filters.faulty && !(st[DOWN] > 0)) return false;
      if (filters.open && restricted(st)) return false;
      if (filters.card && !((st[FLAGS] || 0) & 16)) return false;
      if (filters.free && !(st._p == null || st._p.park == null || st._p.park === 0)) return false;
      if (filters.cheap && !(st._p && median != null && st._p.total <= median)) return false;
      return true;
    });
  }

  /* The header answers "what does a stop cost around here": live figures for
     the chargers in view and the chosen session, not national totals. */
  function updateMeta(rows, w) {
    var priced = rows.filter(function (s) { return s._p; });
    var totals = priced.map(function (s) { return s._p.total; }).sort(function (a, b) { return a - b; });
    var kwhs = rows.filter(function (s) { return s[PPK] != null; }).map(function (s) { return s[PPK]; }).sort(function (a, b) { return a - b; });
    var parks = rows.filter(function (s) { return s._p && s._p.park != null; }).map(function (s) { return s._p.park; }).sort(function (a, b) { return a - b; });
    var fast = rows.filter(function (s) { return s[KW] >= FAST_KW; }).length;
    var freeShare = rows.length ? rows.filter(function (s) { return !s._p || s._p.park == null || s._p.park === 0; }).length / rows.length : 0;
    stat('mCheap', totals.length ? money(totals[0]) : '–');
    stat('mKwh', kwhs.length ? money(kwhs[Math.floor(kwhs.length / 2)]) : '–');
    stat('mPark', !rows.length ? '–' : freeShare >= .5 ? 'Mostly free' : parks.length ? money(parks[Math.floor(parks.length / 2)]) : '–');
    stat('mFast', rows.length ? String(fast) : '–');
    var cap = document.querySelector('#evMeta');
    if (cap) cap.title = 'For the ' + rows.length + ' chargers in view, ' + sessionLabel(w, false);
  }

  function updateMetaNational() {
    stat('mCheap', '–');
    stat('mKwh', '€0.41');
    stat('mPark', '–');
    stat('mFast', '–');
  }

  function markerRadius() {
    var z = map.getZoom();
    return z >= 15 ? 7 : z >= 13 ? 6 : 4.5;
  }

  function drawStations(b) {
    var rows = stationRows(b);
    if (layer) map.removeLayer(layer);
    layer = L.layerGroup();
    markers = {};
    var w = currentWindow(), r = markerRadius();
    /* Price pins only when they can be read: close in, or few in view. */
    var pills = map.getZoom() >= PIN_ZOOM + 1 || (map.getZoom() >= PIN_ZOOM && rows.length <= 150);
    rows.forEach(function (st) {
      var p = pills ? priceOf(st, w) : null, m;
      if (isHub(st)) {
        m = L.marker([st[LAT], st[LON]], { icon: hubIcon(st[CPO], Math.round(st[KW]), st[DOWN] > 0,
          p ? (p.charge != null ? '\u26A1' + money(p.charge) : '') + (p.park != null ? ' P ' + (p.park === 0 ? 'free' : money(p.park)) : '') : null), riseOnHover: true });
      } else if (p) {
        m = L.marker([st[LAT], st[LON]], { icon: pinIcon(p, ppkGrade(st[PPK]), st[DOWN] > 0), riseOnHover: true });
      } else {
        m = L.circleMarker([st[LAT], st[LON]], {
          radius: r, weight: 1.5, color: '#fff',
          fillColor: colour(grade(st[UP], st[DOWN])), fillOpacity: .95
        });
      }
      m.on('click', function () { select(st[ID], true); });
      m.on('mouseover', function () { hover(st[ID], true); });
      m.on('mouseout', function () { hover(null, true); });
      m.bindTooltip(esc(st[NAME]) + (p ? ' · ' + money(p.total) + ' total' : ''), { direction: 'top', opacity: .95 });
      markers[st[ID]] = m;
      layer.addLayer(m);
    });
    layer.addTo(map);
    if (selected && markers[selected]) styleMarker(selected, 'selected');
    listStations(rows, w);
  }

  /* The pin shows the two halves of the bill side by side: charging (bolt,
     coloured by the kWh price grade) and parking (P). One half alone when
     the other is unknown. The total is in the list and the card. */
  function pinIcon(p, g, faulty) {
    var charge = p.charge != null ? '<i class="c" data-g="' + g + '">\u26A1' + money(p.charge) + '</i>' : '';
    var park = p.park != null ? '<i class="p"' + (p.park === 0 ? ' data-free="1"' : '') + '>P ' + (p.park === 0 ? 'free' : money(p.park)) + '</i>' : '';
    return L.divIcon({
      className: 'ev-pinwrap',
      html: '<span class="ev-pin ev-pin-split" data-g="' + g + (faulty ? '" data-faulty="1' : '') + '">' + (faulty ? '<b>!</b>' : '') + charge + park + '</span>',
      iconSize: null, iconAnchor: [0, 0]
    });
  }

  function styleMarker(id, state) {
    var m = markers[id];
    if (!m) return;
    if (m.setStyle) {
      var r = markerRadius();
      if (state === 'selected') m.setStyle({ radius: r + 4, weight: 3, color: '#FFBC42' }).bringToFront();
      else if (state === 'hover') m.setStyle({ radius: r + 2, weight: 2.5, color: '#365FEA' }).bringToFront();
      else m.setStyle({ radius: r, weight: 1.5, color: '#fff' });
      return;
    }
    var el = m.getElement();
    if (!el) return;
    el.classList.toggle('is-sel', state === 'selected');
    el.classList.toggle('is-hover', state === 'hover');
    m.setZIndexOffset(state === 'selected' ? 2000 : state === 'hover' ? 1000 : 0);
  }

  /* --------------------------------------------------------------- list */
  function listCities(rows, title, note) {
    rows = rows.slice().sort(function (a, b) { return b.n - a.n; });
    var total = rows.length;
    rows = rows.slice(0, TOWN_ROWS);
    rowsShown = rows;
    $('#evMode').textContent = title;
    $('#evCount').textContent = note || (
      total > TOWN_ROWS
        ? 'Showing the ' + TOWN_ROWS + ' largest of ' + total.toLocaleString() +
          ' towns in view. Type a town name to search all ' + (meta.cities || cities.length).toLocaleString() + '.'
        : total.toLocaleString() + (total === 1 ? ' town' : ' towns'));
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
    rows.forEach(function (st) { st._d = distKm(st[LAT], st[LON]); });
    rows.sort(function (a, b) {
      if (sortKey === 'near' && origin) return (a._d || 0) - (b._d || 0);
      if (sortKey === 'cheap') {
        return (a._p ? a._p.total : Infinity) - (b._p ? b._p.total : Infinity);
      }
      if (sortKey === 'fast') return (b[KW] || 0) - (a[KW] || 0);
      if ((a[DOWN] > 0) !== (b[DOWN] > 0)) return a[DOWN] > 0 ? 1 : -1;
      return (b[UP] == null ? -1 : b[UP]) - (a[UP] == null ? -1 : a[UP]);
    });
    rowsShown = rows;
    updateMeta(rows, w);

    var active = [];
    if (filters.free) active.push('free parking');
    if (filters.cheap) active.push('low cost');
    if (filters.fast) active.push(FAST_KW + ' kW+');
    if (filters.faulty) active.push('reported faulty');
    if (filters.open) active.push('open access');
    if (filters.card) active.push('pay by card');
    $('#evMode').textContent = 'Chargers in view';
    $('#evCount').textContent = rows.length.toLocaleString() +
      (rows.length === 1 ? ' charger' : ' chargers') +
      (active.length ? ' (' + active.join(', ') + ')' : '') +
      (rows.length >= MAX_MARKERS ? ', zoom in for the rest' : '') +
      (neededTiles(map.getBounds()).some(function (k) { return tileFailures[k]; })
        ? ' · Some map areas could not load; move the map to retry.' : '');
    updateSession();

    var label = sessionLabel(w, true);
    $('#evRows').innerHTML = rows.length ? rows.map(function (st, i) {
      var g = grade(st[UP], st[DOWN]);
      var price = st._p
        ? '<span class="ev-price" data-g="' + ppkGrade(st[PPK]) + '">' + money(st._p.total) +
          '<small>' + (st._p.charge != null ? '<i data-g="' + ppkGrade(st[PPK]) + '">' + money(st._p.charge) + ' charge' + (st[SRC] ? '*' : '') + '</i>' : '<i data-g="none">no charge price</i>') +
          ' + ' + (st._p.park != null ? '<i data-g="' + parkGrade(st._p) + '">' + (st._p.park === 0 ? 'free parking' : money(st._p.park) + ' parking') + '</i>' : '<i data-g="none">no paid zone on record</i>') +
          '</small><small>' + label + '</small></span>'
        : '<span class="ev-price is-unpriced">No published price</span>';
      return '<div class="ev-row" role="option" tabindex="0" data-i="' + i +
        '" data-kind="station" data-id="' + esc(st[ID]) + '"' +
        (selected === st[ID] ? ' aria-selected="true"' : '') + '>' +
        '<div><div class="ev-name">' + esc(st[NAME]) + '</div>' +
        '<div class="ev-meta">' + (st._d != null ? '<span class="ev-dist">' + distLabel(st._d) + '</span>' : '') +
        '<span>' + esc(st[CPO] || 'Operator not published') + '</span>' +
        (st[KW] ? '<span class="ev-kw">' + st[KW] + ' kW</span>' : '') +
        (st[PLUGS] ? '<span>' + esc(st[PLUGS]) + '</span>' : '') +
        (restricted(st) ? '<span class="ev-access" title="' + esc(accessNotes(st).join(', ')) + '">restricted access</span>' : '') +
        '<span class="ev-up" data-g="' + g + '">' +
          (st[DOWN] > 0 ? st[DOWN] + ' reported out of order'
           : st[UP] == null ? 'No fault reported' : st[UP].toFixed(1) + '% uptime') +
        '</span></div>' +
        '</div>' + price + '</div>';
    }).join('') : empty('No chargers match', filters.fast || filters.faulty || filters.free || filters.cheap || filters.open || filters.card
        ? 'Clear a filter, or pan the map.' : 'Pan the map or zoom out.');
    bindRows();
  }

  function empty(title, body) {
    return '<div class="ev-empty"><b>' + title + '</b>' + body + '</div>';
  }

  /* ---------------------------------------------------------- selection */
  function hover(id, fromMap) {
    if (hovered && hovered !== selected) styleMarker(hovered, 'normal');
    var prev = document.querySelector('.ev-row.is-hover');
    if (prev) prev.classList.remove('is-hover');
    hovered = id;
    if (!id) return;
    if (id !== selected) styleMarker(id, 'hover');
    if (fromMap) {
      var row = document.querySelector('.ev-row[data-id="' + id + '"]');
      if (row) row.classList.add('is-hover');
    }
  }

  function select(id, fromMap) {
    if (selected && markers[selected]) styleMarker(selected, 'normal');
    selected = id;
    var all = document.querySelectorAll('.ev-row');
    for (var i = 0; i < all.length; i++) {
      var on = all[i].dataset.id === String(id);
      all[i].setAttribute('aria-selected', on ? 'true' : 'false');
      if (on && fromMap) all[i].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    if (markers[id]) {
      styleMarker(id, 'selected');
      if (!fromMap) map.panTo(markers[id].getLatLng());
    }
    track('select', { mode: showMode, from: fromMap ? 'map' : 'list' });
    showCard(byId[id]);
    if (narrow()) sheet('hidden');   // the card sits over the map
  }

  function clearSelection() {
    if (selected && markers[selected]) styleMarker(selected, 'normal');
    selected = null;
    var all = document.querySelectorAll('.ev-row[aria-selected="true"]');
    for (var i = 0; i < all.length; i++) all[i].setAttribute('aria-selected', 'false');
    $('#evCard').hidden = true;
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = mode !== 'detail';
    if (narrow()) sheet('peek');
  }

  function showCard(st) {
    var card = $('#evCard');
    if (!st) { card.hidden = true; return; }
    if (st._place) { showPlaceCard(st); return; }
    var w = currentWindow(), p = priceOf(st, w), g = grade(st[UP], st[DOWN]);
    var status = st[DOWN] > 0
      ? st[DOWN] + ' of ' + st[PTS] + ' charge point' + (st[PTS] === 1 ? '' : 's') + ' reported out of order'
      : st[UP] == null ? 'No fault reported' : st[UP].toFixed(1) + '% uptime over 30 days';
    var lines = '';
    if (p && p.charge != null) lines += row('Charging, ' + w.kwh + ' kWh at ' + money(st[PPK]) + '/kWh' + (st[SRC] ? ' (' + srcNote(st, true) + ')' : ''), money(p.charge), ppkGrade(st[PPK]));
    else lines += row('Charging', 'Price not published', 'none');
    if (p && p.park != null) lines += row('Parking, ' + hhmm(w.a) + ' to ' + hhmm(w.l), p.park > 0 ? money(p.park) : 'Free in this window', parkGrade(p));
    else lines += row('Parking', 'No paid zone at this spot', 'none');
    card.innerHTML =
      '<button type="button" class="ev-card-x" aria-label="Close">&times;</button>' +
      '<div class="ev-card-name">' + esc(st[NAME]) + '</div>' +
      '<div class="ev-card-meta">' + (st._d != null ? distLabel(st._d) + ' · ' : '') + esc(st[CPO] || 'Operator not published') +
        (st[KW] ? ' · up to ' + st[KW] + ' kW' : ' · power not published') +
        ' · ' + st[PTS] + ' charge point' + (st[PTS] === 1 ? '' : 's') + '</div>' +
      '<div class="ev-card-status" data-g="' + g + '"><i></i>' + status +
        '<small>Reported by the operator ' + reportedAt() + '. Occupancy is not published.</small></div>' +
      '<div class="ev-card-access' + (restricted(st) ? ' is-warn' : '') + '">' +
        '<b>' + (ACCESS_NAME[st[ACC]] || 'Location type not published') + '</b>' +
        (accessNotes(st).length ? ' · ' + esc(accessNotes(st).join(' · ')) : (st[ACC] === 'S' ? ' · public access' : '')) +
        (st[PLUGS] ? '<br>' + esc(st[PLUGS]) + ((st[FLAGS] || 0) & 32 ? ', cable attached' : ', bring your cable') : '') +
        ((st[FLAGS] || 0) & 16 ? ' · pay by card' : ' · charge card or app') +
      '</div>' +
      '<div class="ev-card-rows">' + lines +
        (p ? '<div class="ev-card-row is-total" data-g="' + ppkGrade(st[PPK]) + '"><span>Estimated total</span><b>' + money(p.total) + '</b></div>' : '') +
      '</div>' +
      '<div class="ev-card-note">' + (srcNote(st, false) ? srcNote(st, false) + ' ' : '') + 'Estimate for ' + sessionLabel(w, false) +
        '. Plug types, opening hours and barriers are as the operator reported them to the register.</div>' +
      '<div class="ev-card-act">' + directions(st[LAT], st[LON]) +
        '<button type="button" class="ev-card-btn" id="evCardWindow">Change session</button>' +
      '</div>';
    card.hidden = false;
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = true;
    card.querySelector('.ev-card-x').onclick = clearSelection;
    Array.prototype.forEach.call(card.querySelectorAll('a.ev-card-btn'), function (a) { a.onclick = function () { track('directions', { mode: showMode, app: a.textContent.trim() }); }; });
    $('#evCardWindow').onclick = function () {
      var d = $('#evWindow'); if (d) d.open = true;
      if (narrow()) sheet('full');
      $('#evArrive').focus();
    };
  }

  function row(label, value, g) {
    return '<div class="ev-card-row" data-g="' + (g || 'none') + '"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
  }

  function activate(el) {
    if (el.dataset.kind === 'city') {
      var c = rowsShown[+el.dataset.i];
      if (c) { map.setView([c.lat, c.lon], 13); if (narrow()) sheet('peek'); }
      return;
    }
    select(el.dataset.id, false);
  }

  function bindRows() {
    var all = document.querySelectorAll('.ev-row');
    Array.prototype.forEach.call(all, function (el, i) {
      el.onclick = function () { activate(el); };
      el.onmouseenter = function () { if (el.dataset.id) hover(el.dataset.id, false); };
      el.onmouseleave = function () { hover(null, false); };
      el.onkeydown = function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(el); }
        else if (e.key === 'ArrowDown' && all[i + 1]) { e.preventDefault(); all[i + 1].focus(); }
        else if (e.key === 'ArrowUp' && all[i - 1]) { e.preventDefault(); all[i - 1].focus(); }
      };
    });
  }


  /* ============================================================ parking */
  /* One map, two things to show. Parking mode draws the garages and P+R
     sites the rest of the site already knows (rdw-data.js: 323 facilities
     with published 1 h / 3 h / 24 h drive-in tariffs and their own pages),
     priced for the same session with the same card and tiles. */
  function syncChips(show) {
    Array.prototype.forEach.call(document.querySelectorAll('.ev-chips'), function (c) {
      c.hidden = !show;
      Array.prototype.forEach.call(c.querySelectorAll('button'), function (b) {
        var only = b.dataset.only;
        b.hidden = !!only && only !== showMode;
      });
    });
  }

  function setShowMode(m, silent) {
    if (m !== 'parking' && m !== 'chargers') return;
    showMode = m;
    track('mode', { mode: m });
    $('#evApp').dataset.mode = m;
    Array.prototype.forEach.call(document.querySelectorAll('.ev-modes button'), function (b) {
      b.setAttribute('aria-pressed', b.dataset.mode === m ? 'true' : 'false');
    });
    clearSelection();
    if (m === 'parking') {
      stat('mCheapL', 'cheapest for this stop'); stat('mKwhL', 'typical price per hour');
      stat('mParkL', 'P+R sites in view'); stat('mFastL', 'spaces in view');
      $('#evSearch').placeholder = 'Town, address or postcode';
    } else {
      stat('mCheapL', 'cheapest stop in view'); stat('mKwhL', 'typical price per kWh');
      stat('mParkL', 'parking for this stop'); stat('mFastL', 'fast chargers, 50 kW+');
      $('#evSearch').placeholder = 'Town, address or postcode';
      if (placeLayer) { map.removeLayer(placeLayer); placeLayer = null; }
    }
    if (!silent && map) { updateUrl(); refresh(); }
  }

  function loadPlaces(done) {
    if (places) { done(); return; }
    /* rdw-data.js declares a top-level const, which is a global binding but
       not a window property; typeof is the only safe way to see it. */
    function data() { return typeof RDW_DATA !== 'undefined' ? RDW_DATA : window.RDW_DATA; }
    function flatten() {
      places = [];
      var D = data() || {};
      for (var city in D) {
        D[city].forEach(function (g) {
          var pr = g.pr || /p\+r|park.?and.?ride/i.test(g.name);
          var rec = { _place: true, id: 'p:' + g.slug, name: g.name, city: city, slug: g.slug,
                      kind: pr ? 'pr' : 'garage', lat: g.lat, lon: g.lng, cap: g.capacity, ev: g.ev_points,
                      h: g.max_height_cm, rate_hr: g.rate_hr, rate_3h: g.rate_3h, rate_day: g.rate_day, op: g.op };
          places.push(rec); byId[rec.id] = rec;
        });
      }
      done();
    }
    if (data()) { flatten(); return; }
    var js = document.createElement('script');
    js.src = '/rdw-data.js';
    js.onload = flatten;
    js.onerror = function () { $('#evRows').innerHTML = empty('Parking data did not load', 'Reload the page to try again.'); };
    document.head.appendChild(js);
  }

  /* Drive-in cost through the published 1 h / 3 h / 24 h points, the same
     estimate the parking search uses. */
  function estCost(g, mins) {
    if (g.rate_hr == null) return null;
    var h1 = g.rate_hr, h3 = g.rate_3h != null ? g.rate_3h : h1 * 3, d1 = g.rate_day != null ? g.rate_day : h1 * 24;
    function upTo24(m) {
      if (m <= 0) return 0;
      if (m <= 60) return h1 * (m / 60 < .5 ? .5 : m / 60);
      if (m <= 180) return h1 + (h3 - h1) * (m - 60) / 120;
      return h3 + (d1 - h3) * (m - 180) / 1260;
    }
    if (mins <= 1440) return upTo24(mins);
    var days = Math.floor(mins / 1440), rem = mins % 1440;
    return days * d1 + Math.min(upTo24(rem), d1);
  }
  function placePrice(g, w) {
    var c = estCost(g, (w.l - w.a) / 60000);
    return c == null ? null : { park: c, charge: null, total: c };
  }
  function placeGrade(g, median) {
    if (!g._p) return 'none';
    if (g._p.total === 0) return 'lo';
    if (median == null) return 'mid';
    return g._p.total <= median * .8 ? 'lo' : g._p.total >= median * 1.25 ? 'hi' : 'mid';
  }

  function legend(kind) {
    var lg = document.getElementById('evLegend');
    if (!lg) return;
    lg.innerHTML = kind === 'pins'
      ? '<b>Price for your stop</b><div><i class="is-hub">F</i> Fast hub 150 kW+, operator badge</div><div><i style="background:#168A68"></i> Below typical</div><div><i style="background:#17243A"></i> Around typical</div><div><i style="background:#B45309"></i> Above typical</div><div><i class="is-fault"></i> Red ring: reported out of order</div>'
      : '<b>Charge point status</b><div><i style="background:#168A68"></i> Working, no faults reported</div><div><i style="background:#DC2626"></i> Reported out of order</div><div><i style="background:#7C8DB5"></i> Status not published</div>';
  }

  function refreshParking(b) {
    $('#evHint').classList.remove('is-on');
    var sorts = document.querySelector('.ev-sort'); if (sorts) sorts.hidden = !origin;
    syncChips(true);
    var lg = document.querySelector('.ev-legend'); if (lg) lg.hidden = true;
    $('#evArea').hidden = true;
    if (layer) { map.removeLayer(layer); layer = null; }
    if (cityLayer) { map.removeLayer(cityLayer); cityLayer = null; }
    if (hubLayer) { map.removeLayer(hubLayer); hubLayer = null; }
    loadPlaces(function () { drawPlaces(map.getBounds()); });
  }

  function drawPlaces(b) {
    if (!places) return;
    var w = currentWindow();
    var rows = places.filter(function (g) { return b.contains([g.lat, g.lon]); });
    rows.forEach(function (g) { g._p = placePrice(g, w); });
    var totals = rows.filter(function (g) { return g._p; }).map(function (g) { return g._p.total; }).sort(function (a, c) { return a - c; });
    var median = totals.length ? totals[Math.floor(totals.length / 2)] : null;
    rows = rows.filter(function (g) {
      if (filters.pr && g.kind !== 'pr') return false;
      if (filters.garage && g.kind === 'pr') return false;
      if (filters.free && !(g._p && g._p.total === 0)) return false;
      if (filters.cheap && !(g._p && median != null && g._p.total <= median)) return false;
      return true;
    });
    if (placeLayer) map.removeLayer(placeLayer);
    placeLayer = L.layerGroup();
    markers = {};
    var pills = map.getZoom() >= 12;
    rows.forEach(function (g) {
      var m;
      if (pills && g._p) {
        m = L.marker([g.lat, g.lon], { icon: L.divIcon({ className: 'ev-pinwrap',
          html: '<span class="ev-pin" data-kind="' + g.kind + '" data-g="' + placeGrade(g, median) + '">' + money(g._p.total) + '</span>',
          iconSize: null, iconAnchor: [0, 0] }), riseOnHover: true });
      } else {
        m = L.circleMarker([g.lat, g.lon], { radius: markerRadius() + 1, weight: 1.5, color: '#fff',
          fillColor: g.kind === 'pr' ? '#365FEA' : '#17243A', fillOpacity: .95 });
      }
      m.on('click', function () { select(g.id, true); });
      m.on('mouseover', function () { hover(g.id, true); });
      m.on('mouseout', function () { hover(null, true); });
      m.bindTooltip(esc(g.name), { direction: 'top', opacity: .95 });
      markers[g.id] = m;
      placeLayer.addLayer(m);
    });
    placeLayer.addTo(map);
    if (selected && markers[selected]) styleMarker(selected, 'selected');
    listPlaces(rows, w, median);
  }

  function listPlaces(rows, w, median) {
    rows.forEach(function (g) { g._d = distKm(g.lat, g.lon); });
    rows = rows.slice().sort(function (a, c) {
      if (sortKey === 'near' && origin) return (a._d || 0) - (c._d || 0);
      return (a._p ? a._p.total : Infinity) - (c._p ? c._p.total : Infinity);
    });
    rowsShown = rows;
    var active = [];
    if (filters.pr) active.push('P+R only'); if (filters.garage) active.push('garages only');
    if (filters.free) active.push('free'); if (filters.cheap) active.push('low cost');
    $('#evMode').textContent = 'Parking in view';
    $('#evCount').textContent = rows.length.toLocaleString() + (rows.length === 1 ? ' place' : ' places') +
      (active.length ? ' (' + active.join(', ') + ')' : '') +
      (rows.length ? '' : '. The site covers 14 cities; zoom out or search a city.');
    updateSession();
    var prs = rows.filter(function (g) { return g.kind === 'pr'; });
    var hrs = rows.filter(function (g) { return g.rate_hr != null; }).map(function (g) { return g.rate_hr; }).sort(function (a, c) { return a - c; });
    var totals = rows.filter(function (g) { return g._p; }).map(function (g) { return g._p.total; }).sort(function (a, c) { return a - c; });
    stat('mCheap', totals.length ? money(totals[0]) : '–');
    stat('mKwh', hrs.length ? money(hrs[Math.floor(hrs.length / 2)]) : '–');
    stat('mPark', rows.length ? String(prs.length) : '–');
    stat('mFast', rows.length ? rows.reduce(function (n, g) { return n + (g.cap || 0); }, 0).toLocaleString() : '–');
    var label = sessionLabel(w, true).replace(/est\. \d+ kWh \+ /, 'est. ');
    $('#evRows').innerHTML = rows.length ? rows.map(function (g, i) {
      var price = g._p
        ? '<span class="ev-price" data-g="' + placeGrade(g, median) + '">' + money(g._p.total) +
          '<small>' + label + ' drive-in' + (g.rate_day != null ? ' · ' + money(g.rate_day) + '/day' : '') + '</small></span>'
        : '<span class="ev-price is-unpriced">No published price</span>';
      return '<div class="ev-row" role="option" tabindex="0" data-i="' + i + '" data-kind="station" data-id="' + esc(g.id) + '"' +
        (selected === g.id ? ' aria-selected="true"' : '') + '>' +
        '<div><div class="ev-name">' + esc(g.name) + '</div>' +
        '<div class="ev-meta">' + (g._d != null ? '<span class="ev-dist">' + distLabel(g._d) + '</span>' : '') + '<span>' + (g.kind === 'pr' ? 'P+R' : 'Garage') + '</span>' +
        (g.cap ? '<span class="ev-kw">' + g.cap.toLocaleString() + ' spaces</span>' : '') +
        (g.ev ? '<span class="ev-up" data-g="ok">' + g.ev + ' charge point' + (g.ev === 1 ? '' : 's') + '</span>' : '') +
        (g.h ? '<span>max ' + (g.h / 100).toFixed(2) + ' m</span>' : '') +
        '</div></div>' + price + '</div>';
    }).join('') : empty('No parking in view', filters.pr || filters.garage || filters.free || filters.cheap ? 'Clear a filter, or move the map.' : 'Move the map, or search a city.');
    bindRows();
  }

  function showPlaceCard(g) {
    var card = $('#evCard'), w = currentWindow(), p = placePrice(g, w);
    var lines = '';
    if (p) lines += row('Parking, ' + hhmm(w.a) + ' to ' + hhmm(w.l) + ' (drive-in)', money(p.total), placeGrade(g, null));
    else lines += row('Parking', 'Price not published', 'none');
    if (g.rate_hr != null) lines += row('First hour', money(g.rate_hr), 'none');
    if (g.rate_day != null) lines += row('24 hours', money(g.rate_day), 'none');
    card.innerHTML =
      '<button type="button" class="ev-card-x" aria-label="Close">&times;</button>' +
      '<div class="ev-card-name">' + esc(g.name) + '</div>' +
      '<div class="ev-card-meta">' + (g._d != null ? distLabel(g._d) + ' · ' : '') + (g.kind === 'pr' ? 'Park and Ride' : 'Parking garage') +
        (g.op ? ' · ' + esc(g.op) : '') + (g.cap ? ' · ' + g.cap.toLocaleString() + ' spaces' : '') +
        (g.h ? ' · max height ' + (g.h / 100).toFixed(2) + ' m' : '') + '</div>' +
      (g.ev ? '<div class="ev-card-status" data-g="ok"><i></i>' + g.ev + ' EV charge point' + (g.ev === 1 ? '' : 's') + ' inside</div>' : '') +
      '<div class="ev-card-rows">' + lines + '</div>' +
      '<div class="ev-card-note">Drive-in estimate through the published 1 h, 3 h and 24 h tariffs for ' + sessionLabel(w, false).replace(/^\d+ kWh and a /, 'a ') +
        '. Pre-booking online is often cheaper.</div>' +
      '<div class="ev-card-act">' + directions(g.lat, g.lon) +
        (g.slug ? '<a class="ev-card-btn" href="/garage/' + esc(g.slug) + '">Details &amp; rates</a>' : '<button type="button" class="ev-card-btn" id="evCardWindow">Change session</button>') +
      '</div>';
    card.hidden = false;
    card.querySelector('.ev-card-x').onclick = clearSelection;
    var cw = $('#evCardWindow');
    if (cw) cw.onclick = function () { var d = $('#evWindow'); if (d) d.open = true; $('#evArrive').focus(); };
  }

  /* Addresses go to Photon (OpenStreetMap data) when no town matches. */
  var geoMarker = null;
  /* Dutch postcodes and addresses go to PDOK's Locatieserver (Kadaster, keyless,
     authoritative for NL); anything it does not know falls back to Photon. */
  function geocode(q) {
    $('#evCount').textContent = 'Looking up “' + q + '”…';
    var pc = q.replace(/\s+/g, '').toUpperCase();
    var isPostcode = /^\d{4}[A-Z]{0,2}$/.test(pc);
    var hasNumber = /\d/.test(q);
    function pdok() {
      return fetch('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free?rows=1&fl=weergavenaam,centroide_ll,type&q=' +
            encodeURIComponent(isPostcode ? pc : q) + '&fq=type:(' + (isPostcode ? 'postcode OR adres' : 'adres OR postcode OR woonplaats') + ')')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          var d = j && j.response && j.response.docs && j.response.docs[0];
          var m = d && /POINT\(([-\d.]+) ([-\d.]+)\)/.exec(d.centroide_ll || '');
          return m ? { ll: [parseFloat(m[2]), parseFloat(m[1])], name: d.weergavenaam, zoom: d.type === 'postcode' && pc.length === 4 ? 14 : d.type === 'woonplaats' ? 13 : 15 } : null;
        });
    }
    function photon() {
      return fetch('https://photon.komoot.io/api/?q=' + encodeURIComponent(q) + '&limit=1&lang=en&bbox=3.2,50.7,7.3,53.6')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) {
          var f = p && p.features && p.features[0];
          return f ? { ll: [f.geometry.coordinates[1], f.geometry.coordinates[0]], name: f.properties.name || q, zoom: 15 } : null;
        });
    }
    /* postcodes and house numbers: the Kadaster; place names and venues: OpenStreetMap */
    var first = (isPostcode || hasNumber) ? pdok : photon, second = first === pdok ? photon : pdok;
    first().then(function (hit) { return hit || second(); })
      .then(function (hit) {
        if (!hit) { searchType(q); return; }
        var ll = hit.ll, f = { properties: { name: hit.name } };
        setOrigin(ll);
        if (geoMarker) map.removeLayer(geoMarker);
        geoMarker = L.circleMarker(ll, { radius: 9, weight: 3, color: '#fff', fillColor: '#FFBC42', fillOpacity: 1 })
          .bindTooltip(esc(f.properties.name || q), { direction: 'top' }).addTo(map);
        zoomed = true;
        map.setView(ll, hit.zoom);
        if (narrow()) sheet('peek');
      })
      .catch(function () { searchType(q); });
  }

  /* --------------------------------------------------------------- init */
  function syncWindow() {
    var a = $('#evArrive'), l = $('#evLeave');
    var ad = new Date(a.value), ld = new Date(l.value);
    if (isNaN(ad.getTime()) || isNaN(ld.getTime()) || ld <= ad) return;
    a.dataset.stamp = stamp(ad);
    l.dataset.stamp = stamp(ld);
    updateUrl();
    repriceAll();
  }

  function updateUrl() {
    if (!window.history.replaceState || !map || $('#evApp').classList.contains('is-embed')) return;
    var c = map.getCenter(), w = currentWindow();
    window.history.replaceState({}, '', location.pathname +
      '?lat=' + c.lat.toFixed(5) + '&lng=' + c.lng.toFixed(5) + '&zoom=' + map.getZoom() +
      '&arriving=' + stamp(w.a) + '&leaving=' + stamp(w.l) + '&kwh=' + w.kwh + (showMode === 'parking' ? '&mode=parking' : ''));
  }

  function repriceAll() {
    updateSession();
    if (showMode === 'parking') drawPlaces(map.getBounds());
    else if (mode === 'detail') drawStations(map.getBounds());
    if (selected && byId[selected]) showCard(byId[selected]);
  }

  /* Town search runs over all towns, not just the ones in view. Typing
     filters the list; Enter or a row jumps to the town. */
  function matches(q) {
    q = q.toLowerCase();
    var exact = [], partial = [];
    for (var i = 0; i < cities.length; i++) {
      var n = cities[i].name.toLowerCase();
      if (n === q) exact.push(cities[i]);
      else if (n.indexOf(q) === 0) partial.unshift(cities[i]);
      else if (n.indexOf(q) !== -1) partial.push(cities[i]);
    }
    return exact.concat(partial);
  }

  function searchType(q) {
    q = (q || '').trim();
    if (q.length < 2) { if (map) refresh(); return; }
    var hits = matches(q);
    listCities(hits, 'Town search', hits.length
      ? hits.length.toLocaleString() + ' of ' + cities.length.toLocaleString() + ' towns match “' + q + '”'
      : 'No town found for “' + q + '”. Try another spelling.');
    if (!hits.length) $('#evRows').innerHTML = empty('No matching town', 'Try a broader part of the town name.');
  }

  function searchGo(q) {
    q = (q || '').trim();
    if (!q) return;
    track('search', { term: q, mode: showMode });
    var hit = matches(q)[0];
    if (hit) {
      map.setView([hit.lat, hit.lon], 13);
      zoomed = true;
      scheduleRefresh();
      if (narrow()) sheet('peek');
    } else {
      geocode(q);
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
    $('#evKwh').addEventListener('input', repriceAll);
    updateSession();
    if (narrow()) { var d = $('#evWindow'); if (d) d.open = false; }

    var sorts = document.querySelectorAll('.ev-sort button');
    Array.prototype.forEach.call(sorts, function (btn) {
      btn.onclick = function () {
        sortKey = btn.dataset.sort;
        track('sort', { sort: sortKey });
        Array.prototype.forEach.call(sorts, function (b2) {
          b2.setAttribute('aria-pressed', b2 === btn ? 'true' : 'false');
        });
        if (mode === 'detail') drawStations(map.getBounds());
      };
    });
    Array.prototype.forEach.call(document.querySelectorAll('.ev-modes button'), function (btn) {
      btn.onclick = function () { setShowMode(btn.dataset.mode); };
    });
    var startMode = q.get('mode') || $('#evApp').dataset.startMode;
    if (startMode === 'parking') setShowMode('parking', true);
    var chips = document.querySelectorAll('.ev-chips button');
    Array.prototype.forEach.call(chips, function (btn) {
      btn.onclick = function () {
        var f = btn.dataset.f;
        filters[f] = !filters[f];
        track('filter', { filter: f, on: filters[f] });
        Array.prototype.forEach.call(document.querySelectorAll('.ev-chips button[data-f="' + f + '"]'), function (b2) {
          b2.setAttribute('aria-pressed', filters[f] ? 'true' : 'false');
        });
        if (showMode === 'parking') drawPlaces(map.getBounds());
        else if (mode === 'detail') drawStations(map.getBounds());
      };
    });

    var box = $('#evSearch'), typeTimer = null;
    box.addEventListener('input', function () {
      clearTimeout(typeTimer);
      typeTimer = setTimeout(function () { searchType(box.value); }, 120);
    });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); searchGo(box.value); }
      if (e.key === 'Escape') { box.value = ''; refresh(); }
    });
    $('#evGo').onclick = function () { searchGo(box.value); };
    /* desktop: drag the panel edge to make it wider; remembered per browser */
    var rz = $('#evResizer'), app0 = $('#evApp');
    if (rz && app0) {
      try { var saved = parseInt(localStorage.getItem('evPanelW'), 10); if (saved >= 340 && saved <= 720) app0.style.setProperty('--ev-panel', saved + 'px'); } catch (e) {}
      rz.addEventListener('mousedown', function (e) {
        e.preventDefault();
        var startX = e.clientX, startW = app0.querySelector('.ev-panel').offsetWidth;
        function move(ev) {
          var w = Math.max(340, Math.min(720, startW + (ev.clientX - startX)));
          app0.style.setProperty('--ev-panel', w + 'px');
        }
        function up() {
          document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
          document.body.style.cursor = '';
          try { localStorage.setItem('evPanelW', app0.querySelector('.ev-panel').offsetWidth); } catch (e) {}
          if (map) map.invalidateSize();
        }
        document.body.style.cursor = 'col-resize';
        document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
      });
    }
    var handle = $('#evHandle');
    if (handle) {
      handle.onclick = sheetToggle; sheet('peek');
      var y0 = null;
      handle.addEventListener('touchstart', function (e) { y0 = e.touches[0].clientY; }, { passive: true });
      handle.addEventListener('touchend', function (e) {
        if (y0 == null) return;
        var dy = e.changedTouches[0].clientY - y0; y0 = null;
        if (dy < -30) sheet('full'); else if (dy > 30) sheet('peek');
      }, { passive: true });
    }
    if (narrow()) {
      /* results first; the calculator becomes a secondary "adjust" control under the list */
      var win = $('#evWindow'), foot = document.querySelector('.ev-foot');
      if (win && foot) { win.classList.add('is-after'); foot.parentNode.insertBefore(win, foot); win.querySelector('summary').innerHTML = 'Adjust cost estimate <small id="evSessionSummary"></small>'; updateSession(); }
    }
    /* typing in the sheet's search box needs the sheet open */
    box.addEventListener('focus', function () { if (narrow()) sheet('full'); });
    $('#evArea').onclick = function () { $('#evArea').hidden = true; refresh(); };

    var lat = parseFloat(q.get('lat')), lng = parseFloat(q.get('lng')), zoom = parseInt(q.get('zoom'), 10);
    var start = (isNaN(lat) || isNaN(lng)) ? [52.3731, 4.8926] : [lat, lng];   // Amsterdam unless the link says otherwise
    map = L.map('evmap', { scrollWheelZoom: true, preferCanvas: true }).setView(start, isNaN(zoom) ? 14 : zoom);
    if (q.get('kwh')) $('#evKwh').value = q.get('kwh');
    window.__evMap = map;                       // the mobile tabs resize it
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19
    }).addTo(map);
    map.on('zoomstart', function () { zoomed = true; });
    map.on('moveend', onMoveEnd);
    updateUrl();
    refresh();
    bindHeaderSearch();
    /* deep links: garage pages send ?q=&lat=&lng=, the old search sent ?q= */
    var q0 = (q.get('q') || '').trim();
    if (!isNaN(lat) && !isNaN(lng) && q0) {
      setOrigin([lat, lng]);
      if (geoMarker) map.removeLayer(geoMarker);
      geoMarker = L.circleMarker([lat, lng], { radius: 9, weight: 3, color: '#fff', fillColor: '#FFBC42', fillOpacity: 1 })
        .bindTooltip(esc(q0), { direction: 'top' }).addTo(map);
      $('#evSearch').value = q0;
    } else if (q0 && q0 !== 'Near me') {
      $('#evSearch').value = q0;
      searchGo(q0);
    } else if (q0 === 'Near me') {
      goHere();
    }
  }

  /* On this page the header's search bar and Near me act on the charger
     map, not the parking search: a town name jumps the map, Near me centres
     it on the visitor and marks where they are. */
  var hereMarker = null;
  function goHere() {
    track('near_me', { mode: showMode });
    var btn = document.querySelector('.nav-near') || document.getElementById('evNear'), label = btn ? btn.innerHTML : '';
    if (!navigator.geolocation) { searchGo(''); return; }
    if (btn) { btn.disabled = true; btn.setAttribute('aria-busy', 'true'); }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var ll = [pos.coords.latitude, pos.coords.longitude];
      setOrigin(ll);
      if (hereMarker) map.removeLayer(hereMarker);
      hereMarker = L.circleMarker(ll, { radius: 9, weight: 3, color: '#fff', fillColor: '#365FEA', fillOpacity: 1 })
        .bindTooltip('You are here', { direction: 'top' }).addTo(map);
      zoomed = true;
      map.setView(ll, 15);
      if (narrow()) sheet('peek');
      if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); }
    }, function () {
      if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); }
      $('#evCount').textContent = 'Location not available. Search a town instead.';
    }, { timeout: 8000, maximumAge: 60000 });
  }

  function bindHeaderSearch() {
    /* The homepage hero is a second front door to the same app. */
    var hero = document.getElementById('heroQ'), heroNear = document.querySelector('.hero-near');
    if (hero && hero.form) {
      hero.form.onsubmit = function (e) {
        e.preventDefault();
        var v = hero.value.trim();
        if (!v) { hero.focus(); return; }
        $('#evSearch').value = v;
        searchGo(v);
        $('#evApp').scrollIntoView({ behavior: 'smooth', block: 'start' });
      };
    }
    if (heroNear) heroNear.onclick = function () { goHere(); $('#evApp').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
    var form = document.querySelector('form.nav-search'), near = document.querySelector('.nav-near'), q = document.getElementById('navQ');
    if (form) {
      form.onsubmit = function (e) {
        e.preventDefault();
        var v = (q && q.value || '').trim();
        if (!v) { if (q) q.focus(); return; }
        $('#evSearch').value = v;
        searchGo(v);
      };
      if (q) q.placeholder = 'Search a town for chargers, e.g. Utrecht';
    }
    if (near) near.onclick = goHere;
    var pnear = document.getElementById('evNear');
    if (pnear) pnear.onclick = goHere;
    var loc = document.getElementById('evLocate');
    if (loc) loc.onclick = goHere;
  }

  function stat(id, v) {
    var el = document.getElementById(id);
    if (el) el.textContent = v;
  }
  (function mirrorCount() {
    var src = document.getElementById('evCount'), dst = document.getElementById('evHandleText');
    if (!src || !dst || !window.MutationObserver) return;
    new MutationObserver(function () { dst.textContent = src.textContent.split('.')[0].split(' ·')[0]; }).observe(src, { childList: true, characterData: true, subtree: true });
  })();

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
        updateMetaNational();

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
