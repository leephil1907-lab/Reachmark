/* Reachmark crew orb — the pipeline drawn as a living system.
   Adapted from the tiered approach in the RevenueJob repository (owner's own project):
   a static SVG poster that always renders, an optional 2D canvas "lite" tier that
   takes over when the browser is idle and motion is welcome, and an explicit note that
   the heavy WebGL tier is not shipped here. Every animation has a reduced-motion path.
   No dependencies, no WebGL, ~4 KB. */
(function (root) {
  'use strict';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var STAGES = [
    { key: 'prospects', label: 'Prospects' },
    { key: 'intelligence', label: 'Intelligence' },
    { key: 'conversations', label: 'Conversations' },
    { key: 'opportunities', label: 'Opportunities' },
    { key: 'revenue', label: 'Revenue' }
  ];
  var reduce = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function poster() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 320 240');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label',
      'Crew pipeline: Prospects to Intelligence to Conversations to Opportunities, converging on an AI core, with Revenue leaving the system.');
    svg.innerHTML =
      '<defs><radialGradient id="rmCore" cx="50%" cy="50%" r="50%">' +
      '<stop offset="0%" stop-color="#D5F268" stop-opacity=".95"/><stop offset="100%" stop-color="#8CA650" stop-opacity="0"/></radialGradient></defs>' +
      '<circle cx="160" cy="120" r="96" fill="none" stroke="#39442f" stroke-width="1"/>' +
      '<ellipse cx="160" cy="120" rx="96" ry="34" fill="none" stroke="#39442f" stroke-width="1"/>' +
      '<ellipse cx="160" cy="120" rx="34" ry="96" fill="none" stroke="#39442f" stroke-width="1"/>' +
      '<ellipse cx="160" cy="120" rx="72" ry="88" fill="none" stroke="#2f3827" stroke-width="1" transform="rotate(24 160 120)"/>' +
      STAGES.map(function (stage, index) {
        var x = 54 + index * 53, y = 120 + (index % 2 ? -34 : 30);
        return '<circle cx="' + x + '" cy="' + y + '" r="9" fill="none" stroke="#8CA650" stroke-width="1.4"/>' +
               '<circle cx="' + x + '" cy="' + y + '" r="3.4" fill="#D5F268"/>' +
               '<title>' + stage.label + '</title>';
      }).join('') +
      '<circle cx="160" cy="120" r="34" fill="url(#rmCore)"/><circle cx="160" cy="120" r="11" fill="#D5F268"/>' +
      '<path d="M262 78 L292 60" stroke="#D5F268" stroke-width="1.6" stroke-dasharray="4 5"/>' +
      '<text x="160" y="228" text-anchor="middle" fill="#8CA650" font-size="10" font-family="Manrope,DM Sans,sans-serif">PIPELINE</text>';
    return svg;
  }

  function mount(host) {
    if (!host) return null;
    host.innerHTML = '';
    host.appendChild(poster());
    if (reduce || !host.getContext && !document.createElement('canvas').getContext) {
      host.setAttribute('data-tier', 'poster');
      return { setState: function () {}, destroy: function () {} };
    }
    var canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%';
    host.style.position = 'relative';
    var backdrop = host.firstChild;
    if (backdrop) backdrop.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;opacity:.35';
    host.appendChild(canvas);
    host.setAttribute('data-tier', 'lite');

    var ctx = canvas.getContext('2d');
    var dpr = Math.min(root.devicePixelRatio || 1, 2);
    var width = 0, height = 0, raf = null, visible = true;
    var state = { stage: 0, running: false, counters: {} };
    var pulses = [], t0 = performance.now();

    function resize() {
      width = host.clientWidth || 320;
      height = host.clientHeight || 240;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function ringPoints() {
      var cx = width / 2, cy = height / 2, r = Math.min(width, height) * 0.36, pts = [];
      STAGES.forEach(function (stage, index) {
        var angle = (-Math.PI / 2) + (index / STAGES.length) * Math.PI * 2 + t0 * 0;
        pts.push({ x: cx + Math.cos(angle) * r * 1.12, y: cy + Math.sin(angle) * r * 0.92, label: stage.label });
      });
      return pts;
    }
    function spawn(progress) {
      var pts = ringPoints();
      var from = pts[Math.min(4, Math.floor(progress * pts.length))];
      pulses.push({ p: 0, from: from, active: true });
      if (pulses.length > 26) pulses.shift();
    }
    var lastSpawn = 0;
    function frame(time) {
      raf = null;
      if (!visible) return;
      var cx = width / 2, cy = height / 2, r = Math.min(width, height) * 0.36;
      ctx.clearRect(0, 0, width, height);
      var t = (time - t0) / 1000;
      // shell
      ctx.lineWidth = 1;
      for (var i = 0; i < 3; i++) {
        ctx.strokeStyle = 'rgba(140,166,80,' + (0.34 - i * 0.08) + ')';
        ctx.beginPath();
        ctx.ellipse(cx, cy, r * (1.28 - i * 0.06), r * (0.62 + i * 0.16), (i * Math.PI) / 5 + t * 0.04, 0, Math.PI * 2);
        ctx.stroke();
      }
      // stage rings
      var pts = ringPoints();
      ctx.strokeStyle = 'rgba(213,242,104,.22)';
      pts.forEach(function (pt) {
        ctx.beginPath();
        ctx.moveTo(pt.x, pt.y);
        ctx.lineTo(cx, cy);
        ctx.stroke();
      });
      if (state.running && time - lastSpawn > 260) { spawn(state.stage / 5); lastSpawn = time; }
      // pulses ride inward, then hop closer, then absorb
      ctx.lineWidth = 2.2;
      for (var p = pulses.length - 1; p >= 0; p--) {
        var pulse = pulses[p];
        pulse.p += 0.014;
        if (pulse.p >= 1) { pulses.splice(p, 1); continue; }
        var ease = pulse.p * pulse.p;
        var x = pulse.from.x + (cx - pulse.from.x) * ease;
        var y = pulse.from.y + (cy - pulse.from.y) * ease;
        ctx.strokeStyle = 'rgba(213,242,104,' + (0.85 - ease * 0.4) + ')';
        ctx.beginPath();
        ctx.moveTo(pulse.from.x + (cx - pulse.from.x) * Math.max(0, ease - 0.08), pulse.from.y + (cy - pulse.from.y) * Math.max(0, ease - 0.08));
        ctx.lineTo(x, y);
        ctx.stroke();
      }
      // nodes, lit in order as the crew advances
      pts.forEach(function (pt, index) {
        var active = index <= state.stage - 1 || (state.running && index === state.stage);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, active ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = active ? '#D5F268' : 'rgba(140,166,80,.5)';
        ctx.fill();
      });
      // core with a slow breathing flare
      var breathe = 0.72 + Math.sin(t * 1.6) * 0.08 + (state.running ? 0.12 : 0);
      var grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, r * 0.55);
      grad.addColorStop(0, 'rgba(213,242,104,' + breathe + ')');
      grad.addColorStop(1, 'rgba(140,166,80,0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, r * 0.55, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cx, cy, 8, 0, Math.PI * 2);
      ctx.fillStyle = '#F5F5EF';
      ctx.fill();
      raf = root.requestAnimationFrame(frame);
    }
    function start() { if (!raf && visible) raf = root.requestAnimationFrame(frame); }
    function stop() { if (raf) { root.cancelAnimationFrame(raf); raf = null; } }

    resize();
    start();
    var observer = root.ResizeObserver ? new root.ResizeObserver(resize) : null;
    if (observer) observer.observe(host);
    var io = root.IntersectionObserver ? new root.IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting && !document.hidden;
      visible ? start() : stop();
    }, { threshold: 0.05 }) : null;
    if (io) io.observe(host);
    document.addEventListener('visibilitychange', function () {
      visible = !document.hidden;
      visible ? start() : stop();
    });

    return {
      setState: function (next) {
        state = Object.assign(state, next || {});
      },
      destroy: function () {
        stop();
        if (io) io.disconnect();
        if (observer) observer.disconnect();
      },
      tier: 'lite'
    };
  }

  root.ReachmarkCrewOrb = { mount: mount, stages: STAGES, reduceMotion: !!reduce };
})(window);
