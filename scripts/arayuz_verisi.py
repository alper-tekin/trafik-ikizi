"""Arayüzün okuduğu JSON dosyalarını üretir (web/veri/).

  ozet.json         doğrulama tabloları ve grafikler: sayımlar, sinyal pencereleri,
                    kuyruk profilleri (video / NGSIM / SUMO), takip ve kalibrasyon ölçüleri
  kusbakisi.json    5 fps izler, kavşak merkezli metre (u kuzey, w doğu)
  sim_mevcut.json   SUMO oynatması, videodan çıkarılan plan
  sim_onerilen.json SUMO oynatması, son ajan koşusunun önerisi

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/arayuz_verisi.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from trafik import olcum
from trafik.akis import yerel
from trafik.simule import calistir
from trafik.sumo_ag import faz_plani_surelerden, kur, sim_faz0

VERI = Path("web/veri")
SURE_S = 1122.0
OYNATMA_S = (300.0, 600.0)  # simülasyondan gösterilecek pencere (ısınma sonrası)


def yaz(ad: str, veri) -> None:
    (VERI / ad).write_text(json.dumps(veri, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(VERI / ad, f"{(VERI / ad).stat().st_size / 1e6:.2f} MB")


def profil_sozluk(q: pd.DataFrame) -> dict:
    return {k: [round(float(v), 2) for v in q[k]] for k in ("K", "G") if k in q}


def son_ajan_kosusu() -> dict:
    yollar = sorted(Path("data/ajan").glob("kosu_*.json"))
    for yol in reversed(yollar):
        k = json.loads(yol.read_text(encoding="utf-8"))
        if k.get("cevap"):
            return k
    raise FileNotFoundError("tamamlanmış ajan koşusu yok")


def oynatma(plan: dict, sayim: dict, surucu: dict, klasor: str) -> dict:
    fazlar = faz_plani_surelerden(plan["sol_onde"], plan["guney_onde"], plan["ortak"], plan["ara_sokak"])
    cfg = kur(Path("sim") / klasor, sayim, SURE_S, {}, 0, surucu=surucu, fazlar=fazlar)
    d = calistir(cfg)
    d = d[(d.t >= OYNATMA_S[0]) & (d.t < OYNATMA_S[1])]  # adım 0,5 s -> 2 Hz; arayüz ara kareleri kestirir
    d = d[np.hypot(d.u, d.w) < 110]
    kareler = {}
    for t, g in d.groupby("t"):
        kareler[f"{t - OYNATMA_S[0]:.1f}"] = [
            [a, round(u, 2), round(w, 2), round(h, 1), round(aci)]
            for a, u, w, h, aci in g[["arac", "u", "w", "hiz", "aci"]].itertuples(index=False)]
    # Sinyal durum dizileri (bağlantı sırasıyla), SUMO'nun okuduğu dosyadan
    import xml.etree.ElementTree as ET
    # faz_plani_surelerden ile aynı sıra ve aynı süfir-süre filtresi
    adlar = [(plan["sol_onde"], "Southbound left only"), (plan["guney_onde"], "Southbound through + left"),
             (plan["ortak"], "Lankershim, both directions"), (3, "Yellow"), (1, "All red"),
             (plan["ara_sokak"], "Cross street"), (3, "Yellow"), (1, "All red")]
    adlar = [ad for sure, ad in adlar if sure > 0]
    sinyal = [{"sure": float(f.get("duration")), "durum": f.get("state"), "ad": ad}
              for f, ad in zip(ET.parse(cfg.parent / "sinyal.add.xml").getroot().iter("phase"), adlar)]
    return {"plan": plan, "sinyal": sinyal, "isinma_s": 120.0, "baslangic_s": OYNATMA_S[0], "kareler": kareler}


def ag_geometrisi(ag_yolu: Path) -> dict:
    """Arayüz çizimi için SUMO ağı: şerit şekilleri, kavşak çokgeni, şerit başına
    sinyal bağlantıları (yön harfi ve sinyal dizisindeki sırası). Kavşak merkezli metre."""
    import sumolib

    net = sumolib.net.readNet(str(ag_yolu), withInternal=False)
    mx, my = net.getNode("M").getCoord()
    uw = lambda p: [round(p[1] - my, 2), round(p[0] - mx, 2)]  # noqa: E731  (x doğu, y kuzey) -> (u, w)
    seritler = []
    for kenar in net.getEdges():
        for serit in kenar.getLanes():
            linkler = []
            for b in serit.getOutgoing():
                if b.getTLLinkIndex() >= 0:
                    linkler.append({"yon": b.getDirection().lower()[0], "sira": b.getTLLinkIndex()})
            seritler.append({
                "kenar": kenar.getID(), "giris": kenar.getID().endswith("_gir"),
                "sira": serit.getIndex(), "genislik": serit.getWidth(),
                "sekil": [uw(p) for p in serit.getShape()], "linkler": linkler,
            })
    kavsak = [uw(p) for p in net.getNode("M").getShape()]
    return {"seritler": seritler, "kavsak": kavsak}


def main() -> None:
    VERI.mkdir(parents=True, exist_ok=True)
    plan = json.load(open("data/sinyal_plani.json", encoding="utf-8"))
    C, faz0 = plan["dongu_s"], plan["faz0_video_s"]
    ofset = json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8"))["ofset_s"]
    kal = json.load(open("data/sim_kalibrasyon.json", encoding="utf-8"))
    surucu = {"tau": kal["en_iyi"]["tau"], "accel": kal["en_iyi"]["accel"]}

    akis = pd.read_parquet("data/akis_izler.parquet")
    izler = pd.read_parquet("data/izler_kamera2.parquet")
    sayim = akis.groupby(["yon", "hareket"]).size().to_dict()
    video = olcum.noktalar_izden(izler, akis)
    ngsim = olcum.noktalar_ngsimden(pd.read_parquet("data/ngsim/kavsak2.parquet"), ofset, SURE_S)

    # SUMO kuyruk profili: kalibre edilmiş ayarlar, videodan çıkarılan plan
    from trafik.sumo_ag import plan_videodan
    y, _ = plan_videodan()
    mevcut = {"sol_onde": y["sol_onde"], "guney_onde": y["guney_onde"], "ortak": y["ortak"],
              "ara_sokak": C - y["sol_onde"] - y["guney_onde"] - y["ortak"] - 8}
    sim_mevcut = oynatma(mevcut, sayim, surucu, "arayuz_mevcut")
    cfg = Path("sim/arayuz_mevcut/sim.sumocfg")
    q_sumo = olcum.kuyruk_profili(calistir(cfg), C, sim_faz0())

    ajan = son_ajan_kosusu()
    onerilen = {k: float(v) for k, v in ajan["cevap"]["recommended_plan"].items()}
    sim_onerilen = oynatma(onerilen, sayim, surucu, "arayuz_onerilen")

    # Yol başına bekleme. (1) Kameranın gördüğü 75 m içinde, aynı tanımla:
    # video, NGSIM ve ikiz (mevcut plan, 3 tohum). (2) İki planın karşılaştırması:
    # ikizdeki toplam bekleme (SUMO waitingTime), ajanın görmediği 10 tohumda.
    from trafik.degerlendir import degerlendir
    sim_noktalari = pd.concat([calistir(cfg, tohum=s).assign(arac=lambda x, s=s: x.arac + f"#{s}") for s in (1, 2, 3)])
    sim_noktalari = sim_noktalari[sim_noktalari.t < SURE_S]
    bekleme = {
        "kamera_penceresi": {
            "video": olcum.kol_bekleme_ozeti(olcum.bekleme_sureleri(video)),
            "ngsim": olcum.kol_bekleme_ozeti(olcum.bekleme_sureleri(ngsim)),
            "ikiz": olcum.kol_bekleme_ozeti(olcum.bekleme_sureleri(sim_noktalari)),
        },
        "planlar_10_tohum": {
            ad: {k: degerlendir(p, sayim, surucu, tuple(range(11, 21)))[k]
                 for k in ("kol_bekleme_s", "kol_gecikme_s", "ort_gecikme_s", "arac_basi_durma_bekleme_s")}
            for ad, p in (("mevcut", mevcut), ("onerilen", onerilen))
        },
    }

    ozet = {
        "sayimlar": pd.read_csv("data/akis_karsilastirma.csv").to_dict(orient="records"),
        "sinyal": plan,
        "kuyruk_profili": {
            "video": profil_sozluk(olcum.kuyruk_profili(video, C, faz0)),
            "ngsim": profil_sozluk(olcum.kuyruk_profili(ngsim, C, faz0)),
            "sumo": profil_sozluk(q_sumo),
        },
        "kalibrasyon": {k: kal[k] for k in ("en_iyi", "varsayilan", "video_ort_kuyruk", "ngsim_ort_kuyruk",
                                             "video_vs_ngsim_rmse")},
        "takip": json.load(open("data/takip_degerlendirme.json", encoding="utf-8")),
        "kamera": json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8")),
        "mevcut_plan": mevcut,
        "bekleme": bekleme,
        "ajan": {k: ajan[k] for k in ("soru", "model", "adimlar", "cevap", "dogrulama")},
    }
    yaz("ozet.json", ozet)

    # Kuşbakışı izler (5 fps), hareket etiketiyle
    uw = yerel(izler[["x", "y"]].to_numpy()) * olcum.FT
    k = izler.assign(u=uw[:, 0].round(1), w=uw[:, 1].round(1)).merge(
        akis[["iz", "yon", "hareket"]], on="iz", how="left")
    k = k.fillna({"yon": 0, "hareket": 0})
    kareler = {int(no): [[int(a), u, w, int(yn), int(h)] for a, u, w, yn, h in
                         g[["iz", "u", "w", "yon", "hareket"]].itertuples(index=False)]
               for no, g in k.groupby("kare")}
    yaz("kusbakisi.json", {"fps": 5, "kareler": kareler})
    yaz("sim_mevcut.json", sim_mevcut)
    yaz("sim_onerilen.json", sim_onerilen)
    yaz("sim_ag.json", ag_geometrisi(Path("sim/arayuz_mevcut/ag.net.xml")))


if __name__ == "__main__":
    main()
