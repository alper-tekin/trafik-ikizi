"""Muse Spark sinyal planlama ajanını çalıştırır; kaydı data/ajan/ altına yazar.

Kullanım:
    PYTHONPATH=src .venv/Scripts/python scripts/ajan_calistir.py ["soru"]
"""

import argparse
import json

from trafik.ajan import calistir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("soru", nargs="?", default="Find a better signal plan for this intersection.")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be positive")
    k = calistir(args.soru, en_cok_adim=args.max_steps)
    print(f"{len(k['adimlar'])} araç çağrısı, {k['bitis'] - k['baslangic']:.0f} s")
    print(json.dumps(k["cevap"], ensure_ascii=False, indent=2))
    print("doğrulama:", json.dumps(k["dogrulama"], ensure_ascii=False, indent=2))
    print(k["yol"])


if __name__ == "__main__":
    main()
