// Invoices — Reachmark original billing UI (no AllScale branding copied)
var T_=window.T||function(k,f){return f;};
let invoiceData = {invoices:[], currencies:{}, statuses:[]};

function moneyFmt(minor, currency){
  if(minor==null) return '—';
  const d = invoiceData.currencies[currency] ?? 2;
  if(d===0) return `${currency} ${Number(minor).toLocaleString()}`;
  return `${currency} ${(minor/Math.pow(10,d)).toLocaleString(undefined,{minimumFractionDigits:d, maximumFractionDigits:d})}`;
}

async function loadInvoices(){
  try{
    const d = await api('/api/invoices');
    invoiceData = d;
    renderInvoices();
    // Show portal note for owner
    const note = document.getElementById('invoice-portal-note');
    if(note) note.style.display = (!sessionRole||sessionRole==='owner') ? 'block' : 'none';
    const btn = document.getElementById('new-invoice-btn');
    if(btn) btn.style.display = (sessionRole==='client') ? 'none' : '';
  }catch(e){
    const el=document.getElementById('invoice-list');
    if(el) el.innerHTML=`<p class="auth-error">${esc(e.message)}</p>`;
  }
}

let sessionRole = null; // owner | client | none
async function checkAuth(){
  try{
    const r = await fetch('/api/auth/me', {headers:{'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content||''}});
    if(r.ok){
      const j=await r.json();
      sessionRole=j.role;
    } else {
      // fallback to owner check via state? owner session exists if /api/state 200 and not client?
      sessionRole=null;
    }
  }catch(e){ sessionRole=null; }
  // Also check owner via existing login: if we have owner cookie, /api/state will succeed without client; but we need to infer.
  // If not client, treat as owner if state loads?
  if(!sessionRole){
    try{
      const s=await api('/api/state');
      // If state returned with leads, likely owner
      sessionRole='owner';
    }catch(e){
      sessionRole=null;
    }
  }
  // Adjust nav visibility for clients
  if(sessionRole==='client'){
    document.querySelectorAll('.nav').forEach(el=>{
      const p=el.dataset.page;
      const allowed=['overview','projects','invoices'];
      if(!allowed.includes(p)){
        el.style.display='none';
      } else {
        el.style.display='';
      }
    });
    // Hide owner-only sections in overview if needed
    const emptyNote = document.getElementById('invoice-notice');
    if(emptyNote) emptyNote.textContent=T_('wsj.iv_notice','Only invoices assigned to your email are shown here. Download PDFs anytime.');
    // Show client-specific banner in projects
    const projHead = document.querySelector('#page-projects .page-heading p');
    if(projHead) projHead.textContent=T_('wsj.iv_proj','Projects your studio shared with you.');

  } else {
    document.querySelectorAll('.nav').forEach(el=>el.style.display='');
  }
  // Update profile area
  const profile=document.getElementById('profile-name');
  if(profile){
    if(sessionRole==='client'){
      fetch('/api/auth/me').then(r=>r.json()).then(j=>{
        if(j.email) profile.innerHTML=esc(j.name||j.email.split('@')[0])+'<small>'+T_('wsj.iv_portal','Client portal · {e}').replace('{e}',esc(j.email))+'</small>';
      }).catch(()=>{});
    } else if(sessionRole==='owner'){
      // keep existing owner text from state.settings
    }
  }
  // Adjust logout handler to support both
  const origLogout=window.ownerLogout;
  window.ownerLogout=async function(){
    try{
      if(sessionRole==='client'){
        const r=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content||''}});
        if(r.ok) location.href='/signin';
        else toast(T_('wsj.iv_signout','Unable to sign out.'),true);
      } else if(origLogout) origLogout();
      else { const r=await fetch('/logout',{method:'POST',headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content||''}}); if(r.ok) location.href='/login'; }
    }catch(e){toast(e.message,true)}
  };
}

function renderInvoices(){
  const q = (document.getElementById('invoice-search')?.value||'').toLowerCase();
  const status = document.getElementById('invoice-status')?.value||'';
  const list = document.getElementById('invoice-list');
  const empty = document.getElementById('invoice-empty');
  if(!list) return;
  let rows = invoiceData.invoices || [];
  rows = rows.filter(r=>{
    const hay = (r.number+' '+(r.client_name||'')+' '+(r.client_email||'')).toLowerCase();
    return (!q || hay.includes(q)) && (!status || r.status===status);
  });
  if(empty) empty.style.display = rows.length ? 'none' : 'block';
  if(!rows.length){
    list.innerHTML = invoiceData.invoices.length ? '<p class="small muted">'+T_('wsj.iv_nomatch','No invoices match your search.')+'</p>' : '';
    return;
  }
  list.innerHTML = rows.map(r=>{
    const due = r.due_date ? T_('wsj.iv_due','Due {d}').replace('{d}',esc(r.due_date)) : T_('wsj.iv_nodue','No due date');
    const total = moneyFmt(r.total_minor, r.currency);
    const statusCls = r.status==='Paid' ? 'green' : r.status==='Overdue' ? 'amber' : r.status==='Draft' ? '' : '';
    return `<article class="invoice-card" style="border:1px solid #dce2d0;border-radius:10px;padding:16px;margin-bottom:12px;background:#fff;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap">
      <div style="min-width:220px">
        <strong>${esc(r.number)}</strong> <span class="badge ${statusCls}">${esc(r.status)}</span>
        <div style="margin:6px 0;font-weight:600">${esc(r.client_name)}</div>
        <div class="small muted">${esc(r.client_email||T_('wsj.iv_noemail','No email'))} · ${due}</div>
        <div class="small muted">${esc(r.currency)} · ${T_('wsj.iv_items','{n} items').replace('{n}',r.items?.length||0)}</div>
      </div>
      <div style="text-align:right;min-width:140px">
        <div style="font:600 18px Manrope,sans-serif">${esc(total)}</div>
        <div class="small muted">${T_('wsj.iv_issue','Issue {d}').replace('{d}',esc(r.issue_date||'—'))}</div>
        <div style="margin-top:10px;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">
          <button class="secondary" style="padding:7px 10px;font-size:12px" onclick="editInvoice('${r.id}')">${T_('wsj.iv_edit','Edit')}${sessionRole==='client'?T_('wsj.iv_view',' / view'):''} ↗</button>
          <a class="secondary" style="padding:7px 10px;font-size:12px;text-decoration:none" href="/api/documents/invoice/${r.id}.pdf" target="_blank">${T_('wsj.op_pdf','PDF ↓')}</a>
        </div>
      </div>
    </article>`;
  }).join('');
}

function addInvoiceRow(data={}){
  const list=document.getElementById('invoice-items-list');
  const row=document.createElement('div');
  row.className='invoice-row';
  row.style.cssText='display:grid;grid-template-columns:1fr 90px 120px 40px;gap:8px;margin-bottom:8px;align-items:end';
  row.innerHTML=`
    <label>${T_('wsj.iv_desc','Description')}<input name="item_desc" maxlength="500" required placeholder="${T_('wsj.iv_desc_ph','Website design — homepage')}" value="${esc(data.description||'')}"></label>
    <label>${T_('wsj.iv_qty','Qty')}<input name="item_qty" inputmode="decimal" required value="${esc(data.quantity||1)}"></label>
    <label>${T_('wsj.iv_unit','Unit price')}<input name="item_price" inputmode="decimal" required placeholder="500.00" value="${esc(data.unit_price||'')}"></label>
    <button type="button" class="secondary" style="padding:8px" onclick="this.closest('.invoice-row').remove();updateInvoiceTotals()">×</button>
  `;
  list.appendChild(row);
  row.querySelectorAll('input').forEach(i=>i.addEventListener('input', updateInvoiceTotals));
  updateInvoiceTotals();
}

function updateInvoiceTotals(){
  const currency=document.querySelector('#invoice-form [name="currency"]')?.value||'USD';
  const decimals=invoiceData.currencies[currency] ?? 2;
  const factor=Math.pow(10,decimals);
  let subtotal=0;
  const rows=document.querySelectorAll('#invoice-items-list .invoice-row');
  rows.forEach(r=>{
    const qty=parseFloat(r.querySelector('[name="item_qty"]').value)||0;
    const price=parseFloat(r.querySelector('[name="item_price"]').value)||0;
    const amt=Math.round(qty*price*factor);
    subtotal+=amt;
  });
  const taxRate=parseFloat(document.querySelector('#invoice-form [name="tax_rate"]')?.value)||0;
  const discType=document.querySelector('#invoice-form [name="discount_type"]')?.value||'none';
  const discVal=parseFloat(document.querySelector('#invoice-form [name="discount_value"]')?.value)||0;
  let discount=0;
  if(discType==='percent' && discVal) discount=Math.round(subtotal*discVal/100);
  else if(discType==='fixed' && discVal) discount=Math.min(Math.round(discVal*factor), subtotal);
  const taxable=subtotal-discount;
  const tax=Math.round(taxable*taxRate/100);
  const total=taxable+tax;
  const fmt = (m)=> decimals===0 ? `${currency} ${m.toLocaleString()}` : `${currency} ${(m/factor).toLocaleString(undefined,{minimumFractionDigits:decimals,maximumFractionDigits:decimals})}`;
  const el=document.getElementById('invoice-totals');
  if(el) el.innerHTML=`<div>${T_('wsj.iv_sub','Subtotal:')} <b>${fmt(subtotal)}</b></div><div>${T_('wsj.iv_disc','Discount:')} <b>-${fmt(discount)}</b> ${discType!=='none'?'('+esc(discType)+' '+discVal+')':''}</div><div>${T_('wsj.iv_tax','Tax ({r}%):').replace('{r}',taxRate)} <b>${fmt(tax)}</b></div><div style="font-weight:700;font-size:15px;margin-top:6px;border-top:1px solid #dce2d0;padding-top:6px">${T_('wsj.iv_total','Total:')} ${fmt(total)}</div>`;
}

async function editInvoice(id=null){
  if(sessionRole==='client' && !id){
    toast(T_('wsj.iv_only','Only your studio can create invoices.'), true);
    return;
  }
  await loadInvoices();
  // Populate currencies
  const form=document.getElementById('invoice-form');
  form.reset();
  const currencies=Object.keys(invoiceData.currencies);
  const curSel=form.elements.currency;
  curSel.innerHTML=currencies.map(c=>`<option>${esc(c)}</option>`).join('');
  // Populate projects/leads
  try{
    const stateResp = await api('/api/state');
    const projResp = await api('/api/projects');
    form.elements.project_id.innerHTML='<option value="">'+T_('ws.iv_nolink','Not linked')+'</option>'+ (projResp.projects||[]).map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join('');
    form.elements.lead_id.innerHTML='<option value="">'+T_('ws.iv_nolink','Not linked')+'</option>'+ (stateResp.leads||[]).slice(0,120).map(l=>`<option value="${l.id}">${esc(l.name)} · ${esc(l.city||'')}</option>`).join('');
  }catch(e){ /* client may not have state leads */ 
    try{
      const projResp = await api('/api/projects');
      form.elements.project_id.innerHTML='<option value="">'+T_('ws.iv_nolink','Not linked')+'</option>'+ (projResp.projects||[]).map(p=>`<option value="${p.id}">${esc(p.title)}</option>`).join('');
    }catch(_){}
  }
  const data = invoiceData.invoices.find(x=>x.id===id);
  if(data){
    form.elements.id.value=data.id;
    form.elements.client_name.value=data.client_name||'';
    form.elements.client_email.value=data.client_email||'';
    form.elements.client_address.value=data.client_address||'';
    form.elements.currency.value=data.currency||'USD';
    form.elements.status.value=data.status||'Draft';
    form.elements.issue_date.value=data.issue_date||'';
    form.elements.due_date.value=data.due_date||'';
    form.elements.project_id.value=data.project_id||'';
    form.elements.lead_id.value=data.lead_id||'';
    form.elements.tax_rate.value=data.tax_rate||0;
    form.elements.discount_type.value=data.discount_type||'none';
    form.elements.discount_value.value=data.discount_value||0;
    form.elements.notes.value=data.notes||'';
    form.elements.terms.value=data.terms||'';
    document.getElementById('invoice-items-list').innerHTML='';
    const decimals = invoiceData.currencies[data.currency] ?? 2;
    const factor=Math.pow(10,decimals);
    (data.items||[]).forEach(it=>{
      const unit = decimals===0 ? String(it.unit_minor) : (it.unit_minor/factor).toFixed(decimals);
      addInvoiceRow({description: it.description, quantity: it.quantity, unit_price: unit});
    });
    if(sessionRole==='client'){
      // Make form read-only for clients
      form.querySelectorAll('input,select,textarea,button[type="submit"]').forEach(el=>{
        if(el.type!=='hidden') el.disabled=true;
      });
      document.querySelector('#invoice-modal button.secondary[onclick*="addInvoiceRow"]')?.setAttribute('disabled','');
    } else {
      form.querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=false);
    }
    document.getElementById('invoice-documents').innerHTML=`<a href="/api/documents/invoice/${data.id}.pdf" target="_blank">${T_('wsj.iv_pdf2','↓ Invoice PDF')}</a>${!sessionRole||sessionRole==='owner'?`<button type="button" class="danger-link" onclick="deleteInvoice('${data.id}')">${T_('wsj.iv_del','Delete invoice')}</button>`:''}`;
    document.getElementById('invoice-modal-title').textContent= sessionRole==='client' ? T_('wsj.iv_viewonly','Invoice — view only') : T_('wsj.iv_edit_t','Edit invoice');
  } else {
    form.elements.id.value='';
    form.elements.currency.value='USD';
    form.elements.status.value='Draft';
    form.elements.discount_type.value='none';
    document.getElementById('invoice-items-list').innerHTML='';
    addInvoiceRow({description:T_('wsj.iv_d1','Website design and build'), quantity:1, unit_price:'1200.00'});
    addInvoiceRow({description:T_('wsj.iv_d2','Content and launch'), quantity:1, unit_price:'300.00'});
    document.getElementById('invoice-documents').innerHTML='<p class="small muted">'+T_('wsj.iv_savefirst','Save to enable PDF download. Totals below are live.')+'</p>';
    document.getElementById('invoice-modal-title').textContent=T_('wsj.iv_new','New invoice');
    form.querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=false);
  }
  // Attach listeners
  form.querySelectorAll('[name="currency"],[name="tax_rate"],[name="discount_type"],[name="discount_value"]').forEach(el=>el.addEventListener('input', updateInvoiceTotals));
  form.querySelectorAll('[name="currency"],[name="tax_rate"],[name="discount_type"],[name="discount_value"]').forEach(el=>el.addEventListener('change', updateInvoiceTotals));
  updateInvoiceTotals();
  openModal('invoice-modal');
}

document.getElementById('invoice-form')?.addEventListener('submit', async e=>{
  e.preventDefault();
  const form=e.target;
  if(sessionRole==='client'){ toast(T_('wsj.iv_noedit','Clients cannot edit invoices.'), true); return; }
  const btn=form.querySelector('button[type="submit"]'); btn.disabled=true;
  const data=Object.fromEntries(new FormData(form));
  // Collect items
  const rows=[...document.querySelectorAll('#invoice-items-list .invoice-row')];
  data.items=rows.map(r=>{
    const d=r.querySelector('[name="item_desc"]').value.trim();
    const q=r.querySelector('[name="item_qty"]').value.trim();
    const p=r.querySelector('[name="item_price"]').value.trim();
    return {description:d, quantity:q, unit_price:p};
  });
  // Fix numeric
  data.tax_rate = data.tax_rate||0;
  data.discount_value = data.discount_value||0;
  try{
    const id=data.id;
    delete data.id;
    // Strip empty optional
    if(!data.project_id) delete data.project_id;
    if(!data.lead_id) delete data.lead_id;
    if(id){
      await api('/api/invoices/'+id,'PATCH', data);
      toast(T_('wsj.iv_updated','Invoice updated.'));
    } else {
      const r=await api('/api/invoices','POST', data);
      toast(T_('wsj.iv_created','Invoice created: {n}').replace('{n}',r.number));
    }
    closeModal('invoice-modal');
    await loadInvoices();
    navigate('invoices');
  }catch(err){toast(err.message,true)} finally {btn.disabled=false}
});

async function deleteInvoice(id){
  if(!confirm(T_('wsj.iv_delq','Delete this invoice? This cannot be undone.'))) return;
  try{await api('/api/invoices/'+id,'DELETE'); closeModal('invoice-modal'); await loadInvoices(); toast(T_('wsj.iv_deleted','Invoice deleted.'))}catch(e){toast(e.message,true)}
}

// Extend navigate to handle invoices
const _origNavigate = window.navigate;
window.navigate = function(page){
  if(typeof _origNavigate==='function') _origNavigate(page);
  else {
    document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+page));
    document.querySelectorAll('.nav').forEach(p=>p.classList.toggle('active',p.dataset.page===page));
    const bc=document.getElementById('breadcrumb'); if(bc) bc.textContent=page;
  }
  if(page==='invoices') loadInvoices();
  // Also keep existing behavior for projects etc.
  if(typeof loadProjects==='function' && page==='projects') loadProjects();
};

// Also hook into original app.js navigate if it was defined earlier
if(typeof navigate==='function'){
  const baseNav=navigate;
  window.navigate=function(p){
    baseNav(p);
    if(p==='invoices') loadInvoices();
  }
}

// Init auth and invoices when page loads
document.addEventListener('DOMContentLoaded', async ()=>{
  await checkAuth();
  if(document.getElementById('page-invoices')?.classList.contains('active')) loadInvoices();
});

// Re-check auth after login/logout
setInterval(checkAuth, 30000);
