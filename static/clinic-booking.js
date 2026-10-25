(function(){
  const form=document.getElementById('clinic-booking-form');
  if(!form)return;
  const slotsEl=document.getElementById('clinic-slots');
  const statusEl=document.getElementById('clinic-status');
  const submit=document.getElementById('clinic-submit');
  let selectedSlot=null;
  let loadedSlots=[];
  const fmt=(value)=>{try{return new Intl.DateTimeFormat(undefined,{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(value));}catch(_){return value;}};
  function status(message){statusEl.textContent=message;statusEl.hidden=false;}
  function renderSlots(slots){
    slotsEl.replaceChildren();
    loadedSlots=slots||[];
    if(!loadedSlots.length){
      const p=document.createElement('p');p.className='hint';p.textContent='No future appointment times are configured. Please contact the clinic to ask about availability.';
      slotsEl.appendChild(p);submit.disabled=true;return;
    }
    loadedSlots.forEach(slot=>{
      const button=document.createElement('button');button.type='button';button.className='slot';button.textContent=fmt(slot.start);
      button.setAttribute('aria-pressed','false');
      button.addEventListener('click',()=>{
        selectedSlot=slot.id;
        slotsEl.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed','false'));
        button.setAttribute('aria-pressed','true');submit.disabled=false;statusEl.hidden=true;
      });
      slotsEl.appendChild(button);
    });
    submit.disabled=true;
  }
  fetch('/api/clinic/availability',{headers:{'Accept':'application/json'}})
    .then(r=>r.json().then(data=>({ok:r.ok,data})))
    .then(({ok,data})=>{if(!ok)throw new Error(data.error||'Availability could not be loaded.');renderSlots(data.slots||[]);})
    .catch(()=>{slotsEl.textContent='Availability could not be loaded. Refresh this page or contact the clinic.';submit.disabled=true;});
  form.addEventListener('submit',async event=>{
    event.preventDefault();statusEl.hidden=true;
    if(!selectedSlot||!loadedSlots.some(s=>s.id===selectedSlot)){status('Choose a currently available time first.');return;}
    if(!form.elements.consent.checked){status('Please agree to the contact consent before submitting.');return;}
    submit.disabled=true;submit.textContent='Sending request…';
    const field=(name)=>form.elements.namedItem(name);
    const payload={slot_id:selectedSlot,name:field('name').value,email:field('email').value,
      phone:field('phone').value,service:field('service').value,note:field('note').value,
      consent:field('consent').checked};
    try{
      const response=await fetch('/api/clinic/appointments',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(payload)});
      const data=await response.json();
      if(data.handoff){status(data.message||data.next_action||'Your message needs staff attention.');return;}
      if(response.status===409){
        status(data.error||'That time is no longer available. Refreshing available times…');
        selectedSlot=null;
        const refresh=await fetch('/api/clinic/availability');const fresh=await refresh.json();renderSlots(fresh.slots||[]);return;
      }
      if(!response.ok)throw new Error(data.error||'The request could not be submitted.');
      status(data.message||'Request received. The clinic will confirm your appointment.');
      form.reset();selectedSlot=null;await fetch('/api/clinic/availability').then(r=>r.json()).then(data=>renderSlots(data.slots||[]));
    }catch(error){status(error.message||'A network error occurred. Please try again.');}
    finally{submit.textContent='Request appointment';submit.disabled=!selectedSlot||!loadedSlots.some(s=>s.id===selectedSlot);}
  });
})();