// Reachmark public theme + motion — light/dark + page transitions (not static)
(function(){
  const root=document.documentElement;
  let motionTimer=null;
  function readSavedTheme(){
    try{return localStorage.getItem('reachmark-theme');}catch(e){return null;}
  }
  function saveTheme(value){
    try{localStorage.setItem('reachmark-theme',value);}catch(e){}
  }
  const saved=readSavedTheme();
  if(saved==='dark'||saved==='light') {
    if(saved==='dark') root.setAttribute('data-theme','dark');
    else root.removeAttribute('data-theme');
  } else if(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    root.setAttribute('data-theme','dark');
  }
  function isDark(){return root.getAttribute('data-theme')==='dark';}
  function paintChrome(){
    const dark=isDark();
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta) meta.setAttribute('content',dark?'#0a0c0b':'#fbfbf8');
    const btn=document.getElementById('theme-toggle-public');
    if(btn){
      btn.textContent=dark?'☾':'◐';
      btn.setAttribute('aria-pressed',dark?'true':'false');
      btn.setAttribute('title',dark?'Switch to light theme':'Switch to dark theme');
    }
  }
  window.toggleTheme=function(){
    const next=isDark()?'light':'dark';
    if(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches){
      if(next==='light') root.removeAttribute('data-theme');
      else root.setAttribute('data-theme','dark');
    } else {
      root.classList.add('theme-switching');
      if(next==='light') root.removeAttribute('data-theme');
      else root.setAttribute('data-theme','dark');
      if(motionTimer) clearTimeout(motionTimer);
      motionTimer=setTimeout(function(){root.classList.remove('theme-switching');motionTimer=null;},460);
    }
    saveTheme(next);
    paintChrome();
  };
  paintChrome();
  document.addEventListener('DOMContentLoaded',()=>{
    paintChrome();
    const btn=document.getElementById('theme-toggle-public');
    if(btn && !btn.dataset.themeBound){
      btn.dataset.themeBound='1';
      btn.addEventListener('click',window.toggleTheme);
    }
    // Sticky glass header responds smoothly to scroll without changing layout.
    const navEl=document.querySelector('.pub-head, nav, .public-nav');
    if(navEl){
      let tick=false;
      const onNavScroll=()=>{
        if(!tick){
          requestAnimationFrame(()=>{
            navEl.classList.toggle('scrolled',window.scrollY>18);
            tick=false;
          });
          tick=true;
        }
      };
      window.addEventListener('scroll',onNavScroll,{passive:true});
      onNavScroll();
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
