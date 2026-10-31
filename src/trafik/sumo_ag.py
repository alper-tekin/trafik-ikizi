"""Kavşak 2'nin SUMO modelini videodan çıkarılan veriyle kurar.

  - Ağ: dört kollu kavşak. Lankershim her yönde 3 şerit, güneye gidişte
    ayrıca sol dönüş cebi; ara sokak her yönde 2 şerit (NGSIM şerit
    etiketlerinden).
  - Talep: video penceresindeki yön x hareket sayımları -> araç/saat.
  - Sinyal: döngü ve yeşil süreleri data/sinyal_plani.json'dan; sarı 3 s,
    tüm-kırmızı 1 s. Ara sokağın yeşili döngünün kalanıdır.
"""

import json
import subprocess
from pathlib import Path

import sumolib

SARI, TUM_KIRMIZI = 3, 1
KOL_UZUNLUK_M = 300.0
YON_KOL = {2: "G", 4: "K", 1: "B", 3: "D"}  # gidiş yönü -> giriş kolu
HAREKET_HARF = {1: "s", 2: "l", 3: "r"}
SAAT = 3600.0

# kol: (u, w) birim yön, şerit sayısı (giriş, çıkış). NGSIM şerit etiketlerinden:
# kuzeye giden yaklaşım 4 şerit + sağ cep (11); güneye giden 3 şerit + 2 sol cep
# (11, 12); güneye çıkış 4, kuzeye çıkış 3 şerit.
KOLLAR = {
    "K": ((1, 0), 5, 3),
    "G": ((-1, 0), 5, 4),
    "D": ((0, 1), 2, 2),
    "B": ((0, -1), 2, 2),
}
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


def ag_yaz(klasor: Path) -> Path:
    dugum = ['<nodes>', '  <node id="M" x="0" y="0" type="traffic_light"/>']
    kenar = ['<edges>']
    for k, ((u, w), n_giris, n_cikis) in KOLLAR.items():
        # SUMO'da x doğu, y kuzey
        x, y = w * KOL_UZUNLUK_M, u * KOL_UZUNLUK_M
        dugum.append(f'  <node id="{k}" x="{x}" y="{y}" type="priority"/>')
        kenar.append(f'  <edge id="{k}_gir" from="{k}" to="M" numLanes="{n_giris}" speed="13.9"/>')
        kenar.append(f'  <edge id="{k}_cik" from="M" to="{k}" numLanes="{n_cikis}" speed="13.9"/>')
    dugum.append('</nodes>')
    kenar.append('</edges>')
    (klasor / "ag.nod.xml").write_text("\n".join(dugum), encoding="utf-8")
    (klasor / "ag.edg.xml").write_text("\n".join(kenar), encoding="utf-8")
    ag = klasor / "ag.net.xml"
    # SUMO, ASCII dışı karakter içeren tam yolları (ör. "Masaüstü") açamıyor;
    # klasörün içinden göreli adlarla çalıştırılır.
    subprocess.run(
        [_sumo_bin("netconvert"), "-n", "ag.nod.xml", "-e", "ag.edg.xml", "-o", ag.name,
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
    """sayimlar: (yön, hareket) -> araç sayısı (sure_s içinde).
    surucu: SUMO vType parametreleri (accel, tau, minGap...) videoya kalibre edilmiş değerler."""
    p = {"length": 4.8, "minGap": 2.0, "accel": 2.0, "decel": 4.5, "sigma": 0.5, "tau": 1.0, **(surucu or {})}
    ozellik = " ".join(f'{k}="{v}"' for k, v in p.items())
    satir = ['<routes>', f'  <vType id="oto" {ozellik}/>']
    for (yon, hareket), n in sorted(sayimlar.items()):
        giris = YON_KOL[yon]
        cikis = CIKIS[(giris, hareket)]
        saatlik = n / sure_s * SAAT * olcek
        if saatlik <= 0:
            continue
        satir.append(
            f'  <flow id="{giris}{HAREKET_HARF[hareket]}" type="oto" from="{giris}_gir" to="{cikis}_cik" '
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
