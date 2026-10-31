"""Muse Spark sinyal planlama ajanını çalıştırır; kaydı data/ajan/ altına yazar.

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/ajan_calistir.py ["soru"]
"""

import json
import sys

from trafik.ajan import calistir


def main() -> None:
    soru = sys.argv[1] if len(sys.argv) > 1 else "Find a better signal plan for this intersection."
    k = calistir(soru)
    print(f"{len(k['adimlar'])} araç çağrısı, {k['bitis'] - k['baslangic']:.0f} s")
    print(json.dumps(k["cevap"], ensure_ascii=False, indent=2))
    print("doğrulama:", json.dumps(k["dogrulama"], ensure_ascii=False, indent=2))
    print(k["yol"])


if __name__ == "__main__":
    main()
