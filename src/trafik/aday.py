"""Pure, fail-closed sprint candidate gates; no simulator or API calls.

Inputs use ``sonuclar.ozetle`` fields. Demand fingerprints must describe the
scheduled vehicles (IDs, routes and intended departure times), per paired seed.
Equal counts alone cannot establish identical demand. Quantities are simulation
metrics, not claims of an independent field evaluation.
"""

from math import isfinite


ARMS = ("from north (southbound)", "from south (northbound)", "from east", "from west")
GATE_KEYS = ("min_mean_delay_improvement_s", "max_approach_mean_wait_regression_s",
             "max_p95_wait_regression_s", "max_completion_count_drop")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def evaluate_candidate(baseline, candidate, gates, *, baseline_seeds, candidate_seeds,
                       baseline_demand_hashes, candidate_demand_hashes):
    """Return explicit acceptance and every failed gate without modifying inputs.

    The configured minimum mean improvement is checked for timeLoss. Additional
    guards require non-regressing insertion-aware total loss and apply the
    configured global P95 regression limit to each approach as well.
    A missing/nonfinite metric, incomplete demand or unproven pairing rejects the
    candidate even if the remaining displayed means look better.
    """
    if not isinstance(gates, dict):
        raise ValueError("Sprint gates must be a mapping")
    for key in GATE_KEYS:
        if not _number(gates.get(key)) or gates[key] < 0:
            raise ValueError(f"Missing or invalid nonnegative sprint gate: {key}")
    checks = []

    def check(code, passed, **details):
        checks.append({"code": code, "passed": bool(passed), **details})

    check("baseline_metrics_mapping", isinstance(baseline, dict))
    check("candidate_metrics_mapping", isinstance(candidate, dict))
    baseline = baseline if isinstance(baseline, dict) else {}
    candidate = candidate if isinstance(candidate, dict) else {}

    def seeds_valid(seeds):
        return (isinstance(seeds, (list, tuple)) and bool(seeds)
                and all(isinstance(s, int) and not isinstance(s, bool) for s in seeds)
                and len(set(seeds)) == len(seeds))

    paired = (seeds_valid(baseline_seeds) and seeds_valid(candidate_seeds)
              and set(baseline_seeds) == set(candidate_seeds))
    check("paired_seeds", paired,
          baseline=list(baseline_seeds) if seeds_valid(baseline_seeds) else None,
          candidate=list(candidate_seeds) if seeds_valid(candidate_seeds) else None)
    expected = {str(s) for s in baseline_seeds} if seeds_valid(baseline_seeds) else set()

    def fingerprints_valid(hashes):
        return (isinstance(hashes, dict) and set(hashes) == expected and bool(expected)
                and all(isinstance(h, str) and len(h) == 64
                        and all(c in "0123456789abcdef" for c in h.lower()) for h in hashes.values()))

    check("identical_scheduled_demand", paired and fingerprints_valid(baseline_demand_hashes)
          and fingerprints_valid(candidate_demand_hashes)
          and baseline_demand_hashes == candidate_demand_hashes)

    for name, result in (("baseline", baseline), ("candidate", candidate)):
        status = result.get("tohum_talep_durumu")
        valid = isinstance(status, dict) and set(status) == expected and bool(expected)
        if valid:
            for row in status.values():
                fields = ("planlanan", "tamamlanan", "agda_tamamlanmayan", "girememis",
                          "kaydi_eksik", "kohortu_belirsiz")
                valid = valid and isinstance(row, dict) and all(
                    isinstance(row.get(k), int) and not isinstance(row[k], bool) and row[k] >= 0
                    for k in fields)
                if not valid:
                    break
                valid = (row["planlanan"] > 0 and row["planlanan"] == row["tamamlanan"]
                         and all(row[k] == 0 for k in fields[2:]))
                if not valid:
                    break
        check(name + "_complete_demand", valid and result.get("tam_karsilastirma") is True)

    base_status, cand_status = baseline.get("tohum_talep_durumu", {}), candidate.get("tohum_talep_durumu", {})
    counts_valid = (isinstance(base_status, dict) and isinstance(cand_status, dict)
                    and set(base_status) == set(cand_status) == expected and bool(expected))
    drops = {}
    if counts_valid:
        for seed in expected:
            a, b = base_status[seed], cand_status[seed]
            if (not isinstance(a, dict) or not isinstance(b, dict)
                    or not _number(a.get("planlanan")) or a.get("planlanan") != b.get("planlanan")
                    or not _number(a.get("tamamlanan")) or not _number(b.get("tamamlanan"))):
                counts_valid = False
                break
            drops[seed] = a["tamamlanan"] - b["tamamlanan"]
    check("completion_count_drop", counts_valid and all(v <= gates["max_completion_count_drop"]
          for v in drops.values()), per_seed_drop=drops, maximum=gates["max_completion_count_drop"])

    def delta_check(code, base, cand, limit, improvement=False):
        known = _number(base) and _number(cand) and base >= 0 and cand >= 0
        delta = round(cand - base, 10) if known else None
        passed = known and (delta <= -limit if improvement else delta <= limit)
        check(code, passed, baseline=base if _number(base) else None,
              candidate=cand if _number(cand) else None, candidate_minus_baseline_s=delta,
              maximum_delta_s=-limit if improvement else limit)

    delta_check("ort_gecikme_s", baseline.get("ort_gecikme_s"), candidate.get("ort_gecikme_s"),
                gates["min_mean_delay_improvement_s"], True)
    delta_check("ort_toplam_kayip_s", baseline.get("ort_toplam_kayip_s"), candidate.get("ort_toplam_kayip_s"), 0.)
    delta_check("p95_bekleme_s", baseline.get("p95_bekleme_s"), candidate.get("p95_bekleme_s"),
                gates["max_p95_wait_regression_s"])
    for field, gate in (("kol_bekleme_s", "max_approach_mean_wait_regression_s"),
                        ("kol_p95_bekleme_s", "max_p95_wait_regression_s")):
        base = baseline.get(field) if isinstance(baseline.get(field), dict) else {}
        cand = candidate.get(field) if isinstance(candidate.get(field), dict) else {}
        for arm in ARMS:
            delta_check(field + ":" + arm, base.get(arm), cand.get(arm), gates[gate])
    rejected = [c["code"] for c in checks if not c["passed"]]
    return {"accepted": not rejected, "rejection_reasons": rejected, "checks": checks,
            "gates": {key: gates[key] for key in GATE_KEYS},
            "additional_guards": {"max_combined_loss_regression_s": 0.,
                                  "max_approach_p95_wait_regression_s": gates["max_p95_wait_regression_s"]},
            "scope": "Retrospective engineering gates on paired demand; configured mean improvement "
                     "applies to in-network loss. Additional guards forbid combined-loss regression "
                     "and apply the global P95 limit to every approach. "
                     "Missing evidence rejects acceptance; these are not field-safety guarantees."}
