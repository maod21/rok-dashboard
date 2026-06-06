from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from storage import SQLiteStorage


class SQLiteGoalBandStorageTests(unittest.TestCase):
    db_path = Path("data/unit_test_goals.sqlite")

    def setUp(self) -> None:
        self.storage = None
        if self.db_path.exists():
            self.db_path.unlink()

    def tearDown(self) -> None:
        if self.storage is not None:
            self.storage.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_sqlite_seeds_and_saves_goal_bands(self) -> None:
        storage = SQLiteStorage(self.db_path)
        self.storage = storage

        defaults = storage.load_goal_bands()
        self.assertEqual(defaults["label"].tolist(), ["0-10M", "10M-30M", "30M-60M", "60M-90M", "90M+"])

        custom = pd.DataFrame(
            [
                {
                    "band_id": "custom",
                    "label": "Custom",
                    "min_power": 0,
                    "max_power": None,
                    "target_dkpi": 0.123,
                    "sort_order": 1,
                }
            ]
        )
        storage.save_goal_bands(custom)
        loaded = storage.load_goal_bands()

        self.assertEqual(loaded["label"].tolist(), ["Custom"])
        self.assertAlmostEqual(float(loaded.iloc[0]["target_dkpi"]), 0.123)


if __name__ == "__main__":
    unittest.main()
