"""İzlerden yön/hareket sayımlarını çıkarır ve NGSIM etiketleriyle karşılaştırır.

Çıktılar:
  data/akis_izler.parquet        her iz için giriş/çıkış kolu, yön, hareket, geçiş karesi
  data/akis_karsilastirma.csv    yön x hareket sayıları: NGSIM ve bizim

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/akis_cikar.py
"""

import json

import pandas as pd

from trafik.akis import HAREKET_ADI, siniflandir

YON_ADI = {1: "doğuya", 2: "kuzeye", 3: "batıya", 4: "güneye"}
VIDEO_SURE_S = 1122.0


def main() -> None:
    ofset = json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8"))["ofset_s"]
    s = siniflandir(pd.read_parquet("data/izler_kamera2.parquet"))
    s.to_parquet("data/akis_izler.parquet")

    g = pd.read_parquet("data/ngsim/kavsak2.parquet")
    g = g[(g.t >= ofset) & (g.t <= VIDEO_SURE_S + ofset) & (g.int_id == 2)]
    ngsim = g.groupby("vehicle_id").agg(yon=("direction", "first"), hareket=("movement", "first"))

    a = pd.crosstab(ngsim.yon, ngsim.hareket)
    b = pd.crosstab(s.yon, s.hareket).reindex_like(a).fillna(0).astype(int)
    t = pd.DataFrame({"ngsim": a.stack(), "bizim": b.stack()}).reset_index()
    t["yon"] = t.yon.map(YON_ADI)
    t["hareket"] = t.hareket.map(HAREKET_ADI)
    t["fark_yuzde"] = ((t.bizim - t.ngsim) / t.ngsim * 100).round(1)
    t.to_csv("data/akis_karsilastirma.csv", index=False)
    print(t.to_string(index=False))
    toplam_n, toplam_b = t.ngsim.sum(), t.bizim.sum()
    print(f"toplam: NGSIM {toplam_n}, bizim {toplam_b} ({(toplam_b - toplam_n) / toplam_n * 100:+.1f}%)")


if __name__ == "__main__":
    main()
