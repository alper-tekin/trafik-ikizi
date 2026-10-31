"""NGSIM Lankershim arşivinden (6,9 GB zip) yalnızca istenen dosyaları indirir.

Sunucu HTTP Range desteklediği için önce zip'in içindekiler listesi okunur,
sonra sadece seçilen dosyanın baytları çekilip açılır.

Kullanım:
    py -3 scripts/ngsim_indir.py --liste
    py -3 scripts/ngsim_indir.py <dosya-adı-parçası> [--hedef data/ngsim]
"""

import argparse
import struct
import sys
import urllib.request
import zlib
from pathlib import Path

URL = (
    "https://data.transportation.gov/api/views/uv3e-y54k/files/"
    "27fbaaac-d4b0-4b04-aacd-253d88f93ea8?filename=NGSIM+Lankershim+Videos.zip"
)
PARCA = 8 * 1024 * 1024


def aralik(bas: int, son: int) -> bytes:
    istek = urllib.request.Request(URL, headers={"Range": f"bytes={bas}-{son}"})
    with urllib.request.urlopen(istek) as yanit:
        return yanit.read()


def toplam_boyut() -> int:
    istek = urllib.request.Request(URL, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(istek) as yanit:
        return int(yanit.headers["Content-Range"].split("/")[1])


def zip64_alanlari(ekstra: bytes, degerler: dict) -> None:
    i = 0
    while i < len(ekstra):
        kimlik, uzunluk = struct.unpack("<HH", ekstra[i : i + 4])
        if kimlik == 1:
            sayilar = list(struct.unpack("<" + "Q" * (uzunluk // 8), ekstra[i + 4 : i + 4 + uzunluk]))
            for alan in ("acik", "sikisik", "ofset"):
                if degerler[alan] == 0xFFFFFFFF:
                    degerler[alan] = sayilar.pop(0)
        i += 4 + uzunluk


def icindekiler() -> list[dict]:
    n = toplam_boyut()
    kuyruk = aralik(n - 65536, n - 1)
    z64 = kuyruk.rfind(b"PK\x06\x06")
    if z64 >= 0:
        boyut, ofset = struct.unpack("<QQ", kuyruk[z64 + 40 : z64 + 56])
    else:
        son = kuyruk.rfind(b"PK\x05\x06")
        boyut, ofset = struct.unpack("<II", kuyruk[son + 12 : son + 20])
    dizin = aralik(ofset, ofset + boyut - 1)

    kayitlar, p = [], 0
    while dizin[p : p + 4] == b"PK\x01\x02":
        yontem = struct.unpack("<H", dizin[p + 10 : p + 12])[0]
        crc, sikisik, acik = struct.unpack("<III", dizin[p + 16 : p + 28])
        ad_u, ek_u, yorum_u = struct.unpack("<HHH", dizin[p + 28 : p + 34])
        yerel = struct.unpack("<I", dizin[p + 42 : p + 46])[0]
        ad = dizin[p + 46 : p + 46 + ad_u].decode("cp437")
        degerler = {"acik": acik, "sikisik": sikisik, "ofset": yerel}
        zip64_alanlari(dizin[p + 46 + ad_u : p + 46 + ad_u + ek_u], degerler)
        kayitlar.append({"ad": ad, "yontem": yontem, "crc": crc, **degerler})
        p += 46 + ad_u + ek_u + yorum_u
    return kayitlar


def indir(kayit: dict, hedef: Path) -> Path:
    baslik = aralik(kayit["ofset"], kayit["ofset"] + 29)
    ad_u, ek_u = struct.unpack("<HH", baslik[26:30])
    bas = kayit["ofset"] + 30 + ad_u + ek_u
    son = bas + kayit["sikisik"] - 1

    cikti = hedef / Path(kayit["ad"]).name
    hedef.mkdir(parents=True, exist_ok=True)
    acici = zlib.decompressobj(-15) if kayit["yontem"] == 8 else None
    crc = 0
    with open(cikti, "wb") as f:
        for i in range(bas, son + 1, PARCA):
            veri = aralik(i, min(i + PARCA - 1, son))
            if acici:
                veri = acici.decompress(veri)
            crc = zlib.crc32(veri, crc)
            f.write(veri)
            print(f"\r{(i - bas) * 100 // kayit['sikisik']:3d}%", end="", flush=True)
        if acici:
            kalan = acici.flush()
            crc = zlib.crc32(kalan, crc)
            f.write(kalan)
    print("\r100%")
    if crc != kayit["crc"]:
        cikti.unlink()
        sys.exit(f"CRC uyuşmadı, dosya silindi: {kayit['ad']}")
    return cikti


def onizle(kayit: dict, hedef: Path, bayt: int) -> Path:
    """Dosyanın yalnızca başını indirir; ffmpeg ilk kareleri okuyabilsin diye."""
    baslik = aralik(kayit["ofset"], kayit["ofset"] + 29)
    ad_u, ek_u = struct.unpack("<HH", baslik[26:30])
    bas = kayit["ofset"] + 30 + ad_u + ek_u
    veri = aralik(bas, bas + min(bayt, kayit["sikisik"]) - 1)
    if kayit["yontem"] == 8:
        veri = zlib.decompressobj(-15).decompress(veri)
    hedef.mkdir(parents=True, exist_ok=True)
    cikti = hedef / Path(kayit["ad"]).name
    cikti.write_bytes(veri)
    return cikti


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ad", nargs="?")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--hedef", default="data/ngsim")
    ap.add_argument("--onizleme-mb", type=float, help="yalnızca ilk N MB'ı indir")
    ap.add_argument("--url", help="başka bir NGSIM zip arşivi (varsayılan: Lankershim videoları)")
    args = ap.parse_args()
    if args.url:
        global URL
        URL = args.url

    kayitlar = [k for k in icindekiler() if not k["ad"].endswith("/")]
    if args.liste or not args.ad:
        for k in kayitlar:
            print(f"{k['sikisik'] / 1e6:9.1f} MB  {Path(k['ad']).name}")
        return

    eslesen = [k for k in kayitlar if Path(k["ad"]).name == args.ad]
    if len(eslesen) != 1:
        sys.exit(f"Tam ad bulunamadı: {args.ad}")
    if args.onizleme_mb:
        print(onizle(eslesen[0], Path(args.hedef), int(args.onizleme_mb * 1e6)))
    else:
        print(indir(eslesen[0], Path(args.hedef)))


if __name__ == "__main__":
    main()
