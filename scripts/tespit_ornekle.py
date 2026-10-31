"""Videodan her N karede bir kare alıp SAM 3.1 ile araç tespiti yapar.

Sonuçlar kare numarasına göre JSON satırları olarak önbelleğe yazılır;
önbellekte olan kare tekrar gönderilmez (API kredisi boşa gitmesin).

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/tespit_ornekle.py --adim 20
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

from trafik.sam import istemci, tespit

VIDEO = "data/ngsim/lankershim-camera2-0830am-0845am.avi"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adim", type=int, default=20, help="kaç karede bir (10 fps)")
    ap.add_argument("--kavram", default="car")
    ap.add_argument("--is-parcacigi", type=int, default=8)
    ap.add_argument("--cikti", default="data/tespit/{kavram}.jsonl")
    args = ap.parse_args()

    cikti = Path(args.cikti.format(kavram=args.kavram.replace(" ", "_")))
    cikti.parent.mkdir(parents=True, exist_ok=True)
    bitmis = set()
    if cikti.exists():
        bitmis = {json.loads(s)["kare"] for s in cikti.open(encoding="utf-8")}

    video = cv2.VideoCapture(VIDEO)
    toplam_kare = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    bekleyen = sum(1 for i in range(0, toplam_kare, args.adim) if i not in bitmis)
    print(f"{bekleyen} kare gönderilecek ({len(bitmis)} önbellekte)")

    client = istemci()

    def isle(oge):
        no, kare = oge
        for deneme in range(4):
            try:
                kutular = tespit(client, kare, args.kavram)
                break
            except Exception as hata:  # ağ/oran sınırı hataları geçicidir
                if deneme == 3:
                    raise
                print(f"kare {no}: {hata!r}, yeniden deneniyor", flush=True)
                time.sleep(2 ** deneme * 2)
        return {"kare": no, "kutular": [[k.x1, k.y1, k.x2, k.y2, k.guven] for k in kutular]}

    def kareler():
        i = 0
        while True:
            ok, kare = video.read()
            if not ok:
                return
            if i % args.adim == 0 and i not in bitmis:
                yield i, kare
            i += 1

    # Videonun tamamı belleğe sığmaz; kareler küçük gruplar halinde gönderilir.
    grup_boyu = args.is_parcacigi * 4
    n = 0
    with ThreadPoolExecutor(args.is_parcacigi) as havuz, cikti.open("a", encoding="utf-8") as f:
        grup = []
        for oge in kareler():
            grup.append(oge)
            if len(grup) < grup_boyu:
                continue
            for sonuc in havuz.map(isle, grup):
                f.write(json.dumps(sonuc) + "\n")
            f.flush()
            n += len(grup)
            grup = []
            print(f"{n}/{bekleyen}", flush=True)
        for sonuc in havuz.map(isle, grup):
            f.write(json.dumps(sonuc) + "\n")
        n += len(grup)
    print(f"{n}/{bekleyen}")
    print(cikti)


if __name__ == "__main__":
    main()
