"""Bir sinyal planını kalibre edilmiş SUMO ikizinde dener ve gecikmeleri ölçer.

Ajanın her önerisi buradan geçer: plan önce gerçek dünya kısıtlarına göre
denetlenir, sonra birkaç tohumla simüle edilir (tek koşunun şansına güvenilmez).
Varsayılan trafik videodaki araçlardır (gerçek gelişler); tohum o zaman yalnızca sürücü
davranışındaki rastgeleliği değiştirir. gelis="rastgele" ile sayımlardan rastgele gelişler. Gecikme = SUMO tripinfo 'timeLoss' (serbest akışa göre kayıp süre).
"""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

from trafik.sumo_ag import SARI, TUM_KIRMIZI, VARSAYILAN_GELIS, _ortam, _sumo_bin, faz_plani_surelerden, kur

SURE_S = 1122.0
ISINMA_S = 120.0
# Çıktılar ajana gittiği için İngilizce.
KOL_ADI = {"K": "from north (southbound)", "G": "from south (northbound)", "D": "from east", "B": "from west"}
HAREKET_ADI = {"s": "through", "l": "left", "r": "right"}

# Gerçek dünya kısıtları
KISIT = {
    "ara_sokak_min_s": 30,  # yayalar ~30 m'lik Lankershim'i bu fazda geçer (7 s yürü + ~23 s temizleme)
    "ortak_min_s": 18,  # yayalar ara sokağı (~13 m) bu fazda geçer
    "dongu_min_s": 60,
    "dongu_max_s": 150,
}


def denetle(plan: dict) -> list[str]:
    hatalar = []
    for ad in ("sol_onde", "guney_onde", "ortak", "ara_sokak"):
        if plan.get(ad, -1) < 0:
            hatalar.append(f"{ad} negatif olamaz")
    if plan["ara_sokak"] < KISIT["ara_sokak_min_s"]:
        hatalar.append(f"ara_sokak en az {KISIT['ara_sokak_min_s']} s olmalı (Lankershim yaya geçişi)")
    if plan["ortak"] < KISIT["ortak_min_s"]:
        hatalar.append(f"ortak en az {KISIT['ortak_min_s']} s olmalı (ara sokak yaya geçişi)")
    for ad in ("sol_onde", "guney_onde"):
        if 0 < plan[ad] < 5:
            hatalar.append(f"{ad} 0 ya da en az 5 s olmalı")
    C = dongu(plan)
    if not KISIT["dongu_min_s"] <= C <= KISIT["dongu_max_s"]:
        hatalar.append(f"döngü {C:.0f} s; {KISIT['dongu_min_s']}-{KISIT['dongu_max_s']} s arasında olmalı")
    return hatalar


def dongu(plan: dict) -> float:
    return plan["sol_onde"] + plan["guney_onde"] + plan["ortak"] + plan["ara_sokak"] + 2 * (SARI + TUM_KIRMIZI)


def _tek_kosu(cfg: Path, tohum: int) -> pd.DataFrame:
    cikti = f"trip_{tohum}.xml"
    subprocess.run(
        [_sumo_bin("sumo"), "-c", cfg.name, "--seed", str(tohum), "--tripinfo-output", cikti,
         "--no-warnings", "--no-step-log"],
        check=True, cwd=cfg.parent, env=_ortam(), capture_output=True,
    )
    satir = []
    for t in ET.parse(cfg.parent / cikti).getroot().iter("tripinfo"):
        if float(t.get("depart")) < ISINMA_S:
            continue
        akis = t.get("id").split(".")[0]
        satir.append((akis[0], akis[1], float(t.get("timeLoss")), float(t.get("waitingTime"))))
    return pd.DataFrame(satir, columns=["kol", "hareket", "gecikme", "bekleme"])


def degerlendir(plan: dict, sayim: dict, surucu: dict, tohumlar=(1, 2, 3), gelis: str = VARSAYILAN_GELIS) -> dict:
    hatalar = denetle(plan)
    if hatalar:
        return {"gecerli": False, "hatalar": hatalar}
    anahtar = hashlib.md5(json.dumps([plan, surucu, gelis], sort_keys=True).encode()).hexdigest()[:10]
    fazlar = faz_plani_surelerden(plan["sol_onde"], plan["guney_onde"], plan["ortak"], plan["ara_sokak"])
    cfg = kur(Path("sim/aday") / anahtar, sayim, SURE_S, {}, 0, surucu=surucu, fazlar=fazlar, gelis=gelis)
    d = pd.concat([_tek_kosu(cfg, t).assign(tohum=t) for t in tohumlar])

    kol = d.groupby("kol").gecikme.mean().round(1)
    hareket = d.groupby(["kol", "hareket"]).gecikme.mean().round(1)
    tohum_ort = d.groupby("tohum").gecikme.mean()
    return {
        "gecerli": True,
        "plan": {**plan, "dongu_s": dongu(plan)},
        "ort_gecikme_s": round(float(d.gecikme.mean()), 1),
        "ort_gecikme_tohum_araligi_s": [round(float(tohum_ort.min()), 1), round(float(tohum_ort.max()), 1)],
        "p95_gecikme_s": round(float(d.gecikme.quantile(0.95)), 1),
        "arac_basi_durma_bekleme_s": round(float(d.bekleme.mean()), 1),
        "tamamlanan_arac": int(len(d) / len(tohumlar)),
        "kol_gecikme_s": {KOL_ADI[k]: v for k, v in kol.items()},
        # SUMO waitingTime: hızın 0,1 m/s altında geçen süre (araç başı, kol ortalaması)
        "kol_bekleme_s": {KOL_ADI[k]: round(float(v), 1) for k, v in d.groupby("kol").bekleme.mean().items()},
        "hareket_gecikme_s": {f"{KOL_ADI[k]} {HAREKET_ADI[h]}": v for (k, h), v in hareket.items()},
    }


def webster(sayim: dict, doyma_serit_saat: float = 1800.0) -> dict:
    """Webster yöntemiyle taban plan (klasik trafik mühendisliği formülü).

    Kritik akış oranları: önden sol (güneye sol, 2 şerit), Lankershim düz
    (kuzeye 4 / güneye 3 şerit, büyüğü), ara sokak (2 şerit, büyük kol).
    """
    saat = lambda n: n / SURE_S * 3600  # noqa: E731
    # otobüs/kamyon 2 binek otomobil eşdeğeri sayılır
    sayim = {k: sayim.get(k, 0) + 2 * sayim.get((*k, "b"), 0) for k in {a[:2] for a in sayim}}
    y_sol = saat(sayim.get((4, 2), 0)) / (2 * doyma_serit_saat)
    y_ns = max(saat(sayim.get((2, 1), 0) + sayim.get((2, 3), 0)) / (4 * doyma_serit_saat),
               saat(sayim.get((4, 1), 0) + sayim.get((4, 3), 0)) / (3 * doyma_serit_saat))
    y_db = max(saat(sum(sayim.get((1, h), 0) for h in (1, 2, 3))),
               saat(sum(sayim.get((3, h), 0) for h in (1, 2, 3)))) / (2 * doyma_serit_saat)
    Y = y_sol + y_ns + y_db
    L = 3 * (SARI + TUM_KIRMIZI)
    C = float(np.clip((1.5 * L + 5) / (1 - Y), KISIT["dongu_min_s"], KISIT["dongu_max_s"]))
    yesil = C - L
    plan = {"sol_onde": yesil * y_sol / Y, "guney_onde": 0.0, "ortak": yesil * y_ns / Y, "ara_sokak": yesil * y_db / Y}
    # Yaya kısıtları Webster'in üstünde gelir; eksik süre döngüye eklenir.
    plan["ara_sokak"] = max(plan["ara_sokak"], KISIT["ara_sokak_min_s"])
    plan["ortak"] = max(plan["ortak"], KISIT["ortak_min_s"])
    plan = {k: float(round(v)) for k, v in plan.items()}
    # Webster önden-sol için ayrı bir sarı ara vermez; faz sayısı tutarlı kalsın diye sol fazı korunur.
    return {"plan": plan, "akis_oranlari": {"sol": round(y_sol, 3), "lankershim": round(y_ns, 3),
                                            "ara_sokak": round(y_db, 3), "toplam": round(Y, 3)}}
