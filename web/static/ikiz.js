// Kavşak çizimi: 1. bölümdeki kuşbakışı (videodaki gerçek izler) ve 4. bölümdeki
// ikiz karşılaştırması aynı motorla çizilir.
//
// Kavşak düz kuşbakışı bir + olarak çizilir (perspektif yok, ölçek her yerde aynı) ve videoyla
// aynı yöne döndürülür: kalibrasyon homografisinden (AG.goruntu.G) kuzeyin ve doğunun görüntüdeki
// yönü okunur. Ağ (sim_ag.json) dik kollarla kurulur; şerit sayısı, genişliği, yanal konumu ve
// durma çizgileri yol boyasından ölçülmüştür, şerit okları videoda sayılan dönüşlerdir.
// Videodaki izler, her kolun gerçek yönüyle + yönü arasındaki küçük açı farkı kadar döndürülür.
//
// Kullandığı küreseller (index.html): $, OZET, BEV, SIM_A, SIM_B, AG, Chart.

const SIG = { G: '#3fdc6a', g: '#2f9e55', y: '#f2b531', r: '#ef4444', s: '#ef4444', o: '#555' };
const BODY = { K: '#7aa2ff', G: '#f0c674', D: '#b5e48c', B: '#ff9ecb' };
const MOVE_RENK = { 1: '#e6edf3', 2: '#f0b429', 3: '#39c5cf', 0: '#6e7681' };
const SERIT_KIRP_M = 140;  // şeritler merkezden bu uzaklıkta kesilir

function phaseColor(ad) {
  if (ad.startsWith('Southbound left')) return '#f0b429';
  if (ad.startsWith('Southbound through')) return '#58a6ff';
  if (ad.startsWith('Lankershim')) return '#3fb950';
  if (ad === 'Cross street') return '#bc8cff';
  if (ad === 'Yellow') return '#d29922';
  return '#444c56';
}

// ---------------------------------------------------------------- görünüm
const GORUS_M = 62;  // kavşak merkezinden yatayda her iki yana gösterilen mesafe (m)

// W piksel genişliğindeki tuval için yer -> ekran: videonun yönüne çevrilmiş düz harita.
function gorunum(W) {
  const g = AG.goruntu, G = g.G, H = Math.round(W * g.yukseklik / g.genislik);
  const V = (u, w) => { const z = G[2][0] * u + G[2][1] * w + G[2][2]; return [(G[0][0] * u + G[0][1] * w + G[0][2]) / z, (G[1][0] * u + G[1][1] * w + G[1][2]) / z]; };
  const [x0, y0] = V(0, 0), [xn, yn] = V(1, 0), [xe, ye] = V(0, 1);
  const a = Math.atan2(yn - y0, xn - x0), n = [Math.cos(a), Math.sin(a)];
  // doğu, kuzeye dik iki yönden videodakine yakın olanı
  const e0 = [-n[1], n[0]], isaret = Math.sign(e0[0] * (xe - x0) + e0[1] * (ye - y0)) || 1, e = [e0[0] * isaret, e0[1] * isaret];
  const S = W / (2 * GORUS_M), cx = W / 2, cy = H / 2;
  const P = (u, w) => [cx + S * (u * n[0] + w * e[0]), cy + S * (u * n[1] + w * e[1])];
  return { W, H, P, olcek: () => S };
}

// Videodaki gerçek konum -> + ağı: noktanın bulunduğu kolun gerçek yönüyle dik yönü arasındaki
// açı kadar merkez etrafında döndürülür (kavşak içinde, 10-20 m arası, yumuşak geçiş).
function artiya(u, w) {
  const r = Math.hypot(u, w);
  if (r < 10 || !AG.olculen) return [u, w];
  let en = null, enYakin = -2;
  for (const g of Object.values(AG.olculen)) {
    const ge = g.gercek_e || g.e, c = (u * ge[0] + w * ge[1]) / r;
    if (c > enYakin) { enYakin = c; en = g; }
  }
  const ge = en.gercek_e || en.e;
  const fark = (Math.atan2(en.e[1], en.e[0]) - Math.atan2(ge[1], ge[0])) * Math.min(1, (r - 10) / 10);
  const c = Math.cos(fark), s = Math.sin(fark);
  return [u * c - w * s, u * s + w * c];
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

  for (const l of lanes) { const [a, b] = kirpilmis(l); bant(ctx, gr, a, b, l.genislik + 1.8, '#3a434e'); }  // kaldırım
  for (const l of lanes) { const [a, b] = kirpilmis(l); bant(ctx, gr, a, b, l.genislik + 0.05, '#262b32'); }  // asfalt
  yerCokgen(ctx, gr, AG.kavsak, '#262b32');
  // Gelen ile giden şeritler arasında boşluk varsa (boyalı orta refüj) asfaltla doldur, iki
  // kenarına sarı çiz. Kenarlar ölçülen geometriden: n kolun solu, gelenin iç kenarı sol_gi.
  for (const g of Object.values(AG.olculen || {})) {
    const sol_gi = Math.max(...g.gelen.merkez) + g.gelen.genislik / 2;
    const sol_gc = Math.min(...g.giden.merkez) - g.giden.genislik / 2;
    if (sol_gc - sol_gi < 0.8) continue;
    const yer = (d, s) => [g.e[0] * d + g.n[0] * s, g.e[1] * d + g.n[1] * s], d0 = g.durma_m, d1 = SERIT_KIRP_M;
    const orta = (sol_gi + sol_gc) / 2;
    bant(ctx, gr, yer(d0, orta), yer(d1, orta), sol_gc - sol_gi + 0.1, '#262b32');
    for (const s of [sol_gc - 0.2, sol_gc - 0.4]) bant(ctx, gr, yer(d0, s), yer(d1, s), 0.12, '#e3b341');
  }

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
  // yol adı yolun dışında, yoldan uzağa doğru hizalı yazılır (yola taşmasın)
  const yaz = (t, kol, d) => {
    const g = AG.olculen[kol], ic = (x, y) => x > fs && x < gr.W - fs && y > fs * 1.4 && y < gr.H - fs * 4;  // alttaki bekleme etiketlerinden uzak
    while (d > 20 && !ic(...gr.P(...yolKenari(kol, d, -1, 2)))) d -= 2;  // kadraja girene dek merkeze yaklaş
    const [x, y] = gr.P(...yolKenari(kol, d, -1, 2)), [xm] = gr.P(g.e[0] * d, g.e[1] * d);
    ctx.textAlign = Math.abs(x - xm) < fs ? 'center' : x > xm ? 'left' : 'right';
    ctx.fillText(t, x, y + fs * 0.35);
  };
  yaz('Lankershim Blvd', 'K', 40);
  yaz('Universal Hollywood Dr', 'B', 52);
  ctx.textAlign = 'center';
  // pusula: kuzeyin ekrandaki yönü
  const [x0, y0] = gr.P(0, 0), [x1, y1] = gr.P(10, 0), a = Math.atan2(y1 - y0, x1 - x0);
  const cx = gr.W - fs * 3.6, cy = gr.H - fs * 1.6, r = fs * 1.2;  // sağ alt köşe, etiketlerden uzak
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
// buyuk: otobüs/kamyon (SUMO akış kimliği "KsB..." ya da videoda kutu boyundan), 10 m.
function drawCar(ctx, gr, v, renk, onTampon = true, buyuk = /^[KGDB][slr]B/.test(String(v[0]))) {
  const [id, u, w, hiz, aciDer] = v, a = aciDer * Math.PI / 180;  // 0 = kuzey, saat yönünde
  const fu = Math.cos(a), fw = Math.sin(a), su = -fw, sw = fu, boy = buyuk ? 10 : 4.6, en = buyuk ? 2.5 : 1.9;
  const geri = onTampon ? boy / 2 : 0, cu = u - fu * geri, cw = w - fw * geri;
  const p = (i, y) => [cu + fu * i + su * y, cw + fw * i + sw * y];
  const kutu = (i0, i1, y0, y1) => [p(i0, y0), p(i1, y0), p(i1, y1), p(i0, y1)];
  ctx.save(); ctx.translate(1, 1.5); yerCokgen(ctx, gr, kutu(-boy / 2, boy / 2, -en / 2, en / 2), 'rgba(0,0,0,0.4)'); ctx.restore();
  yerCokgen(ctx, gr, kutu(-boy / 2, boy / 2, -en / 2, en / 2), renk || BODY[String(id)[0]] || '#c9d1d9');
  if (buyuk) {  // otobüs/kamyon: ön cam ve tavan boyunca açık şerit
    yerCokgen(ctx, gr, kutu(boy * 0.40, boy * 0.47, -en * 0.40, en * 0.40), 'rgba(13,17,23,0.8)');
    yerCokgen(ctx, gr, kutu(-boy * 0.44, boy * 0.34, -en * 0.18, en * 0.18), 'rgba(255,255,255,0.35)');
  } else {
    yerCokgen(ctx, gr, kutu(boy * 0.08, boy * 0.26, -en * 0.38, en * 0.38), 'rgba(13,17,23,0.8)');     // ön cam
    yerCokgen(ctx, gr, kutu(-boy * 0.36, -boy * 0.24, -en * 0.36, en * 0.36), 'rgba(13,17,23,0.6)');  // arka cam
  }
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
// Bir kolun yanında, yolun dışında kalan yer noktası (ölçülen geometriden): kol ekseninde
// d metre, yaklaşan şeritler tarafında (taraf 1) ya da karşısında (-1), kenardan pay metre öte.
function yolKenari(kol, d, taraf, pay) {
  const g = AG.olculen[kol], gelen = g.gelen.merkez, isaret = Math.sign(gelen.reduce((a, b) => a + b, 0)) * taraf;
  const kenar = Math.max(...[...gelen, ...g.giden.merkez].map(m => m * isaret)) + 2;
  const s = isaret * (kenar + pay);
  return [g.e[0] * d + g.n[0] * s, g.e[1] * d + g.n[1] * s];
}
const KOL_ADI_KISA = { K: 'from north', G: 'from south', D: 'from east', B: 'from west' };
function armLabels(ctx, gr, bekleme) {
  const fs = Math.round(gr.W / 36), yariG = fs * 3.6, yariY = fs * 1.5;
  ctx.textAlign = 'center';
  for (const [kol, s] of Object.entries(bekleme)) {
    let x, y;
    for (let d = 52; d >= 22; d -= 2) {
      [x, y] = gr.P(...yolKenari(kol, d, 1, 13));
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

// ---------------------------------------------------------------- canlı bekleme sayacı
// Gelen araç durduğu (hız < 0,5 m/s, fren lambasıyla aynı eşik) her an sayacı artar; durma
// çizgisini geçip kavşağa girince sayaç kalkar. kare(i): o karedeki [id, u, w, hız] listesi.
// Dönüş: kare başına Map(id -> saniye), yalnızca bekleme > 0 olan ve henüz geçmemiş araçlar.
function kavsagaGirdi(u, w) {
  let en = null, enD = -Infinity;
  for (const g of Object.values(AG.olculen)) { const d = u * g.e[0] + w * g.e[1]; if (d > enD) { enD = d; en = g; } }
  return enD < en.durma_m - 0.5;
}

function beklemeSayaclari(n, dt, kare) {
  const bek = new Map(), gecti = new Set(), out = [];
  for (let i = 0; i < n; i++) {
    const m = new Map();
    for (const [id, u, w, hiz] of kare(i)) {
      if (gecti.has(id)) continue;
      if (kavsagaGirdi(u, w)) { gecti.add(id); continue; }
      const s = (bek.get(id) || 0) + (hiz < 0.5 ? dt : 0);
      bek.set(id, s);
      if (s > 0) m.set(id, s);
    }
    out.push(m);
  }
  return out;
}

// Bekleme saniyesi aracın tavanına, koyu kenarlı yazılır (kuyrukta yan şeritlerle çakışmasın);
// 30 s'yi geçince kırmızı. (u, w) aracın ortası.
function beklemeYaz(ctx, gr, u, w, s) {
  if (s < 1) return;
  const [x, y] = gr.P(u, w), fs = Math.max(7, Math.min(15, Math.round(gr.olcek(u, w) * 1.6)));
  ctx.font = `700 ${fs}px system-ui`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.lineWidth = Math.max(2, fs / 4); ctx.strokeStyle = 'rgba(13,17,23,0.95)'; ctx.lineJoin = 'round';
  ctx.strokeText(String(Math.floor(s)), x, y);
  ctx.fillStyle = s >= 30 ? '#ff8a8a' : '#ffffff'; ctx.fillText(String(Math.floor(s)), x, y);
  ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
}

// SUMO konumu ön tampondur; etiket gövdenin ortasına.
function govdeOrtasi(v) {
  const a = v[4] * Math.PI / 180, yarim = /^[KGDB][slr]B/.test(String(v[0])) ? 5 : 2.3;
  return [v[1] - Math.cos(a) * yarim, v[2] - Math.sin(a) * yarim];
}

function stoppedNear(vs) { return vs.filter(v => v[3] < 0.5 && Math.hypot(v[1], v[2]) < 75).length; }

function drawTwin(cv, sim, t) {
  const { ctx, gr } = setupCanvas(cv);
  ctx.drawImage(networkImage(gr.W), 0, 0);
  const ph = phaseAt(sim, t);
  drawSignals(ctx, gr, ph.f.durum);
  const vs = vehiclesAt(sim, t);
  for (const v of vs) drawCar(ctx, gr, v);
  // kayıt 2 Hz; sayaçlar bir kez hesaplanır (kayıt penceresinin başında sıfırdan başlar)
  if (!sim._sayac) { const fr = frameMap(sim); sim._sayac = beklemeSayaclari(fr.length, 0.5, i => [...fr[i].values()].map(v => [v[0], v[1], v[2], v[3]])); }
  const sayac = sim._sayac[Math.min(Math.floor(t * 2), sim._sayac.length - 1)];
  for (const v of vs) if (sayac.has(v[0])) beklemeYaz(ctx, gr, ...govdeOrtasi(v), sayac.get(v[0]));
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
    for (const [id, u, w, , h, b] of liste) m.set(id, [...artiya(u, w), h, b]);
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
    return { u: p[0], w: p[1], h: p[2], buyuk: !!p[3], hiz: yol / 0.8, aci: yon.get(id) ?? varsayilan };
  }

  // canlı bekleme sayaçları (5 fps), videonun başından
  const sayac = beklemeSayaclari(kareler.length, 0.2, i => [...(kareler[i]?.keys() || [])].map(id => {
    const a = aracDurumu(i, id); return [id, a.u, a.w, a.hiz];
  }));

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
      drawCar(ctx, gr, [id, a.u + (b.u - a.u) * k, a.w + (b.w - a.w) * k, a.hiz, a.aci + da * k], MOVE_RENK[a.h], false, a.buyuk);
    }
    for (const [id, s] of sayac[i] || []) {
      const a = aracDurumu(i, id);
      if (a) beklemeYaz(ctx, gr, a.u, a.w, s);
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
