"""Kavşak geometrisini videodaki izlerden ölçer ve data/geometri.json'a yazar.

SUMO ağı (sumo_ag.ag_yaz) bu dosyadan kurulur: kol yönleri, şerit sayısı ve
genişliği, durma çizgileri, kavşak alanı.

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/geometri_olc.py
"""

import pandas as pd

from trafik import geometri


def main() -> None:
    g = geometri.olc(pd.read_parquet("data/izler_kamera2.parquet"), pd.read_parquet("data/akis_izler.parquet"))
    geometri.kaydet(g)
    for k, v in geometri.yukle()["kollar"].items():
        print(f"{k}: yön {v['e']}, gelen {v['gelen']['n']} x {v['gelen']['genislik']:.2f} m, "
              f"giden {v['giden']['n']}, durma {v['durma_m']:.1f} m")
    print("data/geometri.json")


if __name__ == "__main__":
    main()
