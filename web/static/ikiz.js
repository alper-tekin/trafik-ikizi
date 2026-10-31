// Karşılaştırma bölümü: kavşak ikizinin iki sinyal planıyla yan yana oynatılması.
// Yollar, şeritler ve sinyal bağlantıları SUMO ağından (sim_ag.json) gelir; araçlar
// 2 Hz kayıttan çizilir, aradaki konumlar doğrusal kestirimle bulunur.
// Kullandığı küreseller (index.html): $, SIM_A, SIM_B, AG, Chart.

const SIG = { G: '#3fdc6a', g: '#2f9e55', y: '#f2b531', r: '#ef4444', s: '#ef4444', o: '#555' };
const BODY = { K: '#7aa2ff', G: '#f0c674', D: '#b5e48c', B: '#ff9ecb' };
const VIEW_M = 64;  // kavşak merkezinden her yöne gösterilen mesafe (m)

function phaseColor(ad) {
  if (ad.startsWith('Southbound left')) return '#f0b429';
  if (ad.startsWith('Southbound through')) return '#58a6ff';
  if (ad.startsWith('Lankershim')) return '#3fb950';
  if (ad === 'Cross street') return '#bc8cff';
  if (ad === 'Yellow') return '#d29922';
  return '#444c56';
}

function cycleOf(sim) { return sim.sinyal.reduce((a, f) => a + f.sure, 0); }

// SUMO döngüsü simülasyon saniyesi 0'da başlar; kayıt ısınmadan ve pencere başından sonra.
function phaseAt(sim, t) {
  const C = cycleOf(sim), x0 = (sim.isinma_s + sim.baslangic_s + t) % C;
  let x = x0;
  for (const f of sim.sinyal) { if (x < f.sure) return { f, kalan: f.sure - x, x: x0 }; x -= f.sure; }
  return { f: sim.sinyal[0], kalan: 0, x: x0 };
}

function frameMap(sim) {
  if (!sim._fr) {
    sim._fr = Object.keys(sim.kareler).map(Number).sort((a, b) => a - b).map(k => {
      const m = new Map();
      for (const v of sim.kareler[k.toFixed(1)]) m.set(v[0], v);
      return m;
    });
  }
  return sim._fr;
}

// v: [id, u, w, hız, açı]
function vehiclesAt(sim, t) {
  const fr = frameMap(sim), i = Math.min(Math.floor(t * 2), fr.length - 1);
  const a = fr[i], b = fr[Math.min(i + 1, fr.length - 1)], f = Math.min(1, t * 2 - i), out = [];
  for (const [id, va] of a) {
    const vb = b.get(id);
    if (!vb) { out.push(va); continue; }
    const da = ((vb[4] - va[4] + 540) % 360) - 180;
    out.push([id, va[1] + (vb[1] - va[1]) * f, va[2] + (vb[2] - va[2]) * f, va[3] + (vb[3] - va[3]) * f, va[4] + da * f]);
  }
  return out;
}

function setupCanvas(cv) {
  const dpr = window.devicePixelRatio || 1, px = Math.round(cv.clientWidth * dpr);
  if (cv.width !== px) { cv.width = px; cv.height = px; }
  return { ctx: cv.getContext('2d'), size: px, k: px / cv.clientWidth };
}

function laneDir(sh) {
  const a = sh[0], b = sh[sh.length - 1], du = b[0] - a[0], dw = b[1] - a[1], L = Math.hypot(du, dw);
  return [du / L, dw / L];
}

function polyline(ctx, P, pts, width, color, dash) {
  ctx.beginPath();
  pts.forEach(([u, w], i) => { const [x, y] = P(u, w); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.lineWidth = width; ctx.strokeStyle = color; ctx.setLineDash(dash || []); ctx.stroke(); ctx.setLineDash([]);
}

// Ağ her plan ve her kare için aynı; bir kez ayrı bir tuvale çizilip kopyalanır.
let netCache = null;
function networkImage(size) {
  if (netCache && netCache.width === size) return netCache;
  const c = document.createElement('canvas'); c.width = c.height = size;
  const ctx = c.getContext('2d'), S = size / (2 * VIEW_M), P = (u, w) => [size / 2 + w * S, size / 2 - u * S];
  ctx.fillStyle = '#0d1410'; ctx.fillRect(0, 0, size, size);
  const lanes = AG.seritler;
  ctx.lineCap = 'butt';
  for (const l of lanes) polyline(ctx, P, l.sekil, (l.genislik + 1.8) * S, '#3a434e');  // kaldırım
  for (const l of lanes) polyline(ctx, P, l.sekil, l.genislik * S, '#262b32');          // asfalt
  ctx.beginPath();
  AG.kavsak.forEach(([u, w], i) => { const [x, y] = P(u, w); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.closePath(); ctx.fillStyle = '#262b32'; ctx.fill();

  // şerit ayırıcıları
  const byEdge = {};
  for (const l of lanes) (byEdge[l.kenar] = byEdge[l.kenar] || []).push(l);
  for (const ls of Object.values(byEdge)) {
    ls.sort((a, b) => a.sira - b.sira);
    for (let i = 0; i + 1 < ls.length; i++) {
      const a = ls[i].sekil, b = ls[i + 1].sekil;
      polyline(ctx, P, a.map((p, j) => [(p[0] + b[j][0]) / 2, (p[1] + b[j][1]) / 2]),
        Math.max(1, 0.15 * S), '#c9d1d999', [2 * S, 2.5 * S]);
    }
  }
  // giriş ve çıkış arasındaki çift sarı çizgi
  for (const kol of ['K', 'G', 'D', 'B']) {
    const gi = byEdge[kol + '_gir'], ci = byEdge[kol + '_cik'];
    if (!gi || !ci) continue;
    const a = gi[gi.length - 1].sekil, b = ci[ci.length - 1].sekil;
    const ga = laneDir(a), off = gi[gi.length - 1].genislik / 2;
    const n = [ga[1], -ga[0]];  // giriş yönünün solu
    for (const d of [0.12, 0.32]) {
      polyline(ctx, P, a.map(p => [p[0] + n[0] * (off + d), p[1] + n[1] * (off + d)]), Math.max(1, 0.12 * S), '#e3b341');
    }
  }
  // yaya geçitleri, durma çizgileri, şerit okları
  for (const l of lanes) {
    const [du, dw] = laneDir(l.sekil), nu = -dw, nw = du;
    const uc = l.giris ? l.sekil[l.sekil.length - 1] : l.sekil[0];
    const bas = l.giris ? 1.0 : -5.0;  // geçit kavşak tarafında, 4 m genişlikte
    for (let k = -1; k <= 1; k += 2) {
      const cu = uc[0] + du * (bas + 2) + nu * k * l.genislik / 4, cw = uc[1] + dw * (bas + 2) + nw * k * l.genislik / 4;
      polyline(ctx, P, [[cu - du * 2, cw - dw * 2], [cu + du * 2, cw + dw * 2]], l.genislik / 2 * S * 0.55, '#d0d7de50');
    }
    if (!l.giris) continue;
    const h = l.genislik / 2;
    polyline(ctx, P, [[uc[0] - du * 0.3 + nu * h, uc[1] - dw * 0.3 + nw * h], [uc[0] - du * 0.3 - nu * h, uc[1] - dw * 0.3 - nw * h]],
      0.45 * S, '#e6edf3');
    drawArrows(ctx, P(uc[0] - du * 9, uc[1] - dw * 9), Math.atan2(-du, dw), l.linkler.map(x => x.yon), S);
  }
  ctx.fillStyle = '#8b949e'; ctx.font = `${Math.round(size / 40)}px system-ui`;
  ctx.fillText('N ↑', size - size / 14, size / 22);
  ctx.fillText('Lankershim Blvd', size / 2 + 26 * S, size / 22);
  ctx.fillText('Universal Hollywood Dr', size / 40, size / 2 - 16 * S);
  netCache = c;
  return c;
}

function drawArrows(ctx, [x, y], ang, dirs, S) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
  ctx.strokeStyle = '#e6edf399'; ctx.lineWidth = Math.max(1, 0.25 * S); ctx.lineCap = 'round';
  const L = 2.2 * S, h = 0.7 * S;
  ctx.beginPath(); ctx.moveTo(-L, 0); ctx.lineTo(0, 0); ctx.stroke();
  for (const d of new Set(dirs)) {
    const [ex, ey] = d === 's' ? [L * 0.8, 0] : d === 'l' ? [0, -L * 0.7] : [0, L * 0.7];
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(ex, ey); ctx.stroke();
    const a = Math.atan2(ey, ex);
    ctx.beginPath();
    ctx.moveTo(ex - h * Math.cos(a - 0.5), ey - h * Math.sin(a - 0.5)); ctx.lineTo(ex, ey);
    ctx.lineTo(ex - h * Math.cos(a + 0.5), ey - h * Math.sin(a + 0.5)); ctx.stroke();
  }
  ctx.restore();
}

function drawSignals(ctx, P, S, state) {
  for (const l of AG.seritler) {
    if (!l.giris || !l.linkler.length) continue;
    const [du, dw] = laneDir(l.sekil), uc = l.sekil[l.sekil.length - 1];
    const [x, y] = P(uc[0] + du * 0.9, uc[1] + dw * 0.9);
    const ana = l.linkler.find(k => k.yon !== 'r') || l.linkler[0], c = state[ana.sira] || 'o';
    const w = l.genislik * S;
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(-du, dw));
    ctx.fillStyle = '#0b0e13'; ctx.fillRect(-0.5 * S, -w * 0.42, 1.0 * S, w * 0.84);
    ctx.shadowColor = SIG[c]; ctx.shadowBlur = (c === 'G' || c === 'y') ? 12 : 4;
    ctx.fillStyle = SIG[c]; ctx.fillRect(-0.32 * S, -w * 0.32, 0.64 * S, w * 0.64);
    ctx.restore();
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

function drawCar(ctx, P, S, v) {
  const [id, u, w, hiz, aciDer] = v, a = aciDer * Math.PI / 180;  // 0 = kuzey, saat yönünde
  const fu = Math.cos(a), fw = Math.sin(a), boy = 4.6, en = 1.9;
  const [x, y] = P(u - fu * boy / 2, w - fw * boy / 2);  // SUMO konumu ön tampondur
  const l = boy * S, wd = en * S;
  ctx.save(); ctx.translate(x, y); ctx.rotate(a - Math.PI / 2);
  ctx.fillStyle = '#00000070'; ctx.fillRect(-l / 2 + 1, -wd / 2 + 1.5, l, wd);
  ctx.fillStyle = BODY[id[0]] || '#c9d1d9'; roundRect(ctx, -l / 2, -wd / 2, l, wd, wd * 0.32); ctx.fill();
  ctx.fillStyle = '#0d1117cc'; ctx.fillRect(l * 0.06, -wd * 0.36, l * 0.17, wd * 0.72);   // ön cam
  ctx.fillStyle = '#0d111788'; ctx.fillRect(-l * 0.36, -wd * 0.34, l * 0.12, wd * 0.68);  // arka cam
  if (hiz < 0.5) {  // duruyor: fren lambaları
    ctx.shadowColor = '#ff3b3b'; ctx.shadowBlur = 10; ctx.fillStyle = '#ff4d4d';
    ctx.fillRect(-l / 2 - 0.6, -wd * 0.46, Math.max(1.5, 0.35 * S), wd * 0.26);
    ctx.fillRect(-l / 2 - 0.6, wd * 0.2, Math.max(1.5, 0.35 * S), wd * 0.26);
  }
  ctx.restore();
}

function stoppedNear(vs) { return vs.filter(v => v[3] < 0.5 && Math.hypot(v[1], v[2]) < 75).length; }

function drawTwin(cv, sim, t) {
  const { ctx, size } = setupCanvas(cv), S = size / (2 * VIEW_M), P = (u, w) => [size / 2 + w * S, size / 2 - u * S];
  ctx.drawImage(networkImage(size), 0, 0);
  const ph = phaseAt(sim, t);
  drawSignals(ctx, P, S, ph.f.durum);
  const vs = vehiclesAt(sim, t);
  for (const v of vs) drawCar(ctx, P, S, v);
  return { ph, stopped: stoppedNear(vs) };
}

function phaseBar(el, sim) {
  const C = cycleOf(sim);
  el.innerHTML = sim.sinyal.map(f =>
    `<span title="${f.ad}: ${f.sure} s" style="width:${f.sure / C * 100}%;background:${phaseColor(f.ad)}"></span>`).join('') + '<i></i>';
}

function simSetup() {
  $('#simAh').textContent = 'Current plan (from video)';
  $('#simBh').textContent = 'Recommended by the agent';
  for (const [k, sim] of [['A', SIM_A], ['B', SIM_B]]) {
    phaseBar($(`#sim${k}bar`), sim);
    const p = sim.plan;
    $(`#sim${k}bar`).title = `left ${p.sol_onde} · SB lead ${p.guney_onde} · shared ${p.ortak} · cross ${p.ara_sokak} s (cycle ${cycleOf(sim)} s)`;
  }
  const seri = sim => frameMap(sim).map(m => stoppedNear([...m.values()]));
  const sA = seri(SIM_A), sB = seri(SIM_B);
  const birikim = s => { let a = 0; return s.map(x => (a += x * 0.5)); };
  const cA = birikim(sA), cB = birikim(sB);
  const max = (sA.length - 1) / 2;
  $('#simT').max = max;
  let t = 0, playing = false, last = 0;

  const playhead = {
    id: 'playhead',
    afterDatasetsDraw(c) {
      const x = c.scales.x.getPixelForValue(t * 2), { top, bottom } = c.chartArea, g = c.ctx;
      g.save(); g.strokeStyle = '#e6edf3'; g.lineWidth = 1; g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.restore();
    },
  };
  const fmt = x => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, '0')}`;
  const chart = new Chart($('#simChart'), {
    type: 'line', plugins: [playhead],
    data: {
      labels: sA.map((_, i) => i),
      datasets: [
        { label: 'Current plan', data: sA, borderColor: '#8b949e', pointRadius: 0, borderWidth: 1.5, tension: 0.3 },
        { label: 'Recommended plan', data: sB, borderColor: '#3fb950', pointRadius: 0, borderWidth: 1.5, tension: 0.3 },
      ],
    },
    options: {
      animation: false, interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 11, callback: v => fmt(v / 2) } },
        y: { beginAtZero: true, title: { display: true, text: 'stopped cars' } },
      },
      onClick: (e, _, c) => { t = Math.max(0, Math.min(max, c.scales.x.getValueForPixel(e.x) / 2)); render(); },
    },
  });

  function render() {
    const a = drawTwin($('#simA'), SIM_A, t), b = drawTwin($('#simB'), SIM_B, t);
    const i = Math.min(Math.round(t * 2), cA.length - 1);
    for (const [k, r, sim] of [['A', a, SIM_A], ['B', b, SIM_B]]) {
      $(`#sim${k}now`).textContent = r.stopped;
      $(`#sim${k}phase`).textContent = `${r.ph.f.ad} · ${Math.ceil(r.ph.kalan)} s`;
      $(`#sim${k}bar i`).style.left = `${r.ph.x / cycleOf(sim) * 100}%`;
    }
    $('#simAcum').textContent = (cA[i] / 60).toFixed(1);
    $('#simBcum').textContent = (cB[i] / 60).toFixed(1);
    $('#simT').value = t;
    $('#simClock').textContent = fmt(t);
    chart.draw();
  }
  $('#simT').oninput = e => { t = +e.target.value; render(); };
  $('#simPlay').onclick = () => {
    playing = !playing; $('#simPlay').textContent = playing ? 'Pause' : 'Play';
    last = performance.now(); if (playing) requestAnimationFrame(tick);
  };
  function tick(now) {
    if (!playing) return;
    t += (now - last) / 1000 * +$('#simSpeed').value; last = now;
    if (t > max) t = 0;
    render(); requestAnimationFrame(tick);
  }
  window.addEventListener('resize', () => { netCache = null; render(); });
  render();
}
