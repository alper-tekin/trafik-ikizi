# Traffic Twin

One fixed camera over a real intersection becomes a measured traffic simulation. SAM 3.1 detects vehicles, a tracker reconstructs their paths, and a Muse Spark agent tests signal plans in SUMO with evidence attached to its recommendation.

Built for the Meta Global AI Developer Hackathon, **Build for Your World**. Code was developed during the event window; the commit history records its evolution. I lose time at traffic lights and wanted to test whether an existing camera can supply the measurements needed to retime one.

## Current pipeline

```text
fixed-camera video → SAM 3.1 "vehicle" detections
    + NGSIM positions → camera homography and time alignment
    → gated vehicle tracking → turns, queues, signal windows, arrivals
    + measured road paint → SUMO network
    → calibrated twin replaying the video's vehicles
    → Muse Spark: evidence, Webster baseline, tested signal plans
    → local verifier + insertion-aware comparison
```

**NGSIM is an input as well as a reference.** Its positions informed the camera homography/time offset and local coordinate axes; its classes/lengths informed large-vehicle assumptions. Counts, arrivals and signal timings are then extracted from video, and SUMO driver parameters are fitted to video queues. These checks are not a fully independent evaluation. The road layout includes manually matched paint measurements in `scripts/geometri_fotodan.py`; arms are modelled as a top-down + schematic, turned to match the video.

## Current measured results

Data: FHWA NGSIM Lankershim Boulevard, Los Angeles, 16 June 2005, camera 2, about 18.7 minutes. SAM detections use 5,610 sampled frames at 5 fps. Video and generated simulation artifacts are rebuilt together.

| Measurement | Current result |
|---|---:|
| Classified video vehicles | 1,191 vs 1,149 NGSIM reference (+3.7%) |
| Reference positions tracked | 91.18% |
| Median matched position error | 0.845 m |
| p90 matched position error | 2.609 m |
| Vehicles spending at least 90% of visible time on one track | 83.45% |
| Large-vehicle tracks (box length >20 ft) | 48, simulated as 10 m vehicles |
| Recovered signal cycle | 101 s |
| Queue-profile RMSE vs video, main approaches | 1.77 vehicles |
| Queue-profile RMSE vs NGSIM reference, main approaches | 3.21 vehicles |
| Driver parameters fitted to video | tau 0.8, acceleration 1.5 m/s² |

The recovered current plan is **14 / 14 / 32 / 33 s**, cycle 101 s. Phase order: southbound protected left, southbound through+left lead, shared Lankershim green, cross street. Yellow/all-red clearance adds 8 s per cycle. Cross-street green is at least 30 s, shared green at least 18 s, cycle 60–150 s.

## Signal comparison — identical arrivals, driver seeds 1, 2, 3

The new fixed plan selected in the model response is **14 / 14 / 35 / 30 s**. It moves 3 s from the cross street to shared Lankershim green while retaining the 101 s cycle. All **1,191 vehicles complete in every compared run**.

| Policy | In-network loss (s) | Before-entry delay (s) | Combined loss (s) | p95 stopped wait (s) |
|---|---:|---:|---:|---:|
| Current plan | 19.4 | 2.6 | 22.0 | 55.0 |
| Agent-selected fixed plan | 17.9 | 1.8 | 19.7 | 52.0 |
| Adaptive: longest wait first | 17.8 | 5.2 | 23.0 | 47.7 |
| Adaptive: weighted wait | 20.1 | 3.4 | 23.5 | 50.0 |

The fixed plan reduces in-network delay **19.4 → 17.9 s** and combined loss **22.0 → 19.7 s** on this simulation. Combined loss adds SUMO `departDelay` to `timeLoss`; it is not the same as physical stopped time. Counting only in-network delay can hide waiting outside the network. Incomplete/uninserted/missing vehicles are reported and block complete-demand comparison status.

Mean stopped time per vehicle, whole simulation, same three seeds:

| Approach | Current (s) | Fixed recommendation (s) |
|---|---:|---:|
| from west | 5.4 | 6.1 |
| from east | 7.9 | 8.2 |
| from south (northbound) | 11.5 | 10.8 |
| from north (southbound) | 13.3 | 11.2 |

Approach tradeoffs remain visible: the verifier reports west/east delay changes of +0.9/+0.5 s and gains on Lankershim. The adaptive rules are alternatives under investigation, not established winners.

## The agent and its verifier

Muse Spark 1.3 uses `intersection_summary`, `video_evidence`, `webster_baseline` and `test_plan`. Plans must be simulated; both in-network and combined losses and per-approach effects must be reported. This search used at most 12 tool steps. The chosen plan was re-simulated and checked against the recorded numbers, timing constraints and completion counts.

The model's final JSON hit its output-token limit. The complete plan, delay fields and summary were recovered locally, checked against the completed tool results, and evidence/caveats were explicitly supplemented by the local verifier. The 12-step trace was reconstructed from completed cached simulator outputs after the first failure; no additional search/tool steps were run. The original failed attempt did not persist all token usage, so **total API cost is unknown**; the recorded final-summary request is **$0.03129175 at token list prices**, not the whole run's cost. New runs checkpoint every response/tool step and retain usage; forced finalization omits tools instead of using Meta's unsupported `tool_choice="none"`.

Synthetic-flow checks use 10 driver seeds. A direct audit found identical intended arrival schedules for seeds 11 and 12, so these are **not ten independent mornings**. The current video has already informed development; a genuinely unseen period/video remains required.

## Tracking correction

Previously, Hungarian assignment considered distant pairs and rejected them afterwards. This could discard valid nearby matches. Distance gating now happens before assignment and tracks can remain unmatched. The old tracker without a mask reproduced the original data exactly, ruling out randomness as the source of the earlier difference.

The fixed tracker with and without the experimental sidewalk exclusion gives the same classified traffic counts. No camera-specific exclusion is enabled. The false 422.4 s queue contribution is gone, while legitimate long waits remain. Full-frame reference coverage improved **90.41% → 91.18%**, dominant-track continuity **80.94% → 83.45%**; median position error is approximately unchanged. Count error increased **3.2% → 3.7%**, a disclosed tradeoff rather than a claimed improvement.

## Run and rebuild

```powershell
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
$env:PYTHONPATH = 'src'
.venv/Scripts/python -m uvicorn web.app:app --port 8020
```

The demo replays recorded model activity. `CANLI_AJAN=1` enables live calls and needs `MODEL_API_KEY` in the environment or ignored `.env` file. Raw data, detection caches and generated video/JSON are intentionally excluded from Git; a fresh clone needs those inputs. This release reused the existing measured camera calibration and road geometry. New-camera setup remains sprint work.

From an existing camera-2 workspace with those inputs, rebuild in this order:

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python scripts/takip_degerlendir.py
.venv/Scripts/python scripts/akis_cikar.py
.venv/Scripts/python scripts/sinyal_cikar.py
.venv/Scripts/python scripts/gelis_cikar.py
.venv/Scripts/python scripts/sim_kalibre.py
.venv/Scripts/python scripts/ajan_calistir.py
.venv/Scripts/python scripts/video_katman.py
.venv/Scripts/python scripts/arayuz_verisi.py --seeds 1 2 3
.venv/Scripts/python scripts/sprint_karsilastir.py --publish
.venv/Scripts/python -m unittest discover -s tests -v
```

The agent command uses paid API tokens. Cached detections, calibration, simulation, rendering and local verification do not call Meta. `arayuz_verisi.py` defaults to ten comparison seeds; this release explicitly uses three and records them in UI metadata. It evaluates a plan once per seed set, not once per reported metric.

## Limitations and sprint status

- One intersection and one morning in 2005; all gains are simulated.
- The same reference informed calibration and evaluation; no fully independent video test yet.
- Side-street timing/reliability and small turning counts remain weaker; pedestrians are timing constraints, not detected people.
- Straight, perpendicular model arms approximate measured geometry. Only a portion of queues is visible.
- New-camera setup, adaptive fairness improvements and agent tuning of adaptive parameters remain pending.

See [the sprint plan](docs/sprint.md), [current rebuild evidence](reports/tracking-rebuild.json) and [current accounting](reports/sprint-accounting.json). [Sprint start](reports/sprint-start.md) and [earlier follow-up](reports/sprint-followup.md) are historical snapshots; their 1,186-vehicle figures are not the current release.

## Credits

- Data: U.S. DOT, Federal Highway Administration, Next Generation Simulation (NGSIM), Lankershim Boulevard. CC BY 2.0; doi:10.21949/1504477.
- Models: SAM 3.1 and Muse Spark 1.3 through Meta Model API.
- Simulation: Eclipse SUMO.
- Coding assistance: Claude (Anthropic) and Codex (OpenAI).
