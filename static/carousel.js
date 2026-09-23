// Premium Framer-like carousels — banner ads + 3D templates + reveals — every click has a purpose
document.addEventListener('DOMContentLoaded', () => {
  const T_ = window.T || ((k, f) => f);
  function initCarousel(rootSelector, trackSelector, slideSelector, dotsSelector, prevSelector, nextSelector, viewportSelector, intervalMs) {
    const root = document.querySelector(rootSelector);
    if (!root) return;
    const track = root.querySelector(trackSelector);
    const slides = root.querySelectorAll(slideSelector);
    const dots = root.querySelectorAll(dotsSelector);
    const prev = root.querySelector(prevSelector);
    const next = root.querySelector(nextSelector);
    const viewport = root.querySelector(viewportSelector);
    if (!track || slides.length === 0) return;
    let idx = 0;
    let timer = null;
    const go = (i) => {
      idx = (i + slides.length) % slides.length;
      track.style.transform = `translateX(-${idx * 100}%)`;
      dots.forEach((d, k) => d.classList.toggle('active', k === idx));
      slides.forEach(s => s.classList.remove('in'));
      if (slides[idx]) slides[idx].classList.add('in');
    };
    const auto = () => { timer = setInterval(() => go(idx + 1), intervalMs); };
    const reset = () => { clearInterval(timer); auto(); };
    dots.forEach((d, k) => d.addEventListener('click', () => { go(k); reset(); }));
    if (prev) prev.addEventListener('click', () => { go(idx - 1); reset(); });
    if (next) next.addEventListener('click', () => { go(idx + 1); reset(); });
    if (viewport) {
      viewport.addEventListener('mouseenter', () => clearInterval(timer));
      viewport.addEventListener('mouseleave', auto);
    }
    // touch swipe (meaningful navigation, not dead)
    let startX = 0;
    track.addEventListener('touchstart', e => startX = e.touches[0].clientX, { passive: true });
    track.addEventListener('touchend', e => {
      const dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) > 50) { go(idx + (dx < 0 ? 1 : -1)); reset(); }
    });
    // keyboard (left/right) when focused
    root.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft') { go(idx - 1); reset(); }
      if (e.key === 'ArrowRight') { go(idx + 1); reset(); }
    });
    root.setAttribute('tabindex', '0');
    go(0); auto();
  }

  // Banner carousel — 3 professional Reachmark ad banners, 3.8s, live images
  initCarousel('.banner-carousel', '.banner-track', '.banner-slide', '.banner-dots button', '.banner-prev', '.banner-next', '.banner-viewport', 3800);
  // 3D template carousel — 4.2s
  initCarousel('.carousel-3d', '.carousel-track', '.carousel-slide', '.carousel-dots button', '.carousel-prev', '.carousel-next', '.carousel-viewport', 4200);

  // 3D tilt on mousemove — only on fine pointer (not touch) to keep premium stable
  if (window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    document.querySelectorAll('.carousel-mock, .banner-visual').forEach(mock => {
      mock.addEventListener('mousemove', (e) => {
        const rect = mock.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        const img = mock.querySelector('img');
        if (img) img.style.transform = `rotateY(${x * 10 - 8}deg) rotateX(${-y * 6 + 4}deg) translateY(-4px)`;
      });
      mock.addEventListener('mouseleave', () => {
        const img = mock.querySelector('img');
        if (img) img.style.transform = '';
      });
    });
  }

  // Premium reveal — IntersectionObserver (every scroll has meaning)
  const reveals = document.querySelectorAll('.premium-reveal, .premium-stagger');
  const io = new IntersectionObserver((entries) => {
    entries.forEach(ent => {
      if (ent.isIntersecting) { ent.target.classList.add('in'); io.unobserve(ent.target); }
    });
  }, { threshold: .14 });
  reveals.forEach(el => io.observe(el));

  // Ensure every CTA click has a visible effect (no dead navigation)
  document.querySelectorAll('a[href^="/"], a[href^="#"]').forEach(a => {
    const href = a.getAttribute('href');
    if (!href || href === '#') {
      a.addEventListener('click', e => {
        e.preventDefault();
        const target = document.querySelector('#enquiry') || document.querySelector('#website-samples') || document.querySelector('main');
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  });

  // Review form — client can leave review for good job done
  const form = document.getElementById('review-form');
  const stars = form ? form.querySelectorAll('.star-input button') : [];
  let rating = 0;
  if (form) {
    stars.forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        rating = parseInt(btn.dataset.star, 10);
        stars.forEach(s => s.classList.toggle('active', parseInt(s.dataset.star, 10) <= rating));
        const input = form.querySelector('input[name="rating"]');
        if (input) input.value = String(rating);
      });
    });
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const toast = document.getElementById('review-toast');
      const fd = new FormData(form);
      const payload = {
        name: (fd.get('name') || '').toString().trim(),
        business: (fd.get('business') || '').toString().trim(),
        rating: parseInt(fd.get('rating'), 10),
        text: (fd.get('text') || '').toString().trim()
      };
      if (!payload.name || !payload.text || !(payload.rating >= 1 && payload.rating <= 5)) {
        if (toast) { toast.textContent = T_('show.js_fill','Please fill name, rating (1-5) and review (≥12 chars).'); toast.className = 'review-toast err'; toast.style.display = 'block'; }
        return;
      }
      const btn = form.querySelector('.submit');
      const prevText = btn ? btn.textContent : '';
      if (btn) { btn.disabled = true; btn.textContent = T_('show.js_sending','Sending…'); }
      try {
        const res = await fetch('/api/client-reviews', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const j = await res.json();
        if (!res.ok) throw new Error(j.error || T_('show.js_failed','Failed'));
        if (toast) { toast.textContent = T_('show.js_thanks','Thank you — your review is live! Refresh to see it alongside Trustpilot.'); toast.className = 'review-toast ok'; toast.style.display = 'block'; }
        form.reset(); rating = 0; stars.forEach(s => s.classList.remove('active'));
        // append to list instantly (no wait)
        const list = document.getElementById('client-review-list');
        if (list) {
          const card = document.createElement('div');
          card.className = 'client-review-card';
          card.innerHTML = `<div class="stars">${'★'.repeat(payload.rating)}${'☆'.repeat(5 - payload.rating)}</div><p>“${payload.text.replace(/</g,'&lt;')}”</p><div class="meta"><span><strong>${payload.name}</strong>${payload.business ? ' · ' + payload.business : ''}</span><span>just now · live</span></div>`;
          list.prepend(card);
        }
      } catch (err) {
        if (toast) { toast.textContent = err.message || T_('show.js_err','Could not submit review. Try again.'); toast.className = 'review-toast err'; toast.style.display = 'block'; }
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = prevText; }
      }
    });
    // Load existing reviews into list (so wall stays fresh)
    fetch('/api/client-reviews').then(r => r.json()).then(rows => {
      const list = document.getElementById('client-review-list');
      if (!list || !Array.isArray(rows) || rows.length === 0) return;
      // keep first Trustpilot-style card? just prepend client reviews
      rows.slice(0, 6).forEach(rw => {
        const card = document.createElement('div');
        card.className = 'client-review-card';
        const d = new Date(rw.created);
        const when = d.toLocaleDateString();
        card.innerHTML = `<div class="stars">${'★'.repeat(rw.rating)}${'☆'.repeat(5 - rw.rating)}</div><p>“${String(rw.text).replace(/</g,'&lt;')}”</p><div class="meta"><span><strong>${String(rw.name).replace(/</g,'&lt;')}</strong>${rw.business ? ' · ' + String(rw.business).replace(/</g,'&lt;') : ''}</span><span>${when}</span></div>`;
        list.appendChild(card);
      });
    }).catch(()=>{});
  }
});
