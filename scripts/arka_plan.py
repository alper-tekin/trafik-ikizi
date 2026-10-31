"""Videodan araçsız yol görüntüsü çıkarır (piksel başına zaman ortancası).

Hareket eden araçlar çoğu karede başka yerde olduğu için ortancada kaybolur;
geriye yolun gerçek görüntüsü kalır: şerit çizgileri, geçitler, refüjler.
Kamera sabit olduğundan görüntü arayüz çizimlerinin altına birebir oturur.

Kullanım:
    .venv/Scripts/python scripts/arka_plan.py
"""

import cv2
import numpy as np

VIDEO = "data/ngsim/lankershim-camera2-0830am-0845am.avi"
CIKTI = "web/static/arka_plan.jpg"
ORNEK = 240


def main() -> None:
    v = cv2.VideoCapture(VIDEO)
    n = int(v.get(cv2.CAP_PROP_FRAME_COUNT))
    kareler = []
    for i in np.linspace(0, n - 1, ORNEK).astype(int):
        v.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, k = v.read()
        if ok:
            kareler.append(k)
    arka = np.median(np.stack(kareler), axis=0).astype(np.uint8)
    cv2.imwrite(CIKTI, arka, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(CIKTI, len(kareler), "kare")


if __name__ == "__main__":
    main()
