import unittest
import numpy as np
from trafik.kamera import dislama_uygula


class CameraExclusions(unittest.TestCase):
    def test_offroad_fixture_removed_but_adjacent_queued_vehicle_retained(self):
        zones = [{"polygon_px": [[186, 0], [202, 0], [202, 44], [186, 44]]}]
        boxes = np.array([[190, 10, 201, 39, .9], [204, 10, 220, 39, .9]])
        np.testing.assert_array_equal(dislama_uygula(boxes, zones), boxes[1:])

    def test_no_regions_is_noop_and_input_is_preserved(self):
        boxes = np.array([[0, 0, 1, 1, .8]])
        original = boxes.copy()
        np.testing.assert_array_equal(dislama_uygula(boxes, []), boxes)
        np.testing.assert_array_equal(boxes, original)
        self.assertEqual(dislama_uygula(np.empty((0, 5)), []).shape, (0, 5))


if __name__ == "__main__":
    unittest.main()
