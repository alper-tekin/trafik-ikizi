"""Kavşak geometrisini videodaki araç izlerinden ölçer.

Kavşak kare değil: kolların yönü, şerit sayısı ve genişliği, durma çizgilerinin
yeri ve kavşak alanının şekli izlerden çıkarılır ve SUMO ağı bununla kurulur.
Koordinatlar kavşak merkezli metre (u kuzey, w doğu).

Her kol için:
  e        dışarı doğru birim yön (gelen araçların ekseninden, PCA)
  yanal    s = p · n, n = e'nin solu (u, w düzleminde [-e_w, e_u])
  gelen    gelen şeritlerin yanal merkezleri ve genişliği
  giden    giden şeritlerin yanal merkezleri ve genişliği
  durma_m  durma çizgisinin merkeze uzaklığı (öndeki duran araçlardan)
"""

import json

import numpy as np
import pandas as pd

from trafik import olcum
from trafik.akis import kol

ARAC_YARI_BOY_M = 2.3  # iz noktası kutu merkezi; aracın önü ~2,3 m ileride
SERIT_M = 3.3


def _seritler(s: np.ndarray, alt: float, ust: float) -> dict:
    """Yanal konum dağılımından şerit sayısı, merkezleri ve genişliği."""
    lo, hi = np.percentile(s, [alt, ust])
    n = int(np.clip(round((hi - lo) / SERIT_M) + 1, 1, 6))
    if n == 1:
        return {"n": 1, "merkez": [float(np.median(s))], "genislik": SERIT_M}
    gen = float(np.clip((hi - lo) / (n - 1), 2.9, 3.8))
    orta = (lo + hi) / 2
    merkez = [float(orta + (i - (n - 1) / 2) * gen) for i in range(n)]
    return {"n": n, "merkez": merkez, "genislik": gen}


def olc(izler: pd.DataFrame, akis: pd.DataFrame) -> dict:
    d = olcum.noktalar_izden(izler, akis).merge(
        akis[["iz", "cikis"]].rename(columns={"iz": "arac"}), on="arac")
    d = d.assign(r=np.hypot(d.u, d.w), k=kol(d[["u", "w"]].to_numpy()))
    kollar = {}
    for k in "KGDB":
        gelen = d[(d.giris == k) & (d.k == k) & (d.r > 18) & (d.r < 70)]
        giden = d[(d.cikis == k) & (d.k == k) & (d.r > 18) & (d.r < 70)]
        x = gelen[["u", "w"]].to_numpy()
        m = x.mean(axis=0)
        e = np.linalg.svd(x - m, full_matrices=False)[2][0]
        e = e if e @ m > 0 else -e
        n = np.array([-e[1], e[0]])
        duran = gelen[gelen.hiz < 0.5][["u", "w"]].to_numpy()
        kollar[k] = {
            "e": e.round(4).tolist(),
            "n": n.round(4).tolist(),
            # gelen kuyruklar şeritleri dolduruyor; gidenlerin dış şeritleri seyrek kullanılıyor
            "gelen": _seritler(x @ n, 5, 95),
            "giden": _seritler(giden[["u", "w"]].to_numpy() @ n, 10, 90),
            "durma_m": float(np.percentile(duran @ e, 5) - ARAC_YARI_BOY_M),
            "ornek": int(len(gelen)),
        }
    return {"kollar": kollar}


def kavsak_cokgeni(g: dict) -> list:
    """Her kolun durma çizgisindeki şerit dış kenarlarından kavşak alanı (dışbükey zarf)."""
    noktalar = []
    for k in g["kollar"].values():
        e, n, t = np.array(k["e"]), np.array(k["n"]), k["durma_m"]
        for taraf in ("gelen", "giden"):
            s = k[taraf]
            for kenar in (min(s["merkez"]) - s["genislik"] / 2, max(s["merkez"]) + s["genislik"] / 2):
                noktalar.append(e * t + n * kenar)
    p = np.array(noktalar)
    merkez = p.mean(axis=0)
    sira = np.argsort(np.arctan2(p[:, 1] - merkez[1], p[:, 0] - merkez[0]))
    p = p[sira]
    # dışbükey zarf (monoton zincir)
    p = sorted(map(tuple, p))

    def capraz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    alt, ust = [], []
    for q in p:
        while len(alt) >= 2 and capraz(alt[-2], alt[-1], q) <= 0:
            alt.pop()
        alt.append(q)
    for q in reversed(p):
        while len(ust) >= 2 and capraz(ust[-2], ust[-1], q) <= 0:
            ust.pop()
        ust.append(q)
    return [list(map(float, q)) for q in alt[:-1] + ust[:-1]]


def kaydet(g: dict, yol: str = "data/geometri.json") -> None:
    g = {**g, "kavsak": kavsak_cokgeni(g)}
    json.dump(g, open(yol, "w", encoding="utf-8"), indent=2)


def yukle(yol: str = "data/geometri.json") -> dict:
    return json.load(open(yol, encoding="utf-8"))
