"""Araçların kavşaktan geçiş zamanlarından sinyal planını çıkarır.

Sinyal raporları (RSM) indirilebilir değil; bunun yerine:
  1. Kuzey-güney düz/sağ geçişlerinin saniyelik sayısının otokorelasyonu
     döngü süresini verir.
  2. Her faz grubunun geçişleri döngü içinde katlanır; geçişlerin yoğun olduğu
     ardışık saniyeler o grubun yeşil penceresidir.
Aynı yöntem NGSIM yörüngelerine de uygulanır ve iki sonuç karşılaştırılır.

Çıktı: data/sinyal_plani.json

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/sinyal_cikar.py
"""

import json

import numpy as np
import pandas as pd

from trafik.akis import yerel

VIDEO_SURE_S = 1122
GRUPLAR = {
    "kuzey_guney": lambda d: d.yon.isin([2, 4]) & (d.hareket != 2),
    # Bu kavşakta önden sol var: güneye giden yön kuzeye gidenden önce açılıyor.
    "guneye_duz": lambda d: (d.yon == 4) & (d.hareket == 1),
    "kuzeye_duz": lambda d: (d.yon == 2) & (d.hareket == 1),
    "guneye_sol": lambda d: (d.yon == 4) & (d.hareket == 2),
    "dogu_bati": lambda d: d.yon.isin([1, 3]),
}


def ngsim_gecisleri(ofset: float) -> pd.DataFrame:
    g = pd.read_parquet("data/ngsim/kavsak2.parquet")
    g = g[(g.t >= ofset) & (g.t <= VIDEO_SURE_S + ofset) & (g.int_id == 2)].copy()
    uw = yerel(g[["global_x", "global_y"]].to_numpy())
    g["r"] = np.hypot(uw[:, 0], uw[:, 1])
    d = g.loc[g.groupby("vehicle_id").r.idxmin(), ["t", "direction", "movement"]]
    d = d.rename(columns={"direction": "yon", "movement": "hareket"})
    return d.assign(t=d.t - ofset)


def bizim_gecisler() -> pd.DataFrame:
    s = pd.read_parquet("data/akis_izler.parquet")
    return s.assign(t=s.gecis_kare / 10.0)


def dongu(d: pd.DataFrame) -> tuple[int, float]:
    h = np.zeros(VIDEO_SURE_S + 1)
    np.add.at(h, d[GRUPLAR["kuzey_guney"](d)].t.astype(int).clip(0, VIDEO_SURE_S), 1)
    h -= h.mean()
    ac = [np.corrcoef(h[:-L], h[L:])[0, 1] for L in range(40, 160)]
    return 40 + int(np.argmax(ac)), float(max(ac))


def yesil_pencere(t: np.ndarray, C: int, faz0: float) -> tuple[int, int]:
    """Döngü içinde geçişlerin yoğun olduğu en uzun dairesel aralık (s)."""
    hist = np.histogram((t - faz0) % C, bins=C, range=(0, C))[0].astype(float)
    duz = np.convolve(np.r_[hist[-2:], hist, hist[:2]], np.ones(5) / 5, mode="valid")
    acik = duz > 0.25 * duz.max()
    # dairesel en uzun açık dizi
    iki = np.r_[acik, acik]
    en_iyi, bas, uzun, en_bas = 0, 0, 0, 0
    for i, a in enumerate(iki):
        if a:
            if uzun == 0:
                bas = i
            uzun += 1
            if uzun > en_iyi and uzun <= C:
                en_iyi, en_bas = uzun, bas
        else:
            uzun = 0
    return en_bas % C, en_iyi


def plan(d: pd.DataFrame, C: int, faz0: float) -> dict:
    return {ad: dict(zip(("baslangic_s", "sure_s"), yesil_pencere(d[f(d)].t.to_numpy(), C, faz0)))
            for ad, f in GRUPLAR.items()}


def main() -> None:
    ofset = json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8"))["ofset_s"]
    gercek, bizim = ngsim_gecisleri(ofset), bizim_gecisler()

    C_b, r_b = dongu(bizim)
    C_n, r_n = dongu(gercek)
    print(f"döngü: bizim {C_b} s (r={r_b:.2f}), NGSIM {C_n} s (r={r_n:.2f})")

    # Döngünün sıfır noktası: kuzey-güney yeşilinin başı (bizim veriden).
    faz0 = 0.0
    bas, _ = yesil_pencere(bizim[GRUPLAR["kuzey_guney"](bizim)].t.to_numpy(), C_b, 0.0)
    faz0 = float(bas)

    sonuc = {
        "dongu_s": C_b,
        "faz0_video_s": faz0,
        "bizim": plan(bizim, C_b, faz0),
        "ngsim": plan(gercek, C_b, faz0),
        "ngsim_dongu_s": C_n,
    }
    json.dump(sonuc, open("data/sinyal_plani.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    for ad in GRUPLAR:
        b, n = sonuc["bizim"][ad], sonuc["ngsim"][ad]
        print(f"{ad:12s} bizim: {b['baslangic_s']:3d}+{b['sure_s']:3d} s   NGSIM: {n['baslangic_s']:3d}+{n['sure_s']:3d} s")


if __name__ == "__main__":
    main()
