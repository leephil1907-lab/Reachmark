/* Small pointer-driven tilt for the existing product scene. No canvas or external runtime. */
(function(){
  var scene=document.querySelector('.ed-console');
  if(!scene||!window.matchMedia||window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var fine=window.matchMedia('(hover: hover) and (pointer: fine)');
  if(!fine.matches) return;
  var frame=0, rect=null, x=0, y=0;
  function move(e){
    rect=rect||scene.getBoundingClientRect();
    x=((e.clientX-rect.left)/rect.width-.5)*2;
    y=((e.clientY-rect.top)/rect.height-.5)*2;
    if(frame) cancelAnimationFrame(frame);
    frame=requestAnimationFrame(function(){
      scene.style.setProperty('--rm-tilt-x',(x*3.2).toFixed(2)+'deg');
      scene.style.setProperty('--rm-tilt-y',(y*-2.2).toFixed(2)+'deg');
      scene.style.setProperty('--rm-lift',Math.min(5,Math.hypot(x,y)*2).toFixed(2)+'px');
      frame=0;
    });
  }
  function reset(){
    rect=null;
    scene.style.setProperty('--rm-tilt-x','0deg');
    scene.style.setProperty('--rm-tilt-y','0deg');
    scene.style.setProperty('--rm-lift','0px');
  }
  scene.addEventListener('pointermove',move,{passive:true});
  scene.addEventListener('pointerleave',reset,{passive:true});
  window.addEventListener('resize',function(){rect=null;},{passive:true});
})();
