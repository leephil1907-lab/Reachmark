(function(){
  const root=document.getElementById('page-outreach');
  if(!root)return;
  const csrf=()=>document.querySelector('meta[name="csrf-token"]')?.content||'';
  async function api(url,options){
    const opts=options||{};
    opts.credentials='same-origin';
    opts.headers=Object.assign({'Content-Type':'application/json','X-CSRF-Token':csrf()},opts.headers||{});
    const r=await fetch(url,opts), data=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(data.error||('Request failed: '+r.status));
    return data;
  }
  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function shell(){
    root.innerHTML='<div class="page-heading"><div class="eyebrow">REACHMARK DIGITAL</div><h1>Outreach, orchestrated from one workspace.</h1><p>Create the campaign in Reachmark, choose the email execution engine, and keep leads, replies and suppression state in the Reachmark CRM.</p></div>'+
      '<div class="outreach-grid">'+
      '<section class="card outreach-create"><div class="section-top"><div><h3>Create campaign</h3><p class="small muted">One Reachmark campaign. Instantly or Smartlead underneath.</p></div><span class="badge" id="provider-state">Checking providers…</span></div>'+
      '<label>Campaign name<input id="rm-campaign-name" maxlength="160" placeholder="e.g. Lagos hospitality — website opportunity"/></label>'+
      '<label>Email provider<select id="rm-provider"><option value="instantly">Instantly</option><option value="smartlead">Smartlead</option></select></label>'+
      '<button class="primary" id="rm-create-campaign">Create campaign</button><p class="small muted" id="rm-create-note">No provider credentials are exposed to the browser.</p></section>'+
      '<section class="card"><div class="section-top"><div><h3>Your campaigns</h3><p class="small muted">Provider state is reflected only after the provider accepts the action.</p></div><button class="secondary" id="rm-refresh">Refresh</button></div><div id="rm-campaign-list"><div class="sk"><i></i><i></i><i></i></div></div></section></div>';
  }
  async function loadProviders(){
    const d=await api('/api/outreach/providers',{headers:{'Content-Type':'application/json'}});
    const map=Object.fromEntries(d.providers.map(x=>[x.id,x]));
    document.getElementById('provider-state').textContent=Object.values(map).some(x=>x.configured)?'Provider ready':'Connect a provider';
    for(const option of document.querySelectorAll('#rm-provider option')) option.disabled=!map[option.value]?.configured;
    const first=Object.values(map).find(x=>x.configured); if(first)document.getElementById('rm-provider').value=first.id;
  }
  async function loadCampaigns(){
    const d=await api('/api/outreach/campaigns',{headers:{'Content-Type':'application/json'}});
    const el=document.getElementById('rm-campaign-list');
    if(!d.campaigns.length){el.innerHTML='<div class="empty-state"><strong>No Reachmark campaigns yet.</strong><p>Create one above and select the email execution provider.</p></div>';return;}
    el.innerHTML=d.campaigns.map(c=>'<article class="rm-campaign-row"><div><strong>'+esc(c.name)+'</strong><div class="small muted">'+esc(c.provider)+' · '+esc(c.status)+' · '+esc(c.provider_campaign_id)+'</div></div><div class="button-group"><button class="secondary" data-action="start" data-id="'+esc(c.id)+'">Start</button><button class="secondary" data-action="pause" data-id="'+esc(c.id)+'">Pause</button></div></article>').join('');
    el.querySelectorAll('button').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/outreach/campaigns/'+encodeURIComponent(b.dataset.id)+'/'+b.dataset.action,{method:'POST',body:'{}'});await loadCampaigns();}catch(e){alert(e.message)}finally{b.disabled=false;}});
  }
  shell();
  document.getElementById('rm-create-campaign').onclick=async function(){
    const name=document.getElementById('rm-campaign-name').value.trim(),provider=document.getElementById('rm-provider').value;
    if(!name){alert('Give the campaign a name first.');return;}
    this.disabled=true;
    try{await api('/api/outreach/campaigns',{method:'POST',body:JSON.stringify({name,provider})});document.getElementById('rm-campaign-name').value='';await loadCampaigns();}catch(e){alert(e.message)}finally{this.disabled=false;}
  };
  document.getElementById('rm-refresh').onclick=loadCampaigns;
  loadProviders().catch(e=>{document.getElementById('provider-state').textContent='Provider check failed';});
  loadCampaigns().catch(()=>{document.getElementById('rm-campaign-list').innerHTML='<p class="muted">Sign in as a Reachmark workspace owner to use Outreach.</p>';});
})();