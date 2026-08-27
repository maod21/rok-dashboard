from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from rok_metrics import OUTPUT_COLUMNS

SQLITE_PATH = Path(os.getenv("ROK_SQLITE_PATH", "data/rok_dashboard.sqlite"))

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
        self._init_schema()

    # --- RELATÓRIOS E ESTATÍSTICAS ---

    def list_imports(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "select id, filename, report_date, imported_at, file_hash, row_count from rok_imports order by report_date desc, imported_at desc",
            self.connection,
        )

    def load_stats(self, import_id: str) -> pd.DataFrame:
        return pd.read_sql_query(
            "select * from rok_stats where import_id = ?",
            self.connection,
            params=(import_id,),
        )

    def save_import(self, *, filename: str, report_date: str, file_hash: str, stats: pd.DataFrame) -> tuple[str, bool]:
        existing = self.connection.execute("select id from rok_imports where file_hash = ?", (file_hash,)).fetchone()
        if existing:
            return str(existing["id"]), False

        import_id = str(uuid.uuid4())
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

    # --- GESTÃO DE KVK (SIMPLIFICADA POR DATAS) ---

    def create_kvk_event(self, name: str, start_date: str, end_date: str) -> str:
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "insert into rok_kvk_events (id, name, start_date, end_date, created_at) values (?, ?, ?, ?, ?)",
                (event_id, name, start_date, end_date, created_at)
            )
        return event_id

    def list_kvk_events(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "select id, name, start_date, end_date, created_at from rok_kvk_events order by start_date desc",
            self.connection,
        )

    def delete_kvk_event(self, event_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute("delete from rok_kvk_events where id = ?", (event_id,))
        return cursor.rowcount > 0

    # --- HALL OF FAME ---
    
    def save_hof_entries(self, entries: list[dict]) -> None:
        with self.connection:
            self.connection.executemany(
                """
                insert into rok_hall_of_fame (id, import_id, kvk_name, category, position, username, character_id, power, value, created_at)
                values (:id, :import_id, :kvk_name, :category, :position, :username, :character_id, :power, :value, :created_at)
                """,
                entries,
            )

    def load_hof(self, import_id: str | None = None) -> pd.DataFrame:
        if import_id:
            return pd.read_sql_query("select * from rok_hall_of_fame where import_id = ? order by position asc", self.connection, params=(import_id,))
        return pd.read_sql_query("select * from rok_hall_of_fame order by created_at desc, position asc", self.connection)

    # --- INICIALIZAÇÃO DE ESQUEMA ---

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
            self.connection.execute("create index if not exists rok_stats_char_idx on rok_stats (character_id)")
            self.connection.execute("create index if not exists rok_imports_date_idx on rok_imports (report_date desc)")
            
            # Tabela de KvK simplificada
            self.connection.execute("""
                create table if not exists rok_kvk_events (
                    id text primary key, name text not null,
                    start_date text not null, end_date text not null, created_at text not null
                )
            """)
            
            self.connection.execute("""
                create table if not exists rok_hall_of_fame (
                    id text primary key, import_id text not null references rok_imports(id) on delete cascade,
                    kvk_name text not null, category text not null, position integer not null, username text not null,
                    character_id text not null, power integer not null, value integer not null, created_at text not null
                )
            """)

    def close(self) -> None:
        self.connection.close()


def create_storage():
    return SQLiteStorage()

def _secret(name: str) -> str | None:
    value = os.getenv(name)
    if value: return value
    try:
        import streamlit as st
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value) if value else None
