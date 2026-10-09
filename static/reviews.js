/* Reviews page only. Server already rendered published reviews — never fetch them again. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  var form = document.getElementById('review-form');
  if (!form) return;
  var stars = form.querySelectorAll('.star-input button');
  var rating = 0;
  stars.forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      rating = parseInt(btn.dataset.star, 10);
      stars.forEach(function (s) {
        s.classList.toggle('active', parseInt(s.dataset.star, 10) <= rating);
      });
      var input = form.querySelector('input[name="rating"]');
      if (input) input.value = String(rating);
    });
  });
  function esc(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var toast = document.getElementById('review-toast');
    var fd = new FormData(form);
    var payload = {
      name: (fd.get('name') || '').toString().trim(),
      business: (fd.get('business') || '').toString().trim(),
      rating: parseInt(fd.get('rating'), 10),
      text: (fd.get('text') || '').toString().trim()
    };
    if (!payload.name || payload.text.length < 12 || !(payload.rating >= 1 && payload.rating <= 5)) {
      if (toast) {
        toast.textContent = T_('show.js_fill', 'Please fill name, rating (1–5) and a review of at least 12 characters.');
        toast.className = 'review-toast err';
        toast.style.display = 'block';
      }
      return;
    }
    var btn = form.querySelector('.submit');
    var prevText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = T_('show.js_sending', 'Sending…'); }
    fetch('/api/client-reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.json().then(function (j) { return { ok: res.ok, j: j }; });
    }).then(function (o) {
      if (!o.ok) throw new Error(o.j.error || T_('show.js_failed', 'Failed'));
      if (toast) {
        toast.textContent = T_('rev.js_thanks', 'Thank you. Your review is on the page.');
        toast.className = 'review-toast ok';
        toast.style.display = 'block';
      }
      form.reset();
      rating = 0;
      stars.forEach(function (s) { s.classList.remove('active'); });
      var list = document.getElementById('client-review-list');
      if (list) {
        var empty = document.getElementById('rev-empty');
        if (empty) empty.remove();
        var card = document.createElement('article');
        card.className = 'client-review-card';
        card.innerHTML = '<div class="stars">' + '★'.repeat(payload.rating) + '☆'.repeat(5 - payload.rating) +
          '</div><p>' + esc(payload.text) + '</p><div class="meta"><strong>' + esc(payload.name) + '</strong>' +
          (payload.business ? ' · ' + esc(payload.business) : '') + '</div>';
        list.insertBefore(card, list.firstChild);
      }
    }).catch(function (err) {
      if (toast) {
        toast.textContent = err.message || T_('show.js_err', 'Could not submit review. Try again.');
        toast.className = 'review-toast err';
        toast.style.display = 'block';
      }
    }).then(function () {
      if (btn) { btn.disabled = false; btn.textContent = prevText; }
    });
  });
})();
