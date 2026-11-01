# Traffic Twin

**One fixed camera over an intersection, turned into a calibrated traffic simulation, with a Muse Spark agent that tests signal timings in it and backs every recommendation with evidence.**

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026). Every line of code in this repository was written during the hackathon; the commit history shows the order it was built in.

## Why

I lose a lot of time stuck at traffic lights. Retiming a signal is cheap compared with rebuilding a road, but the evidence needed to do it well (turning counts, queues, the current plan) usually takes a field survey. Most intersections already have a camera. The question behind this project: can one camera feed, plus Meta's models, produce a simulation that is accurate enough to test signal timings on, and an agent that only claims what it has measured?

## What it does

```
fixed-camera video
   │  SAM 3.1 (Meta Model API): "vehicle" on every 2nd frame, 5,610 frames
   ▼
detections ──► camera calibration solved from the data (no hand-placed points)
   │
   ▼
tracks in ground coordinates ──► turning counts, queues, signal plan, road geometry
   │                              (signal plan recovered from vehicle movements only;
   │                               arm angles, lanes and stop lines measured from the tracks)
   ▼
SUMO digital twin built on that geometry; it replays the video's vehicles at their real arrival times
   │
   ▼
Muse Spark agent (muse-spark-1.3, tool calling)
   tools: intersection_summary · video_evidence · webster_baseline · test_plan
   │
   ▼
recommendation + evidence ──► automatic verifier (re-simulates, checks every number,
                                                  re-tests on 10 seeds the agent never saw)
```

The web demo (`web/`) shows the four stages side by side: the video with SAM 3.1 tracks, the ground-truth checks, the agent's tool calls with its verified answer, and the current and recommended plans running next to each other in the twin. Every panel is a clean top-down + schematic of the simulation network, turned to match the video (the calibration tells which way north and east run on screen, so Lankershim runs left to right as in the video). The network is built from the road paint: in the empty-road image (per-pixel median of the video) every lane line, road edge, yellow line and stop line was located and converted to metres through the camera calibration (`scripts/geometri_fotodan.py`). The measured arms are within 6° of square, so they are drawn and simulated at right angles; lane counts, widths, offsets and stop lines are the measured ones. Each lane's allowed turns come from the video: for every lane, the cars waiting at the stop line were counted by where they went, and checked against the painted arrows.

## Every stage is checked against ground truth

The data is the FHWA NGSIM Lankershim Boulevard set (Los Angeles, 16 June 2005, camera 2, 08:28 to 08:47). NGSIM also publishes hand-verified trajectories for every vehicle. **They are used only to check results, never as an input.** The pipeline sees only the video, and the simulation is calibrated to the video.

| Stage | Result | Ground truth |
|---|---|---|
| Camera calibration (from data) | median position error 0.62 m on single-frame detections | NGSIM's own stated accuracy is about 0.6 m (X) and 1.2 m (Y) |
| Video/trajectory time offset | −0.3 s, found automatically | — |
| Tracking | 90% of ground-truth vehicle positions tracked (94% for buses and trucks); median error 0.84 m, p90 2.6 m | — |
| Track identity | median vehicle spends its whole visible time on one track; 81% of vehicles stay ≥90% on one track | — |
| Buses and trucks | 47 tracks longer than 20 ft on the ground, simulated as 10 m vehicles | 47 large vehicles in NGSIM |
| Turning counts, 18.7 min | 1,186 vehicles | 1,149 (+3.2%) |
| Main movements | NB through 310 · NB right 105 · SB through 414 · SB left 164 | 305 · 98 · 392 · 156 (all within 7.1%) |
| Signal cycle | 101 s | 101 s |
| Green windows | SB left 84+35 s · SB through 99+48 s · NB through 11+32 s | 84+35 · 99+48 · 11+32 (exact) |
| Road geometry | measured from the road paint: arms within 6° of square (modelled as +); 5/5/3/3 approach lanes, 2.5 to 3.6 m wide; stop lines 17 to 22 m from the centre | lanes and stop lines overlay the paint in the video |
| Lane turns | counted per lane from the video, e.g. east arm 42 right / 9 through / 4 left by lane | painted arrows on the east arm say right / through / left |
| Twin queue profile error | 1.7 vehicles against the video it replays; 3.6 against ground truth (RMSE across the cycle) | floor: the video itself is 2.4 off ground truth |
| Vehicle by vehicle | the same 1,186 vehicles wait 12.9 s in the twin (current plan) and 14.8 s in the video; median difference per vehicle 1.2 s | — |

The signal plan was recovered without the signal logs. The cycle length comes from the autocorrelation of vehicles crossing the intersection, and each green window comes from where crossings cluster within the cycle. This is how the twin learned that the intersection runs a **lead-lag left**: southbound left turns go first, then southbound through, then both directions.

## The agent

`src/trafik/ajan.py`, using `muse-spark-1.3` through the Responses API with four developer-defined tools:

| Tool | What it returns |
|---|---|
| `intersection_summary` | demand per movement from video, current plan, its simulated delays, calibration quality, constraints |
| `video_evidence` | an approach's queue across the cycle, and its 3 worst moments as video timestamps (clickable in the demo) |
| `webster_baseline` | the textbook Webster plan and its simulated delays |
| `test_plan` | runs a plan in the twin on the video's own traffic, over 3 seeds of driver behaviour: average, p95, per-approach and per-movement delay |

The instructions require that every number comes from a tool result, that per-approach delay is reported along with the average, and that differences inside the seed-to-seed spread are treated as noise. Constraints come from the real street: the cross-street green must be at least 30 s so that pedestrians can cross the ~30 m of Lankershim, and the cycle must be 60 to 150 s.

**Result of the recorded run (14 tool calls, 11 plans tested), on the vehicles from the video:**

| Plan (southbound-only left / southbound lead / shared / cross street) | Avg delay per vehicle |
|---|---|
| Current plan, recovered from video (15 / 14 / 31 / 33 s, cycle 101 s) | 20.4 s |
| Webster textbook plan (14 / 0 / 27 / 30 s, cycle 79 s) | 22.8 s |
| **Agent's recommendation (8 / 7 / 48 / 30 s, cycle 101 s)** | **17.4 s (−15%)** |

The measured geometry has two left-turn bays for southbound traffic, so the southbound left clears faster than a single bay would allow. The agent kept the 101 s cycle and the lead-lag order, halved both lead phases (protected left 15 → 8 s, southbound lead 14 → 7 s) and moved that time into the shared Lankershim green (31 → 48 s). Lankershim gains: from south −4.3 s, from north −3.1 s. The cross street pays a little: from west +1.4 s, from east +0.4 s; the agent called these "essentially unchanged", and the verifier flags the west arm. On the real traffic the textbook Webster plan is worse than the current plan (22.8 s against 20.4 s): its short cycle does not clear the morning's southbound queue.

**Average wait per vehicle, by approach** (time stopped, whole simulation, the video's vehicles, 10 seeds of driver behaviour):

| Approach | Current plan | Recommended | Change |
|---|---|---|---|
| From west | 6.1 s | 7.3 s | +1.2 s |
| From east | 8.2 s | 8.7 s | +0.5 s |
| From south | 11.0 s | 7.4 s | −3.6 s |
| From north | 14.1 s | 11.8 s | −2.3 s |
| All vehicles | 12.2 s | 9.7 s | −2.5 s |

Vehicle by vehicle (the same 1,186 vehicles, wait within the 75 m the camera sees): 14.8 s in the video, 12.9 s in the twin under the current plan, 9.9 s under the agent's plan. Under the agent's plan 26% of the vehicles wait at least 1 s less and 10% at least 1 s more. In the demo, hovering over a car shows its own three numbers.

The same wait measure, restricted to the 75 m the camera sees, was also computed from the video, from ground truth and from the twin. From north the three agree (15.2 / 15.3 / 15.2 s). On the cross street the twin reads low: from east 9.6 s against 18.5 s in the video and 16.3 s in ground truth, from west 7.0 s against 17.3 s in the video. From south the video reads low, because the queue runs off the bottom of the frame. From west the ground truth reads low, because NGSIM starts tracking side-street cars only near the intersection.

**Verifier** (`dogrula` in `ajan.py`). The agent's answer is never trusted on its own word. The verifier checks that:
- the recommended plan was actually simulated by the agent ✓
- the reported baseline and recommended delays match a fresh re-simulation ✓
- pedestrian minimums and cycle bounds hold ✓
- per-approach delay changes: Lankershim gains, the west arm loses 1.4 s and is flagged
- the gain holds on traffic the agent never saw, **10 seeds of random arrivals** drawn from the turning counts: 26.0 s → 21.9 s (−16%), with non-overlapping ranges (25.5–26.4 vs 21.4–22.4) ✓

Different runs of the agent find different plans. Every run is saved with its full tool trace in `data/ajan/`. On the earlier, idealised square network (before the road geometry was measured) the agent's best plan gained only 9%, because that network had a single southbound left bay. The geometry of the twin changes the answer, which is why it is measured from the video rather than assumed. The twin has since gained lane turns counted from the video and buses and trucks; the agent is re-run whenever the twin changes, and the verifier always checks the run against the twin as it is now.

## An adaptive signal: serve whoever has waited longest

The camera already knows how long every vehicle has been waiting (the counters on the cars in the demo), so the signal does not have to run a fixed plan. `src/trafik/uyarlamali.py` drives the twin's signal every half second through TraCI, using the same three phases as the fixed plan (southbound through + left, Lankershim both ways, cross street):

- a green stays on while its own approaches still have vehicles within 40 m of the stop line, up to 60 s (minimum 7 s, cross street 10 s); every change costs 3 s yellow + 1 s all-red;
- when that demand ends, the next green goes to the phase chosen by the rule: **longest wait first** (the single vehicle that has waited longest) or **weighted** (the sum of the waiting times, so long waits and long queues both count);
- pedestrian-button assumption: at least once every 120 s the cross street gets 30 s (pedestrians cross Lankershim) and the shared Lankershim green gets 18 s.

Same 1,186 vehicles from the video, 10 seeds of driver behaviour, and 10 random mornings as a check:

| | Avg delay, video's traffic | Avg wait | Avg delay, random traffic |
|---|---|---|---|
| Current plan | 20.4 s | 12.2 s | 26.0 s |
| Agent's fixed plan | **17.6 s** | **9.7 s** | **21.9 s** |
| Adaptive, longest wait first | 18.1 s | 10.0 s | 22.2 s |
| Adaptive, weighted | 20.1 s | 10.6 s | **21.9 s** |

With no tuning at all, longest-wait-first gets within half a second of the agent's tuned plan, and it is the best of the four for Lankershim from the north (wait 14.1 → 9.4 s). It pays on the cross street (from west 6.1 → 16.3 s), mostly because of the pedestrian rule: every two minutes the cross street holds 30 s of green whether or not cars are there. The first version switched as soon as another phase scored higher and lost a quarter of the time to yellow and all-red; keeping the green while its queue is still discharging fixed that. The 40 m demand distance was checked at 20, 30, 40 and 60 m (longest wait first: 17.8 to 18.2 s, weighted: 20.2 to 20.6 s). In the demo the right-hand twin can switch between the agent's plan and both adaptive rules.

## What went wrong along the way (and what fixed it)

- **ICP calibration drifted.** NGSIM only tracks vehicles on Lankershim, so SAM's correct detections on the side street pulled point matching off. A grid search scored by a one-sided "coverage" measure fixed it: extra detections cannot raise the score, only covered ground-truth vehicles can.
- **Right turns came out as zero.** Right-turning vehicles cut the corner and never come within 40 ft of the intersection centre, which my first filter required.
- **Driver parameters did not matter. Structure did.** Tuning SUMO's driver model changed the error by under 2%. The big errors were the phase order (lead-lag left) and the lane layout.
- **The first twin was a square.** It had four perpendicular arms, so the animation did not match the camera view. Measuring arm directions, lanes and stop lines from the tracked cars fixed the lane counts (the cross street has 3 approach lanes, not 2) but still did not land on the paint: it assumed one straight axis per arm with evenly spaced lanes, and it read the west arm as skewed by 18°. Laid over the video, the lanes missed the painted lines. The geometry is now read from the paint itself, which puts the west arm at −84° (almost square after all) and gives each arm its real lane widths. One lane was easy to miss: on the east arm the outgoing side has a curved right-turn slip lane next to its two lanes. Without it, left turns and right turns squeezed into two lanes and the cross street jammed (60 s waits against 11 s in the video).
- **A plot exposed an alignment bug.** The queue profiles in the demo showed the twin shifted in time. The cause was the simulation's 120 s warm-up, which shifts the cycle. With the correct alignment, the error was 4.2 vehicles, not the 3.9 I had reported earlier in the commit history. On the current twin it is 4.5.
- **Buses and trucks were half missing.** The first detection pass asked SAM 3.1 for "car", and it caught only half of the large vehicles. On 20 test frames "car" found 10 of 26 buses and trucks, "bus" 7, "truck" 13 (and it also boxed ordinary cars), "vehicle" 25. Re-running every frame with "vehicle" raised large-vehicle coverage from 49% to 94% and overall coverage from 85% to 90%. Large vehicles are told apart by the length of their box on the ground and simulated as 10 m vehicles.
- **Average flows hid how well the twin could fit.** The twin first ran random arrivals drawn from the turning counts, so its queues could only match the video on average (error 5.0 vehicles against the video). Replaying the video's own vehicles, each at the second, place, lane and speed it was first seen, brought the error to 1.7, and made it possible to compare plans vehicle by vehicle. Random arrivals are kept as an option in the demo and as the verifier's independent check.
- **SAM masks needed a decoder.** The masks come back range-coded, and installing Meta's parser package was not possible in this environment, so `sam_maske.py` ports its one_bit decoder to Python. Faint lane paint on bright concrete was missed by a single prompt; contrast-enhanced, upscaled tiles recover more of it.
- **SUMO cannot open paths with non-ASCII characters** (my project folder is under `Masaüstü`), so SUMO runs from inside its working folder with `SUMO_HOME` unset.
- **Long agent loops lost server-side state** (`previous_response_id` expired mid-run). The loop now keeps history on the client and replays encrypted reasoning.

## Limitations

- One intersection, one 18.7-minute morning period from 2005. The gains are simulated, not a field trial.
- On the cross street the twin underestimates waits (7 to 10 s against about 18 s in the video), so the plan's small cross-street cost may be larger in reality.
- Lane boundaries were read from brightness peaks across each arm and matched to lines by hand, at two cross-sections per arm. Lanes are modelled as straight and parallel, and arms as exactly square (they are within 6°). The curved slip lane on the east arm is modelled as a straight lane. Lane turns on the cross street rest on few cars (57 east, 71 west).
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
  uyarlamali.py   adaptive signal: longest-wait-first and weighted rules, run through TraCI
  ajan.py         Muse Spark agent, tools and verifier
scripts/          one script per pipeline step (see Run it)
web/              FastAPI server and single-page demo
```

## Credits

- Data: U.S. Department of Transportation, Federal Highway Administration, Next Generation Simulation (NGSIM) Program, Lankershim Boulevard. Licensed under Creative Commons Attribution 2.0. doi:10.21949/1504477
- Models: SAM 3.1 and Muse Spark 1.3 through Meta Model API.
- Simulation: Eclipse SUMO.
- Built with help from Claude (Anthropic) as a coding assistant.
