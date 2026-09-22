document.querySelectorAll('[data-enquiry-form]').forEach(form=>{
 const shell=form.parentElement,success=shell.querySelector('[data-enquiry-success]'),error=form.querySelector('[data-enquiry-error]'),button=form.querySelector('button[type=submit]');
 const newId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');let requestId=newId();
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(!form.reportValidity())return;error.hidden=true;button.disabled=true;button.textContent='Sending your enquiry…';
  const data=Object.fromEntries(new FormData(form));data.consent=form.elements.consent.checked;data.request_id=requestId;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
  try{
   const response=await fetch('/api/enquiries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
   const result=await response.json();if(!response.ok)throw new Error(result.error||'The request could not be saved. Please try again.');
   shell.querySelector('[data-enquiry-reference]').textContent=result.reference;form.hidden=true;success.hidden=false;success.focus();success.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
  }catch(err){error.textContent=err.name==='AbortError'?'The connection timed out. Your details are still here. Retry to confirm receipt; duplicate requests with the same reference are prevented.':err.message||'Unable to connect. Please try again.';error.hidden=false;error.scrollIntoView({block:'center'});}
  finally{clearTimeout(timer);button.disabled=false;button.textContent='Send your enquiry ↗';}
 });
 shell.querySelector('[data-enquiry-again]').addEventListener('click',()=>{form.reset();requestId=newId();form.hidden=false;success.hidden=true;error.hidden=true;form.elements.name.focus();});
});
