# trafik-ikizi

Turns fixed-camera intersection video into a calibrated traffic simulation, then lets an agent test signal-timing changes against it. Built for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026). All code in this repository was written during the hackathon.

Work in progress.

## Pipeline so far

1. `scripts/ngsim_indir.py`: pulls single files out of the NGSIM video archive with HTTP range requests, so the full 6.9 GB zip is never downloaded.
2. `scripts/yorunge_indir.py`: downloads the ground-truth NGSIM vehicle trajectories from the data.transportation.gov API.
3. `scripts/tespit_ornekle.py`: runs SAM 3.1 (Meta Model API) on video frames with the concept prompt `car`. Results are cached, so a frame is never paid for twice.
4. `scripts/kalibre.py`: estimates the time offset and the pixel → ground homography from the data alone, with no hand-picked points.
5. `src/trafik/takip.py`, `scripts/takip_degerlendir.py`: track vehicles across frames and score the tracks against ground truth.

## Setup

```bash
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
echo MODEL_API_KEY=... > .env
```

## Data

Video and trajectories come from the FHWA Next Generation Simulation (NGSIM) program, Lankershim Boulevard, Los Angeles, June 16, 2005, licensed under Creative Commons Attribution 2.0.

> U.S. Department of Transportation Federal Highway Administration. (2016). Next Generation Simulation (NGSIM) Vehicle Trajectories and Supporting Data. Provided by ITS DataHub through Data.transportation.gov. http://doi.org/10.21949/1504477

The data is not stored in this repository. The scripts above download it into `data/`.
