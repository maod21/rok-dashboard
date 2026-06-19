from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from goal_metrics import default_goal_bands, normalize_goal_bands, serialize_goal_bands
from rok_metrics import OUTPUT_COLUMNS


SQLITE_PATH = Path(os.getenv("ROK_SQLITE_PATH", "data/rok_dashboard.sqlite"))
STATS_TABLE_COLUMNS = ["import_id", *OUTPUT_COLUMNS]

SUPABASE_BATCH_SIZE = 500


class SQLiteStorage:
    label = "SQLite local"

    def __init__(self, path: Path = SQLITE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("pragma journal_mode=wal")
        self.connection.execute("pragma synchronous=normal")
        self.connection.execute("pragma foreign_keys=on")
        self.connection.execute("pragma cache_size=-8000")
        self.connection.execute("pragma temp_store=memory")
        self._init_schema()

    def list_imports(self) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            select id, filename, report_date, imported_at, file_hash, row_count
            from rok_imports
            order by report_date desc, imported_at desc
            """,
            self.connection,
        )

    def load_stats(self, import_id: str) -> pd.DataFrame:
        return pd.read_sql_query(
            "select * from rok_stats where import_id = ?",
            self.connection,
            params=(import_id,),
        )

    def save_import(self, *, filename, report_date, file_hash, stats):
        existing = self.connection.execute(
            "select id from rok_imports where file_hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            return str(existing["id"]), False

        import_id   = str(uuid.uuid4())
        imported_at = datetime.now(timezone.utc).isoformat()

        with self.connection:
            self.connection.execute(
                "insert into rok_imports (id, filename, report_date, imported_at, file_hash, row_count) values (?, ?, ?, ?, ?, ?)",
                (import_id, filename, report_date, imported_at, file_hash, len(stats)),
            )
            payload = stats[OUTPUT_COLUMNS].copy()
            payload.insert(0, "import_id", import_id)
            payload.to_sql("rok_stats", self.connection, if_exists="append", index=False)

        return import_id, True

    def delete_import(self, import_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute("delete from rok_imports where id = ?", (import_id,))
        return cursor.rowcount > 0

    def load_goal_bands(self) -> pd.DataFrame:
        bands = pd.read_sql_query(
            "select band_id, label, min_power, max_power, target_dkpi, sort_order from rok_goal_bands order by sort_order, min_power",
            self.connection,
        )
        if bands.empty:
            self.reset_goal_bands()
            bands = pd.read_sql_query(
                "select band_id, label, min_power, max_power, target_dkpi, sort_order from rok_goal_bands order by sort_order, min_power",
                self.connection,
            )
        return normalize_goal_bands(bands)

    def save_goal_bands(self, bands: pd.DataFrame) -> None:
        records = serialize_goal_bands(bands)
        with self.connection:
            self.connection.execute("delete from rok_goal_bands")
            self.connection.executemany(
                "insert into rok_goal_bands (band_id, label, min_power, max_power, target_dkpi, sort_order) values (:band_id, :label, :min_power, :max_power, :target_dkpi, :sort_order)",
                records,
            )

    def reset_goal_bands(self) -> None:
        self.save_goal_bands(default_goal_bands())

    def aggregate_imports(self) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            select i.id, i.report_date, i.filename,
                count(s.character_id) as players,
                coalesce(sum(s.t5_kills * 10 + s.t4_kills * 5), 0) as kill_points,
                coalesce(sum(s.t5_deaths * 70 + s.t4_deaths * 30), 0) as death_points
            from rok_imports i
            left join rok_stats s on s.import_id = i.id
            group by i.id, i.report_date, i.filename
            order by i.report_date asc, i.imported_at asc
            """,
            self.connection,
        )

    # ── Hall of Fame ──────────────────────────────────────────────────

    def save_hof_entries(self, entries: list) -> None:
        with self.connection:
            self.connection.executemany(
                """
                insert or ignore into rok_hall_of_fame
                    (id, import_id, kvk_name, category, position,
                     username, character_id, power, value, created_at)
                values
                    (:id, :import_id, :kvk_name, :category, :position,
                     :username, :character_id, :power, :value, :created_at)
                """,
                entries,
            )

    def load_hof(self, import_id: str | None = None) -> "pd.DataFrame":
        import pandas as pd
        if import_id:
            return pd.read_sql_query(
                "select * from rok_hall_of_fame where import_id = ? order by category, position",
                self.connection, params=(import_id,),
            )
        return pd.read_sql_query(
            """
            select * from rok_hall_of_fame
            order by
                created_at desc,
                kvk_name   desc,
                category   asc,
                position   asc
            """,
            self.connection,
        )

    def close(self) -> None:
        self.connection.close()

    def _init_schema(self) -> None:
        with self.connection:
            self.connection.execute("""
                create table if not exists rok_imports (
                    id text primary key, filename text not null, report_date text not null,
                    imported_at text not null, file_hash text not null unique, row_count integer not null
                )
            """)
            self.connection.execute("""
                create table if not exists rok_stats (
                    import_id text not null, character_id text not null, username text not null,
                    power integer not null, highest_power integer not null,
                    t5_deaths integer not null, t4_deaths integer not null, t3_deaths integer not null,
                    t2_deaths integer not null, t1_deaths integer not null, total_kill_points integer not null,
                    t5_kills integer not null, t4_kills integer not null, t3_kills integer not null,
                    t2_kills integer not null, t1_kills integer not null, resources_gathered integer not null,
                    primary key (import_id, character_id),
                    foreign key (import_id) references rok_imports(id) on delete cascade
                )
            """)
            self.connection.execute("create index if not exists rok_stats_character_idx on rok_stats (character_id)")
            self.connection.execute("create index if not exists rok_imports_date_idx on rok_imports (report_date desc)")
            self.connection.execute("""
                create table if not exists rok_goal_bands (
                    band_id text primary key, label text not null, min_power integer not null,
                    max_power integer, target_dkpi real not null, sort_order integer not null
                )
            """)


class SupabaseStorage:
    label = "Supabase online"

    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client
        self.client = create_client(url, key)
        self._url = url
        self._key = key

    def list_imports(self) -> pd.DataFrame:
        data = self._select_all("rok_imports", "id, filename, report_date, imported_at, file_hash, row_count", order=("report_date", True))
        return _ensure_import_columns(pd.DataFrame(data))

    def load_stats(self, import_id: str) -> pd.DataFrame:
        data = self._select_all("rok_stats", "*", filters={"import_id": import_id})
        return _ensure_stat_columns(pd.DataFrame(data))

    def save_import(self, *, filename, report_date, file_hash, stats):
        existing = self.client.table("rok_imports").select("id").eq("file_hash", file_hash).limit(1).execute().data
        if existing:
            return str(existing[0]["id"]), False

        import_id   = str(uuid.uuid4())
        imported_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_imports").insert({
            "id": import_id, "filename": filename, "report_date": report_date,
            "imported_at": imported_at, "file_hash": file_hash, "row_count": len(stats),
        }).execute()

        payload = stats[OUTPUT_COLUMNS].copy()
        payload.insert(0, "import_id", import_id)
        records = json.loads(payload.to_json(orient="records"))
        for start in range(0, len(records), SUPABASE_BATCH_SIZE):
            self.client.table("rok_stats").insert(records[start: start + SUPABASE_BATCH_SIZE]).execute()

        return import_id, True

    def delete_import(self, import_id: str) -> bool:
        result = self.client.table("rok_imports").delete().eq("id", import_id).execute()
        return bool(result.data)

    def load_goal_bands(self) -> pd.DataFrame:
        data = self._select_all("rok_goal_bands", "band_id, label, min_power, max_power, target_dkpi, sort_order", order=("sort_order", False))
        if not data:
            self.reset_goal_bands()
            data = self._select_all("rok_goal_bands", "band_id, label, min_power, max_power, target_dkpi, sort_order", order=("sort_order", False))
        return normalize_goal_bands(_ensure_goal_band_columns(pd.DataFrame(data)))

    def save_goal_bands(self, bands: pd.DataFrame) -> None:
        records = serialize_goal_bands(bands)
        self.client.table("rok_goal_bands").delete().neq("band_id", "").execute()
        if records:
            self.client.table("rok_goal_bands").insert(records).execute()

    def reset_goal_bands(self) -> None:
        self.save_goal_bands(default_goal_bands())

    # ── Hall of Fame ──────────────────────────────────────────────────

    def save_hof_entries(self, entries: list) -> None:
        import json as _json
        for start in range(0, len(entries), 500):
            self.client.table("rok_hall_of_fame").upsert(
                entries[start: start + 500], on_conflict="id"
            ).execute()

    def load_hof(self, import_id: str | None = None) -> "pd.DataFrame":
        import pandas as pd
        filters = {"import_id": import_id} if import_id else None
        data = self._select_all(
            "rok_hall_of_fame", "*",
            filters=filters,
            order=("created_at", True),
        )
        if not data:
            from hall_of_fame import HOF_COLUMNS
            return pd.DataFrame(columns=HOF_COLUMNS)
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values(["kvk_name","category","position"],
                                ascending=[False, True, True]).reset_index(drop=True)
        return df

    def _select_all(self, table, columns, *, filters=None, order=None):
        rows  = []
        start = 0
        step  = 1000

        while True:
            query = self.client.table(table).select(columns)
            for key, value in (filters or {}).items():
                query = query.eq(key, value)
            if order:
                col, desc = order
                query = query.order(col, desc=desc)

            try:
                response = query.range(start, start + step - 1).execute()
            except Exception:
                try:
                    response = query.execute()
                except Exception:
                    return rows

            batch = getattr(response, "data", None) or []
            rows.extend(batch)
            if len(batch) < step:
                return rows
            start += step


def create_storage():
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_KEY")
    if url and key:
        return SupabaseStorage(url, key)
    return SQLiteStorage()


def _secret(name: str):
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value) if value else None


def _ensure_import_columns(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["id", "filename", "report_date", "imported_at", "file_hash", "row_count"]
    for col in columns:
        if col not in frame:
            frame[col] = pd.Series(dtype="object")
    return frame[columns]


def _ensure_stat_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for col in STATS_TABLE_COLUMNS:
        if col not in frame:
            frame[col] = 0 if col not in {"import_id", "character_id", "username"} else ""
    return frame[STATS_TABLE_COLUMNS]


def _ensure_goal_band_columns(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["band_id", "label", "min_power", "max_power", "target_dkpi", "sort_order"]
    for col in columns:
        if col not in frame:
            frame[col] = pd.Series(dtype="object")
    return frame[columns]
