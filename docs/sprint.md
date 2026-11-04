# Traffic Twin sprint

Status: **started**. This document tracks delivered work separately from planned work.

## Goal and sequence

| Work | Status | Exit condition |
|---|---|---|
| Freeze current inputs and reproduce the baseline | Implemented; see `reports/sprint-start.json` | Versioned protocol, input hashes, package versions, fresh simulation and recorded-result comparison |
| Diagnose side-street measurement/model errors | In progress; static fixture confirmed and insertion accounting implemented | Review extreme tracks, insertion delays, signal timing and matched vehicle populations before changing calibration |
| Balance the adaptive controller | Pending | Compare mean, p95, per-approach wait, completion and pedestrian service on paired demand |
| Let Muse Spark test adaptive parameters and additional baselines | Pending | Only recommend tested candidates; use the same demand and evaluation budget |
| Explain signal decisions in the existing UI | Pending | Show why a phase was selected, including tradeoffs |
| New fixed-camera video setup prototype | Pending | User-assisted metric calibration and lane validation without NGSIM trajectories |
| Final evaluation | Pending | Frozen parameters; separate evidence on a new period/video, with all limitations recorded |

## Evaluation protocol

`config/sprint.json` fixes the windows, seeds and candidate acceptance targets.
The existing video is split into [0, 404), [404, 707) and [707, 1122) seconds
for **retrospective diagnosis only**. All of it has already informed development.
Neither slicing metrics nor changing seeds makes it an unseen test. Existing
calibration, geometry and signal estimates are not refitted by the baseline tool.
A genuinely independent test period/video remains unavailable.

The prospective engineering targets for a new controller are at least 1 s mean
delay improvement, no approach's mean wait more than 1 s worse, no p95 wait more
than 2 s worse, and no completion-count drop. These are targets, not measured
achievements or field deployment guarantees. Evaluate with paired seeds and
identical scheduled demand, and account for incomplete/uninserted vehicles.
Do not silently tune thresholds after seeing candidate results.

## Reproduce and inspect the baseline

From the repository root, in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python scripts/sprint_baseline.py
```

Use `--snapshot-only` to capture without running SUMO. No Meta API calls are made.
Each run creates a new, ignored `data/sprint/<UTC timestamp>/` folder containing:

- `manifest.json`: SHA-256 hashes, source revision/status, exact installed package
  versions and protocol. An explicit file allowlist excludes `.env` and secrets.
- `snapshot/`: copies of code and small inputs. Large assets are hashed in place;
  keep the original data files to reproduce the run.
- `twin_seed1.parquet`: the fresh simulation trajectory used for diagnosis.
- `baseline.json`: current-plan results on seeds 1–3, seed-1 insertion accounting,
  per-arm and per-window measurements, paired vehicle errors and extreme tracks.

The tool checks that inventoried files did not change during the simulation.
It leaves the original calibration, detections, agent records and web data alone.
Simulation scratch files live under `sim/`, which is ignored.

## Measurement definitions and limitations

- Existing average delay is SUMO `timeLoss`, measured **after insertion**.
  `departDelay` is recorded separately and added to `timeLoss` in an additional
  completed-trip metric. This is simulation scheduling loss, not observed
  stopped time or a measured field-travel-time improvement.
- Window waits are observed stopped exposure: speed below 1 m/s, within 12–75 m
  of the intersection centre on the entry arm. Intervals are clipped at the
  window boundaries; gaps contribute at most 1 s. These are not whole journeys.
- Vehicle-level errors pair the same original track IDs. Missing counterparts
  are reported, never silently dropped from counts.
- Queue comparisons use integer-second samples. Missing source coverage remains
  unknown rather than being presented as an empty queue; comparisons report the
  number of paired seconds as well as RMSE.
- Long stopped tracks need review. They may include parked/stationary vehicles,
  real prolonged queues or identity errors. No suspect tracks are automatically
  excluded to improve scores.
- NGSIM positions informed the homography/time offset and local coordinate
  origin/axis. NGSIM class comparisons informed the large-vehicle threshold.
  NGSIM is therefore a reference, not independent ground truth for this pipeline.

## Next investigations

1. Review track 1500 and other large side-street wait mismatches against video.
   Separate road-side stopping from signal-controlled queuing before filtering.
2. Explain delayed insertion, especially the south approach. Ensure any candidate
   gain is not simply more waiting outside the simulated network.
3. Inspect side-street green-window uncertainty and permitted turns using reviewed
   tracks, not only aggregate mean wait.
4. Audit whether the synthetic-demand mode changes arrival schedules across seeds
   or only driver behaviour before treating its runs as different mornings.

Controller/agent/UI changes have not yet been made as part of this sprint.


## Follow-up delivery

See [the follow-up report](../reports/sprint-followup.md). Shared fixed/adaptive accounting and the insertion-aware UI table are implemented. A narrow off-road exclusion was tested on cached detections and remains experimental. The adaptive policy itself has not yet been retuned.
