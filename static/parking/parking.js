/* RamHub Parking — no frameworks, no fabricated vacancy counts.
   Coordinates for two separately mapped lots are approximate visual reference points.
   Weather: Django same-origin proxy first, then Open-Meteo directly when possible.
*/
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const ZONE = 'America/New_York';
  const OFFICIAL = 'https://map.farmingdale.edu/';
  const LOT_PDF = 'https://www.farmingdale.edu/capital-projects-and-construction/pdfs/2025aprilcampusmapduringconstruction.pdf';
  const ALL_LOTS = ['1','2','3','5','5A','6','7','7A','8','9','10','11','12','15','15A','17','18','22','23'];
  // FSC campus lot locations cross-checked with an OSM-derived parking directory.
  // Locations are map reference points, NEVER verified empty parking spaces.
  const REFERENCE_LOTS = {
    '1': {lat:40.7540948,lon:-73.4236436,label:'Student Lot #1 — mapped campus location',osm:'https://www.latlong.net/poi/parking-lot-1-491558',source:'mapped directory'},
    '2': {lat:40.7553798,lon:-73.4253039,label:'Student Lot #2 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '3': {lat:40.7547098,lon:-73.4308490,label:'Student Lot #3 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '5': {lat:40.7519968,lon:-73.4319477,label:'Student Lot #5 — mapped campus location',osm:'https://www.latlong.net/poi/parking-lot-5-491555',source:'mapped directory'},
    '5A':{lat:40.7532635,lon:-73.4331273,label:'Student Lot #5A — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '6': {lat:40.7522143,lon:-73.4337538,label:'Student Lot #6 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '7': {lat:40.7499644,lon:-73.4324596,label:'Student Lot #7 — near Nold Hall',osm:'https://www.openstreetmap.org/way/557143564',source:'OSM way'},
    '7A':{lat:40.7494274,lon:-73.4326140,label:'Student Lot #7A — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '8': {lat:40.7497228,lon:-73.4296980,label:'Student Lot #8 — mapped campus location',osm:'https://www.openstreetmap.org/way/493679415',source:'OSM way'},
    '9': {lat:40.7491945,lon:-73.4293887,label:'Student Lot #9 — mapped campus location',osm:'https://www.openstreetmap.org/way/49332870',source:'OSM way'},
    '10':{lat:40.7511068,lon:-73.4260345,label:'Student Lot #10 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '15':{lat:40.7528727,lon:-73.4301459,label:'Student Lot #15 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '15A':{lat:40.7527345,lon:-73.4299466,label:'Student Lot #15A — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '17':{lat:40.7532753,lon:-73.4294192,label:'Student Lot #17 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '18':{lat:40.7540273,lon:-73.4298164,label:'Student Lot #18 — mapped campus location',osm:'https://www.latlong.net/pois/us/levittown/parking',source:'mapped directory'},
    '22':{lat:40.7553361,lon:-73.4268074,label:'Student Lot #22 — mapped campus location (check permit restrictions)',osm:'https://www.latlong.net/poi/parking-lot-22-491556',source:'mapped directory'}
  };
  const SOURCE_LOTS = new Set(Object.keys(REFERENCE_LOTS));
  let osmLookupState='loading'; // loading | ready | unavailable
  let osmMatched=0;
  const BUILDING_HINTS = {
    'Lupton Hall':'FSC campus guidance identifies Student Lot #5 near Lupton Hall. Check signs and the published map before parking.',
    'Nold Hall':'Student Lot #7 is a documented western-campus lot near Nold Hall. No availability information is currently published.',
    'School of Business':'Student Lot #9 is shown near the south-campus business area on FSC’s map.',
    'Whitman Hall':'Whitman Hall is shown near the center of the official FSC campus plan. Use the lot directory and check permitted parking.',
  };
  const fmt = (opts) => new Intl.DateTimeFormat('en-US', {timeZone:ZONE,...opts});
  const dateFmt = fmt({month:'short',day:'numeric',year:'numeric'});
  const dayFmt = fmt({weekday:'long'});
  const timeFmt = fmt({hour:'numeric',minute:'2-digit',hour12:true});
  const hourFmt = fmt({hour:'numeric',hourCycle:'h23'});
  let map = null;
  let markers = new Map();
  let selectedLot = '7';

  function updateClock(){
    const now = new Date();
    $('dateValue').textContent = dateFmt.format(now);
    $('dayValue').textContent = dayFmt.format(now);
    $('timeValue').textContent = timeFmt.format(now);
  }
  updateClock();
  setInterval(updateClock, 1000);

  const tips = ['Get to campus 20 minutes before class.', 'Time is money, people. Plan ahead.', 'Less circling, more time for your coffee.', 'Rambo says: check your permit and lot signs.'];
  const typingEl = $('typingTip');
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
    let tip=0, count=0, pause=0, deleting=false;
    typingEl.textContent='';
    function tick(){
      const line=tips[tip];
      if (!deleting){count=Math.min(count+1,line.length);typingEl.textContent=line.slice(0,count);if(count===line.length){deleting=true;pause=2400;}}
      else if(pause>0){pause-=80;}
      else{count=Math.max(0,count-1);typingEl.textContent=line.slice(0,count);if(!count){deleting=false;tip=(tip+1)%tips.length;}}
      setTimeout(tick,pause>0?80:deleting?25:45);
    }
    tick();
  }

  async function fetchJSON(url, timeoutMs=7000){
    const abort = new AbortController();
    const handle=setTimeout(()=>abort.abort(),timeoutMs);
    try{
      const res=await fetch(url,{signal:abort.signal,cache:'no-store',headers:{'Accept':'application/json'}});
      if(!res.ok)throw Error(`HTTP ${res.status}`);
      return await res.json();
    } finally {clearTimeout(handle);}
  }

  const OPEN_METEO = 'https://api.open-meteo.com/v1/forecast?latitude=40.7524&longitude=-73.4280&current=temperature_2m,apparent_temperature,weather_code,is_day&hourly=precipitation_probability&temperature_unit=fahrenheit&timezone=America%2FNew_York&forecast_days=1';
  function condition(code){
    if([95,96,99].includes(code))return ['⛈','Storms','Allow extra travel time and avoid walking in lightning.'];
    if([71,73,75,77,85,86].includes(code))return ['❄','Snow','Bundle up and check campus notices.'];
    if([51,53,55,56,57,61,63,65,66,67,80,81,82].includes(code))return ['🌧','Rain','Rambo says: grab your umbrella.'];
    if([45,48].includes(code))return ['🌫','Fog','Drive carefully and leave early.'];
    if(code===0)return ['☀','Clear','What a day for sunglasses.'];
    if([1,2].includes(code))return ['⛅','Partly cloudy','Good day to beat the rush.'];
    if(code===3)return ['☁','Cloudy','Keep an eye on the forecast.'];
    return ['☁','Current conditions','Plan your drive before class.'];
  }
  let weatherBusy=false;
  async function updateWeather(){
    if(weatherBusy)return;
    weatherBusy=true;
    $('weatherRetry').hidden=true;
    $('weatherExternal').hidden=true;
    $('weatherRain').hidden=true;
    $('weatherLive').hidden=true;
    $('weatherValue').textContent='Checking conditions…';
    $('weatherNote').textContent='Contacting weather service';
    const backend = document.querySelector('.parking-app').dataset.weatherUrl;
    try{
      let response;
      if(backend && !backend.includes('{%')){
        try{response=await fetchJSON(backend,5000);}catch(e){response=await fetchJSON(OPEN_METEO,7000);}
      } else {response=await fetchJSON(OPEN_METEO,7000);}
      const current=response.current;
      if(!current || !Number.isFinite(Number(current.temperature_2m)) || !Number.isFinite(Number(current.weather_code)))throw Error('Unexpected response');
      const code=Number(current.weather_code),temp=Math.round(Number(current.temperature_2m));
      let [glyph,summary,advice]=condition(code);
      const hours=response.hourly?.time||[];
      const probs=response.hourly?.precipitation_probability||[];
      const matched=hours.findIndex(s=>String(s).slice(0,13)===String(current.time||'').slice(0,13));
      const nextRain=matched>=0?Math.max(0,...probs.slice(matched,matched+3).filter(Number.isFinite)):0;
      if(nextRain>=60&&!['Snow','Storms','Rain'].includes(summary)){advice='Rain possible soon — take your umbrella.';glyph='🌧';}
      if(matched>=0){$('weatherRain').textContent=`Next 3 hours: up to ${Math.round(nextRain)}% chance of rain`; $('weatherRain').hidden=false;}
      if(temp>=86&&!['Storms','Snow','Rain'].includes(summary))advice='Hot day — grab water or an iced coffee.';
      $('weatherIcon').textContent=glyph;
      $('weatherValue').textContent=`${temp}°F · ${summary}`;
      $('weatherNote').textContent=advice;
      $('weatherLive').hidden=false;
      $('weatherValue').title=`Last observed: ${current.time||'latest'} · Source: Open-Meteo`;
    } catch(e){
      $('weatherIcon').textContent='☁';
      $('weatherValue').textContent='Forecast unavailable';
      $('weatherNote').textContent='Weather service is unreachable. Other parking features still work.';
      $('weatherRetry').hidden=false;
      $('weatherExternal').hidden=false;
      console.warn('RamHub parking weather:',e.message);
    }finally{weatherBusy=false;}
  }
  $('weatherRetry').addEventListener('click',updateWeather);
  updateWeather();
  setInterval(updateWeather,10*60*1000);

  function loadPref(){
    try{return JSON.parse(localStorage.getItem('ramhub.parking.preference')||'{}');}
    catch(e){return {};}
  }
  const pref=loadPref();
  if(pref.building && [...$('destination').options].some(o=>o.value===pref.building))$('destination').value=pref.building;
  if(pref.classTime && /^\d{2}:\d{2}$/.test(pref.classTime))$('classTime').value=pref.classTime;
  function updatePlanner(){
    const building=$('destination').value;
    const clock=$('classTime').value||'09:00';
    $('plannerHeading').textContent=building?`Heading to ${building}?`:'A little planning goes a long way.';
    $('plannerAdvice').textContent=building?(BUILDING_HINTS[building]||`Check the official campus parking layout for permitted lots near ${building}.`) + ` If class starts at ${clock}, aim to arrive about 20 minutes earlier.`:'Choose a building to see a documented parking reference. No fictional walking times or vacancy predictions.';
  }
  $('destination').addEventListener('change',updatePlanner);
  $('classTime').addEventListener('change',updatePlanner);
  updatePlanner();
  $('saveDefault').addEventListener('click',()=>{
    if(!$('destination').value){$('saveStatus').textContent='Choose your building first.';return;}
    try{localStorage.setItem('ramhub.parking.preference',JSON.stringify({building:$('destination').value,classTime:$('classTime').value}));$('saveStatus').textContent=`Saved ${$('destination').value} as your default on this device.`;}
    catch(e){$('saveStatus').textContent='Preferences cannot be saved in this browser, but you can still use the planner.';}
  });

  // Keep map markers in sync when late OSM geometry arrives.
  function addRealLotMarker(id,lot){
    if(!map || !mapReady || markers.has(id) || !window.maplibregl) return;
    const btn=document.createElement('button');btn.type='button';btn.className='campus-pin';
    btn.textContent='P · '+id;btn.title='Mapped FSC Student Lot #'+id+' — no live vacancy data';
    btn.setAttribute('aria-label','Select Student Lot #'+id);
    btn.addEventListener('click',()=>updateLotDetails(id));
    const marker=new window.maplibregl.Marker({element:btn,anchor:'bottom'}).setLngLat([lot.lon,lot.lat]).addTo(map);
    markers.set(id,marker);
  }
  function syncRealMarkers(){ Object.entries(REFERENCE_LOTS).forEach(([id,lot])=>addRealLotMarker(id,lot)); }

  function updateLotDetails(id){
    selectedLot=id;
    $('lotButtons').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.lot===id));
    markers.forEach((m,key)=>{const node=m.getElement();if(node)node.classList.toggle('is-selected',key===id);});
    const l=REFERENCE_LOTS[id];
    const info=$('lotDetails');
    info.replaceChildren();
    const head=document.createElement('strong');head.textContent=`Student Lot #${id}`;info.append(head);
    const p=document.createElement('p');
    p.textContent=l?`${l.label}. Pin is a geographic reference, NOT a vacant parking space.`:(osmLookupState==='loading'?'Checking OpenStreetMap for the real numbered lot…':'On FSC’s official map; no separately mapped location was returned. We do not invent a pin.');
    info.append(p);
    const link=document.createElement('a');link.href=l?l.osm:LOT_PDF;link.target='_blank';link.rel='noopener noreferrer';link.textContent=l?'View mapped location / source':'Locate on the official FSC parking plan';info.append(link);
    if(map && mapReady && l){map.flyTo({center:[l.lon,l.lat],zoom:17.3,pitch:$('map3d').classList.contains('is-on')?57:0,bearing:$('map3d').classList.contains('is-on')?-27:0,duration:900});}
    else if(map && mapReady && !l){map.flyTo({center:MAP_CENTER,zoom:MAP_ZOOM,pitch:57,bearing:-27,duration:700});}
  }
  for(const id of ALL_LOTS){
    const b=document.createElement('button');b.type='button';b.className='lot-button';b.dataset.lot=id;b.textContent=`#${id}`;b.setAttribute('aria-label',`Explore student parking lot ${id}`);
    b.addEventListener('click',()=>updateLotDetails(id));$('lotButtons').append(b);
    const opt=document.createElement('option');opt.value=id;opt.textContent=`Student Lot #${id}`;$('chartLot').append(opt);
    const reportOpt=opt.cloneNode(true);$('reportLot').append(reportOpt);
  }
  updateLotDetails('7');

  // MapLibre 5.24.0 is pinned deliberately: MapLibre 6 removed the legacy UMD
  // script-tag bundle. Dynamic script loading with window.maplibregl requires v5.
  // No parking vacancy counts are implied by either the map or the pins.
  const MAP_CENTER = [-73.4283, 40.7527];
  const MAP_ZOOM = 15.9;
  const MAP_2D_URL = $('mapSourceFrame').dataset.src;
  const infoLine = document.querySelector('.map-game-help');
  let mapReady = false;
  let mapLoading = false;
  let sourceMode = false;
  let mapTimeout;
  let libraryPromise = null;

  function statusMessage(text) {
    infoLine.textContent = text;
    infoLine.setAttribute('role', 'status');
  }
  function showFallback(message) {
    $('mapFallbackText').textContent = message;
    if (!sourceMode) $('mapFallback').classList.add('visible');
  }
  function hideFallback() {
    $('mapFallback').classList.remove('visible');
  }
  function sourceFrame() {
    const frame = $('mapSourceFrame');
    if (!frame.getAttribute('src') || frame.getAttribute('src') === 'about:blank') {
      frame.src = MAP_2D_URL;
    }
    return frame;
  }
  function setMode(is3D) {
    sourceMode = !is3D;
    $('map3d').classList.toggle('is-on', is3D);
    $('map2d').classList.toggle('is-on', !is3D);
    $('map3d').setAttribute('aria-pressed', String(is3D));
    $('map2d').setAttribute('aria-pressed', String(!is3D));
    $('mapSourceFrameWrap').hidden = is3D;
    $('campusGameMap').hidden = !is3D;
    if (!is3D) {
      sourceFrame();
      hideFallback();
      statusMessage('2D campus map · choose 3D to retry the interactive view');
    } else if (!mapReady) {
      showFallback('Connecting to real campus buildings. The page will switch to 2D if 3D is unavailable.');
      statusMessage('Loading 3D map…');
    } else {
      hideFallback();
      statusMessage('Drag to explore · Scroll to zoom · Choose a documented lot');
    }
    if (map) {
      // Recalculate when switching back from a hidden canvas.
      requestAnimationFrame(() => {
        try { map.resize(); } catch (_) { /* map was disposed */ }
      });
    }
  }
  function fail3D(message) {
    clearTimeout(mapTimeout);
    mapLoading = false;
    mapReady = false;
    if (map) { try {map.remove();} catch (_) {} map = null; }
    markers.clear();
    // Never trap users behind a permanent 'Loading the 3D campus' overlay.
    setMode(false);
    statusMessage('3D unavailable · showing the 2D campus map');
    console.warn('RamHub parking map: ' + message);
  }
  function loadStyle(url) { return new Promise((resolve, reject) => {
    const existing = document.querySelector('link[data-ramhub-map-css]');
    if (existing) {resolve();return;}
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = url; css.dataset.ramhubMapCss = '1';
    css.onload = resolve; css.onerror = () => {css.remove();reject(Error('MapLibre CSS blocked'));};
    document.head.appendChild(css);
  }); }
  function loadScript(url) { return new Promise((resolve, reject) => {
    if (window.maplibregl) {resolve();return;}
    const script = document.createElement('script'); script.src = url; script.async = true;
    script.onload = () => window.maplibregl ? resolve() : reject(Error('Map library did not initialize'));
    script.onerror = () => {script.remove();reject(Error('MapLibre script blocked'));};
    document.head.appendChild(script);
  }); }
  async function getLibrary() {
    if (window.maplibregl) return window.maplibregl;
    if (!libraryPromise) libraryPromise = (async () => {
      const ver = '5.24.0';
      const cdn = 'https://cdn.jsdelivr.net/npm/maplibre-gl@' + ver + '/dist/';
      await Promise.all([
        loadStyle(cdn + 'maplibre-gl.css').catch(() => loadStyle('https://unpkg.com/maplibre-gl@' + ver + '/dist/maplibre-gl.css')),
        loadScript(cdn + 'maplibre-gl.js').catch(() => loadScript('https://unpkg.com/maplibre-gl@' + ver + '/dist/maplibre-gl.js'))
      ]);
      if (!window.maplibregl) throw Error('Map library missing');
      return window.maplibregl;
    })().catch(e => {libraryPromise = null;throw e;});
    return libraryPromise;
  }
  function recenter2D() {
    // Reassigning the original iframe URL restores the real campus area.
    const frame = sourceFrame();
    frame.src = MAP_2D_URL;
    statusMessage('2D campus map recentered on Farmingdale State College');
  }
  function recenter3D() {
    if (!map || !mapReady) { setMode(false); recenter2D(); return; }
    map.resize();
    map.flyTo({center: MAP_CENTER, zoom: MAP_ZOOM, pitch: 57, bearing: -27, duration: 1000});
    statusMessage('3D campus map recentered');
  }
  $('map2d').addEventListener('click', () => setMode(false));
  $('map3d').addEventListener('click', () => {
    setMode(true);
    if (mapReady && map) {
      map.easeTo({pitch:57, bearing:-27, duration:700});
    } else if (!mapLoading) {
      initializeMap(); // Explicit retry, instead of a dead button.
    }
  });
  $('mapReset').addEventListener('click', () => {
    if (sourceMode || !mapReady) {
      setMode(false); recenter2D();
    } else recenter3D();
  });
  async function initializeMap() {
    if (mapLoading || mapReady) return;
    mapLoading = true;
    setMode(true);
    const failTimer = setTimeout(() => fail3D('3D map could not finish loading; verify map CDN, map tiles and WebGL.'), 7500);
    mapTimeout = failTimer;
    try {
      const ml = await getLibrary();
      // An earlier network timeout may have switched us to 2D in the meantime.
      if (!mapLoading) return;
      if (typeof ml.Map !== 'function') throw Error('MapLibre Map constructor is unavailable');
      const instance = new ml.Map({
        container:'campusGameMap',
        style:'https://tiles.openfreemap.org/styles/liberty',
        center:MAP_CENTER, zoom:MAP_ZOOM, pitch:57, bearing:-27,
        antialias:true, maxPitch:78, attributionControl:true, interactive:true
      });
      map = instance;
      instance.addControl(new ml.NavigationControl({showCompass:true,showZoom:true,visualizePitch:true}),'bottom-right');
      instance.on('load', () => {
        if (map !== instance || !mapLoading) return;
        try {
          const style=instance.getStyle();
          if (style?.sources?.openmaptiles && !style.layers.some(layer=>layer.type==='fill-extrusion')) {
            instance.addLayer({id:'ramhub-real-3d-buildings',type:'fill-extrusion',source:'openmaptiles',
              'source-layer':'building',minzoom:14,
              paint:{'fill-extrusion-color':'#c7bba5',
                'fill-extrusion-height':['coalesce',['get','render_height'],['get','height'],10],
                'fill-extrusion-base':['coalesce',['get','render_min_height'],0],
                'fill-extrusion-opacity':0.83}});
          }
        } catch (error) {console.warn('RamHub building layer:',error.message);}
        mapLoading=false;
        mapReady=true;
        syncRealMarkers();
        syncBuildingMarkers();
        syncBuildingLabels();
        clearTimeout(mapTimeout);
        if (!sourceMode) hideFallback();
        statusMessage('3D campus ready · drag to explore · scroll to zoom');
      });
      instance.on('error', e => console.warn('RamHub map tile:',e.error?.message || 'Map tile failed'));
    } catch (error) {
      if (mapLoading) fail3D(error.message);
    }
  }
  initializeMap();

  // Dynamically resolve actual campus lot geometry with OpenStreetMap Overpass.
  // Data is matched by numbered `ref` or `name`; unrelated areas are discarded.
  // This is geographic data ONLY: it cannot reveal whether spaces are vacant.
  const OVERPASS_Q='[out:json][timeout:25];(nwr["amenity"="parking"](40.7468,-73.439,40.7595,-73.416););out center tags;';
  const OVERPASS_ENDPOINTS=[
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass-api.de/api/interpreter'
  ];
  function lotIdFromTags(tags){
    const ref=String(tags?.ref||'').trim().toUpperCase();
    const refMatch=ref.match(/^#?(\d{1,2}[A-Z]?)$/);
    if(refMatch && ALL_LOTS.includes(refMatch[1])) return refMatch[1];
    const name=String(tags?.name||'');
    const m=name.match(/\bLOT\s*(?:NO\.?\s*)?#?\s*(\d{1,2}[A-Z]?)(?![\dA-Z])/i);
    if(!m)return null;
    const id=m[1].toUpperCase();
    return ALL_LOTS.includes(id)?id:null;
  }
  function usableOSM(entry){
    const lat=Number(entry.center?.lat ?? entry.lat), lon=Number(entry.center?.lon ?? entry.lon);
    // Strictly bound candidate coordinates to FSC's main campus area, avoiding
    // unrelated Farmingdale Village / station lots with matching numbers.
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat<40.7468||lat>40.7595||lon< -73.439||lon> -73.416)return null;
    const tags=entry.tags||{}, id=lotIdFromTags(tags);
    if(!id)return null;
    const name=String(tags.name||'');
    if(!/lot/i.test(name)&&!String(tags.ref||''))return null;
    return {id,lat,lon,osm:'https://www.openstreetmap.org/'+entry.type+'/'+entry.id,
      label:name||'Parking Lot #'+id,source:'OSM '+entry.type+' '+entry.id};
  }
  function applyOSMFeatures(elements){
    let count=0;
    for(const item of elements){
      const p=usableOSM(item);
      if(!p || SOURCE_LOTS.has(p.id))continue;
      const existing=REFERENCE_LOTS[p.id];
      if(existing && existing.source?.startsWith('OSM ')) continue;
      REFERENCE_LOTS[p.id]=p;
      count++;
    }
    osmLookupState='ready';osmMatched=count;
    syncRealMarkers();
    if(selectedLot)updateLotDetails(selectedLot);
    if(mapReady && !sourceMode)statusMessage('Mapped '+Object.keys(REFERENCE_LOTS).length+' of '+ALL_LOTS.length+' published lots · choose one to explore');
  }
  async function loadOfficialOSMGeometry(){
    let result=null;
    // Endpoints are independent; fail gracefully if both are unavailable.
    for(const endpoint of OVERPASS_ENDPOINTS){
      const controller=new AbortController();
      const timer=setTimeout(()=>controller.abort(),11000);
      try{
        const resp=await fetch(endpoint+'?data='+encodeURIComponent(OVERPASS_Q),{signal:controller.signal,headers:{Accept:'application/json'}});
        if(!resp.ok)throw Error('HTTP '+resp.status);
        const parsed=await resp.json();
        if(!Array.isArray(parsed.elements))throw Error('Unrecognized Overpass response');
        result=parsed.elements;break;
      }catch(e){console.info('RamHub OSM lot lookup unavailable at '+new URL(endpoint).hostname+': '+e.message);}
      finally{clearTimeout(timer);}

    }
    if(result){applyOSMFeatures(result);return;}
    osmLookupState='unavailable';
    if(selectedLot)updateLotDetails(selectedLot);
  }
  // Start without blocking the page or the map, but do not claim live sensor data.
  loadOfficialOSMGeometry();

  /* RAMHUB_BUILDING_MAP_V1 — building locations connected to real campus map. */
  // Static references are source-confirmed geographic points, NOT classroom doors.
  // Remaining campus buildings are looked up by their OSM feature name within the FSC bounding box.
  const BUILDING_POINTS = {
    'Lupton Hall':{lat:40.75075,lon:-73.43125,source:'https://www.openstreetmap.org/way/470067577'},
    'Nold Hall':{lat:40.74889,lon:-73.43167,source:'https://topoquest.com/map/usgs-24k/new-york/amityville/890'},
    'Gleeson Hall':{lat:40.75301,lon:-73.42862,source:'https://www.openstreetmap.org/way/470064987'},
    'Greenley Library':{lat:40.75153,lon:-73.42951,source:'https://www.openstreetmap.org/way/49332856'},
    'Hale Hall':{lat:40.752222,lon:-73.430278,source:'https://topoquest.com/place/new-york/populated-place/north-wantagh/958941'},
    'Hicks Hall':{lat:40.753611,lon:-73.426667,source:'https://topoquest.com/place/new-york/building/hicks-hall/2076540'}
  };
  const NAME_ALIASES = {
    'nold atletic complex':'Nold Hall',
    'nold athletic complex':'Nold Hall',
    'thomas d greenley library':'Greenley Library',
    'thomas d. greenley library':'Greenley Library',
    'farmingdale campus center':'Campus Center',
    'business school':'School of Business',
    'farmingdale school of business':'School of Business',
    'childrens center':'Children’s Center'
  };
  let selectedBuildingName = '';
  let buildingLookupBusy=false;
  let buildingLookupComplete=false;
  let buildingMarker=null;
  const buildingStatus = $('buildingMapStatus');
  const buildingSuggestions = $('buildingNearbyLots');
  const buildingPick = $('mapBuildingPicker');
  const plannerPick = $('destination');
  const MAP_OFFICIAL_BUILDINGS='https://tour.farmingdale.edu/';

  function normalizeBuildingName(value){
    return String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[\u2018\u2019']/g,'').replace(/[^a-z0-9]+/g,' ').trim();
  }
  function canonicalBuildingName(input){
    const raw=normalizeBuildingName(input);
    const known=NAME_ALIASES[raw];if(known)return known;
    for(const opt of plannerPick.options){if(opt.value && normalizeBuildingName(opt.value)===raw)return opt.value;}
    return null;
  }
  function checkCampusPoint(lat,lon){
    return Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=40.7465&&lat<=40.7595&&lon>=-73.439&&lon<=-73.417;
  }
  function pointFromOSM(entry){
    const tags=entry.tags||{};
    const name=canonicalBuildingName(tags.name||tags['name:en']||'');
    const lat=Number(entry.center?.lat??entry.lat), lon=Number(entry.center?.lon??entry.lon);
    if(!name||!checkCampusPoint(lat,lon))return null;
    if(!tags.building&&!tags.amenity&&!tags.leisure&&!tags.office) return null;
    return {name,lat,lon,source:'https://www.openstreetmap.org/'+entry.type+'/'+entry.id};
  }
  function nextLotDistance(latA,lonA,latB,lonB){
    const toRad=Math.PI/180;
    const dLat=(latB-latA)*toRad,dLon=(lonB-lonA)*toRad;
    const a=Math.sin(dLat/2)**2+Math.cos(latA*toRad)*Math.cos(latB*toRad)*Math.sin(dLon/2)**2;
    return 6371000*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
  }
  function nearbyLotReferences(place){
    return Object.entries(REFERENCE_LOTS)
      .filter(([id,lot])=>ALL_LOTS.includes(id)&&checkCampusPoint(Number(lot.lat),Number(lot.lon)))
      .map(([id,lot])=>({id,meters:nextLotDistance(place.lat,place.lon,Number(lot.lat),Number(lot.lon))}))
      .sort((a,b)=>a.meters-b.meters).slice(0,3);
  }
  function updateBuildingSuggestions(name){
    const pt=BUILDING_POINTS[name];
    buildingSuggestions.replaceChildren();
    if(!pt){
      buildingStatus.textContent='No independently mapped point found for '+name+'. Open the official FSC campus map to locate it.';
      const a=document.createElement('a');a.href=MAP_OFFICIAL_BUILDINGS;a.textContent='Find this building on FSC’s campus map';a.target='_blank';a.rel='noopener noreferrer';buildingSuggestions.append(a);
      return;
    }
    buildingStatus.textContent='Destination: '+name+' · mapped location (not a live parking guarantee).';
    const caption=document.createElement('p');caption.textContent='Closest mapped lots by straight-line distance (NOT verified walking routes, permits, or vacant spaces):';buildingSuggestions.append(caption);
    for(const {id,meters} of nearbyLotReferences(pt)){
      const b=document.createElement('button');b.type='button';b.className='building-lot-suggestion';
      b.textContent='Lot #'+id+' · about '+Math.round(meters/10)*10+' m (straight line)';
      b.addEventListener('click',()=>{updateLotDetails(id);if(map&&mapReady)statusMessage('Viewing Lot #'+id+' near '+name+'. Check parking signs and permits.');});
      buildingSuggestions.append(b);
    }
    const source=document.createElement('a');source.href=pt.source;source.target='_blank';source.rel='noopener noreferrer';source.textContent='View building’s mapped source';buildingSuggestions.append(source);
  }
  function showBuildingMarker(name){
    if(buildingMarker){try{buildingMarker.remove();}catch(_){} buildingMarker=null;}
    const pt=BUILDING_POINTS[name];
    if(!pt||!map||!mapReady||!window.maplibregl||sourceMode)return;
    const el=document.createElement('div');el.className='ramhub-building-pin';
    el.textContent=name;el.title='Destination: '+name;el.setAttribute('aria-label','Destination: '+name);
    const marker=new window.maplibregl.Marker({element:el,anchor:'bottom'})
      .setLngLat([pt.lon,pt.lat]).addTo(map);
    buildingMarker=marker;
  }
  function focusBuilding(name, scrollToMap=true, skipLookup=false){
    selectedBuildingName=name;
    syncBuildingLabels();
    if(!name){
      buildingStatus.textContent='Choose your classroom building to locate it on the campus map.';
      buildingSuggestions.replaceChildren();
      if(buildingMarker){try{buildingMarker.remove();}catch(_){}buildingMarker=null;}
      return;
    }
    if(plannerPick.value!==name)plannerPick.value=name;
    if(buildingPick.value!==name)buildingPick.value=name;
    updatePlanner();
    updateBuildingSuggestions(name);
    if(scrollToMap)document.getElementById('map').scrollIntoView({behavior:'smooth',block:'start'});
    const place=BUILDING_POINTS[name];
    if(place&&map&&mapReady){
      if(sourceMode)setMode(true);
      showBuildingMarker(name);
      map.flyTo({center:[place.lon,place.lat],zoom:17.5,pitch:55,bearing:-27,duration:850});
      statusMessage('Showing mapped building: '+name+' · click a suggested lot to explore');
    }else if(place && !mapReady){
      buildingStatus.textContent='Mapped '+name+'. Switch to the 3D map once it finishes loading to highlight the destination.';
    }else if(!place && !buildingLookupComplete && !skipLookup){
      buildingStatus.textContent='Looking for '+name+' in actual OpenStreetMap building records…';
      searchMappedBuildings();
    }
  }
  // Only mapped buildings receive pins. No generic campus-centre pin is substituted.
  async function searchMappedBuildings(){
    if(buildingLookupBusy||buildingLookupComplete)return;
    buildingLookupBusy=true;
    const query='[out:json][timeout:20];(nwr["name"~"Hall|Library|Center|Business|Nold|Gleeson|Lupton|Hale|Hicks|Whitman|Roosevelt|Greenhouse|Dewey|Orchard|Knapp|Thompson|Police|Quintyne|Laffin",i](40.7465,-73.439,40.7595,-73.417););out center tags;';
    let points=null;
    for(const endpoint of ['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']){
      const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),11500);
      try{
        const res=await fetch(endpoint+'?data='+encodeURIComponent(query),{signal:controller.signal,headers:{Accept:'application/json'}});
        if(!res.ok)throw Error('HTTP '+res.status);
        const data=await res.json();if(!Array.isArray(data.elements))throw Error('No OSM elements');
        points=data.elements;break;
      }catch(err){console.info('RamHub building location lookup: '+err.message);}finally{clearTimeout(timeout);}
    }
    if(points){
      for(const item of points){
        const p=pointFromOSM(item);
        if(p&&!BUILDING_POINTS[p.name])BUILDING_POINTS[p.name]=p;
      }
    }
    syncBuildingLabels();
    buildingLookupBusy=false;
    buildingLookupComplete=true;
    if(selectedBuildingName)focusBuilding(selectedBuildingName,false,true);
    if(!points && selectedBuildingName && !BUILDING_POINTS[selectedBuildingName])buildingStatus.textContent='External building lookup unavailable. '+selectedBuildingName+' can still be found using FSC’s official map.';
  }
  // The map-sidebar selector mirrors the existing planner selector so all building names
  // (including the 42-item directory when installed) stay in sync.
  for(const child of plannerPick.children){
    buildingPick.appendChild(child.cloneNode(true));
  }
  buildingPick.addEventListener('change',()=>focusBuilding(buildingPick.value,true));
  plannerPick.addEventListener('change',()=>focusBuilding(plannerPick.value,true));
  $('saveDefault').addEventListener('click',()=>{if(plannerPick.value)focusBuilding(plannerPick.value,false);});
  if(plannerPick.value){
    buildingPick.value=plannerPick.value;
    focusBuilding(plannerPick.value,false);
  }
  // Existing 3D map's load callback calls this function once real map geometry is ready.
  function syncBuildingMarkers(){
    if(selectedBuildingName)focusBuilding(selectedBuildingName,false,true);
    if(!buildingLookupComplete&&!buildingLookupBusy)searchMappedBuildings();
  }


  /* RAMHUB_BUILDING_LABELS_V2: show on-map names for located FSC buildings. */
  const campusBuildingLabels = new Map();
  function syncBuildingLabels(){
    // MapLibre markers track 3D map pitch and movement; no invented x/y pixel positions.
    for(const marker of campusBuildingLabels.values()){
      try{marker.remove();}catch(_){}
    }
    campusBuildingLabels.clear();
    if(!map || !mapReady || !window.maplibregl) return;
    for(const [name,point] of Object.entries(BUILDING_POINTS)){
      if(name===selectedBuildingName || !checkCampusPoint(Number(point.lat),Number(point.lon))) continue;
      const button=document.createElement('button');
      button.type='button';
      button.className='ramhub-map-building-label';
      button.textContent=name;
      button.title='View '+name+' on the campus map';
      button.setAttribute('aria-label','Focus building: '+name);
      button.addEventListener('click',ev=>{ev.stopPropagation();focusBuilding(name,false,true);});
      const marker=new window.maplibregl.Marker({element:button,anchor:'bottom'})
        .setLngLat([Number(point.lon),Number(point.lat)]).addTo(map);
      campusBuildingLabels.set(name,marker);
    }
  }

  // The chart is generated only from *real user-entered local observations*.
  // It is not a traffic sensor, not an FSC feed, and not shared across student devices.
  const STORE='ramhub.parking.observations.v1';
  function readReports(){try{const arr=JSON.parse(localStorage.getItem(STORE)||'[]');return Array.isArray(arr)?arr.filter(r=>Number.isInteger(r.hour)&&r.hour>=0&&r.hour<24&&ALL_LOTS.includes(r.lot)&&r.difficulty>=1&&r.difficulty<=4):[];}catch(e){return [];}}
  function drawChart(){
    const reports=readReports().filter(r=>r.lot===$('chartLot').value);
    $('chartSub').textContent=`${reports.length} local observation${reports.length===1?'':'s'} for Student Lot #${$('chartLot').value}`;
    const plot=$('chartArea');plot.replaceChildren();
    if(!reports.length){const empty=document.createElement('div');empty.className='chart-empty';empty.textContent='No actual parking reports for this lot yet. Record a visit below to build its history.';plot.append(empty);return;}
    for(let hour=6;hour<=21;hour++){
      const matching=reports.filter(r=>r.hour===hour);
      const average=matching.reduce((sum,r)=>sum+r.difficulty,0)/Math.max(1,matching.length);
      const col=document.createElement('div');col.className='chart-column';col.tabIndex=0;
      const bar=document.createElement('span');bar.style.height=matching.length?`${Math.round(average/4*100)}%`:'2px';bar.style.opacity=matching.length?'1':'.12';
      const pretty=(hour%12||12)+(hour<12?' AM':' PM');
      col.title=`${pretty}: ${matching.length} reports${matching.length?', average difficulty '+average.toFixed(1)+' of 4':''}`;
      col.setAttribute('aria-label',col.title);col.append(bar);plot.append(col);
    }
  }
  $('chartLot').addEventListener('change',drawChart);
  $('reportForm').addEventListener('submit',(e)=>{
    e.preventDefault();
    const reports=readReports();
    reports.push({lot:$('reportLot').value,difficulty:Number($('reportDifficulty').value),hour:Number(hourFmt.format(new Date())),at:new Date().toISOString()});
    try{localStorage.setItem(STORE,JSON.stringify(reports.slice(-300)));$('reportStatus').textContent='Recorded on this browser. Thanks for reporting after parking safely.';$('chartLot').value=$('reportLot').value;drawChart();}
    catch(err){$('reportStatus').textContent='This browser prevents local storage. The report was not saved.';}
  });
  $('clearReports').addEventListener('click',()=>{
    if(!window.confirm('Clear the parking observations saved on this browser?'))return;
    try{localStorage.removeItem(STORE);$('reportStatus').textContent='Your local observations were cleared.';drawChart();}
    catch(e){$('reportStatus').textContent='Unable to clear reports in this browser.';}
  });
  // Import recorded observations in a simple CSV schema. This does not invent occupancy.
  $('importReports').addEventListener('change',async event=>{
    const file=event.target.files?.[0];if(!file)return;
    try{
      if(file.size>2_000_000)throw Error('File exceeds 2 MB.');
      const lines=(await file.text()).replace(/^\uFEFF/,'').split(/\r?\n/).filter(line=>line.trim());
      const headings=lines.shift()?.split(',').map(x=>x.trim().toLowerCase())||[];
      const cols=['timestamp','lot','difficulty'].map(x=>headings.indexOf(x));
      const hourCol=headings.indexOf('arrival_hour');
      if(cols.some(x=>x<0))throw Error('Use columns timestamp,lot,difficulty (optional arrival_hour).');
      const newReports=[];let invalid=0;
      for(const line of lines){
        const cells=line.split(',').map(x=>x.trim());
        const stamp=cells[cols[0]]||'';
        const match=/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(stamp);
        const lot=(cells[cols[1]]||'').replace(/^#/,''), difficulty=Number(cells[cols[2]]);
        if(!match||!ALL_LOTS.includes(lot)||!Number.isInteger(difficulty)||difficulty<1||difficulty>4){invalid++;continue;}
        const hour=hourCol>=0?Number(cells[hourCol]):Number(match[4]);
        const date=new Date(`${match[1]}-${match[2]}-${match[3]}T12:00:00`);
        if(!Number.isInteger(hour)||hour<0||hour>=24||!Number.isFinite(date.getTime())||date.getFullYear()!==Number(match[1])||date.getMonth()+1!==Number(match[2])||date.getDate()!==Number(match[3])){invalid++;continue;}
        newReports.push({lot,difficulty,hour,at:stamp});
      }
      if(newReports.length===0)throw Error('No valid rows were found.');
      const all=[...readReports(),...newReports].slice(-300);
      localStorage.setItem(STORE,JSON.stringify(all));
      $('importStatus').textContent=`Imported ${newReports.length} real observations${invalid?`; skipped ${invalid} invalid rows`:''}. Saved in this browser only.`;
      $('chartLot').value=newReports[0].lot;drawChart();
    }catch(e){$('importStatus').textContent=`Import failed: ${e.message}`;}
    event.target.value='';
  });
  $('exportReports').addEventListener('click',()=>{
    const reports=readReports();
    if(!reports.length){$('importStatus').textContent='No locally saved observations to export.';return;}
    const safe=str=>String(str??'').replace(/[\r\n,]/g,' ');
    // Export the recorded New York arrival hour explicitly so UTC timestamps round-trip.
    const csv='timestamp,lot,difficulty,arrival_hour\n'+reports.map(r=>[safe(r.at),safe(r.lot),r.difficulty,r.hour].join(',')).join('\n')+'\n';
    const objectURL=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=objectURL;a.download='ramhub-parking-observations.csv';
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(objectURL),5000);
    $('importStatus').textContent=`Exported ${reports.length} observations to CSV.`;
  });
  drawChart();
    /* RAMHUB_BUILDING_POPOUTS_V4
     Source-backed FSC buildings shown on the existing MapLibre 3D map.
     All catalog names appear in the searchable list. ONLY located names get map pins.
     This deliberately does not manufacture coordinates or available parking spaces.
  */
  const fscBuildingGroups = {
    'Academic buildings': ['Cutler Hall','Gleeson Hall','Hale Hall','Hicks Hall','Knapp Hall','Laffin Hall','Lupton Hall','Memorial Hall','Roosevelt Hall','School of Business','Sinclair Hall','Thompson Hall','Ward Hall','Whitman Hall'],
    'Campus services': ['Campus Center','Campus Commons','Greenley Library','Health & Wellness Center','Hooper Hall','Horton Hall','Nold Hall','Quintyne Hall','University Police'],
    'Residence halls': ['Alumni Hall','Dewey Hall','Orchard Hall'],
    'Other facilities': ['Agriculture Building','Capital Planning Trailer','Children’s Center','Conference Center','Custodial Building','Driving Range Office','Greenhouse','Hay Barn','Heating Plant','Poultry Building','Service Building','Smart Grid House','Storage Building'],
    'Other FSC sites (may be off campus)': ['Aviation Education Center','Broad Hollow Bioscience Park','Fred R. Harrison Service Complex']
  };
  const fscBuildingNames = Object.values(fscBuildingGroups).flat();
  const fscOfficialTour = 'https://tour.farmingdale.edu/';
  // Existing BUILDING_POINTS were already source-linked in earlier RamHub releases;
  // no additional coordinates are fabricated for the remaining directory entries.
  const fscBuildingPoints = {};
  if (typeof BUILDING_POINTS !== 'undefined') {
    for (const [name, point] of Object.entries(BUILDING_POINTS)) {
      if (point && Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)) &&
          Number(point.lat) >= 40.7465 && Number(point.lat) <= 40.7595 &&
          Number(point.lon) >= -73.439 && Number(point.lon) <= -73.417) {
        fscBuildingPoints[name] = {lat:Number(point.lat),lon:Number(point.lon),source:point.source || fscOfficialTour};
      }
    }
  }
  // For installs without the older connector, these are its six individually sourced references.
  const fscFallbackPoints = {
    'Lupton Hall': {lat:40.75075,lon:-73.43125,source:'https://www.openstreetmap.org/way/470067577'},
    'Nold Hall': {lat:40.74889,lon:-73.43167,source:'https://tour.farmingdale.edu/'},
    'Gleeson Hall': {lat:40.75301,lon:-73.42862,source:'https://www.openstreetmap.org/way/470064987'},
    'Greenley Library': {lat:40.75153,lon:-73.42951,source:'https://www.openstreetmap.org/way/49332856'},
    'Hale Hall': {lat:40.752222,lon:-73.430278,source:'https://tour.farmingdale.edu/'},
    'Hicks Hall': {lat:40.753611,lon:-73.426667,source:'https://tour.farmingdale.edu/'}
  };
  for (const [name,pt] of Object.entries(fscFallbackPoints)) if (!fscBuildingPoints[name]) fscBuildingPoints[name] = pt;

  /* Approximate main-campus positions digitized from the published FSC April 2025 plan.
     Their source is the official map, NOT independently surveyed GPS coordinates.
     Six older OSM points above remain preferred where available.
     See README for validation and attribution details. */
  const FSC_2025_PLAN_SOURCE = "https://www.farmingdale.edu/capital-projects-and-construction/pdfs/2025aprilcampusmapduringconstruction.pdf";
  const fscOfficialPlanApprox = {
  "Cutler Hall": {
    "lat": 40.7534329,
    "lon": -73.4262478,
    "planPx": [
      980,
      507
    ]
  },
  "Gleeson Hall": {
    "lat": 40.7530118,
    "lon": -73.4286303,
    "planPx": [
      773,
      391
    ]
  },
  "Hale Hall": {
    "lat": 40.7520783,
    "lon": -73.4302029,
    "planPx": [
      584,
      369
    ]
  },
  "Hicks Hall": {
    "lat": 40.7535105,
    "lon": -73.4267453,
    "planPx": [
      950,
      469
    ]
  },
  "Knapp Hall": {
    "lat": 40.7516942,
    "lon": -73.4281049,
    "planPx": [
      706,
      534
    ]
  },
  "Laffin Hall": {
    "lat": 40.7506184,
    "lon": -73.428587,
    "planPx": [
      585,
      593
    ]
  },
  "Lupton Hall": {
    "lat": 40.7507109,
    "lon": -73.4310521,
    "planPx": [
      413,
      429
    ]
  },
  "Memorial Hall": {
    "lat": 40.7503137,
    "lon": -73.4275518,
    "planPx": [
      636,
      684
    ]
  },
  "Roosevelt Hall": {
    "lat": 40.7504295,
    "lon": -73.4297813,
    "planPx": [
      483,
      533
    ]
  },
  "School of Business": {
    "lat": 40.7519924,
    "lon": -73.4273191,
    "planPx": [
      787,
      559
    ]
  },
  "Sinclair Hall": {
    "lat": 40.7520868,
    "lon": -73.4257599,
    "planPx": [
      908,
      650
    ]
  },
  "Thompson Hall": {
    "lat": 40.7538618,
    "lon": -73.4278454,
    "planPx": [
      898,
      370
    ]
  },
  "Ward Hall": {
    "lat": 40.7524854,
    "lon": -73.4291794,
    "planPx": [
      691,
      400
    ]
  },
  "Whitman Hall": {
    "lat": 40.7524424,
    "lon": -73.4278954,
    "planPx": [
      781,
      485
    ]
  },
  "Campus Center": {
    "lat": 40.7541997,
    "lon": -73.4282849,
    "planPx": [
      893,
      314
    ]
  },
  "Campus Commons": {
    "lat": 40.7545357,
    "lon": -73.4271971,
    "planPx": [
      999,
      355
    ]
  },
  "Greenley Library": {
    "lat": 40.7517429,
    "lon": -73.4298074,
    "planPx": [
      586,
      422
    ]
  },
  "Health & Wellness Center": {
    "lat": 40.7503562,
    "lon": -73.4271174,
    "planPx": [
      671,
      708
    ]
  },
  "Hooper Hall": {
    "lat": 40.7509363,
    "lon": -73.4273968,
    "planPx": [
      697,
      642
    ]
  },
  "Horton Hall": {
    "lat": 40.7550788,
    "lon": -73.4273672,
    "planPx": [
      1030,
      299
    ]
  },
  "Nold Hall": {
    "lat": 40.7488785,
    "lon": -73.431597,
    "planPx": [
      227,
      547
    ]
  },
  "Quintyne Hall": {
    "lat": 40.7536581,
    "lon": -73.428996,
    "planPx": [
      798,
      314
    ]
  },
  "University Police": {
    "lat": 40.755624,
    "lon": -73.426399,
    "planPx": [
      1144,
      315
    ]
  },
  "Alumni Hall": {
    "lat": 40.7509759,
    "lon": -73.4266981,
    "planPx": [
      751,
      683
    ]
  },
  "Dewey Hall": {
    "lat": 40.7512335,
    "lon": -73.4260602,
    "planPx": [
      818,
      702
    ]
  },
  "Orchard Hall": {
    "lat": 40.7504888,
    "lon": -73.4245146,
    "planPx": [
      871,
      862
    ]
  },
  "Capital Planning Trailer": {
    "lat": 40.7530772,
    "lon": -73.431052,
    "planPx": [
      602,
      232
    ]
  },
  "Children’s Center": {
    "lat": 40.7534051,
    "lon": -73.4243759,
    "planPx": [
      1114,
      628
    ]
  },
  "Greenhouse": {
    "lat": 40.7545649,
    "lon": -73.4266383,
    "planPx": [
      1042,
      388
    ]
  },
  "Heating Plant": {
    "lat": 40.7536319,
    "lon": -73.4303552,
    "planPx": [
      697,
      230
    ]
  },
  "Service Building": {
    "lat": 40.753894,
    "lon": -73.4308628,
    "planPx": [
      681,
      176
    ]
  },
  "Smart Grid House": {
    "lat": 40.7491907,
    "lon": -73.4286004,
    "planPx": [
      470,
      711
    ]
  }
};
  for(const [name,pt] of Object.entries(fscOfficialPlanApprox)) {
    if(!fscBuildingPoints[name]) fscBuildingPoints[name]={lat:pt.lat,lon:pt.lon,accuracy:'plan-estimated',source:FSC_2025_PLAN_SOURCE};
  }
  // Source-located CAMPUS SITE points; these are not individual facility entrances.
  const fscVerifiedSiteCenters = {
  "Broad Hollow Bioscience Park": {
    "lat": 40.7558333,
    "lon": -73.4241667,
    "source": "https://www.anyplaceamerica.com/directory/ny/suffolk-county-36103/locales/broad-hollow-bioscience-park-2076557/",
    "accuracy": "site-center",
    "siteOnly": true,
    "siteName": "Broad Hollow Bioscience Park"
  },
  "Fred R. Harrison Service Complex": {
    "lat": 40.75757,
    "lon": -73.42978,
    "source": "https://truckparkinginfo.com/new-york/farmingdale/fred-r-harrison-service-complex/",
    "accuracy": "site-center",
    "siteOnly": true,
    "siteName": "Fred R. Harrison Service Complex"
  }
};
  for(const [name,pt] of Object.entries(fscVerifiedSiteCenters)) fscBuildingPoints[name]=pt;
  const fscHarrisonFacilities = ["Agriculture Building", "Conference Center", "Custodial Building", "Driving Range Office", "Hay Barn", "Poultry Building", "Storage Building"];
  for(const name of fscHarrisonFacilities) fscBuildingPoints[name]={...fscVerifiedSiteCenters['Fred R. Harrison Service Complex'],accuracy:'complex-only',siteOnly:true,siteName:'Fred R. Harrison Service Complex'};
  const fscAviationAddress = '885 Broadhollow Road, Farmingdale, NY 11735';
  const fscAviationDirections = 'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(fscAviationAddress);

  const fscNameKey = s => String(s||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const fscNamesByKey = new Map(fscBuildingNames.map(n => [fscNameKey(n),n]));
  const fscAliases = {
    'nold athletic complex':'Nold Hall', 'nold atletic complex':'Nold Hall',
    'thomas d greenley library':'Greenley Library', 'greenley hall':'Greenley Library',
    'business school':'School of Business', 'farmingdale school of business':'School of Business',
    'farmingdale campus center':'Campus Center', 'childrens center':'Children’s Center',
    'hicks art center':'Hicks Hall', 'memorial gallery':'Memorial Hall'
  };
  const fscResolveName = raw => fscNamesByKey.get(fscNameKey(raw)) || fscAliases[fscNameKey(raw)] || null;
  let fscMapShown = null;
  let fscMapMarkers = new Map();
  let fscBuildingPopup = null;
  let fscSelectedName = '';
  let fscShowingLabels = true;
  let fscOSMState = 'pending';
  let fscLastCount = -1;
  let fscLastReady = false;

  // Inject into the rendered page itself. This solves template-selection/stale HTML issues.
  const fscSidebar = document.querySelector('.lot-sidebar');
  if (!fscSidebar) {
    console.warn('RamHub building popups: parking sidebar not found.');
  } else {
    const fscPanel = document.createElement('section');
    fscPanel.className = 'fsc-building-explorer';
    fscPanel.id = 'fscBuildingExplorer';
    const heading = document.createElement('h3'); heading.textContent = 'Find a campus building';
    const eyebrow = document.createElement('div');eyebrow.className='fsc-building-eyebrow';eyebrow.textContent='FSC / BUILDING DIRECTORY';
    const description = document.createElement('p');description.className='fsc-building-intro';description.textContent='Named buildings appear as clickable pins where their map locations are documented.';
    const inputLabel = document.createElement('label');inputLabel.htmlFor='fscBuildingSearch';inputLabel.textContent='Search buildings';
    const search = document.createElement('input');search.type='search';search.id='fscBuildingSearch';search.placeholder='Try Lupton Hall, Whitman Hall…';search.autocomplete='off';
    const clearSearch=document.createElement('button');clearSearch.type='button';clearSearch.className='fsc-show-all-buildings';clearSearch.textContent='Show all 42 buildings and locations';
    clearSearch.addEventListener('click',()=>{search.value='';fscRenderDirectory();search.focus();});
    const toggleWrap = document.createElement('label');toggleWrap.className='fsc-labels-toggle';
    const toggle = document.createElement('input');toggle.id='fscShowBuildingLabels';toggle.type='checkbox';toggle.checked=true;
    const toggleText = document.createElement('span');toggleText.textContent='Show building names on map';toggleWrap.append(toggle,toggleText);
    const count = document.createElement('p');count.id='fscBuildingCount';count.className='fsc-building-count';count.setAttribute('role','status');
    const results=document.createElement('div');results.id='fscBuildingResults';results.className='fsc-building-results';results.setAttribute('role','list');
    const selected=document.createElement('div');selected.id='fscBuildingDetails';selected.className='fsc-building-details';selected.setAttribute('role','status');
    const official=document.createElement('a');official.href=fscOfficialTour;official.target='_blank';official.rel='noopener noreferrer';official.className='fsc-official-link';official.textContent='Official FSC interactive campus map';
    fscPanel.append(eyebrow,heading,description,inputLabel,search,clearSearch,toggleWrap,count,results,selected,official);
    fscSidebar.insertBefore(fscPanel,fscSidebar.firstChild);

    const distM=(a,b)=>{const lat1=a.lat*Math.PI/180,lat2=b.lat*Math.PI/180,dLat=lat2-lat1,dLon=(b.lon-a.lon)*Math.PI/180;
      const h=Math.sin(dLat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dLon/2)**2;return 6371000*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));};
    function fscNearby(pt){
      if(typeof REFERENCE_LOTS==='undefined')return [];
      return Object.entries(REFERENCE_LOTS).filter(([id,l])=>Number.isFinite(Number(l.lat))&&Number.isFinite(Number(l.lon)))
        .map(([id,l])=>({id,meters:distM(pt,{lat:Number(l.lat),lon:Number(l.lon)})})).sort((a,b)=>a.meters-b.meters).slice(0,3);
    }
    function fscDetails(name){
      selected.replaceChildren();
      const title=document.createElement('strong');title.textContent=name;selected.append(title);
      const pt=fscBuildingPoints[name];
      if(!pt){
        const p=document.createElement('p');p.textContent=name==='Aviation Education Center'?'The Aviation Education Center is at '+fscAviationAddress+'. This is an off-campus address, not a main-campus building pin.':'The exact mapped building position is not available.';selected.append(p);
        const a=document.createElement('a');a.href=name==='Aviation Education Center'?fscAviationDirections:fscOfficialTour;a.target='_blank';a.rel='noopener noreferrer';a.textContent=name==='Aviation Education Center'?'Open address in Google Maps':'Find it on the official FSC campus map';selected.append(a);return;
      }
      const p=document.createElement('p');p.textContent=pt.siteOnly?'Site-level reference: this facility is associated with '+pt.siteName+'. The individual building entrance has not been independently mapped.':pt.accuracy==='plan-estimated'?'Approximate position aligned from FSC’s published April 2025 map, not a surveyed building coordinate. Tap its label to view details.':'Mapped location reference. Tap its label on the map to view details.';selected.append(p);
      const near=pt.siteOnly?[]:fscNearby(pt);
      if(near.length){const sub=document.createElement('p');sub.textContent='Closest mapped lots by straight-line distance (not a walking route or space guarantee):';selected.append(sub);
        for(const entry of near){const b=document.createElement('button');b.type='button';b.className='fsc-nearby-lot';b.textContent='Lot #'+entry.id+' · ~'+Math.round(entry.meters/10)*10+' m';
          b.addEventListener('click',()=>{if(typeof updateLotDetails==='function')updateLotDetails(entry.id);if(map&&mapReady&&REFERENCE_LOTS[entry.id]){const l=REFERENCE_LOTS[entry.id];map.flyTo({center:[l.lon,l.lat],zoom:17.5,pitch:55,duration:750});}});
          selected.append(b);}
      }
      const a=document.createElement('a');a.href=pt.source;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Location source / campus reference';selected.append(a);
    }
    function fscPopContent(name){
      const wrap=document.createElement('div');wrap.className='fsc-map-pop-content';
      const kicker=document.createElement('div');kicker.className='fsc-popup-kicker';kicker.textContent='FARMINGDALE STATE COLLEGE';
      const pt=fscBuildingPoints[name];
      const h=document.createElement('h4');h.textContent=pt.siteOnly ? name+' (service site)' : name;
      const p=document.createElement('p');p.textContent=pt.siteOnly?'Site-level location only. The exact facility footprint is not confirmed.':pt.accuracy==='plan-estimated'?'Approximate building position from FSC’s published 2025 campus plan.':'Mapped campus building reference.';
      const near=pt.siteOnly?[]:fscNearby(pt);
      const line=document.createElement('p');line.textContent=near.length?'Nearest mapped lot reference points (straight-line only): '+near.map(x=>'#'+x.id).join(', '):'See FSC’s official parking plan; no live spaces are reported.';
      const link=document.createElement('a');link.target='_blank';link.rel='noopener noreferrer';link.href=fscBuildingPoints[name].source;link.textContent='View map source';
      if(name==='Fred R. Harrison Service Complex'){
        const facilities=document.createElement('p');
        facilities.textContent='Published service-complex facilities: '+fscHarrisonFacilities.join(', ')+'. Individual entrances have not been mapped.';
        wrap.append(kicker,h,p,facilities,line,link);
      } else wrap.append(kicker,h,p,line,link);
      return wrap;
    }
    function fscOpenPopup(name,fly){
      const pt=fscBuildingPoints[name];if(!pt)return;
      if(!map || !mapReady || !window.maplibregl){count.textContent='3D map is not ready. Switch to 3D to view the selected building.';return;}
      if (typeof sourceMode !== 'undefined' && sourceMode && typeof setMode === 'function') setMode(true);
      try{if(fscBuildingPopup)fscBuildingPopup.remove();
        fscBuildingPopup=new window.maplibregl.Popup({offset:24,closeOnClick:false,maxWidth:'300px'})
          .setLngLat([pt.lon,pt.lat]).setDOMContent(fscPopContent(name)).addTo(map);
        if(fly && typeof map.flyTo==='function')map.flyTo({center:[pt.lon,pt.lat],zoom:17.5,pitch:55,bearing:-26,duration:800});
      } catch(err){console.warn('RamHub building popup:',err.message);}
    }
    function fscChoose(name,fly=true){
      fscSelectedName=name;fscDetails(name);
      const planner=$('destination');if(planner&&[...planner.options].some(o=>o.value===name) && planner.value!==name){planner.value=name;planner.dispatchEvent(new Event('change',{bubbles:true}));}
      if(fscBuildingPoints[name])fscOpenPopup(name,fly);
      for(const el of results.querySelectorAll('.fsc-directory-item'))el.classList.toggle('selected',el.dataset.name===name);
    }
    function fscRenderDirectory(){
      const q=fscNameKey(search.value), filtered=fscBuildingNames.filter(name=>fscNameKey(name).includes(q));
      results.replaceChildren();
      for(const name of filtered){
        const button=document.createElement('button');button.className='fsc-directory-item';button.type='button';button.dataset.name=name;
        const left=document.createElement('span');left.textContent=name;
        const right=document.createElement('span');right.className='fsc-location-state';const info=fscBuildingPoints[name];right.textContent=!info?'Address':info.accuracy==='complex-only'?'Service site':info.accuracy==='site-center'?'Site pin':info.accuracy==='plan-estimated'?'Plan position':'Map pin';
        button.append(left,right);button.classList.toggle('selected',name===fscSelectedName);button.addEventListener('click',()=>fscChoose(name));
        results.append(button);
      }
      const campusCount=fscBuildingNames.filter(n=>fscBuildingPoints[n]&&!fscBuildingPoints[n].siteOnly).length;
      count.textContent=campusCount+' placed building/site labels · '+fscHarrisonFacilities.length+' service-complex references · '+fscBuildingNames.length+' total entries'+(fscOSMState==='pending'?' · checking OpenStreetMap…':'');
    }
    function fscSyncMap(){
      // Pick up any new source-backed locations discovered by the existing RamHub OSM lookup.
      if(typeof BUILDING_POINTS !== 'undefined') {
        for(const [name,point] of Object.entries(BUILDING_POINTS)) {
          const lat=Number(point?.lat),lon=Number(point?.lon);
          if(!fscBuildingNames.includes(name)||!Number.isFinite(lat)||!Number.isFinite(lon)||
              lat<40.7465||lat>40.7595||lon< -73.439||lon> -73.417)continue;
          const prior=fscBuildingPoints[name];
          if(!prior || prior.lat!==lat || prior.lon!==lon) {
            fscBuildingPoints[name]={lat,lon,source:point.source||fscOfficialTour,accuracy:'OSM'};
            const old=fscMapMarkers.get(name);
            if(old) {try{old.remove();}catch(_){}fscMapMarkers.delete(name);}
            fscRenderDirectory();
          }
        }
      }
      const m=mapReady && map && window.maplibregl ? map : null;
      if(!m){if(fscMapShown){for(const marker of fscMapMarkers.values()){try{marker.remove();}catch(_){}}fscMapMarkers.clear();fscMapShown=null;}return;}
      if(m!==fscMapShown){for(const marker of fscMapMarkers.values()){try{marker.remove();}catch(_){}}fscMapMarkers.clear();fscMapShown=m;}
      if(!fscShowingLabels){for(const marker of fscMapMarkers.values()){try{marker.remove();}catch(_){}}fscMapMarkers.clear();return;}
      for(const [name,pt] of Object.entries(fscBuildingPoints)){
        // Do not stack seven inaccurate individual pins at one service-complex centre.
        if(pt.accuracy==='complex-only')continue;
        if(fscMapMarkers.has(name))continue;
        const el=document.createElement('button');el.type='button';el.className='fsc-map-building-pin';el.textContent=name;
        el.title=pt.accuracy==='plan-estimated'?'Approximate official-plan position — '+name:'Click for '+name+' building information';
        if(pt.accuracy==='plan-estimated')el.classList.add('fsc-plan-derived-label');
        if(pt.siteOnly)el.classList.add('fsc-site-label');el.setAttribute('aria-label','View '+name+' information');
        el.addEventListener('click',event=>{event.stopPropagation();fscChoose(name,false);});
        try{const marker=new window.maplibregl.Marker({element:el,anchor:'bottom'}).setLngLat([pt.lon,pt.lat]).addTo(m);fscMapMarkers.set(name,marker);}
        catch(e){console.warn('Could not place FSC building pin:',name,e.message);}
      }
    }
    search.addEventListener('input',fscRenderDirectory);
    toggle.addEventListener('change',()=>{fscShowingLabels=toggle.checked;fscSyncMap();});
    fscRenderDirectory();
    if(!fscSelectedName){selected.textContent='Choose a building to open its map popup or see the official campus reference.';}
    // Old label implementation is deliberately not needed. The new pins attach to the live map.
    setInterval(fscSyncMap,900);

    async function fscLoadOSMBuildings(){
      const bbox='40.7465,-73.439,40.7595,-73.417';
      const query='[out:json][timeout:18];(nwr["name"]["building"]('+bbox+');nwr["name"]["amenity"]('+bbox+');nwr["name"]["office"]('+bbox+'););out center tags;';
      // Fetches real named OSM records; no guesses for missing buildings.
      for(const endpoint of ['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']){
        const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),10000);
        try{
          const res=await fetch(endpoint+'?data='+encodeURIComponent(query),{signal:controller.signal,headers:{Accept:'application/json'}});
          if(!res.ok)throw Error('HTTP '+res.status);
          const body=await res.json();if(!Array.isArray(body.elements))throw Error('Invalid OSM response');
          for(const item of body.elements){
            const resolved=fscResolveName(item.tags?.name || item.tags?.['name:en']);
            const lat=Number(item.center?.lat??item.lat),lon=Number(item.center?.lon??item.lon);
            if(!resolved||!Number.isFinite(lat)||!Number.isFinite(lon)||lat<40.7465||lat>40.7595||lon< -73.439||lon> -73.417)continue;
            fscBuildingPoints[resolved]={lat,lon,source:'https://www.openstreetmap.org/'+item.type+'/'+item.id,accuracy:'OSM'};
          }
          fscOSMState='ready';fscRenderDirectory();fscSyncMap();return;
        }catch(e){console.info('FSC building map lookup unavailable:',e.message);}
        finally{clearTimeout(timer);}
      }
      fscOSMState='unavailable';fscRenderDirectory();
    }
    // Existing RamHub building connector performs its own OSM lookup; reuse it
    // rather than doubling external requests. Older installations use this fallback.
    fscLoadOSMBuildings();

  }

})();
