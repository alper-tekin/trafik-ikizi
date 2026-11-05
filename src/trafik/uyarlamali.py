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
  - yaya talebi varsayımı: tamamlanan hizmetten 120 s sonra ilgili faz öncelik alır.
    Hizmet ara sokakta 30 s, Lankershim fazında 18 s sürer. Geçişler ve asgari yeşil
    nedeniyle bu, 120 s azami hizmet aralığı garantisi değildir; hizmet günlüğü raporlanır.
Bekleme: aracın giriş kolunda hızı 0,5 m/s altında geçen toplam süre (arayüzdeki sayaçla aynı).
"""

import os
import math
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


def parametreleri_dogrula(parametreler: dict | None = None) -> dict:
    """Only the maximum-green experiment is configurable; safety timings stay fixed."""
    params = {} if parametreler is None else dict(parametreler)
    unknown = set(params) - {"max_green_s"}
    if unknown:
        raise ValueError(f"Unknown adaptive parameters: {sorted(unknown)}")
    maximum = params.get("max_green_s", EN_UZUN)
    if isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or not math.isfinite(maximum):
        raise ValueError("max_green_s must be finite")
    if maximum < max(*EN_KISA.values(), *YAYA_SURE.values()):
        raise ValueError("max_green_s cannot be shorter than fixed minimum/pedestrian service")
    return {"max_green_s": float(maximum)}


def faz_sec(faz: str, sure: float, puan: dict, talep: bool,
            gecikmis: list[str], max_green_s: float) -> tuple[str | None, str | None]:
    """Choice after the caller enforces the unchanged minimum green."""
    if gecikmis:
        return gecikmis[0], "pedestrian_service_due"
    digerleri = {f: p for f, p in puan.items() if f != faz}
    en_iyi = max(digerleri, key=digerleri.get)
    if (sure >= max_green_s or not talep) and digerleri[en_iyi] > 0:
        return en_iyi, "maximum_green" if sure >= max_green_s else "demand_cleared"
    return None, None


class YayaKaydi:
    """Observe continuous green service without changing the controller's timers."""

    def __init__(self):
        self.hizmetler = []
        self.olaylar = []
        self.aktif = None

    def baslat(self, faz: str, t: float):
        self.aktif = None
        if faz in YAYA_SURE:
            self.aktif = {"faz": faz, "baslangic_s": t, "gereken_s": YAYA_SURE[faz],
                          "tamamlanma_s": None, "bitis_s": None}
            self.hizmetler.append(self.aktif)
            self.olaylar.append({"t": t, "olay": "pedestrian_service_start", "faz": faz})

    def guncelle(self, t: float):
        if self.aktif and self.aktif["tamamlanma_s"] is None:
            if t - self.aktif["baslangic_s"] >= self.aktif["gereken_s"]:
                self.aktif["tamamlanma_s"] = t
                self.olaylar.append({"t": t, "olay": "pedestrian_service_complete", "faz": self.aktif["faz"]})

    def bitir(self, t: float):
        if self.aktif:
            self.guncelle(t)
            self.aktif["bitis_s"] = t
            self.olaylar.append({"t": t, "olay": "pedestrian_service_end", "faz": self.aktif["faz"],
                                 "tamamlandi": self.aktif["tamamlanma_s"] is not None})
        self.aktif = None

    def ozet(self, t: float) -> dict:
        self.bitir(t)
        gaps, no_service = {}, {}
        for faz in YAYA_SURE:
            completions = [h["tamamlanma_s"] for h in self.hizmetler
                           if h["faz"] == faz and h["tamamlanma_s"] is not None]
            boundaries = [0.0, *completions, t]
            gaps[faz] = max((b-a for a,b in zip(boundaries, boundaries[1:])), default=0.0)
            # Once the required green duration is reached, service remains
            # available until that phase ends. A long green is not no service.
            intervals = [(h["tamamlanma_s"], h["bitis_s"])
                         for h in self.hizmetler if h["faz"] == faz and h["tamamlanma_s"] is not None]
            cursor, maximum = 0.0, 0.0
            for begin, end in intervals:
                maximum = max(maximum, begin-cursor)
                cursor = max(cursor, end)
            no_service[faz] = max(maximum, t-cursor)
        return {"hizmetler": self.hizmetler, "olaylar": self.olaylar, "gozlem_bitis_s": t,
                "azami_tamamlanma_boslugu_s": gaps,
                "azami_hizmetsiz_bosluk_s": no_service,
                "tamamlanmayan_hizmet_sayisi": sum(h["tamamlanma_s"] is None for h in self.hizmetler),
                "aralik_hedef_s": YAYA_ARALIK,
                "azami_aralik_garantisi": False,
                "not": "Assumed periodic requests, not simulated pedestrians. Completion gaps include initial/final boundaries. No-service gaps count the required green duration before first completion, then continuous green remains service availability. 120 s is a priority threshold, not a guaranteed maximum gap."}


def calistir(cfg: Path, kural: str, tohum: int = 1, kayit: bool = False,
             *, parametreler: dict | None = None) -> dict:
    """Simülasyonu uyarlamalı denetleyiciyle koşturur. Dönüş: tripinfo yolu ve (kayit=True ise)
    simule.calistir biçiminde araç noktaları + kare başına sinyal durumu ve faz adı."""
    params = parametreleri_dogrula(parametreler)
    if kural not in ("saf", "agirlikli"):
        raise ValueError("Unknown adaptive rule")
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
    noktalar, durumlar, kararlar = [], [], []
    yaya_kaydi = YayaKaydi()
    t = 0.0
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
        yaya_kaydi.baslat(faz, 0.0)
        kararlar.append({"t": 0.0, "olay": "green_start", "onceki_faz": None, "sonraki_faz": faz, "neden": "initial_phase"})
        traci.trafficlight.setRedYellowGreenState(tls, _durum(gruplar, harfler, FAZLAR[faz][1]))

        def hizmet(faz_ad: str, kol: str, harf: str) -> bool:
            return FAZLAR[faz_ad][1].get(sinyal_grubu(kol, harf), "r") in ("G", "g")

        bitis_s = float(ET.parse(cfg.name).getroot().find("time/end").get("value"))
        while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < bitis_s:
            traci.simulationStep()
            t = traci.simulation.getTime()
            if not gecis:
                yaya_kaydi.guncelle(t)
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
                        onceki = faz
                        faz, faz_bas = hedef, t
                        yaya_kaydi.baslat(faz, t)
                        kararlar.append({"t": t, "olay": "green_start", "onceki_faz": onceki, "sonraki_faz": faz, "neden": "transition_completed"})
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
                    # Yeşil, kendi kuyruğu boşalırken ya da durma çizgisine TALEP_M içinde araç
                    # gelirken sürer (her geçiş 4 s kaybettirir); talep bitince ya da en uzun
                    # yeşil dolunca sıradaki faz kurala göre seçilir.
                    talep = any(hizmet(faz, v.split(".")[0][0], v.split(".")[0][1]) for v in yakindakiler)
                    yeni, neden = faz_sec(faz, sure, puan, talep, gecikmis, params["max_green_s"])
                    if yeni:
                        yaya_kaydi.bitir(t)
                        kararlar.append({"t": t, "olay": "transition_requested", "onceki_faz": faz,
                                         "sonraki_faz": yeni, "neden": neden, "puanlar": dict(puan),
                                         "gecen_yesil_s": sure, "yakin_talep": talep,
                                         "gecikmis_yaya_fazlari": list(gecikmis)})
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

    sonuc = {"trip": cfg.parent / trip, "parametreler": params,
             "kararlar": kararlar, "yaya_hizmeti": yaya_kaydi.ozet(t)}
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


def degerlendir(kural: str, sayim: dict, surucu: dict, tohumlar=(1, 2, 3), gelis: str = VARSAYILAN_GELIS,
                *, parametreler: dict | None = None, klasor: str = "sim/uyarlamali") -> dict:
    """Shared trip metrics plus per-seed phase reasons and observed pedestrian service."""
    params = parametreleri_dogrula(parametreler)
    cfg = hazirla(sayim, surucu, gelis, klasor)
    frames, audit = [], []
    for seed in tohumlar:
        run = calistir(cfg, kural, seed, parametreler=params)
        frames.append(trip_oku(run["trip"], talep_yolu(cfg), ISINMA_S).assign(tohum=seed))
        audit.append({"tohum": seed, "kararlar": run["kararlar"], "yaya_hizmeti": run["yaya_hizmeti"]})
    d = pd.concat(frames)
    return {"gecerli": True, "kural": kural, "parametreler": params,
            **ozetle(d, tohumlar), "denetleyici_kaydi": audit}
