(() => {
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => [...root.querySelectorAll(s)];
  const toastEl = $('#toast');
  let toastTimer;
  let projects = [];
  let currentView = 'create';
  const labels = {cinematic:'Cinematic',editorial:'Editorial',product:'Product',surreal:'Surreal',documentary:'Documentary',motion:'Motion design'};
  function toast(message, kind='') {
    toastEl.textContent = message; toastEl.className = 'toast show ' + kind;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => toastEl.className='toast', 4500);
  }
  async function api(url, options={}) {
    const response = await fetch(url, {credentials:'same-origin', ...options, headers:{'Content-Type':'application/json', ...(options.headers||{})}});
    const data = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(data.error || 'Request failed. Please try again.');
    return data;
  }
  function setView(view) {
    currentView = view;
    $$('.view').forEach(el => el.classList.toggle('hidden', el.id !== 'view-' + view));
    $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
    if (view === 'projects') loadProjects();
    window.scrollTo({top:0,behavior:'smooth'});
  }
  $$('.nav-item').forEach(btn => btn.addEventListener('click', () => setView(btn.dataset.view)));
  $$('[data-go-create]').forEach(btn => btn.addEventListener('click', () => setView('create')));
  $('#new-project-top').addEventListener('click', () => { $('#project-title').value='Untitled film'; $('#brief').value=''; setView('create'); });
  $('#new-project-list').addEventListener('click', () => { $('#project-title').value='Untitled film'; $('#brief').value=''; setView('create'); });
  $$('.prompt-chip').forEach(btn => btn.addEventListener('click', () => { $('#brief').value=btn.dataset.prompt; $('#brief').focus(); updatePreview(); }));
  $$('input[name="style"]').forEach(input => input.addEventListener('change', () => { $$('.style-option').forEach(x=>x.classList.toggle('selected',x.contains(input) && input.checked)); updatePreview(); }));
  $('#aspect').addEventListener('change', updatePreview);
  $('#duration').addEventListener('change', updatePreview);
  function updatePreview() {
    const ratio = $('#aspect').value, duration = Number($('#duration').value), style = $('input[name="style"]:checked').value;
    $('#preview-ratio').textContent = ratio; $('#preview-length').textContent = '00:' + String(duration).padStart(2,'0'); $('#preview-style').textContent = labels[style];
    const stage = $('#preview-stage');
    stage.style.aspectRatio = ratio.replace(':',' / ');
    stage.style.height = ratio === '16:9' ? '220px' : ratio === '1:1' ? '270px' : '270px';
    stage.style.background = ({
      cinematic:'radial-gradient(ellipse at 55% 38%,#63784c,#273629 38%,#121812 80%)',
      editorial:'linear-gradient(135deg,#d0d0ad,#777f63 42%,#20291e)',
      product:'radial-gradient(ellipse at 50% 45%,#9b9d7b,#344334 43%,#121812 82%)',
      surreal:'radial-gradient(ellipse at 50% 40%,#8e75a8,#43344f 38%,#17141d 80%)',
      documentary:'radial-gradient(ellipse at 50% 40%,#829b82,#3d5746 42%,#17231a 80%)',
      motion:'repeating-linear-gradient(135deg,#d6f269 0 12px,#243426 12px 24px)'
    })[style];
    const brief = $('#brief').value.trim();
    if (brief) $('.preview-type b').innerHTML = escapeHtml(brief.split(/[.!?\n]/)[0].slice(0,30) || 'Objects of desire').replace(/\s+/g,' ').replace(/(.{16})/g,'$1<br>');
  }
  function escapeHtml(s) { return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  async function loadCapabilities() {
    try {
      const d = await api('/api/studio/capabilities');
      $('#system-status').textContent = d.status === 'ready' ? 'Render engine connected' : 'Studio ready';
      $('#system-detail').textContent = d.status === 'ready' ? 'GPU worker online' : 'GPU worker not connected';
      $('#pipeline-message').textContent = d.features.message;
      Object.entries({wangp:'wangp',ltx2:'ltx2',hunyuan:'hunyuan',opensora:'opensora'}).forEach(([id,key]) => {
        const el = $('[data-engine="'+id+'"]'); if (!el) return;
        const p = d.providers.find(x=>x.id===key);
        el.textContent = p && p.configured ? 'Connected' : 'Not connected';
        el.classList.toggle('state-ready', !!(p && p.configured));
      });
    } catch (e) { $('#system-status').textContent='Workspace available'; $('#system-detail').textContent='Engine status unavailable'; $('#pipeline-message').textContent='Could not check engine status.'; }
  }
  async function loadProjects() {
    const root = $('#projects-list');
    try {
      const d = await api('/api/studio/projects'); projects = d.projects || [];
      if (!projects.length) { root.innerHTML='<div class="empty-state"><span>✳</span><h3>Your next great film starts here.</h3><p>Create a brief to begin your first project.</p><button class="button button-primary" data-go-create>Start creating</button></div>'; $('[data-go-create]',root).addEventListener('click',()=>setView('create')); return; }
      root.innerHTML = projects.map(p=>'<article class="project-card"><div class="project-card-top"></div><div class="project-card-meta"><span>'+escapeHtml(p.aspect_ratio)+' · '+Number(p.duration)+' sec</span><span>'+escapeHtml(p.status)+'</span></div><h3>'+escapeHtml(p.title)+'</h3><p>'+escapeHtml((p.brief||'No creative brief yet.').slice(0,110))+'</p><button class="button button-quiet" data-open="'+escapeHtml(p.id)+'">Open project ↗</button></article>').join('');
      $$('[data-open]',root).forEach(btn=>btn.addEventListener('click',()=>openProject(btn.dataset.open)));
    } catch(e) { root.innerHTML='<div class="empty-state"><h3>Projects could not be loaded.</h3><p>'+escapeHtml(e.message)+'</p></div>'; }
  }
  async function openProject(id) {
    try {
      const d = await api('/api/studio/projects/'+encodeURIComponent(id));
      $('#project-title').value = d.project.title; $('#brief').value = d.project.brief || '';
      $('#aspect').value = d.project.aspect_ratio; $('#duration').value = String(d.project.duration);
      const style = $('input[name="style"][value="'+d.project.style+'"]'); if (style) style.checked=true;
      updatePreview(); setView('create');
      if (d.jobs && d.jobs.length) toast('Project loaded. Latest production status: '+d.jobs[0].status+'.');
      else toast('Project loaded. Your brief is ready to continue.','success');
    } catch(e) { toast(e.message,'error'); }
  }
  $('#project-form').addEventListener('submit', async event => {
    event.preventDefault();
    const brief = $('#brief').value.trim();
    if (brief.length < 8) { toast('Add a creative brief of at least a few words first.','error'); $('#brief').focus(); return; }
    const btn = $('.generate-button'); btn.disabled=true; btn.style.opacity='.7';
    const old = btn.innerHTML; btn.innerHTML='✳ Saving creative project…';
    try {
      const d = await api('/api/studio/projects',{method:'POST',body:JSON.stringify({
        title:$('#project-title').value.trim() || 'Untitled film', brief,
        aspect_ratio:$('#aspect').value, duration:Number($('#duration').value),
        style:$('input[name="style"]:checked').value
      })});
      const project = d.project;
      try {
        const job = await api('/api/studio/projects/'+encodeURIComponent(project.id)+'/generate',{method:'POST',body:JSON.stringify({provider:'ltx2',prompt:brief})});
        toast('Project saved. Generation job '+job.job.status+'.','success');
      } catch (e) {
        if (e.message.includes('VIDEO_STUDIO_WORKER_URL') || e.message.includes('GPU worker')) toast('Project saved. '+e.message,'error');
        else toast('Project saved. '+e.message,'error');
      }
      await loadProjects();
    } catch(e) { toast(e.message,'error'); }
    finally { btn.disabled=false; btn.style.opacity='1'; btn.innerHTML=old; }
  });
  updatePreview(); loadCapabilities();
})();