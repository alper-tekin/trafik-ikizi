"""SAM tespitlerinden kareler arası araç takibi (saha koordinatlarında).

Her tespit kalibrasyonla sahaya (ft) izdüşülür. İzler sabit hızla ileri
tahmin edilir ve tespitlerle Macar algoritmasıyla eşlenir. Eşlenmeyen tespit
yeni iz açar; birkaç kare görünmeyen iz kapanır.
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


def takip_et(
    kareler: list[tuple[int, np.ndarray]],
    H_px2saha: np.ndarray,
    fps: float = 10.0,
    kapi_ft: float = 12.0,
    en_cok_kayip: int = 5,
    en_az_gorulme: int = 5,
) -> pd.DataFrame:
    """kareler: (kare_no, kutular[N,4+]) listesi, kare sırasına göre.

    Dönüş: iz, kare, x, y (saha ft) satırları; kısa ömürlü izler atılır.
    """
    izler: list[Iz] = []
    biten: list[Iz] = []
    sayac = 0
    onceki = None
    for kare_no, kutular in kareler:
        dt = 0.0 if onceki is None else (kare_no - onceki) / fps
        onceki = kare_no
        noktalar = sahaya(H_px2saha, kutular) if len(kutular) else np.empty((0, 2))
        tahmin = np.array([iz.konum + iz.hiz * dt for iz in izler]).reshape(-1, 2)

        eslenen_iz, eslenen_nokta = set(), set()
        if len(izler) and len(noktalar):
            maliyet = np.linalg.norm(tahmin[:, None, :] - noktalar[None, :, :], axis=2)
            satir, sutun = linear_sum_assignment(maliyet)
            for i, j in zip(satir, sutun):
                if maliyet[i, j] > kapi_ft:
                    continue
                iz = izler[i]
                yeni_hiz = (noktalar[j] - iz.konum) / dt if dt > 0 else iz.hiz
                iz.hiz = 0.6 * iz.hiz + 0.4 * yeni_hiz if iz.gorulme > 1 else yeni_hiz
                iz.konum = noktalar[j]
                iz.kayip = 0
                iz.gorulme += 1
                iz.gecmis.append((kare_no, *iz.konum))
                eslenen_iz.add(i)
                eslenen_nokta.add(j)

        kalan = []
        for i, iz in enumerate(izler):
            if i not in eslenen_iz:
                iz.kayip += 1
                iz.konum = tahmin[i]
            (biten if iz.kayip > en_cok_kayip else kalan).append(iz)
        izler = kalan

        for j in range(len(noktalar)):
            if j not in eslenen_nokta:
                sayac += 1
                izler.append(Iz(sayac, noktalar[j].copy(), gecmis=[(kare_no, *noktalar[j])]))

    satirlar = [
        (iz.no, k, x, y)
        for iz in biten + izler
        if iz.gorulme >= en_az_gorulme
        for k, x, y in iz.gecmis
    ]
    return pd.DataFrame(satirlar, columns=["iz", "kare", "x", "y"])
