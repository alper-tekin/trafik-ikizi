"""5 fps SAM tespitlerinden izleri çıkarır ve gerçek NGSIM yörüngeleriyle karşılaştırır.

Ölçüler (görüntüye düşen gerçek araçlar üzerinden):
  - kapsama: gerçek aracın o karede yakınında (kapı içinde) bir iz noktası olma oranı
  - konum hatası: eşleşen iz noktası ile gerçek konum arası mesafe (ft)
  - parçalanma: bir gerçek aracın görüldüğü süre boyunca kaç farklı ize bölündüğü

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/takip_degerlendir.py
"""

import json

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from trafik.takip import takip_et

KAPI_FT = 12.0


def main() -> None:
    H = np.load("data/kalibrasyon_kamera2.npy")
    ofset = json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8"))["ofset_s"]

    satirlar = sorted(
        (json.loads(s) for s in open("data/tespit/car.jsonl", encoding="utf-8")),
        key=lambda x: x["kare"],
    )
    kareler = [(x["kare"], np.array(x["kutular"], dtype=float).reshape(-1, 5)[:, :4]) for x in satirlar]
    izler = takip_et(kareler, H)
    izler.to_parquet("data/izler_kamera2.parquet")
    print(f"{izler.iz.nunique()} iz, {len(izler)} nokta")

    g = pd.read_parquet("data/ngsim/kavsak2.parquet", columns=["t", "vehicle_id", "global_x", "global_y"])
    g = g.assign(tk=np.round(g.t, 1))
    gruplar = dict(tuple(g.groupby("tk")))
    Hi = np.linalg.inv(H)

    eslesmeler, gorunen = [], 0
    for kare, grup in izler.groupby("kare"):
        t = round(kare / 10 + ofset, 1)
        if t not in gruplar:
            continue
        gercek = gruplar[t]
        px = cv2.perspectiveTransform(
            gercek[["global_x", "global_y"]].to_numpy().reshape(-1, 1, 2).astype(np.float64), Hi
        ).reshape(-1, 2)
        icerde = (px[:, 0] >= 0) & (px[:, 0] < 640) & (px[:, 1] >= 0) & (px[:, 1] < 480)
        gercek = gercek[icerde]
        gorunen += len(gercek)
        if gercek.empty:
            continue
        a = gercek[["global_x", "global_y"]].to_numpy()
        b = grup[["x", "y"]].to_numpy()
        maliyet = np.linalg.norm(a[:, None] - b[None], axis=2)
        r, c = linear_sum_assignment(maliyet)
        for i, j in zip(r, c):
            if maliyet[i, j] <= KAPI_FT:
                eslesmeler.append((kare, gercek.vehicle_id.iloc[i], grup.iz.iloc[j], maliyet[i, j]))

    e = pd.DataFrame(eslesmeler, columns=["kare", "arac", "iz", "hata"])
    parca = e.groupby("arac").iz.nunique()
    sonuc = {
        "iz_sayisi": int(izler.iz.nunique()),
        "gercek_arac_sayisi": int(e.arac.nunique()),
        "kapsama": len(e) / gorunen,
        "hata_medyan_ft": float(e.hata.median()),
        "hata_p90_ft": float(e.hata.quantile(0.9)),
        "parca_medyan": float(parca.median()),
        "tek_izde_arac_orani": float((parca == 1).mean()),
    }
    json.dump(sonuc, open("data/takip_degerlendirme.json", "w", encoding="utf-8"), indent=2)
    for k, v in sonuc.items():
        print(f"{k}: {v:.3f}" if isinstance(v, float) else f"{k}: {v}")


if __name__ == "__main__":
    main()
