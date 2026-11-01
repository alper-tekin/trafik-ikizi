"""Kavşak 2'nin SUMO modelini videodan çıkarılan veriyle kurar.

  - Ağ: kolların yönü, şerit sayısı/genişliği/yanal yeri, durma çizgileri ve
    kavşak alanı araçsız yol fotoğrafındaki boyadan ölçülür (scripts/geometri_fotodan.py,
    data/geometri.json). Kollar dik (+) kurulur (ölçülen yönler 4°/−177°/96°/−84°, dike
    yakın); şerit sayıları, genişlikleri (2,5-3,6 m), yanal konumları ve durma çizgileri
    (17-22 m) ölçüldüğü gibidir. Güney ve doğu kolunda orta refüj var.
  - Talep: video penceresindeki yön x hareket sayımları -> araç/saat.
  - Sinyal: döngü ve yeşil süreleri data/sinyal_plani.json'dan; sarı 3 s,
    tüm-kırmızı 1 s. Ara sokağın yeşili döngünün kalanıdır.
"""

import json
import subprocess
from pathlib import Path

import sumolib

SARI, TUM_KIRMIZI = 3, 1
BUYUK_BOY_M = 10.0  # otobüs/kamyon karışımı (NGSIM büyük araç boy medyanı 29 ft ≈ 9 m, otobüsler 12 m)
KOL_UZUNLUK_M = 300.0
YON_KOL = {2: "G", 4: "K", 1: "B", 3: "D"}  # gidiş yönü -> giriş kolu
HAREKET_HARF = {1: "s", 2: "l", 3: "r"}
SAAT = 3600.0

# giriş kolu, hareket -> çıkış kolu
CIKIS = {
    ("K", 1): "G", ("K", 2): "D", ("K", 3): "B",
    ("G", 1): "K", ("G", 2): "B", ("G", 3): "D",
    ("D", 1): "B", ("D", 2): "G", ("D", 3): "K",
    ("B", 1): "D", ("B", 2): "K", ("B", 3): "G",
}


def _sumo_bin(ad: str) -> str:
    import sumo

    return str(Path(sumo.SUMO_HOME) / "bin" / ad)


# Şerit -> hareket eşlemesi (şerit 0 = en sağ/en dış), videodan: her şeritte durma çizgisi
# önünde bekleyen araçların gerçekte nereye gittiği sayıldı ve yoldaki boyalı oklarla
# karşılaştırıldı (doğu kolunda oklar sağ / düz / sol, sayımlarla aynı). Şerit başına sayımlar:
#   K: 150 düz+32 sağ | 117 düz | 119 düz | 98 sol | 59 sol (sağ cepte boyalı sağ ok)
#   G: 92 sağ | 120 düz | 99 düz | 70 düz | 13 sol
#   D: 42 sağ | 9 düz | 4 sol            B: 26 düz+3 sağ | 7 düz | 34 sol
SERIT_HAREKET = {
    "K": [("r", "s"), ("s",), ("s",), ("l",), ("l",)],
    "G": [("r",), ("s",), ("s",), ("s",), ("l",)],
    "D": [("r",), ("s",), ("l",)],
    "B": [("r", "s"), ("s",), ("l",)],
}
HARF_HAREKET = {"s": 1, "l": 2, "r": 3}


def _xy(p) -> str:
    """(u kuzey, w doğu) -> SUMO 'x,y' (x doğu, y kuzey)."""
    return f"{p[1]:.2f},{p[0]:.2f}"


def ag_yaz(klasor: Path, geo: dict | None = None) -> Path:
    import numpy as np

    from trafik import geometri

    geo = geo or geometri.yukle()
    kavsak = " ".join(_xy(p) for p in geo["kavsak"])
    dugum = ['<nodes>', f'  <node id="M" x="0" y="0" type="traffic_light" shape="{kavsak}"/>']
    kenar = ['<edges>']
    for k, g in geo["kollar"].items():
        e, n, t = np.array(g["e"]), np.array(g["n"]), g["durma_m"]
        gi, gc = g["gelen"], g["giden"]
        # Gelen şeritler içe doğru gider, sağları -n tarafında; spreadType="right" ile
        # şeritler kenar çizgisinin sağına dizilir, çizgi en iç şeridin sol kenarıdır.
        sol_gi = max(gi["merkez"]) + gi["genislik"] / 2
        sol_gc = min(gc["merkez"]) - gc["genislik"] / 2
        uzak_gi, yakin_gi = e * KOL_UZUNLUK_M + n * sol_gi, e * t + n * sol_gi
        yakin_gc, uzak_gc = e * t + n * sol_gc, e * KOL_UZUNLUK_M + n * sol_gc
        dugum.append(f'  <node id="{k}_g" x="{uzak_gi[1]:.2f}" y="{uzak_gi[0]:.2f}" type="priority"/>')
        dugum.append(f'  <node id="{k}_c" x="{uzak_gc[1]:.2f}" y="{uzak_gc[0]:.2f}" type="priority"/>')
        kenar.append(f'  <edge id="{k}_gir" from="{k}_g" to="M" numLanes="{gi["n"]}" speed="13.9" '
                     f'width="{gi["genislik"]:.2f}" spreadType="right" shape="{_xy(uzak_gi)} {_xy(yakin_gi)}"/>')
        kenar.append(f'  <edge id="{k}_cik" from="M" to="{k}_c" numLanes="{gc["n"]}" speed="13.9" '
                     f'width="{gc["genislik"]:.2f}" spreadType="right" shape="{_xy(yakin_gc)} {_xy(uzak_gc)}"/>')
    dugum.append('</nodes>')
    kenar.append('</edges>')

    # Şerit bağlantıları: düzler sağdan sağa, soller en soldaki giden şeritlere, sağlar en sağa.
    baglanti = ['<connections>']
    for k, seritler in SERIT_HAREKET.items():
        n_gelen = geo["kollar"][k]["gelen"]["n"]
        seritler = seritler[:n_gelen] + [("s",)] * max(0, n_gelen - len(seritler))
        for hedef_harf in ("s", "l", "r"):
            hedef = CIKIS[(k, HARF_HAREKET[hedef_harf])]
            n_giden = geo["kollar"][hedef]["giden"]["n"]
            kaynak = [i for i, h in enumerate(seritler) if hedef_harf in h]
            for j, i in enumerate(kaynak):
                if hedef_harf == "s":
                    to = min(j, n_giden - 1)
                elif hedef_harf == "l":
                    to = n_giden - 1 - (len(kaynak) - 1 - j)
                else:
                    to = 0
                baglanti.append(f'  <connection from="{k}_gir" to="{hedef}_cik" fromLane="{i}" toLane="{max(0, to)}"/>')
    baglanti.append('</connections>')

    (klasor / "ag.nod.xml").write_text("\n".join(dugum), encoding="utf-8")
    (klasor / "ag.edg.xml").write_text("\n".join(kenar), encoding="utf-8")
    (klasor / "ag.con.xml").write_text("\n".join(baglanti), encoding="utf-8")
    ag = klasor / "ag.net.xml"
    # SUMO, ASCII dışı karakter içeren tam yolları (ör. "Masaüstü") açamıyor;
    # klasörün içinden göreli adlarla çalıştırılır.
    subprocess.run(
        [_sumo_bin("netconvert"), "-n", "ag.nod.xml", "-e", "ag.edg.xml", "-x", "ag.con.xml", "-o", ag.name,
         "--no-turnarounds", "--tls.default-type", "static", "--no-warnings"],
        check=True, cwd=klasor, env=_ortam(),
    )
    return ag


def _ortam() -> dict:
    """SUMO_HOME ASCII dışı bir yolu gösterirse SUMO çöküyor; değişken kaldırılır
    (SUMO yerleşik tip tablolarını kullanır, yalnızca XML doğrulaması kapanır)."""
    import os

    return {k: v for k, v in os.environ.items() if k != "SUMO_HOME"}


def talep_yaz(klasor: Path, sayimlar: dict[tuple[int, int], int], sure_s: float, olcek: float = 1.0,
              surucu: dict | None = None) -> Path:
    """sayimlar: (yön, hareket) -> araba sayısı, (yön, hareket, "b") -> otobüs/kamyon sayısı (sure_s içinde).
    surucu: SUMO vType parametreleri (accel, tau, minGap...) videoya kalibre edilmiş değerler."""
    p = {"length": 4.8, "minGap": 2.0, "accel": 2.0, "decel": 4.5, "sigma": 0.5, "tau": 1.0, **(surucu or {})}
    # Otobüs/kamyon: BUYUK_BOY_M, daha yavaş hızlanan; sürücü tepki süresi arabalarla aynı.
    b = {**p, "length": BUYUK_BOY_M, "minGap": 2.5, "accel": min(p["accel"], 1.2), "decel": 4.0}
    ozellik = lambda q: " ".join(f'{k}="{v}"' for k, v in q.items())  # noqa: E731
    satir = ['<routes>', f'  <vType id="oto" {ozellik(p)}/>', f'  <vType id="buyuk" {ozellik(b)}/>']
    for anahtar, n in sorted(sayimlar.items(), key=lambda x: tuple(map(str, x[0]))):
        yon, hareket, buyuk = anahtar[0], anahtar[1], len(anahtar) > 2
        giris = YON_KOL[yon]
        cikis = CIKIS[(giris, hareket)]
        saatlik = n / sure_s * SAAT * olcek
        if saatlik <= 0:
            continue
        # akış kimliği: kol + hareket harfi (+ B otobüs/kamyon); arayüz araç türünü buradan okur
        satir.append(
            f'  <flow id="{giris}{HAREKET_HARF[hareket]}{"B" if buyuk else ""}" type="{"buyuk" if buyuk else "oto"}" '
            f'from="{giris}_gir" to="{cikis}_cik" '
            f'begin="0" end="{sure_s:.0f}" vehsPerHour="{saatlik:.1f}" departLane="best" departSpeed="max"/>'
        )
    satir.append('</routes>')
    yol = klasor / "talep.rou.xml"
    yol.write_text("\n".join(satir), encoding="utf-8")
    return yol


def _baglanti_hareketleri(ag: Path) -> list[tuple[str, str]]:
    """Sinyal bağlantı sırasına göre (giriş kolu, hareket harfi) listesi."""
    net = sumolib.net.readNet(str(ag))
    tls = net.getTrafficLights()[0]
    sira = sorted(tls.getConnections(), key=lambda c: c[2])
    return [(gir.getEdge().getID().split("_")[0], baglanti.getDirection().lower()[0]) for gir, _, _, baglanti in
            [(c[0], c[1], c[2], _baglanti(c)) for c in sira]]


def _baglanti(c):
    gir_serit, cik_serit, _ = c
    for b in gir_serit.getOutgoing():
        if b.getToLane() == cik_serit:
            return b
    raise ValueError("bağlantı bulunamadı")


def faz_plani(yesil: dict[str, float], dongu: float) -> list[tuple[float, dict]]:
    """Önden sol (lead-lag) düzeni, videoda görülen sırayla:
      1. sol_onde:   yalnızca kuzeyden gelen sola döner (güneye giden sol)
      2. guney_onde: güneye düz + sol; kuzeye giden hâlâ kırmızı
      3. ortak:      iki yön düz; sollar izinli
      4. ara sokak:  döngünün kalanı
    Gruplar: gd (güneye düz+sağ, K kolu), kd (kuzeye düz+sağ, G kolu),
    ks (K kolundan sol), gs (G kolundan sol), db (ara sokak)."""
    sol, onde, ortak = yesil["sol_onde"], yesil["guney_onde"], yesil["ortak"]
    db = dongu - sol - onde - ortak - 2 * (SARI + TUM_KIRMIZI)
    if db < 5:
        raise ValueError(f"ara sokağa {db:.0f} s kalıyor; plan geçersiz")
    r = dict.fromkeys(["gd", "kd", "ks", "gs", "db"], "r")
    return [
        (sol, {**r, "ks": "G"}),
        (onde, {**r, "ks": "G", "gd": "G"}),
        (ortak, {**r, "gd": "G", "kd": "G", "ks": "g", "gs": "g"}),
        (SARI, {**r, "gd": "y", "kd": "y", "ks": "y", "gs": "y"}),
        (TUM_KIRMIZI, r),
        (db, {**r, "db": "G"}),
        (SARI, {**r, "db": "y"}),
        (TUM_KIRMIZI, r),
    ]


def faz_plani_surelerden(sol_onde: float, guney_onde: float, ortak: float, ara_sokak: float) -> list:
    """Ajanın önerdiği yeşil sürelerinden faz listesi; 0 s'lik fazlar atlanır."""
    r = dict.fromkeys(["gd", "kd", "ks", "gs", "db"], "r")
    fazlar = [
        (sol_onde, {**r, "ks": "G"}),
        (guney_onde, {**r, "ks": "G", "gd": "G"}),
        (ortak, {**r, "gd": "G", "kd": "G", "ks": "g", "gs": "g"}),
        (SARI, {**r, "gd": "y", "kd": "y", "ks": "y", "gs": "y"}),
        (TUM_KIRMIZI, r),
        (ara_sokak, {**r, "db": "G"}),
        (SARI, {**r, "db": "y"}),
        (TUM_KIRMIZI, r),
    ]
    return [(s, d) for s, d in fazlar if s > 0]


def sinyal_yaz(klasor: Path, ag: Path, fazlar: list[tuple[float, dict]]) -> Path:
    baglantilar = _baglanti_hareketleri(ag)

    def grup(kol: str, harf: str) -> str:
        if kol in ("D", "B"):
            return "db"
        if harf == "l":
            return "ks" if kol == "K" else "gs"
        return "gd" if kol == "K" else "kd"

    gruplar = [grup(k, h) for k, h in baglantilar]
    tls_id = sumolib.net.readNet(str(ag)).getTrafficLights()[0].getID()
    satir = ['<additional>', f'  <tlLogic id="{tls_id}" type="static" programID="video" offset="0">']
    for sure, durum in fazlar:
        # Sağa dönüşler kırmızıda da yol vererek dönebilir (ABD kuralı)
        s = "".join(
            ("s" if durum[g] == "r" and h == "r" else durum[g]) for g, (_, h) in zip(gruplar, baglantilar)
        )
        satir.append(f'    <phase duration="{sure:.0f}" state="{s}"/>')
    satir += ['  </tlLogic>', '</additional>']
    yol = klasor / "sinyal.add.xml"
    yol.write_text("\n".join(satir), encoding="utf-8")
    return yol


def yapilandirma_yaz(klasor: Path, ag: Path, talep: Path, sinyal: Path, sure_s: float, tohum: int = 1) -> Path:
    cfg = klasor / "sim.sumocfg"
    cfg.write_text(f"""<configuration>
  <input>
    <net-file value="{ag.name}"/>
    <route-files value="{talep.name}"/>
    <additional-files value="{sinyal.name}"/>
  </input>
  <time><begin value="0"/><end value="{sure_s + 300:.0f}"/><step-length value="0.5"/></time>
  <random_number><seed value="{tohum}"/></random_number>
  <processing><time-to-teleport value="-1"/></processing>
  <report><no-step-log value="true"/><no-warnings value="true"/></report>
</configuration>""", encoding="utf-8")
    return cfg


def kur(klasor: Path, sayimlar: dict, sure_s: float, yesil: dict, dongu: float, olcek: float = 1.0,
        surucu: dict | None = None, fazlar: list | None = None) -> Path:
    """fazlar verilirse yesil/dongu yerine doğrudan o faz listesi kullanılır."""
    klasor.mkdir(parents=True, exist_ok=True)
    ag = ag_yaz(klasor)
    talep = talep_yaz(klasor, sayimlar, sure_s, olcek, surucu)
    sinyal = sinyal_yaz(klasor, ag, fazlar or faz_plani(yesil, dongu))
    return yapilandirma_yaz(klasor, ag, talep, sinyal, sure_s)


def sim_faz0(yol: str = "data/sinyal_plani.json", isinma_s: float = 120.0) -> float:
    """SUMO döngüsü simülasyon saniyesi 0'da önden-sol fazıyla başlar; kayıtlar ise
    ısınmadan sonra (t = simülasyon saniyesi - isinma_s) başlar. Video döngü
    profilleri güneye düz yeşilinin başından sayılır ve önden-sol orada
    baslangic_s'de başlar. kuyruk_profili(sim, C, sim_faz0()) ikisini hizalar.
    (Veriden en iyi kayma ölçüldüğünde bu formülle ~5 s içinde tutuyor.)"""
    p = json.load(open(yol, encoding="utf-8"))
    C = float(p["dongu_s"])
    return -((float(p["bizim"]["guneye_sol"]["baslangic_s"]) + isinma_s) % C)


def plan_videodan(yol: str = "data/sinyal_plani.json") -> tuple[dict, float]:
    """Yön bazlı yeşil pencerelerinden (sinyal_cikar.py) önden-sol faz süreleri."""
    p = json.load(open(yol, encoding="utf-8"))
    b, C = p["bizim"], p["dongu_s"]
    sol_bas = b["guneye_sol"]["baslangic_s"]
    gd_bas = b["guneye_duz"]["baslangic_s"]
    kd_bas, kd_sure = b["kuzeye_duz"]["baslangic_s"], b["kuzeye_duz"]["sure_s"]
    return {
        "sol_onde": (gd_bas - sol_bas) % C,
        "guney_onde": (kd_bas - gd_bas) % C,
        "ortak": kd_sure,
    }, float(C)
