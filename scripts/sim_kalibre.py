"""SUMO sürücü parametrelerini videodaki kuyruk profillerine kalibre eder.

Hedef: döngü içindeki kol başına kuyruk profili (videodan). Hata = ana
kollardaki (K, G) profillerin RMSE'si. NGSIM kalibrasyonda kullanılmaz;
sonda bağımsız kontrol olarak raporlanır.

Çıktı: data/sim_kalibrasyon.json

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/sim_kalibre.py
"""

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from trafik import olcum
from trafik.simule import calistir
from trafik.sumo_ag import kur, plan_videodan

SURE_S = 1122.0
KOLLAR = ["K", "G"]


def rmse(a: pd.DataFrame, b: pd.DataFrame) -> float:
    a, b = a.reindex(columns=KOLLAR, fill_value=0), b.reindex(columns=KOLLAR, fill_value=0)
    ortak = a.index.intersection(b.index)
    return float(np.sqrt(((a.loc[ortak] - b.loc[ortak]) ** 2).to_numpy().mean()))


def main() -> None:
    plan = json.load(open("data/sinyal_plani.json", encoding="utf-8"))
    C, faz0 = plan["dongu_s"], plan["faz0_video_s"]
    ofset = json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8"))["ofset_s"]

    akis = pd.read_parquet("data/akis_izler.parquet")
    sayim = akis.groupby(["yon", "hareket"]).size().to_dict()
    video = olcum.kuyruk_profili(
        olcum.noktalar_izden(pd.read_parquet("data/izler_kamera2.parquet"), akis), C, faz0)
    ngsim = olcum.kuyruk_profili(
        olcum.noktalar_ngsimden(pd.read_parquet("data/ngsim/kavsak2.parquet"), ofset, SURE_S), C, faz0)
    yesil, dongu = plan_videodan()

    sonuclar = []
    for tau, accel in itertools.product([0.8, 1.0, 1.2], [1.5, 2.0, 2.6]):
        surucu = {"tau": tau, "accel": accel}
        cfg = kur(Path("sim/kalibre"), sayim, SURE_S, yesil, dongu, surucu=surucu)
        q = olcum.kuyruk_profili(calistir(cfg), C, 0.0)
        hata = rmse(q, video)
        sonuclar.append({**surucu, "rmse_video": hata, "rmse_ngsim": rmse(q, ngsim),
                         "ort_kuyruk": q.reindex(columns=KOLLAR, fill_value=0).mean().round(2).to_dict()})
        print(sonuclar[-1], flush=True)

    varsayilan = next(s for s in sonuclar if s["tau"] == 1.0 and s["accel"] == 2.0)
    en_iyi = min(sonuclar, key=lambda s: s["rmse_video"])
    cikti = {
        "en_iyi": en_iyi,
        "varsayilan": varsayilan,
        "video_ort_kuyruk": video.reindex(columns=KOLLAR).mean().round(2).to_dict(),
        "ngsim_ort_kuyruk": ngsim.reindex(columns=KOLLAR).mean().round(2).to_dict(),
        "video_vs_ngsim_rmse": rmse(video, ngsim),
        "tum": sonuclar,
    }
    json.dump(cikti, open("data/sim_kalibrasyon.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("en iyi:", en_iyi)
    print("varsayılan:", varsayilan)


if __name__ == "__main__":
    main()
