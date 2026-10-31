# Traffic Twin

**One fixed camera over an intersection, turned into a calibrated traffic simulation, with a Muse Spark agent that tests signal timings in it and backs every recommendation with evidence.**

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026). Every line of code in this repository was written during the hackathon; the commit history shows the order it was built in.

## Why

I lose a lot of time stuck at traffic lights. Retiming a signal is cheap compared with rebuilding a road, but the evidence needed to do it well (turning counts, queues, the current plan) usually takes a field survey. Most intersections already have a camera. The question behind this project: can one camera feed, plus Meta's models, produce a simulation that is accurate enough to test signal timings on, and an agent that only claims what it has measured?

## What it does

```
fixed-camera video
   │  SAM 3.1 (Meta Model API): "car" on every 2nd frame, 5,610 frames
   ▼
detections ──► camera calibration solved from the data (no hand-placed points)
   │
   ▼
tracks in ground coordinates ──► turning counts, queues, signal plan
   │                              (signal plan recovered from vehicle movements only)
   ▼
SUMO digital twin, calibrated to the video
   │
   ▼
Muse Spark agent (muse-spark-1.3, tool calling)
   tools: intersection_summary · video_evidence · webster_baseline · test_plan
   │
   ▼
recommendation + evidence ──► automatic verifier (re-simulates, checks every number,
                                                  re-tests on 10 seeds the agent never saw)
```

The web demo (`web/`) shows the four stages side by side: the video with SAM 3.1 tracks, the ground-truth checks, the agent's tool calls with its verified answer, and the current and recommended plans running next to each other in the twin.

## Every stage is checked against ground truth

The data is the FHWA NGSIM Lankershim Boulevard set (Los Angeles, 16 June 2005, camera 2, 08:28 to 08:47). NGSIM also publishes hand-verified trajectories for every vehicle. **They are used only to check results, never as an input.** The pipeline sees only the video, and the simulation is calibrated to the video.

| Stage | Result | Ground truth |
|---|---|---|
| Camera calibration (from data) | median position error 0.62 m on single-frame detections | NGSIM's own stated accuracy is about 0.6 m (X) and 1.2 m (Y) |
| Video/trajectory time offset | −0.3 s, found automatically | — |
| Tracking | 85% of ground-truth vehicles tracked; median error 0.81 m, p90 2.6 m | — |
| Track identity | median vehicle spends 99.7% of its visible time on one track; 79% of vehicles stay ≥90% on one track | — |
| Turning counts, 18.7 min | 1,120 vehicles | 1,149 (−2.5%) |
| Main movements | NB through 294 · NB right 101 · SB through 388 · SB left 159 | 305 · 98 · 392 · 156 (all within 4%) |
| Signal cycle | 101 s | 101 s |
| Green windows | SB left 84+35 s · SB through 99+49 s · NB through 12+31 s | 84+35 · 99+48 · 11+32 (within 1 s) |
| Twin queue profile error | 4.2 vehicles (RMSE across the cycle) | floor: the video itself is 2.7 off |

The signal plan was recovered without the signal logs. The cycle length comes from the autocorrelation of vehicles crossing the intersection, and each green window comes from where crossings cluster within the cycle. This is how the twin learned that the intersection runs a **lead-lag left**: southbound left turns go first, then southbound through, then both directions.

## The agent

`src/trafik/ajan.py`, using `muse-spark-1.3` through the Responses API with four developer-defined tools:

| Tool | What it returns |
|---|---|
| `intersection_summary` | demand per movement from video, current plan, its simulated delays, calibration quality, constraints |
| `video_evidence` | an approach's queue across the cycle, and its 3 worst moments as video timestamps (clickable in the demo) |
| `webster_baseline` | the textbook Webster plan and its simulated delays |
| `test_plan` | runs a plan in the twin over 3 random seeds: average, p95, per-approach and per-movement delay |

The instructions require that every number comes from a tool result, that per-approach delay is reported along with the average, and that differences inside the seed-to-seed spread are treated as noise. Constraints come from the real street: the cross-street green must be at least 30 s so that pedestrians can cross the ~30 m of Lankershim, and the cycle must be 60 to 150 s.

**Result of the recorded run (15 tool calls, 11 plans tested):**

| Plan | Avg delay per vehicle |
|---|---|
| Current plan, recovered from video (15 / 14 / 31 / 33 s) | 24.6 s |
| Webster textbook plan | 32.2 s (it has no slot for the lead-lag left, so southbound traffic suffers) |
| **Agent's recommendation (15 / 8 / 37 / 30 s, cycle 98 s)** | **22.3 s (−9%)** |

The recommendation shortens the southbound-only lead and gives the time to the shared Lankershim green. No approach gets worse: from west −2.4 s, from east −2.7 s, from south −5.3 s, from north 0.0 s.

**Verifier** (`dogrula` in `ajan.py`). The agent's answer is never trusted on its own word. The verifier checks that:
- the recommended plan was actually simulated by the agent ✓
- the reported baseline and recommended delays match a fresh re-simulation ✓
- pedestrian minimums and cycle bounds hold ✓
- per-approach delay changes, which is how the claim "no approach gets worse" was checked ✓
- the gain holds on **10 random seeds the agent never saw**: 24.7 s → 22.6 s, with non-overlapping ranges (23.9–25.3 vs 22.1–23.3) ✓

Different runs of the agent find different plans. An earlier run recommended 10 / 14 / 40 / 30 s for 22.3 s, but the far side of the intersection got worse with that plan. Every run is saved with its full tool trace in `data/ajan/`.

## What went wrong along the way (and what fixed it)

- **ICP calibration drifted.** NGSIM only tracks vehicles on Lankershim, so SAM's correct detections on the side street pulled point matching off. A grid search scored by a one-sided "coverage" measure fixed it: extra detections cannot raise the score, only covered ground-truth vehicles can.
- **Right turns came out as zero.** Right-turning vehicles cut the corner and never come within 40 ft of the intersection centre, which my first filter required.
- **Driver parameters did not matter. Structure did.** Tuning SUMO's driver model changed the error by under 2%. The big errors were the phase order (lead-lag left) and the lane counts (turn bays from NGSIM lane labels).
- **A plot exposed an alignment bug.** The queue profiles in the demo showed the twin shifted in time. The cause was the simulation's 120 s warm-up, which shifts the cycle. With the correct alignment, the twin's error is 4.2 vehicles, not the 3.9 I had reported earlier in the commit history.
- **SUMO cannot open paths with non-ASCII characters** (my project folder is under `Masaüstü`), so SUMO runs from inside its working folder with `SUMO_HOME` unset.
- **Long agent loops lost server-side state** (`previous_response_id` expired mid-run). The loop now keeps history on the client and replays encrypted reasoning.

## Limitations

- One intersection, one 18.7-minute morning period from 2005. The gains are simulated, not a field trial.
- The twin clears the north approach's queue later in the cycle than the real intersection does (cycle seconds 80 to 97). Its remaining error (4.2 vehicles) is above the 2.7 measurement floor.
- Pedestrians are treated as timing constraints only. They are a few pixels tall in this video and are not detected.
- The cross-street green is the weakest recovered window (25 s vs 39 s in ground truth), because the side street has few vehicles in view.
- Small movements (under 40 vehicles) have count errors of 10 to 25%.

## Run it

```bash
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
echo MODEL_API_KEY=your-key > .env
```

Rebuild everything from scratch (downloads about 500 MB; SAM 3.1 calls cost about $15 in Meta Model API credits at $2.50 per 1,000 images):

```bash
.venv/Scripts/python scripts/ngsim_indir.py lankershim-camera2-0830am-0845am.avi
.venv/Scripts/python scripts/yorunge_indir.py
PYTHONPATH=src .venv/Scripts/python scripts/tespit_ornekle.py --adim 2
.venv/Scripts/python scripts/kalibre.py
PYTHONPATH=src .venv/Scripts/python scripts/takip_degerlendir.py
PYTHONPATH=src .venv/Scripts/python scripts/akis_cikar.py
PYTHONPATH=src .venv/Scripts/python scripts/sinyal_cikar.py
PYTHONPATH=src .venv/Scripts/python scripts/sim_kalibre.py
PYTHONPATH=src .venv/Scripts/python scripts/ajan_calistir.py
PYTHONPATH=src .venv/Scripts/python scripts/video_katman.py
PYTHONPATH=src .venv/Scripts/python scripts/arayuz_verisi.py
```

Start the demo (it replays the recorded agent run, so it uses no API credits). Set `CANLI_AJAN=1` to allow live agent runs:

```bash
.venv/Scripts/python -m uvicorn web.app:app --port 8020
```

## Repository layout

```
src/trafik/
  sam.py          SAM 3.1 detection through Meta Model API
  takip.py        tracking in ground coordinates (Hungarian matching, track stitching)
  akis.py         entry/exit arm → NGSIM direction and movement codes
  olcum.py        queue and crossing measures, identical for video, NGSIM and SUMO
  sumo_ag.py      SUMO network, demand and lead-lag signal plan from video data
  simule.py       runs SUMO through TraCI
  degerlendir.py  plan constraints, multi-seed evaluation, Webster baseline
  ajan.py         Muse Spark agent, tools and verifier
scripts/          one script per pipeline step (see Run it)
web/              FastAPI server and single-page demo
```

## Credits

- Data: U.S. Department of Transportation, Federal Highway Administration, Next Generation Simulation (NGSIM) Program, Lankershim Boulevard. Licensed under Creative Commons Attribution 2.0. doi:10.21949/1504477
- Models: SAM 3.1 and Muse Spark 1.3 through Meta Model API.
- Simulation: Eclipse SUMO.
- Built with help from Claude (Anthropic) as a coding assistant.
