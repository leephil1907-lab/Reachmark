var T_=window.T||function(k,f){return f;};
let nwCurrent='cards',nwEvent=null,nwScanDraft=null;

function nwTab(t){nwCurrent=t;nwEvent=null;
document.querySelectorAll('#nw-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.nwtab===t));
loadNetwork()}
async function loadNetwork(){nwOfflineBar();
try{
if(nwCurrent==='cards')await nwCards();
else if(nwCurrent==='events')await (nwEvent?nwEventDetail(nwEvent):nwEvents());
else if(nwCurrent==='scan')await nwScan();
else if(nwCurrent==='book')await nwBook();
else await nwHooks();
}catch(err){document.getElementById('nw-body').innerHTML=`<div class="notice">${esc(err.message)}</div>`}}
function nwBody(h){document.getElementById('nw-body').innerHTML=h}

/* ---- offline capture queue (this device only) ---- */
function nwQueue(){try{return JSON.parse(localStorage.getItem('rm_nw_queue')||'[]')}catch{return[]}}
function nwQueueSave(q){localStorage.setItem('rm_nw_queue',JSON.stringify(q));nwOfflineBar()}
function nwOfflineBar(){const q=nwQueue(),bar=document.getElementById('nw-offline-bar');if(!bar)return;
bar.innerHTML=q.length?`<div class="notice"><b>${q.length}</b> · <button class="secondary" onclick="nwSync()">${T_('nw.w_sync','Sync now ({n})').replace('{n}',q.length)}</button></div>`:''}
async function nwSync(){const q=nwQueue();let done=0;
for(const item of q){try{await api('/api/events/'+item.eid+'/capture','POST',item.payload);done++}catch{break}}
nwQueueSave(q.slice(done));toast(T_('nw.w_synced','Offline captures synced.'));loadNetwork()}
window.addEventListener('online',()=>{if(nwQueue().length)nwSync()});

/* ---- cards ---- */
async function nwCards(){const r=await api('/api/cards');const cards=r.cards;
nwBody(`<div class="card"><div class="section-top"><h3>${T_('nw.w_cards','My cards')}</h3><button class="primary" onclick="nwCardForm()">${T_('nw.w_new_card','New card')}</button></div>
<div id="nw-card-list">${cards.length?cards.map(nwCardRow).join(''):`<p class="small muted">${T_('nw.w_empty_cards','No cards yet.')}</p>`}</div></div>
<div class="card" id="nw-card-form" style="display:none;margin-top:20px"></div>`)}
function nwCardRow(c){return `<div class="table-row" style="display:flex;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #eef1e4">
<div style="flex:1"><b>${esc(c.name)}</b><br/><small class="muted">${esc([c.role,c.org].filter(Boolean).join(' · '))}</small><br/>
<small><a href="/c/${c.token}" target="_blank" rel="noopener">/c/${c.token}</a></small></div>
<img src="/api/qr.png?u=/c/${c.token}" alt="QR" style="width:64px;height:64px;border-radius:8px"/>
<button class="secondary" onclick="window.open('/c/${c.token}','_blank')">${T_('nw.w_open','Open card')}</button>
<button class="secondary" onclick="nwCopy(location.origin+'/c/${c.token}')">${T_('nw.w_copy','Copy link')}</button>
<button class="secondary" onclick="nwCardForm('${c.id}')">${T_('ws.dr_savedet','Save')}</button>
<button class="danger-link" onclick="nwCardDel('${c.id}')">${T_('nw.w_del','Delete')}</button></div>`}
function nwCopy(t){(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>toast(T_('nw.w_copied','Copied.')),()=>window.prompt(t,t))}
async function nwCardForm(id){const f=document.getElementById('nw-card-form');let c={theme:'charcoal'};
if(id){const r=await api('/api/cards');c=r.cards.find(x=>x.id===id)||c}
const links=(c.links?JSON.parse(c.links):[]).map(l=>l.label+' | '+l.url).join('\n');
f.style.display='block';f.innerHTML=`<h3>${T_('nw.w_new_card','New card')}</h3>
<div class="form-grid"><label>${T_('nw.w_name','Full name')}<input id="nc-name" value="${esc(c.name||'')}"/></label>
<label>${T_('nw.w_role','Role')}<input id="nc-role" value="${esc(c.role||'')}"/></label></div>
<div class="form-grid"><label>${T_('nw.w_org','Organisation')}<input id="nc-org" value="${esc(c.org||'')}"/></label>
<label>${T_('nw.w_phone','Phone')}<input id="nc-phone" value="${esc(c.phone||'')}"/></label></div>
<div class="form-grid"><label>${T_('rv.email','E-mail')}<input id="nc-email" value="${esc(c.email||'')}"/></label>
<label>${T_('nw.w_site','Website')}<input id="nc-site" value="${esc(c.website||'')}"/></label></div>
<label>${T_('nw.w_theme','Theme')}<select id="nc-theme">${['charcoal','paper','lime'].map(t=>`<option ${c.theme===t?'selected':''}>${t}</option>`).join('')}</select></label>
<label>${T_('nw.w_links','Links')}<textarea id="nc-links" rows="3">${esc(links)}</textarea></label>
<button class="primary" onclick="nwCardSave('${id||''}')">${T_('nw.w_save','Save card')}</button>`;
f.scrollIntoView({behavior:'smooth'})}
async function nwCardSave(id){const v=i=>document.getElementById(i).value.trim();
const links=v('nc-links').split('\n').map(l=>l.split('|').map(s=>s.trim())).filter(p=>p[0]&&p[1]).map(p=>({label:p[0],url:p[1]}));
const body={name:v('nc-name'),role:v('nc-role'),org:v('nc-org'),phone:v('nc-phone'),email:v('nc-email'),website:v('nc-site'),theme:document.getElementById('nc-theme').value,links};
try{if(id)await api('/api/cards/'+id,'PUT',body);else await api('/api/cards','POST',body);
toast(T_('nw.w_saved','Saved.'));loadNetwork()}catch(err){toast(err.message,true)}}
async function nwCardDel(id){if(!confirm(T_('nw.w_delq','Delete this?')))return;
try{await api('/api/cards/'+id,'DELETE');loadNetwork()}catch(err){toast(err.message,true)}}

/* ---- events ---- */
async function nwEvents(){const r=await api('/api/events');
nwBody(`<div class="card"><div class="section-top"><h3>${T_('nw.w_events','Events')}</h3><button class="primary" onclick="nwEventForm()">${T_('nw.w_new_ev','New event')}</button></div>
<div id="nw-ev-list">${r.events.length?r.events.map(e=>{const pct=e.goal?Math.min(100,Math.round(e.captured/e.goal*100)):0;
return `<div style="padding:12px 0;border-bottom:1px solid #eef1e4"><b>${esc(e.name)}</b> <small class="muted">${esc(e.location||'')}</small><br/>
<small>${T_('nw.w_captured','{c} of {g} captured').replace('{c}',e.captured).replace('{g}',e.goal||'∞')}</small>
<div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
<button class="secondary" onclick="nwEventDetail('${e.id}')">${T_('wsj.ap_open','Open ↗')}</button>
<button class="danger-link" onclick="nwEventDel('${e.id}')">${T_('nw.w_del','Delete')}</button></div>`}).join(''):`<p class="small muted">${T_('nw.w_empty_ev','No events yet.')}</p>`}</div></div>
<div class="card" id="nw-ev-form" style="display:none;margin-top:20px"></div>`)}
function nwEventForm(){const f=document.getElementById('nw-ev-form');f.style.display='block';
f.innerHTML=`<h3>${T_('nw.w_new_ev','New event')}</h3><div class="form-grid"><label>${T_('nw.w_ev_name','Event name')}<input id="ne-name"/></label>
<label>${T_('nw.w_ev_loc','Location')}<input id="ne-loc"/></label></div>
<label>${T_('nw.w_goal','Lead goal')}<input id="ne-goal" type="number" min="0" value="50"/></label>
<button class="primary" onclick="nwEventSave()">${T_('nw.w_create','Create event')}</button>`}
async function nwEventSave(){try{await api('/api/events','POST',{name:document.getElementById('ne-name').value,location:document.getElementById('ne-loc').value,goal:document.getElementById('ne-goal').value});
loadNetwork()}catch(err){toast(err.message,true)}}
async function nwEventDel(id){if(!confirm(T_('nw.w_delq','Delete this?')))return;
try{await api('/api/events/'+id,'DELETE');loadNetwork()}catch(err){toast(err.message,true)}}

async function nwEventDetail(id){nwEvent=id;const d=await api('/api/events/'+id);const e=d.event;
const draft=nwScanDraft;nwScanDraft=null;
const quals=d.qualifiers.map(q=>q.kind==='choice'
?`<label>${esc(q.question)}<select data-q="${q.id}">${JSON.parse(q.options).map(o=>`<option>${esc(o)}</option>`).join('')}</select></label>`
:`<label>${esc(q.question)}<input data-q="${q.id}"/></label>`).join('');
nwBody(`<button class="text-link" onclick="nwEvent=null;loadNetwork()">← ${T_('nw.w_back','All events')}</button>
<div class="card" style="margin-top:12px"><div class="section-top"><h3>${esc(e.name)}</h3>
<span class="badge">${T_('nw.w_captured','{c} of {g} captured').replace('{c}',d.leads.length).replace('{g}',e.goal||'∞')}</span></div>
<div id="nw-stats" class="small muted"></div></div>
<div class="card" style="margin-top:20px"><h3>${T_('nw.w_capture','Capture a lead')}</h3>
<div class="form-grid"><label>${T_('nw.w_name','Full name')}<input id="cap-name" value="${esc((draft&&draft.name)||'')}"/></label>
<label>${T_('nw.w_category','Category')}<input id="cap-cat"/></label></div>
<div class="form-grid"><label>${T_('rv.email','E-mail')}<input id="cap-email" value="${esc((draft&&draft.email)||'')}"/></label>
<label>${T_('nw.w_phone','Phone')}<input id="cap-phone" value="${esc((draft&&draft.phone)||'')}"/></label></div>
<div class="form-grid"><label>${T_('nw.w_site','Website')}<input id="cap-web" value="${esc((draft&&draft.website)||'')}"/></label>
<label>${T_('nw.w_city','City')}<input id="cap-city"/></label></div>
${quals?`<h4>${T_('nw.w_answers','Qualifier answers')}</h4>${quals}`:''}
${draft?`<p class="small muted">${T_('nw.w_ai_note','AI suggestion — verify.')}</p>`:''}
<button class="primary" onclick="nwCapture('${id}','${draft?draft.scan_id:''}')">${T_('nw.w_save_cap','Save capture')}</button></div>
<div class="card" style="margin-top:20px"><h3>${T_('nw.w_qual','Qualifying questions')}</h3>
<div id="nw-quals">${d.qualifiers.map(q=>`<div>• ${esc(q.question)} <small class="muted">(${q.kind})</small> <button class="danger-link" onclick="nwQualDel('${id}','${q.id}')">×</button></div>`).join('')||`<p class="small muted">${T_('nw.w_none','Nothing here yet.')}</p>`}</div>
<div class="form-grid" style="margin-top:12px"><label>${T_('nw.w_q_text','Question')}<input id="nq-q"/></label>
<label>${T_('nw.w_q_kind','Type')}<select id="nq-kind"><option value="text">${T_('nw.w_q_free','Free text')}</option><option value="choice">${T_('nw.w_q_choice','Multiple choice')}</option></select></label></div>
<label>${T_('nw.w_q_opts','Options')}<input id="nq-opts" placeholder="a, b, c"/></label>
<button class="secondary" onclick="nwQualAdd('${id}')">${T_('nw.w_q_add','Add question')}</button></div>
<div class="card" style="margin-top:20px"><h3>${T_('nw.w_leads','Captured leads')}</h3>
<label>${T_('nw.w_basis','Contact basis')}<input id="fu-basis" placeholder="Met at ${esc(e.name)}"/></label>
<div>${d.leads.map(l=>`<div style="padding:10px 0;border-bottom:1px solid #eef1e4"><b>${esc(l.name)}</b> <small class="muted">${esc(l.email||l.phone||'')}</small>
<span class="badge">${esc(l.stage)}</span> <button class="secondary" onclick="nwFollow('${l.id}')">${T_('nw.w_follow','Follow up')}</button></div>`).join('')||`<p class="small muted">${T_('nw.w_none','Nothing here yet.')}</p>`}</div></div>`);
nwStats(id)}
async function nwStats(id){try{const s=await api('/api/events/'+id+'/stats');const el=document.getElementById('nw-stats');if(!el)return;
el.innerHTML=`${T_('nw.w_stats','Results')}: ${Object.entries(s.stages).map(([k,v])=>esc(k)+' '+v).join(' · ')||'—'} · ${T_('nw.w_answered','answered')}: ${s.answered}`+
(s.revenue?`<br/>${T_('nw.w_rev','Revenue')}: contracts ${esc(JSON.stringify(s.revenue.contracts))} · paid ${esc(JSON.stringify(s.revenue.paid_invoices))}`:`<br/><a href="/pricing">${T_('nw.w_rev_req','Needs Pro.')}</a>`)}catch{}}
async function nwCapture(eid,scanId){const v=i=>document.getElementById(i).value.trim();
const answers={};document.querySelectorAll('[data-q]').forEach(el=>answers[el.dataset.q]=el.value);
const payload={name:v('cap-name'),category:v('cap-cat'),email:v('cap-email'),phone:v('cap-phone'),website:v('cap-web'),city:v('cap-city'),answers,scan_id:scanId||''};
if(!navigator.onLine){const q=nwQueue();q.push({eid,payload});nwQueueSave(q);toast(T_('nw.w_offline','Offline — saved on device.'));return}
try{await api('/api/events/'+eid+'/capture','POST',payload);toast(T_('nw.w_saved','Saved.'));nwEventDetail(eid)}catch(err){toast(err.message,true)}}
async function nwQualAdd(eid){const q=document.getElementById('nq-q').value.trim(),kind=document.getElementById('nq-kind').value;
const options=document.getElementById('nq-opts').value.split(',').map(s=>s.trim()).filter(Boolean);
try{await api('/api/events/'+eid+'/qualifiers','POST',{question:q,kind,options});nwEventDetail(eid)}catch(err){toast(err.message,true)}}
async function nwQualDel(eid,qid){try{await api('/api/events/'+eid+'/qualifiers/'+qid,'DELETE');nwEventDetail(eid)}catch(err){toast(err.message,true)}}
async function nwFollow(lid){const basis=(document.getElementById('fu-basis')||{}).value||'';
try{await api('/api/leads/'+lid+'/followup','POST',{approved:true,basis});
toast(T_('nw.w_fu_ok','Follow-up sent.'));nwEventDetail(nwEvent)}catch(err){toast(err.message,true)}}

/* ---- scan ---- */
async function nwScan(){const evs=await api('/api/events').catch(()=>({events:[]}));
nwBody(`<div class="card"><h3>${T_('nw.w_scan','Scan')}</h3>
<label>${T_('nw.w_up','Upload card photo')}<input type="file" id="scan-file" accept="image/jpeg,image/png,image/webp"/></label>
<label>${T_('nw.w_events','Events')}<select id="scan-ev">${evs.events.map(e=>`<option value="${e.id}">${esc(e.name)}</option>`).join('')}</select></label>
<div id="scan-out"></div></div>
<script>null<\/script>`);
document.getElementById('scan-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;
const form=new FormData();form.append('photo',f);
try{const r=await api('/api/scans','POST',form);
document.getElementById('scan-out').innerHTML=`<img src="/api/scans/${r.id}/photo" style="max-width:280px;border-radius:12px;margin:12px 0"/>
<br/><button class="secondary" onclick="nwExtract('${r.id}')">${T_('nw.w_extract','Read with AI')}</button> <span id="scan-sugg"></span>`}catch(err){toast(err.message,true)}}}
async function nwExtract(sid){try{const r=await api('/api/scans/'+sid+'/extract','POST',{});
if(!r.available){document.getElementById('scan-sugg').textContent=r.reason||T_('nw.w_noai','Unavailable.');return}
const s=r.suggestions;s.scan_id=sid;window._nwSugg=s;
document.getElementById('scan-sugg').innerHTML=`<p class="small muted">${T_('nw.w_ai_note','Verify.')} (${esc(r.model||'')}) <b>${esc(s.name||'')}</b> ${esc(s.email||'')}</p>
<button class="primary" onclick="nwScanUse()">${T_('nw.w_fill','Use these details')}</button>`}catch(err){toast(err.message,true)}}
function nwScanUse(){nwScanDraft=window._nwSugg||{};const eid=document.getElementById('scan-ev').value;
if(!eid){toast(T_('nw.w_empty_ev','No events yet.'),true);return}
nwCurrent='events';document.querySelectorAll('#nw-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.nwtab==='events'));
nwEventDetail(eid)}

/* ---- booking ---- */
const NW_DAYS=[0,1,2,3,4,5,6].map(i=>new Date(2026,0,4+i).toLocaleDateString(document.documentElement.lang,{weekday:'long'}));
async function nwBook(){const r=await api('/api/booking/availability');const bks=await api('/api/bookings');
const wins={};r.windows.forEach(w=>{(wins[w.weekday]=wins[w.weekday]||[]).push(w)});
nwBody(`<div class="card"><h3>${T_('nw.w_win','Weekly availability')}</h3>
${[1,2,3,4,5,6,0].map(d=>`<div class="form-grid" style="align-items:end"><label><input type="checkbox" data-win="${d}" ${wins[d]?'checked':''}/> ${NW_DAYS[d]}</label>
<label>Start<input type="time" data-s="${d}" value="${wins[d]?wins[d][0].start:'09:00'}"/></label>
<label>End<input type="time" data-e="${d}" value="${wins[d]?wins[d][0].end:'17:00'}"/></label></div>`).join('')}
<button class="primary" onclick="nwWinSave()">${T_('nw.w_win_save','Save windows')}</button>
<p style="margin-top:12px">${T_('nw.w_book_url','Your booking page')}: <a href="${r.book_url}" target="_blank" rel="noopener">${r.book_url}</a>
<button class="secondary" onclick="nwCopy(location.origin+'${r.book_url}')">${T_('nw.w_copy','Copy link')}</button></p></div>
<div class="card" style="margin-top:20px"><h3>${T_('nw.w_bookings','Bookings')}</h3>
${bks.bookings.map(b=>`<div style="padding:10px 0;border-bottom:1px solid #eef1e4"><b>${esc(b.slot_start.replace('T',' '))}</b> — ${esc(b.name)} (${esc(b.email)}) <span class="badge">${esc(b.status)}</span>
${b.status==='booked'?`<button class="secondary" onclick="nwBkStatus('${b.id}','confirmed')">${T_('nw.w_confirm','Confirm')}</button>`:''}
<button class="danger-link" onclick="nwBkStatus('${b.id}','cancelled')">${T_('nw.w_cancel','Cancel')}</button></div>`).join('')||`<p class="small muted">${T_('nw.w_empty_bk','No bookings yet.')}</p>`}</div>`)}
async function nwWinSave(){const windows=[];document.querySelectorAll('[data-win]').forEach(c=>{if(!c.checked)return;
const d=c.dataset.win;windows.push({weekday:+d,start:document.querySelector(`[data-s="${d}"]`).value,end:document.querySelector(`[data-e="${d}"]`).value})});
try{await api('/api/booking/availability','POST',{windows});toast(T_('nw.w_saved','Saved.'));loadNetwork()}catch(err){toast(err.message,true)}}
async function nwBkStatus(id,st){try{await api('/api/bookings/'+id+'/status','POST',{status:st});loadNetwork()}catch(err){toast(err.message,true)}}

/* ---- webhooks ---- */
async function nwHooks(){const r=await api('/api/webhooks');
nwBody(`<div class="card"><h3>${T_('nw.w_hooks','Webhooks')}</h3><p class="small muted">${T_('nw.w_hook_sig','Signed.')}<\/p>
${r.webhooks.map(h=>`<div style="padding:10px 0;border-bottom:1px solid #eef1e4"><b>${esc(h.url)}</b><br/><small class="muted">${esc(JSON.parse(h.events).join(', '))}</small>
<button class="danger-link" onclick="nwHookDel('${h.id}')">${T_('nw.w_del','Delete')}</button></div>`).join('')||`<p class="small muted">${T_('nw.w_empty_hooks','No webhooks yet.')}</p>`}
<label>${T_('nw.w_hook_url','Webhook URL')}<input id="hk-url" placeholder="https://…"/></label>
<div>${r.events.map(e=>`<label class="check" style="display:inline-flex;margin-right:12px"><input type="checkbox" data-he="${e}" checked/> ${esc(e)}</label>`).join('')}</div>
<button class="primary" style="margin-top:12px" onclick="nwHookAdd()">${T_('nw.w_add_hook','Add webhook')}</button></div>`)}
async function nwHookAdd(){const events=[...document.querySelectorAll('[data-he]:checked')].map(c=>c.dataset.he);
try{await api('/api/webhooks','POST',{url:document.getElementById('hk-url').value.trim(),events});loadNetwork()}catch(err){toast(err.message,true)}}
async function nwHookDel(id){try{await api('/api/webhooks/'+id,'DELETE');loadNetwork()}catch(err){toast(err.message,true)}}
