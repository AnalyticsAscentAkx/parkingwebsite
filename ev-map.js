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

  var map, cities = [], tariffs = {}, meta = {};
  var tiles = {}, tileFailures = {}, layer, cityLayer, markers = {}, byId = {};
  var selected = null, mode = 'overview', sortKey = 'reliable';
  var filters = { fast: false, faulty: false, priced: false };
  var rowsShown = [], moveTimer = null, zoomed = false, hovered = null;

  /* Station record is positional, which roughly halves the tile size:
     0 id, 1 name, 2 operator, 3 lat, 4 lon, 5 kW, 6 points,
     7 uptime, 8 price per kWh, 9 parking area id, 10 points down now,
     11 price source: 0 this charger's tariff, 1 operator's usual rate,
        2 national median (operator publishes nothing) */
  var ID = 0, NAME = 1, CPO = 2, LAT = 3, LON = 4, KW = 5,
      PTS = 6, UP = 7, PPK = 8, AREA = 9, DOWN = 10, SRC = 11;
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
    return g === 'ok' ? '#059669' : g === 'warn' ? '#D97706'
         : g === 'bad' ? '#DC2626' : '#7C8DB5';
  }
  function narrow() { return window.innerWidth <= 900; }
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
    var el = $('#evSession');
    if (el) el.textContent = 'Estimates assume ' + sessionLabel(currentWindow(), false) + '. * = operator\u2019s usual rate, no tariff published for that charger.';
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
    $('#evHint').textContent = 'Each circle is a town; larger circles have more locations. Select a town to zoom in.';
    $('#evHint').classList.toggle('is-on', mode === 'overview');
    var sorts = document.querySelector('.ev-sort');
    if (sorts) sorts.hidden = mode !== 'detail';
    var chips = document.querySelector('.ev-chips');
    if (chips) chips.hidden = mode !== 'detail';
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = mode !== 'detail' || !!selected;   // colour only means status up close
    $('#evArea').hidden = true;

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
        weight: 1.5, color: '#fff', fillColor: '#2337C6', fillOpacity: .62
      });
      m.bindTooltip(esc(c.name) + ': ' + c.n.toLocaleString() + ' locations',
                    { direction: 'top' });
      m.on('click', function () { map.setView([c.lat, c.lon], 13); });
      cityLayer.addLayer(m);
    });
    cityLayer.addTo(map);
    listCities(inView, 'Towns in view');
  }

  function stationRows(b) {
    var rows = [];
    for (var k in tiles) {
      var t = tiles[k];
      if (!t) continue;
      for (var i = 0; i < t.length; i++) {
        var st = t[i];
        if (!b.contains([st[LAT], st[LON]])) continue;
        if (filters.fast && !(st[KW] >= FAST_KW)) continue;
        if (filters.faulty && !(st[DOWN] > 0)) continue;
        if (filters.priced && st[PPK] == null) continue;
        rows.push(st);
        if (rows.length >= MAX_MARKERS) return rows;
      }
    }
    return rows;
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
    var pills = map.getZoom() >= PIN_ZOOM;
    rows.forEach(function (st) {
      var p = pills ? priceOf(st, w) : null, m;
      if (p) {
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
      m.bindTooltip(esc(st[NAME]), { direction: 'top', opacity: .95 });
      markers[st[ID]] = m;
      layer.addLayer(m);
    });
    layer.addTo(map);
    if (selected && markers[selected]) styleMarker(selected, 'selected');
    listStations(rows, w);
  }

  function pinIcon(p, g, faulty) {
    return L.divIcon({
      className: 'ev-pinwrap',
      html: '<span class="ev-pin" data-g="' + g + (faulty ? '" data-faulty="1' : '') + '">' + money(p.total) + '</span>',
      iconSize: null, iconAnchor: [0, 0]
    });
  }

  function styleMarker(id, state) {
    var m = markers[id];
    if (!m) return;
    if (m.setStyle) {
      var r = markerRadius();
      if (state === 'selected') m.setStyle({ radius: r + 4, weight: 3, color: '#0B1120' }).bringToFront();
      else if (state === 'hover') m.setStyle({ radius: r + 2, weight: 2.5, color: '#0B1120' }).bringToFront();
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
    rows.sort(function (a, b) {
      if (sortKey === 'cheap') {
        return (a._p ? a._p.total : Infinity) - (b._p ? b._p.total : Infinity);
      }
      if (sortKey === 'fast') return (b[KW] || 0) - (a[KW] || 0);
      if ((a[DOWN] > 0) !== (b[DOWN] > 0)) return a[DOWN] > 0 ? 1 : -1;
      return (b[UP] == null ? -1 : b[UP]) - (a[UP] == null ? -1 : a[UP]);
    });
    rowsShown = rows;

    var active = [];
    if (filters.fast) active.push(FAST_KW + ' kW+');
    if (filters.faulty) active.push('reported faulty');
    if (filters.priced) active.push('with a published price');
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
        '<div class="ev-meta"><span>' + esc(st[CPO] || 'Operator not published') + '</span>' +
        (st[KW] ? '<span class="ev-kw">' + st[KW] + ' kW</span>' : '') +
        '<span class="ev-up" data-g="' + g + '">' +
          (st[DOWN] > 0 ? st[DOWN] + ' reported out of order'
           : st[UP] == null ? 'No fault reported' : st[UP].toFixed(1) + '% uptime') +
        '</span></div>' +
        '</div>' + price + '</div>';
    }).join('') : empty('No chargers match', filters.fast || filters.faulty || filters.priced
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
    showCard(byId[id]);
    if (!fromMap && narrow()) {
      var tab = $('#tabMap');
      if (tab) tab.click();           // the card sits over the map
    }
  }

  function clearSelection() {
    if (selected && markers[selected]) styleMarker(selected, 'normal');
    selected = null;
    var all = document.querySelectorAll('.ev-row[aria-selected="true"]');
    for (var i = 0; i < all.length; i++) all[i].setAttribute('aria-selected', 'false');
    $('#evCard').hidden = true;
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = mode !== 'detail';
  }

  function showCard(st) {
    var card = $('#evCard');
    if (!st) { card.hidden = true; return; }
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
      '<div class="ev-card-meta">' + esc(st[CPO] || 'Operator not published') +
        (st[KW] ? ' · up to ' + st[KW] + ' kW' : ' · power not published') +
        ' · ' + st[PTS] + ' charge point' + (st[PTS] === 1 ? '' : 's') + '</div>' +
      '<div class="ev-card-status" data-g="' + g + '"><i></i>' + status +
        '<small>Reported by the operator ' + reportedAt() + '. Occupancy is not published.</small></div>' +
      '<div class="ev-card-rows">' + lines +
        (p ? '<div class="ev-card-row is-total" data-g="' + ppkGrade(st[PPK]) + '"><span>Estimated total</span><b>' + money(p.total) + '</b></div>' : '') +
      '</div>' +
      '<div class="ev-card-note">' + (srcNote(st, false) ? srcNote(st, false) + ' ' : '') + 'Estimate for ' + sessionLabel(w, false) +
        '. Connector types are not in the register; check the operator app before relying on a fast charge.</div>' +
      '<div class="ev-card-act">' +
        '<a class="ev-card-btn is-primary" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' +
          st[LAT] + ',' + st[LON] + '">Directions</a>' +
        '<button type="button" class="ev-card-btn" id="evCardWindow">Change session</button>' +
      '</div>';
    card.hidden = false;
    var lg = document.querySelector('.ev-legend');
    if (lg) lg.hidden = true;
    card.querySelector('.ev-card-x').onclick = clearSelection;
    $('#evCardWindow').onclick = function () {
      var d = $('#evWindow'); if (d) d.open = true;
      if (narrow()) { var t = $('#tabList'); if (t) t.click(); }
      $('#evArrive').focus();
    };
  }

  function row(label, value, g) {
    return '<div class="ev-card-row" data-g="' + (g || 'none') + '"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
  }

  function activate(el) {
    if (el.dataset.kind === 'city') {
      var c = rowsShown[+el.dataset.i];
      if (c) { map.setView([c.lat, c.lon], 13); if (narrow()) { var t = $('#tabMap'); if (t) t.click(); } }
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
    if (!window.history.replaceState || !map) return;
    var c = map.getCenter(), w = currentWindow();
    window.history.replaceState({}, '', location.pathname +
      '?lat=' + c.lat.toFixed(5) + '&lng=' + c.lng.toFixed(5) + '&zoom=' + map.getZoom() +
      '&arriving=' + stamp(w.a) + '&leaving=' + stamp(w.l) + '&kwh=' + w.kwh);
  }

  function repriceAll() {
    updateSession();
    if (mode === 'detail') drawStations(map.getBounds());
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
    var hit = matches(q)[0];
    if (hit) {
      map.setView([hit.lat, hit.lon], 13);
      zoomed = true;
      scheduleRefresh();
      if (narrow()) { var t = $('#tabMap'); if (t) t.click(); }
    } else {
      searchType(q);
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
        Array.prototype.forEach.call(sorts, function (b2) {
          b2.setAttribute('aria-pressed', b2 === btn ? 'true' : 'false');
        });
        if (mode === 'detail') drawStations(map.getBounds());
      };
    });
    var chips = document.querySelectorAll('.ev-chips button');
    Array.prototype.forEach.call(chips, function (btn) {
      btn.onclick = function () {
        var f = btn.dataset.f;
        filters[f] = !filters[f];
        btn.setAttribute('aria-pressed', filters[f] ? 'true' : 'false');
        if (mode === 'detail') drawStations(map.getBounds());
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
