"""Arayüz için takip katmanlı video üretir (tarayıcıda oynayan H.264 MP4).

Her karede: SAM 3.1 kutuları (en yakın tespit karesinden) ve izlerin son
2 saniyelik kuyruğu, iz rengiyle. Kareler ffmpeg'e borudan aktarılır.

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/video_katman.py
"""

import json
import subprocess
from collections import defaultdict

import cv2
import numpy as np
import pandas as pd

VIDEO = "data/ngsim/lankershim-camera2-0830am-0845am.avi"
CIKTI = "web/static/video_katman.mp4"


def renk(no: int) -> tuple[int, int, int]:
    rng = np.random.default_rng(no)
    h = int(rng.integers(0, 180))
    bgr = cv2.cvtColor(np.uint8([[[h, 200, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return tuple(int(c) for c in bgr)


def main() -> None:
    H = np.load("data/kalibrasyon_kamera2.npy")
    Hi = np.linalg.inv(H)
    izler = pd.read_parquet("data/izler_kamera2.parquet")
    px = cv2.perspectiveTransform(izler[["x", "y"]].to_numpy().reshape(-1, 1, 2).astype(np.float64), Hi).reshape(-1, 2)
    izler = izler.assign(px=px[:, 0], py=px[:, 1])
    kare_izleri = defaultdict(list)
    for iz, kare, x, y in izler[["iz", "kare", "px", "py"]].itertuples(index=False):
        kare_izleri[kare].append((iz, x, y))
    kutular = {}
    for s in open("data/tespit/vehicle.jsonl", encoding="utf-8"):
        d = json.loads(s)
        kutular[d["kare"]] = d["kutular"]

    import os
    os.makedirs("web/static", exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "640x480", "-r", "10",
         "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-preset", "veryfast",
         "-movflags", "+faststart", CIKTI],
        stdin=subprocess.PIPE,
    )
    video = cv2.VideoCapture(VIDEO)
    gecmis = defaultdict(list)  # iz -> [(kare, x, y)]
    i = 0
    while True:
        ok, kare = video.read()
        if not ok:
            break
        ref = i - (i % 2)
        for b in kutular.get(ref, []):
            cv2.rectangle(kare, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (255, 255, 255), 1)
        for iz, x, y in kare_izleri.get(ref, []) if i % 2 == 0 else []:
            gecmis[iz].append((i, x, y))
        for iz in list(gecmis):
            noktalar = [(x, y) for k, x, y in gecmis[iz] if i - k <= 20]
            if not noktalar:
                del gecmis[iz]
                continue
            gecmis[iz] = [p for p in gecmis[iz] if i - p[0] <= 20]
            c = renk(iz)
            pts = np.array(noktalar, dtype=np.int32)
            cv2.polylines(kare, [pts], False, c, 2, cv2.LINE_AA)
            cv2.circle(kare, tuple(pts[-1]), 3, c, -1, cv2.LINE_AA)
        cv2.putText(kare, f"{i / 10:6.1f}s", (8, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        ff.stdin.write(kare.tobytes())
        i += 1
    ff.stdin.close()
    ff.wait()
    print(CIKTI, i, "kare")


if __name__ == "__main__":
    main()
