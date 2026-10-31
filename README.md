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
tracks in ground coordinates ──► turning counts, queues, signal plan, road geometry
   │                              (signal plan recovered from vehicle movements only;
   │                               arm angles, lanes and stop lines measured from the tracks)
   ▼
SUMO digital twin built on that geometry, calibrated to the video
   │
   ▼
Muse Spark agent (muse-spark-1.3, tool calling)
   tools: intersection_summary · video_evidence · webster_baseline · test_plan
   │
   ▼
recommendation + evidence ──► automatic verifier (re-simulates, checks every number,
                                                  re-tests on 10 seeds the agent never saw)
```

The web demo (`web/`) shows the four stages side by side: the video with SAM 3.1 tracks, the ground-truth checks, the agent's tool calls with its verified answer, and the current and recommended plans running next to each other in the twin. Every panel is drawn from the camera's own angle, projected through the camera calibration, so a different video lines up the same way through its own calibration. The road itself is our own vector drawing of the real geometry: SAM 3.1 segments the video with the cars removed (per-pixel median over 240 frames) into road, sidewalks and crosswalks (plus grass, trees and buildings, used only to keep road gaps from leaking into them), and the smoothed road outline becomes a clean dark schematic. Lane paint is not traced from the photo: dashed dividers, the double yellow median and stop lines are ruled on the ground from each arm's measured direction, lane positions and stop-line distance (from where the tracked cars actually drove and stopped), then projected into the camera view, so lane counts and asymmetry are real and the lines are straight.

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
| Road geometry | arms at 4°, 177°, 90° and −72° (the west arm is skewed ~18°); 5/5/3/3 approach lanes; stop lines 16 to 20 m from the centre | stop lines line up with the painted ones in the video |
| Twin queue profile error | 4.3 vehicles (RMSE across the cycle) | floor: the video itself is 2.7 off |

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

**Result of the recorded run (14 tool calls, 9 plans tested):**

| Plan (southbound-only left / southbound lead / shared / cross street) | Avg delay per vehicle |
|---|---|
| Current plan, recovered from video (15 / 14 / 31 / 33 s, cycle 101 s) | 24.1 s |
| Webster textbook plan (15 / 0 / 26 / 30 s) | 21.7 s |
| **Agent's recommendation (10 / 0 / 31 / 30 s, cycle 79 s)** | **19.3 s (−20%)** |

The measured geometry has two left-turn bays for southbound traffic, so the southbound left clears faster than a single bay would allow. The agent dropped the southbound-through lead phase, shortened the protected left, and shortened the cycle from 101 s to 79 s. No approach gets worse: from west −10.0 s, from east −3.4 s, from south −10.0 s, from north −0.6 s. The textbook Webster plan already beats the current plan here; the agent's search beats Webster by another 2.4 s.

**Average wait per car, by approach** (time stopped, whole simulation, 10 random seeds the agent never saw):

| Approach | Current plan | Recommended | Change |
|---|---|---|---|
| From west | 22.6 s | 13.3 s | −9.3 s |
| From east | 13.4 s | 10.1 s | −3.3 s |
| From south | 17.8 s | 9.8 s | −8.0 s |
| From north | 13.5 s | 12.4 s | −1.1 s |
| All cars | 15.7 s | 11.4 s | −4.3 s |

The same wait measure, restricted to the 75 m the camera sees, was also computed from the video, from ground truth and from the twin. From north the three agree within 1.5 s (15.0 / 15.3 / 13.8 s) and from east within 3.1 s (17.9 / 16.3 / 14.8 s). From south the video reads low, because the queue runs off the bottom of the frame. From west the ground truth reads low, because NGSIM starts tracking side-street cars only near the intersection.

**Verifier** (`dogrula` in `ajan.py`). The agent's answer is never trusted on its own word. The verifier checks that:
- the recommended plan was actually simulated by the agent ✓
- the reported baseline and recommended delays match a fresh re-simulation ✓
- pedestrian minimums and cycle bounds hold ✓
- per-approach delay changes, which is how the claim "no approach gets worse" was checked ✓
- the gain holds on **10 random seeds the agent never saw**: 24.1 s → 19.4 s, with non-overlapping ranges (23.6–24.5 vs 19.1–19.8) ✓

Different runs of the agent find different plans. Every run is saved with its full tool trace in `data/ajan/`. On the earlier, idealised square network (before the road geometry was measured) the agent's best plan gained only 9%, because that network had a single southbound left bay. The geometry of the twin changes the answer, which is why it is measured from the video rather than assumed.

## What went wrong along the way (and what fixed it)

- **ICP calibration drifted.** NGSIM only tracks vehicles on Lankershim, so SAM's correct detections on the side street pulled point matching off. A grid search scored by a one-sided "coverage" measure fixed it: extra detections cannot raise the score, only covered ground-truth vehicles can.
- **Right turns came out as zero.** Right-turning vehicles cut the corner and never come within 40 ft of the intersection centre, which my first filter required.
- **Driver parameters did not matter. Structure did.** Tuning SUMO's driver model changed the error by under 2%. The big errors were the phase order (lead-lag left) and the lane layout.
- **The first twin was a square.** It had four perpendicular arms, so the animation did not match the camera view: the west arm is actually skewed by about 18°, and the stop lines sit at different distances. Arm directions, lane counts and widths, and stop lines are now measured from the tracked cars, and the network is rebuilt from those measurements. The cross street turned out to have 3 approach lanes, not 2.
- **A plot exposed an alignment bug.** The queue profiles in the demo showed the twin shifted in time. The cause was the simulation's 120 s warm-up, which shifts the cycle. With the correct alignment, the error was 4.2 vehicles, not the 3.9 I had reported earlier in the commit history. On the measured geometry it is 4.3.
- **SAM masks needed a decoder.** The masks come back range-coded, and installing Meta's parser package was not possible in this environment, so `sam_maske.py` ports its one_bit decoder to Python. Faint lane paint on bright concrete was missed by a single prompt; contrast-enhanced, upscaled tiles recover more of it.
- **SUMO cannot open paths with non-ASCII characters** (my project folder is under `Masaüstü`), so SUMO runs from inside its working folder with `SUMO_HOME` unset.
- **Long agent loops lost server-side state** (`previous_response_id` expired mid-run). The loop now keeps history on the client and replays encrypted reasoning.

## Limitations

- One intersection, one 18.7-minute morning period from 2005. The gains are simulated, not a field trial.
- The twin's queue-profile error (4.3 vehicles) is still above the 2.7 measurement floor.
- Toward the edges of the frame the camera calibration bends straight lanes slightly, so lanes measured from tracks fan out by a few degrees on the south and east arms. The road and lane lines in the demo come from SAM 3.1 segments of the image itself, which do not have this error; only the faint-paint arms use track-measured dividers.
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
PYTHONPATH=src .venv/Scripts/python scripts/geometri_olc.py
PYTHONPATH=src .venv/Scripts/python scripts/sim_kalibre.py
PYTHONPATH=src .venv/Scripts/python scripts/ajan_calistir.py
PYTHONPATH=src .venv/Scripts/python scripts/video_katman.py
.venv/Scripts/python scripts/arka_plan.py
PYTHONPATH=src .venv/Scripts/python scripts/sahne_katmanlari.py
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
  sam_maske.py    decoder for SAM 3.1 one_bit masks (Python port of Meta's mask codec)
  takip.py        tracking in ground coordinates (Hungarian matching, track stitching)
  akis.py         entry/exit arm → NGSIM direction and movement codes
  geometri.py     arm directions, lanes and stop lines measured from tracks
  olcum.py        queue and crossing measures, identical for video, NGSIM and SUMO
  sumo_ag.py      SUMO network on the measured geometry, demand and signal plan from video data
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
