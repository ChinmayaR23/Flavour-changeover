"""Dashboard hero: a 3D drink can drawn with CSS transforms (no image).

Rendered with streamlit.components.v1.html. Move the pointer to tilt it,
click to spin it. Respects prefers-reduced-motion.
"""
from __future__ import annotations

import html
import json

TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Space+Grotesk:wght@700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box} html,body{margin:0;background:transparent;font-family:Inter,system-ui,sans-serif}
.hero{position:relative;overflow:hidden;border-radius:24px;padding:32px 36px;color:#fff;display:flex;flex-wrap:wrap;align-items:center;gap:16px;
  background:radial-gradient(circle at 78% 46%, __SOFT__ 0%, rgba(11,18,32,0) 55%), linear-gradient(160deg,#111B2E 0%,#0B1220 60%);min-height:396px}
.text{flex:1 1 340px;min-width:0;display:flex;flex-direction:column;gap:18px}
.eyebrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.live{width:8px;height:8px;border-radius:50%;background:#34D399;animation:pulse 2s ease-in-out infinite}
.ey{font-size:12px;font-weight:700;letter-spacing:.12em;color:#C9D3E1}
.sample{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:999px;background:rgba(251,191,36,.14);color:#FCD34D;font-size:12px;font-weight:600}
h1{margin:0;font-family:'Space Grotesk',Inter,sans-serif;font-size:44px;line-height:50px;letter-spacing:-.01em}
h1 span{color:__HI__}
p{margin:0;font-size:16px;line-height:24px;color:#B7C2D3;max-width:460px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;max-width:480px}
.tile{padding:14px 16px;border-radius:14px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)}
.tile small{display:block;font-size:12px;color:#A9B5C8}.tile b{display:block;margin-top:4px;font-size:18px}
.tile i{font-style:normal;font-size:13px;font-weight:500;color:#A9B5C8}
.scene{position:relative;flex:1 1 300px;min-height:360px;border:0;padding:0;background:transparent;cursor:pointer;perspective:900px;perspective-origin:50% 40%;color:inherit;font:inherit}
.scene:focus-visible{outline:2px solid #93C5FD;outline-offset:4px;border-radius:16px}
.stage{position:absolute;left:50%;top:47%;width:0;height:0;transform-style:preserve-3d;transition:transform .25s ease-out}
.p3{position:absolute;left:0;top:0;transform-style:preserve-3d}
.bob{animation:bob 4.5s ease-in-out infinite}
.can{transition:transform 1.2s cubic-bezier(.2,.8,.2,1)}
.face{position:absolute;left:-8.7px;top:-115px;width:17.4px;height:230px;backface-visibility:hidden}
.cap{position:absolute;left:-64px;width:128px;height:128px;border-radius:50%}
.label{position:absolute;left:-27px;top:-92px;width:54px;height:184px;display:flex;align-items:center;justify-content:center;backface-visibility:hidden;
  transform:translateZ(65px) rotate(180deg);writing-mode:vertical-rl;font-family:'Space Grotesk',Inter,sans-serif;font-size:40px;font-weight:700;letter-spacing:.08em;color:__LABEL__}
.cube{transition:transform .6s cubic-bezier(.2,.8,.2,1)}
.spin{animation:cubespin linear infinite}
.cf{position:absolute;left:-20px;top:-20px;width:40px;height:40px;border-radius:6px;background:rgba(214,236,255,.28);border:1px solid rgba(255,255,255,.7);box-shadow:inset 0 0 14px rgba(255,255,255,.55)}
.bub{border-radius:50%;border:1.5px solid rgba(255,255,255,.75);background:radial-gradient(circle at 30% 30%,rgba(255,255,255,.9),rgba(255,255,255,.08) 60%);animation:rise ease-in infinite}
.hint{position:absolute;left:0;right:0;bottom:4px;text-align:center;font-size:13px;color:#94A0B4}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
@keyframes cubespin{from{transform:rotateX(0) rotateY(0)}to{transform:rotateX(360deg) rotateY(360deg)}}
@keyframes rise{0%{transform:translateY(0) scale(.6);opacity:0}15%{opacity:.95}100%{transform:translateY(-270px) scale(1.1);opacity:0}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}50%{box-shadow:0 0 0 6px rgba(52,211,153,0)}}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<section class="hero" aria-label="Line status">
  <div class="text">
    <div class="eyebrow"><span class="live"></span><span class="ey">__LINE__ · LIVE</span>__SAMPLE__</div>
    <div style="display:flex;flex-direction:column;gap:10px">
      <h1>Now running <span>__NAME__</span></h1>
      <p>__NEXT_TEXT__</p>
    </div>
    <div class="tiles">
      <div class="tile"><small>Next changeover</small><b>__NEXT_PAIR__</b></div>
      <div class="tile"><small>Line-stop with plan</small><b>__PLANNED__ <i>__USUAL__</i></b></div>
    </div>
  </div>
  <button class="scene" id="scene" type="button" aria-label="3D __NAME__ can. Move the pointer over it to tilt, click to spin.">
    <div class="stage" id="stage">
      <div style="position:absolute;left:-210px;top:-210px;width:420px;height:420px;border-radius:50%;background:radial-gradient(circle,__GLOW__ 0%,rgba(0,0,0,0) 62%);transform:translateZ(-170px) scale(1.4)"></div>
      <div style="position:absolute;left:-100px;top:128px;width:200px;height:36px;border-radius:50%;background:radial-gradient(ellipse,rgba(0,0,0,.6) 0%,rgba(0,0,0,0) 70%);transform:translateZ(-30px)"></div>
      <div class="p3 bob"><div class="p3 can" id="can">
        <div id="faces"></div>
        <div class="cap" style="top:-179px;transform:rotateX(90deg);background:radial-gradient(circle,#CDD3DA 0%,#CDD3DA 36%,#8B939D 38%,#8B939D 41%,#EEF1F4 43%,#D3D9DF 68%,#8E97A1 71%,#8E97A1 75%,#F1F3F6 78%,#B5BDC6 100%)"><div style="position:absolute;left:50px;top:30px;width:28px;height:40px;border-radius:12px;border:3px solid #A7B0BA;background:#DDE2E7"></div></div>
        <div class="cap" style="top:51px;transform:rotateX(-90deg);background:radial-gradient(circle,#7C858F 0%,#A9B1BA 60%,#6C747D 100%)"></div>
        <div class="label">__UPPER__</div>
      </div></div>
      <div id="extras"></div>
    </div>
    <span class="hint">Move your pointer to tilt · click to spin</span>
  </button>
</section>
<script>
const C = __COLOURS__;
const N = 24;
let rx = -14, ry = -22, hov = false, spin = 0;
const facesEl = document.getElementById('faces'), stage = document.getElementById('stage'), can = document.getElementById('can');
const faces = [];
const drop = (x, y) => 'radial-gradient(circle at ' + x + '% ' + y + '%, rgba(255,255,255,.9) 0, rgba(255,255,255,.35) 1.5px, rgba(255,255,255,0) 3px)';
const band = 'linear-gradient(180deg,#E9EDF1 0%,#9AA3AD 2.5%,#F4F6F8 4.5%,#B9C1CA 6%,' + C.c + ' 7.5%,' + C.c + ' 70%,' + C.light + ' 70%,' + C.light + ' 74%,' + C.c + ' 74%,' + C.c + ' 92.5%,#B9C1CA 94%,#F4F6F8 95.5%,#9AA3AD 97.5%,#E9EDF1 100%)';
for (let i = 0; i < N; i++) {
  const f = document.createElement('div');
  f.className = 'face';
  const a = i * 360 / N;
  f.style.transform = 'rotateY(' + a + 'deg) translateZ(64px)';
  f.style.background = [drop(50, (i*37)%80+10), drop(30, (i*53)%70+15), drop(70, (i*71)%60+25), band].join(',');
  facesEl.appendChild(f); faces.push([f, a]);
}
const extras = document.getElementById('extras');
const cubes = [[-150, 40, 70, 14], [140, -40, 100, 18], [120, 150, -70, 22]].map(([x, y, z, d]) => {
  const w = document.createElement('div'); w.className = 'p3 cube';
  const s = document.createElement('div'); s.className = 'p3 spin'; s.style.animationDuration = d + 's';
  ['translateZ(20px)','rotateY(180deg) translateZ(20px)','rotateY(90deg) translateZ(20px)','rotateY(-90deg) translateZ(20px)','rotateX(90deg) translateZ(20px)','rotateX(-90deg) translateZ(20px)']
    .forEach(t => { const f = document.createElement('div'); f.className = 'cf'; f.style.transform = t; s.appendChild(f); });
  w.appendChild(s); extras.appendChild(w); return [w, x, y, z];
});
[[-95,40,8,5.5,0],[-70,-60,6,6.5,1.2],[-110,20,10,7,2.6],[90,50,7,6,.6],[105,-40,9,7.5,1.9],[75,10,5,5,3.1],[-40,90,6,6.8,3.8],[45,95,8,6.2,4.4],[0,-90,7,7.2,2.2],[-130,-20,5,5.8,4.9]]
  .forEach(([x, z, size, dur, delay]) => {
    const w = document.createElement('div'); w.className = 'p3'; w.style.transform = 'translate3d(' + x + 'px,110px,' + z + 'px)';
    const b = document.createElement('div'); b.className = 'bub';
    Object.assign(b.style, {width: size + 'px', height: size + 'px', animationDuration: dur + 's', animationDelay: delay + 's'});
    w.appendChild(b); extras.appendChild(w);
  });
function draw() {
  stage.style.transform = 'rotateX(' + rx + 'deg) rotateY(' + ry + 'deg) translateZ(' + (hov ? 40 : 0) + 'px)';
  can.style.transform = 'rotateY(' + spin + 'deg)';
  for (const [f, a] of faces) {
    const d = Math.max(0, Math.cos((a + ry + 30) * Math.PI / 180));
    f.style.filter = 'brightness(' + (0.5 + 0.55 * d + 0.5 * Math.pow(d, 24)).toFixed(3) + ')';
  }
  const k = hov ? 1.18 : 1;
  for (const [w, x, y, z] of cubes) w.style.transform = 'translate3d(' + x * k + 'px,' + y * k + 'px,' + (z + (hov ? 30 : 0)) + 'px)';
}
const scene = document.getElementById('scene');
scene.addEventListener('mousemove', e => {
  const r = scene.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
  rx = -14 - (y - 0.5) * 28; ry = (x - 0.5) * 70; hov = true; requestAnimationFrame(draw);
});
scene.addEventListener('mouseleave', () => { rx = -14; ry = -22; hov = false; requestAnimationFrame(draw); });
scene.addEventListener('click', () => { spin += 360; draw(); });
draw();
</script></body></html>"""


def render(name: str, colours: tuple[str, str, str, str], line: str, next_text: str,
           next_pair: str, planned: str, usual: str, sample: bool) -> str:
    c, light, label, hi = colours
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    rep = {
        "__COLOURS__": json.dumps({"c": c, "light": light}),
        "__SOFT__": f"rgba({r},{g},{b},0.22)",
        "__GLOW__": f"rgba({max(r, 120)},{max(g, 60)},{max(b, 40)},0.55)",
        "__HI__": hi, "__LABEL__": label,
        "__LINE__": html.escape(line.upper()),
        "__SAMPLE__": '<span class="sample">Sample data</span>' if sample else "",
        "__NAME__": html.escape(name), "__UPPER__": html.escape(name.upper()),
        "__NEXT_TEXT__": html.escape(next_text), "__NEXT_PAIR__": html.escape(next_pair),
        "__PLANNED__": html.escape(planned), "__USUAL__": html.escape(usual),
    }
    out = TEMPLATE
    for k, v in rep.items():
        out = out.replace(k, v)
    return out
