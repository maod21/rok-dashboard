from __future__ import annotations

"""
goal_metrics.py — Lógica de metas por City Power

Metas (City Power → Dead Troops + KP):
  ≤ 49M          : 900k T4 mortes  | 80M KP
  50M – 59M      : 900k T4 ou 450k T5 mortes | 100M KP
  60M – 69M      : 1M T4 ou 500k T5 mortes   | 140M KP
  70M – 79M      : 1.4M T4 ou 700k T5 mortes | 180M KP
  80M – 89M      : 1.6M T4 ou 800k T5 mortes | 200M KP
  90M – 99M      : 2M T4 ou 1M T5 mortes     | 280M KP
  ≥ 100M         : 2M T4 ou 1M T5 mortes     | 320M KP

Equivalência T5↔T4: 1 morte T5 = 2 mortes T4
(score_mortes = deaths_t5 * 2 + deaths_t4)
Meta em "T4 equivalente".
"""

import math
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Tabela de metas fixas por faixa de power
# ---------------------------------------------------------------------------
# target_deaths_t4eq = meta de mortes em unidades T4-equivalente
# target_kp           = meta de Kill Points
POWER_GOAL_BANDS = [
    {"label": "≤ 49M",   "min_power": 0,           "max_power": 50_000_000,  "target_deaths_t4eq": 900_000,   "target_kp": 80_000_000},
    {"label": "50M–59M", "min_power": 50_000_000,  "max_power": 60_000_000,  "target_deaths_t4eq": 900_000,   "target_kp": 100_000_000},
    {"label": "60M–69M", "min_power": 60_000_000,  "max_power": 70_000_000,  "target_deaths_t4eq": 1_000_000, "target_kp": 140_000_000},
    {"label": "70M–79M", "min_power": 70_000_000,  "max_power": 80_000_000,  "target_deaths_t4eq": 1_400_000, "target_kp": 180_000_000},
    {"label": "80M–89M", "min_power": 80_000_000,  "max_power": 90_000_000,  "target_deaths_t4eq": 1_600_000, "target_kp": 200_000_000},
    {"label": "90M–99M", "min_power": 90_000_000,  "max_power": 100_000_000, "target_deaths_t4eq": 2_000_000, "target_kp": 280_000_000},
    {"label": "≥ 100M",  "min_power": 100_000_000, "max_power": None,        "target_deaths_t4eq": 2_000_000, "target_kp": 320_000_000},
]


def _find_band(power: float) -> dict[str, Any] | None:
    for band in POWER_GOAL_BANDS:
        if power < band["min_power"]:
            continue
        if band["max_power"] is None or power < band["max_power"]:
            return band
    return None


def _deaths_t4eq(row: pd.Series) -> int:
    """T4-equivalent death score: T5 * 2 + T4."""
    t5 = float(row.get("t5_deaths", 0) or 0)
    t4 = float(row.get("t4_deaths", 0) or 0)
    return int(t5 * 2 + t4)


def _death_status(deaths_t4eq: int, target_t4eq: int) -> str:
    """Classifica o progresso de mortes."""
    if target_t4eq <= 0:
        return "ok"
    pct = deaths_t4eq / target_t4eq
    if pct >= 1.0:
        return "ok"
    if pct >= 0.75:
        return "pending"
    return "below"


def _kp_status(kp: float, target_kp: int) -> str:
    if target_kp <= 0:
        return "ok"
    pct = kp / target_kp
    if pct >= 1.0:
        return "ok"
    if pct >= 0.75:
        return "pending"
    return "below"


def _overall_status(death_s: str, kp_s: str) -> str:
    """
    Aprovado   → ambos ok
    Pendente   → algum pending, nenhum below
    Abaixo     → algum below
    """
    statuses = {death_s, kp_s}
    if "below" in statuses:
        return "Abaixo da meta"
    if "pending" in statuses:
        return "Pendente"
    return "Aprovado"


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def calculate_member_goals(metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame de métricas (saída de calculate_metrics) e retorna um
    DataFrame enriquecido com colunas de metas individuais:

      power_band          – faixa de power
      target_deaths_t4eq  – meta de mortes em T4-eq
      target_kp           – meta de KP
      deaths_t4eq         – mortes T4-eq do membro
      deaths_pct          – % da meta de mortes atingida
      kp_pct              – % da meta de KP atingida
      deaths_gap          – quanto falta em T4-eq (0 se já bateu)
      kp_gap              – quanto falta em KP (0 se já bateu)
      death_goal_status   – "ok" | "pending" | "below"
      kp_goal_status      – "ok" | "pending" | "below"
      goal_status         – "Aprovado" | "Pendente" | "Abaixo da meta"
    """
    out = metrics.copy()
    if out.empty:
        for col in [
            "power_band", "target_deaths_t4eq", "target_kp",
            "deaths_t4eq", "deaths_pct", "kp_pct",
            "deaths_gap", "kp_gap", "death_goal_status",
            "kp_goal_status", "goal_status",
        ]:
            out[col] = pd.Series(dtype="object")
        return out

    out["power"] = pd.to_numeric(out.get("power", 0), errors="coerce").fillna(0)
    out["kill_points"] = pd.to_numeric(out.get("kill_points", 0), errors="coerce").fillna(0)
    out["t5_deaths"] = pd.to_numeric(out.get("t5_deaths", 0), errors="coerce").fillna(0)
    out["t4_deaths"] = pd.to_numeric(out.get("t4_deaths", 0), errors="coerce").fillna(0)

    bands = out["power"].map(lambda p: _find_band(float(p)))

    out["power_band"] = bands.map(lambda b: b["label"] if b else "—")
    out["target_deaths_t4eq"] = bands.map(lambda b: int(b["target_deaths_t4eq"]) if b else 0)
    out["target_kp"] = bands.map(lambda b: int(b["target_kp"]) if b else 0)

    out["deaths_t4eq"] = out.apply(_deaths_t4eq, axis=1)

    out["deaths_pct"] = out.apply(
        lambda r: min(r["deaths_t4eq"] / r["target_deaths_t4eq"], 1.0) if r["target_deaths_t4eq"] > 0 else 0.0,
        axis=1,
    )
    out["kp_pct"] = out.apply(
        lambda r: min(float(r["kill_points"]) / r["target_kp"], 1.0) if r["target_kp"] > 0 else 0.0,
        axis=1,
    )

    out["deaths_gap"] = (out["target_deaths_t4eq"] - out["deaths_t4eq"]).clip(lower=0).astype("int64")
    out["kp_gap"] = (out["target_kp"] - out["kill_points"]).clip(lower=0).astype("int64")

    out["death_goal_status"] = out.apply(
        lambda r: _death_status(int(r["deaths_t4eq"]), int(r["target_deaths_t4eq"])), axis=1
    )
    out["kp_goal_status"] = out.apply(
        lambda r: _kp_status(float(r["kill_points"]), int(r["target_kp"])), axis=1
    )
    out["goal_status"] = out.apply(
        lambda r: _overall_status(r["death_goal_status"], r["kp_goal_status"]), axis=1
    )

    return out


# ---------------------------------------------------------------------------
# Legado — mantido para não quebrar imports existentes no app.py original
# ---------------------------------------------------------------------------
GOAL_BAND_COLUMNS = ["band_id", "label", "min_power", "max_power", "target_dkpi", "sort_order"]

DEFAULT_GOAL_BANDS = [
    {"band_id": "0_49m",   "label": "≤ 49M",   "min_power": 0,           "max_power": 50_000_000,  "target_dkpi": 0.0, "sort_order": 1},
    {"band_id": "50_59m",  "label": "50M–59M",  "min_power": 50_000_000,  "max_power": 60_000_000,  "target_dkpi": 0.0, "sort_order": 2},
    {"band_id": "60_69m",  "label": "60M–69M",  "min_power": 60_000_000,  "max_power": 70_000_000,  "target_dkpi": 0.0, "sort_order": 3},
    {"band_id": "70_79m",  "label": "70M–79M",  "min_power": 70_000_000,  "max_power": 80_000_000,  "target_dkpi": 0.0, "sort_order": 4},
    {"band_id": "80_89m",  "label": "80M–89M",  "min_power": 80_000_000,  "max_power": 90_000_000,  "target_dkpi": 0.0, "sort_order": 5},
    {"band_id": "90_99m",  "label": "90M–99M",  "min_power": 90_000_000,  "max_power": 100_000_000, "target_dkpi": 0.0, "sort_order": 6},
    {"band_id": "100m_plus","label": "≥ 100M",  "min_power": 100_000_000, "max_power": None,        "target_dkpi": 0.0, "sort_order": 7},
]


def default_goal_bands() -> pd.DataFrame:
    return normalize_goal_bands(pd.DataFrame(DEFAULT_GOAL_BANDS))


def normalize_goal_bands(raw) -> pd.DataFrame:
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


def serialize_goal_bands(raw) -> list[dict[str, Any]]:
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
    """Compat shim — delegates to calculate_member_goals."""
    result = calculate_member_goals(metrics)
    result["combined_points"] = result.get("kill_points", 0)
    result["target_points"] = result.get("target_kp", 0)
    result["progress_pct"] = result.get("kp_pct", 0.0)
    result["gap_to_goal"] = result.get("kp_gap", 0)
    result["over_goal_points"] = (result["kill_points"] - result["target_kp"]).clip(lower=0).astype("int64")
    # map status to old format
    status_map = {"Aprovado": "Met", "Pendente": "In Progress", "Abaixo da meta": "No Points"}
    result["goal_status"] = result["goal_status"].map(status_map).fillna("No Target")
    result["target_dkpi"] = 0.0
    result["power_band"] = result.get("power_band", "—")
    return result


def summarize_goal_bands(goal_progress: pd.DataFrame) -> pd.DataFrame:
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
    grouped["progress_pct"] = grouped.apply(
        lambda r: float(r["combined_points"]) / r["target_points"] if r["target_points"] > 0 else 0.0,
        axis=1,
    )
    return grouped.sort_values("target_points", ascending=False).reset_index(drop=True)
