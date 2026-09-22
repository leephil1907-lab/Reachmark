// Reachmark public theme + motion — light/dark + page transitions (not static)
(function(){
  const root=document.documentElement;
  const saved=localStorage.getItem('reachmark-theme');
  if(saved) root.setAttribute('data-theme', saved);
  else if(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) root.setAttribute('data-theme','dark');
  window.toggleTheme=function(){
    const isDark=root.getAttribute('data-theme')==='dark';
    const next=isDark?'light':'dark';
    if(next==='light') root.removeAttribute('data-theme'); else root.setAttribute('data-theme','dark');
    localStorage.setItem('reachmark-theme', next);
    const btn=document.getElementById('theme-toggle-public');
    if(btn) btn.textContent=isDark?'◐':'☾';
  };
  document.addEventListener('DOMContentLoaded',()=>{
    const btn=document.getElementById('theme-toggle-public');
    if(btn){
      const isDark=root.getAttribute('data-theme')==='dark';
      btn.textContent=isDark?'☾':'◐';
      btn.addEventListener('click', window.toggleTheme);
    }
    // nav dynamic motion: sticky glass on scroll
    const navEl=document.querySelector('nav, .public-nav');
    if(navEl){
      let tick=false;
      const onNavScroll=()=>{
        if(!tick){
          requestAnimationFrame(()=>{
            if(window.scrollY>18) navEl.classList.add('scrolled');
            else navEl.classList.remove('scrolled');
            tick=false;
          });
          tick=true;
        }
      };
      window.addEventListener('scroll', onNavScroll, {passive:true});
      onNavScroll();
    }
    // motion: reveal on scroll
    const els=document.querySelectorAll('.hero, .ribbon, .features .card, .honest, .sample-card, .enquiry-layout, .cta');
    els.forEach((el,i)=>{el.style.opacity='0'; el.style.transform='translateY(14px)'; el.style.transition='opacity .6s ease, transform .6s cubic-bezier(.16,1,.3,1)'; el.style.transitionDelay=(i%3*80)+'ms'});
    const io=new IntersectionObserver((entries)=>{
      entries.forEach(e=>{
        if(e.isIntersecting){ e.target.style.opacity='1'; e.target.style.transform='none'; io.unobserve(e.target); }
      });
    },{threshold:.12});
    els.forEach(el=>io.observe(el));
    // respect reduced motion
    if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){
      els.forEach(el=>{el.style.opacity='1'; el.style.transform='none'; el.style.transition='none'});
    }
  });

  // hidden owner access: 5 rapid clicks on logo → /login (no visible link)
  let clicks=0, timer=null;
  const goOwner=()=>{ clicks=0; location.href='/login'; };
  const attach=(el)=>{ if(!el) return; el.style.cursor='pointer'; el.addEventListener('click', (e)=>{
    // Only count if not already navigating
    clicks++;
    if(clicks===1){ timer=setTimeout(()=>{clicks=0;}, 2200); }
    if(clicks>=5){ clearTimeout(timer); e.preventDefault(); goOwner(); }
  }); };
  // public pages logo selectors
  document.querySelectorAll('.logo, .public-logo, [aria-label="Reachmark home"] img, .brand-wordmark, .brand-compact').forEach(attach);
  // also allow hidden keyboard: type "reach" quickly
  let keys='';
  document.addEventListener('keydown', (e)=>{
    keys+=e.key.toLowerCase();
    if(keys.length>10) keys=keys.slice(-10);
    if(keys.endsWith('reach')){
      keys='';
      goOwner();
    }
  });

})();
