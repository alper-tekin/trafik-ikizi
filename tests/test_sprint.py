"""Measurement regressions: boundaries, paired populations and incomplete trips."""

import unittest

import pandas as pd

from trafik.sprint import arrival_diagnostics, paired_waits, queue_series, validate_config, window_waits


def points(times, ids=None, speeds=None):
    n = len(times)
    return pd.DataFrame({"t": times, "arac": ids or [1] * n, "giris": ["K"] * n,
                         "u": [30.] * n, "w": [0.] * n, "hiz": speeds or [0.] * n})


class SprintMeasurements(unittest.TestCase):
    def test_intervals_are_clipped_at_window_boundaries(self):
        d = points([0., .5, 1., 1.5, 2.])
        self.assertAlmostEqual(window_waits(d, .25, 1.25).loc[1, "wait_s"], 1.)
        self.assertAlmostEqual(window_waits(d, 0, 1).loc[1, "wait_s"], 1.)
        self.assertAlmostEqual(window_waits(d, 1, 2).loc[1, "wait_s"], 1.)

    def test_gaps_are_not_filled_and_moving_vehicles_are_retained(self):
        d = points([0., 10., 0., 1.], [1, 1, 2, 2], [0., 0., 3., 3.])
        waits = window_waits(d, 0, 11)
        self.assertEqual(waits.loc[1, "wait_s"], 1.)
        self.assertEqual(waits.loc[2, "wait_s"], 0.)

    def test_pairs_exclude_missing_ids_but_report_them(self):
        video = pd.DataFrame({"giris": ["K", "K"], "wait_s": [10., 100.]}, index=[1, 2])
        twin = pd.DataFrame({"giris": ["K", "K"], "wait_s": [8., 0.]}, index=[1, 3])
        result = paired_waits(video, twin)["K"]
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["mean_twin_minus_video_s"], -2.)
        self.assertEqual(result["video_only_n"], 1)
        self.assertEqual(result["twin_only_n"], 1)

    def test_queue_has_zero_seconds_and_all_arms(self):
        result = queue_series(points([0., 1., 2.], speeds=[0., 3., 3.]), 0, 3)
        self.assertEqual(result.K.tolist(), [1, 0, 0])
        self.assertEqual(result.B.tolist(), [0, 0, 0])

    def test_missing_source_coverage_is_not_zero_queue(self):
        result = queue_series(points([0., 2.]), 0, 3)
        self.assertTrue(result.loc[1].isna().all())
        self.assertEqual(result.loc[0, "K"], 1)

    def test_missing_trip_is_counted_as_not_completed(self):
        arrivals = pd.DataFrame({"arac": [1, 2], "giris": ["K", "K"], "hiz": [0., 2.], "d_m": [30., 40.]})
        trips = pd.DataFrame({"arac": [1], "depart_delay_s": [5.]})
        result = arrival_diagnostics(arrivals, trips, {"K": {"durma_m": 20.}})["K"]
        self.assertEqual(result["scheduled_n"], 2)
        self.assertEqual(result["not_completed_n"], 1)
        self.assertEqual(result["mean_insertion_delay_s"], 5.)

    def test_protocol_rejects_gaps_and_independent_claim(self):
        valid = {"windows": {"a": [0, 2], "b": [2, 3]}, "video_duration_s": 3,
                 "independent_test": {"status": "not_available"}}
        validate_config(valid)
        with self.assertRaises(ValueError):
            validate_config({**valid, "windows": {"a": [0, 2], "b": [2.1, 3]}})
        with self.assertRaises(ValueError):
            validate_config({**valid, "independent_test": {"status": "available"}})


if __name__ == "__main__":
    unittest.main()
