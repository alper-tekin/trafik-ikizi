"""SAM tespitlerinden kareler arası araç takibi (saha koordinatlarında).

Her tespit kalibrasyonla sahaya (ft) izdüşülür. İzler sabit hızla ileri
tahmin edilir ve tespitlerle Macar algoritmasıyla eşlenir:
  - Önce oturmuş izler (en az `oturma` kez görülen), sonra yeni izler eşlenir;
    böylece yeni açılmış bir iz, yanındaki oturmuş aracın tespitini çalamaz.
  - Görülmeyen izin hızı sönümlenir; kırmızıda duran araç tahminde kaymaz.
  - Sonunda kopuk izler birleştirilir: biri bittikten kısa süre sonra, tahmin
    edilen konumun yakınında başlayan iz aynı araç sayılır.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


@dataclass
class Iz:
    no: int
    konum: np.ndarray
    hiz: np.ndarray = field(default_factory=lambda: np.zeros(2))
    kayip: int = 0
    gorulme: int = 1
    gecmis: list = field(default_factory=list)


def sahaya(H_px2saha: np.ndarray, kutular: np.ndarray) -> np.ndarray:
    merkez = np.c_[(kutular[:, 0] + kutular[:, 2]) / 2, (kutular[:, 1] + kutular[:, 3]) / 2]
    return cv2.perspectiveTransform(merkez.reshape(-1, 1, 2).astype(np.float64), H_px2saha).reshape(-1, 2)


def kutu_boyu(H_px2saha: np.ndarray, kutular: np.ndarray) -> np.ndarray:
    """Kutunun yerdeki uzun kenarı (ft). Kollar görüntü eksenlerine yakın olduğu için araç
    kutunun bir kenarı boyunca uzanır; otobüs/kamyonu arabadan ayırmak için kullanılır."""
    x1, y1, x2, y2 = kutular[:, 0], kutular[:, 1], kutular[:, 2], kutular[:, 3]
    k = np.stack([np.c_[x1, y1], np.c_[x2, y1], np.c_[x1, y2]], axis=1).astype(np.float64)
    y = cv2.perspectiveTransform(k.reshape(-1, 1, 2), H_px2saha).reshape(-1, 3, 2)
    return np.maximum(np.linalg.norm(y[:, 1] - y[:, 0], axis=1), np.linalg.norm(y[:, 2] - y[:, 0], axis=1))


def _esle(izler, indeksler, tahmin, noktalar, bos_nokta, kapi_ft):
    """Verilen izleri boştaki noktalarla eşler; (iz indeksi, nokta indeksi) listesi döner."""
    if not indeksler or not bos_nokta:
        return []
    bos = sorted(bos_nokta)
    maliyet = np.linalg.norm(tahmin[indeksler][:, None, :] - noktalar[bos][None, :, :], axis=2)
    satir, sutun = linear_sum_assignment(maliyet)
    return [(indeksler[i], bos[j]) for i, j in zip(satir, sutun) if maliyet[i, j] <= kapi_ft]


def takip_et(
    kareler: list[tuple[int, np.ndarray]],
    H_px2saha: np.ndarray,
    fps: float = 10.0,
    kapi_ft: float = 10.0,
    en_cok_kayip: int = 10,
    en_az_gorulme: int = 5,
    oturma: int = 3,
    sonum: float = 0.7,
    birlestir_kare: int = 30,
    birlestir_ft: float = 15.0,
) -> pd.DataFrame:
    """kareler: (kare_no, kutular[N,4+]) listesi, kare sırasına göre.

    Dönüş: iz, kare, x, y (saha ft), boy (kutunun yerdeki uzun kenarı, ft) satırları;
    kısa ömürlü izler atılır.
    """
    izler: list[Iz] = []
    biten: list[Iz] = []
    sayac = 0
    onceki = None
    for kare_no, kutular in kareler:
        dt = 0.0 if onceki is None else (kare_no - onceki) / fps
        onceki = kare_no
        noktalar = sahaya(H_px2saha, kutular) if len(kutular) else np.empty((0, 2))
        boylar = kutu_boyu(H_px2saha, kutular) if len(kutular) else np.empty(0)
        tahmin = np.array([iz.konum + iz.hiz * dt for iz in izler]).reshape(-1, 2)

        bos_nokta = set(range(len(noktalar)))
        oturmus = [i for i, iz in enumerate(izler) if iz.gorulme >= oturma]
        yeni = [i for i, iz in enumerate(izler) if iz.gorulme < oturma]
        eslesme = _esle(izler, oturmus, tahmin, noktalar, bos_nokta, kapi_ft)
        bos_nokta -= {j for _, j in eslesme}
        eslesme += _esle(izler, yeni, tahmin, noktalar, bos_nokta, kapi_ft)
        bos_nokta -= {j for _, j in eslesme}

        eslenen_iz = set()
        for i, j in eslesme:
            iz = izler[i]
            yeni_hiz = (noktalar[j] - iz.konum) / dt if dt > 0 else iz.hiz
            iz.hiz = 0.6 * iz.hiz + 0.4 * yeni_hiz if iz.gorulme > 1 else yeni_hiz
            iz.konum = noktalar[j]
            iz.kayip = 0
            iz.gorulme += 1
            iz.gecmis.append((kare_no, *iz.konum, boylar[j]))
            eslenen_iz.add(i)

        kalan = []
        for i, iz in enumerate(izler):
            if i not in eslenen_iz:
                iz.kayip += 1
                iz.konum = tahmin[i]
                iz.hiz = iz.hiz * sonum
            (biten if iz.kayip > en_cok_kayip else kalan).append(iz)
        izler = kalan

        for j in sorted(bos_nokta):
            sayac += 1
            izler.append(Iz(sayac, noktalar[j].copy(), gecmis=[(kare_no, *noktalar[j], boylar[j])]))

    tumu = [iz for iz in biten + izler if iz.gorulme >= en_az_gorulme]
    satirlar = [(iz.no, k, x, y, b) for iz in tumu for k, x, y, b in iz.gecmis]
    df = pd.DataFrame(satirlar, columns=["iz", "kare", "x", "y", "boy"])
    return birlestir(df, fps, birlestir_kare, birlestir_ft)


def birlestir(df: pd.DataFrame, fps: float, en_cok_kare: int, esik_ft: float) -> pd.DataFrame:
    """Biten bir izi, kısa süre sonra tahmini konumunun yakınında başlayan izle birleştirir."""
    ozet = []
    for no, g in df.groupby("iz", sort=False):
        g = g.sort_values("kare")
        son = g.tail(5)
        sure = (son.kare.iloc[-1] - son.kare.iloc[0]) / fps
        hiz = (son[["x", "y"]].iloc[-1].to_numpy() - son[["x", "y"]].iloc[0].to_numpy()) / sure if sure > 0 else np.zeros(2)
        ozet.append((no, g.kare.iloc[0], g.kare.iloc[-1], g[["x", "y"]].iloc[0].to_numpy(),
                     g[["x", "y"]].iloc[-1].to_numpy(), hiz))
    baslangic = sorted(ozet, key=lambda o: o[1])

    ebeveyn = {o[0]: o[0] for o in ozet}

    def kok(n):
        while ebeveyn[n] != n:
            ebeveyn[n] = ebeveyn[ebeveyn[n]]
            n = ebeveyn[n]
        return n

    kullanildi = set()
    for no, _, bitis, _, son_konum, hiz in sorted(ozet, key=lambda o: o[2]):
        en_iyi, en_iyi_mesafe = None, esik_ft
        for no2, bas2, _, ilk_konum, _, _ in baslangic:
            if bas2 <= bitis:
                continue
            if bas2 - bitis > en_cok_kare:
                break
            if no2 in kullanildi:
                continue
            tahmin = son_konum + hiz * (bas2 - bitis) / fps
            mesafe = np.linalg.norm(tahmin - ilk_konum)
            if mesafe < en_iyi_mesafe:
                en_iyi, en_iyi_mesafe = no2, mesafe
        if en_iyi is not None:
            kullanildi.add(en_iyi)
            ebeveyn[kok(en_iyi)] = kok(no)

    return df.assign(iz=df.iz.map(kok))
