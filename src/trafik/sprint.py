"""Read-only measurement helpers for sprint baselines and retrospective diagnostics.

No calibration, detection or agent calls are performed here. All intervals are
half-open [start, end). Waiting intervals are clipped before aggregation so an
observation at the window boundary cannot silently lose the preceding interval.
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from trafik import olcum

ARMS = ("K", "G", "D", "B")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_config(config: dict) -> None:
    end = 0.0
    for start, stop in config["windows"].values():
        if start != end or stop <= start:
            raise ValueError("Windows must be ordered, contiguous and non-empty")
        end = stop
    if end != config["video_duration_s"]:
        raise ValueError("Windows must cover exactly the video duration")
    if config["independent_test"]["status"] != "not_available":
        raise ValueError("Existing data cannot be labelled an independent test")


def window_waits(points: pd.DataFrame, start: float, end: float) -> pd.DataFrame:
    """Observed stopped time within a window, including zero-wait approaches.

This is window-clipped exposure, not a complete journey wait. An interval is
represented by its left sample and capped at 1 s to avoid filling tracking gaps.
"""
    d = points.sort_values(["arac", "t"]).copy()
    next_t = d.groupby("arac").t.shift(-1)
    stop = np.minimum(next_t.fillna(d.t), d.t + 1.0)
    duration = (np.minimum(stop, end) - np.maximum(d.t, start)).clip(lower=0)
    on_approach = olcum.yaklasimda(d)
    visible = on_approach & (duration > 0)
    selected = d.loc[visible, "arac"].unique()
    stopped = on_approach & (d.hiz < olcum.DURGUN_MS)
    waits = (duration * stopped).groupby(d.arac).sum()
    info = d.groupby("arac").giris.first().to_frame()
    return info.assign(wait_s=waits).loc[selected]


def wait_summary(waits: pd.DataFrame) -> dict:
    result = {}
    for arm in ARMS:
        values = waits.loc[waits.giris == arm, "wait_s"]
        result[arm] = {
            "n": int(len(values)),
            "mean_s": round(float(values.mean()), 3) if len(values) else None,
            "median_s": round(float(values.median()), 3) if len(values) else None,
            "p95_s": round(float(values.quantile(0.95)), 3) if len(values) else None,
            "max_s": round(float(values.max()), 3) if len(values) else None,
        }
    return result


def queue_series(points: pd.DataFrame, start: float, end: float) -> pd.DataFrame:
    """Instantaneous queue sampled at common integer seconds; absent queues are 0.

    Missing source samples are NaN, not evidence of an empty street. Callers
    must report coverage alongside any error calculated on the common samples.
    """
    grid = np.arange(np.ceil(start), end)
    observed = points.loc[np.isclose(points.t, np.round(points.t), atol=1e-6), "t"].unique()
    q = points[olcum.yaklasimda(points) & (points.hiz < olcum.DURGUN_MS)].copy()
    # Existing sources sample at 0.1, 0.2 and 0.5 s and include integer seconds.
    q = q[np.isclose(q.t, np.round(q.t), atol=1e-6)]
    counts = q.groupby(["t", "giris"]).arac.nunique().unstack(fill_value=0)
    result = counts.reindex(index=grid, columns=ARMS, fill_value=0).fillna(0).astype(float)
    result.loc[~np.isin(grid, observed), :] = np.nan
    return result


def paired_waits(video: pd.DataFrame, twin: pd.DataFrame) -> dict:
    """Pair the very same track IDs; do not compare differently sized populations."""
    common = video.index.intersection(twin.index)
    result = {}
    for arm in ARMS:
        ids = common[video.loc[common, "giris"].to_numpy() == arm]
        delta = twin.loc[ids, "wait_s"] - video.loc[ids, "wait_s"]
        result[arm] = {
            "n": len(ids),
            "video_only_n": int(((video.giris == arm) & ~video.index.isin(common)).sum()),
            "twin_only_n": int(((twin.giris == arm) & ~twin.index.isin(common)).sum()),
            "mean_twin_minus_video_s": round(float(delta.mean()), 3) if len(ids) else None,
            "median_absolute_error_s": round(float(delta.abs().median()), 3) if len(ids) else None,
        }
    return result


def arrival_diagnostics(arrivals: pd.DataFrame, trips: pd.DataFrame, geometry: dict) -> dict:
    merged = arrivals.merge(trips, on="arac", how="left", validate="one_to_one")
    result = {}
    for arm in ARMS:
        d = merged[merged.giris == arm]
        delay = d.depart_delay_s.dropna()
        result[arm] = {
            "scheduled_n": len(d),
            "completed_n": int(d.depart_delay_s.notna().sum()),
            "not_completed_n": int(d.depart_delay_s.isna().sum()),
            "first_seen_stopped_fraction": round(float((d.hiz < 1.0).mean()), 3) if len(d) else None,
            "median_first_seen_distance_to_stop_m": round(float((d.d_m - geometry[arm]["durma_m"]).median()), 3) if len(d) else None,
            "mean_insertion_delay_s": round(float(delay.mean()), 3) if len(delay) else None,
            "p95_insertion_delay_s": round(float(delay.quantile(0.95)), 3) if len(delay) else None,
            "max_insertion_delay_s": round(float(delay.max()), 3) if len(delay) else None,
        }
    return result
