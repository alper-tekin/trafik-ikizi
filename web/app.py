"""Arayüz sunucusu.

    PYTHONPATH=src .venv/Scripts/python -m uvicorn web.app:app --port 8020

Ajan uç noktası varsayılan olarak son kaydedilmiş koşuyu adım adım yeniden
oynatır (API kredisi harcamaz). CANLI_AJAN=1 ortam değişkeniyle gerçek
Muse Spark koşusu açılır; aynı anda yalnızca bir koşu çalışır.
"""

import asyncio
import json
import os
import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

KOK = Path(__file__).parent
app = FastAPI(title="trafik-ikizi")
app.mount("/static", StaticFiles(directory=KOK / "static"), name="static")
app.mount("/veri", StaticFiles(directory=KOK / "veri"), name="veri")

_kilit = threading.Lock()


@app.middleware("http")
async def onbellek_basligi(istek, sonraki):
    """Sayfa ve veri dosyaları yeniden üretildiğinde tarayıcı eskisini göstermesin:
    her istekte doğrulat (değişmediyse 304 döner). Büyük video önbellekte kalabilir."""
    yanit = await sonraki(istek)
    if not istek.url.path.endswith(".mp4"):
        yanit.headers["Cache-Control"] = "no-cache"
    return yanit


@app.get("/")
def ana_sayfa():
    return FileResponse(KOK / "index.html")


@app.get("/api/durum")
def durum():
    return {"canli_ajan": os.environ.get("CANLI_AJAN") == "1", "ajan_mesgul": _kilit.locked()}


def _sse(olay: dict) -> str:
    return f"data: {json.dumps(olay, ensure_ascii=False, default=str)}\n\n"


async def _yeniden_oynat():
    ozet = json.loads((KOK / "veri" / "ozet.json").read_text(encoding="utf-8"))["ajan"]
    yield _sse({"tur": "basladi", "kaynak": "kayit", "model": ozet["model"]})
    for i, a in enumerate(ozet["adimlar"], 1):
        await asyncio.sleep(0.9 if a["arac"] == "test_plan" else 0.5)
        yield _sse({"tur": "adim", "no": i, **a})
    await asyncio.sleep(0.6)
    yield _sse({"tur": "cevap", "cevap": ozet["cevap"]})
    yield _sse({"tur": "dogrulama", "dogrulama": ozet["dogrulama"]})
    yield _sse({"tur": "bitti"})


async def _canli(soru: str):
    from trafik.ajan import calistir

    if not _kilit.acquire(blocking=False):
        yield _sse({"tur": "hata", "mesaj": "ajan şu an başka bir koşuda"})
        yield _sse({"tur": "bitti"})
        return
    kuyruk: queue.Queue = queue.Queue()

    def is_parcacigi():
        try:
            calistir(soru, bildir=kuyruk.put)
        except Exception as hata:
            kuyruk.put({"tur": "hata", "mesaj": repr(hata)})
        finally:
            kuyruk.put({"tur": "bitti"})
            _kilit.release()

    threading.Thread(target=is_parcacigi, daemon=True).start()
    yield _sse({"tur": "basladi", "kaynak": "canli", "model": "muse-spark-1.3"})
    while True:
        try:
            olay = kuyruk.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.2)
            continue
        yield _sse(olay)
        if olay["tur"] == "bitti":
            break


@app.get("/api/ajan")
async def ajan(soru: str = "Find a better signal plan for this intersection.", canli: int = 0):
    if canli and os.environ.get("CANLI_AJAN") != "1":
        raise HTTPException(403, "canlı ajan kapalı (CANLI_AJAN=1 ile açılır)")
    if canli and _kilit.locked():
        raise HTTPException(409, "ajan şu an başka bir koşuda")
    akis = _canli(soru) if canli else _yeniden_oynat()
    return StreamingResponse(akis, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
