"""İzlerden kavşak akış verisi: hangi koldan girip hangi kola çıktığı ve hareketi.

Kavşak merkezi ve Lankershim ekseni NGSIM verisinden alınır. Saha düzlemi
(u: Lankershim boyunca kuzeye, w: ona dik doğuya) dört kola bölünür.
NGSIM yön kodları: 1 doğuya, 2 kuzeye, 3 batıya, 4 güneye giden.
NGSIM hareket kodları: 1 düz, 2 sol, 3 sağ.
"""

import numpy as np
import pandas as pd

MERKEZ = np.array([6452082.3, 1873173.3])  # kavşak 2, int_id == 2 noktalarının ortalaması
KUZEY = np.array([0.368, 0.930])  # Lankershim ana ekseni
DOGU = np.array([KUZEY[1], -KUZEY[0]])

# Kol -> o koldan giren aracın gidiş yönü (NGSIM kodu)
GIRIS_YONU = {"G": 2, "K": 4, "B": 1, "D": 3}
HAREKET_ADI = {1: "düz", 2: "sol", 3: "sağ"}
# Otobüs/kamyon: izin kutu boyu medyanı (yerde, ft) bu eşiğin üstündeyse. Eşik, izler
# NGSIM'in araç sınıfıyla eşlenerek seçildi: arabalarda kutu boyu medyanı 14,8 ft, büyük
# araçlarda 22 ft (NGSIM'in "kamyon" sınıfında küçük kamyonetler de var). 20 ft'te 63 iz
# büyük sayılıyor, gerçekte 71 (45'i doğru); toplam büyük araç payı en iyi bu eşikte tutuyor.
BUYUK_FT = 20.0


def talep_sayimlari(akis: pd.DataFrame) -> dict:
    """SUMO talebi için sayımlar: (yön, hareket) -> araba sayısı, (yön, hareket, "b") ->
    otobüs/kamyon sayısı. 'buyuk' sütunu yoksa hepsi araba sayılır."""
    buyuk = akis["buyuk"].astype(bool) if "buyuk" in akis else pd.Series(False, index=akis.index)
    s = akis[~buyuk].groupby(["yon", "hareket"]).size().to_dict()
    s.update({(y, h, "b"): n for (y, h), n in akis[buyuk].groupby(["yon", "hareket"]).size().items()})
    return s


def yerel(xy: np.ndarray) -> np.ndarray:
    """Saha (ft) -> (u kuzey, w doğu), merkez kavşak."""
    p = np.asarray(xy, dtype=float) - MERKEZ
    return np.c_[p @ KUZEY, p @ DOGU]


def kol(uw: np.ndarray) -> np.ndarray:
    u, w = uw[:, 0], uw[:, 1]
    return np.where(np.abs(u) >= np.abs(w), np.where(u >= 0, "K", "G"), np.where(w >= 0, "D", "B"))


def hareket(giris: str, cikis: str) -> int | None:
    """Giriş ve çıkış kolundan NGSIM hareket kodu; geri dönüş/eksikse None."""
    sira = ["K", "D", "G", "B"]  # saat yönünde
    if giris == cikis:
        return None
    fark = (sira.index(cikis) - sira.index(giris)) % 4
    # Kuzey kolundan giren (güneye giden) araç doğu koluna çıkarsa sola dönmüştür.
    return {2: 1, 1: 2, 3: 3}[fark]


def siniflandir(izler: pd.DataFrame, min_uzaklik_ft: float = 60.0) -> pd.DataFrame:
    """Her iz için giriş/çıkış kolu, yön ve hareket. Kavşağın iki yanını görmeyen izler atılır."""
    satirlar = []
    for no, g in izler.sort_values("kare").groupby("iz"):
        uw = yerel(g[["x", "y"]].to_numpy())
        r = np.hypot(uw[:, 0], uw[:, 1])
        # Sağa dönenler köşeyi keser, merkeze 55-75 ft'ten fazla yaklaşmaz.
        if r[0] < min_uzaklik_ft or r[-1] < min_uzaklik_ft or r.min() > 90:
            continue
        k = kol(uw[[0, -1]])
        h = hareket(k[0], k[1])
        if h is None:
            continue
        gecis = g.kare.iloc[int(np.argmin(r))]
        satirlar.append((no, k[0], k[1], GIRIS_YONU[k[0]], h, gecis))
    return pd.DataFrame(satirlar, columns=["iz", "giris", "cikis", "yon", "hareket", "gecis_kare"])
