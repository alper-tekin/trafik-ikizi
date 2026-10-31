"""Video izleri, NGSIM ve SUMO için aynı tanımla ölçülen kavşak göstergeleri.

Hepsi kavşak merkezli yerel düzlemde (u kuzey, w doğu, metre):
  - kuyruk: yaklaşım kolunda, merkeze 75 m'den yakın, hızı 1 m/s altındaki araç sayısı
  - geçiş süresi: aracın merkeze 60 m'lik çemberin içinde geçirdiği süre
Kuyruklar sinyal döngüsü içinde katlanır (döngü başı = kuzey-güney yeşili),
böylece farklı zaman eksenleri karşılaştırılabilir.
"""

import numpy as np
import pandas as pd

from trafik.akis import kol, yerel

FT = 0.3048
# Kamera kavşağın çevresinde ~75 m'ye kadar görüyor; geçiş çemberi bunun içinde kalmalı.
KUYRUK_M, GECIS_M, DURGUN_MS = 75.0, 40.0, 1.0


def noktalar_izden(izler: pd.DataFrame, akis: pd.DataFrame, fps: float = 10.0) -> pd.DataFrame:
    """Video izleri -> t, arac, giris kolu, u, w (m), hiz (m/s)."""
    d = izler.merge(akis[["iz", "giris", "yon", "hareket"]], on="iz").sort_values(["iz", "kare"])
    uw = yerel(d[["x", "y"]].to_numpy()) * FT
    d = d.assign(t=d.kare / fps, u=uw[:, 0], w=uw[:, 1])
    dt = d.groupby("iz").t.diff()
    yol = np.hypot(d.groupby("iz").u.diff(), d.groupby("iz").w.diff())
    hiz = (yol / dt).groupby(d.iz).transform(lambda s: s.rolling(3, min_periods=1, center=True).median())
    return d.assign(hiz=hiz.bfill()).rename(columns={"iz": "arac"})[
        ["t", "arac", "giris", "yon", "hareket", "u", "w", "hiz"]]


def noktalar_ngsimden(g: pd.DataFrame, ofset: float, sure_s: float) -> pd.DataFrame:
    g = g[(g.t >= ofset) & (g.t <= sure_s + ofset)].sort_values(["vehicle_id", "t"])
    # NGSIM araç kimlikleri tekrar kullanılıyor; 1 s'den uzun boşluk yeni araç demek.
    yeni = g.groupby("vehicle_id").t.diff().fillna(99) > 1.0
    g = g.assign(vehicle_id=g.vehicle_id.astype(str) + "_" + yeni.groupby(g.vehicle_id).cumsum().astype(str))
    araclar = g[g.int_id == 2].groupby("vehicle_id").agg(yon=("direction", "first"), hareket=("movement", "first"))
    g = g[g.vehicle_id.isin(araclar.index)].merge(araclar, left_on="vehicle_id", right_index=True)
    uw = yerel(g[["global_x", "global_y"]].to_numpy()) * FT
    giris = {2: "G", 4: "K", 1: "B", 3: "D"}
    return pd.DataFrame({
        "t": g.t - ofset, "arac": g.vehicle_id, "giris": g.yon.map(giris), "yon": g.yon,
        "hareket": g.hareket, "u": uw[:, 0], "w": uw[:, 1], "hiz": g.v_vel * FT,
    })


def yaklasimda(d: pd.DataFrame) -> pd.Series:
    """Nokta aracın giriş kolunda ve kavşağa henüz girmemiş mi."""
    k = kol(d[["u", "w"]].to_numpy())
    return (k == d.giris.to_numpy()) & (np.hypot(d.u, d.w) < KUYRUK_M) & (np.hypot(d.u, d.w) > 12)


def kuyruk_profili(d: pd.DataFrame, dongu: float, faz0: float, adim: float = 1.0) -> pd.DataFrame:
    """Döngü içindeki her saniye için kol başına ortalama durgun araç sayısı."""
    q = d[yaklasimda(d) & (d.hiz < DURGUN_MS)]
    zaman = np.round(q.t / adim) * adim
    say = q.groupby([zaman, q.giris]).arac.nunique().unstack(fill_value=0)
    tum = np.round(np.arange(np.ceil(d.t.min()), np.floor(d.t.max()), adim) / adim) * adim
    say = say.reindex(tum, fill_value=0)
    faz = ((say.index - faz0) % dongu).astype(int)
    return say.groupby(faz).mean()


def gecis_sureleri(d: pd.DataFrame) -> pd.DataFrame:
    ic = d[np.hypot(d.u, d.w) < GECIS_M]
    s = ic.groupby("arac").agg(t0=("t", "min"), t1=("t", "max"), yon=("yon", "first"), hareket=("hareket", "first"))
    # Çemberin iki yanını da görmeyen (görüntüde kesilen) araçlar atılır.
    tam = d.groupby("arac").apply(lambda g: (np.hypot(g.u, g.w).iloc[[0, -1]] > GECIS_M).all())
    s = s[s.index.isin(tam[tam].index)]
    return s.assign(sure=s.t1 - s.t0)
