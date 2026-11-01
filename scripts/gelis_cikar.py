"""Videodaki her aracın ikize giriş bilgisi: ne zaman, nerede, hangi şeritte, hangi hızla
girdiği ve nereye gittiği. İkiz bu listeyle videodaki trafiği araç araç yeniden oynatır
(sumo_ag.gercek_talep_yaz); rastgele gelişler ise seçenek olarak kalır.

Her iz için giriş kolunda, durma çizgisinin gerisinde ilk görüldüğü nokta alınır. Konum
+ ağa çevrilir (kolun gerçek yönüyle dik yönü arasındaki küçük açı kadar döndürülür),
kol ekseni boyunca uzaklık ve yanal konumdan şerit bulunur. Şerit aracın hareketine izin
vermiyorsa en yakın izin veren şerit seçilir (sumo_ag.SERIT_HAREKET).

Çıktı: data/gelisler.parquet (arac, giris, cikis, hareket, buyuk, t, d_m, serit, hiz)

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/gelis_cikar.py
"""

import numpy as np
import pandas as pd

from trafik import geometri, olcum
from trafik.akis import kol
from trafik.sumo_ag import HAREKET_HARF, SERIT_HAREKET


def artiya(u: np.ndarray, w: np.ndarray, g: dict) -> tuple[np.ndarray, np.ndarray]:
    """Gerçek konumu + ağa çevirir (arayüzdeki artiya ile aynı, kol içinde tam açı farkı)."""
    ge = g.get("gercek_e", g["e"])
    fark = np.arctan2(g["e"][1], g["e"][0]) - np.arctan2(ge[1], ge[0])
    c, s = np.cos(fark), np.sin(fark)
    return u * c - w * s, u * s + w * c


def main() -> None:
    geo = geometri.yukle()["kollar"]
    akis = pd.read_parquet("data/akis_izler.parquet")
    d = olcum.noktalar_izden(pd.read_parquet("data/izler_kamera2.parquet"), akis)
    d = d.merge(akis[["iz", "cikis", "buyuk"]].rename(columns={"iz": "arac"}), on="arac")
    d = d[kol(d[["u", "w"]].to_numpy()) == d.giris.to_numpy()].sort_values(["arac", "t"])

    satir = []
    for arac, p in d.groupby("arac"):
        k = p.giris.iloc[0]
        g = geo[k]
        u, w = artiya(p.u.to_numpy(), p.w.to_numpy(), g)
        mesafe = u * g["e"][0] + w * g["e"][1]
        yanal = u * g["n"][0] + w * g["n"][1]
        geride = np.flatnonzero(mesafe > g["durma_m"] + 1)
        i = geride[0] if len(geride) else 0
        # gelen şeritler n'nin negatif tarafına doğru sağa dizilir: şerit 0 = en sağ = en küçük yanal
        merkez = np.sort(g["gelen"]["merkez"])
        serit = int(np.argmin(np.abs(merkez - yanal[i])))
        harf = HAREKET_HARF[int(p.hareket.iloc[0])]
        if not g.get("cep"):  # cepli kolda şerit hareketi kurulurken (cep/uzak kısım) seçilir
            izinli = [j for j, h in enumerate(SERIT_HAREKET[k][:len(merkez)]) if harf in h]
            serit = min(izinli, key=lambda j: abs(j - serit)) if izinli else serit
        satir.append({
            "arac": int(arac), "giris": k, "cikis": p.cikis.iloc[0], "hareket": int(p.hareket.iloc[0]),
            "buyuk": bool(p.buyuk.iloc[0]), "t": round(float(p.t.iloc[i]), 1),
            "d_m": round(float(max(mesafe[i], g["durma_m"] + 1)), 1), "serit": serit,
            "hiz": round(float(np.nan_to_num(p.hiz.iloc[i])), 1),
        })
    out = pd.DataFrame(satir).sort_values("t")
    out.to_parquet("data/gelisler.parquet")
    print(f"{len(out)} araç; kuyrukta başlayan (ilk 1 s): {(out.t < 1).sum()}; "
          f"ilk görüldüğü uzaklık medyanı {out.d_m.median():.0f} m")
    print(out.groupby("giris").size().to_dict())


if __name__ == "__main__":
    main()
