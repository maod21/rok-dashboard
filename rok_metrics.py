from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import BinaryIO

import pandas as pd


COLUMN_RENAMES = {
    "Character ID":      "character_id",
    "Username":          "username",
    "Power":             "power",
    "Highest Power":     "highest_power",
    "T5 Deaths":         "t5_deaths",
    "T4 Deaths":         "t4_deaths",
    "T3 Deaths":         "t3_deaths",
    "T2 Deaths":         "t2_deaths",
    "T1 Deaths":         "t1_deaths",
    "Total Kill Points": "total_kill_points",
    "T5 Kills":          "t5_kills",
    "T4 Kills":          "t4_kills",
    "T3 Kills":          "t3_kills",
    "T2 Kills":          "t2_kills",
    "T1 Kills":          "t1_kills",
    "Resources Gathered": "resources_gathered",
}

OUTPUT_COLUMNS = list(COLUMN_RENAMES.values())

NUMERIC_COLUMNS = [
    "power", "highest_power",
    "t5_deaths", "t4_deaths", "t3_deaths", "t2_deaths", "t1_deaths",
    "total_kill_points",
    "t5_kills", "t4_kills", "t3_kills", "t2_kills", "t1_kills",
    "resources_gathered",
]

CUMULATIVE_COLUMNS = [
    "t5_deaths", "t4_deaths", "t3_deaths", "t2_deaths", "t1_deaths",
    "total_kill_points",
    "t5_kills", "t4_kills", "t3_kills", "t2_kills", "t1_kills",
    "resources_gathered",
]

# Default scoring weights.
# T3 kills/deaths are 0 by default; alliance leaders can enable them
# without changing the schema by passing a custom `weights` dict.
POINT_WEIGHTS: dict[str, int] = {
    "t4_kills":   5,
    "t5_kills":   10,
    "t3_deaths":  0,   # set to e.g. 10 to enable T3 deaths
    "t4_deaths":  30,
    "t5_deaths":  70,
}

# Maximum file size accepted (bytes) — guards against accidental huge uploads
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def file_sha256(file_bytes: bytes) -> str:
    """Return the SHA-256 hex digest of *file_bytes*."""
    return hashlib.sha256(file_bytes).hexdigest()


def extract_report_date_from_name(filename: str) -> date | None:
    """Try to parse a YYYYMMDD date from *filename*.

    Returns the last valid date found, or ``None`` if no date is present.
    """
    matches = re.findall(r"(20\d{2})(\d{2})(\d{2})", filename)
    for year, month, day in reversed(matches):
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


def load_stats_file(source: str | Path | BinaryIO, filename: str | None = None) -> pd.DataFrame:
    """Read an Excel stats export and return a normalised DataFrame.

    Raises ``ValueError`` for oversized or unreadable files.
    """
    suffix = Path(filename or str(source)).suffix.lower()
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    try:
        raw = pd.read_excel(source, dtype=object, engine=engine)
    except Exception as exc:
        raise ValueError(f"Não foi possível ler o arquivo Excel: {exc}") from exc
    return normalize_stats(raw)


def normalize_stats(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise a raw stats DataFrame.

    Raises ``ValueError`` if required columns are missing or no valid players
    are found.
    """
    if raw.empty:
        raise ValueError("O arquivo enviado não tem nenhuma linha.")

    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    lookup = {_clean_header(c): c for c in df.columns}
    rename_map: dict[str, str] = {}
    missing: list[str] = []

    for expected, canonical in COLUMN_RENAMES.items():
        existing = lookup.get(_clean_header(expected))
        if existing is None:
            missing.append(expected)
        else:
            rename_map[existing] = canonical

    if missing:
        raise ValueError(f"Colunas obrigatórias não encontradas: {', '.join(missing)}")

    df = df.rename(columns=rename_map)[OUTPUT_COLUMNS].copy()
    df["character_id"] = df["character_id"].map(_clean_identifier)
    df["username"] = df["username"].fillna("").astype(str).str.strip()

    for col in NUMERIC_COLUMNS:
        df[col] = df[col].map(_parse_integer).astype("int64")

    df = df[df["character_id"].ne("")]
    if df.empty:
        raise ValueError("Nenhum jogador válido foi encontrado no arquivo.")

    # Deduplicate: keep the row with the highest power for each character_id
    df = (
        df.sort_values("power", ascending=False)
        .drop_duplicates(subset="character_id", keep="first")
    )

    return df.reset_index(drop=True)


def compute_period_deltas(current: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    """Return *current* with cumulative columns replaced by the delta vs *previous*.

    Players absent in *previous* are treated as having zero prior values.
    All deltas are clipped at zero (negative drift is clamped to 0).
    """
    if previous is None or previous.empty:
        return current.copy()

    prev_index = (
        previous.drop_duplicates("character_id", keep="last")
        .set_index("character_id")[CUMULATIVE_COLUMNS]
    )
    output = current.copy()

    for col in CUMULATIVE_COLUMNS:
        prev_values = output["character_id"].map(prev_index[col]).fillna(0).astype("int64")
        output[col] = (output[col] - prev_values).clip(lower=0)

    return output


def calculate_metrics(
    stats: pd.DataFrame,
    group_power: int | float | None = None,
    weights: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Compute kill/death/combined points and DKPi variants.

    Parameters
    ----------
    stats:
        Normalised player stats (output of :func:`normalize_stats`).
    group_power:
        Override for the group's initial power used to calculate DKPi.
        If ``None`` or 0, the current sum of player powers is used.
    weights:
        Custom point weights per column.  Defaults to :data:`POINT_WEIGHTS`.
    """
    w      = {**POINT_WEIGHTS, **(weights or {})}
    output = stats.copy()

    for col in NUMERIC_COLUMNS:
        if col not in output:
            output[col] = 0
        output[col] = pd.to_numeric(output[col], errors="coerce").fillna(0)

    kill_components  = {col: pts for col, pts in w.items() if col.endswith("_kills")  and pts > 0}
    death_components = {col: pts for col, pts in w.items() if col.endswith("_deaths") and pts > 0}

    output["kill_points"] = sum(
        output.get(col, 0) * pts for col, pts in kill_components.items()
    )
    output["death_points"] = sum(
        output.get(col, 0) * pts for col, pts in death_components.items()
    )
    output["combined_points"] = output["kill_points"] + output["death_points"]

    resolved_group_power = float(group_power or output["power"].sum() or 0)
    output["dkpi"] = (
        output["combined_points"] / resolved_group_power if resolved_group_power > 0 else 0.0
    )

    output["personal_dkpi"] = (
        output["combined_points"] / output["power"].replace(0, pd.NA)
    ).fillna(0.0)

    output["kill_share"]     = _safe_share(output["kill_points"])
    output["death_share"]    = _safe_share(output["death_points"])
    output["combined_share"] = _safe_share(output["combined_points"])

    return output.sort_values("combined_points", ascending=False).reset_index(drop=True)


def add_rank(stats: pd.DataFrame, column: str) -> pd.DataFrame:
    """Return *stats* sorted descending by *column* with a leading ``rank`` column."""
    output = stats.sort_values(column, ascending=False).reset_index(drop=True).copy()
    output.insert(0, "rank", range(1, len(output) + 1))
    return output


def active_weights() -> dict[str, int]:
    """Return only the weight entries with a positive value."""
    return {k: v for k, v in POINT_WEIGHTS.items() if v > 0}


def kingdom_summary(metrics: pd.DataFrame, group_power: int) -> dict:
    """Return a dict with top-level kingdom KPIs for quick display."""
    total_combined = int(metrics["combined_points"].sum())
    return {
        "players":         len(metrics),
        "active_players":  int((metrics["combined_points"] > 0).sum()),
        "kill_points":     int(metrics["kill_points"].sum()),
        "death_points":    int(metrics["death_points"].sum()),
        "combined_points": total_combined,
        "group_dkpi":      total_combined / group_power if group_power else 0.0,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _clean_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _clean_identifier(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return re.sub(r"\.0$", "", text)


def _parse_integer(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(round(value))
    text = str(value).strip()
    if not text:
        return 0
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"[^\d-]", "", text)
    if text in {"", "-"}:
        return 0
    return int(text)


def _safe_share(series: pd.Series) -> pd.Series:
    total = float(series.sum())
    if total <= 0:
        return pd.Series([0.0] * len(series), index=series.index)
    return series / total
