/* ============================================
   PARKING NETHERLANDS — Shared JS
   Built by Analytics Ascent
   ============================================ */

// Mobile menu
function toggleMenu(){document.querySelector('.nl').classList.toggle('open');}
// FAQ
document.addEventListener('click',e=>{const q=e.target.closest('.fqq');if(q)q.parentElement.classList.toggle('open');});

// ---- MAP UTILITIES ----
function mkI(c,l){return L.divIcon({html:`<svg xmlns="http://www.w3.org/2000/svg" width="36" height="46" viewBox="0 0 36 46"><path d="M18 0C8.1 0 0 8.1 0 18c0 13.5 18 28 18 28s18-14.5 18-28C36 8.1 27.9 0 18 0z" fill="${c}" filter="drop-shadow(0 2px 4px rgba(0,0,0,.3))"/><circle cx="18" cy="17" r="9" fill="white" opacity=".95"/><text x="18" y="21" text-anchor="middle" font-size="11" font-weight="bold" fill="${c}" font-family="DM Sans,sans-serif">${l}</text></svg>`,iconSize:[36,46],iconAnchor:[18,46],popupAnchor:[0,-40],className:''});}

function initMap(id,center,zoom){
    const m=L.map(id,{scrollWheelZoom:false,zoomControl:true}).setView(center,zoom);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',maxZoom:18}).addTo(m);
    m.on('click',()=>m.scrollWheelZoom.enable());
    m.on('mouseout',()=>m.scrollWheelZoom.disable());
    return m;
}

function addMarker(map,d,color,sym){
    const m=L.marker([d.lat,d.lng],{icon:mkI(color,sym)}).addTo(map);
    m.bindPopup(`<div style="font-family:DM Sans,sans-serif;min-width:180px;padding:6px 4px">
        <div style="font-family:Instrument Serif,serif;font-size:18px;color:#0A1628;margin-bottom:2px">${d.name}</div>
        <div style="font-size:11px;color:#94A3B8;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">${d.type||''}</div>
        <div style="font-family:Instrument Serif,serif;font-size:22px;color:${color}">${d.price}</div>
        ${d.detail?`<div style="font-size:12px;color:#64748B;margin-top:4px">${d.detail}</div>`:''}
        ${d.link?`<a href="${d.link}" style="display:block;margin-top:12px;padding:8px 16px;background:#FF6B2C;color:#fff;text-align:center;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">View Details →</a>`:''}
    </div>`);
    return m;
}

// ---- CITY DATA ----
const CITIES = {
    amsterdam: {
        name: 'Amsterdam', streetRate: '€8.05/hr', cheapGarage: '€1.25/hr', prRate: '€1.00/24hr', fine: '€72.90',
        center: [52.3600, 4.9000], zoom: 12,
        pr: [
            {name:'P+R Sloterdijk',lat:52.389,lng:4.8376,price:'€1/24hr',type:'Park + Ride · West',detail:'Train → Centre ~8min · 600 spots'},
            {name:'P+R Arena',lat:52.3123,lng:4.9423,price:'€1/24hr',type:'Park + Ride · Southeast',detail:'Metro 54 → Centre ~15min · 700 spots'},
            {name:'P+R Olympisch Stadion',lat:52.3432,lng:4.853,price:'€1/24hr',type:'Park + Ride · South',detail:'Metro → Centre ~12min · 500 spots'},
            {name:'P+R RAI',lat:52.3394,lng:4.8893,price:'€1/24hr',type:'Park + Ride · South',detail:'Metro 52 → Centre ~10min · 400 spots'},
            {name:'P+R Zeeburg',lat:52.3658,lng:4.9587,price:'€1/24hr',type:'Park + Ride · East',detail:'Tram 26 → Centre ~20min · 350 spots'},
            {name:'P+R Noord',lat:52.3914,lng:4.9235,price:'€1/24hr',type:'Park + Ride · North',detail:'Ferry/Metro → Centre ~12min · 300 spots'},
            {name:'P+R Boven \'t IJ',lat:52.3912,lng:4.9024,price:'€1/24hr',type:'Park + Ride · North',detail:'Ferry → Centre ~15min · 250 spots'},
            {name:'P+R VU MC',lat:52.334,lng:4.8627,price:'€1/24hr',type:'Park + Ride · South',detail:'Tram → Centre ~20min · 200 spots'},
        ],
        garages: [
            {name:'Mobihub Rembrandtpark',lat:52.3625,lng:4.8552,price:'€1.25/hr · €10/day',type:'Mobility Hub · West',detail:'Cheapest city garage'},
            {name:'Mobihub NDSM',lat:52.4015,lng:4.8925,price:'€2/hr · €12/day',type:'Mobility Hub · North',detail:'Free ferry to centre'},
            {name:'Q-Park Byzantium',lat:52.353,lng:4.878,price:'€4/hr · €35/day',type:'Garage · South',detail:'Pre-book for 15% off'},
            {name:'Parking Piet Hein',lat:52.3665,lng:4.92,price:'€4.50/hr · €38/day',type:'Garage · East',detail:'Waterfront location'},
            {name:'Centrum Oosterdok',lat:52.3763,lng:4.9054,price:'€5/hr · €40/day',type:'Garage · Centre',detail:'Near Central Station'},
            {name:'Q-Park Museumplein',lat:52.3566,lng:4.8787,price:'€5.50/hr · €45/day',type:'Garage · Museum Quarter',detail:'Near Rijksmuseum & Van Gogh'},
            {name:'APCOA Euro Parking',lat:52.372,lng:4.894,price:'€6/hr · €55/day',type:'Garage · Centre',detail:'Pre-book online'},
            {name:'Q-Park De Bijenkorf',lat:52.373,lng:4.893,price:'€7.50/hr · €60/day',type:'Garage · Dam Square',detail:'Most central location'},
        ],
        free: [
            {name:'Amsterdam Noord (free streets)',lat:52.398,lng:4.926,price:'FREE',type:'Free Parking',detail:'Free ferry to Centraal Station'},
            {name:'Mobihub NDSM (free + bike)',lat:52.4015,lng:4.8925,price:'FREE w/ bike rental',type:'Mobility Hub',detail:'Rent bike to continue trip'},
        ],
        zones: [
            {zone:'Centrum (Grachtengordel, Dam, Jordaan)',rate:'€8.05',hours:'24/7',cost4:'€32.20',tip:'Avoid — use P+R'},
            {zone:'Oud-West (Vondelpark area)',rate:'€7.50',hours:'24/7',cost4:'€30.00',tip:'Use Mobihub Rembrandtpark'},
            {zone:'De Pijp / Oost',rate:'€6.50',hours:'9-24 / Sun 12-24',cost4:'€26.00',tip:'Free before 9am'},
            {zone:'Zuid (Zuidas)',rate:'€5.00',hours:'Mon-Sat 9-23',cost4:'€20.00',tip:'Free Sundays'},
            {zone:'West / Bos en Lommer',rate:'€4.50',hours:'Mon-Sat 9-23',cost4:'€18.00',tip:'Varies by street'},
            {zone:'Noord',rate:'€3.50',hours:'Mon-Sat 9-21',cost4:'€14.00',tip:'Often free evenings'},
            {zone:'Nieuw-West',rate:'€2.50',hours:'Mon-Sat 9-21',cost4:'€10.00',tip:'Best street rate'},
        ]
    },
    rotterdam: {
        name: 'Rotterdam', streetRate: '€4.24/hr', cheapGarage: '€2.00/hr', prRate: '€2.50/24hr', fine: '€72.90',
        center: [51.9244, 4.4777], zoom: 13,
        pr: [
            {name:'P+R Kralingse Zoom',lat:51.9210,lng:4.5165,price:'€2.50/24hr',type:'Park + Ride · East',detail:'Metro → Centre ~10min · 450 spots'},
            {name:'P+R Slinge',lat:51.8870,lng:4.4875,price:'€2.50/24hr',type:'Park + Ride · South',detail:'Metro → Centre ~15min · 300 spots'},
            {name:'P+R Alexander',lat:51.9520,lng:4.5555,price:'€3.00/24hr',type:'Park + Ride · Northeast',detail:'Metro → Centre ~12min · 350 spots'},
            {name:'P+R Schiedam Centrum',lat:51.9195,lng:4.3985,price:'€3.50/24hr',type:'Park + Ride · West',detail:'Metro → Centre ~8min · 200 spots'},
        ],
        garages: [
            {name:'Parking Lijnbaan',lat:51.9214,lng:4.4738,price:'€2/hr · €18/day',type:'Garage · Centre',detail:'Shopping district'},
            {name:'Q-Park Markthal',lat:51.9200,lng:4.4870,price:'€3/hr · €25/day',type:'Garage · Centre',detail:'Under Markthal'},
            {name:'Parking Museumpark',lat:51.9150,lng:4.4730,price:'€2.50/hr · €20/day',type:'Garage · Museum area',detail:'Near Kunsthal & Boijmans'},
            {name:'Euromast Parking',lat:51.9055,lng:4.4665,price:'€2/hr · €15/day',type:'Garage · West',detail:'Near Het Park'},
            {name:'Parking Kruisplein',lat:51.9235,lng:4.4685,price:'€3.50/hr · €30/day',type:'Garage · Centre',detail:'Near Rotterdam Centraal'},
        ],
        free: [
            {name:'Rotterdam Zuid (free streets)',lat:51.8960,lng:4.4780,price:'FREE',type:'Free Parking',detail:'Metro to centre available'},
            {name:'Weekend parking various zones',lat:51.9180,lng:4.4500,price:'FREE weekends',type:'Free Zones',detail:'Check local signs'},
        ],
        zones: [
            {zone:'Centrum (Coolsingel, Blaak)',rate:'€4.24',hours:'Mon-Sat 9-23',cost4:'€16.96',tip:'Free Sundays'},
            {zone:'Delfshaven / West',rate:'€3.50',hours:'Mon-Sat 9-21',cost4:'€14.00',tip:'Free weekends some streets'},
            {zone:'Kralingen / Oost',rate:'€3.00',hours:'Mon-Sat 9-21',cost4:'€12.00',tip:'Use P+R Kralingse Zoom'},
            {zone:'Noord',rate:'€2.80',hours:'Mon-Sat 9-21',cost4:'€11.20',tip:'Free evenings'},
            {zone:'Zuid / Charlois',rate:'€2.00',hours:'Mon-Sat 9-18',cost4:'€8.00',tip:'Often free parking'},
        ]
    },
    'the-hague': {
        name: 'The Hague', streetRate: '€3.98/hr', cheapGarage: '€2.50/hr', prRate: '€2.00/24hr', fine: '€72.90',
        center: [52.0705, 4.3007], zoom: 13,
        pr: [
            {name:'P+R Den Haag Laan van NOI',lat:52.0810,lng:4.3260,price:'€2/24hr',type:'Park + Ride · South',detail:'Train/Tram → Centre ~8min · 300 spots'},
            {name:'P+R Hoornwijck',lat:52.0510,lng:4.3580,price:'€2.50/24hr',type:'Park + Ride · East',detail:'Bus → Centre ~15min · 250 spots'},
            {name:'P+R Forepark',lat:52.0940,lng:4.3170,price:'€3/24hr',type:'Park + Ride · North',detail:'Tram → Centre ~12min · 200 spots'},
        ],
        garages: [
            {name:'Parking Muzenplein',lat:52.0700,lng:4.3040,price:'€2.50/hr · €20/day',type:'Garage · Centre',detail:'Near Grote Markt'},
            {name:'Q-Park Malieveld',lat:52.0810,lng:4.3100,price:'€3/hr · €24/day',type:'Garage · Centre',detail:'Near Binnenhof'},
            {name:'Parking Noordeinde',lat:52.0840,lng:4.3100,price:'€3.50/hr · €28/day',type:'Garage · Centre',detail:'Near Royal Palace'},
            {name:'Parking Kijkduin',lat:52.0640,lng:4.2200,price:'€1.50/hr · €8/day',type:'Beach Parking',detail:'Summer rates vary'},
            {name:'Parking Scheveningen',lat:52.1100,lng:4.2800,price:'€3/hr · €20/day',type:'Beach Parking',detail:'Free off-peak in winter'},
        ],
        free: [
            {name:'Scheveningen (winter)',lat:52.1100,lng:4.2700,price:'FREE off-season',type:'Free Parking',detail:'November-March many spots free'},
            {name:'Outer districts',lat:52.0600,lng:4.3400,price:'FREE',type:'Free Zones',detail:'Ypenburg, Leidschenveen areas'},
        ],
        zones: [
            {zone:'Centrum (Binnenhof, Grote Markt)',rate:'€3.98',hours:'Mon-Sat 9-21',cost4:'€15.92',tip:'Free Sundays'},
            {zone:'Scheveningen (summer)',rate:'€3.50',hours:'Daily 10-20 (Apr-Sep)',cost4:'€14.00',tip:'Free in winter!'},
            {zone:'Benoordenhout',rate:'€3.00',hours:'Mon-Sat 9-18',cost4:'€12.00',tip:'Residential area'},
            {zone:'Laakkwartier / Transvaalkwartier',rate:'€2.50',hours:'Mon-Sat 9-18',cost4:'€10.00',tip:'Cheap option'},
        ]
    },
    utrecht: {
        name: 'Utrecht', streetRate: '€5.10/hr', cheapGarage: '€2.50/hr', prRate: '€5.00/24hr', fine: '€72.90',
        center: [52.0907, 5.1214], zoom: 13,
        pr: [
            {name:'P+R Westraven',lat:52.0680,lng:5.0990,price:'€5/24hr',type:'Park + Ride · South',detail:'Bus → Centre ~10min · 800 spots'},
            {name:'P+R De Uithof',lat:52.0850,lng:5.1740,price:'€5/24hr',type:'Park + Ride · East',detail:'Bus → Centre ~15min · 600 spots'},
            {name:'P+R Papendorp',lat:52.0740,lng:5.0680,price:'€5/24hr',type:'Park + Ride · West',detail:'Tram → Centre ~12min · 500 spots'},
        ],
        garages: [
            {name:'Jaarbeurs Parking',lat:52.0880,lng:5.1080,price:'€2.50/hr · €20/day',type:'Garage · West',detail:'Near Centraal Station'},
            {name:'Springweg Parking',lat:52.0900,lng:5.1200,price:'€3/hr · €25/day',type:'Garage · Centre',detail:'Historic centre'},
            {name:'Q-Park Hoog Catharijne',lat:52.0910,lng:5.1090,price:'€3.50/hr · €30/day',type:'Garage · Centre',detail:'Shopping mall parking'},
            {name:'Parking Vaartsche Rijn',lat:52.0810,lng:5.1250,price:'€3/hr · €22/day',type:'Garage · South',detail:'Near canals'},
        ],
        free: [
            {name:'Leidsche Rijn / Vleuten',lat:52.0890,lng:5.0300,price:'FREE',type:'Free Parking',detail:'Bus to centre ~20min'},
        ],
        zones: [
            {zone:'Centrum (Oudegracht, Domplein)',rate:'€5.10',hours:'Mon-Sat 9-23, Sun 12-23',cost4:'€20.40',tip:'Use P+R or garage'},
            {zone:'Lombok / Oost',rate:'€4.00',hours:'Mon-Sat 9-23',cost4:'€16.00',tip:'Slightly cheaper'},
            {zone:'Wittevrouwen / Overvecht',rate:'€3.00',hours:'Mon-Sat 9-21',cost4:'€12.00',tip:'Free evenings'},
            {zone:'Outer areas',rate:'€1.50-2.50',hours:'Mon-Sat 9-18',cost4:'€6-10',tip:'Check local signs'},
        ]
    },
    eindhoven: {
        name: 'Eindhoven', streetRate: '€3.30/hr', cheapGarage: '€1.50/hr', prRate: '€3.00/24hr', fine: '€72.90',
        center: [51.4416, 5.4697], zoom: 13,
        pr: [
            {name:'P+R Meerhoven',lat:51.4350,lng:5.3900,price:'€3/24hr',type:'Park + Ride · West',detail:'Bus → Centre ~15min · 200 spots'},
            {name:'P+R Woensel',lat:51.4650,lng:5.4700,price:'€3/24hr',type:'Park + Ride · North',detail:'Bus → Centre ~10min · 150 spots'},
        ],
        garages: [
            {name:'Parking De Admirant',lat:51.4400,lng:5.4750,price:'€1.50/hr · €12/day',type:'Garage · Centre',detail:'Cheapest central garage'},
            {name:'Q-Park Heuvel',lat:51.4380,lng:5.4770,price:'€2/hr · €15/day',type:'Garage · Centre',detail:'Shopping area'},
            {name:'Parking Stationsplein',lat:51.4430,lng:5.4790,price:'€2.50/hr · €18/day',type:'Garage · Station',detail:'Near Eindhoven Centraal'},
            {name:'Parking Stratumseind',lat:51.4360,lng:5.4780,price:'€2/hr · €14/day',type:'Garage · Nightlife',detail:'Near restaurants & bars'},
        ],
        free: [
            {name:'Woensel / Tongelre',lat:51.4550,lng:5.5000,price:'FREE',type:'Free Parking',detail:'Residential areas, bus to centre'},
            {name:'IKEA / retail areas',lat:51.4600,lng:5.4400,price:'FREE (customers)',type:'Free Parking',detail:'Large free lots'},
        ],
        zones: [
            {zone:'Centrum',rate:'€3.30',hours:'Mon-Sat 9-18',cost4:'€13.20',tip:'Free evenings & Sundays!'},
            {zone:'Strijp / Woensel-Zuid',rate:'€2.50',hours:'Mon-Sat 9-18',cost4:'€10.00',tip:'Free evenings'},
            {zone:'Outer zones',rate:'€1.00-1.50',hours:'Mon-Sat 9-18',cost4:'€4-6',tip:'Many free options'},
        ]
    },
    schiphol: {
        name: 'Schiphol Airport', streetRate: 'N/A', cheapGarage: '€8/day (off-site)', prRate: '~€6 total', fine: 'N/A',
        center: [52.330, 4.790], zoom: 12,
        official: [
            {name:'P1 Short Term',lat:52.3093,lng:4.7621,price:'€54/day',type:'Official · Terminal',detail:'2 min walk to terminal'},
            {name:'P3 Long Stay',lat:52.3041,lng:4.753,price:'€29/day',type:'Official · Long Stay',detail:'Free shuttle to terminal'},
            {name:'P5 Holiday Parking',lat:52.305,lng:4.749,price:'€23/day',type:'Official · Budget',detail:'Shuttle to terminal'},
            {name:'P7 Valet',lat:52.3112,lng:4.768,price:'€69/day',type:'Official · Valet',detail:'Drop off at terminal'},
        ],
        offsite: [
            {name:'Schiphol Smart Parking',lat:52.299,lng:4.741,price:'€8/day',type:'Off-site Shuttle',detail:'Shuttle every 10min'},
            {name:'Parking Schiphol Zuid',lat:52.294,lng:4.738,price:'€9/day',type:'Off-site Shuttle',detail:'Shuttle every 15min'},
            {name:'Quick Parking Schiphol',lat:52.301,lng:4.735,price:'€11/day',type:'Off-site Shuttle',detail:'Shuttle every 12min'},
        ],
        hack: [
            {name:'P+R Sloterdijk → Train',lat:52.389,lng:4.8376,price:'~€6 total',type:'P+R + Train · Best Value',detail:'P+R €1 + train €5 return. 5 min ride.'},
        ]
    },

    leiden: {
        name: 'Leiden', streetRate: '€3.50/hr', cheapGarage: '€2.00/hr', prRate: '€5.00/24hr', fine: '€72.90',
        center: [52.1601, 4.497], zoom: 13,
        pr: [
            {name:'P+R Lammermarkt',lat:52.1560,lng:4.4800,price:'€5/24hr',type:'Park + Ride · West',detail:'Bus → Centrum ~10min · 600 spots'},
            {name:'P+R Haagweg',lat:52.1500,lng:4.4850,price:'€5/24hr',type:'Park + Ride · South',detail:'Bus → Centrum ~12min · 400 spots'},
            {name:'P+R Leeuwenhoek',lat:52.1460,lng:4.4940,price:'€5/24hr',type:'Park + Ride · Southeast',detail:'Bus → Centrum ~15min · 300 spots'},
        ],
        garages: [
            {name:'Parking Lammermarkt',lat:52.1565,lng:4.4835,price:'€2.00/hr · €16/day',type:'Garage · Centre',detail:'Largest central garage'},
            {name:'Parking Garenmarkt',lat:52.1590,lng:4.4870,price:'€2.50/hr · €20/day',type:'Garage · Centre',detail:'Near historic centre'},
            {name:'Parking Apothekersdijk',lat:52.1610,lng:4.4910,price:'€2.50/hr · €18/day',type:'Garage · Centre',detail:'Near canals'},
            {name:'Parking Mors',lat:52.1640,lng:4.4780,price:'€2.00/hr · €15/day',type:'Garage · West',detail:'Near station'},
            {name:'Parking Haagweg',lat:52.1510,lng:4.4865,price:'€1.80/hr · €12/day',type:'Garage · South',detail:'Budget option'},
        ],
        free: [
            {name:'Leiderdorp free streets',lat:52.1520,lng:4.5260,price:'FREE',type:'Free Parking',detail:'Bus 3 to Leiden centre'},
            {name:'Noord of station',lat:52.1720,lng:4.4900,price:'FREE',type:'Free Zones',detail:'30 min walk to centre'},
        ],
        zones: [
            {zone:'Binnenstad (historic centre)',rate:'€3.50',hours:'Mon-Sat 9-21',cost4:'€14.00',tip:'Free Sundays'},
            {zone:'Stationsomgeving',rate:'€3.00',hours:'Mon-Sat 9-21',cost4:'€12.00',tip:'Near Leiden Centraal'},
            {zone:'Morspoort / West',rate:'€2.50',hours:'Mon-Sat 9-18',cost4:'€10.00',tip:'Free evenings'},
            {zone:'Outer zones',rate:'€1.50-2.00',hours:'Mon-Sat 9-18',cost4:'€6-8',tip:'Often free evenings'},
        ]
    },
    groningen: {
        name: 'Groningen', streetRate: '€3.40/hr', cheapGarage: '€1.80/hr', prRate: '€2.00/24hr', fine: '€72.90',
        center: [53.2194, 6.5665], zoom: 13,
        pr: [
            {name:'P+R Kardinge',lat:53.2260,lng:6.6070,price:'€2/24hr',type:'Park + Ride · East',detail:'Bus → Centrum ~15min · 600 spots'},
            {name:'P+R Haren',lat:53.1780,lng:6.5890,price:'€2/24hr',type:'Park + Ride · South',detail:'Bus → Centrum ~20min · 400 spots'},
            {name:'P+R Driebond',lat:53.2310,lng:6.5290,price:'€2/24hr',type:'Park + Ride · West',detail:'Bus → Centrum ~15min · 300 spots'},
            {name:'P+R Reitdiep',lat:53.2200,lng:6.5300,price:'€2/24hr',type:'Park + Ride · Northwest',detail:'Bus → Centrum ~12min · 350 spots'},
        ],
        garages: [
            {name:'Parking Westerhaven',lat:53.2175,lng:6.5630,price:'€1.80/hr · €12/day',type:'Garage · Centre',detail:'Cheapest city centre'},
            {name:'Parking Damsterdiep',lat:53.2155,lng:6.5750,price:'€2.00/hr · €15/day',type:'Garage · Centre',detail:'East side of Grote Markt'},
            {name:'Parking Ossenmarkt',lat:53.2200,lng:6.5670,price:'€2.50/hr · €18/day',type:'Garage · Centre',detail:'Historic centre'},
            {name:'Q-Park Forum',lat:53.2185,lng:6.5700,price:'€2.50/hr · €20/day',type:'Garage · Centre',detail:'Near Forum Groningen'},
            {name:'Parking Hereweg',lat:53.2080,lng:6.5640,price:'€2.00/hr · €14/day',type:'Garage · South',detail:'Near UMCG hospital'},
        ],
        free: [
            {name:'Kardinge / Beijum',lat:53.2350,lng:6.6100,price:'FREE',type:'Free Parking',detail:'Bus to centre available'},
            {name:'Lewenborg',lat:53.2380,lng:6.6050,price:'FREE',type:'Free Zones',detail:'Outer residential area'},
        ],
        zones: [
            {zone:'Binnenstad (centrum)',rate:'€3.40',hours:'Mon-Sat 9-21',cost4:'€13.60',tip:'Free Sundays'},
            {zone:'Schilderswijk / Rivierenbuurt',rate:'€2.80',hours:'Mon-Sat 9-18',cost4:'€11.20',tip:'Free evenings'},
            {zone:'Helpman / De Wijert',rate:'€2.20',hours:'Mon-Sat 9-18',cost4:'€8.80',tip:'Residential area'},
            {zone:'Outer areas',rate:'€1.00-1.80',hours:'Mon-Sat 9-18',cost4:'€4-7',tip:'Often free parking nearby'},
        ]
    },
    maastricht: {
        name: 'Maastricht', streetRate: '€3.60/hr', cheapGarage: '€2.00/hr', prRate: '€4.00/24hr', fine: '€72.90',
        center: [50.8514, 5.691], zoom: 14,
        pr: [
            {name:'P+R Geusselt',lat:50.8560,lng:5.7220,price:'€4/24hr',type:'Park + Ride · East',detail:'Bus 7 → Centrum ~12min · 400 spots'},
            {name:'P+R Beatrixhaven',lat:50.8680,lng:5.6790,price:'€4/24hr',type:'Park + Ride · North',detail:'Bus → Centrum ~15min · 300 spots'},
            {name:'P+R Campagne',lat:50.8340,lng:5.7050,price:'€4/24hr',type:'Park + Ride · South',detail:'Bus → Centrum ~10min · 250 spots'},
        ],
        garages: [
            {name:'Parking Mosae Forum',lat:50.8477,lng:5.6940,price:'€2.00/hr · €16/day',type:'Garage · Centre',detail:'Modern shopping centre'},
            {name:'Parking Markt',lat:50.8499,lng:5.6908,price:'€2.50/hr · €18/day',type:'Garage · Centre',detail:'Near Markt square'},
            {name:'Parking Forum',lat:50.8510,lng:5.6920,price:'€2.50/hr · €20/day',type:'Garage · Centre',detail:'Near historic centre'},
            {name:'Parking Sphinxkwartier',lat:50.8530,lng:5.7000,price:'€2.00/hr · €14/day',type:'Garage · East',detail:'Redevelopment area'},
            {name:'Parking Boschstraat',lat:50.8465,lng:5.6880,price:'€3.00/hr · €22/day',type:'Garage · Centre',detail:'Quiet town side'},
        ],
        free: [
            {name:'Wolder / Heer',lat:50.8290,lng:5.7080,price:'FREE',type:'Free Parking',detail:'Bus to centrum ~20min'},
            {name:'Belfort area',lat:50.8750,lng:5.6860,price:'FREE',type:'Free Zones',detail:'North of centre, flat walk'},
        ],
        zones: [
            {zone:'Binnenstad (Vrijthof, Markt)',rate:'€3.60',hours:'Mon-Sat 9-21',cost4:'€14.40',tip:'Free Sundays — use this!'},
            {zone:'Wyck (station side)',rate:'€3.00',hours:'Mon-Sat 9-21',cost4:'€12.00',tip:'Near Maastricht Centraal'},
            {zone:'Stadspark / Oost',rate:'€2.50',hours:'Mon-Sat 9-18',cost4:'€10.00',tip:'Free evenings'},
            {zone:'Wolder / Heer',rate:'€1.00-2.00',hours:'Mon-Sat 9-18',cost4:'€4-8',tip:'Free options nearby'},
        ]
    },
    breda: {
        name: 'Breda', streetRate: '€2.80/hr', cheapGarage: '€1.50/hr', prRate: '€2.00/24hr', fine: '€72.90',
        center: [51.5719, 4.7683], zoom: 14,
        pr: [
            {name:'P+R Claudius Prinsenlaan',lat:51.5800,lng:4.7920,price:'€2/24hr',type:'Park + Ride · East',detail:'Bus → Centrum ~12min · 400 spots'},
            {name:'P+R Gageldonk',lat:51.5530,lng:4.7540,price:'€2/24hr',type:'Park + Ride · South',detail:'Bus → Centrum ~15min · 300 spots'},
        ],
        garages: [
            {name:'Parking Chasse',lat:51.5854,lng:4.7750,price:'€1.50/hr · €10/day',type:'Garage · Centre',detail:'Cheapest central option'},
            {name:'Parking Haven',lat:51.5879,lng:4.7740,price:'€2.00/hr · €14/day',type:'Garage · Centre',detail:'Near Grote Kerk'},
            {name:'Parking Dr. Batenburglaan',lat:51.5870,lng:4.7790,price:'€2.00/hr · €15/day',type:'Garage · Centre',detail:'Shopping district'},
            {name:'Q-Park Raadhuisplein',lat:51.5896,lng:4.7755,price:'€2.50/hr · €18/day',type:'Garage · Centre',detail:'Near City Hall'},
            {name:'Parking Speelhuislaan',lat:51.5850,lng:4.7720,price:'€1.80/hr · €12/day',type:'Garage · Centre',detail:'Budget option west'},
        ],
        free: [
            {name:'Tuinzigt / Heusdenhout',lat:51.5640,lng:4.7520,price:'FREE',type:'Free Parking',detail:'Bus to centre ~15min'},
            {name:'Industrial areas west',lat:51.5900,lng:4.7300,price:'FREE',type:'Free Zones',detail:'20 min walk to centre'},
        ],
        zones: [
            {zone:'Centrum (Grote Markt, Havermarkt)',rate:'€2.80',hours:'Mon-Sat 9-21',cost4:'€11.20',tip:'Free Sundays'},
            {zone:'Stationsomgeving',rate:'€2.50',hours:'Mon-Sat 9-21',cost4:'€10.00',tip:'Near Breda Centraal'},
            {zone:'Ginneken / South',rate:'€2.00',hours:'Mon-Sat 9-18',cost4:'€8.00',tip:'Free evenings'},
            {zone:'Outer zones',rate:'€1.00-1.50',hours:'Mon-Sat 9-18',cost4:'€4-6',tip:'Often free parking'},
        ]
    },
    nijmegen: {
        name: 'Nijmegen', streetRate: '€3.10/hr', cheapGarage: '€1.60/hr', prRate: '€2.50/24hr', fine: '€80.20',
        center: [51.8426, 5.8546], zoom: 13,
        pr: [
            {name:'P+R De Goffert',lat:51.8330,lng:5.8570,price:'€2.50/24hr',type:'Park + Ride · South',detail:'Bus 10 → Centrum ~10min · 600 spots'},
            {name:'P+R Ressen',lat:51.8680,lng:5.8970,price:'€2.50/24hr',type:'Park + Ride · East',detail:'Bus → Centrum ~18min · 400 spots'},
            {name:'P+R Winkelsteeg',lat:51.8370,lng:5.8160,price:'€2.50/24hr',type:'Park + Ride · West',detail:'Bus → Centrum ~15min · 350 spots'},
        ],
        garages: [
            {name:'Parking Mariënburg',lat:51.8434,lng:5.8669,price:'€1.60/hr · €12/day',type:'Garage · Centre',detail:'Cheapest central option'},
            {name:'Parking Plein 1944',lat:51.8446,lng:5.8604,price:'€2.00/hr · €16/day',type:'Garage · Centre',detail:'Near main square'},
            {name:'Q-Park Waalkade',lat:51.8468,lng:5.8666,price:'€2.50/hr · €20/day',type:'Garage · Centre',detail:'River views nearby'},
            {name:'Parking Kelfkensbos',lat:51.8423,lng:5.8715,price:'€2.00/hr · €15/day',type:'Garage · Centre',detail:'Near Valkhof museum'},
            {name:'Parking Parkeergarage Doddendaal',lat:51.8460,lng:5.8630,price:'€1.80/hr · €13/day',type:'Garage · Centre',detail:'Historic city area'},
        ],
        free: [
            {name:'Dukenburg / Lindenholt',lat:51.8150,lng:5.8150,price:'FREE',type:'Free Parking',detail:'Bus to centre ~20min'},
            {name:'Nijmegen-Noord (Lent)',lat:51.8700,lng:5.8530,price:'FREE',type:'Free Zones',detail:'Over the Waal bridge'},
        ],
        zones: [
            {zone:'Binnenstad (Plein 1944, Grote Markt)',rate:'€3.10',hours:'Mon-Sat 9-21',cost4:'€12.40',tip:'Free Sundays'},
            {zone:'Stationsomgeving',rate:'€2.80',hours:'Mon-Sat 9-21',cost4:'€11.20',tip:'Near Nijmegen Centraal'},
            {zone:'Altrade / Neerbosch-Oost',rate:'€2.00',hours:'Mon-Sat 9-18',cost4:'€8.00',tip:'Free evenings'},
            {zone:'Outer areas',rate:'€1.00-1.60',hours:'Mon-Sat 9-18',cost4:'€4-6.40',tip:'Free options available'},
        ]
    },
    tilburg: {
        name: 'Tilburg', streetRate: '€2.70/hr', cheapGarage: '€1.50/hr', prRate: '€2.00/24hr', fine: '€80.20',
        center: [51.5555, 5.0913], zoom: 13,
        pr: [
            {name:'P+R Wagnerplein',lat:51.5480,lng:5.0730,price:'€2/24hr',type:'Park + Ride · West',detail:'Bus → Centrum ~12min · 500 spots'},
            {name:'P+R Koningshoeven',lat:51.5400,lng:5.1020,price:'€2/24hr',type:'Park + Ride · South',detail:'Bus → Centrum ~15min · 300 spots'},
            {name:'P+R Reeshof',lat:51.5380,lng:5.0450,price:'€2/24hr',type:'Park + Ride · Southwest',detail:'Bus → Centrum ~18min · 250 spots'},
        ],
        garages: [
            {name:'Parking Piushaven',lat:51.5566,lng:5.0950,price:'€1.50/hr · €10/day',type:'Garage · Centre',detail:'Cheapest central option'},
            {name:'Q-Park Paleis-Raadhuis',lat:51.5590,lng:5.0880,price:'€2.00/hr · €15/day',type:'Garage · Centre',detail:'Near City Hall'},
            {name:'Parking 013',lat:51.5560,lng:5.0940,price:'€2.00/hr · €14/day',type:'Garage · Centre',detail:'Near music venue 013'},
            {name:'Parking Stadhuisplein',lat:51.5575,lng:5.0870,price:'€2.50/hr · €18/day',type:'Garage · Centre',detail:'Central location'},
            {name:'Parking Spoorlaan',lat:51.5600,lng:5.0890,price:'€1.80/hr · €12/day',type:'Garage · Station',detail:'Near Tilburg Centraal'},
        ],
        free: [
            {name:'Tilburg Noord / Loven',lat:51.5800,lng:5.0850,price:'FREE',type:'Free Parking',detail:'Bus to centre ~18min'},
            {name:'Berkel-Enschot',lat:51.5510,lng:5.1480,price:'FREE',type:'Free Zones',detail:'Eastern residential area'},
        ],
        zones: [
            {zone:'Centrum (Stadhuisplein, Piushaven)',rate:'€2.70',hours:'Mon-Sat 9-21',cost4:'€10.80',tip:'Free Sundays'},
            {zone:'Stationsomgeving',rate:'€2.50',hours:'Mon-Sat 9-21',cost4:'€10.00',tip:'Near Tilburg Centraal'},
            {zone:'Binnenstad / West',rate:'€2.00',hours:'Mon-Sat 9-18',cost4:'€8.00',tip:'Free evenings'},
            {zone:'Outer zones',rate:'€1.00-1.50',hours:'Mon-Sat 9-18',cost4:'€4-6',tip:'Often free parking'},
        ]
    },
    zwolle: {
        name: 'Zwolle', streetRate: '€2.50/hr', cheapGarage: '€1.40/hr', prRate: '€2.00/24hr', fine: '€80.20',
        center: [52.5168, 6.0830], zoom: 14,
        pr: [
            {name:'P+R Hanzeland',lat:52.5150,lng:6.1050,price:'€2/24hr',type:'Park + Ride · East',detail:'Bus → Centrum ~10min · 600 spots'},
            {name:'P+R Meppelerdiep',lat:52.5230,lng:6.0580,price:'€2/24hr',type:'Park + Ride · Northwest',detail:'Bus → Centrum ~12min · 400 spots'},
            {name:'P+R Schellerlaan',lat:52.5050,lng:6.0960,price:'€2/24hr',type:'Park + Ride · South',detail:'Bus → Centrum ~15min · 300 spots'},
        ],
        garages: [
            {name:'Parking Lübeckplein',lat:52.5164,lng:6.0905,price:'€1.40/hr · €10/day',type:'Garage · Centre',detail:'Cheapest central garage'},
            {name:'Parking Rodetorenplein',lat:52.5168,lng:6.0845,price:'€1.80/hr · €13/day',type:'Garage · Centre',detail:'Near historic Sassenpoort'},
            {name:'Q-Park Diezerstraat',lat:52.5175,lng:6.0860,price:'€2.00/hr · €15/day',type:'Garage · Centre',detail:'Shopping street'},
            {name:'Parking Potgietersingel',lat:52.5145,lng:6.0890,price:'€1.60/hr · €11/day',type:'Garage · Centre',detail:'Budget option'},
            {name:'Parking Stationsplein',lat:52.5052,lng:6.0938,price:'€2.50/hr · €18/day',type:'Garage · Station',detail:'Near Zwolle Centraal'},
        ],
        free: [
            {name:'Westenholte / Berkum',lat:52.5350,lng:6.0550,price:'FREE',type:'Free Parking',detail:'Residential outskirts, bus to centre'},
            {name:'Stadshagen',lat:52.5240,lng:6.0280,price:'FREE',type:'Free Zones',detail:'West residential area'},
        ],
        zones: [
            {zone:'Binnenstad (Grote Markt, Sassenstraat)',rate:'€2.50',hours:'Mon-Sat 9-21',cost4:'€10.00',tip:'Free Sundays'},
            {zone:'Stationsomgeving',rate:'€2.20',hours:'Mon-Sat 9-21',cost4:'€8.80',tip:'Near Zwolle Centraal'},
            {zone:'Assendorp / Holtenbroek',rate:'€1.80',hours:'Mon-Sat 9-18',cost4:'€7.20',tip:'Free evenings'},
            {zone:'Outer zones',rate:'€1.00-1.40',hours:'Mon-Sat 9-18',cost4:'€4-5.60',tip:'Free options nearby'},
        ]
    },
    haarlem: {
        name: 'Haarlem', streetRate: '€3.50/hr', cheapGarage: '€2.00/hr', prRate: '€3.00/24hr', fine: '€72.90',
        center: [52.3874, 4.6462], zoom: 14,
        pr: [
            {name:'P+R Haarlem Station',lat:52.3879,lng:4.6363,price:'€3/24hr',type:'Park + Ride · West',detail:'10 min walk to Grote Markt · Train to Amsterdam 15min'},
            {name:'P+R Haarlem Noord',lat:52.4040,lng:4.6480,price:'€3/24hr',type:'Park + Ride · North',detail:'Bus to centre ~10min · 200 spots'},
        ],
        garages: [
            {name:'Ter Kleef',lat:52.3838,lng:4.6388,price:'€2/hr · €10/day',type:'Garage · Near Grote Markt',detail:'Cheapest garage · 5min walk to centre'},
            {name:'Houtplein',lat:52.3870,lng:4.6352,price:'€2.20/hr · €11/day',type:'Garage · West Centre',detail:'Near station · Free Sundays'},
            {name:'Raaks',lat:52.3882,lng:4.6410,price:'€2.50/hr · €13/day',type:'Garage · Near Station',detail:'Covered · Open 24/7'},
            {name:'Cronjé',lat:52.3821,lng:4.6418,price:'€2.80/hr · €14/day',type:'Garage · South Centre',detail:'Near Grote Markt south'},
            {name:'Appelmarkt',lat:52.3808,lng:4.6387,price:'€3/hr · €15/day',type:'Garage · City Centre',detail:'1 min walk to Grote Kerk'},
        ],
        free: [
            {name:'Schalkwijk (free evenings)',lat:52.3690,lng:4.6550,price:'FREE after 18:00',type:'Free Parking',detail:'Mon-Sat free from 18:00, all day Sunday'},
            {name:'Suburbs North (free)',lat:52.4050,lng:4.6350,price:'FREE',type:'Free Parking',detail:'Outer residential areas, all day'},
        ],
        zones: [
            {zone:'Centrum (Grote Markt area)',rate:'€3.50',hours:'Mon-Sat 9-21',cost4:'€14.00',tip:'FREE Sundays — use garage for all-day'},
            {zone:'Binnenstad (Inner Streets)',rate:'€3.00',hours:'Mon-Sat 9-21',cost4:'€12.00',tip:'FREE Sundays'},
            {zone:'Schalkwijk / Suburbs',rate:'€2.00',hours:'Mon-Sat 9-18',cost4:'€8.00',tip:'Free evenings from 18:00'},
            {zone:'Blue Zone',rate:'FREE',hours:'Max 1-2hrs',cost4:'€0',tip:'Need parking disc (€2 petrol station)'},
        ]
    },
    delft: {
        name: 'Delft', streetRate: '€2.90/hr', cheapGarage: '€1.50/hr', prRate: '€2.50/24hr', fine: '€72.90',
        center: [52.0116, 4.3571], zoom: 14,
        pr: [
            {name:'P+R Delft Station',lat:52.0125,lng:4.3567,price:'€2.50/24hr',type:'Park + Ride · Centre West',detail:'10 min walk to Markt · Train to The Hague 8min / Rotterdam 12min'},
            {name:'P+R TU Delft Campus',lat:51.9990,lng:4.3740,price:'€3/24hr',type:'Park + Ride · South',detail:'~15min cycle to centre · Large capacity'},
        ],
        garages: [
            {name:'Phoenixstraat',lat:52.0052,lng:4.3609,price:'€1.50/hr · €7/day',type:'Garage · South Centre',detail:'Cheapest garage · 8min walk to Markt'},
            {name:'Boterbrug',lat:52.0120,lng:4.3580,price:'€2.20/hr · €9/day',type:'Garage · Centre',detail:'5min walk to Markt · Free Sundays'},
            {name:'Zuidpoort',lat:52.0108,lng:4.3598,price:'€2.50/hr · €11/day',type:'Garage · Centre',detail:'3min walk to Markt · Closest to centre'},
            {name:'Nieuwe Gracht',lat:52.0130,lng:4.3640,price:'€2.70/hr · €12/day',type:'Garage · East',detail:'Near Prinsenhof Museum'},
            {name:'Vrijenban',lat:52.0148,lng:4.3650,price:'€2.80/hr · €13/day',type:'Garage · Station',detail:'Near Delft Centraal station'},
        ],
        free: [
            {name:'Outer Districts (Voorhof)',lat:52.0020,lng:4.3450,price:'FREE',type:'Free Parking',detail:'Free Mon-Sat evenings from 18:00, all day Sundays'},
            {name:'Buitenhof area',lat:52.0170,lng:4.3530,price:'FREE on Sundays',type:'Free Zones',detail:'Free Sundays city-wide'},
        ],
        zones: [
            {zone:'Centrum (Markt / Binnenstad)',rate:'€2.90',hours:'Mon-Sat 9-21',cost4:'€11.60',tip:'FREE Sundays — or use Boterbrug garage'},
            {zone:'Stationsomgeving',rate:'€2.50',hours:'Mon-Sat 9-21',cost4:'€10.00',tip:'Good if travelling on by train'},
            {zone:'Outer Districts (Voorhof/Buitenhof)',rate:'€1.50',hours:'Mon-Sat 9-18',cost4:'€6.00',tip:'Free evenings after 18:00'},
            {zone:'Blue Zone',rate:'FREE',hours:'Max 1-2hrs',cost4:'€0',tip:'Need parking disc (€2 petrol station)'},
        ]
    }
};

// Shared nav HTML
function getNav(active){
    const links = [
        {href:'/amsterdam.html',text:'Amsterdam',id:'amsterdam'},
        {href:'/rotterdam.html',text:'Rotterdam',id:'rotterdam'},
        {href:'/the-hague.html',text:'The Hague',id:'the-hague'},
        {href:'/schiphol.html',text:'Schiphol ✈',id:'schiphol'},
        {href:'/all-cities.html',text:'All Cities',id:'all'},
    ];
    return links.map(l=>`<li><a href="${l.href}"${l.id===active?' class="act"':''}>${l.text}</a></li>`).join('');
}
