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
      if(!btn.querySelector('svg')) btn.textContent=dark?'☾':'◐';
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

  // The admin console is reached only by typing /admin — no hidden shortcuts on the public site.
})();
