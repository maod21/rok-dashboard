from __future__ import annotations

import unittest

import pandas as pd

from goal_metrics import calculate_goal_progress, default_goal_bands, summarize_goal_bands


class GoalMetricTests(unittest.TestCase):
    def test_power_band_boundaries_use_lower_inclusive_upper_exclusive(self) -> None:
        powers = [9_999_999, 10_000_000, 29_999_999, 30_000_000, 59_999_999, 60_000_000, 89_999_999, 90_000_000]
        metrics = pd.DataFrame(
            {
                "character_id": [str(index) for index, _ in enumerate(powers)],
                "username": [f"Player {index}" for index, _ in enumerate(powers)],
                "power": powers,
                "combined_points": [0] * len(powers),
            }
        )

        result = calculate_goal_progress(metrics, default_goal_bands())

        self.assertEqual(
            result["power_band"].tolist(),
            ["0-10M", "10M-30M", "10M-30M", "30M-60M", "30M-60M", "60M-90M", "60M-90M", "90M+"],
        )

    def test_goal_progress_gap_and_status(self) -> None:
        metrics = pd.DataFrame(
            {
                "character_id": ["zero", "none", "partial", "met"],
                "username": ["Zero", "None", "Partial", "Met"],
                "power": [0, 10_000_000, 10_000_000, 10_000_000],
                "combined_points": [0, 0, 60_000, 120_000],
            }
        )

        result = calculate_goal_progress(metrics, default_goal_bands()).set_index("character_id")

        self.assertEqual(result.loc["zero", "target_points"], 0)
        self.assertEqual(result.loc["zero", "goal_status"], "No Target")
        self.assertEqual(result.loc["none", "target_points"], 120_000)
        self.assertEqual(result.loc["none", "goal_status"], "No Points")
        self.assertEqual(result.loc["none", "gap_to_goal"], 120_000)
        self.assertEqual(result.loc["partial", "goal_status"], "In Progress")
        self.assertAlmostEqual(result.loc["partial", "progress_pct"], 0.5)
        self.assertEqual(result.loc["partial", "gap_to_goal"], 60_000)
        self.assertEqual(result.loc["met", "goal_status"], "Met")
        self.assertEqual(result.loc["met", "gap_to_goal"], 0)

    def test_goal_summary_rolls_up_band_progress(self) -> None:
        metrics = pd.DataFrame(
            {
                "character_id": ["a", "b"],
                "username": ["A", "B"],
                "power": [10_000_000, 10_000_000],
                "combined_points": [120_000, 0],
            }
        )

        progress = calculate_goal_progress(metrics, default_goal_bands())
        summary = summarize_goal_bands(progress).set_index("power_band")

        self.assertEqual(summary.loc["10M-30M", "players"], 2)
        self.assertEqual(summary.loc["10M-30M", "met_goal"], 1)
        self.assertEqual(summary.loc["10M-30M", "no_points"], 1)
        self.assertEqual(summary.loc["10M-30M", "gap_to_goal"], 120_000)
        self.assertAlmostEqual(summary.loc["10M-30M", "progress_pct"], 0.5)


if __name__ == "__main__":
    unittest.main()
