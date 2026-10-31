"""NGSIM Lankershim araç yörüngelerini data.transportation.gov API'sinden indirir.

Ekteki zip arşivi sunucuda bozuk olduğu için veri Socrata API'sinden sayfa
sayfa çekilir ve tek bir gzip'li CSV'ye yazılır.

Kullanım:
    py -3 scripts/yorunge_indir.py [--hedef data/ngsim/lankershim_yorunge.csv.gz]
"""

import argparse
import gzip
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://data.transportation.gov/resource/8ect-6jqj.csv"
SAYFA = 200_000


def sayfa_cek(ofset: int) -> list[bytes]:
    sorgu = urllib.parse.urlencode({
        "$where": "location='lankershim'",
        "$order": "global_time, vehicle_id",
        "$limit": SAYFA,
        "$offset": ofset,
    })
    istek = urllib.request.Request(f"{API}?{sorgu}", headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(istek, timeout=600) as yanit:
        veri = yanit.read()
        if yanit.headers.get("Content-Encoding") == "gzip":
            veri = gzip.decompress(veri)
    return veri.splitlines(keepends=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedef", default="data/ngsim/lankershim_yorunge.csv.gz")
    args = ap.parse_args()

    hedef = Path(args.hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_suffix(".part")
    toplam, ofset = 0, 0
    with gzip.open(gecici, "wb") as f:
        while True:
            satirlar = sayfa_cek(ofset)
            baslik, govde = satirlar[0], satirlar[1:]
            if ofset == 0:
                f.write(baslik)
            f.writelines(govde)
            toplam += len(govde)
            print(f"{toplam:,} satır", flush=True)
            if len(govde) < SAYFA:
                break
            ofset += SAYFA
    gecici.replace(hedef)
    print(hedef)
    kavsak2_alt_kumesi(hedef)


def kavsak2_alt_kumesi(kaynak: Path) -> None:
    """Kamera 2'nin baktığı bölge (kavşak 2 çevresi, local_y 150-700 ft) ve
    yörünge başlangıcından itibaren saniye cinsinden zaman (t)."""
    import pandas as pd

    d = pd.read_csv(kaynak)
    d["t"] = (d.global_time - d.global_time.min()) / 1000.0
    alt = d[(d.local_y > 150) & (d.local_y < 700)]
    yol = kaynak.parent / "kavsak2.parquet"
    alt.to_parquet(yol)
    print(yol, len(alt), "satır")


if __name__ == "__main__":
    main()
