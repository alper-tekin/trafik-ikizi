from copy import deepcopy
import json
import unittest

from trafik.aday import ARMS, evaluate_candidate


GATES = {"min_mean_delay_improvement_s": 1., "max_approach_mean_wait_regression_s": 1.,
         "max_p95_wait_regression_s": 2., "max_completion_count_drop": 0}


def result(loss=20., total=23.):
    return {"ort_gecikme_s": loss, "ort_toplam_kayip_s": total, "p95_bekleme_s": 40.,
            "kol_bekleme_s": dict.fromkeys(ARMS, 10.), "kol_p95_bekleme_s": dict.fromkeys(ARMS, 30.),
            "tam_karsilastirma": True, "tohum_talep_durumu": {
                str(s): {"planlanan": 10, "tamamlanan": 10, "agda_tamamlanmayan": 0,
                         "girememis": 0, "kaydi_eksik": 0, "kohortu_belirsiz": 0} for s in (1, 2)}}


class CandidateGates(unittest.TestCase):
    def evaluate(self, baseline=None, candidate=None, **changes):
        kwargs = {"baseline_seeds": [1, 2], "candidate_seeds": [1, 2],
                  "baseline_demand_hashes": {"1": "a" * 64, "2": "b" * 64},
                  "candidate_demand_hashes": {"1": "a" * 64, "2": "b" * 64}}
        kwargs.update(changes)
        return evaluate_candidate(baseline or result(), candidate or result(19., 22.), GATES, **kwargs)

    def test_exact_thresholds_pass_and_inputs_are_unchanged(self):
        baseline, candidate = result(), result(19., 22.)
        candidate["kol_bekleme_s"][ARMS[0]] = 11.
        candidate["kol_p95_bekleme_s"][ARMS[0]] = 32.
        before = deepcopy((baseline, candidate))
        self.assertTrue(self.evaluate(baseline, candidate)["accepted"])
        self.assertEqual((baseline, candidate), before)

    def test_insertion_delay_cannot_hide_lost_gain(self):
        report = self.evaluate(candidate=result(18., 23.1))
        self.assertIn("ort_toplam_kayip_s", report["rejection_reasons"])

    def test_combined_loss_uses_nonregression_not_an_invented_improvement_target(self):
        self.assertTrue(self.evaluate(candidate=result(19., 23.))["accepted"])

    def test_one_approach_and_its_tail_cannot_be_hidden_by_global_gain(self):
        candidate = result(17., 20.)
        candidate["kol_bekleme_s"][ARMS[1]] = 11.1
        candidate["kol_p95_bekleme_s"][ARMS[2]] = 32.1
        report = self.evaluate(candidate=candidate)
        self.assertIn("kol_bekleme_s:" + ARMS[1], report["rejection_reasons"])
        self.assertIn("kol_p95_bekleme_s:" + ARMS[2], report["rejection_reasons"])

    def test_equal_counts_do_not_prove_identical_scheduled_demand(self):
        report = self.evaluate(candidate_demand_hashes={"1": "c" * 64, "2": "b" * 64})
        self.assertIn("identical_scheduled_demand", report["rejection_reasons"])
        self.assertFalse(self.evaluate(candidate_demand_hashes={})["accepted"])

    def test_seeds_must_be_nonempty_unique_and_paired(self):
        for seeds in (None, 1, "1,2", [], [1, 1], [1, 3], [True, 2], [{}, 2]):
            with self.subTest(seeds=seeds):
                self.assertIn("paired_seeds", self.evaluate(candidate_seeds=seeds)["rejection_reasons"])
        self.assertTrue(self.evaluate(candidate_seeds=[2, 1])["accepted"])

    def test_null_or_malformed_metric_containers_reject_without_crashing(self):
        for invalid in (None, [], "missing", 3):
            with self.subTest(invalid=invalid):
                report = evaluate_candidate(result(), invalid, GATES,
                    baseline_seeds=[1, 2], candidate_seeds=[1, 2],
                    baseline_demand_hashes={"1": "a" * 64, "2": "b" * 64},
                    candidate_demand_hashes={"1": "a" * 64, "2": "b" * 64})
                self.assertIn("candidate_metrics_mapping", report["rejection_reasons"])
                json.dumps(report, allow_nan=False)
        for status in (None, [], "missing", {"1": None, "2": []}):
            candidate = result(17., 19.)
            candidate["tohum_talep_durumu"] = status
            self.assertIn("candidate_complete_demand", self.evaluate(candidate=candidate)["rejection_reasons"])

    def test_lost_uninserted_vehicle_blocks_acceptance_even_if_flag_is_wrong(self):
        candidate = result(17., 19.)
        candidate["tohum_talep_durumu"]["2"].update(tamamlanan=9, girememis=1)
        report = self.evaluate(candidate=candidate)
        self.assertIn("candidate_complete_demand", report["rejection_reasons"])
        self.assertIn("completion_count_drop", report["rejection_reasons"])

    def test_missing_metric_null_and_nan_are_not_improvements(self):
        for value in (None, float("nan"), float("inf"), -1., True):
            candidate = result(17., 19.)
            candidate["kol_p95_bekleme_s"][ARMS[0]] = value
            report = self.evaluate(candidate=candidate)
            self.assertFalse(report["accepted"])
            json.dumps(report, allow_nan=False)
        candidate = result(17., 19.)
        del candidate["kol_p95_bekleme_s"]
        self.assertFalse(self.evaluate(candidate=candidate)["accepted"])

    def test_missing_seed_counts_and_false_complete_flag_reject(self):
        candidate = result(17., 19.)
        del candidate["tohum_talep_durumu"]["2"]
        self.assertFalse(self.evaluate(candidate=candidate)["accepted"])
        baseline = result()
        baseline["tam_karsilastirma"] = False
        self.assertFalse(self.evaluate(baseline=baseline)["accepted"])

    def test_unknown_cohort_is_rejected(self):
        candidate = result(17., 19.)
        candidate["tohum_talep_durumu"]["1"]["kohortu_belirsiz"] = 1
        self.assertIn("candidate_complete_demand", self.evaluate(candidate=candidate)["rejection_reasons"])

    def test_bad_protocol_fails_before_evaluation(self):
        for gates in (None, {}, [], {**GATES, "min_mean_delay_improvement_s": None}):
            with self.subTest(gates=gates), self.assertRaises(ValueError):
                evaluate_candidate({}, {}, gates, baseline_seeds=[], candidate_seeds=[],
                                   baseline_demand_hashes={}, candidate_demand_hashes={})


if __name__ == "__main__":
    unittest.main()
