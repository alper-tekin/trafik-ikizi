"""Compare existing policies with shared insertion and completion accounting.

Cached observations and the recorded agent plan only. No Meta API calls.
Writes a new ignored run folder without replacing UI data or historical reports.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from trafik.akis import talep_sayimlari
from trafik.degerlendir import degerlendir
from trafik import uyarlamali
from trafik.sprint import sha256


def input_hashes():
    files = [ROOT / name for name in ("data/gelisler.parquet", "data/akis_izler.parquet", "data/geometri.json",
             "data/sinyal_plani.json", "data/sim_kalibrasyon.json", "web/veri/ozet.json")]
    files.extend((ROOT / "src/trafik").glob("*.py"))
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--publish", action="store_true", help="Also update the report served by the comparison UI")
    args = parser.parse_args()
    hashes = input_hashes()
    data = json.loads((ROOT / "web/veri/ozet.json").read_text(encoding="utf-8"))
    drivers = {k: data["kalibrasyon"]["en_iyi"][k] for k in ("tau", "accel")}
    counts = talep_sayimlari(pd.read_parquet(ROOT / "data/akis_izler.parquet"))
    results = {}
    for name, plan in (("current", data["mevcut_plan"]), ("agent_recorded", data["ajan"]["cevap"]["recommended_plan"])):
        results[name] = degerlendir(plan, counts, drivers, tuple(args.seeds), gelis="gercek")
        print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
    for name, rule in (("longest_wait", "saf"), ("weighted", "agirlikli")):
        results[name] = uyarlamali.degerlendir(rule, counts, drivers, tuple(args.seeds), gelis="gercek")
        print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
    output = ROOT / "data/sprint" / ("accounting-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    payload = {"seeds": args.seeds, "arrival_mode": "video_replay", "driver_parameters": drivers,
               "input_hashes": hashes,
               "scope": "Existing observations and policies, retrospective comparison; no new controller tuning or model API calls.",
               "results": results}
    if hashes != input_hashes():
        raise RuntimeError("Comparison inputs changed while running; refusing to publish results")
    (output / "result.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    if args.publish:
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports/sprint-accounting.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(output / "result.json")


if __name__ == "__main__":
    main()
