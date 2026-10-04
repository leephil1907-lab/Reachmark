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

setTimeout(()=>{const page=location.hash.slice(1);if(['overview','crew','leads','outreach','settings','global','health','portfolio','enquiries','contracts','projects','invoices','clients','network'].includes(page))navigate(page)},0);
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