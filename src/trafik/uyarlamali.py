"""Uyarlamalı sinyal: sabit bir plan yerine, kameranın gördüğüne göre her saniye karar verir.

Kamera her aracın kaç saniyedir beklediğini biliyor (arayüzdeki sayaçlar); denetleyici
yeşili bekleyenlere göre verir. İki kural:
  saf        en uzun bekleyen tek aracın yönü (o araca hangi faz yeşil veriyorsa)
  agirlikli  bekleyenlerin bekleme sürelerinin toplamı (uzun bekleme x çok araç)
Fazlar sabit plandakilerle aynı: güneye düz+sol, Lankershim iki yön (sollar izinli), ara sokak.

Kurallar (gerçek bir denetleyicinin uyması gerekenler):
  - yeşil, o fazın durma çizgisine 40 m içinde araç oldukça sürer (en kısa 7 s, ara sokak
    10 s; en uzun 60 s); talep bitince sıradaki faz kurala göre seçilir
  - her geçişte yeşili kaybeden gruplara 3 s sarı, sonra 1 s tüm-kırmızı
  - yaya butonu varsayımı: ara sokağa en az 120 s'de bir 30 s (yayalar Lankershim'i geçer),
    Lankershim iki yön fazına en az 120 s'de bir 18 s (yayalar ara sokağı geçer); bekleyen
    yaya hizmeti süresi dolunca o faz önceliklidir
Bekleme: aracın giriş kolunda hızı 0,5 m/s altında geçen toplam süre (arayüzdeki sayaçla aynı).
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from trafik.degerlendir import ISINMA_S, KOL_ADI, SURE_S, HAREKET_ADI
from trafik.simule import GIRIS_YON, HAREKET
from trafik.sumo_ag import SARI, TUM_KIRMIZI, VARSAYILAN_GELIS, _ortam, _baglanti_hareketleri, kur, plan_videodan, sinyal_grubu
from trafik.sonuclar import ozetle, talep_yolu, trip_oku

FAZLAR = {
    "guney": ("Southbound through + left", {"ks": "G", "gd": "G"}),
    "ortak": ("Lankershim, both directions", {"gd": "G", "kd": "G", "ks": "g", "gs": "g"}),
    "ara": ("Cross street", {"db": "G"}),
}
EN_KISA = {"guney": 7.0, "ortak": 7.0, "ara": 10.0}
EN_UZUN = 60.0
YAYA_ARALIK = 120.0
YAYA_SURE = {"ara": 30.0, "ortak": 18.0}
DURGUN_MS = 0.5
TALEP_M = 40.0  # durma çizgisine bu kadar yakın araç varsa yeşil sürer (kuyruk boşalıyor ya da araç geliyor)
ADIM = 0.5


def _durum(gruplar: list[str], harfler: list[str], yesil: dict, sari: set = frozenset()) -> str:
    """Bağlantı başına durum harfi; sağa dönüşler kırmızıda yol vererek döner (ABD kuralı)."""
    out = []
    for g, h in zip(gruplar, harfler):
        c = "y" if g in sari else yesil.get(g, "r")
        out.append("s" if c == "r" and h == "r" else c)
    return "".join(out)


def calistir(cfg: Path, kural: str, tohum: int = 1, kayit: bool = False) -> dict:
    """Simülasyonu uyarlamalı denetleyiciyle koşturur. Dönüş: tripinfo yolu ve (kayit=True ise)
    simule.calistir biçiminde araç noktaları + kare başına sinyal durumu ve faz adı."""
    import sumo
    import traci

    ag = cfg.parent / "ag.net.xml"
    bag = _baglanti_hareketleri(ag)
    gruplar = [sinyal_grubu(k, h) for k, h in bag]
    harfler = [h for _, h in bag]
    trip = f"trip_uyar_{kural}_{tohum}.xml"
    eski = os.getcwd()
    os.chdir(cfg.parent)
    env = _ortam()
    os.environ.pop("SUMO_HOME", None)
    noktalar, durumlar = [], []
    try:
        traci.start([str(Path(sumo.SUMO_HOME) / "bin" / "sumo"), "-c", cfg.name, "--seed", str(tohum),
                     "--tripinfo-output.write-unfinished", "true", "--tripinfo-output.write-undeparted", "true",
                     "--tripinfo-output", trip, "--no-warnings"])
        tls = traci.trafficlight.getIDList()[0]
        mx, my = traci.junction.getPosition("M")
        bekleme: dict[str, float] = {}
        faz, faz_bas = "ortak", 0.0          # yeşilin başladığı an
        gecis: list = []                      # sıradaki geçiş adımları: (bitiş, durum, ad)
        hedef = None
        son_yaya = {"ara": 0.0, "ortak": 0.0}
        traci.trafficlight.setRedYellowGreenState(tls, _durum(gruplar, harfler, FAZLAR[faz][1]))

        def hizmet(faz_ad: str, kol: str, harf: str) -> bool:
            return FAZLAR[faz_ad][1].get(sinyal_grubu(kol, harf), "r") in ("G", "g")

        bitis_s = float(ET.parse(cfg.name).getroot().find("time/end").get("value"))
        while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < bitis_s:
            traci.simulationStep()
            t = traci.simulation.getTime()
            # bekleme sayaçları: giriş kolunda, durgunken
            bekleyen, yakindakiler = [], []
            for v in traci.vehicle.getIDList():
                if not traci.vehicle.getRoadID(v).endswith("_gir"):
                    bekleme.pop(v, None)
                    continue
                serit = traci.vehicle.getLaneID(v)
                kalan = traci.lane.getLength(serit) - traci.vehicle.getLanePosition(v)
                if traci.vehicle.getRoadID(v).endswith("_uzak_gir"):
                    kalan += traci.lane.getLength(f"{v[0]}_gir_1")  # cep kısmı
                if kalan < TALEP_M:
                    yakindakiler.append(v)
                if traci.vehicle.getSpeed(v) < DURGUN_MS:
                    bekleme[v] = bekleme.get(v, 0.0) + ADIM
                if bekleme.get(v, 0.0) > 0:
                    akis = v.split(".")[0]
                    bekleyen.append((akis[0], akis[1], bekleme[v]))

            if gecis:  # sarı / tüm-kırmızı sürüyor
                if t >= gecis[0][0]:
                    gecis.pop(0)
                    if gecis:
                        traci.trafficlight.setRedYellowGreenState(tls, gecis[0][1])
                    else:
                        faz, faz_bas = hedef, t
                        traci.trafficlight.setRedYellowGreenState(tls, _durum(gruplar, harfler, FAZLAR[faz][1]))
            else:
                sure = t - faz_bas
                puan = {}
                for f in FAZLAR:
                    w = [b for k, h, b in bekleyen if hizmet(f, k, h)]
                    puan[f] = (max(w) if w else 0.0) if kural == "saf" else sum(w)
                en_az = max(EN_KISA[faz], YAYA_SURE.get(faz, 0) if son_yaya.get(faz, 1e9) <= faz_bas - YAYA_ARALIK else 0)
                if faz in YAYA_SURE and sure >= YAYA_SURE[faz]:
                    son_yaya[faz] = t
                if sure >= en_az:
                    gecikmis = [f for f in YAYA_SURE if f != faz and t - son_yaya[f] > YAYA_ARALIK]
                    digerleri = {f: p for f, p in puan.items() if f != faz}
                    en_iyi = max(digerleri, key=digerleri.get)
                    # Yeşil, kendi kuyruğu boşalırken ya da durma çizgisine TALEP_M içinde araç
                    # gelirken sürer (her geçiş 4 s kaybettirir); talep bitince ya da en uzun
                    # yeşil dolunca sıradaki faz kurala göre seçilir.
                    talep = any(hizmet(faz, v.split(".")[0][0], v.split(".")[0][1]) for v in yakindakiler)
                    if gecikmis:
                        yeni = gecikmis[0]
                    elif (sure >= EN_UZUN or not talep) and digerleri[en_iyi] > 0:
                        yeni = en_iyi
                    else:
                        yeni = None
                    if yeni:
                        eski_y, yeni_y = FAZLAR[faz][1], FAZLAR[yeni][1]
                        kaybeden = {g for g, c in eski_y.items() if c in ("G", "g") and yeni_y.get(g, "r") != c
                                    and not (c == "G" and yeni_y.get(g) == "g")}
                        ortak = {g: c for g, c in eski_y.items() if g not in kaybeden and g in yeni_y}
                        gecis = [(t + SARI, _durum(gruplar, harfler, eski_y, kaybeden), "Yellow"),
                                 (t + SARI + TUM_KIRMIZI, _durum(gruplar, harfler, ortak), "All red")]
                        hedef = yeni
                        traci.trafficlight.setRedYellowGreenState(tls, gecis[0][1])
            if kayit and t >= ISINMA_S:
                ad = gecis[0][2] if gecis else FAZLAR[faz][0]
                durumlar.append((t - ISINMA_S, traci.trafficlight.getRedYellowGreenState(tls), ad))
                for v in traci.vehicle.getIDList():
                    x, y = traci.vehicle.getPosition(v)
                    noktalar.append((t - ISINMA_S, v, x - mx, y - my, traci.vehicle.getSpeed(v), traci.vehicle.getAngle(v)))
        traci.close()
    finally:
        os.chdir(eski)
        os.environ.clear()
        os.environ.update(env)

    sonuc = {"trip": cfg.parent / trip}
    if kayit:
        d = pd.DataFrame(noktalar, columns=["t", "arac", "w", "u", "hiz", "aci"])
        akis = d.arac.str.split(".").str[0]
        sonuc["noktalar"] = d.assign(giris=akis.str[0], yon=akis.str[0].map(GIRIS_YON),
                                     hareket=akis.str[1].map(HAREKET))[
            ["t", "arac", "giris", "yon", "hareket", "u", "w", "hiz", "aci"]]
        sonuc["durumlar"] = durumlar
    return sonuc


def hazirla(sayim: dict, surucu: dict, gelis: str = VARSAYILAN_GELIS, klasor: str = "sim/uyarlamali") -> Path:
    """Ağ ve talep; sinyal programı yalnızca başlangıç için (denetleyici her adımda üzerine yazar)."""
    y, C = plan_videodan()
    return kur(Path(klasor) / gelis, sayim, SURE_S, y, C, surucu=surucu, gelis=gelis)


def degerlendir(kural: str, sayim: dict, surucu: dict, tohumlar=(1, 2, 3), gelis: str = VARSAYILAN_GELIS) -> dict:
    """degerlendir.degerlendir ile aynı biçimde ölçüler (plan yerine kural)."""
    cfg = hazirla(sayim, surucu, gelis)
    d = pd.concat([trip_oku(calistir(cfg, kural, t)["trip"], talep_yolu(cfg), ISINMA_S).assign(tohum=t)
                   for t in tohumlar])
    return {
        "gecerli": True,
        "kural": kural,
        **ozetle(d, tohumlar),
    }
