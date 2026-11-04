"""Explicit, reviewed image exclusions; no duration-based vehicle filtering."""

import cv2
import numpy as np


def dislama_uygula(kutular: np.ndarray, bolgeler: list[dict]) -> np.ndarray:
    if len(kutular) == 0:
        return kutular.copy()
    centres = (kutular[:, :2] + kutular[:, 2:4]) / 2
    keep = np.ones(len(kutular), dtype=bool)
    for zone in bolgeler:
        polygon = np.asarray(zone["polygon_px"], dtype=np.float32)
        if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3:
            raise ValueError("An exclusion requires at least three pixel-coordinate vertices")
        keep &= np.array([cv2.pointPolygonTest(polygon, (float(x), float(y)), False) < 0 for x, y in centres])
    return kutular[keep].copy()
