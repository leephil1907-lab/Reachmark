(function(){
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const count = value => Number(value || 0).toLocaleString();
  const date = value => { if(!value) return 'Time not recorded'; const d=new Date(value); return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString(); };
  let busy = false;
  async function api(path, options){
    const headers = Object.assign({'Accept':'application/json'}, options && options.headers || {});
    if(options && options.method && options.method !== 'GET'){
      headers['Content-Type'] = 'application/json';
      headers['X-CSRFToken'] = document.querySelector('meta[name="csrf-token"]')?.content || '';
    }
    const response = await fetch(path, Object.assign({credentials:'same-origin'}, options || {}, {headers}));
    let body = {};
    try { body = await response.json(); } catch (_) {}
    if(!response.ok) throw new Error(body.error || ('Request failed ('+response.status+')'));
    return body;
  }
  function status(message, kind){
    const node=$('ros-status'); if(!node)return;
    node.textContent=message; node.dataset.kind=kind||'';
  }
  function renderKpis(command, metrics){
    const p=command.pipeline||metrics.pipeline||{};
    const funnel=command.funnel?.counts||{};
    const items=[
      ['Saved leads',funnel.lead ?? metrics.leads,'Real workspace records'],
      ['Verified opportunities',p.verified_problems,'Reports with recorded evidence'],
      ['Proposals',funnel.proposal ?? p.proposals,'Generated proposal records'],
      ['Paid clients',command.money?.paid_clients ?? p.paid_clients,'Based on invoices marked Paid'],
      ['Unpaid invoices',command.money?.unpaid_invoices,'Draft, sent, or overdue']
    ];
    $('ros-kpis').innerHTML=items.map(x=>'<article class="card rm-ros-kpi"><span>'+esc(x[0])+'</span><strong>'+count(x[1])+'</strong><small>'+esc(x[2])+'</small></article>').join('');
  }
  function renderNext(next){
    const body=$('ros-next-body'), actions=$('ros-next-actions'), score=$('ros-next-score');
    actions.innerHTML='';
    if(!next){
      score.textContent='No lead yet';
      body.innerHTML='<div class="rm-ros-empty">No unpaid lead is ready for a next action. Save a real prospect and run an evidence-backed report to begin.</div>';
      return;
    }
    score.textContent=next.index_score == null ? 'Unscored' : 'Fit index '+next.index_score;
    const step=next.next||{};
    const blockers=Array.isArray(next.blockers)?next.blockers:[];
    body.innerHTML='<div class="rm-ros-next-lead"><h3>'+esc(next.lead_name||'Unnamed business')+'</h3><p>'+esc(next.wedge||'Unclassified segment')+' · '+esc(next.city||'Location not recorded')+'</p><p>Next missing step: <strong>'+esc(step.label||step.id||'Review record')+'</strong></p></div>'+
      (next.why?'<div class="rm-ros-next-reason">'+esc(next.why)+'</div>':'')+
      (blockers.length?'<strong class="small">What may be blocking progress</strong><ul class="rm-ros-blockers">'+blockers.map(b=>'<li>'+esc(typeof b==='string'?b:(b.label||b.reason||b.message||JSON.stringify(b)))+'</li>').join('')+'</ul>':'<p class="small muted">No recorded blockers were returned.</p>');
    const leadBtn=document.createElement('button');leadBtn.type='button';leadBtn.className='secondary';leadBtn.textContent='Open lead directory';leadBtn.addEventListener('click',()=>{if(window.navigate)window.navigate('leads');});
    actions.appendChild(leadBtn);
    const prepare=document.createElement('button');prepare.type='button';prepare.textContent='Prepare report + proposal';prepare.addEventListener('click',()=>prepareLead(next.lead_id,prepare));
    actions.appendChild(prepare);
  }
  async function prepareLead(id, button){
    if(!id||busy)return;
    if(!window.confirm('Prepare or reuse an evidence-backed report, concept, and draft proposal? Nothing will be sent.'))return;
    busy=true;button.disabled=true;button.textContent='Preparing…';status('Preparing artifacts from saved evidence. No message will be sent.');
    try{
      const result=await api('/api/os/lead/'+encodeURIComponent(id)+'/advance',{method:'POST',body:'{}'});
      const links=[];
      if(result.prototype_url)links.push('<a class="secondary" href="'+esc(result.prototype_url)+'" target="_blank" rel="noopener">Open concept</a>');
      if(result.proposal_url)links.push('<a href="'+esc(result.proposal_url)+'" target="_blank" rel="noopener">Review draft proposal</a>');
      const actions=$('ros-next-actions');
      actions.innerHTML=links.join('');
      status('Prepared/reused: '+(result.steps||[]).join(', ')+'. Outbound messages: not sent. Review the proposal and set real prices before sharing.','success');
      await load();
    }catch(error){status(error.message,'error');}
    finally{busy=false;button.disabled=false;button.textContent='Prepare report + proposal';}
  }
  function renderFunnel(funnel){
    const steps=funnel.steps||[], max=Math.max(1,...steps.map(x=>Number(x.count||0)));
    $('ros-funnel').innerHTML=steps.map(x=>'<li><div class="rm-ros-funnel-name"><span>'+esc(x.label)+'</span><div class="rm-ros-track" aria-hidden="true"><i style="width:'+Math.min(100,Math.round((Number(x.count||0)/max)*100))+'%"></i></div><small>'+esc(x.basis||'Saved records')+'</small></div><strong class="rm-ros-count">'+count(x.count)+'</strong></li>').join('');
    $('ros-funnel-note').textContent=funnel.disclaimer||'Counts are read from stored records.';
  }
  function renderSegments(metrics){
    const rows=metrics.by_wedge||[];
    if(!rows.length){$('ros-wedges').innerHTML='<div class="rm-ros-empty">No segment observations are available yet.</div>';return;}
    $('ros-wedges').innerHTML='<div class="rm-ros-segments">'+rows.slice(0,8).map(x=>'<div class="rm-ros-segment"><div><strong>'+esc(x.label||x.k||'Unclassified')+'</strong><small>'+count(x.n)+' saved · '+count(x.won)+' won</small></div><span class="rm-ros-count">'+(x.n?Math.round((Number(x.won||0)/Number(x.n))*100)+'%':'—')+'</span></div>').join('')+'</div>';
  }
  function renderEvents(events){
    if(!events.length){$('ros-events').innerHTML='<li class="rm-ros-empty">No commercial events recorded yet. Activity will appear here as real work moves through the pipeline.</li>';return;}
    $('ros-events').innerHTML=events.slice(0,10).map(e=>'<li><div><strong>'+esc(e.lead_name||e.object_type||'Workspace event')+' · '+esc(e.stage||'Activity')+'</strong>'+esc(e.detail||'Record updated')+'<small>'+esc(date(e.created))+'</small></div></li>').join('');
  }
  async function load(){
    if(busy)return;
    status('Refreshing from saved workspace records…');
    try{
      const [command,metrics]=await Promise.all([api('/api/os/command'),api('/api/os/metrics')]);
      renderKpis(command,metrics);
      renderNext(command.next_to_win);
      renderFunnel(command.funnel||{steps:[],counts:{}});
      renderSegments(metrics);
      renderEvents(command.happened||[]);
      status('Updated from live database records · '+new Date().toLocaleTimeString(),'success');
    }catch(error){
      status(error.message+' If you are not signed in, sign in with the account that owns this workspace.','error');
      $('ros-next-body').innerHTML='<div class="rm-ros-empty">Revenue OS could not read the workspace records. Check your session and refresh.</div>';
    }
  }
  async function reconcile(){
    if(busy)return;
    if(!window.confirm('Reconcile existing saved records into Revenue OS? This updates derived bookkeeping only; it does not send messages.'))return;
    busy=true;const btn=$('ros-backfill');btn.disabled=true;btn.textContent='Reconciling…';
    try{const result=await api('/api/os/backfill',{method:'POST',body:'{}'});status('Reconciliation complete. '+JSON.stringify(result),'success');}
    catch(error){status(error.message,'error');}
    finally{busy=false;btn.disabled=false;btn.textContent='Reconcile saved records';await load();}
  }
  document.addEventListener('DOMContentLoaded',function(){
    $('ros-refresh')?.addEventListener('click',load);
    $('ros-backfill')?.addEventListener('click',reconcile);
    document.querySelector('[data-page="revenue-os"]')?.addEventListener('click',()=>setTimeout(load,50));
    if($('page-revenue-os'))load();
  });
  window.loadRevenueOS=load;
})();