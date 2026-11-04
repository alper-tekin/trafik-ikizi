"""Shared completed-trip metrics and demand accounting for every controller.

timeLoss excludes time waiting to enter SUMO. Both are reported separately;
their sum is scheduling loss, never labelled as observed stopped waiting.
Incomplete or uninserted vehicles remain in counts, not in completed-trip means.
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

KOL_ADI = {"K": "from north (southbound)", "G": "from south (northbound)", "D": "from east", "B": "from west"}
HAREKET_ADI = {"s": "through", "l": "left", "r": "right"}
COLUMNS = ["arac", "kol", "hareket", "gecikme", "bekleme", "giris_gecikmesi", "toplam_kayip",
           "tamamlandi", "basladi", "kohort_biliniyor", "kayit_eksik"]


def talep_yolu(cfg: Path) -> Path:
    value = ET.parse(cfg).getroot().find("input/route-files").get("value")
    if "," in value:
        raise ValueError("Demand accounting currently supports a single route file")
    return cfg.parent / value


def trip_oku(yol: Path, talep: Path, isinma_s: float = 120.0) -> pd.DataFrame:
    """Filter by intended departure, not delayed actual departure.

    Explicit real-arrival schedules also catch entirely missing trip records.
    Flow demand is accounted from SUMO output with unfinished/undeparted enabled.
    An undeparted flow with unknown intended time blocks complete-comparison status.
    """
    routes = ET.parse(talep).getroot()
    expected = {v.get("id"): float(v.get("depart")) for v in routes.findall("vehicle")}
    has_flows = bool(routes.findall("flow"))
    if expected and has_flows:
        raise ValueError("Mixed explicit vehicles and flows are not supported")
    rows, seen = [], set()
    for t in ET.parse(yol).getroot().iter("tripinfo"):
        vehicle = t.get("id")
        if vehicle in seen:
            raise ValueError(f"Duplicate trip record: {vehicle}")
        seen.add(vehicle)
        depart = float(t.get("depart"))
        insertion = float(t.get("departDelay"))
        started = depart >= 0
        intended = expected.get(vehicle, depart - insertion if started else None)
        if expected and vehicle not in expected:
            raise ValueError(f"Unscheduled trip record: {vehicle}")
        if intended is not None and intended < isinma_s:
            continue
        complete = started and float(t.get("arrival")) >= 0
        flow = vehicle.split(".")[0]
        loss, wait = float(t.get("timeLoss")), float(t.get("waitingTime"))
        rows.append((vehicle, flow[0], flow[1], loss if complete else None,
                     wait if complete else None, insertion if started else None,
                     loss + insertion if complete else None, complete, started,
                     intended is not None, False))
    for vehicle, intended in expected.items():
        if vehicle not in seen and intended >= isinma_s:
            flow = vehicle.split(".")[0]
            rows.append((vehicle, flow[0], flow[1], None, None, None, None,
                         False, None, True, True))
    return pd.DataFrame(rows, columns=COLUMNS)


def ozetle(d: pd.DataFrame, tohumlar: tuple) -> dict:
    if not tohumlar or len(set(tohumlar)) != len(tohumlar):
        raise ValueError("Use a non-empty set of unique seeds")
    completed = d[d.tamamlandi == True]  # noqa: E712; nullable started/completed flags

    def number(value):
        return round(float(value), 1) if pd.notna(value) else None

    def by_arm(column):
        return {KOL_ADI[k]: number(v) for k, v in completed.groupby("kol")[column].mean().items()}

    counts = {}
    for seed in tohumlar:
        g = d[d.tohum == seed]
        counts[str(seed)] = {
            "planlanan": len(g), "tamamlanan": int(g.tamamlandi.sum()),
            "agda_tamamlanmayan": int(((g.basladi == True) & ~g.tamamlandi).sum()),
            "girememis": int((g.basladi == False).sum()),
            "kaydi_eksik": int(g.kayit_eksik.sum()),
            "kohortu_belirsiz": int((~g.kohort_biliniyor).sum()),
        }
    seed_means = completed.groupby("tohum").gecikme.mean()
    moves = completed.groupby(["kol", "hareket"]).gecikme.mean()
    return {
        "ort_gecikme_s": number(completed.gecikme.mean()),
        "ort_gecikme_tohum_araligi_s": [number(seed_means.min()), number(seed_means.max())],
        "p95_gecikme_s": number(completed.gecikme.quantile(0.95)),
        "arac_basi_durma_bekleme_s": number(completed.bekleme.mean()),
        "p95_bekleme_s": number(completed.bekleme.quantile(0.95)),
        "en_uzun_bekleme_s": number(completed.bekleme.max()),
        "ort_giris_gecikmesi_s": number(completed.giris_gecikmesi.mean()),
        "ort_toplam_kayip_s": number(completed.toplam_kayip.mean()),
        "tamamlanan_arac": int(len(completed) / len(tohumlar)),
        "tam_karsilastirma": all(c["planlanan"] > 0 and c["planlanan"] == c["tamamlanan"]
                                  and c["kohortu_belirsiz"] == 0 for c in counts.values()),
        "tohum_talep_durumu": counts,
        "kol_gecikme_s": by_arm("gecikme"), "kol_bekleme_s": by_arm("bekleme"),
        "kol_giris_gecikmesi_s": by_arm("giris_gecikmesi"), "kol_toplam_kayip_s": by_arm("toplam_kayip"),
        "hareket_gecikme_s": {f"{KOL_ADI[k]} {HAREKET_ADI[h]}": number(v) for (k, h), v in moves.items()},
        "olcum_notu": "Means and quantiles describe completed trips only. timeLoss excludes insertion delay; "
                       "toplam_kayip adds it. Neither insertion delay nor total loss is observed stopped time. "
                       "Do not rank a plan with tam_karsilastirma=false as a complete-demand improvement.",
    }
