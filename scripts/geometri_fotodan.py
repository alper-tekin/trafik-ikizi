"""Kavşak geometrisini araçsız yol fotoğrafındaki boyadan ölçer (izlerden ölçmenin yerine).

İzlerden ölçülen geometri (geometri.py) her kolu tek eksenli, eşit aralıklı şeritler olarak
kestiriyordu; video üstüne bindirildiğinde şeritler boyaya oturmuyordu. Burada her kolun şerit
sınırları (kenar, kesikli/düz beyaz, sarı) fotoğrafta iki enine kesitte piksel olarak okunur
(scripts/profil çıktısındaki parlaklık tepeleri, elle eşlenmiş), durma çizgileri iki uç
noktasıyla verilir. Hepsi kalibrasyonla (G⁻¹) yere, kavşak merkezli metreye çevrilir ve
geometri.py ile aynı biçimde yazılır: e, n, gelen/giden {n, merkez, genislik}, durma_m.

Kullanım: python scripts/geometri_fotodan.py [--yaz]   (--yaz: data/geometri.json'un yerine geçer)
"""

import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trafik import geometri  # noqa: E402

# Her kol: enine kesit ekseni ('x' = kesit sabit x'te, sınırlar y; 'y' = sabit y'de, sınırlar x),
# yakın ve uzak kesit konumu, o kesitlerdeki gelen ve giden şerit sınırları (piksel, sıralı;
# gelen ve giden kendi içinde kenardan kenara) ve durma çizgisinin iki ucu (piksel).
KOLLAR = {
    # kuzey kolu (sağda): gelen üstte (güneye giden araçların sağı batı = yukarı)
    "K": {"eksen": "x", "kesit": (395, 625),
          "gelen": ([118.0, 133.6, 148.8, 165.4, 182.5, 199.5], [124.0, 139.0, 154.0, 168.4, 183.3, 198.2]),
          "giden": ([199.5, 215.6, 232.9, 250.3], [198.2, 213.1, 228.6, 245.6]),
          "durma": ((373.0, 100.0), (373.0, 199.0))},
    # güney kolu (solda): gelen altta; iki sarı arasında ~3 m boyalı orta refüj
    "G": {"eksen": "x", "kesit": (125, 15),
          "gelen": ([186.5, 204.5, 222.7, 241.8, 261.9, 281.0], [186.9, 205.6, 225.0, 245.5, 264.6, 283.2]),
          "giden": ([112.5, 131.0, 148.8, 170.8], [114.2, 132.8, 151.0, 171.3]),
          "durma": ((150.0, 187.0), (142.0, 287.0))},
    # batı kolu (üstte): gelen solda (doğuya, aşağı giden araçların sağı ekranın solu)
    "B": {"eksen": "y", "kesit": (42, 8),
          "gelen": ([202.6, 220.5, 237.6, 254.1], [200.7, 218.4, 235.5, 251.6]),
          "giden": ([254.1, 273.5, 296.9, 321.4], [251.6, 272.5, 295.0, 318.4]),
          "durma": ((202.0, 67.0), (254.0, 60.5))},
    # doğu kolu (altta): gelen sağda; aradaki koyu şerit orta refüj. Gidenin en dışı, güneyden
    # sağa dönenlerin kıvrık serbest sağ şeridi (kavşak yakınında ayrı şerit, sonra birleşir);
    # SUMO'da düz üçüncü şerit olarak alınır, yoksa sağa dönenler ve soldan gelenler iki şeride
    # sıkışıp ara sokağı tıkıyor.
    "D": {"eksen": "y", "kesit": (360, 450),
          "gelen": ([280.0, 299.2, 319.3, 339.4], [285.0, 304.4, 325.0, 345.6]),
          "giden": ([199.0, 219.1, 240.7, 261.8], [205.0, 226.2, 244.9, 266.9]),
          "durma": ((278.0, 292.0), (345.0, 288.0))},
}


def piksel(eksen, kesit, deger):
    return (kesit, deger) if eksen == "x" else (deger, kesit)


def yere(Ginv, p):
    v = Ginv @ [p[0], p[1], 1.0]
    return v[:2] / v[2]


def olc(G):
    Ginv = np.linalg.inv(G)
    kollar, rapor = {}, {}
    for k, c in KOLLAR.items():
        ek, (k0, k1) = c["eksen"], c["kesit"]
        # her sınır çizgisinin yakın ve uzak ucu, yerde
        hatlar = {t: [(yere(Ginv, piksel(ek, k0, a)), yere(Ginv, piksel(ek, k1, b)))
                      for a, b in zip(*c[t])] for t in ("gelen", "giden")}
        tum = hatlar["gelen"] + hatlar["giden"]
        # kol yönü: tüm sınırların ortalama yönü, merkezden dışarı
        yon = np.mean([(q - p) / np.linalg.norm(q - p) for p, q in tum], axis=0)
        e = yon / np.linalg.norm(yon)
        orta = np.mean([p for p, _ in tum], axis=0)
        if e @ orta < 0:
            e = -e
        n = np.array([-e[1], e[0]])
        # durma çizgisi: kol ekseni boyunca gelen şeritlerin ortasındaki uzaklık
        d0, d1 = (yere(Ginv, p) for p in c["durma"])
        s_hat = {t: [float(((p + q) / 2) @ n) for p, q in h] for t, h in hatlar.items()}
        sapma = {t: [round(float((q - p) @ n), 2) for p, q in h] for t, h in hatlar.items()}  # yakın-uzak yanal fark
        durma_m = float(np.mean([d0 @ e, d1 @ e]))
        g = {"e": e.round(4).tolist(), "n": n.round(4).tolist(), "durma_m": round(durma_m, 2), "ornek": 0}
        for t in ("gelen", "giden"):
            s = sorted(s_hat[t])
            gen = [b - a for a, b in zip(s, s[1:])]
            g[t] = {"n": len(gen), "merkez": [round((a + b) / 2, 2) for a, b in zip(s, s[1:])],
                    "genislik": round(float(np.mean(gen)), 3)}
            rapor[f"{k}_{t}"] = {"genislikler_m": [round(x, 2) for x in gen], "yakin_uzak_yanal_fark_m": sapma[t]}
        kollar[k] = g
        rapor[k] = {"aci_der": round(float(np.degrees(np.arctan2(e[1], e[0]))), 1), "durma_m": g["durma_m"]}
    return {"kollar": kollar, "kaynak": "araçsız yol fotoğrafındaki boya (scripts/geometri_fotodan.py)"}, rapor


def main():
    G = geometri.goruntu_donusumu()
    geo, rapor = olc(G)
    print(json.dumps(rapor, indent=1, ensure_ascii=False))
    Path("data/geometri_foto.json").write_text(
        json.dumps({**geo, "kavsak": geometri.kavsak_cokgeni(geo)}, indent=2, ensure_ascii=False), encoding="utf-8")
    if "--yaz" in sys.argv:
        if not Path("data/geometri_izden.json").exists():
            shutil.copy("data/geometri.json", "data/geometri_izden.json")
        geometri.kaydet(geo)
        print("data/geometri.json güncellendi (eskisi data/geometri_izden.json)")


if __name__ == "__main__":
    main()
