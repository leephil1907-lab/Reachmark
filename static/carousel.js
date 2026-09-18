// Premium Framer-like 3D carousel — top business samples
document.addEventListener('DOMContentLoaded', () => {
  const track = document.querySelector('.carousel-track');
  const slides = document.querySelectorAll('.carousel-slide');
  const dots = document.querySelectorAll('.carousel-dots button');
  const prev = document.querySelector('.carousel-prev');
  const next = document.querySelector('.carousel-next');
  if(!track || slides.length===0) return;
  let idx = 0;
  let timer = null;
  const go = (i) => {
    idx = (i + slides.length) % slides.length;
    track.style.transform = `translateX(-${idx*100}%)`;
    dots.forEach((d, k) => d.classList.toggle('active', k===idx));
    // premium stagger reveal
    slides.forEach(s => s.classList.remove('in'));
    slides[idx].classList.add('in');
  };
  const auto = () => {
    timer = setInterval(() => go(idx+1), 4200);
  };
  const reset = () => { clearInterval(timer); auto(); };
  dots.forEach((d,k)=> d.addEventListener('click', ()=>{ go(k); reset(); }));
  if(prev) prev.addEventListener('click', ()=>{ go(idx-1); reset(); });
  if(next) next.addEventListener('click', ()=>{ go(idx+1); reset(); });
  // pause on hover
  const viewport = document.querySelector('.carousel-viewport');
  if(viewport){
    viewport.addEventListener('mouseenter', ()=> clearInterval(timer));
    viewport.addEventListener('mouseleave', auto);
  }
  // touch swipe
  let startX=0;
  track.addEventListener('touchstart', e=> startX=e.touches[0].clientX, {passive:true});
  track.addEventListener('touchend', e=>{
    const dx = e.changedTouches[0].clientX - startX;
    if(Math.abs(dx)>50){ go(idx + (dx<0?1:-1)); reset(); }
  });
  go(0); auto();

  // 3D tilt on mousemove for active slide mock
  const mock = document.querySelector('.carousel-mock');
  if(mock){
    mock.addEventListener('mousemove', (e)=>{
      const rect = mock.getBoundingClientRect();
      const x = (e.clientX - rect.left)/rect.width - 0.5;
      const y = (e.clientY - rect.top)/rect.height - 0.5;
      const img = mock.querySelector('img');
      if(img) img.style.transform = `rotateY(${x*10-8}deg) rotateX(${ -y*6 +4}deg) translateY(-4px)`;
    });
    mock.addEventListener('mouseleave', ()=>{
      const img = mock.querySelector('img');
      if(img) img.style.transform = '';
    });
  }

  // Intersection reveal for premium sections
  const reveals = document.querySelectorAll('.premium-reveal, .premium-stagger');
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(ent=>{
      if(ent.isIntersecting){ ent.target.classList.add('in'); io.unobserve(ent.target); }
    });
  }, {threshold:.14});
  reveals.forEach(el=> io.observe(el));
});
