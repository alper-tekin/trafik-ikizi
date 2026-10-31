"""Araçsız yol fotoğrafını SAM 3.1 ile katmanlara ayırır ve vektör çokgenlere çevirir.

Her katman bir kavram istemidir ("road", "crosswalk"...). Maskeler kameranın kendi
piksel düzleminde olduğu için çizim videoyla birebir örtüşür; arayüz bu çokgenleri
kendi renkleriyle çizer (fotoğrafın kendisini göstermez).

Çıktı: web/veri/sahne.json  {genislik, yukseklik, katmanlar: {ad: [[ [x,y], ... ], ...]}}
SAM yanıtları data/sahne/ altında önbelleğe alınır.

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/sahne_katmanlari.py
"""

import base64
import json
from pathlib import Path

import cv2
import numpy as np

from trafik.sam import istemci
from trafik.sam_maske import maskeler

GORUNTU = "web/static/arka_plan.jpg"
ONBELLEK = Path("data/sahne")
# katman adı -> SAM kavram istemleri (istem başına bir istek; maskeler birleştirilir).
# Bir kavram bazı bölgeleri kaçırabiliyor (ör. parlak betondaki kesik çizgiler), o yüzden
# çizgiler için birden çok istem var.
KATMANLAR = {
    "yol": ["road"],
    "kaldirim": ["sidewalk"],
    "gecit": ["crosswalk"],
    "beyaz_cizgi": ["white lane line", "dashed lane line", "stop line"],
    "sari_cizgi": ["yellow line"],
    "ok": ["road arrow marking"],
    "cim": ["grass"],
    "agac": ["tree"],
    "bina": ["building roof"],
}


def sor(anahtar: str, url: str, kavram: str | None = None) -> str:
    """anahtar önbellek dosyasını adlandırır; kavram SAM'e giden istemdir (varsayılan: anahtar)."""
    yol = ONBELLEK / f"{anahtar.replace(' ', '_')}.txt"
    if yol.exists():
        return yol.read_text(encoding="utf-8")
    yanit = istemci().responses.create(
        model="sam-3.1",
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": kavram or anahtar}, {"type": "input_image", "image_url": url}]}],
        metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
    )
    yol.write_text(yanit.output_text, encoding="utf-8")
    return yanit.output_text


def karo_maskeleri(img: np.ndarray, kavram: str, karo: int = 2, buyutme: int = 2, ortusme: int = 40) -> np.ndarray:
    """İnce ve soluk işaretler için: görüntüyü örtüşen karolara böl, kontrastı artır (CLAHE),
    büyüt, her karoda ayrı sor; maskeleri tam kareye geri yerleştir."""
    h, w = img.shape[:2]
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    guclu = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    birlesik = np.zeros((h, w), dtype=np.uint8)
    for i in range(karo):
        for j in range(karo):
            y0, y1 = max(0, i * h // karo - ortusme), min(h, (i + 1) * h // karo + ortusme)
            x0, x1 = max(0, j * w // karo - ortusme), min(w, (j + 1) * w // karo + ortusme)
            parca = cv2.resize(guclu[y0:y1, x0:x1], None, fx=buyutme, fy=buyutme, interpolation=cv2.INTER_CUBIC)
            ok, png = cv2.imencode(".png", parca)
            url = "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()
            for k in maskeler(sor(f"{kavram} karo{i}{j}", url, kavram)):
                if k["guven"] is not None and k["guven"] < 0.3:
                    continue
                kucuk = cv2.resize(k["maske"], (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
                birlesik[y0:y1, x0:x1] |= kucuk
    return birlesik


def cokgenler(maske: np.ndarray, en_az_alan: float, sadelik: float) -> list:
    """Maske -> sadeleştirilmiş dış hat çokgenleri (delikler ayrı çizilmez; çizim sırası kapatır)."""
    konturlar, _ = cv2.findContours(maske.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cikti = []
    for k in konturlar:
        if cv2.contourArea(k) < en_az_alan:
            continue
        k = cv2.approxPolyDP(k, sadelik, True)
        cikti.append(k.reshape(-1, 2).astype(float).round(1).tolist())
    return cikti


def main() -> None:
    ONBELLEK.mkdir(parents=True, exist_ok=True)
    img = cv2.imread(GORUNTU)
    h, w = img.shape[:2]
    ok, png = cv2.imencode(".png", img)
    url = "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()

    sahne = {"genislik": w, "yukseklik": h, "katmanlar": {}, "ozet": {}}
    for ad, kavramlar in KATMANLAR.items():
        kayitlar = [k for kavram in kavramlar for k in maskeler(sor(kavram, url))]
        birlesik = np.zeros((h, w), dtype=np.uint8)
        for k in kayitlar:
            if k["guven"] is None or k["guven"] >= 0.3:
                birlesik |= k["maske"]
        ince = ad in ("beyaz_cizgi", "sari_cizgi", "ok")
        if not ince:  # geniş yüzeyler: maske sınırındaki tırtıkları yumuşat
            cekirdek = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            birlesik = cv2.morphologyEx(cv2.morphologyEx(birlesik, cv2.MORPH_OPEN, cekirdek), cv2.MORPH_CLOSE, cekirdek)
        if ince:  # soluk işaretler: kontrastı artırılmış, büyütülmüş karolarda da sor
            birlesik |= karo_maskeleri(img, kavramlar[0])
            birlesik &= (cv2.dilate(yol_maskesi, np.ones((5, 5), np.uint8)) > 0).astype(np.uint8)
        if ad == "yol":
            # Yol maskesinde gedikler var (ağaç gölgesi, refüj kenarı). Büyük bir kapatmayla
            # doldur, ama kaldırım/çimen/bina olduğu bilinen pikselleri dışarıda bırak ki
            # kavşak köşeleri ve kaldırımlar yola karışmasın.
            yol_disi = np.zeros((h, w), dtype=np.uint8)
            for kavram in ("sidewalk", "grass", "building roof"):
                for k in maskeler(sor(kavram, url)):
                    yol_disi |= k["maske"]
            kapali = cv2.morphologyEx(birlesik, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61)))
            birlesik |= kapali & (1 - yol_disi)
            yol_maskesi = birlesik.copy()
        sahne["katmanlar"][ad] = cokgenler(birlesik, 2 if ince else 30, 0.6 if ince else 2.0)
        sahne["ozet"][ad] = {"kayit": len(kayitlar), "kaplama": round(float(birlesik.mean()), 4),
                             "cokgen": len(sahne["katmanlar"][ad])}
        print(ad, sahne["ozet"][ad])
    # Boyası fotoğrafta görünmeyen kollar: yol yüzeyinde şerit çizgisi oranı düşükse arayüz o
    # kolda şerit ayırıcılarını araçların izlediği şeritlerden (geometri.json) çizer.
    from trafik import geometri
    from trafik.akis import kol
    cizgi = np.zeros((h, w), np.uint8)
    for p in sahne["katmanlar"]["beyaz_cizgi"]:
        cv2.fillPoly(cizgi, [np.array(p, np.int32)], 1)
    ys, xs = np.mgrid[0:h, 0:w]
    v = np.linalg.inv(geometri.goruntu_donusumu()) @ np.stack([xs.ravel(), ys.ravel(), np.ones(xs.size)])
    uw = (v[:2] / v[2]).T
    r, k = np.hypot(uw[:, 0], uw[:, 1]).reshape(h, w), kol(uw).reshape(h, w)
    sahne["serit_boyasi"] = {}
    for a in "KGDB":
        bolge = (k == a) & (r > 22) & (r < 70) & (yol_maskesi > 0)
        sahne["serit_boyasi"][a] = round(float(cizgi[bolge].mean()), 3) if bolge.any() else 0.0
    sahne["olculen_serit_kollari"] = [a for a, o in sahne["serit_boyasi"].items() if o < 0.10]
    print("şerit boyası oranı", sahne["serit_boyasi"], "-> ölçülen şeritler:", sahne["olculen_serit_kollari"])

    Path("web/veri").mkdir(parents=True, exist_ok=True)
    Path("web/veri/sahne.json").write_text(json.dumps(sahne, separators=(",", ":")), encoding="utf-8")
    print("web/veri/sahne.json", round(Path("web/veri/sahne.json").stat().st_size / 1e3), "kB")


if __name__ == "__main__":
    main()
