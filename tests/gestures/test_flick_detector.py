import unittest

from backend.gestures.FlickDetector import FlickDetector


class FlickDetectorTests(unittest.TestCase):
    def _feed_points(self, detector: FlickDetector, points, dt: float = 0.03):
        t = 10.0
        for x, y in points:
            detector.add_sample((x, y), t)
            t += dt

    def test_detects_left_right_up_down(self):
        detector = FlickDetector()

        self._feed_points(detector, [(0.70, 0.50), (0.58, 0.50), (0.46, 0.50)])
        self.assertEqual(detector.detect(), "left")
        self.assertIsNone(detector.detect())

        detector.reset()
        self._feed_points(detector, [(0.40, 0.50), (0.52, 0.50), (0.64, 0.50)])
        self.assertEqual(detector.detect(), "right")

        detector.reset()
        self._feed_points(detector, [(0.50, 0.62), (0.50, 0.50), (0.50, 0.38)])
        self.assertEqual(detector.detect(), "up")

        detector.reset()
        self._feed_points(detector, [(0.50, 0.38), (0.50, 0.50), (0.50, 0.62)])
        self.assertEqual(detector.detect(), "down")

    def test_rejects_small_or_slow_motion(self):
        detector = FlickDetector()
        self._feed_points(detector, [(0.50, 0.50), (0.54, 0.50), (0.58, 0.50)])
        self.assertIsNone(detector.detect())

        detector.reset()
        self._feed_points(detector, [(0.40, 0.50), (0.52, 0.50), (0.64, 0.50)], dt=1.0)
        self.assertIsNone(detector.detect())

    def test_rejects_ambiguous_diagonal(self):
        detector = FlickDetector(dominance_ratio=1.3)
        self._feed_points(detector, [(0.50, 0.50), (0.60, 0.40), (0.70, 0.30)])
        self.assertIsNone(detector.detect())

    def test_one_shot_until_reset(self):
        detector = FlickDetector()
        self._feed_points(detector, [(0.40, 0.50), (0.52, 0.50), (0.64, 0.50)])
        self.assertEqual(detector.detect(), "right")
        self.assertIsNone(detector.detect())

        detector.reset()
        self._feed_points(detector, [(0.70, 0.50), (0.58, 0.50), (0.46, 0.50)])
        self.assertEqual(detector.detect(), "left")


if __name__ == "__main__":
    unittest.main()
