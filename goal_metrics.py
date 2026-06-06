from __future__ import annotations

import math
from typing import Any

import pandas as pd


GOAL_BAND_COLUMNS = ["band_id", "label", "min_power", "max_power", "target_dkpi", "sort_order"]

DEFAULT_GOAL_BANDS = [
    {"band_id": "0_10m",    "label": "0-10M",    "min_power": 0,          "max_power": 10_000_000,  "target_dkpi": 0.008, "sort_order": 1},
    {"band_id": "10_30m",   "label": "10M-30M",  "min_power": 10_000_000, "max_power": 30_000_000,  "target_dkpi": 0.012, "sort_order": 2},
    {"band_id": "30_60m",   "label": "30M-60M",  "min_power": 30_000_000, "max_power": 60_000_000,  "target_dkpi": 0.018, "sort_order": 3},
    {"band_id": "60_90m",   "label": "60M-90M",  "min_power": 60_000_000, "max_power": 90_000_000,  "target_dkpi": 0.024, "sort_order": 4},
    {"band_id": "90m_plus", "label": "90M+",     "min_power": 90_000_000, "max_power": None,         "target_dkpi": 0.030, "sort_order": 5},
]


def default_goal_bands() -> pd.DataFrame:
    """Return the built-in 'Balanceado' preset as a normalised DataFrame."""
    return normalize_goal_bands(pd.DataFrame(DEFAULT_GOAL_BANDS))


def normalize_goal_bands(raw: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    """Coerce and validate a goal-band table.

    Missing columns are added as ``None``/0.  Rows with blank ``band_id`` or
    ``label`` are dropped.  The result is sorted by ``sort_order`` then
    ``min_power``.
    """
    frame = pd.DataFrame(raw).copy()
    for col in GOAL_BAND_COLUMNS:
        if col not in frame:
            frame[col] = None

    frame = frame[GOAL_BAND_COLUMNS]
    frame["band_id"] = frame["band_id"].fillna("").astype(str).str.strip()
    frame["label"] = frame["label"].fillna("").astype(str).str.strip()
    frame["min_power"] = pd.to_numeric(frame["min_power"], errors="coerce").fillna(0).astype("int64")
    frame["max_power"] = pd.to_numeric(frame["max_power"], errors="coerce")
    frame["target_dkpi"] = pd.to_numeric(frame["target_dkpi"], errors="coerce").fillna(0.0).astype(float)
    frame["sort_order"] = pd.to_numeric(frame["sort_order"], errors="coerce").fillna(0).astype("int64")
    frame = frame[frame["band_id"].ne("") & frame["label"].ne("")]
    return frame.sort_values(["sort_order", "min_power"]).reset_index(drop=True)


def serialize_goal_bands(raw: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalise *raw* and return a list of plain dicts safe for JSON / SQL."""
    frame = normalize_goal_bands(raw)
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        max_power = row["max_power"]
        row["max_power"] = None if pd.isna(max_power) else int(max_power)
        row["min_power"] = int(row["min_power"])
        row["target_dkpi"] = float(row["target_dkpi"])
        row["sort_order"] = int(row["sort_order"])
        records.append(row)
    return records


def calculate_goal_progress(metrics: pd.DataFrame, goal_bands: pd.DataFrame) -> pd.DataFrame:
    """Annotate *metrics* with goal-progress columns.

    Added columns: ``power_band``, ``target_dkpi``, ``target_points``,
    ``progress_pct``, ``gap_to_goal``, ``over_goal_points``, ``goal_status``.
    """
    bands = normalize_goal_bands(goal_bands)
    output = metrics.copy()

    if output.empty:
        for col in _goal_columns():
            output[col] = []
        return output

    output["power"] = pd.to_numeric(output.get("power", 0), errors="coerce").fillna(0)
    output["combined_points"] = pd.to_numeric(output.get("combined_points", 0), errors="coerce").fillna(0)

    assigned = output["power"].map(lambda p: _find_band(float(p), bands))
    output["power_band"] = assigned.map(lambda b: b["label"] if b else "Unassigned")
    output["target_dkpi"] = assigned.map(lambda b: float(b["target_dkpi"]) if b else 0.0)
    output["target_points"] = output.apply(
        lambda row: int(math.ceil(max(float(row["power"]), 0) * max(float(row["target_dkpi"]), 0))),
        axis=1,
    )
    output["progress_pct"] = output.apply(_progress_pct, axis=1)
    output["gap_to_goal"] = (output["target_points"] - output["combined_points"]).clip(lower=0).astype("int64")
    output["over_goal_points"] = (output["combined_points"] - output["target_points"]).clip(lower=0).astype("int64")
    output["goal_status"] = output.apply(_goal_status, axis=1)

    return output


def summarize_goal_bands(goal_progress: pd.DataFrame) -> pd.DataFrame:
    """Aggregate goal progress by power band."""
    if goal_progress.empty:
        return pd.DataFrame(columns=[
            "power_band", "players", "met_goal", "no_points",
            "combined_points", "target_points", "gap_to_goal", "progress_pct",
        ])

    grouped = (
        goal_progress.groupby("power_band", dropna=False)
        .agg(
            players=("character_id", "count"),
            met_goal=("goal_status", lambda v: int((v == "Met").sum())),
            no_points=("combined_points", lambda v: int((v <= 0).sum())),
            combined_points=("combined_points", "sum"),
            target_points=("target_points", "sum"),
            gap_to_goal=("gap_to_goal", "sum"),
        )
        .reset_index()
    )
    grouped["progress_pct"] = grouped.apply(_progress_pct, axis=1)
    return grouped.sort_values("target_points", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_band(power: float, bands: pd.DataFrame) -> dict[str, Any] | None:
    for band in bands.to_dict(orient="records"):
        min_power = float(band["min_power"])
        max_power = band["max_power"]
        if power < min_power:
            continue
        if pd.isna(max_power) or power < float(max_power):
            return band
    return None


def _progress_pct(row: pd.Series) -> float:
    target = float(row.get("target_points", 0) or 0)
    if target <= 0:
        return 0.0
    return float(row.get("combined_points", 0) or 0) / target


def _goal_status(row: pd.Series) -> str:
    target = float(row.get("target_points", 0) or 0)
    combined = float(row.get("combined_points", 0) or 0)
    if target <= 0:
        return "No Target"
    if combined >= target:
        return "Met"
    if combined <= 0:
        return "No Points"
    return "In Progress"


def _goal_columns() -> list[str]:
    return [
        "power_band", "target_dkpi", "target_points",
        "progress_pct", "gap_to_goal", "over_goal_points", "goal_status",
    ]
