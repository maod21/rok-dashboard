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

    # KvK Structure

    def save_kvk_structure(self, *, name: str, story_type: str, start_date: str, end_date: str, camps: list[dict]) -> str:
        kvk_id   = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "insert into rok_kvk_structure (id, name, story_type, start_date, end_date, created_at) values (?, ?, ?, ?, ?, ?)",
                (kvk_id, name, story_type, start_date, end_date, created_at),
            )
            for camp in camps:
                camp_id = str(uuid.uuid4())
                self.connection.execute(
                    "insert into rok_kvk_camps (id, kvk_id, camp_name, kingdom, sort_order) values (?, ?, ?, ?, ?)",
                    (camp_id, kvk_id, camp['name'], camp.get('kingdom', ''), camp['sort_order'])
                )
        return kvk_id

    def list_kvk_structures(self) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            select id, name, story_type, start_date, end_date, created_at
            from rok_kvk_structure
            order by start_date desc, created_at desc
            """,
            self.connection,
        )

    def load_kvk_camps(self, kvk_id: str) -> pd.DataFrame:
        return pd.read_sql_query(
            "select id, camp_name, kingdom, sort_order from rok_kvk_camps where kvk_id = ? order by sort_order",
            self.connection,
            params=(kvk_id,),
        )

    def update_camp_kingdom(self, camp_id: str, kingdom_name: str) -> None:
        with self.connection:
            self.connection.execute(
                "update rok_kvk_camps set kingdom = ? where id = ?",
                (kingdom_name, camp_id),
            )

    # Gerenciamento de Reinos (novo)

    def add_empty_kingdom(self, camp_id: str, kingdom_name: str) -> bool:
        # ve se ja existe
        existing = self.connection.execute(
            "select id from rok_kvk_kingdom_stats where kvk_camp_id = ? and kingdom_name = ?",
            (camp_id, kingdom_name)
        ).fetchone()
        
        if existing:
            return False
        
        stats_id = str(uuid.uuid4())
        uploaded_at = datetime.now(timezone.utc).isoformat()
        
        with self.connection:
            self.connection.execute(
                """
                insert into rok_kvk_kingdom_stats (id, kvk_camp_id, import_id, kingdom_name, total_kp, total_deaths, player_count, uploaded_at)
                values (?, ?, ?, ?, 0, 0, 0, ?)
                """,
                (stats_id, camp_id, "", kingdom_name, uploaded_at),
            )
        return True

    def save_kingdom_stats(self, *, kvk_camp_id: str, import_id: str, kingdom_name: str, total_kp: int, total_deaths: int, player_count: int):
        # salva um upload de stats de reino (acumula historico)
        stats_id = str(uuid.uuid4())
        uploaded_at = datetime.now(timezone.utc).isoformat()
        
        with self.connection:
            self.connection.execute(
                """
                insert into rok_kvk_kingdom_stats (id, kvk_camp_id, import_id, kingdom_name, total_kp, total_deaths, player_count, uploaded_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (stats_id, kvk_camp_id, import_id, kingdom_name, total_kp, total_deaths, player_count, uploaded_at),
            )
        return stats_id

    def get_kingdoms_by_camp(self, camp_id: str) -> pd.DataFrame:
        # retorna reinos do acampamento com stats agregados (soma kp/mortes)
        return pd.read_sql_query(
            """
            select 
                kingdom_name,
                sum(total_kp) as total_kp,
                sum(total_deaths) as total_deaths,
                max(player_count) as player_count,
                max(uploaded_at) as uploaded_at,
                count(*) as total_uploads
            from rok_kvk_kingdom_stats
            where kvk_camp_id = ?
            group by kingdom_name
            order by total_kp desc
            """,
            self.connection,
            params=(camp_id,),
        )

    def get_kingdom_history(self, camp_id: str, kingdom_name: str) -> pd.DataFrame:
        # historico de uploads de um reino especifico
        return pd.read_sql_query(
            """
            select 
                id, import_id, kingdom_name, total_kp, total_deaths, 
                player_count, uploaded_at
            from rok_kvk_kingdom_stats
            where kvk_camp_id = ? and kingdom_name = ?
            order by uploaded_at desc
            """,
            self.connection,
            params=(camp_id, kingdom_name),
        )

    def delete_kingdom_from_camp(self, camp_id: str, kingdom_name: str) -> bool:
        # remove um reino e todos os uploads dele do acampamento
        with self.connection:
            cursor = self.connection.execute(
                "delete from rok_kvk_kingdom_stats where kvk_camp_id = ? and kingdom_name = ?",
                (camp_id, kingdom_name),
            )
        return cursor.rowcount > 0

    def load_kingdom_stats(self, kvk_camp_id: str) -> pd.DataFrame:
        # mantido pra compatibilidade
        return self.get_kingdoms_by_camp(kvk_camp_id)

    def get_all_kingdoms_in_kvk(self, kvk_id: str) -> pd.DataFrame:
        # todos os reinos de todos acampamentos de um kvk
        return pd.read_sql_query(
            """
            select 
                c.camp_name,
                ks.kingdom_name,
                sum(ks.total_kp) as total_kp,
                sum(ks.total_deaths) as total_deaths,
                max(ks.player_count) as player_count,
                max(ks.uploaded_at) as uploaded_at
            from rok_kvk_camps c
            left join rok_kvk_kingdom_stats ks on c.id = ks.kvk_camp_id
            where c.kvk_id = ?
            group by c.camp_name, ks.kingdom_name
            order by c.sort_order, total_kp desc
            """,
            self.connection,
            params=(kvk_id,),
        )

    # KvK Events (Legado)

    def save_kvk_event(self, *, name: str, start_date: str, end_date: str) -> str:
        return self.save_kvk_structure(
            name=name, story_type="Legacy", start_date=start_date, end_date=end_date, camps=[]
        )

    def list_kvk_events(self) -> pd.DataFrame:
        return self.list_kvk_structures()

    def load_kvk_event(self, event_id: str) -> dict | None:
        row = self.connection.execute(
            "select id, name, story_type, start_date, end_date, created_at from rok_kvk_structure where id = ?",
            (event_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_kvk_event(self, event_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute("delete from rok_kvk_structure where id = ?", (event_id,))
        return cursor.rowcount > 0

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
            self.connection.execute("""
                create table if not exists rok_kvk_structure (
                    id text primary key, name text not null, story_type text not null,
                    start_date text not null, end_date text not null, created_at text not null
                )
            """)
            self.connection.execute("""
                create table if not exists rok_kvk_camps (
                    id text primary key, kvk_id text not null references rok_kvk_structure(id) on delete cascade,
                    camp_name text not null, kingdom text, sort_order integer not null
                )
            """)
            self.connection.execute("""
                create table if not exists rok_kvk_kingdom_stats (
                    id text primary key, kvk_camp_id text not null references rok_kvk_camps(id) on delete cascade,
                    import_id text not null references rok_imports(id) on delete cascade,
                    kingdom_name text not null, total_kp integer not null, total_deaths integer not null,
                    player_count integer not null, uploaded_at text not null
                )
            """)
            self.connection.execute("create index if not exists rok_kvk_camps_kvk_idx on rok_kvk_camps (kvk_id)")
            self.connection.execute("create index if not exists rok_kvk_kingdom_stats_camp_idx on rok_kvk_kingdom_stats (kvk_camp_id)")


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

    # KvK Structure (Supabase)

    def save_kvk_structure(self, *, name: str, story_type: str, start_date: str, end_date: str, camps: list[dict]) -> str:
        kvk_id   = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_kvk_structure").insert({
            "id": kvk_id, "name": name, "story_type": story_type,
            "start_date": start_date, "end_date": end_date, "created_at": created_at
        }).execute()

        for camp in camps:
            camp_id = str(uuid.uuid4())
            self.client.table("rok_kvk_camps").insert({
                "id": camp_id, "kvk_id": kvk_id,
                "camp_name": camp['name'], "kingdom": camp.get('kingdom', ''),
                "sort_order": camp['sort_order']
            }).execute()
        return kvk_id

    def list_kvk_structures(self) -> pd.DataFrame:
        data = self._select_all("rok_kvk_structure", "id, name, story_type, start_date, end_date, created_at", order=("start_date", True))
        return pd.DataFrame(data) if data else pd.DataFrame()

    def load_kvk_camps(self, kvk_id: str) -> pd.DataFrame:
        data = self._select_all("rok_kvk_camps", "id, camp_name, kingdom, sort_order", filters={"kvk_id": kvk_id}, order=("sort_order", False))
        return pd.DataFrame(data) if data else pd.DataFrame()

    def update_camp_kingdom(self, camp_id: str, kingdom_name: str) -> None:
        self.client.table("rok_kvk_camps").update({"kingdom": kingdom_name}).eq("id", camp_id).execute()

    # Gerenciamento de Reinos (Supabase)

    def add_empty_kingdom(self, camp_id: str, kingdom_name: str) -> bool:
        existing = self.client.table("rok_kvk_kingdom_stats").select("id").eq("kvk_camp_id", camp_id).eq("kingdom_name", kingdom_name).limit(1).execute().data
        if existing:
            return False
        
        stats_id = str(uuid.uuid4())
        uploaded_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_kvk_kingdom_stats").insert({
            "id": stats_id, "kvk_camp_id": camp_id, "import_id": "",
            "kingdom_name": kingdom_name, "total_kp": 0, "total_deaths": 0,
            "player_count": 0, "uploaded_at": uploaded_at
        }).execute()
        return True

    def save_kingdom_stats(self, *, kvk_camp_id: str, import_id: str, kingdom_name: str, total_kp: int, total_deaths: int, player_count: int):
        stats_id = str(uuid.uuid4())
        uploaded_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_kvk_kingdom_stats").insert({
            "id": stats_id, "kvk_camp_id": kvk_camp_id, "import_id": import_id,
            "kingdom_name": kingdom_name, "total_kp": total_kp,
            "total_deaths": total_deaths, "player_count": player_count,
            "uploaded_at": uploaded_at
        }).execute()
        return stats_id

    def get_kingdoms_by_camp(self, camp_id: str) -> pd.DataFrame:
        data = self._select_all("rok_kvk_kingdom_stats", "kingdom_name, total_kp, total_deaths, player_count, uploaded_at", filters={"kvk_camp_id": camp_id}, order=("total_kp", True))
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        # agrupa igual sqlite
        if not df.empty:
            df = df.groupby('kingdom_name').agg({
                'total_kp': 'sum', 'total_deaths': 'sum',
                'player_count': 'max', 'uploaded_at': 'max'
            }).reset_index()
            df['total_uploads'] = 1  # simplificado
            df = df.sort_values('total_kp', ascending=False)
        return df

    def get_kingdom_history(self, camp_id: str, kingdom_name: str) -> pd.DataFrame:
        data = self._select_all("rok_kvk_kingdom_stats", "*", filters={"kvk_camp_id": camp_id, "kingdom_name": kingdom_name}, order=("uploaded_at", True))
        return pd.DataFrame(data) if data else pd.DataFrame()

    def delete_kingdom_from_camp(self, camp_id: str, kingdom_name: str) -> bool:
        result = self.client.table("rok_kvk_kingdom_stats").delete().eq("kvk_camp_id", camp_id).eq("kingdom_name", kingdom_name).execute()
        return bool(result.data)

    def load_kingdom_stats(self, kvk_camp_id: str) -> pd.DataFrame:
        return self.get_kingdoms_by_camp(kvk_camp_id)

    def get_all_kingdoms_in_kvk(self, kvk_id: str) -> pd.DataFrame:
        camps_data = self._select_all("rok_kvk_camps", "id, camp_name", filters={"kvk_id": kvk_id})
        if not camps_data:
            return pd.DataFrame()
        
        all_kingdoms = []
        for camp in camps_data:
            kingdoms = self.get_kingdoms_by_camp(camp['id'])
            if not kingdoms.empty:
                kingdoms['camp_name'] = camp['camp_name']
                all_kingdoms.append(kingdoms)
        
        if not all_kingdoms:
            return pd.DataFrame()
        return pd.concat(all_kingdoms, ignore_index=True)

    # KvK Events (Legacy)

    def save_kvk_event(self, *, name: str, start_date: str, end_date: str) -> str:
        return self.save_kvk_structure(name=name, story_type="Legacy", start_date=start_date, end_date=end_date, camps=[])

    def list_kvk_events(self) -> pd.DataFrame:
        return self.list_kvk_structures()

    def load_kvk_event(self, event_id: str) -> dict | None:
        data = self.client.table("rok_kvk_structure").select("*").eq("id", event_id).limit(1).execute().data
        return data[0] if data else None

    def delete_kvk_event(self, event_id: str) -> bool:
        result = self.client.table("rok_kvk_structure").delete().eq("id", event_id).execute()
        return bool(result.data)

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
