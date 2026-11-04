# Sprint start: reproduced baseline and first diagnosis

Run: `20261104T200739796377Z`. Source revision: `c50bf4edc5ae1b8ba49e247370116a855a768ff8` plus the new baseline tooling captured in the local snapshot. Machine-readable results: [sprint-start.json](sprint-start.json). Protocol and remaining work: [sprint plan](../docs/sprint.md).

## Delivered

- Added an input/source snapshot with SHA-256 hashes, exact installed package versions, the evaluation protocol and a check for input changes during execution.
- Re-ran the current signal plan (15/13/32/33 s, cycle 101 s) on driver seeds 1–3: **20.5 s** mean in-network delay, **20.3–20.6 s** seed range, **68.0 s** p95 delay and **1,186 completed vehicles**. The average matches the recorded run.
- Added vehicle-paired, per-approach and per-window diagnosis, with zero-wait vehicles retained and missing queue samples explicitly marked unknown.
- Passed **7 measurement regression tests**, covering interval boundaries, tracking gaps, vehicle pairing, missing samples, incomplete trips and protocol validation.
- Made no Meta API requests and changed no detector, calibration, signal policy or production web-data files.

## Insertion delay must not disappear from comparisons

SUMO can postpone insertion if there is insufficient room at a vehicle's scheduled entry position. The existing `timeLoss` metric starts after insertion. The fresh seed-1 accounting is:

- In-network time loss: **20.56 s** per completed vehicle.
- Insertion delay: **4.51 s**.
- Sum: **25.07 s**.

These three numbers use the same seed-1 completed population. They must not be mixed with the three-seed mean above or labelled as observed physical stopped time. A future controller must not appear better by leaving vehicles outside the network.

| Approach | Scheduled | Completed | Mean insertion delay (s) | Max insertion delay (s) | Twin minus video stopped exposure (s) |
|---|---:|---:|---:|---:|---:|
| From north | 615 | 615 | 1.70 | 60.5 | -0.06 |
| From south | 429 | 429 | 9.43 | 85.2 | -1.87 |
| From east | 66 | 66 | 0.22 | 1.2 | -9.08 |
| From west | 76 | 76 | 3.18 | 70.0 | -10.32 |

The final column pairs the same track IDs within video seconds [0, 1122), speed below 1 m/s and 12–75 m from the centre. All 1,186 tracks have counterparts. This is observed stopped exposure, not the whole-simulation `waitingTime` metric.

## Extreme tracks require review before recalibration

Track **1500**, assigned to the west approach, contributes **422.4 s** of observed stopped exposure versus **1.0 s** in the twin. Several other side-street tracks contribute 70–105 s. Consequently, a large mean error does not by itself prove that the signal model is the sole cause. Possible explanations include road-side stopping, prolonged real queues and tracking identity errors. None of these tracks has been removed or relabelled.

## Evaluation status

The current video and NGSIM reference were already used during development. Windows [0, 404), [404, 707) and [707, 1122) are **retrospective diagnostic windows only**; this run does not refit calibration on the first window. A genuinely unseen period/video is still required. NGSIM also informed the coordinate origin/axis and large-vehicle assumptions, in addition to homography and time offset.

The next work is to review the extreme side-street tracks and delayed insertion, then reassess the signal windows. Adaptive-controller changes, expanded agent tools and the new-video UI remain pending. Arrival-schedule variation in the synthetic-demand mode also needs auditing before calling its seeded runs different mornings.
