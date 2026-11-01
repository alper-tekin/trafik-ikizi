"""Arayüzün okuduğu JSON dosyalarını üretir (web/veri/).

  ozet.json         doğrulama tabloları ve grafikler: sayımlar, sinyal pencereleri,
                    kuyruk profilleri (video / NGSIM / SUMO), takip ve kalibrasyon ölçüleri
  kusbakisi.json    5 fps izler, kavşak merkezli metre (u kuzey, w doğu), otobüs/kamyon işaretli
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
from trafik.akis import BUYUK_FT, talep_sayimlari, yerel
from trafik.simule import calistir
from trafik.sumo_ag import faz_plani_surelerden, kayit_faz0, kur, video_ofseti

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


def arac_beklemeleri(d: pd.DataFrame) -> dict:
    """Araç (video iz numarası) -> kameranın gördüğü 75 m içinde bekleme (s), olcum.bekleme_sureleri."""
    b = olcum.bekleme_sureleri(d).bekleme_s
    return {int(str(a).split(".")[-1]): round(float(v), 1) for a, v in b.items()}


def oynatma(plan: dict, sayim: dict, surucu: dict, klasor: str, gelis: str = "gercek") -> dict:
    fazlar = faz_plani_surelerden(plan["sol_onde"], plan["guney_onde"], plan["ortak"], plan["ara_sokak"])
    cfg = kur(Path("sim") / klasor, sayim, SURE_S, {}, 0, surucu=surucu, fazlar=fazlar, gelis=gelis)
    d = calistir(cfg)
    # gerçek gelişlerde her aracın videodakiyle karşılaştırılacak beklemesi (araç numarası = iz)
    arac_bekleme = arac_beklemeleri(d[d.t < SURE_S]) if gelis == "gercek" else {}
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
    # gerçek gelişlerde sinyal videoyla hizalı: döngü simülasyon saniyesi ofset_s'de başlar
    ofset_s = video_ofseti(sum(f["sure"] for f in sinyal)) if gelis == "gercek" else 0.0
    return {"plan": plan, "gelis": gelis, "sinyal": sinyal, "isinma_s": 120.0, "ofset_s": ofset_s,
            "baslangic_s": OYNATMA_S[0], "kareler": kareler, "arac_bekleme": arac_bekleme}


def kareler_penceresi(d: pd.DataFrame) -> dict:
    """Oynatma penceresindeki araçlar (2 Hz), arayüz biçiminde."""
    d = d[(d.t >= OYNATMA_S[0]) & (d.t < OYNATMA_S[1])]
    d = d[np.hypot(d.u, d.w) < 110]
    return {f"{t - OYNATMA_S[0]:.1f}": [[a, round(u, 2), round(w, 2), round(h, 1), round(aci)]
                                         for a, u, w, h, aci in g[["arac", "u", "w", "hiz", "aci"]].itertuples(index=False)]
            for t, g in d.groupby("t")}


def oynatma_uyarlamali(kural: str, sayim: dict, surucu: dict, gelis: str = "gercek") -> dict:
    """Uyarlamalı sinyal (uyarlamali.py): sabit döngü yok; her karenin sinyal durumu ve faz adı kaydedilir."""
    from trafik import uyarlamali

    cfg = uyarlamali.hazirla(sayim, surucu, gelis, klasor=f"sim/arayuz_uyarlamali_{kural}")
    k = uyarlamali.calistir(cfg, kural, 1, kayit=True)
    d = k["noktalar"]
    durumlar = [[s, ad] for t, s, ad in k["durumlar"] if OYNATMA_S[0] <= t < OYNATMA_S[1]]
    return {"kural": kural, "gelis": gelis, "sinyal": [], "durumlar": durumlar, "isinma_s": 120.0, "ofset_s": 0.0,
            "baslangic_s": OYNATMA_S[0], "kareler": kareler_penceresi(d),
            "arac_bekleme": arac_beklemeleri(d[d.t < SURE_S]) if gelis == "gercek" else {}}


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
    from trafik import geometri

    # Arayüz bütün çizimleri bu homografiyle yapar (kuşbakışı ve ikiz videoyla aynı açı ve
    # kadrajda); 'olculen' kollar, boyası görünmeyen kollarda şerit ayırıcı çizmek içindir.
    return {"seritler": seritler, "kavsak": kavsak,
            "goruntu": {"G": geometri.goruntu_donusumu().round(8).tolist(), "genislik": 640, "yukseklik": 480},
            "olculen": geometri.yukle()["kollar"]}


def main() -> None:
    VERI.mkdir(parents=True, exist_ok=True)
    plan = json.load(open("data/sinyal_plani.json", encoding="utf-8"))
    C, faz0 = plan["dongu_s"], plan["faz0_video_s"]
    ofset = json.load(open("data/kalibrasyon_kamera2.json", encoding="utf-8"))["ofset_s"]
    kal = json.load(open("data/sim_kalibrasyon.json", encoding="utf-8"))
    surucu = {"tau": kal["en_iyi"]["tau"], "accel": kal["en_iyi"]["accel"]}

    akis = pd.read_parquet("data/akis_izler.parquet")
    izler = pd.read_parquet("data/izler_kamera2.parquet")
    sayim = talep_sayimlari(akis)
    video = olcum.noktalar_izden(izler, akis)
    ngsim = olcum.noktalar_ngsimden(pd.read_parquet("data/ngsim/kavsak2.parquet"), ofset, SURE_S)

    # SUMO kuyruk profili: kalibre edilmiş ayarlar, videodan çıkarılan plan
    from trafik.sumo_ag import plan_videodan
    y, _ = plan_videodan()
    mevcut = {"sol_onde": y["sol_onde"], "guney_onde": y["guney_onde"], "ortak": y["ortak"],
              "ara_sokak": C - y["sol_onde"] - y["guney_onde"] - y["ortak"] - 8}
    sim_mevcut = oynatma(mevcut, sayim, surucu, "arayuz_mevcut")
    sim_mevcut_r = oynatma(mevcut, sayim, surucu, "arayuz_mevcut_rastgele", gelis="rastgele")
    cfg = Path("sim/arayuz_mevcut/sim.sumocfg")
    q_sumo = olcum.kuyruk_profili(calistir(cfg), C, kayit_faz0())

    ajan = son_ajan_kosusu()
    # Kayıttaki doğrulama, koşunun yapıldığı ağa aittir; ikiz ağı sonradan değiştiyse (ör. geometri
    # boyadan yeniden ölçüldü) önerilen plan bugünkü ikizde yeniden doğrulanır. Kayıt dosyası değişmez.
    from trafik.ajan import Ortam, dogrula
    ajan["dogrulama_kayit"] = ajan["dogrulama"]
    ajan["dogrulama"] = dogrula(ajan, Ortam())
    onerilen = {k: float(v) for k, v in ajan["cevap"]["recommended_plan"].items()}
    sim_onerilen = oynatma(onerilen, sayim, surucu, "arayuz_onerilen")
    sim_onerilen_r = oynatma(onerilen, sayim, surucu, "arayuz_onerilen_rastgele", gelis="rastgele")

    # Yol başına bekleme. (1) Kameranın gördüğü 75 m içinde, aynı tanımla:
    # video, NGSIM ve ikiz (mevcut plan, videodaki araçlar, 3 tohum). (2) İki planın
    # karşılaştırması: ikizdeki toplam bekleme (SUMO waitingTime), 10 tohumda; videodaki
    # araçlarla (tohum sürücü davranışı) ve rastgele gelişlerle (ajanın görmediği trafik).
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
        "planlar_10_tohum_rastgele": {
            ad: {k: degerlendir(p, sayim, surucu, tuple(range(11, 21)), gelis="rastgele")[k]
                 for k in ("kol_bekleme_s", "kol_gecikme_s", "ort_gecikme_s", "arac_basi_durma_bekleme_s")}
            for ad, p in (("mevcut", mevcut), ("onerilen", onerilen))
        },
    }
    # Uyarlamalı sinyal: iki kural, videodaki araçlarla ve rastgele gelişlerle (10 tohum) + oynatmalar
    from trafik import uyarlamali
    sim_uyar = {}
    for kural in ("saf", "agirlikli"):
        for anahtar, gelis in (("planlar_10_tohum", "gercek"), ("planlar_10_tohum_rastgele", "rastgele")):
            u = uyarlamali.degerlendir(kural, sayim, surucu, tuple(range(11, 21)), gelis=gelis)
            bekleme[anahtar][f"uyarlamali_{kural}"] = {
                k: u[k] for k in ("kol_bekleme_s", "kol_gecikme_s", "ort_gecikme_s", "arac_basi_durma_bekleme_s")}
            sim_uyar[(kural, gelis)] = oynatma_uyarlamali(kural, sayim, surucu, gelis)

    # Araç araç: aynı aracın videodaki, mevcut plandaki ve önerilen plandaki beklemesi (75 m, tohum 1)
    v = arac_beklemeleri(video)
    a, b = sim_mevcut["arac_bekleme"], sim_onerilen["arac_bekleme"]
    ortak = sorted(set(v) & set(a) & set(b))
    va, aa, ba = (np.array([x[i] for i in ortak]) for x in (v, a, b))
    for kural in ("saf", "agirlikli"):
        c = sim_uyar[(kural, "gercek")]["arac_bekleme"]
        cc = np.array([c.get(i, np.nan) for i in ortak])
        bekleme[f"arac_arac_uyarlamali_{kural}"] = {
            "ort_s": round(float(np.nanmean(cc)), 1),
            "mevcuttan_daha_az_pay": round(float((cc < aa - 1).mean()), 3),
            "mevcuttan_daha_fazla_pay": round(float((cc > aa + 1).mean()), 3),
        }
    bekleme["arac_arac"] = {
        "n": len(ortak),
        "ort_s": {"video": round(float(va.mean()), 1), "mevcut": round(float(aa.mean()), 1),
                  "onerilen": round(float(ba.mean()), 1)},
        "onerilende_daha_az_pay": round(float((ba < aa - 1).mean()), 3),
        "onerilende_daha_fazla_pay": round(float((ba > aa + 1).mean()), 3),
        "video_mevcut_korelasyon": round(float(np.corrcoef(va, aa)[0, 1]), 2),
        "video_mevcut_medyan_mutlak_fark_s": round(float(np.median(np.abs(va - aa))), 1),
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
        "video_arac_bekleme": arac_beklemeleri(video),
        "bekleme": bekleme,
        "ajan": {k: ajan[k] for k in ("soru", "model", "adimlar", "cevap", "dogrulama", "dogrulama_kayit")},
    }
    yaz("ozet.json", ozet)

    # Kuşbakışı izler (5 fps), hareket etiketiyle
    uw = yerel(izler[["x", "y"]].to_numpy()) * olcum.FT
    k = izler.assign(u=uw[:, 0].round(1), w=uw[:, 1].round(1)).merge(
        akis[["iz", "yon", "hareket"]], on="iz", how="left")
    k = k.fillna({"yon": 0, "hareket": 0})
    # son alan: otobüs/kamyon mu (izin kutu boyu medyanı, akis.BUYUK_FT)
    k = k.assign(buyuk=k.iz.map(izler.groupby("iz").boy.median() > BUYUK_FT).astype(int))
    kareler = {int(no): [[int(a), u, w, int(yn), int(h), int(b)] for a, u, w, yn, h, b in
                         g[["iz", "u", "w", "yon", "hareket", "buyuk"]].itertuples(index=False)]
               for no, g in k.groupby("kare")}
    yaz("kusbakisi.json", {"fps": 5, "kareler": kareler})
    yaz("sim_mevcut.json", sim_mevcut)
    yaz("sim_onerilen.json", sim_onerilen)
    yaz("sim_mevcut_rastgele.json", sim_mevcut_r)
    yaz("sim_onerilen_rastgele.json", sim_onerilen_r)
    for (kural, gelis), v in sim_uyar.items():
        yaz(f"sim_uyarlamali_{kural}{'_rastgele' if gelis == 'rastgele' else ''}.json", v)
    yaz("sim_ag.json", ag_geometrisi(Path("sim/arayuz_mevcut/ag.net.xml")))


if __name__ == "__main__":
    main()
