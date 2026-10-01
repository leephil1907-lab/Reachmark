(() => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function load() {
    const status = document.getElementById('google-business-status');
    const list = document.getElementById('google-business-locations');
    if (!status || !list) return;
    try {
      const r = await fetch('/api/google-business/status');
      const j = await r.json();
      status.innerHTML = j.configured
        ? (j.connected ? '<span class="gbp-ok">Connected</span>' : '<span class="gbp-warn">Not connected</span>')
        : '<span class="gbp-warn">Server configuration required</span>';
      document.getElementById('google-business-connect').disabled = !j.configured;
      if (!j.connected) {
        list.innerHTML = '<div class="gbp-empty">Connect an authorized Google account to load real Business Profile locations.</div>';
        return;
      }
      const lr = await fetch('/api/google-business/locations');
      const locations = (await lr.json()).locations || [];
      list.innerHTML = locations.length ? locations.map(x =>
        '<article class="gbp-location"><div><strong>'+esc(x.title || 'Untitled location')+'</strong><p>'+esc(x.website_uri || 'No website recorded')+'</p><small>'+esc(x.resource_name)+'</small></div><button class="secondary gbp-review" data-id="'+esc(x.id)+'">Load reviews</button></article>'
      ).join('') : '<div class="gbp-empty">No locations have been synced yet.</div>';
      list.querySelectorAll('.gbp-review').forEach(b => b.addEventListener('click', async () => {
        b.disabled=true; b.textContent='Loading…';
        try {
          const rr=await fetch('/api/google-business/reviews?location_id='+encodeURIComponent(b.dataset.id));
          const jj=await rr.json();
          if(!rr.ok) throw new Error(jj.error || 'Unable to load reviews');
          alert('Loaded '+((jj.reviews||[]).length)+' real Google reviews.');
        } catch(e) { alert(e.message); }
        finally { b.disabled=false; b.textContent='Load reviews'; }
      }));
    } catch(e) {
      status.innerHTML='<span class="gbp-warn">Unable to read integration status</span>';
    }
  }
  window.loadGoogleBusiness = load;
  document.addEventListener('click', e => {
    if (e.target?.id === 'google-business-connect') window.location.href='/api/google-business/connect';
    if (e.target?.id === 'google-business-sync') {
      (async () => {
        const r=await fetch('/api/google-business/status'); const j=await r.json();
        const id=j.accounts?.[0]?.id;
        if(!id) return alert('Connect a Google Business account first.');
        const rr=await fetch('/api/google-business/sync',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify({account_id:id})});
        const jj=await rr.json();
        if(!rr.ok) return alert(jj.error||'Sync failed');
        await load();
        alert('Synced '+jj.synced+' real Business Profile location(s).');
      })();
    }
  });
  document.addEventListener('DOMContentLoaded', load);
})();
