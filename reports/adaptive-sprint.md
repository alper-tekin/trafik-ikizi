# Adaptive controller sprint experiment

None of the six candidates passed all gates. The selected fixed plan stays the recommendation. The lowest-total-loss adaptive candidate with complete demand was **Weighted wait, 30 s** at **21.8 s**, compared with **19.7 s** for the selected fixed plan.

All eight policies used the same hashed route schedule and driver seeds 1, 2 and 3. All 1,191 vehicles completed in every run. These 24 runs reuse the development video; different seeds do not make them independent traffic periods. No model API calls were made.

| Policy | In-network loss (s) | Insertion (s) | Total loss (s) | P95 stopped wait (s) | Vehicle gates vs. current | Vehicle gates vs. selected | Pedestrian gap guard |
|---|---:|---:|---:|---:|---|---|---|
| Current fixed | 19.4 | 2.6 | 22.0 | 55.0 | — | — | — |
| Selected fixed | 17.9 | 1.8 | 19.7 | 52.0 | — | — | — |
| Longest wait, 30 s | 17.3 | 6.3 | 23.6 | 42.2 | No | No | No |
| Longest wait, 45 s | 18.5 | 5.8 | 24.2 | 42.0 | No | No | No |
| Longest wait, 60 s | 17.8 | 5.2 | 23.0 | 47.7 | No | No | Yes |
| Weighted wait, 30 s | 18.0 | 3.8 | 21.8 | 37.0 | No | No | No |
| Weighted wait, 45 s | 21.5 | 5.7 | 27.2 | 52.5 | No | No | No |
| Weighted wait, 60 s | 20.1 | 3.4 | 23.5 | 50.0 | No | No | Yes |

The longest-wait rule at 60 s illustrates the tradeoff: compared with the selected fixed plan, in-network loss falls from 17.9 to 17.8 s, but total loss rises from 19.7 to 23.0 s. Mean insertion delay rises from 3.2 to 8.7 s on the south approach and from 4.2 to 13.6 s on the west approach. The next tuning target is the entry backlog on these approaches.

Vehicle gates require at least 1 s less in-network loss, no increase in insertion-aware total loss, at most 1 s more mean stopped wait per approach, at most 2 s more p95 stopped wait overall or per approach, and complete matched demand. The results use the project's one-decimal trip summaries. Candidates are checked against both fixed plans. Full checks, paired demand fingerprints, inputs and preregistration are in [the experiment data](adaptive-sprint.json).

The pedestrian guard compares the longest observed gap in assumed service against the same adaptive rule at 60 s, by phase and seed. These are green-duration observations, not pedestrian trajectories. After the required duration is reached, ongoing green counts as available service for this proxy. The 120 s priority trigger does not guarantee a maximum service gap or crossing safety.

The four existing adaptive replays (both rules, both traffic modes) were repeated and matched on all 600 signal states and all vehicle frames before adding decision reasons. The playback explanations use the same timestamps as the simulated signal. No adaptive policy was promoted.

To reproduce, run `scripts/sprint_adaptive.py --seeds 1 2 3` with the project Python environment from the repository root. Each run writes a new ignored folder with preregistration, route files, trip records and full phase/pedestrian logs. The committed JSON contains the summary and gate results.
