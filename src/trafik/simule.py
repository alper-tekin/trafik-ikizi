"""SUMO simülasyonunu çalıştırır ve araç noktalarını olcum.py'nin biçiminde döndürür."""

import os
from pathlib import Path

import numpy as np
import pandas as pd

from trafik.sumo_ag import _ortam

GIRIS_YON = {"G": 2, "K": 4, "B": 1, "D": 3}
HAREKET = {"s": 1, "l": 2, "r": 3}


def calistir(cfg: Path, isinma_s: float = 120.0, tohum: int = 1) -> pd.DataFrame:
    import sumo
    import traci

    eski = os.getcwd()
    os.chdir(cfg.parent)  # SUMO ASCII dışı tam yolları açamıyor
    env = _ortam()
    os.environ.pop("SUMO_HOME", None)
    try:
        traci.start([str(Path(sumo.SUMO_HOME) / "bin" / "sumo"), "-c", cfg.name, "--seed", str(tohum)])
        # netconvert ağı pozitif koordinatlara kaydırır; merkez kavşağın konumu çıkarılır.
        mx, my = traci.junction.getPosition("M")
        kayit = []
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            t = traci.simulation.getTime()
            if t < isinma_s:
                continue
            for v in traci.vehicle.getIDList():
                x, y = traci.vehicle.getPosition(v)
                kayit.append((t - isinma_s, v, x - mx, y - my, traci.vehicle.getSpeed(v)))
        traci.close()
    finally:
        os.chdir(eski)
        os.environ.clear()
        os.environ.update(env)

    d = pd.DataFrame(kayit, columns=["t", "arac", "w", "u", "hiz"])  # SUMO: x doğu, y kuzey
    akis = d.arac.str.split(".").str[0]
    return d.assign(giris=akis.str[0], yon=akis.str[0].map(GIRIS_YON), hareket=akis.str[1].map(HAREKET))[
        ["t", "arac", "giris", "yon", "hareket", "u", "w", "hiz"]]
