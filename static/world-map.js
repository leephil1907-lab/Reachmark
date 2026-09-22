/* Locally bundled Leaflet; external tiles are optional. Saved records are never invented. */
let worldMap, worldTiles, worldMarkers, worldCoverage, worldScans=[], worldBusy=false, worldRequest=false;
const mapColors={checked:'#557831',partial:'#db9c40',failed:'#b85757',pending:'#838a94',running:'#387ba6'};
function mapMessage(text){$('#map-message').textContent=text}
function worldBounds(){const b=worldMap.getBounds(),wrap=n=>((n+180)%360+360)%360-180;return [Math.max(-90,b.getSouth()),wrap(b.getWest()),Math.min(90,b.getNorth()),wrap(b.getEast())]}
function loadBasemap(){
 if(worldTiles)worldMap.removeLayer(worldTiles);
 let errors=0,loaded=0;
 worldTiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,noWrap:false,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'});
 worldTiles.on('tileerror',()=>{if(++errors>=3)mapMessage('Some basemap tiles are unavailable. Saved markers, coordinates and scan areas still work. Use Reload basemap to try again.')});
 worldTiles.on('tileload',()=>{loaded++});worldTiles.addTo(worldMap);
}
function drawWorldLeads(){
 if(!worldMap)return;worldMarkers.clearLayers();
 const located=state.leads.filter(l=>typeof l.latitude==='number'&&typeof l.longitude==='number'&&Number.isFinite(l.latitude)&&Number.isFinite(l.longitude)&&Math.abs(l.latitude)<=90&&Math.abs(l.longitude)<=180);
 const rows=located.filter(l=>$('#map-filter').value==='all'||l.status!=='HAS_WEBSITE');
 rows.slice(0,5000).forEach(l=>{const content=document.createElement('div');content.className='map-popup';content.innerHTML=`<strong>${esc(l.name)}</strong><span>${esc(l.category)} · ${esc(l.city)}</span><br><span>${esc(statusLabel(l.status))}</span><br>`;const btn=document.createElement('button');btn.textContent='Review business ↗';btn.onclick=()=>openLead(l.id);content.appendChild(btn);L.marker([l.latitude,l.longitude],{title:l.name,icon:L.divIcon({className:'world-pin',html:`<span style="background:${l.status==='HAS_WEBSITE'?'#80abc0':'#cee77c'}"></span>`,iconSize:[16,16],iconAnchor:[8,8]})}).bindPopup(content).addTo(worldMarkers)});
 $('#map-records').textContent=`${Math.min(rows.length,5000)} mapped${rows.length>5000?' (5,000 display limit)':''} · ${state.leads.length-located.length} without valid coordinates`;
}
async function openWorldMap(){
 if(!window.L){mapMessage('Map library unavailable. Reload the page; your saved leads remain in the directory.');return}
 if(!worldMap){
  let view={center:[20,0],zoom:2};try{const saved=JSON.parse(localStorage.getItem('reachmark-map-view'));if(saved&&Array.isArray(saved.center)&&saved.center.length===2&&saved.center.every(Number.isFinite)&&Number.isFinite(saved.zoom))view=saved}catch{}
  worldMap=L.map('world-map',{worldCopyJump:true,preferCanvas:true,minZoom:2,maxZoom:19}).setView(view.center,view.zoom);
  worldMarkers=L.markerClusterGroup({maxClusterRadius:45,showCoverageOnHover:false,iconCreateFunction:cluster=>L.divIcon({className:'world-cluster',html:`<span>${cluster.getChildCount()}</span>`,iconSize:[38,38]})}).addTo(worldMap);worldCoverage=L.layerGroup().addTo(worldMap);loadBasemap();
  worldMap.on('moveend',()=>{const p=worldMap.getCenter();$('#map-coordinates').textContent=`${p.lat.toFixed(5)}, ${p.wrap().lng.toFixed(5)} · zoom ${worldMap.getZoom()}`;try{localStorage.setItem('reachmark-map-view',JSON.stringify({center:[p.lat,p.wrap().lng],zoom:worldMap.getZoom()}))}catch{}});
 }
 requestAnimationFrame(()=>worldMap.invalidateSize());
 const current=$('#map-category').value;$('#map-category').innerHTML=(state.categories||[]).map(c=>`<option>${esc(c)}</option>`).join('');if(current)$('#map-category').value=current;
 drawWorldLeads();await loadMapScans();
}
async function loadMapScans(){
 if(worldRequest)return;worldRequest=true;
 try{const result=await api('/api/map/state');const changed=JSON.stringify(worldScans)!==JSON.stringify(result.scans);worldScans=result.scans;drawMapScans();if(changed){await refresh();drawWorldLeads()}}
 catch(e){mapMessage('Could not refresh scan progress. Last displayed progress is retained. '+e.message)}finally{worldRequest=false}
}
function drawMapScans(){
 if(!worldMap)return;worldCoverage.clearLayers();
 for(const scan of worldScans)for(const cell of scan.cells){const [s,w,n,e]=cell.bounds;const rect=L.rectangle([[s,w],[n,e]],{color:mapColors[cell.state]||'#838a94',weight:2,fillOpacity:.1});const text=document.createElement('div');text.className='map-popup';text.innerHTML=`<strong>${esc(scan.label)}</strong>${esc(scan.category)} · ${esc(cell.state)}<br>${cell.found} listing hits<br>${esc(cell.message)}<br><small>${esc(new Date(cell.updated).toLocaleString())}</small>`;rect.bindPopup(text).addTo(worldCoverage)}
 worldMarkers.eachLayer(layer=>layer.bringToFront?.());
 $('#map-history').innerHTML=worldScans.length?worldScans.map(s=>{const checked=s.cells.filter(c=>c.state==='checked').length,retry=s.cells.some(c=>['pending','failed','running'].includes(c.state)),active=['queued','running'].includes(s.state);return `<article class="map-scan-row"><div><strong>${esc(s.label)}</strong><p class="small">${esc(s.category)} · ${esc(s.state)} · ${checked}/${s.cells.length} cells checked</p><p class="small muted">${esc(new Date(s.created).toLocaleString())} · ${s.cells.reduce((n,c)=>n+c.found,0)} listing hits (may overlap)</p></div><div class="map-scan-actions"><button type="button" class="text-link" data-map-fit="${s.id}">View area</button>${active?`<button type="button" class="text-link" data-map-action="cancel" data-id="${s.id}">Pause</button>`:retry?`<button type="button" class="text-link" data-map-action="resume" data-id="${s.id}">Resume unfinished</button>`:''}</div></article>`}).join(''):'<p class="small muted">No areas scanned yet. Navigate to a neighbourhood, choose a category and scan the visible area.</p>';
 $('#map-history').querySelectorAll('[data-map-fit]').forEach(b=>b.onclick=()=>{const s=worldScans.find(s=>s.id===b.dataset.mapFit);let [south,west,north,east]=s.bounds;if(west>east)east+=360;worldMap.fitBounds([[south,west],[north,east]],{padding:[18,18]})});
 $('#map-history').querySelectorAll('[data-map-action]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`/api/map/scans/${b.dataset.id}/${b.dataset.mapAction}`,'POST',{});await loadMapScans();mapMessage(b.dataset.mapAction==='cancel'?'Pause requested. An in-flight request may finish saving its cell.':'Resuming unfinished cells; checked cells will not be repeated.')}catch(e){mapMessage(e.message)}finally{b.disabled=false}});
}
$('#map-search-form').onsubmit=async e=>{e.preventDefault();const b=$('#map-search-btn');b.disabled=true;try{const query=$('#map-search').value.trim(),coordinates=query.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);if(coordinates){const lat=Number(coordinates[1]),lng=Number(coordinates[2]);if(Math.abs(lat)>85.05||Math.abs(lng)>180)throw Error('Map navigation supports latitude ±85.05 and longitude ±180.');worldMap.setView([lat,lng],14);mapMessage('Coordinates selected. Confirm the visible area before scanning.');return}mapMessage('Looking up this place…');const r=await api('/api/map/search','POST',{query});worldMap.setView([Number(r.place.lat),Number(r.place.lon)],14);$('#map-label').value=query.slice(0,150);mapMessage(`Matched: ${r.place.display_name||query}${r.cached?' · saved lookup':''}. Adjust the viewport before scanning.`)}catch(e){mapMessage(e.message)}finally{b.disabled=false}};
$('#map-world').onclick=()=>worldMap?.setView([20,0],2);
$('#map-saved').onclick=()=>{const points=state.leads.filter(l=>typeof l.latitude==='number'&&typeof l.longitude==='number'&&Math.abs(l.latitude)<=85.05&&Math.abs(l.longitude)<=180).map(l=>[l.latitude,l.longitude]);if(points.length)worldMap.fitBounds(points,{padding:[30,30],maxZoom:15});else mapMessage('No saved leads have displayable map coordinates yet.')};
$('#map-retry-tiles').onclick=()=>{if(worldMap){loadBasemap();mapMessage('Reloading visible basemap tiles.')}};
$('#map-filter').onchange=drawWorldLeads;
$('#map-scan-form').onsubmit=async e=>{e.preventDefault();if(worldBusy||!worldMap)return;const bounds=worldBounds(),raw=worldMap.getBounds();const height=(bounds[2]-bounds[0])*111.32,width=(raw.getEast()-raw.getWest())*111.32*Math.max(.01,Math.cos(worldMap.getCenter().lat*Math.PI/180));if(height>25||width>25||raw.getEast()-raw.getWest()>2){mapMessage('Zoom in before scanning: choose an area at most 25 km wide and high.');return}if(!confirm(`Scan the visible rectangle for ${$('#map-category').value}? Other categories and unmapped businesses are not included.`))return;worldBusy=true;$('#map-start').disabled=true;try{await api('/api/map/scans','POST',{bounds,category:$('#map-category').value,label:$('#map-label').value.trim()});await loadMapScans();mapMessage('Scan started. Progress is saved per cell; you can leave this page and return.')}catch(e){mapMessage(e.message)}finally{worldBusy=false;$('#map-start').disabled=false}};
setInterval(async()=>{if(!document.hidden&&$('#page-global').classList.contains('active')){await loadMapScans();drawWorldLeads()}},5000);
if(location.hash==='#global')openWorldMap();
