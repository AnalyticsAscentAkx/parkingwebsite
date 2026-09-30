/* Choropleth of EV share and public charge points per 100 EVs, per municipality. */
(function () {
  var L_ = window.EA_LABELS || {};
  var el = document.getElementById('eamap'); if (!el) return;
  var metric = 'share', geo = null, layer = null, map = null;
  var RAMP = ['#E8ECFA', '#BFC9F2', '#8E9EE8', '#5F73DC', '#3A4FD0', '#2337C6', '#16247F'];
  var BREAKS = { share: [10, 12, 14, 16, 18, 21, 24], ratio: [1, 2, 3, 4, 6, 8, 12] };
  function fmt(v, m) { if (v == null) return L_.na; var s = (m === 'share' ? v.toFixed(1) + '%' : v.toFixed(1)); return L_.lang === 'nl' ? s.replace('.', ',') : s; }
  function fmtInt(v) { return v == null ? L_.na : v.toLocaleString(L_.lang === 'nl' ? 'nl-NL' : 'en-GB'); }
  function color(v, m) { if (v == null) return '#F3F5F9'; var b = BREAKS[m], i = 0; while (i < b.length && v >= b[i]) i++; return RAMP[Math.min(i, RAMP.length - 1)]; }
  function style(f) { var v = metric === 'share' ? f.properties.s : f.properties.r; return { fillColor: color(v, metric), weight: 0.6, color: '#fff', fillOpacity: 0.9 }; }
  function legend() {
    var b = BREAKS[metric], h = '<span>' + (L_[metric]) + '</span>';
    h += '<i style="background:' + RAMP[0] + '" title="&lt; ' + b[0] + '"></i>';
    for (var i = 0; i < b.length; i++) h += '<i style="background:' + RAMP[Math.min(i + 1, RAMP.length - 1)] + '" title="' + b[i] + (b[i + 1] ? ' to ' + b[i + 1] : '+') + '"></i>';
    h += '<span>' + fmt(b[0], metric) + ' to ' + fmt(b[b.length - 1], metric) + '+</span>';
    document.getElementById('eaLegend').innerHTML = h;
  }
  function info(p) {
    var box = document.getElementById('eaInfo');
    if (!p) { box.innerHTML = '<b>' + (L_.lang === 'nl' ? 'Nederland' : 'Netherlands') + '</b><small>' + L_.hint + '</small>'; return; }
    box.innerHTML = '<b>' + p.n + '</b>' + L_.share + ': <strong>' + fmt(p.s, 'share') + '</strong><br>' + L_.evs + ': ' + fmtInt(p.e) + '<br>' + L_.points + ': ' + fmtInt(p.p) + '<br>' + L_.ratio + ': <strong>' + fmt(p.r, 'ratio') + '</strong><br><small>' + L_.pop + ': ' + fmtInt(p.pop) + '</small>';
  }
  function draw() {
    if (layer) map.removeLayer(layer);
    layer = L.geoJSON(geo, { style: style, onEachFeature: function (f, l) {
      l.on('mouseover', function () { l.setStyle({ weight: 2, color: '#0B1120' }); l.bringToFront(); info(f.properties); });
      l.on('mouseout', function () { layer.resetStyle(l); });
      l.on('click', function () { info(f.properties); if (window.track) window.track('ev_adoption_select', { municipality: f.properties.n, metric: metric }); });
    } }).addTo(map);
    legend();
  }
  function boot() {
    map = L.map('eamap', { scrollWheelZoom: false, zoomSnap: 0.25 }).setView([52.2, 5.3], 7);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/light_nolabels/{z}/{x}/{y}{r}.png', { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CARTO · CBS/PDOK · charge points: NDW / DOT-NL', maxZoom: 12 }).addTo(map);
    fetch('/ev-data/gemeenten-ev.json').then(function (r) { return r.json(); }).then(function (g) { geo = g; draw(); map.fitBounds(layer.getBounds(), { padding: [6, 6] }); });
    Array.prototype.forEach.call(document.querySelectorAll('.ea-ctl button'), function (b) {
      b.onclick = function () {
        metric = b.dataset.metric;
        Array.prototype.forEach.call(document.querySelectorAll('.ea-ctl button'), function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        if (geo) draw();
        if (window.track) window.track('ev_adoption_metric', { metric: metric });
      };
    });
  }
  var css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'; document.head.appendChild(css);
  var js = document.createElement('script'); js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'; js.onload = boot; document.head.appendChild(js);
})();
