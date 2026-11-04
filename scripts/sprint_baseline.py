"""Freeze inputs, rerun the current plan and diagnose approach-specific errors.

Run from the repository root:
    .venv/Scripts/python scripts/sprint_baseline.py

No Meta API requests. Existing data, calibrations and web demo files are not
overwritten. Each run creates a new data/sprint/<UTC timestamp>/ directory.
"""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from trafik import olcum
from trafik.akis import talep_sayimlari
from trafik.degerlendir import degerlendir
from trafik.simule import calistir
from trafik.sprint import (ARMS, arrival_diagnostics, paired_waits, queue_series,
                           sha256, validate_config, wait_summary, window_waits)
from trafik.sumo_ag import faz_plani_surelerden, kur, plan_videodan


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def freeze(output: Path, config: dict):
    """Only an explicit allowlist is read. In particular, never read .env."""
    files = [ROOT / "README.md", ROOT / "requirements.txt", ROOT / "config/sprint.json"]
    for folder, pattern in (("src", "*.py"), ("scripts", "*.py"), ("tests", "*.py"), ("web", "*.html"), ("web/static", "*.js")):
        files.extend((ROOT / folder).rglob(pattern))
    files.extend((ROOT / "data").glob("*.*"))
    files.extend((ROOT / "data/ngsim").glob("*.parquet"))
    files.extend((ROOT / "data/ngsim").glob("*.avi"))
    files.extend((ROOT / "data/tespit").glob("*.jsonl"))
    files.extend((ROOT / "data/ajan").glob("kosu_*.json"))
    files.append(ROOT / "web/veri/ozet.json")
    inventory = {}
    for path in sorted(set(files)):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        entry = {"sha256": sha256(path), "bytes": path.stat().st_size}
        # Large source assets are hashed in place; small inputs/code are copied.
        if path.stat().st_size <= 5_000_000:
            target = output / "snapshot" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            entry["snapshot"] = target.relative_to(output).as_posix()
        inventory[relative] = entry
    packages = dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions() if d.metadata["Name"]))
    manifest = {
        "schema_version": 1, "captured_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"), "git_status": git("status", "--short"),
        "python": platform.python_version(), "packages": packages, "protocol": config,
        "files": inventory,
        "provenance": [
            "NGSIM positions are used to fit camera homography/time offset and define the local coordinate origin/axis.",
            "The large-vehicle length threshold was selected using NGSIM class comparisons (akis.BUYUK_FT).",
            "Existing geometry, signal estimates and driver parameters have seen the full video.",
            "No window in this existing video is an independent, unseen test."
        ],
    }
    dump(output / "manifest.json", manifest)
    print(f"Snapshot: {len(inventory)} hashed files", flush=True)
    return manifest


def diagnose(config, twin, arrivals, trips, geometry):
    flow = pd.read_parquet(ROOT / "data/akis_izler.parquet")
    video = olcum.noktalar_izden(pd.read_parquet(ROOT / "data/izler_kamera2.parquet"), flow)
    # Current real-arrival IDs end in the original numeric video track ID.
    twin = twin.copy()
    twin["arac"] = twin.arac.str.rsplit(".", n=1).str[-1].astype(int)
    report = {"arrival_diagnostics": arrival_diagnostics(arrivals, trips, geometry), "windows": {}}
    vw = window_waits(video, 0, config["video_duration_s"])
    tw = window_waits(twin, 0, config["video_duration_s"])
    common = vw.index.intersection(tw.index)
    paired = vw.loc[common].join(tw.wait_s.rename("twin_wait_s"))
    paired = paired.assign(error_s=paired.twin_wait_s - paired.wait_s)
    report["largest_wait_mismatches"] = [
        {"track_id": int(i), "arm": r.giris, "video_wait_s": round(r.wait_s, 3),
         "twin_wait_s": round(r.twin_wait_s, 3), "twin_minus_video_s": round(r.error_s, 3),
         "video_first_s": float(video.loc[video.arac == i, "t"].min()),
         "video_last_s": float(video.loc[video.arac == i, "t"].max())}
        for i, r in paired.loc[paired.error_s.abs().nlargest(12).index].iterrows()
    ]
    for name, (start, end) in {"full_video": [0.0, config["video_duration_s"]], **config["windows"]}.items():
        vw, tw = (window_waits(d, start, end) for d in (video, twin))
        vq, tq = (queue_series(d, start, end) for d in (video, twin))
        report["windows"][name] = {
            "interval_s": [start, end], "status": "retrospective_only",
            "measure": "Observed stopped exposure within this window, speed <1 m/s and 12-75 m from centre; not full-journey wait.",
            "video": wait_summary(vw), "twin": wait_summary(tw),
            "paired_same_tracks": paired_waits(vw, tw),
            "queue_comparison_by_arm": {
                arm: {
                    "paired_seconds": int((vq[arm].notna() & tq[arm].notna()).sum()),
                    "requested_seconds": len(vq),
                    "rmse_veh": round(float(np.sqrt(((vq[arm] - tq[arm]) ** 2).mean())), 3)
                    if (vq[arm].notna() & tq[arm].notna()).any() else None,
                } for arm in ARMS
            },
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-only", action="store_true")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT.resolve():
        raise SystemExit("Run this script from the repository root")
    config = json.loads((ROOT / "config/sprint.json").read_text(encoding="utf-8"))
    validate_config(config)
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "data/sprint" / run
    output.mkdir(parents=True, exist_ok=False)
    manifest = freeze(output, config)
    if args.snapshot_only:
        print(output)
        return
    flow = pd.read_parquet(ROOT / "data/akis_izler.parquet")
    counts = talep_sayimlari(flow)
    calibration = json.loads((ROOT / "data/sim_kalibrasyon.json").read_text(encoding="utf-8"))
    drivers = {key: calibration["en_iyi"][key] for key in ("tau", "accel")}
    greens, cycle = plan_videodan()
    plan = {**greens, "ara_sokak": cycle - sum(greens.values()) - 8}
    measured = degerlendir(plan, counts, drivers, tuple(config["driver_seeds"]), gelis="gercek")
    phases = faz_plani_surelerden(**plan)
    cfg = kur(Path("sim/sprint") / run, counts, config["video_duration_s"], {}, 0,
              surucu=drivers, fazlar=phases, gelis="gercek")
    # Dedicated trip output for insertion/completion diagnostics, without touching the web demo.
    tree = ET.parse(cfg)
    output_xml = ET.SubElement(tree.getroot(), "output")
    ET.SubElement(output_xml, "tripinfo-output", value="trip_diagnostics.xml")
    tree.write(cfg, encoding="utf-8", xml_declaration=True)
    twin = calistir(cfg, tohum=config["driver_seeds"][0])
    twin.to_parquet(output / "twin_seed1.parquet", index=False)
    trips = pd.DataFrame([
        {"arac": int(t.get("id").rsplit(".", 1)[-1]), "depart_delay_s": float(t.get("departDelay")),
         "time_loss_s": float(t.get("timeLoss")), "waiting_time_s": float(t.get("waitingTime"))}
        for t in ET.parse(cfg.parent / "trip_diagnostics.xml").getroot().iter("tripinfo")
    ], columns=["arac", "depart_delay_s", "time_loss_s", "waiting_time_s"])
    arrivals = pd.read_parquet(ROOT / "data/gelisler.parquet")
    geometry = json.loads((ROOT / "data/geometri.json").read_text(encoding="utf-8"))["kollar"]
    diagnostic = diagnose(config, twin, arrivals, trips, geometry)
    changed = [name for name, entry in manifest["files"].items() if sha256(ROOT / name) != entry["sha256"]]
    if changed:
        raise RuntimeError(f"Inputs changed during the run; baseline invalid: {changed}")
    recorded = json.loads((ROOT / "web/veri/ozet.json").read_text(encoding="utf-8"))["ajan"]["dogrulama"]
    baseline = {
        "schema_version": 1, "run_id": run, "git_commit": manifest["git_commit"],
        "manifest_sha256": sha256(output / "manifest.json"), "protocol": config,
        "plan": plan, "drivers": drivers, "fresh_current_plan": measured,
        "recorded_current_delay_s": recorded["taban_gecikme_simulasyon"],
        "delay_matches_recorded": measured["ort_gecikme_s"] == recorded["taban_gecikme_simulasyon"],
        "diagnostics": diagnostic,
        "seed1_completed_trip_accounting": {
            "scope": "Seed 1 completed trips only. Insertion delay is time outside the simulation, not observed stopped time. Not a field-travel-time estimate.",
            "scheduled_n": len(arrivals), "completed_n": len(trips),
            "mean_in_network_time_loss_s": float(trips.time_loss_s.mean()),
            "mean_insertion_delay_s": float(trips.depart_delay_s.mean()),
            "mean_time_loss_plus_insertion_s": float((trips.time_loss_s + trips.depart_delay_s).mean()),
            "p95_stopped_wait_s": float(trips.waiting_time_s.quantile(0.95)),
            "max_stopped_wait_s": float(trips.waiting_time_s.max()),
        },
    }
    dump(output / "baseline.json", baseline)
    print(json.dumps({"run_id": run, "baseline": measured, "arrival_diagnostics": diagnostic["arrival_diagnostics"],
                      "paired_waits": diagnostic["windows"]["full_video"]["paired_same_tracks"],
                      "matches_recorded": baseline["delay_matches_recorded"]}, indent=2))
    print(f"Saved: {output / 'baseline.json'}", flush=True)


if __name__ == "__main__":
    main()
