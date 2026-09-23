var T_=window.T||function(k,f){return f;};
let state={leads:[],activity:[],settings:{},suppressed:[],jobs:[]}, selected=null, toastTimer;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusLabel=s=>({NOT_LISTED:T_('wsj.ap_sl1','Website not listed'),SOCIAL_ONLY:T_('wsj.ap_sl2','Social only'),HAS_WEBSITE:T_('wsj.ap_sl3','Has website')}[s]||s);
const badge=s=>`<span class="badge ${s==='NOT_LISTED'?'amber':s==='HAS_WEBSITE'?'green':''}">${esc(statusLabel(s))}</span>`;
const empty=(title,desc,action='')=>`<div class="empty-state"><div class="empty-icon">⌁</div><strong>${title}</strong><p>${desc}</p>${action}</div>`;
function toast(msg,error=false){clearTimeout(toastTimer);const el=$('#toast');el.textContent=msg;el.className='show'+(error?' error':'');toastTimer=setTimeout(()=>el.className='',6500)}
function setC(id,v){if(window.setCount)window.setCount(id,v);else{const e=document.getElementById(id);if(e)e.textContent=v}}
async function api(path,method='GET',data){const opts={method,headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content||''}};if(data instanceof FormData)opts.body=data;else if(data!==undefined){opts.headers={...opts.headers,'Content-Type':'application/json'};opts.body=JSON.stringify(data)}const res=await fetch(path,opts);let result;try{result=await res.json()}catch{throw Error(T_('wsj.ap_err','The server could not complete the request. Please try again.'))}if(res.status===401){location.href=location.pathname.startsWith('/workspace')?'/login':'/signin';throw Error(T_('wsj.ap_signin','Please sign in again.'))}if(!res.ok)throw Error(result.error||T_('wsj.ap_fail','Request failed'));return result}
async function refresh(){state=await api('/api/state');render();}
function render(){
 $('#nav-count').textContent=state.leads.length;$('#enquiry-count').textContent=state.enquiry_count||0;setC('stat-total',state.leads.length);setC('stat-opportunity',state.leads.filter(l=>(l.status!=='HAS_WEBSITE'||['DNS_UNRESOLVED','HTTP_ERROR','PARKED_SUSPECTED','UNREACHABLE','SOCIAL_ONLY'].includes(l.audit_status))&&l.stage!=='Not a fit').length);setC('stat-sent',state.sent);setC('stat-replied',state.leads.filter(l=>['Replied','Won'].includes(l.stage)).length);
 const stages=['New','Drafted','Contacted','Replied'];$('#pipeline-bars').innerHTML=stages.map((s,i)=>{const n=state.leads.filter(l=>l.stage===s).length;return `<div class="pipeline-row"><div class="pipeline-label"><span>${[T_('wsj.ap_pl1','Discovered'),T_('wsj.ap_pl2','Draft ready'),T_('wsj.ap_pl3','Contacted'),T_('wsj.ap_pl4','Replied')][i]}</span><b>${n}</b></div><div class="bar-track"><div class="bar-fill" style="width:${state.leads.length?n/state.leads.length*100:0}%;background:${['#cbe36b','#9dad70','#586c45','#2b4230'][i]}"></div></div></div>`}).join('');
 $('#recent-leads').innerHTML=state.leads.length?state.leads.slice(0,4).map(l=>recentRow(l)).join(''):empty(T_('wsj.ap_next_t','Your next opportunity is out there.'),T_('wsj.ap_next_d','Discover local businesses or import your first lead list.'),'<button class="text-link" onclick="openDiscover()">'+T_('wsj.ap_find','Find businesses ↗')+'</button>');
 $('#activity').innerHTML=state.activity.length?state.activity.slice(0,5).map(a=>`<div class="activity-entry"><span class="activity-symbol">${{sent:'↗',draft:'✦',discovery:'◎',import:'＋',error:'!'}[a.kind]||'·'}</span><div><p>${esc(a.message)}</p><small>${esc(new Date(a.created).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}))}</small></div></div>`).join(''):empty(T_('wsj.ap_fresh_t','A fresh start.'),T_('wsj.ap_fresh_d','Your discoveries, drafts, and sent emails will appear here.'));
 $('#outreach-list').innerHTML=state.leads.filter(l=>l.body||l.stage==='Contacted').map(l=>recentRow(l,'compose')).join('')||empty(T_('wsj.ap_nodraft_t','No drafts yet.'),T_('wsj.ap_nodraft_d','Open a business from the lead directory to compose an introduction.'));
 const selectedCategory=$('#discover-category').value;$('#discover-category').innerHTML=state.categories.map(c=>`<option>${esc(c)}</option>`).join('');
 if(selectedCategory)$('#discover-category').value=selectedCategory;const gc=$('#global-category').value;$('#global-category').innerHTML=state.categories.map(c=>`<option>${esc(c)}</option>`).join('');if(gc)$('#global-category').value=gc;renderJobs();renderHealth();
 for(const [k,v] of Object.entries(state.settings)){const input=$(`#settings-form [name="${k}"]`);if(input&&document.activeElement!==input)input.value=v;}
 $('#profile-name').innerHTML=esc(state.settings.agency||T_('ws.pstudio','Your studio'))+'<small>'+T_('ws.powner','Workspace owner')+'</small>';
 $('#smtp-badge').textContent=state.smtp_ready?T_('wsj.ap_configured','Configured'):T_('ws.se_nc','Not connected');$('#smtp-badge').className='badge '+(state.smtp_ready?'green':'amber');renderLeads();
}
function recentRow(l,tab='details'){return `<div class="recent-row" role="button" tabindex="0" onclick="openLead('${l.id}','${tab}')" onkeydown="if(event.key==='Enter')openLead('${l.id}','${tab}')"><span class="business-icon">${esc(l.name.slice(0,1).toUpperCase())}</span><div><div class="business-name">${esc(l.name)}</div><div class="business-sub">${esc(l.category||T_('wsj.ap_local','Local business'))} · ${esc(l.city||T_('wsj.ap_noloc','Location not added'))}</div></div>${badge(l.status)}<span class="muted">↗</span></div>`}
function navigate(page){if(typeof inboxDirty==='function'&&inboxDirty()&&page!=='enquiries'&&!confirm(T_('wsj.ap_leave','Leave this page and discard unsaved enquiry changes?')))return;document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+page));document.querySelectorAll('.nav').forEach(p=>p.classList.toggle('active',p.dataset.page===page));$('#breadcrumb').textContent={overview:T_('ws.n_overview','Overview'),crew:T_('ws.n_crew','AI crew'),leads:T_('ws.n_leads','Lead directory'),outreach:T_('ws.n_outreach','Outreach studio'),settings:T_('ws.n_settings','Settings'),global:T_('wsj.t_t3','Global finder'),health:T_('ws.n_health','Website health'),portfolio:T_('ws.n_portfolio','Website samples'),enquiries:T_('ws.n_enquiries','Enquiry inbox'),contracts:T_('ws.n_contracts','Contracts'),projects:T_('ws.n_projects','Projects & follow-ups'),invoices:T_('ws.n_invoices','Invoices'),clients:T_('ws.n_clients','Clients & plans'),network:T_('ws.n_network','Network')}[page];window.scrollTo({top:0,behavior:'smooth'});history.replaceState(null,'','#'+page);if(page==='projects'&&typeof loadProjects==='function')loadProjects();if(page==='global'&&typeof openWorldMap==='function')openWorldMap();if(page==='enquiries'&&typeof loadEnquiries==='function')loadEnquiries();if(page==='contracts'&&typeof loadContracts==='function')loadContracts();if(page==='overview'&&typeof loadAnalytics==='function')loadAnalytics();if(page==='crew'&&typeof loadCrew==='function')loadCrew();if(page==='clients'&&typeof loadClients==='function')loadClients();if(page==='network'&&typeof loadNetwork==='function')loadNetwork()}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>navigate(b.dataset.page));
let leadSort={key:'',dir:1};function sortVal(l,k){return k==='contact'?(l.email||l.phone||''):String(l[k]||'').toLowerCase()}function sortLeads(k){if(leadSort.key===k)leadSort.dir*=-1;else leadSort={key:k,dir:1};renderLeads()}function renderLeads(){if(typeof syncQualityFilters==='function')syncQualityFilters();let q=$('#search').value.toLowerCase(),status=$('#filter-status').value,stage=$('#filter-stage').value;let leads=state.leads.filter(l=>(typeof qualityMatches!=='function'||qualityMatches(l))&&(!q||[l.name,l.city,l.category,l.email].join(' ').toLowerCase().includes(q))&&(!status||l.status===status)&&(!stage||l.stage===stage));if(leadSort.key)leads.sort((a,b)=>sortVal(a,leadSort.key)<sortVal(b,leadSort.key)?-leadSort.dir:sortVal(a,leadSort.key)>sortVal(b,leadSort.key)?leadSort.dir:0);$('#lead-table').innerHTML=leads.length?leads.map(l=>`<tr><td><div class="business-cell"><span class="business-icon">${esc(l.name[0])}</span><div><div class="business-name">${esc(l.name)}</div><div class="business-sub">${esc(l.category||T_('wsj.ap_local','Local business'))}</div></div></div></td><td>${esc(l.city||'—')}</td><td>${badge(l.status)}</td><td><span class="badge ${['Replied','Won'].includes(l.stage)?'green':''}">${esc(l.stage)}</span></td><td>${l.email?'<span style="color:#718d81">'+T_('wsj.ap_email_av','Email available')+'</span>':l.phone?T_('wsj.ap_phone_av','Phone available'):T_('wsj.ap_needs','Needs research')}</td><td><button class="text-link" onclick="openLead('${l.id}')">${T_('wsj.ap_open','Open ↗')}</button></td></tr>`).join(''):`<tr><td colspan="6">${empty(state.leads.length?T_('wsj.ap_nomatch_t','No matching businesses.'):T_('wsj.ap_clean_t','A clean slate. A lot of potential.'),state.leads.length?T_('wsj.ap_nomatch_d','Try a different search or filter.'):T_('wsj.ap_clean_d','Discover businesses, add one manually, or import a CSV.'))}</td></tr>`;$('#table-count').textContent=T_('wsj.ap_count','{n} of {m} businesses · Saved to your workspace').replace('{n}',leads.length).replace('{m}',state.leads.length);document.querySelectorAll('.sort-arrow').forEach(s=>s.textContent='');if(leadSort.key){const a=document.getElementById('sort-'+leadSort.key);if(a)a.textContent=leadSort.dir>0?'▲':'▼'}}
let previousFocus=null;
function openModal(id){previousFocus=document.activeElement;$('#'+id).classList.add('open');document.body.classList.add('locked');setTimeout(()=>$('#'+id+' input')?.focus(),100)}
function closeModal(id){$('#'+id).classList.remove('open');document.body.classList.remove('locked');previousFocus?.focus()}
function openDiscover(){openModal('discover-modal')}
function openManual(){openModal('manual-modal')}
document.querySelectorAll('.modal-backdrop').forEach(el=>el.addEventListener('click',e=>{if(e.target===el)closeModal(el.id)}));
document.addEventListener('keydown',e=>{if(e.key==='Escape'){document.querySelectorAll('.modal-backdrop.open').forEach(el=>closeModal(el.id));if($('#lead-drawer').classList.contains('open'))closeDrawer()}if(e.key==='Tab'){const active=document.querySelector('.modal-backdrop.open .modal,.drawer-backdrop.open .drawer');if(!active)return;const focusable=[...active.querySelectorAll('a[href],button,input,select,textarea,iframe')].filter(x=>x.offsetParent!==null&&!x.disabled);const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}});
$('#discover-form').onsubmit=async e=>{e.preventDefault();const b=$('#discover-submit');b.disabled=true;b.textContent=T_('wsj.ap_searching','Searching public map data…');$('#discovery-result').textContent=T_('wsj.ap_search_d','This may take up to a minute. Looking for real businesses, not sample leads.');try{const r=await api('/api/discover','POST',{city:$('#discover-city').value,category:$('#discover-category').value});$('#discovery-result').textContent=T_('wsj.ap_result','Checked {s} listings. Found {c} candidates; {a} newly added. Existing leads are deduplicated. {lim}').replace('{s}',r.scanned).replace('{c}',r.candidates).replace('{a}',r.added).replace('{lim}',r.scanned===80?T_('wsj.ap_lim','The 80-listing search limit was reached.'):'');await refresh();toast(T_('wsj.ap_added','{n} new businesses saved.').replace('{n}',r.added))}catch(err){$('#discovery-result').textContent=err.message;toast(err.message,true)}finally{b.disabled=false;b.textContent=T_('ws.le_disc','Discover businesses ↗')}};
$('#manual-form').onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/leads','POST',Object.fromEntries(new FormData(e.target)));await refresh();closeModal('manual-modal');e.target.reset();navigate('leads');toast(r.added?T_('wsj.ap_biz_added','Business added.'):T_('wsj.ap_biz_dup','This business is already saved.'))}catch(err){toast(err.message,true)}};
async function importCSV(input){const f=input.files[0];if(!f)return;const form=new FormData();form.append('file',f);toast(T_('wsj.ap_importing','Importing your business list…'));try{const r=await api('/api/import','POST',form);await refresh();toast(T_('wsj.ap_imported','Imported {a} businesses. {s} duplicate or empty rows skipped.').replace('{a}',r.added).replace('{s}',r.skipped))}catch(err){toast(err.message,true)}finally{input.value=''}}
$('#settings-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings','POST',Object.fromEntries(new FormData(e.target)));await refresh();toast(T_('wsj.ap_sender','Sender profile saved.'))}catch(err){toast(err.message,true)}};
function openLead(id,tab='details'){selected=state.leads.find(l=>l.id===id);if(!selected)return;previousFocus=document.activeElement;$('#detail-title').textContent=selected.name;if(typeof renderLeadWork==='function')renderLeadWork();$('#detail-meta').innerHTML=`<div class="detail-chips">${badge(selected.status)}<span class="badge">${esc(selected.source)}</span>${state.suppressed.includes(selected.email.toLowerCase())?'<span class="badge amber">'+T_('wsj.ap_blocked','Outreach blocked')+'</span>':''}</div><p class="detail-address">${esc(selected.category||T_('wsj.ap_local','Local business'))} · ${esc(selected.city)}<br>${esc(selected.address||T_('wsj.ap_noaddr','Address not listed'))}</p>${/^https:\/\/www\.openstreetmap\.org\//.test(selected.source_url)?`<a class="text-link" href="${esc(selected.source_url)}" target="_blank" rel="noopener">${T_('wsj.ap_verify','Verify original map listing ↗')}</a>`:''}`;
 renderAuditDetail();
 for(const k of ['name','email','phone','website','stage','note'])$(`#detail-form [name="${k}"]`).value=selected[k]||'';
 $('#compose-recipient').textContent=selected.email||T_('wsj.ap_noemail','No email yet — add a verified address in Business details');$('#email-subject').value=selected.subject||'';$('#email-body').value=selected.body||'';$('#send-approved').checked=false;$('#send-basis').checked=false;
 $('#preview-warning').textContent=state.settings.public_base_url?T_('wsj.ap_prev_ok','Preview links use your configured public URL. Open the link and verify it works before sending.'):T_('wsj.ap_prev_no','No public URL configured. The draft can offer a preview, but won’t include a non-shareable local link. Set a public deployment URL in Settings to include a live concept.');
 const url='/preview/'+selected.token;$('#preview-open').href=url;$('#preview-frame').src=url;updateCount();drawerTab(tab);$('#lead-drawer').classList.add('open');document.body.classList.add('locked');$('.close-inline').focus();}
function closeDrawer(){if(selected&&($('#email-subject').value!==(selected.subject||'')||$('#email-body').value!==(selected.body||''))&&!confirm(T_('wsj.ap_discard','Discard unsaved email edits?')))return;$('#lead-drawer').classList.remove('open');document.body.classList.remove('locked');selected=null;previousFocus?.focus()}
function drawerTab(tab){document.querySelectorAll('.drawer-tab').forEach(el=>el.classList.toggle('active',el.id==='tab-'+tab));document.querySelectorAll('.drawer-tabs button').forEach(el=>(el.classList.toggle('active',el.dataset.tab===tab),el.setAttribute('role','tab'),el.setAttribute('aria-selected',String(el.dataset.tab===tab))))}
$('#detail-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/leads/'+selected.id,'PATCH',Object.fromEntries(new FormData(e.target)));const id=selected.id;await refresh();openLead(id);toast(T_('wsj.ap_detsaved','Business details saved.'))}catch(err){toast(err.message,true)}};
async function generateDraft(){if(!selected)return;if($('#email-body').value&&!confirm(T_('wsj.ap_replace','Replace the current message with a new draft?')))return;const b=$('#generate-btn');b.disabled=true;try{const r=await api('/api/leads/'+selected.id+'/compose','POST',{tone:$('#tone').value,preview:$('#include-preview').checked});$('#email-subject').value=r.subject;$('#email-body').value=r.body;await refresh();selected=state.leads.find(l=>l.id===selected.id);updateCount();toast(T_('wsj.ap_draftgen','Draft generated and saved. Review it before sending.'))}catch(err){toast(err.message,true)}finally{b.disabled=false}}
function updateCount(){$('#word-count').textContent=T_('wsj.ap_words','{n} words').replace('{n}',($('#email-body').value.trim().match(/\S+/g)||[]).length)}
$('#email-body').addEventListener('input',()=>{updateCount();$('#send-approved').checked=false});$('#email-subject').addEventListener('input',()=>$('#send-approved').checked=false);
async function saveDraft(silent=false){try{await api('/api/leads/'+selected.id,'PATCH',{subject:$('#email-subject').value,body:$('#email-body').value,...(selected.stage==='New'?{stage:'Drafted'}:{})});await refresh();selected=state.leads.find(l=>l.id===selected.id);if(!silent)toast(T_('wsj.ap_draftsaved','Draft saved.'));return true}catch(err){toast(err.message,true);return false}}
async function sendEmail(){if(!$('#send-basis').checked||!$('#send-approved').checked)return toast(T_('wsj.ap_confirm','Please confirm the contact basis and review the message before sending.'),true);if(!state.smtp_ready)return toast(T_('wsj.ap_smtp','Configure your SMTP connection first. See Settings.'),true);if(!confirm(T_('wsj.ap_sendq','Send this email to {e}? This action cannot be undone.').replace('{e}',selected.email||T_('wsj.ap_missing','(missing address)'))))return;const b=$('#send-btn');b.disabled=true;b.textContent=T_('show.js_sending','Sending…');try{if(!await saveDraft(true))return;await api('/api/leads/'+selected.id+'/send','POST',{approved:true,basis:true});await refresh();selected=state.leads.find(l=>l.id===selected.id);toast(T_('wsj.ap_accepted','Your mail server accepted the email. Delivery and replies are not tracked.'))}catch(err){toast(err.message,true)}finally{b.disabled=false;b.textContent=T_('ws.cp_send','Send email ↗')}}
async function blockLead(){if(!confirm(T_('wsj.ap_blockq','Block all future outreach to this email address?')))return;try{await api('/api/leads/'+selected.id+'/suppress','POST',{});let id=selected.id;await refresh();openLead(id);toast(T_('wsj.ap_optout','Recipient added to the opt-out list.'))}catch(err){toast(err.message,true)}}
async function deleteLead(){if(!confirm(T_('wsj.ap_delq','Delete this lead and its draft? Email history and opt-out records will be retained.')))return;try{await api('/api/leads/'+selected.id,'DELETE');$('#lead-drawer').classList.remove('open');document.body.classList.remove('locked');selected=null;await refresh();toast(T_('wsj.ap_delsaved','Lead deleted.'))}catch(err){toast(err.message,true)}}
async function copyPreview(){const base=state.settings.public_base_url||location.origin;const url=base.replace(/\/$/,'')+'/preview/'+selected.token;try{await navigator.clipboard.writeText(url);toast(state.settings.public_base_url?T_('wsj.ap_copied','Preview link copied.'):T_('wsj.ap_copied_ws','Workspace preview link copied. Public deployment is needed for reliable external sharing.'))}catch{prompt(T_('wsj.ap_copyq','Copy this preview link:'),url)}}
$('#today').textContent=new Date().toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
refresh().then(()=>{const page=location.hash.slice(1);if(['overview','crew','leads','outreach','settings','global','health','portfolio','enquiries','contracts','projects','invoices','clients','network'].includes(page))navigate(page)}).catch(e=>toast(e.message,true));
// Refresh real workspace metrics while idle without overwriting an open editor.
setInterval(()=>{if(!document.hidden&&!$('.drawer-backdrop.open')&&!$('.modal-backdrop.open')&&!$('#page-settings').classList.contains('active'))refresh().catch(()=>{})},30000);

const auditLabel=s=>({LIVE:T_('wsj.ap_a1','Responding'),DNS_UNRESOLVED:T_('wsj.ap_a2','DNS unresolved'),HTTP_ERROR:T_('wsj.ap_a3','HTTP error'),UNREACHABLE:T_('wsj.ap_a4','Connection failed'),BLOCKED:T_('wsj.ap_a5','Access restricted'),PARKED_SUSPECTED:T_('wsj.ap_a6','Possible parked domain'),CHECK_FAILED:T_('wsj.ap_a7','Check inconclusive'),NOT_LISTED:T_('wsj.ap_a8','No URL listed'),SOCIAL_ONLY:T_('wsj.ap_a9','Social only')}[s]||T_('wsj.ap_a0','Not checked'));
function renderAuditDetail(){if(!selected)return;let tags={};try{tags=JSON.parse(selected.source_tags||'{}')}catch{}$('#detail-audit').innerHTML=`<div class="audit-panel"><div class="section-top"><h3>${esc(auditLabel(selected.audit_status))}</h3><span class="badge ${selected.audit_status==='LIVE'?'green':'amber'}">${selected.http_code?'HTTP '+esc(selected.http_code):T_('wsj.ap_srcev','Source evidence')}</span></div><p class="small muted">${esc(selected.audit_reason||T_('wsj.ap_nocheck','No live URL check has been performed for this business.'))}</p><small>${selected.checked_at?T_('wsj.ap_checked','Checked {d}').replace('{d}',esc(new Date(selected.checked_at).toLocaleString())):T_('wsj.ap_notyet','Not yet checked')}</small>${selected.opening_hours?'<p class="small">'+T_('wsj.ap_hours','Listed hours: {h}').replace('{h}',esc(selected.opening_hours))+'</p>':''}${selected.latitude!=null?'<p class="small muted">'+T_('wsj.ap_coords','Map coordinates: {c}').replace('{c}',esc(selected.latitude)+', '+esc(selected.longitude))+'</p>':''}${Object.keys(tags).length?'<details><summary>'+T_('wsj.ap_srcdet','All available source details')+'</summary><dl>'+Object.entries(tags).map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join('')+'</dl></details>':''}</div>`}
async function auditSelected(){const b=$('#audit-btn');b.disabled=true;b.textContent=T_('wsj.ap_checking','Checking live URL…');try{const r=await api('/api/leads/'+selected.id+'/audit','POST',{});await refresh();selected=state.leads.find(l=>l.id===selected.id);renderAuditDetail();toast(auditLabel(r.status)+': '+r.reason)}catch(e){toast(e.message,true)}finally{b.disabled=false;b.textContent=T_('ws.dr_audit','⌁ Check website live')}}
function renderJobs(){$('#global-jobs').innerHTML=(state.jobs||[]).length?state.jobs.map(j=>`<article class="job-card"><div class="section-top"><strong>${esc(j.category)}</strong><span class="badge ${j.state==='completed'?'green':''}">${esc(j.state)}</span></div><p class="small muted">${esc(JSON.parse(j.locations).join(' · '))}</p><div class="bar-track"><div class="bar-fill" style="width:${j.progress/j.total*100}%"></div></div><p class="small">${T_('wsj.ap_jobprog','{p}/{t} locations · {a} saved · {c} URL checks').replace('{p}',j.progress).replace('{t}',j.total).replace('{a}',j.added).replace('{c}',j.checked)}</p><p class="small muted">${esc(j.message)}</p>${['queued','running'].includes(j.state)?`<button class="text-link" onclick="cancelJob('${j.id}')">${T_('wsj.ap_canceljob','Cancel job')}</button>`:''}</article>`).join(''):empty(T_('wsj.ap_nojobs_t','No search jobs yet.'),T_('wsj.ap_nojobs_d','Enter your own cities to start discovering real businesses across countries.'));}
$('#global-form').onsubmit=async e=>{e.preventDefault();const b=$('#global-submit');b.disabled=true;try{const locations=$('#global-locations').value.split('\n').map(x=>x.trim()).filter(Boolean);await api('/api/jobs','POST',{locations,category:$('#global-category').value,check_websites:$('#global-audit').checked});await refresh();toast(T_('wsj.ap_global','Global discovery started. Progress is saved live.'))}catch(err){toast(err.message,true)}finally{b.disabled=false}};
async function cancelJob(id){try{await api('/api/jobs/'+id+'/cancel','POST',{});await refresh();toast(T_('wsj.ap_cancelled','Cancellation requested; an in-flight request may still finish.'))}catch(e){toast(e.message,true)}}
function renderHealth(){const filter=$('#health-filter').value;const rows=state.leads.filter(l=>!filter||(filter==='unchecked'&&!l.audit_status)||(filter==='LIVE'&&l.audit_status==='LIVE')||(filter==='needs'&&['DNS_UNRESOLVED','HTTP_ERROR','UNREACHABLE','PARKED_SUSPECTED'].includes(l.audit_status)));$('#health-list').innerHTML=rows.length?rows.map(l=>`<div class="health-row"><div><strong>${esc(l.name)}</strong><p class="small muted">${esc(l.city)} · ${esc(l.website||T_('wsj.ap_a8','No URL listed'))}</p><small>${esc(l.audit_reason||T_('wsj.ap_health_d','Open this business to check its URL or verify its website manually.'))}</small></div><span class="badge ${l.audit_status==='LIVE'?'green':'amber'}">${esc(auditLabel(l.audit_status))}</span><button class="text-link" onclick="openLead('${l.id}')">${T_('wsj.ap_review','Review ↗')}</button></div>`).join(''):empty(T_('wsj.ap_nochecks_t','No matching website checks.'),T_('wsj.ap_nochecks_d','Run a global search or open a saved lead to check its website.'));}
setInterval(async()=>{if(!document.hidden&&(state.jobs||[]).some(j=>['running','queued'].includes(j.state))){try{const fresh=await api('/api/state');state.jobs=fresh.jobs;if(!$('.drawer-backdrop.open')&&!$('#page-settings').classList.contains('active')){state=fresh;render()}else renderJobs()}catch{}}},4000);
window.addEventListener('beforeunload',e=>{if(selected&&($('#email-subject').value!==(selected.subject||'')||$('#email-body').value!==(selected.body||''))){e.preventDefault();e.returnValue=''}});


// --- Client vs Owner view: hide owner-only nav for clients, show dashboard ---
async function applyRoleView(){
  try{
    const me = await fetch('/api/auth/me').then(r=>r.json().catch(()=>({})));
    const role = me.role || 'none';
    const isClient = role==='client';
    const ownerOnly = ['global','leads','health','contracts','crew','clients','network'];
    document.querySelectorAll('.nav').forEach(btn=>{
      const page = btn.dataset.page;
      if(isClient && ownerOnly.includes(page)){
        btn.style.display='none';
      } else {
        btn.style.display='';
      }
    });
    // Client sees their own identity, not the owner's studio label
    if(isClient){
      const pn=document.getElementById('profile-name');
      if(pn) pn.innerHTML=esc(me.name||T_('wsj.ap_client','Client'))+'<small>'+(me.email||T_('wsj.ap_client_acct','Client account'))+'</small>';
    }
    // If client lands on owner-only page, redirect to dashboard view
    const hash = location.hash.slice(1);
    if(isClient && ownerOnly.includes(hash)){
      navigate('invoices');
      history.replaceState(null,'','#invoices');
    }
    // If client, ensure breadcrumb shows Dashboard
    if(isClient){
      const bc=document.getElementById('breadcrumb');
      if(bc && !bc.textContent.includes('Dashboard')) {
        // keep Overview as Dashboard for clients
      }
    }
  }catch{}
}
originalRefresh = refresh;
refresh = async function(){
  const res = await originalRefresh();
  applyRoleView();
  return res;
};

function chooseWorldMix(){const regions=[['Cairo, Egypt','Accra, Ghana','Nairobi, Kenya'],['London, United Kingdom','Lisbon, Portugal','Berlin, Germany'],['Toronto, Canada','Austin, United States','Vancouver, Canada'],['São Paulo, Brazil','Bogotá, Colombia','Lima, Peru'],['Tokyo, Japan','Mumbai, India','Singapore'],['Sydney, Australia','Auckland, New Zealand','Perth, Australia']];$('#global-locations').value=regions.map(r=>r[Math.floor(Math.random()*r.length)]).join('\n');toast(T_('wsj.ap_mix','Six search locations selected across regions. These are search seeds, not business results.'));}

// --- Theme + Sidebar fixes (simplify + expand) ---
(function(){
  const root = document.documentElement;
  const sidebar = document.getElementById('sidebar');
  const tbtn = document.getElementById('theme-toggle');
  const sbtn = document.getElementById('sidebar-toggle');
  // theme
  try{
    const saved = localStorage.getItem('reachmark-theme');
    if(saved) root.setAttribute('data-theme', saved);
    else if(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) root.setAttribute('data-theme','dark');
  }catch{}
  function updateThemeIcon(){
    if(!tbtn) return;
    const isDark = root.getAttribute('data-theme')==='dark';
    tbtn.textContent = isDark ? '☾' : '◐';
    tbtn.title = isDark ? T_('wsj.ap_light','Switch to light') : T_('wsj.ap_dark','Switch to dark');
  }
  updateThemeIcon();
  if(tbtn){
    tbtn.addEventListener('click', ()=>{
      const isDark = root.getAttribute('data-theme')==='dark';
      const next = isDark ? 'light' : 'dark';
      if(next==='light') root.removeAttribute('data-theme');
      else root.setAttribute('data-theme','dark');
      try{ localStorage.setItem('reachmark-theme', next==='light'?'light':'dark'); }catch{}
      updateThemeIcon();
    });
  }
  // sidebar collapsed
  try{
    const sc = localStorage.getItem('reachmark-sidebar-collapsed');
    if(sc==='1' && sidebar) sidebar.classList.add('collapsed');
  }catch{}
  function syncSidebarBtn(){
    if(!sbtn || !sidebar) return;
    const collapsed = sidebar.classList.contains('collapsed');
    sbtn.setAttribute('aria-expanded', String(!collapsed));
    sbtn.textContent = collapsed ? '›' : '‹';
  }
  syncSidebarBtn();
  if(sbtn && sidebar){
    sbtn.addEventListener('click', ()=>{
      sidebar.classList.toggle('collapsed');
      try{ localStorage.setItem('reachmark-sidebar-collapsed', sidebar.classList.contains('collapsed')?'1':'0'); }catch{}
      syncSidebarBtn();
    });
  }
  // ensure nav tooltips have data-page already set in HTML, but also ensure title
  document.querySelectorAll('.nav').forEach(b=>{
    if(!b.getAttribute('title')) b.setAttribute('title', (b.textContent||b.dataset.page||'').trim());
  });
})();
