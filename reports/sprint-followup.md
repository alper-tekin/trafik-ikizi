# Sprint follow-up: insertion-aware comparisons and a camera error

## Shared accounting is now used by fixed and adaptive evaluation

All four existing policies were run on the same original 1,186 video arrivals,
driver parameters and seeds **1, 2, 3**. No new policy was tuned and no Meta API
calls were made. The original in-network metrics are preserved and new fields
report insertion delay, combined loss, p95/max stopped wait and per-seed demand
completion. Results: [sprint-accounting.json](sprint-accounting-9e0408f.json).

| Policy | In-network loss (s) | Insertion delay (s) | Combined loss (s) | p95 stopped wait (s) | Completed |
|---|---:|---:|---:|---:|---|
| Current plan | 20.5 | 4.4 | 24.9 | 55.0 | 1,186 / run |
| Recorded agent plan | 18.4 | 2.2 | 20.6 | 48.5 | 1,186 / run |
| Longest wait first | 18.3 | 8.2 | 26.5 | 47.5 | 1,186 / run |
| Weighted wait | 20.3 | 6.4 | 26.7 | 49.0 | 1,186 / run |

**The ranking changes when insertion delay is counted.** Longest-wait-first has
less in-network loss than the current plan but more combined loss. The recorded
agent plan is best of these four on combined loss in this three-seed audit.
This is a retrospective simulation comparison, not an independent test or a
field-travel-time result. It is separate from the historical 10-seed in-network
tables in the demo. Insertion delay is not physical stopped time.

## Prevent incomplete demand from producing a misleading gain

- Trip selection now uses intended departure, so a warm-up vehicle delayed past
  the warm-up boundary cannot contaminate the evaluated population.
- SUMO emits unfinished and uninserted trips. Explicit scheduled vehicles absent
  from output remain in missing-record counts.
- Completed-trip averages exclude partial trips but cannot certify a complete
  comparison when vehicles are unfinished, uninserted or missing.
- Adaptive runs obey the same configured end time as fixed runs.
- Muse Spark is instructed to consider combined loss and recommend only complete
  comparisons. The verifier records completion and both plans' combined loss.
- The comparison UI displays all four policies with insertion delay included.
  Its API rejects stale reports after data or policy-source fingerprints change.

All **17 automated tests** pass. In a live SUMO check, two scheduled vehicles were
deliberately blocked: one entered but did not finish, the other could not enter.
Both fixed and adaptive runs reported **2 scheduled, 0 completed, 1 unfinished,
1 uninserted**, with null completed-trip averages and incomplete comparison status.
See [the engine check](sprint-completion-smoke.json).

## Camera review: track 1500 contains a static off-road fixture

The apparent 422.4 s wait in original track 1500 was traced to a static object on
the west sidewalk around pixel (195.5, 24.5), with the identity later moving onto
a passing vehicle. Video was reviewed at 100, 430, 700, 845, 849 and 860 seconds.
Other extreme tracks reviewed showed real stopped vehicles, so no duration-based
filter was introduced.

An explicit, narrow image polygon was tested offline on the cached detections:

- Removed **4,915 of 189,521** detections in the reviewed off-road region.
- Removed the false 422.4 s contribution; legitimate 80–107 s vehicle waits remain.
- West approach observed mean stopped exposure changed **17.35 → 11.67 s**.
- Classified flow changed **1,186 → 1,184** (one fewer classified track on each
  main approach); candidate numeric IDs must not be paired with original IDs.
- On the same 2-second reference sample grid, position coverage changed
  **90.2345% → 90.1451%**, and median position error stayed **0.841 m**.

This is a **camera-specific experiment, not enabled in production**. It changes
tracking and demand, so activating it requires tracing the changed main-road
counts and rebuilding downstream calibration, agent verification and UI artifacts
together. None of the original production tracks/arrivals/UI data was overwritten.
Results: [camera experiment](sprint-camera-experiment.json).

## Reproduce

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python scripts/sprint_karsilastir.py --publish
.venv/Scripts/python scripts/kamera_maske_deneyi.py
```

The first command checks accounting, warm-up boundaries, missing demand and stale
report handling. The comparison writes new local results and, with `--publish`,
updates the audit table's report. The camera experiment writes a separate ignored
folder and does not replace production inputs. Both tools use existing data and
make no model API calls. The UI audit appears for video replay, not synthetic traffic.

## Remaining work

Trace the two changed main-road classifications before promoting the exclusion;
then rebuild the measurement pipeline coherently. Investigate true long side-street
queues and time-varying signal behaviour. Balance the adaptive controller using
the corrected accounting, and audit synthetic arrival schedules. Independent
video testing, expanded agent tools and new-camera setup remain pending.
