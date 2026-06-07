"""
member_goals.py
Lógica de metas por City Power para o RoK KP Dashboard.

Regras:
  - Meta de KP: baseada nos Kill Points calculados
  - Meta de mortes: T4 ou T5, com equivalência 1 T5 = 2 T4
  - Status: Aprovado / Pendente (perto) / Abaixo da meta
"""
from __future__ import annotations
import pandas as pd

# ── Tabela de metas ─────────────────────────────────────────────────────────
# Cada entrada: (power_min, power_max, dead_t4_goal, dead_t5_goal, kp_goal)
# dead_t4_goal = meta em T4 equivalente (base de comparação)
# dead_t5_goal = meta em T5 equivalente
# A lógica: (t5_deaths * 2 + t4_deaths) >= dead_t4_goal

GOAL_TABLE = [
    # (min_power_incl, max_power_incl, dead_t4, dead_t5, kp)
    (0,          49_999_999,  900_000,   450_000,   80_000_000),
    (50_000_000, 59_999_999,  900_000,   450_000,  100_000_000),
    (60_000_000, 69_999_999, 1_000_000,  500_000,  140_000_000),
    (70_000_000, 79_999_999, 1_400_000,  700_000,  180_000_000),
    (80_000_000, 89_999_999, 1_600_000,  800_000,  200_000_000),
    (90_000_000, 99_999_999, 2_000_000, 1_000_000, 280_000_000),
    (100_000_000, float("inf"), 2_000_000, 1_000_000, 320_000_000),
]

# Limiar para "Pendente": atingiu N% da meta
PENDING_THRESHOLD = 0.75  # 75%


def get_goals(power: int) -> dict:
    """Retorna as metas para um determinado City Power."""
    for pmin, pmax, dead_t4, dead_t5, kp in GOAL_TABLE:
        if pmin <= power <= pmax:
            return {
                "dead_t4_goal": dead_t4,
                "dead_t5_goal": dead_t5,
                "kp_goal":      kp,
                "power_band":   _power_label(pmin, pmax),
            }
    # fallback (não deve acontecer)
    return {"dead_t4_goal": 0, "dead_t5_goal": 0, "kp_goal": 0, "power_band": "—"}


def _power_label(pmin: int, pmax) -> str:
    if pmax == float("inf"):
        return f"{pmin // 1_000_000}M+"
    return f"{pmin // 1_000_000}M–{(pmax + 1) // 1_000_000}M"


def calculate_dead_equivalent(t4_deaths: int, t5_deaths: int) -> int:
    """Converte mortes T4 e T5 para equivalente T4 (1 T5 = 2 T4)."""
    return int(t4_deaths + t5_deaths * 2)


def classify_member(row: pd.Series) -> pd.Series:
    """
    Dado um row com colunas de kills/deaths, retorna métricas de meta.
    """
    power = int(row.get("power", 0))
    goals = get_goals(power)

    kp_goal      = goals["kp_goal"]
    dead_t4_goal = goals["dead_t4_goal"]
    dead_t5_goal = goals["dead_t5_goal"]

    # Kill Points (já calculados)
    kp_actual = float(row.get("kill_points", 0))

    # Mortes equivalentes em T4
    t4_d = int(row.get("t4_deaths", 0))
    t5_d = int(row.get("t5_deaths", 0))
    dead_equiv = calculate_dead_equivalent(t4_d, t5_d)

    # Progresso
    kp_pct   = kp_actual / kp_goal   if kp_goal   > 0 else 1.0
    dead_pct = dead_equiv / dead_t4_goal if dead_t4_goal > 0 else 1.0

    kp_ok   = kp_actual  >= kp_goal
    dead_ok = dead_equiv >= dead_t4_goal

    # Status
    if kp_ok and dead_ok:
        status     = "Aprovado"
        status_key = "approved"
    elif kp_pct >= PENDING_THRESHOLD and dead_pct >= PENDING_THRESHOLD:
        status     = "Pendente"
        status_key = "pending"
    else:
        status     = "Abaixo da meta"
        status_key = "below"

    # Gap (quanto falta)
    kp_gap   = max(0, kp_goal   - kp_actual)
    dead_gap = max(0, dead_t4_goal - dead_equiv)   # em equivalente T4

    return pd.Series({
        "power_band":    goals["power_band"],
        "kp_goal":       kp_goal,
        "dead_t4_goal":  dead_t4_goal,
        "dead_t5_goal":  dead_t5_goal,
        "dead_equiv":    dead_equiv,
        "kp_pct":        min(kp_pct,   1.0),
        "dead_pct":      min(dead_pct, 1.0),
        "kp_ok":         kp_ok,
        "dead_ok":       dead_ok,
        "status":        status,
        "status_key":    status_key,
        "kp_gap":        kp_gap,
        "dead_gap_t4":   dead_gap,
        "dead_gap_t5":   max(0, dead_t5_goal - t5_d),
    })


def apply_goals(metrics: pd.DataFrame) -> pd.DataFrame:
    """Aplica classify_member a cada linha e retorna DataFrame enriquecido."""
    if metrics.empty:
        return metrics
    goal_cols = metrics.apply(classify_member, axis=1)
    return pd.concat([metrics.reset_index(drop=True), goal_cols.reset_index(drop=True)], axis=1)
