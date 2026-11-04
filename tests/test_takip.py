import unittest
import numpy as np

from trafik.takip import _esle


class GatedMatching(unittest.TestCase):
    def test_invalid_shortcut_cannot_steal_a_second_valid_match(self):
        # Ungated Hungarian prefers A->d (14.14, invalid) + B->c (1)
        # over A->c (9) + B->d (10), then loses A when the gate is applied.
        tracks = np.array([[0., 0.], [10., 0.]])
        detections = np.array([[9., 0.], [10., 10.]])
        self.assertEqual(_esle([], [0, 1], tracks, detections, {0, 1}, 10), [(0, 0), (1, 1)])

    def test_every_track_can_remain_unmatched(self):
        tracks = np.array([[0., 0.], [10., 0.]])
        detections = np.array([[100., 100.]])
        self.assertEqual(_esle([], [0, 1], tracks, detections, {0}, 10), [])

    def test_nearest_valid_assignment_is_used_when_cardinality_is_equal(self):
        tracks = np.array([[0., 0.], [10., 0.]])
        detections = np.array([[1., 0.], [9., 0.]])
        self.assertEqual(_esle([], [0, 1], tracks, detections, {0, 1}, 10), [(0, 0), (1, 1)])

    def test_extra_far_detection_does_not_steal_close_matches(self):
        tracks = np.array([[0., 0.], [10., 0.]])
        detections = np.array([[1., 0.], [9., 0.], [1000., 1000.]])
        self.assertEqual(_esle([], [0, 1], tracks, detections, {0, 1, 2}, 10), [(0, 0), (1, 1)])


if __name__ == "__main__":
    unittest.main()
