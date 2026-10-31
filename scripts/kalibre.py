"""Kamera 2 için piksel -> saha (CA State Plane, ft) homografisini veriden çıkarır.

Elle nokta işaretlemek yerine SAM tespit merkezleri ile aynı andaki gerçek
NGSIM araç konumları eşleştirilir. NGSIM yalnızca Lankershim üzerindeki
araçları içerir; yan yoldaki kuyruklar veride yoktur. Bu yüzden:
  1. Kaba arama: açı, ölçek, ayna ve kaydırma ızgarası. Her aday, görüntüye
     düşen gerçek araçların yüzde kaçının yanında bir tespit olduğuna
     ("kapsama") göre puanlanır. Yan yoldaki fazla tespitler bu puanı bozmaz.
  2. İnce ayar: gerçek araçların yakınındaki tespitlerle RANSAC homografisi,
     birkaç tur.

Kullanım:
    .venv/Scripts/python scripts/kalibre.py [--ofset 1.5]
"""

import argparse
import json

import cv2
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

GENISLIK, YUKSEKLIK = 640, 480
KAVSAK_PX = (270.0, 200.0)  # kavşak 2'nin görüntüdeki yaklaşık merkezi


def yukle(ofset: float):
    tespitler = sorted(
        (json.loads(s) for s in open("data/tespit/car.jsonl", encoding="utf-8")),
        key=lambda x: x["kare"],
    )
    g = pd.read_parquet("data/ngsim/kavsak2.parquet", columns=["t", "global_x", "global_y", "int_id"])
    g = g.assign(tk=np.round(g.t, 1))
    gruplar = dict(tuple(g.groupby("tk")))

    ciftler = []
    for x in tespitler:
        t = round(x["kare"] / 10 + ofset, 1)
        if t not in gruplar or not x["kutular"]:
            continue
        k = np.array(x["kutular"], dtype=float)[:, :4]
        merkez = np.c_[(k[:, 0] + k[:, 2]) / 2, (k[:, 1] + k[:, 3]) / 2]
        gercek = gruplar[t][["global_x", "global_y"]].to_numpy()
        ciftler.append((merkez, cKDTree(merkez), gercek))
    kavsak_merkez = g[g.int_id == 2][["global_x", "global_y"]].to_numpy().mean(axis=0)
    return ciftler, kavsak_merkez


def izdus(H: np.ndarray, p: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(p.reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2)


def kapsama(ciftler, H_saha2px: np.ndarray, esik_px: float = 10.0) -> float:
    """Görüntüye düşen gerçek araçların yanında tespit bulunma oranı."""
    toplam = isabet = 0
    for _, agac, gercek in ciftler:
        px = izdus(H_saha2px, gercek)
        icerde = (px[:, 0] >= 0) & (px[:, 0] < GENISLIK) & (px[:, 1] >= 0) & (px[:, 1] < YUKSEKLIK)
        if icerde.sum() == 0:
            continue
        mesafe, _ = agac.query(px[icerde])
        toplam += icerde.sum()
        isabet += (mesafe < esik_px).sum()
    # Çok az aracı görüntüye düşüren adaylar ödüllendirilmesin.
    return isabet / max(toplam, 1) * min(1.0, toplam / (8 * len(ciftler)))


def benzerlik(aci: float, olcek: float, ayna: bool, kaydir, merkez_saha) -> np.ndarray:
    c, s = np.cos(aci), np.sin(aci)
    R = olcek * np.array([[c, -s], [s, c]])
    if ayna:
        R = R @ np.diag([1, -1])
    T = np.array(KAVSAK_PX) + kaydir - R @ merkez_saha
    return np.vstack([np.c_[R, T], [0, 0, 1]])


def kaba_arama(ciftler, merkez_saha):
    ornek = ciftler[:: max(1, len(ciftler) // 40)]
    en_iyi = (-1.0, None)
    for ayna in (False, True):
        for aci in np.deg2rad(np.arange(0, 360, 5)):
            for olcek in (0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4):
                for dx in range(-60, 61, 20):
                    for dy in range(-60, 61, 20):
                        H = benzerlik(aci, olcek, ayna, (dx, dy), merkez_saha)
                        p = kapsama(ornek, H)
                        if p > en_iyi[0]:
                            en_iyi = (p, H)
    return en_iyi


def ince_ayar(ciftler, H_saha2px: np.ndarray, tur: int = 8, esik_px: float = 12.0):
    for _ in range(tur):
        kaynak, hedef = [], []
        for merkez, agac, gercek in ciftler:
            px = izdus(H_saha2px, gercek)
            mesafe, j = agac.query(px)
            iyi = mesafe < esik_px
            kaynak.append(gercek[iyi])
            hedef.append(merkez[j[iyi]])
        kaynak, hedef = np.vstack(kaynak), np.vstack(hedef)
        H_yeni, _ = cv2.findHomography(kaynak, hedef, cv2.RANSAC, 6.0)
        if H_yeni is None:
            break
        H_saha2px = H_yeni
        esik_px = max(8.0, esik_px * 0.85)
    return H_saha2px


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ofset", type=float, default=1.5, help="video t=0 anının yörünge zamanı (s)")
    args = ap.parse_args()

    ciftler, merkez_saha = yukle(args.ofset)
    print(f"{len(ciftler)} kare eşlendi")
    puan, H = kaba_arama(ciftler, merkez_saha)
    print(f"kaba arama kapsaması: %{puan * 100:.0f}")
    H = ince_ayar(ciftler, H)
    print(f"ince ayar sonrası kapsama: %{kapsama(ciftler, H) * 100:.0f}")

    # Sayım korelasyonu zamanı ~1 s hassasiyetle verir; hareketli araçlar
    # için bu kaba. Zaman kaydırmasını homografiyle birlikte sıkılaştır.
    ofset = args.ofset
    for _ in range(3):
        adaylar = np.round(np.arange(ofset - 2, ofset + 2.01, 0.1), 1)
        puanlar = [kapsama(yukle(o)[0][::4], H) for o in adaylar]
        ofset = float(adaylar[int(np.argmax(puanlar))])
        ciftler = yukle(ofset)[0]
        H = ince_ayar(ciftler, H)
        print(f"ofset {ofset:.1f} s, kapsama %{kapsama(ciftler, H) * 100:.0f}")

    np.save("data/kalibrasyon_kamera2.npy", np.linalg.inv(H))  # piksel -> saha
    with open("data/kalibrasyon_kamera2.json", "w", encoding="utf-8") as f:
        json.dump({"ofset_s": ofset, "kapsama": kapsama(ciftler, H)}, f)
    print("data/kalibrasyon_kamera2.npy (piksel -> saha)")


if __name__ == "__main__":
    main()
