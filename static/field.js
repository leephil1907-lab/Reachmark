/* Reachmark dark field — one WebGL layer under the page.
   Book-of-shaders / Shadertoy language, no Three.js, never covers type. */
(function () {
  'use strict';
  var canvas, gl, prog, uTime, uRes, buf, raf = 0, t0 = 0, reduced = false;

  var VERT = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.0,1.0);}';
  var FRAG = [
    'precision mediump float;',
    'uniform vec2 u_res;uniform float u_time;',
    'void main(){',
    '  vec2 uv=gl_FragCoord.xy/u_res;',
    '  float aspect=u_res.x/max(u_res.y,1.0);',
    '  vec2 p=vec2(uv.x*aspect,uv.y);',
    '  float t=u_time*0.065;',
    '  vec2 a=p-vec2(0.28+0.10*sin(t),0.78+0.07*cos(t*0.8));',
    '  vec2 b=p-vec2(aspect*0.92+0.08*cos(t*0.7),0.28+0.09*sin(t*0.9));',
    '  vec2 c=p-vec2(aspect*0.45,0.02+0.06*sin(t*0.5));',
    '  float g1=exp(-dot(a,a)*3.2);',
    '  float g2=exp(-dot(b,b)*2.6);',
    '  float g3=exp(-dot(c,c)*1.8);',
    '  vec3 charcoal=vec3(0.039,0.047,0.043);',
    '  vec3 lime=vec3(0.835,0.949,0.408);',
    '  vec3 forest=vec3(0.125,0.145,0.078);',
    '  vec3 col=charcoal+lime*(g1*0.26+g3*0.10)+forest*(g2*0.38);',
    '  vec2 q=uv-0.5; col*=1.0-dot(q,q)*0.55;',
    '  float grain=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233))+u_time)*43758.5453);',
    '  col+=(grain-0.5)*0.025;',
    '  gl_FragColor=vec4(col,1.0);',
    '}'
  ].join('');

  function compile(type, src) {
    var sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    return sh;
  }

  function resize() {
    if (!canvas || !gl) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    var w = Math.max(1, Math.floor(window.innerWidth * dpr * 0.6));
    var h = Math.max(1, Math.floor(window.innerHeight * dpr * 0.6));
    if (canvas.width === w && canvas.height === h) return;
    canvas.width = w;
    canvas.height = h;
    gl.viewport(0, 0, w, h);
    gl.uniform2f(uRes, w, h);
  }

  function frame(now) {
    raf = 0;
    if (!gl) return;
    if (!t0) t0 = now;
    gl.uniform1f(uTime, (now - t0) * 0.001);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!reduced && isDark()) raf = requestAnimationFrame(frame);
  }

  function isDark() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  }

  function play() {
    if (!gl || raf) return;
    if (reduced) {
      resize();
      gl.uniform1f(uTime, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      return;
    }
    raf = requestAnimationFrame(frame);
  }

  function pause() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }

  function sync() {
    if (isDark()) play();
    else pause();
  }

  function boot() {
    var host = document.querySelector('.x-depth');
    canvas = document.getElementById('x-field') || (host && host.querySelector('canvas'));
    if (!host || !canvas) return;
    reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, stencil: false, premultipliedAlpha: false });
    if (!gl) return;
    prog = gl.createProgram();
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.bindAttribLocation(prog, 0, 'a');
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { gl = null; return; }
    gl.useProgram(prog);
    uTime = gl.getUniformLocation(prog, 'u_time');
    uRes = gl.getUniformLocation(prog, 'u_res');
    buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    host.classList.add('live');
    resize();
    window.addEventListener('resize', function () {
      resize();
      if (isDark() && !raf) {
        gl.uniform1f(uTime, t0 ? (performance.now() - t0) * 0.001 : 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    }, { passive: true });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) pause();
      else sync();
    });
    new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    sync();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
