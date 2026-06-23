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

    # =================================================================
    # SISTEMA DE IMPORTS (Base para todo o resto)
    # =================================================================

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

    # =================================================================
    # NOVA ARQUITETURA: KvK CAMPAIGNS, REALMS, UPLOADS (SQLite)
    # =================================================================

    def create_campaign(self, name: str, story_type: str, start_date: str, end_date: str) -> str:
        campaign_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "insert into rok_kvk_campaigns (id, name, story_type, start_date, end_date, created_at) values (?, ?, ?, ?, ?, ?)",
                (campaign_id, name, story_type, start_date, end_date, created_at)
            )
        return campaign_id

    def list_campaigns(self) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            select id, name, story_type, start_date, end_date, created_at
            from rok_kvk_campaigns
            order by start_date desc, created_at desc
            """,
            self.connection,
        )

    def get_campaign(self, campaign_id: str) -> dict | None:
        row = self.connection.execute(
            "select id, name, story_type, start_date, end_date, created_at from rok_kvk_campaigns where id = ?",
            (campaign_id,)
        ).fetchone()
        return dict(row) if row else None

    def delete_campaign(self, campaign_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute("delete from rok_kvk_campaigns where id = ?", (campaign_id,))
        return cursor.rowcount > 0

    def add_realm(self, campaign_id: str, camp_name: str, kingdom_name: str) -> str:
        existing = self.connection.execute(
            "select id from rok_kvk_realms where campaign_id = ? and kingdom_name = ?",
            (campaign_id, kingdom_name)
        ).fetchone()
        if existing:
            return str(existing["id"])
        
        realm_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "insert into rok_kvk_realms (id, campaign_id, camp_name, kingdom_name, created_at) values (?, ?, ?, ?, ?)",
                (realm_id, campaign_id, camp_name, kingdom_name, created_at)
            )
            self.connection.execute(
                "insert into rok_kvk_aggregates (id, realm_id) values (?, ?)",
                (str(uuid.uuid4()), realm_id)
            )
        return realm_id

    def remove_realm(self, realm_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute("delete from rok_kvk_realms where id = ?", (realm_id,))
        return cursor.rowcount > 0

    def move_realm(self, realm_id: str, new_camp_name: str) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                "update rok_kvk_realms set camp_name = ? where id = ?",
                (new_camp_name, realm_id)
            )
        return cursor.rowcount > 0

    def list_realms(self, campaign_id: str) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            select 
                r.id, r.camp_name, r.kingdom_name, 
                a.total_kp, a.total_deaths, a.player_count, a.last_upload_at
            from rok_kvk_realms r
            left join rok_kvk_aggregates a on r.id = a.realm_id
            where r.campaign_id = ?
            order by r.camp_name, r.kingdom_name
            """,
            self.connection,
            params=(campaign_id,)
        )

    def get_realm(self, realm_id: str) -> dict | None:
        row = self.connection.execute(
            "select * from rok_kvk_realms where id = ?",
            (realm_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_upload_to_realm(self, realm_id: str, import_id: str, filename: str, report_date: str, 
                            total_kp: int, total_deaths: int, player_count: int) -> str:
        upload_id = str(uuid.uuid4())
        uploaded_at = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                """
                insert into rok_kvk_uploads (id, realm_id, import_id, filename, report_date, uploaded_at,
                                            total_kp, total_deaths, player_count)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (upload_id, realm_id, import_id, filename, report_date, uploaded_at, total_kp, total_deaths, player_count)
            )
            self.connection.execute(
                """
                update rok_kvk_aggregates 
                set total_kp = total_kp + ?, 
                    total_deaths = total_deaths + ?, 
                    player_count = ?, 
                    last_upload_at = ?
                where realm_id = ?
                """,
                (total_kp, total_deaths, player_count, uploaded_at, realm_id)
            )
        return upload_id

    def get_uploads_by_realm(self, realm_id: str) -> pd.DataFrame:
        return pd.read_sql_query(
            """
            select id, import_id, filename, report_date, uploaded_at, total_kp, total_deaths, player_count
            from rok_kvk_uploads
            where realm_id = ?
            order by report_date desc
            """,
            self.connection,
            params=(realm_id,)
        )

    def delete_upload(self, upload_id: str) -> bool:
        upload = self.connection.execute(
            "select realm_id, total_kp, total_deaths from rok_kvk_uploads where id = ?",
            (upload_id,)
        ).fetchone()
        if not upload:
            return False
        
        with self.connection:
            self.connection.execute(
                "update rok_kvk_aggregates set total_kp = total_kp - ?, total_deaths = total_deaths - ? where realm_id = ?",
                (upload["total_kp"], upload["total_deaths"], upload["realm_id"])
            )
            self.connection.execute("delete from rok_kvk_uploads where id = ?", (upload_id,))
        return True

    def get_realm_dashboard(self, realm_id: str) -> dict:
        realm = self.get_realm(realm_id)
        if not realm:
            return {}
        uploads = self.get_uploads_by_realm(realm_id)
        
        return {
            "realm": realm,
            "uploads_count": len(uploads),
            "uploads_data": uploads,
            "metrics": {
                "avg_kp": int(uploads["total_kp"].mean()) if not uploads.empty else 0,
                "avg_deaths": int(uploads["total_deaths"].mean()) if not uploads.empty else 0,
                "kp_growth": int(uploads["total_kp"].max() - uploads["total_kp"].min()) if len(uploads) > 1 else 0,
                "death_growth": int(uploads["total_deaths"].max() - uploads["total_deaths"].min()) if len(uploads) > 1 else 0,
            }
        }

    # =================================================================
    # ADAPTADORES DE COMPATIBILIDADE (SQLite)
    # =================================================================

    def list_kvk_events(self) -> pd.DataFrame:
        return self.list_campaigns()

    def delete_kvk_event(self, kvk_id: str) -> bool:
        return self.delete_campaign(kvk_id)

    def save_kvk_structure(self, name: str, story_type: str, start_date: str, end_date: str, camps: list) -> str:
        campaign_id = self.create_campaign(name, story_type, start_date, end_date)
        for camp in camps:
            if camp.get("kingdom"):
                self.add_realm(campaign_id, camp["name"], camp["kingdom"])
        return campaign_id

    def load_kvk_camps(self, kvk_id: str) -> pd.DataFrame:
        campaign = self.get_campaign(kvk_id)
        if not campaign:
            return pd.DataFrame()
        
        KVK_STORIES = {
            "Heroic Anthem": ["Fire", "Water", "Earth", "Wind"],
            "Heroic Anthem: Power Up": ["Fire", "Water", "Earth", "Wind"],
            "Desert Conquest": ["Fire", "Water", "Earth", "Wind"],
            "Orleans Campaign": ["Fire", "Water", "Earth", "Wind"],
            "Nile": ["Fire", "Water", "Earth", "Wind"],
            "Warriors Unbound": ["Fire", "Water", "Earth", "Wind"],
            "Kingdom of Aurics": ["Aurics", "Glaciers", "Storms", "Embers", "Tides", "Verdure"],
            "Strife of the Eight": ["Dragon", "Tiger", "Lion", "Bear", "Wolf", "Raven", "Lotus", "Viper"],
        }
        
        camps = KVK_STORIES.get(campaign["story_type"], [])
        data = [{"id": f"{kvk_id}||{c}", "camp_name": c} for c in camps]
        return pd.DataFrame(data)

    def load_kingdom_stats(self, camp_id: str) -> pd.DataFrame:
        if "||" not in camp_id: return pd.DataFrame()
        kvk_id, camp_name = camp_id.split("||")
        
        realms_df = self.list_realms(kvk_id)
        if realms_df.empty: return pd.DataFrame()
        
        # Garante contagem de uploads se requisitada pela interface
        if "upload_count" not in realms_df.columns:
            realms_df["upload_count"] = 0
            for idx, row in realms_df.iterrows():
                ups = self.get_uploads_by_realm(row["id"])
                realms_df.at[idx, "upload_count"] = len(ups)

        return realms_df[realms_df["camp_name"] == camp_name].copy()

    def add_empty_kingdom(self, camp_id: str, kingdom_name: str) -> None:
        if "||" not in camp_id: return
        kvk_id, camp_name = camp_id.split("||")
        self.add_realm(kvk_id, camp_name, kingdom_name)

    def save_kingdom_stats(self, kvk_camp_id: str, import_id: str, kingdom_name: str, total_kp: int, total_deaths: int, player_count: int) -> None:
        if "||" not in kvk_camp_id: return
        campaign_id, camp_name = kvk_camp_id.split("||")
        
        realms = self.list_realms(campaign_id)
        realm_id = None
        if not realms.empty:
            matches = realms[(realms["camp_name"] == camp_name) & (realms["kingdom_name"] == str(kingdom_name))]
            if not matches.empty:
                realm_id = matches.iloc[0]["id"]
                
        if not realm_id:
            realm_id = self.add_realm(campaign_id, camp_name, str(kingdom_name))
            
        imports = self.list_imports()
        imp_row = imports[imports["id"] == import_id]
        if imp_row.empty: return
        
        filename = imp_row.iloc[0]["filename"]
        report_date = imp_row.iloc[0]["report_date"]
        
        self.add_upload_to_realm(realm_id, import_id, filename, report_date, total_kp, total_deaths, player_count)

    def delete_kingdom_from_camp(self, camp_id: str, kingdom_name: str) -> None:
        if "||" not in camp_id: return
        campaign_id, camp_name = camp_id.split("||")
        
        realms = self.list_realms(campaign_id)
        if not realms.empty:
            matches = realms[(realms["camp_name"] == camp_name) & (realms["kingdom_name"] == str(kingdom_name))]
            if not matches.empty:
                self.remove_realm(matches.iloc[0]["id"])

    # =================================================================
    # Inicialização do Schema
    # =================================================================

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
                create table if not exists rok_kvk_campaigns (
                    id text primary key, name text not null, story_type text not null,
                    start_date text not null, end_date text not null, created_at text not null
                )
            """)
            self.connection.execute("""
                create table if not exists rok_kvk_realms (
                    id text primary key, campaign_id text not null references rok_kvk_campaigns(id) on delete cascade,
                    camp_name text not null, kingdom_name text not null, created_at text not null
                )
            """)
            self.connection.execute("""
                create table if not exists rok_kvk_aggregates (
                    id text primary key, realm_id text not null references rok_kvk_realms(id) on delete cascade,
                    total_kp integer not null default 0, total_deaths integer not null default 0,
                    player_count integer not null default 0, last_upload_at text
                )
            """)
            self.connection.execute("""
                create table if not exists rok_kvk_uploads (
                    id text primary key, realm_id text not null references rok_kvk_realms(id) on delete cascade,
                    import_id text not null references rok_imports(id) on delete cascade,
                    filename text not null, report_date text not null, uploaded_at text not null,
                    total_kp integer not null, total_deaths integer not null, player_count integer not null
                )
            """)
            self.connection.execute("create index if not exists idx_kvk_realms_campaign on rok_kvk_realms (campaign_id)")
            self.connection.execute("create index if not exists idx_kvk_uploads_realm on rok_kvk_uploads (realm_id)")

    def close(self) -> None:
        self.connection.close()


# =================================================================
# SupabaseStorage (Nuvem)
# =================================================================

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

    def create_campaign(self, name: str, story_type: str, start_date: str, end_date: str) -> str:
        campaign_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_kvk_campaigns").insert({
            "id": campaign_id, "name": name, "story_type": story_type,
            "start_date": start_date, "end_date": end_date, "created_at": created_at
        }).execute()
        return campaign_id

    def list_campaigns(self) -> pd.DataFrame:
        data = self._select_all("rok_kvk_campaigns", "id, name, story_type, start_date, end_date, created_at", order=("start_date", True))
        return pd.DataFrame(data) if data else pd.DataFrame()

    def get_campaign(self, campaign_id: str) -> dict | None:
        data = self.client.table("rok_kvk_campaigns").select("*").eq("id", campaign_id).limit(1).execute().data
        return data[0] if data else None

    def delete_campaign(self, campaign_id: str) -> bool:
        result = self.client.table("rok_kvk_campaigns").delete().eq("id", campaign_id).execute()
        return bool(result.data)

    def add_realm(self, campaign_id: str, camp_name: str, kingdom_name: str) -> str:
        existing = self.client.table("rok_kvk_realms").select("id").eq("campaign_id", campaign_id).eq("kingdom_name", kingdom_name).limit(1).execute().data
        if existing:
            return str(existing[0]["id"])
        
        realm_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_kvk_realms").insert({
            "id": realm_id, "campaign_id": campaign_id,
            "camp_name": camp_name, "kingdom_name": kingdom_name, "created_at": created_at
        }).execute()
        self.client.table("rok_kvk_aggregates").insert({"id": str(uuid.uuid4()), "realm_id": realm_id}).execute()
        return realm_id

    def remove_realm(self, realm_id: str) -> bool:
        result = self.client.table("rok_kvk_realms").delete().eq("id", realm_id).execute()
        return bool(result.data)

    def move_realm(self, realm_id: str, new_camp_name: str) -> bool:
        result = self.client.table("rok_kvk_realms").update({"camp_name": new_camp_name}).eq("id", realm_id).execute()
        return bool(result.data)

    def list_realms(self, campaign_id: str) -> pd.DataFrame:
        data = self.client.table("rok_kvk_realms").select("id, camp_name, kingdom_name").eq("campaign_id", campaign_id).execute().data
        if not data:
            return pd.DataFrame()
        
        realms_list = []
        for realm in data:
            agg = self.client.table("rok_kvk_aggregates").select("total_kp, total_deaths, player_count, last_upload_at").eq("realm_id", realm["id"]).execute().data
            if agg:
                realm.update(agg[0])
            realms_list.append(realm)
        
        return pd.DataFrame(realms_list)

    def get_realm(self, realm_id: str) -> dict | None:
        data = self.client.table("rok_kvk_realms").select("*").eq("id", realm_id).limit(1).execute().data
        return data[0] if data else None

    def add_upload_to_realm(self, realm_id: str, import_id: str, filename: str, report_date: str, 
                            total_kp: int, total_deaths: int, player_count: int) -> str:
        upload_id = str(uuid.uuid4())
        uploaded_at = datetime.now(timezone.utc).isoformat()
        self.client.table("rok_kvk_uploads").insert({
            "id": upload_id, "realm_id": realm_id, "import_id": import_id,
            "filename": filename, "report_date": report_date, "uploaded_at": uploaded_at,
            "total_kp": total_kp, "total_deaths": total_deaths, "player_count": player_count
        }).execute()
        
        agg = self.client.table("rok_kvk_aggregates").select("total_kp, total_deaths").eq("realm_id", realm_id).execute().data
        if agg:
            new_kp = agg[0]["total_kp"] + total_kp
            new_deaths = agg[0]["total_deaths"] + total_deaths
            self.client.table("rok_kvk_aggregates").update({
                "total_kp": new_kp, "total_deaths": new_deaths,
                "player_count": player_count, "last_upload_at": uploaded_at
            }).eq("realm_id", realm_id).execute()
        return upload_id

    def get_uploads_by_realm(self, realm_id: str) -> pd.DataFrame:
        data = self.client.table("rok_kvk_uploads").select("*").eq("realm_id", realm_id).order("report_date", desc=True).execute().data
        return pd.DataFrame(data) if data else pd.DataFrame()

    def delete_upload(self, upload_id: str) -> bool:
        upload = self.client.table("rok_kvk_uploads").select("realm_id, total_kp, total_deaths").eq("id", upload_id).limit(1).execute().data
        if not upload: return False
        
        agg = self.client.table("rok_kvk_aggregates").select("total_kp, total_deaths").eq("realm_id", upload[0]["realm_id"]).execute().data
        if agg:
            self.client.table("rok_kvk_aggregates").update({
                "total_kp": agg[0]["total_kp"] - upload[0]["total_kp"],
                "total_deaths": agg[0]["total_deaths"] - upload[0]["total_deaths"]
            }).eq("realm_id", upload[0]["realm_id"]).execute()
        
        result = self.client.table("rok_kvk_uploads").delete().eq("id", upload_id).execute()
        return bool(result.data)

    def get_realm_dashboard(self, realm_id: str) -> dict:
        realm = self.get_realm(realm_id)
        if not realm: return {}
        uploads = self.get_uploads_by_realm(realm_id)
        
        return {
            "realm": realm,
            "uploads_count": len(uploads),
            "uploads_data": uploads,
            "metrics": {
                "avg_kp": int(uploads["total_kp"].mean()) if not uploads.empty else 0,
                "avg_deaths": int(uploads["total_deaths"].mean()) if not uploads.empty else 0,
                "kp_growth": int(uploads["total_kp"].max() - uploads["total_kp"].min()) if len(uploads) > 1 else 0,
                "death_growth": int(uploads["total_deaths"].max() - uploads["total_deaths"].min()) if len(uploads) > 1 else 0,
            }
        }

    # =================================================================
    # ADAPTADORES DE COMPATIBILIDADE (Supabase)
    # =================================================================

    def list_kvk_events(self) -> pd.DataFrame:
        return self.list_campaigns()

    def delete_kvk_event(self, kvk_id: str) -> bool:
        return self.delete_campaign(kvk_id)

    def save_kvk_structure(self, name: str, story_type: str, start_date: str, end_date: str, camps: list) -> str:
        campaign_id = self.create_campaign(name, story_type, start_date, end_date)
        for camp in camps:
            if camp.get("kingdom"):
                self.add_realm(campaign_id, camp["name"], camp["kingdom"])
        return campaign_id

    def load_kvk_camps(self, kvk_id: str) -> pd.DataFrame:
        campaign = self.get_campaign(kvk_id)
        if not campaign:
            return pd.DataFrame()
        
        KVK_STORIES = {
            "Heroic Anthem": ["Fire", "Water", "Earth", "Wind"],
            "Heroic Anthem: Power Up": ["Fire", "Water", "Earth", "Wind"],
            "Desert Conquest": ["Fire", "Water", "Earth", "Wind"],
            "Orleans Campaign": ["Fire", "Water", "Earth", "Wind"],
            "Nile": ["Fire", "Water", "Earth", "Wind"],
            "Warriors Unbound": ["Fire", "Water", "Earth", "Wind"],
            "Kingdom of Aurics": ["Aurics", "Glaciers", "Storms", "Embers", "Tides", "Verdure"],
            "Strife of the Eight": ["Dragon", "Tiger", "Lion", "Bear", "Wolf", "Raven", "Lotus", "Viper"],
        }
        
        camps = KVK_STORIES.get(campaign["story_type"], [])
        data = [{"id": f"{kvk_id}||{c}", "camp_name": c} for c in camps]
        return pd.DataFrame(data)

    def load_kingdom_stats(self, camp_id: str) -> pd.DataFrame:
        if "||" not in camp_id: return pd.DataFrame()
        kvk_id, camp_name = camp_id.split("||")
        
        realms_df = self.list_realms(kvk_id)
        if realms_df.empty: return pd.DataFrame()
        
        if "upload_count" not in realms_df.columns:
            realms_df["upload_count"] = 0
            for idx, row in realms_df.iterrows():
                ups = self.get_uploads_by_realm(row["id"])
                realms_df.at[idx, "upload_count"] = len(ups)

        return realms_df[realms_df["camp_name"] == camp_name].copy()

    def add_empty_kingdom(self, camp_id: str, kingdom_name: str) -> None:
        if "||" not in camp_id: return
        kvk_id, camp_name = camp_id.split("||")
        self.add_realm(kvk_id, camp_name, kingdom_name)

    def save_kingdom_stats(self, kvk_camp_id: str, import_id: str, kingdom_name: str, total_kp: int, total_deaths: int, player_count: int) -> None:
        if "||" not in kvk_camp_id: return
        campaign_id, camp_name = kvk_camp_id.split("||")
        
        realms = self.list_realms(campaign_id)
        realm_id = None
        if not realms.empty:
            matches = realms[(realms["camp_name"] == camp_name) & (realms["kingdom_name"] == str(kingdom_name))]
            if not matches.empty:
                realm_id = matches.iloc[0]["id"]
                
        if not realm_id:
            realm_id = self.add_realm(campaign_id, camp_name, str(kingdom_name))
            
        imports = self.list_imports()
        imp_row = imports[imports["id"] == import_id]
        if imp_row.empty: return
        
        filename = imp_row.iloc[0]["filename"]
        report_date = imp_row.iloc[0]["report_date"]
        
        self.add_upload_to_realm(realm_id, import_id, filename, report_date, total_kp, total_deaths, player_count)

    def delete_kingdom_from_camp(self, camp_id: str, kingdom_name: str) -> None:
        if "||" not in camp_id: return
        campaign_id, camp_name = camp_id.split("||")
        
        realms = self.list_realms(campaign_id)
        if not realms.empty:
            matches = realms[(realms["camp_name"] == camp_name) & (realms["kingdom_name"] == str(kingdom_name))]
            if not matches.empty:
                self.remove_realm(matches.iloc[0]["id"])

    # =================================================================
    # Utilitários Internos
    # =================================================================

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
