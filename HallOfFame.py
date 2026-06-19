"""
hall_of_fame.py
Arquivamento automático do Top 10 KP + Top 10 Mortes de cada KVK.

Lógica:
  - Acionado sempre que um novo import é salvo com sucesso.
  - Compara o novo import com o anterior (se existir) para calcular
    os deltas do período.
  - Se não houver import anterior, usa os totais absolutos.
  - Grava na tabela rok_hall_of_fame (um registro por posição por import).
  - Nunca sobrescreve entradas já gravadas para o mesmo import_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


# Colunas gravadas por entrada do Hall
HOF_COLUMNS = [
    "id",           # UUID gerado pelo banco ou Python
    "import_id",    # FK → rok_imports.id
    "kvk_name",     # label do KVK (ex: "KVK · 2026-06-10")
    "category",     # "kp" | "deaths"
    "position",     # 1-10
    "username",
    "character_id",
    "power",
    "value",        # kill_points ou dead_equiv
    "created_at",
]

TOP_N = 10


# ─── public API ──────────────────────────────────────────────────────────────

def maybe_archive(
    storage,
    new_import_id: str,
    new_stats: pd.DataFrame,
    prev_stats: pd.DataFrame | None,
    kvk_name: str | None = None,
) -> int:
    """
    Arquiva o Hall da Fama para *new_import_id* se ainda não foi feito.
    Retorna o número de entradas gravadas (0 se já existiam).
    """
    if _already_archived(storage, new_import_id):
        return 0

    # Calcular métricas — delta se houver import anterior, senão absoluto
    from rok_metrics import calculate_metrics, compute_period_deltas
    basis = compute_period_deltas(new_stats, prev_stats) if prev_stats is not None and not prev_stats.empty else new_stats
    metrics = calculate_metrics(basis, group_power=1)   # group_power irrelevante aqui

    # Calcular mortes equivalentes T4
    metrics["dead_equiv"] = (
        metrics.get("t4_deaths", 0) + metrics.get("t5_deaths", 0) * 2
    ).fillna(0).astype(int)

    label = kvk_name or _auto_label(storage, new_import_id)

    entries = _build_entries(metrics, new_import_id, label)
    if not entries:
        return 0

    _save_entries(storage, entries)
    return len(entries)


def load_hall(storage) -> pd.DataFrame:
    """Retorna todas as entradas do Hall da Fama ordenadas por KVK desc + posição asc."""
    return _fetch_all(storage)


def list_kvks(hof: pd.DataFrame) -> list[str]:
    """Retorna os KVKs únicos em ordem decrescente."""
    if hof.empty:
        return []
    return hof["kvk_name"].drop_duplicates().tolist()


# ─── internal ────────────────────────────────────────────────────────────────

def _already_archived(storage, import_id: str) -> bool:
    try:
        existing = _fetch_by_import(storage, import_id)
        return not existing.empty
    except Exception:
        return False


def _auto_label(storage, import_id: str) -> str:
    try:
        imports = storage.list_imports()
        row = imports.loc[imports["id"] == import_id]
        if not row.empty:
            d = str(row.iloc[0]["report_date"])[:10]
            return f"KVK · {d}"
    except Exception:
        pass
    return f"KVK · {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


def _build_entries(
    metrics: pd.DataFrame,
    import_id: str,
    kvk_name: str,
) -> list[dict[str, Any]]:
    import uuid as _uuid

    entries: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    def _top(df: pd.DataFrame, col: str, category: str):
        top = (
            df.sort_values(col, ascending=False)
            .head(TOP_N)
            .reset_index(drop=True)
        )
        for i, row in top.iterrows():
            val = int(row[col])
            if val <= 0:
                continue
            entries.append({
                "id":           str(_uuid.uuid4()),
                "import_id":    import_id,
                "kvk_name":     kvk_name,
                "category":     category,
                "position":     i + 1,
                "username":     str(row.get("username", "")),
                "character_id": str(row.get("character_id", "")),
                "power":        int(row.get("power", 0)),
                "value":        val,
                "created_at":   now,
            })

    _top(metrics, "kill_points", "kp")
    _top(metrics, "dead_equiv",  "deaths")
    return entries


def _save_entries(storage, entries: list[dict[str, Any]]) -> None:
    """Persiste via duck-typed storage (SQLite ou Supabase)."""
    try:
        storage.save_hof_entries(entries)
    except AttributeError:
        # Storage antigo sem o método — ignora silenciosamente
        pass


def _fetch_all(storage) -> pd.DataFrame:
    try:
        return storage.load_hof()
    except AttributeError:
        return pd.DataFrame(columns=HOF_COLUMNS)


def _fetch_by_import(storage, import_id: str) -> pd.DataFrame:
    try:
        return storage.load_hof(import_id=import_id)
    except AttributeError:
        return pd.DataFrame(columns=HOF_COLUMNS)
