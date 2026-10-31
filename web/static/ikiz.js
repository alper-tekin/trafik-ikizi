// Kavşak çizimi: 1. bölümdeki kuşbakışı (videodaki gerçek izler) ve 4. bölümdeki
// ikiz karşılaştırması aynı motorla çizilir.
//
// Her şey kamera görüntüsünün açısı ve kadrajıyla çizilir: yerdeki her nokta
// (u kuzey, w doğu, metre) kalibrasyondan gelen homografiyle (AG.goruntu.G) video
// pikseline yansıtılır. Şeritler, çizgiler, ışıklar ve arabalar yerde birer çokgen
// olarak tanımlanır, köşeleri yansıtılır; böylece perspektif de videoyla aynıdır.
// Başka bir videonun kalibrasyonuyla çizim kendiliğinden ona hizalanır.
//
// Kullandığı küreseller (index.html): $, OZET, BEV, SIM_A, SIM_B, AG, Chart.

const SIG = { G: '#3fdc6a', g: '#2f9e55', y: '#f2b531', r: '#ef4444', s: '#ef4444', o: '#555' };
const BODY = { K: '#7aa2ff', G: '#f0c674', D: '#b5e48c', B: '#ff9ecb' };
const MOVE_RENK = { 1: '#e6edf3', 2: '#f0b429', 3: '#39c5cf', 0: '#6e7681' };
const SERIT_KIRP_M = 140;  // şeritler bu uzaklıkta kesilir (daha ötesi ufkun arkasına düşebilir)

function phaseColor(ad) {
  if (ad.startsWith('Southbound left')) return '#f0b429';
  if (ad.startsWith('Southbound through')) return '#58a6ff';
  if (ad.startsWith('Lankershim')) return '#3fb950';
  if (ad === 'Cross street') return '#bc8cff';
  if (ad === 'Yellow') return '#d29922';
  return '#444c56';
}

// ---------------------------------------------------------------- görünüm
// W piksel genişliğindeki tuval için yer -> ekran yansıtması.
function gorunum(W) {
  const g = AG.goruntu, G = g.G, k = W / g.genislik, H = Math.round(g.yukseklik * k);
  const P = (u, w) => {
    const z = G[2][0] * u + G[2][1] * w + G[2][2];
    return [(G[0][0] * u + G[0][1] * w + G[0][2]) / z * k, (G[1][0] * u + G[1][1] * w + G[1][2]) / z * k];
  };
  // yerel ölçek (piksel/metre), metin ve çizgi kalınlıkları için
  const olcek = (u, w) => {
    const [x0, y0] = P(u, w), [x1, y1] = P(u + 1, w), [x2, y2] = P(u, w + 1);
    return (Math.hypot(x1 - x0, y1 - y0) + Math.hypot(x2 - x0, y2 - y0)) / 2;
  };
  return { W, H, P, olcek };
}

function setupCanvas(cv) {
  const dpr = window.devicePixelRatio || 1, W = Math.round(cv.clientWidth * dpr);
  const H = Math.round(W * AG.goruntu.yukseklik / AG.goruntu.genislik);
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  return { ctx: cv.getContext('2d'), gr: gorunum(W) };
}

// Yerdeki çokgeni (metre köşeleri) yansıtıp doldur.
function yerCokgen(ctx, gr, kose, renk) {
  ctx.beginPath();
  kose.forEach(([u, w], i) => { const [x, y] = gr.P(u, w); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.closePath(); ctx.fillStyle = renk; ctx.fill();
}

// a'dan b'ye uzanan, genislik metre enli bir yer şeridi.
function bant(ctx, gr, a, b, genislik, renk) {
  const du = b[0] - a[0], dw = b[1] - a[1], L = Math.hypot(du, dw) || 1, h = genislik / 2;
  const nu = -dw / L * h, nw = du / L * h;
  yerCokgen(ctx, gr, [[a[0] + nu, a[1] + nw], [b[0] + nu, b[1] + nw], [b[0] - nu, b[1] - nw], [a[0] - nu, a[1] - nw]], renk);
}

// Kesikli yer çizgisi.
function kesikli(ctx, gr, a, b, genislik, renk, dolu = 3, bos = 4) {
  const du = b[0] - a[0], dw = b[1] - a[1], L = Math.hypot(du, dw);
  for (let s = 0; s < L; s += dolu + bos) {
    const e = Math.min(L, s + dolu);
    bant(ctx, gr, [a[0] + du * s / L, a[1] + dw * s / L], [a[0] + du * e / L, a[1] + dw * e / L], genislik, renk);
  }
}

// Şerit şeklini merkeze SERIT_KIRP_M'den yakın kısma kes; [kavşak ucu, uzak uç].
function kirpilmis(l) {
  const s = l.sekil, a = s[0], b = s[s.length - 1];
  const yakin = Math.hypot(...a) < Math.hypot(...b) ? a : b, uzak = yakin === a ? b : a;
  const du = uzak[0] - yakin[0], dw = uzak[1] - yakin[1], L = Math.hypot(du, dw);
  const m = Math.min(L, SERIT_KIRP_M - Math.hypot(...yakin));
  return [yakin, [yakin[0] + du / L * m, yakin[1] + dw / L * m]];
}

function laneDir(sh) {
  const a = sh[0], b = sh[sh.length - 1], du = b[0] - a[0], dw = b[1] - a[1], L = Math.hypot(du, dw);
  return [du / L, dw / L];
}

// ---------------------------------------------------------------- ağ
// Ağ her kare için aynı; her tuval genişliği için bir kez ayrı tuvale çizilir.
const netCache = new Map();
function networkImage(W) {
  if (netCache.has(W)) return netCache.get(W);
  const gr = gorunum(W), c = document.createElement('canvas');
  c.width = gr.W; c.height = gr.H;
  if (!gr.W || !gr.H) { c.width = c.height = 1; return c; }  // gizli panelde tuval 0 genişlikli
  const ctx = c.getContext('2d'), lanes = AG.seritler;
  ctx.fillStyle = '#0d1410'; ctx.fillRect(0, 0, gr.W, gr.H);

  // Zemin: araçsız yol fotoğrafının SAM 3.1 ile çıkarılmış katmanları (yol, kaldırım, geçit,
  // şerit çizgileri, oklar...), kendi renklerimizle. Çokgenler kameranın piksel düzleminde
  // olduğu için yolun asimetrisi birebir korunur.
  if (window.SAHNE) {
    sahneCiz(ctx, gr);
    yaziVePusula(ctx, gr);
    netCache.set(W, c);
    return c;
  }

  // Fotoğraf yoksa yedek: ağın şematik çizimi.
  for (const l of lanes) { const [a, b] = kirpilmis(l); bant(ctx, gr, a, b, l.genislik + 1.8, '#3a434e'); }  // kaldırım
  for (const l of lanes) { const [a, b] = kirpilmis(l); bant(ctx, gr, a, b, l.genislik + 0.05, '#262b32'); }  // asfalt
  yerCokgen(ctx, gr, AG.kavsak, '#262b32');

  const byEdge = {};
  for (const l of lanes) (byEdge[l.kenar] = byEdge[l.kenar] || []).push(l);
  for (const ls of Object.values(byEdge)) {  // şerit ayırıcıları
    ls.sort((a, b) => a.sira - b.sira);
    for (let i = 0; i + 1 < ls.length; i++) {
      const [a1, b1] = kirpilmis(ls[i]), [a2, b2] = kirpilmis(ls[i + 1]);
      kesikli(ctx, gr, [(a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2], [(b1[0] + b2[0]) / 2, (b1[1] + b2[1]) / 2], 0.15, '#c9d1d999');
    }
  }
  for (const kol of ['K', 'G', 'D', 'B']) {  // giriş ile çıkış arasında çift sarı çizgi
    const gi = byEdge[kol + '_gir'];
    if (!gi || !byEdge[kol + '_cik']) continue;
    const sol = gi[gi.length - 1], [a, b] = kirpilmis(sol), [du, dw] = laneDir(sol.sekil);
    const nu = dw, nw = -du;  // giriş yönünün solu
    for (const d of [sol.genislik / 2 + 0.12, sol.genislik / 2 + 0.32]) {
      bant(ctx, gr, [a[0] + nu * d, a[1] + nw * d], [b[0] + nu * d, b[1] + nw * d], 0.12, '#e3b341');
    }
  }
  for (const l of lanes) {  // yaya geçitleri, durma çizgileri, şerit okları
    const [du, dw] = laneDir(l.sekil), nu = -dw, nw = du;
    const uc = l.giris ? l.sekil[l.sekil.length - 1] : l.sekil[0];
    const ic = l.giris ? 1 : -1;  // kavşağa doğru yön işareti
    for (let s = -0.4; s <= 0.4; s += 0.27) {
      const cu = uc[0] + du * ic * 0 + nu * s * l.genislik, cw = uc[1] + dw * ic * 0 + nw * s * l.genislik;
      const g0 = l.giris ? 1 : -5, g1 = g0 + 4;
      bant(ctx, gr, [cu + du * g0, cw + dw * g0], [cu + du * g1, cw + dw * g1], l.genislik * 0.14, '#d0d7de55');
    }
    if (!l.giris) continue;
    const h = l.genislik / 2;
    bant(ctx, gr, [uc[0] - du * 0.3 + nu * h, uc[1] - dw * 0.3 + nw * h], [uc[0] - du * 0.3 - nu * h, uc[1] - dw * 0.3 - nw * h], 0.45, '#e6edf3');
    yerOklari(ctx, gr, [uc[0] - du * 9, uc[1] - dw * 9], [du, dw], l.linkler.map(x => x.yon));
  }
  yaziVePusula(ctx, gr);
  netCache.set(W, c);
  return c;
}

// Düzgünleştirilmiş şematik sahne. Geometri SAM katmanlarından (gerçek yol) gelir ama
// titrek maske kenarları çizilmez:
//   - yol: kenarlar sadeleştirilip Chaikin ile yumuşatılır, düz koyu dolgu
//   - şerit ve sarı çizgiler: her parça PCA ile bir doğru parçasına oturtulur, sabit
//     kalınlıkta, yuvarlak uçlu çizilir (kesikli çizgiler kendi kısa parçalarıyla kalır)
//   - yaya geçidi: yönlü sınır kutusu + eşit aralıklı çizgiler
//   - ağaç, bina, doku yok
const SEMA = {
  zemin: '#11151a', kaldirim: '#181d23', yol: '#262b32', kenar: '#3a424c',
  beyaz: 'rgba(214,221,228,0.92)', sari: '#e3b341', gecit: 'rgba(214,221,228,0.85)',
};

// Chaikin köşe kesme: kapalı çokgeni yumuşatır.
function chaikin(p, tur = 2) {
  let q = p;
  for (let t = 0; t < tur; t++) {
    const r = [];
    for (let i = 0; i < q.length; i++) {
      const a = q[i], b = q[(i + 1) % q.length];
      r.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25], [a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
    }
    q = r;
  }
  return q;
}

// Noktaların ana ekseni: merkez, birim yön, eksen boyunca ve ona dik yayılım.
function eksen(p) {
  const n = p.length, mx = p.reduce((a, q) => a + q[0], 0) / n, my = p.reduce((a, q) => a + q[1], 0) / n;
  let sxx = 0, syy = 0, sxy = 0;
  for (const [x, y] of p) { sxx += (x - mx) ** 2; syy += (y - my) ** 2; sxy += (x - mx) * (y - my); }
  const a = 0.5 * Math.atan2(2 * sxy, sxx - syy), ux = Math.cos(a), uy = Math.sin(a);
  let t0 = Infinity, t1 = -Infinity, s0 = Infinity, s1 = -Infinity;
  for (const [x, y] of p) {
    const t = (x - mx) * ux + (y - my) * uy, s = -(x - mx) * uy + (y - my) * ux;
    t0 = Math.min(t0, t); t1 = Math.max(t1, t); s0 = Math.min(s0, s); s1 = Math.max(s1, s);
  }
  return { mx, my, ux, uy, t0, t1, s0, s1 };
}

function cokgenYolu(ctx, p, k) {
  ctx.beginPath();
  p.forEach(([x, y], i) => (i ? ctx.lineTo(x * k, y * k) : ctx.moveTo(x * k, y * k)));
  ctx.closePath();
}

function sahneCiz(ctx, gr) {
  const S = window.SAHNE, k = gr.W / S.genislik, kat = S.katmanlar;
  ctx.fillStyle = SEMA.zemin; ctx.fillRect(0, 0, gr.W, gr.H);

  ctx.fillStyle = SEMA.kaldirim;
  for (const p of kat.kaldirim || []) { cokgenYolu(ctx, chaikin(p), k); ctx.fill(); }
  for (const p of kat.yol || []) {
    cokgenYolu(ctx, chaikin(p, 3), k);
    ctx.fillStyle = SEMA.yol; ctx.fill();
    ctx.strokeStyle = SEMA.kenar; ctx.lineWidth = Math.max(1.5, 1.6 * k); ctx.lineJoin = 'round'; ctx.stroke();
  }

  // Şerit boyası fotoğraftan kopyalanmaz: her kolun ölçülen yönü, şerit merkezleri ve
  // durma çizgisinden zeminde cetvelle çizilir, yol şekline kırpılır. Şerit sayıları ve
  // asimetri gerçek yoldan gelir, çizgiler ise kusursuz düz ve paraleldir.
  ctx.save();
  ctx.beginPath();
  for (const p of kat.yol || []) chaikin(p, 3).forEach(([x, y], i) => (i ? ctx.lineTo(x * k, y * k) : ctx.moveTo(x * k, y * k)));
  ctx.clip();
  for (const g of Object.values(AG.olculen || {})) seritBoyasi(ctx, gr, g);
  ctx.restore();
  for (const p of kat.gecit || []) {  // yaya geçidi: yönlü kutu + eşit aralıklı çizgiler
    const e = eksen(p);
    ctx.strokeStyle = SEMA.gecit; ctx.lineWidth = 2.2 * k; ctx.lineCap = 'butt';
    for (let t = e.t0 + 1.5; t <= e.t1 - 1; t += 4.5) {
      const x = e.mx + e.ux * t, y = e.my + e.uy * t;
      ctx.beginPath();
      ctx.moveTo((x - e.uy * e.s0) * k, (y + e.ux * e.s0) * k);
      ctx.lineTo((x - e.uy * e.s1) * k, (y + e.ux * e.s1) * k);
      ctx.stroke();
    }
  }
}

// Bir kolun yer boyası (metre, kol ekseni e ve ona dik n üzerinde).
function seritBoyasi(ctx, gr, g) {
  const e = g.e, n = g.n, d0 = g.durma_m, d1 = 90;
  const yer = (d, s) => [e[0] * d + n[0] * s, e[1] * d + n[1] * s];
  const kenar = (t, uc) => { const m = g[t].merkez, w = g[t].genislik / 2; return uc < 0 ? Math.min(...m) - w : Math.max(...m) + w; };
  for (const t of ['gelen', 'giden']) {  // aynı yöndeki şeritler arası kesikli beyaz
    const m = [...g[t].merkez].sort((a, b) => a - b);
    for (let i = 0; i + 1 < m.length; i++) {
      const s = (m[i] + m[i + 1]) / 2;
      kesikli(ctx, gr, yer(d0 + 2, s), yer(d1, s), 0.16, SEMA.beyaz, 3, 6);
    }
  }
  // gelen ile giden arası çift sarı (orta refüj ölçülen boşluğun ortasında)
  const gelenUst = Math.max(...g.gelen.merkez) > Math.max(...g.giden.merkez);
  const orta = gelenUst ? (kenar('gelen', -1) + kenar('giden', 1)) / 2 : (kenar('gelen', 1) + kenar('giden', -1)) / 2;
  for (const s of [orta - 0.18, orta + 0.18]) bant(ctx, gr, yer(d0, s), yer(d1, s), 0.14, SEMA.sari);
  // durma çizgisi: gelen şeritlerin tamamı boyunca
  bant(ctx, gr, yer(d0, kenar('gelen', -1)), yer(d0, kenar('gelen', 1)), 0.45, SEMA.beyaz);
}


// Şerit okları yerde çizilir (perspektifle birlikte döner).
function yerOklari(ctx, gr, merkez, [du, dw], dirs) {
  const nu = -dw, nw = du, at = (ileri, yan) => [merkez[0] + du * ileri + nu * yan, merkez[1] + dw * ileri + nw * yan];
  const ok = (a, b) => {
    bant(ctx, gr, a, b, 0.25, '#e6edf399');
    const yu = b[0] - a[0], yw = b[1] - a[1], L = Math.hypot(yu, yw), eu = yu / L, ew = yw / L;
    for (const s of [-1, 1]) bant(ctx, gr, b, [b[0] - eu * 0.8 - ew * s * 0.5, b[1] - ew * 0.8 + eu * s * 0.5], 0.22, '#e6edf399');
  };
  bant(ctx, gr, at(-2.4, 0), at(0, 0), 0.25, '#e6edf399');
  for (const d of new Set(dirs)) {
    if (d === 's') ok(at(0, 0), at(1.8, 0));
    else if (d === 'l') ok(at(0, 0), at(0.3, -1.4));
    else if (d === 'r') ok(at(0, 0), at(0.3, 1.4));
  }
}

function yaziVePusula(ctx, gr) {
  const fs = Math.round(gr.W / 46);
  ctx.font = `${fs}px system-ui`; ctx.fillStyle = '#8b949e'; ctx.textAlign = 'center';
  const yaz = (t, u, w) => { const [x, y] = gr.P(u, w); if (x > 0 && x < gr.W && y > 0 && y < gr.H) ctx.fillText(t, x, y); };
  yaz('Lankershim Blvd', 46, -24);
  yaz('Universal Hollywood Dr', 16, -30);
  // pusula: kuzeyin ekrandaki yönü
  const [x0, y0] = gr.P(0, 0), [x1, y1] = gr.P(10, 0), a = Math.atan2(y1 - y0, x1 - x0);
  const cx = gr.W - fs * 4.2, cy = fs * 3.2, r = fs * 1.3;  // "N" harfi tuvalin içinde kalsın
  ctx.strokeStyle = '#8b949e'; ctx.lineWidth = Math.max(1, fs / 9);
  ctx.beginPath(); ctx.moveTo(cx - Math.cos(a) * r, cy - Math.sin(a) * r); ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  ctx.lineTo(cx + Math.cos(a + 2.6) * r * 0.5 + Math.cos(a) * r * 0.5, cy + Math.sin(a + 2.6) * r * 0.5 + Math.sin(a) * r * 0.5);
  ctx.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  ctx.lineTo(cx + Math.cos(a - 2.6) * r * 0.5 + Math.cos(a) * r * 0.5, cy + Math.sin(a - 2.6) * r * 0.5 + Math.sin(a) * r * 0.5);
  ctx.stroke();
  ctx.fillText('N', cx + Math.cos(a) * r * 1.9, cy + Math.sin(a) * r * 1.9 + fs * 0.35);
  ctx.textAlign = 'start';
}

// ---------------------------------------------------------------- ışıklar ve araçlar
function drawSignals(ctx, gr, state) {
  for (const l of AG.seritler) {
    if (!l.giris || !l.linkler.length) continue;
    const [du, dw] = laneDir(l.sekil), uc = l.sekil[l.sekil.length - 1], nu = -dw, nw = du;
    const ana = l.linkler.find(k => k.yon !== 'r') || l.linkler[0], c = state[ana.sira] || 'o';
    const h = l.genislik * 0.42, m = [uc[0] + du * 0.8, uc[1] + dw * 0.8];
    ctx.save(); ctx.shadowColor = SIG[c]; ctx.shadowBlur = (c === 'G' || c === 'y') ? 12 : 4;
    bant(ctx, gr, [m[0] + nu * h, m[1] + nw * h], [m[0] - nu * h, m[1] - nw * h], 0.9, SIG[c]);
    ctx.restore();
  }
}

// Sade araç: geldiği kola göre düz renk, koyu camlar, hafif gölge; dururken fren lambası.
// v: [id, u, w, hız, açı]. onTampon: konum ön tampon mu (SUMO) yoksa aracın ortası mı (video izi).
function drawCar(ctx, gr, v, renk, onTampon = true) {
  const [id, u, w, hiz, aciDer] = v, a = aciDer * Math.PI / 180;  // 0 = kuzey, saat yönünde
  const fu = Math.cos(a), fw = Math.sin(a), su = -fw, sw = fu, boy = 4.6, en = 1.9;
  const geri = onTampon ? boy / 2 : 0, cu = u - fu * geri, cw = w - fw * geri;
  const p = (i, y) => [cu + fu * i + su * y, cw + fw * i + sw * y];
  const kutu = (i0, i1, y0, y1) => [p(i0, y0), p(i1, y0), p(i1, y1), p(i0, y1)];
  ctx.save(); ctx.translate(1, 1.5); yerCokgen(ctx, gr, kutu(-boy / 2, boy / 2, -en / 2, en / 2), 'rgba(0,0,0,0.4)'); ctx.restore();
  yerCokgen(ctx, gr, kutu(-boy / 2, boy / 2, -en / 2, en / 2), renk || BODY[String(id)[0]] || '#c9d1d9');
  yerCokgen(ctx, gr, kutu(boy * 0.08, boy * 0.26, -en * 0.38, en * 0.38), 'rgba(13,17,23,0.8)');     // ön cam
  yerCokgen(ctx, gr, kutu(-boy * 0.36, -boy * 0.24, -en * 0.36, en * 0.36), 'rgba(13,17,23,0.6)');  // arka cam
  if (hiz < 0.5) {
    ctx.save(); ctx.shadowColor = '#ff3b3b'; ctx.shadowBlur = 8;
    yerCokgen(ctx, gr, kutu(-boy / 2 - 0.1, -boy / 2 + 0.25, -en * 0.46, -en * 0.2), '#ff4d4d');
    yerCokgen(ctx, gr, kutu(-boy / 2 - 0.1, -boy / 2 + 0.25, en * 0.2, en * 0.46), '#ff4d4d');
    ctx.restore();
  }
}


// Her kolun gelen şeritlerinin yanına o kolun ortalama beklemesi (10 tohum, tüm simülasyon).
// Kol yönü (e) ve gelen şeritlerin tarafı (yan): etiket kolun ekseninden 'yan' kadar
// açıkta, kavşaktan uzaktan başlayıp kadrajın içine girene kadar yaklaştırılarak konur.
const ARM_LABEL = { K: { e: [1, 0], yan: [0, -18] }, G: { e: [-1, 0], yan: [0, 20] },
                    D: { e: [0, 1], yan: [24, 0] }, B: { e: [0, -1], yan: [-24, 0] } };
const KOL_ADI_KISA = { K: 'from north', G: 'from south', D: 'from east', B: 'from west' };
function armLabels(ctx, gr, bekleme) {
  const fs = Math.round(gr.W / 36), yariG = fs * 3.6, yariY = fs * 1.5;
  ctx.textAlign = 'center';
  for (const [kol, s] of Object.entries(bekleme)) {
    const { e, yan } = ARM_LABEL[kol];
    let x, y;
    for (let d = 60; d >= 18; d -= 2) {
      [x, y] = gr.P(e[0] * d + yan[0], e[1] * d + yan[1]);
      if (x > yariG && x < gr.W - yariG && y > yariY && y < gr.H - yariY) break;
    }
    x = Math.min(Math.max(x, yariG), gr.W - yariG); y = Math.min(Math.max(y, yariY), gr.H - yariY);
    ctx.fillStyle = '#0d1117e0'; roundRect(ctx, x - yariG, y - fs * 1.35, yariG * 2, fs * 2.55, fs * 0.4); ctx.fill();
    ctx.fillStyle = '#e6edf3'; ctx.font = `600 ${fs}px system-ui`; ctx.fillText(`${s.toFixed(1)} s`, x, y);
    ctx.fillStyle = '#8b949e'; ctx.font = `${Math.round(fs * 0.72)}px system-ui`;
    ctx.fillText(`avg wait ${KOL_ADI_KISA[kol]}`, x, y + fs * 0.95);
  }
  ctx.textAlign = 'start';
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// ---------------------------------------------------------------- ikiz oynatma verisi
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

// v: [id, u, w, hız, açı]; 2 Hz kareler arasında doğrusal kestirim
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

function stoppedNear(vs) { return vs.filter(v => v[3] < 0.5 && Math.hypot(v[1], v[2]) < 75).length; }

function drawTwin(cv, sim, t) {
  const { ctx, gr } = setupCanvas(cv);
  ctx.drawImage(networkImage(gr.W), 0, 0);
  const ph = phaseAt(sim, t);
  drawSignals(ctx, gr, ph.f.durum);
  const vs = vehiclesAt(sim, t);
  for (const v of vs) drawCar(ctx, gr, v);
  if (sim._bekleme) armLabels(ctx, gr, sim._bekleme);
  return { ph, stopped: stoppedNear(vs) };
}

// ---------------------------------------------------------------- 1. bölüm: videodaki gerçek izler
function bevStart() {
  const cv = $('#bev'), video = $('#video');
  // BEV.kareler: 10 fps kare no (çift) -> [[iz, u, w, yön, hareket], ...]; 5 fps
  const kareler = [];
  for (const [k, liste] of Object.entries(BEV.kareler)) {
    const m = new Map();
    for (const [id, u, w, , h] of liste) m.set(id, [u, w, h]);
    kareler[+k / 2] = m;
  }
  const yon = new Map();  // iz -> son güvenilir açı (duran araç titremesin)
  const sinyal = SIM_A.sinyal, C = cycleOf(SIM_A);
  const faz0 = OZET.sinyal.faz0_video_s, solBas = OZET.sinyal.bizim.guneye_sol.baslangic_s;

  function aracDurumu(i, id) {
    const p = kareler[i]?.get(id);
    if (!p) return null;
    const ileri = kareler[i + 2]?.get(id) || kareler[i + 1]?.get(id) || p;
    const geri = kareler[i - 2]?.get(id) || kareler[i - 1]?.get(id) || p;
    const du = ileri[0] - geri[0], dw = ileri[1] - geri[1], yol = Math.hypot(du, dw);
    if (yol > 0.6) yon.set(id, Math.atan2(dw, du) * 180 / Math.PI);
    const varsayilan = Math.abs(p[1]) > Math.abs(p[0]) ? (p[1] > 0 ? 270 : 90) : (p[0] > 0 ? 180 : 0);
    return { u: p[0], w: p[1], h: p[2], hiz: yol / 0.8, aci: yon.get(id) ?? varsayilan };
  }

  function draw() {
    const t = video.currentTime, f = t * 5, i = Math.floor(f), k = f - i;
    const { ctx, gr } = setupCanvas(cv);
    ctx.drawImage(networkImage(gr.W), 0, 0);
    // videodan çıkarılan sinyal planı: SUMO döngüsü önden-sol fazıyla başlar
    let x = (((t - faz0 - solBas) % C) + C) % C, faz = sinyal[0];
    for (const s of sinyal) { if (x < s.sure) { faz = s; break; } x -= s.sure; }
    drawSignals(ctx, gr, faz.durum);
    const simdi = kareler[i] || new Map();
    for (const id of simdi.keys()) {
      const a = aracDurumu(i, id);
      if (!a) continue;
      const b = aracDurumu(i + 1, id) || a, da = ((b.aci - a.aci + 540) % 360) - 180;
      drawCar(ctx, gr, [id, a.u + (b.u - a.u) * k, a.w + (b.w - a.w) * k, a.hiz, a.aci + da * k], MOVE_RENK[a.h], false);
    }
    ctx.fillStyle = '#8b949e'; ctx.font = `${Math.round(gr.W / 46)}px system-ui`;
    ctx.fillText(`${simdi.size} tracked · ${faz.ad} · t = ${t.toFixed(1)} s`, gr.W / 40, gr.H - gr.W / 40);
    requestAnimationFrame(draw);
  }
  draw();
}

// ---------------------------------------------------------------- 4. bölüm: plan karşılaştırması
function phaseBar(el, sim) {
  const C = cycleOf(sim);
  el.innerHTML = sim.sinyal.map(f =>
    `<span title="${f.ad}: ${f.sure} s" style="width:${f.sure / C * 100}%;background:${phaseColor(f.ad)}"></span>`).join('') + '<i></i>';
}

function simSetup() {
  $('#simAh').textContent = 'Current plan (from video)';
  $('#simBh').textContent = 'Recommended by the agent';
  const plan10 = OZET.bekleme.planlar_10_tohum;
  const kolKodu = { 'from north (southbound)': 'K', 'from south (northbound)': 'G', 'from east': 'D', 'from west': 'B' };
  SIM_A._bekleme = Object.fromEntries(Object.entries(plan10.mevcut.kol_bekleme_s).map(([k, v]) => [kolKodu[k], v]));
  SIM_B._bekleme = Object.fromEntries(Object.entries(plan10.onerilen.kol_bekleme_s).map(([k, v]) => [kolKodu[k], v]));
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
  window.addEventListener('resize', () => { netCache.clear(); render(); });
  render();
}
