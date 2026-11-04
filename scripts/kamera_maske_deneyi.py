"""Offline camera-2 exclusion experiment; never overwrites production artifacts.

Run from the repository root. Uses cached SAM boxes; no model API calls.
The configured off-road region was reviewed in video, not chosen by score.
"""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from trafik import olcum
from trafik.akis import BUYUK_FT, siniflandir
from trafik.kamera import dislama_uygula
from trafik.sprint import sha256, wait_summary, window_waits
from trafik.takip import takip_et


def reference_check(tracks, reference, h, offset):
    """Same 2-second sample grid for baseline/candidate; NGSIM is not held out."""
    inverse = np.linalg.inv(h)
    samples = reference.assign(tk=np.round(reference.t, 1)).groupby("tk")
    groups = dict(tuple(samples))
    visible, matched, distances = 0, 0, []
    for frame, tracked in tracks[tracks.kare % 20 == 0].groupby("kare"):
        truth = groups.get(round(frame / 10 + offset, 1))
        if truth is None:
            continue
        world = truth[["global_x", "global_y"]].to_numpy()
        pixel = cv2.perspectiveTransform(world.reshape(-1, 1, 2).astype(float), inverse).reshape(-1, 2)
        world = world[(pixel[:, 0] >= 0) & (pixel[:, 0] < 640) & (pixel[:, 1] >= 0) & (pixel[:, 1] < 480)]
        visible += len(world)
        if not len(world):
            continue
        cost = np.linalg.norm(world[:, None] - tracked[["x", "y"]].to_numpy()[None], axis=2)
        a, b = linear_sum_assignment(cost)
        good = cost[a, b][cost[a, b] <= 12]
        matched += len(good)
        distances.extend(good.tolist())
    return {"sample_step_s": 2, "visible_reference_positions": visible, "matched_positions": matched,
            "coverage": matched / visible if visible else None,
            "median_error_m": float(np.median(distances) * .3048) if distances else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", action="store_true", help="Also rerun the same tracker without image exclusions")
    args = parser.parse_args()
    config_path = ROOT / "config/kamera2_experiment.json"
    source = ROOT / "data/tespit/vehicle.jsonl"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frames, raw_frames, removed, total = [], [], 0, 0
    original_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in [
        source, ROOT / "data/izler_kamera2.parquet", ROOT / "data/akis_izler.parquet",
        ROOT / "data/gelisler.parquet", ROOT / "web/veri/ozet.json"]}
    for line in source.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        boxes = np.asarray(row["kutular"], dtype=float).reshape(-1, 5)
        if args.control:
            raw_frames.append((row["kare"], boxes[:, :4]))
        filtered = dislama_uygula(boxes, config["exclusions"])
        total += len(boxes)
        removed += len(boxes) - len(filtered)
        frames.append((row["kare"], filtered[:, :4]))
    frames.sort(key=lambda x: x[0])
    print(f"Removed {removed}/{total} detections; tracking {len(frames)} frames", flush=True)
    h = np.load(ROOT / "data/kalibrasyon_kamera2.npy")
    tracks = takip_et(frames, h)
    flow = siniflandir(tracks)
    sizes = tracks.groupby("iz").boy.median()
    flow = flow.assign(boy_ft=flow.iz.map(sizes).round(1), buyuk=flow.iz.map(sizes > BUYUK_FT).fillna(False))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "data/sprint" / ("camera-mask-" + stamp)
    output.mkdir(parents=True, exist_ok=False)
    tracks.to_parquet(output / "tracks.parquet", index=False)
    flow.to_parquet(output / "flow.parquet", index=False)
    baseline_tracks = pd.read_parquet(ROOT / "data/izler_kamera2.parquet")
    baseline_flow = pd.read_parquet(ROOT / "data/akis_izler.parquet")
    variants = [("baseline", baseline_tracks, baseline_flow), ("candidate", tracks, flow)]
    if args.control:
        raw_frames.sort(key=lambda x: x[0])
        control_tracks = takip_et(raw_frames, h)
        control_flow = siniflandir(control_tracks)
        control_sizes = control_tracks.groupby("iz").boy.median()
        control_flow = control_flow.assign(boy_ft=control_flow.iz.map(control_sizes).round(1),
                                          buyuk=control_flow.iz.map(control_sizes > BUYUK_FT).fillna(False))
        control_tracks.to_parquet(output / "control_tracks.parquet", index=False)
        control_flow.to_parquet(output / "control_flow.parquet", index=False)
        variants.insert(1, ("unfiltered_control", control_tracks, control_flow))
    reference = pd.read_parquet(ROOT / "data/ngsim/kavsak2.parquet", columns=["t", "global_x", "global_y"])
    offset = json.loads((ROOT / "data/kalibrasyon_kamera2.json").read_text())["ofset_s"]
    results = {}
    for name, t, f in variants:
        points = olcum.noktalar_izden(t, f)
        waits = window_waits(points, 0, 1122)
        results[name] = {
            "tracks_n": int(t.iz.nunique()), "flow_n": len(f),
            "flow_by_arm": {k: int(v) for k, v in f.groupby("giris").size().items()},
            "observed_waits_by_arm": wait_summary(waits),
            "reference_check": reference_check(t, reference, h, offset),
            "long_wait_tracks": [{"track_id": int(i), "arm": r.giris, "wait_s": round(r.wait_s, 2)}
                                 for i, r in waits.nlargest(12, "wait_s").iterrows()],
        }
    result = {"experiment": output.name, "config": config, "config_sha256": sha256(config_path),
              "tracker_sha256": sha256(ROOT / "src/trafik/takip.py"),
              "source_hashes": original_hashes, "removed_detections": removed, "total_detections": total,
              "results": results, "production_activated": False,
              "limitations": "Retrospective camera-specific exclusion; reference sampling is every 2 s, not the full tracking benchmark. Candidate IDs differ; do not pair baseline/candidate by numeric ID."}
    assert all(sha256(ROOT / p) == value for p, value in original_hashes.items())
    (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(output / "result.json")


if __name__ == "__main__":
    main()
