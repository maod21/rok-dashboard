from __future__ import annotations
import os, re
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from member_goals import apply_goals, GOAL_TABLE
from rok_metrics import (
    POINT_WEIGHTS, add_rank, calculate_metrics, compute_period_deltas,
    extract_report_date_from_name, file_sha256, load_stats_file,
)
from security import is_admin_authenticated
from hall_of_fame import load_hall, list_kvks, maybe_archive
from storage import create_storage

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:
    px = None; go = None

KVK_STORIES = {
    "Heroic Anthem": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Desert Conquest": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Orleans Campaign": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Nile": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Warriors Unbound": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Kingdom of Aurics": {"camps": ["Aurics", "Glaciers", "Storms", "Embers", "Tides", "Verdure"]},
    "Strife of the Eight": {"camps": ["Dragon", "Tiger", "Lion", "Bear", "Wolf", "Raven", "Lotus", "Viper"]},
}

st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_resource
def _css() -> str:
    bg_main        = "#0e1a2b"
    bg_surface     = "#162233"
    bg_surface_alt = "#1c2a3f"
    border_color   = "#2a3f5e"
    text_main      = "#f0f4fa"
    text_sub       = "#9ab0cc"
    text_muted     = "#5a7294"
    gold           = "#d4a847"
    gold_hi        = "#e6c268"
    blue_accent    = "#4a7cba"
    green_ok       = "#3ba37a"
    yellow_pend    = "#d4a03a"
    red_alert      = "#c95a4e"
    sb_bg          = "#0a131f"
    sb_text        = "#8398b5"
    t5_color       = gold
    t4_color       = "#cf6f3a"
    t3_color       = "#7d5eb8"
    t2_color       = "#3f93a6"
    t1_color       = text_muted

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body, [class*="css"], .stApp {{
  font-family: 'Inter', system-ui, sans-serif !important;
  background: {bg_main} !important;
  color: {text_main} !important;
}}
.main .block-container {{ padding: 1.2rem 2rem 3rem !important; max-width: 1500px !important; background:{bg_main} !important; }}

section[data-testid="stSidebar"] {{ background: {sb_bg} !important; border-right: 1px solid {border_color} !important; }}
section[data-testid="stSidebar"] > div {{ padding: 1.5rem 1rem !important; }}
section[data-testid="stSidebar"] * {{ color: {sb_text} !important; }}
section[data-testid="stSidebar"] .stSuccess p {{ color: {green_ok} !important; }}
section[data-testid="stSidebar"] .stError p {{ color: {red_alert} !important; }}
section[data-testid="stSidebar"] .stWarning p {{ color: {yellow_pend} !important; }}
.sb-sec {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .14em; color: {sb_text}; border-bottom: 1px solid {border_color}; padding-bottom: 6px; margin: 14px 0 10px; }}

[data-testid="stMetric"] {{
  background: {bg_surface} !important; border: 1px solid {border_color} !important;
  border-radius: 8px !important; padding: 16px 20px !important;
  position: relative; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}}
[data-testid="stMetric"]::after {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background:{blue_accent}; }}
[data-testid="stMetricLabel"] {{ font-size:.62rem !important; font-weight:600 !important; text-transform:uppercase; letter-spacing:.08em; color:{text_sub} !important; }}
[data-testid="stMetricValue"] {{ font-family:'JetBrains Mono',monospace !important; font-size:1.6rem !important; font-weight:600 !important; color:{text_main} !important; letter-spacing:-.03em; }}

[data-testid="stTabs"] [role="tablist"] {{ border-bottom: 1px solid {border_color}; gap: 0; background: transparent; flex-wrap: wrap; }}
[data-testid="stTabs"] button[role="tab"] {{
  font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em;
  color: {text_muted} !important; padding: 10px 20px; border-bottom: 2px solid transparent;
  border-radius: 0; background: transparent !important; transition: color .2s, border-color .2s;
}}
[data-testid="stTabs"] button[role="tab"]:hover {{ color: {gold} !important; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ color: {gold} !important; border-bottom-color: {gold} !important; background: transparent !important; }}

[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input {{
  background: {bg_surface_alt} !important; border: 1px solid {border_color} !important; border-radius: 6px !important;
  color: {text_main} !important; font-family: 'Inter', sans-serif !important; font-size: .82rem !important;
}}
[data-testid="stTextInput"] input::placeholder {{ color: {text_muted} !important; }}
[data-testid="stTextInput"] input:focus, [data-testid="stSelectbox"] > div > div:focus-within {{
  border-color: {blue_accent} !important; box-shadow: 0 0 0 2px rgba(74, 124, 186, 0.2) !important;
}}

[data-testid="stButton"] button {{
  background: {blue_accent} !important; color: #fff !important; border: none !important; border-radius: 6px !important;
  font-weight: 700 !important; font-size: .78rem !important; text-transform: uppercase; letter-spacing: .08em;
  transition: all .2s; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}}
[data-testid="stButton"] button:hover {{ background: {gold} !important; transform: translateY(-1px); color: #000 !important; }}
[data-testid="stButton"] button[kind="secondary"] {{ background: transparent !important; border: 1px solid {border_color} !important; color: {text_sub} !important; }}

[data-testid="stDataFrame"] {{ border: 1px solid {border_color} !important; border-radius: 8px !important; overflow: hidden; background: {bg_surface}; }}
[data-testid="stDataFrame"] th {{ background: {bg_surface_alt} !important; color: {text_sub} !important; }}
[data-testid="stDataFrame"] td {{ color: {text_main} !important; }}

hr {{ border-color: {border_color} !important; margin: 1.2rem 0 !important; }}

.rok-header {{
  display: flex; align-items: center; gap: 18px; padding: 16px 24px; margin-bottom: 18px;
  background: {bg_surface} !important;
  border: 1px solid {border_color}; border-radius: 8px; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}}
.rok-header::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background: linear-gradient(90deg, {blue_accent} 0%, {gold} 100%); }}
.rok-header-emblem {{
  width: 48px; height: 48px; flex-shrink: 0; background: {bg_surface_alt};
  border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; border: 1px solid {gold};
}}
.rok-header-title {{ font-size: 1.4rem; font-weight: 900; color: {text_main}; letter-spacing: -.03em; line-height: 1; }}
.rok-header-sub {{ font-size: .7rem; color: {text_sub}; letter-spacing: .05em; margin-top: 4px; text-transform: uppercase; }}

.tier-pills {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 18px; }}
.tier-pill {{ padding: 4px 12px; border-radius: 4px; font-size: .65rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; white-space: nowrap; border: 1px solid; }}
.tp-t5 {{ color:{t5_color}; border-color:{t5_color}; background: rgba(212, 168, 71, 0.1); }}
.tp-t4 {{ color:{t4_color}; border-color:{t4_color}; background: rgba(207, 111, 58, 0.1); }}
.tp-t3 {{ color:{t3_color}; border-color:{t3_color}; background: rgba(125, 94, 184, 0.1); }}
.tp-t2 {{ color:{t2_color}; border-color:{t2_color}; background: rgba(63, 147, 166, 0.1); }}
.tp-t1 {{ color:{t1_color}; border-color:{t1_color}; background: rgba(90, 114, 148, 0.1); }}
.tp-eq {{ color:{text_muted}; border-color:{border_color}; background: rgba(255,255,255,0.03); }}

.sec-label {{ font-size: .6rem; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; color: {gold}; display: flex; align-items: center; gap: 10px; margin: 20px 0 12px; }}
.sec-label::after {{ content: ''; flex: 1; height: 1px; background: {border_color}; }}

.sbadge {{ display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 4px; font-size: .63rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; white-space: nowrap; border: 1px solid; }}
.sbadge-ok {{ color:{green_ok}; border-color:{green_ok}; background: rgba(59, 163, 122, 0.15); }}
.sbadge-wa {{ color:{yellow_pend}; border-color:{yellow_pend}; background: rgba(212, 160, 58, 0.15); }}
.sbadge-er {{ color:{red_alert}; border-color:{red_alert}; background: rgba(201, 90, 78, 0.15); }}

.mrow {{ background: {bg_surface}; border: 1px solid {border_color}; border-radius: 6px; margin-bottom: 4px; overflow: hidden; transition: border-color .2s, background .2s; }}
.mrow:hover {{ border-color: {gold}; background: {bg_surface_alt}; }}
.mrow.ok {{ border-left: 3px solid {green_ok}; }}
.mrow.wa {{ border-left: 3px solid {yellow_pend}; }}
.mrow.er {{ border-left: 3px solid {red_alert}; }}

.mrow-sum {{ display: grid; grid-template-columns: 36px 1fr 90px 80px auto; align-items: center; gap: 12px; padding: 12px 16px; cursor: pointer; }}
.mrow-rank {{ font-family: 'JetBrains Mono', monospace; font-size: .85rem; font-weight: 600; color: {text_muted}; text-align: right; }}
.mrow-info {{ min-width: 0; }}
.mrow-name {{ font-size: .88rem; font-weight: 700; color: {text_main}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mrow-meta {{ font-size: .64rem; color: {text_sub}; margin-top: 2px; }}

.mrow-gauges {{ display: flex; flex-direction: column; gap: 5px; }}
.gauge-head {{ display: flex; justify-content: space-between; font-size: .58rem; color: {text_sub}; margin-bottom: 2px; }}
.gauge-track {{ height: 5px; background: {bg_main}; border-radius: 99px; overflow: hidden; border: 1px solid {border_color}; }}
.gauge-fill {{ height: 100%; border-radius: 99px; transition: width .6s cubic-bezier(.4,0,.2,1); }}
.gauge-fill.kp {{ background: {gold}; }}
.gauge-fill.dead {{ background: {blue_accent}; }}
.gauge-fill.full {{ background: {green_ok}; }}

.mrow-kp {{ font-family: 'JetBrains Mono', monospace; font-size: .9rem; font-weight: 600; color: {gold}; text-align: right; white-space: nowrap; }}

.mdet {{ border-top: 1px solid {border_color}; background: {bg_main}; padding: 16px 20px 20px; border-radius: 0 0 6px 6px; }}
.mdet-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 16px; }}
.mdet-block-label {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: {text_sub}; margin-bottom: 6px; }}
.mdet-block-val {{ font-family: 'JetBrains Mono', monospace; font-size: 1.6rem; font-weight: 600; color: {text_main}; letter-spacing: -.04em; line-height: 1; }}
.mdet-block-sub {{ font-size: .65rem; color: {text_muted}; margin-top: 4px; }}
.mdet-prog {{ margin-top: 8px; }}
.mdet-prog-head {{ display: flex; justify-content: space-between; font-size: .6rem; color: {text_sub}; margin-bottom: 3px; }}
.mdet-prog-track {{ height: 8px; background: {bg_main}; border-radius: 99px; overflow: hidden; border: 1px solid {border_color}; }}
.mdet-prog-fill {{ height: 100%; border-radius: 99px; transition: width .6s cubic-bezier(.4,0,.2,1); }}
.mdet-prog-fill.kp {{ background: {gold}; }}
.mdet-prog-fill.dead {{ background: {blue_accent}; }}
.mdet-gap {{ font-size: .62rem; color: {text_sub}; margin-top: 4px; }}
.mdet-gap.warn {{ color: {red_alert}; }}
.mdet-gap.ok {{ color: {green_ok}; }}

.tier-table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
.tier-table th {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em; color: {text_sub}; padding: 5px 8px; text-align: right; border-bottom: 1px solid {border_color}; }}
.tier-table th:first-child {{ text-align: left; }}
.tier-table td {{ font-family: 'JetBrains Mono', monospace; font-size: .75rem; color: {text_main}; padding: 5px 8px; text-align: right; border-bottom: 1px solid {bg_surface_alt}; }}
.tier-table td:first-child {{ text-align: left; color: {text_sub}; font-weight: 600; }}
.tier-table tr:last-child td {{ border-bottom: none; }}
.tier-table td.amber {{ color: {gold}; }}
.tier-table td.blue  {{ color: {blue_accent}; }}
.tier-table td.equiv {{ color: {text_muted}; font-size: .68rem; }}

.kd-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 18px; }}
.kd-card {{ background: {bg_surface}; border: 1px solid {border_color}; border-radius: 8px; padding: 16px 18px; position: relative; overflow: hidden; }}
.kd-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }}
.kd-card.amber::before {{ background: {gold}; }}
.kd-card.green::before {{ background: {green_ok}; }}
.kd-card.yellow::before{{ background: {yellow_pend}; }}
.kd-card.red::before   {{ background: {red_alert}; }}
.kd-card.blue::before  {{ background: {blue_accent}; }}
.kd-card-label {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: {text_sub}; margin-bottom: 5px; }}
.kd-card-value {{ font-family: 'JetBrains Mono', monospace; font-size: 1.45rem; font-weight: 600; color: {text_main}; letter-spacing: -.03em; line-height: 1; }}
.kd-card-sub {{ font-size: .65rem; color: {text_muted}; margin-top: 4px; }}

.rok-caption {{ display: flex; align-items: center; gap: 14px; padding: 8px 14px; margin-bottom: 16px; background: {bg_surface}; border: 1px solid {border_color}; border-radius: 6px; flex-wrap: wrap; }}
.rok-caption-item {{ font-size: .68rem; color: {text_sub}; }}
.rok-caption-val  {{ color: {gold}; font-weight: 600; }}
.rok-caption-sep  {{ color: {text_muted}; font-size: .7rem; }}

.empty-state {{ text-align: center; padding: 60px 20px; background: {bg_surface}; border: 1px dashed {border_color}; border-radius: 12px; }}
.empty-state-icon {{ font-size: 3rem; margin-bottom: 14px; opacity: .4; }}
.empty-state-title {{ font-size: 1rem; font-weight: 700; color: {text_sub}; margin-bottom: 6px; }}
.empty-state-sub   {{ font-size: .75rem; color: {text_muted}; }}

.filter-tag {{
  display: inline-block; padding: 3px 10px; border-radius: 4px;
  font-size: .62rem; font-weight: 600; background: rgba(74, 124, 186, 0.15); color: {blue_accent}; border: 1px solid rgba(74, 124, 186, 0.3);
}}

.att-row {{ display: grid; grid-template-columns: 1fr 60px 140px auto; align-items: center; gap: 12px; padding: 10px 14px; background: {bg_surface}; border: 1px solid {border_color}; border-radius: 6px; margin-bottom: 5px; }}
.att-row.er {{ border-left: 3px solid {red_alert}; }}
.att-row.wa {{ border-left: 3px solid {yellow_pend}; }}
.att-name {{ flex: 1; font-size: .82rem; font-weight: 600; color: {text_main}; }}
.att-pow  {{ font-size: .68rem; color: {text_sub}; white-space: nowrap; }}
.att-pcts {{ font-size: .65rem; color: {text_sub}; white-space: nowrap; }}

.upload-lock {{ background: {bg_surface}; border: 1px solid {border_color}; border-radius: 6px; padding: 14px; text-align: center; margin-bottom: 10px; }}
.upload-lock-icon {{ font-size: 1.3rem; margin-bottom: 6px; }}
.upload-lock-text {{ font-size: .72rem; color: {text_sub}; margin-bottom: 10px; }}

.band-table {{ width: 100%; border-collapse: collapse; }}
.band-table th {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em; color: {text_sub}; padding: 8px 12px; text-align: right; border-bottom: 1px solid {border_color}; }}
.band-table th:first-child {{ text-align: left; }}
.band-table td {{ font-family: 'JetBrains Mono', monospace; font-size: .76rem; color: {text_main}; padding: 8px 12px; text-align: right; border-bottom: 1px solid {bg_surface_alt}; }}
.band-table td:first-child {{ text-align: left; color: {text_sub}; font-weight: 600; font-family: 'Inter', sans-serif; font-size: .78rem; }}
.band-table tr:last-child td {{ border-bottom: none; }}
</style>
"""

STATUS_CLS   = {"Goal Reached":"ok","Pending":"wa","Goal Missed":"er"}
STATUS_ICON  = {"Goal Reached":"●","Pending":"◐","Goal Missed":"○"}
STATUS_LABEL = {"Goal Reached":"Reached","Pending":"Pending","Goal Missed":"Missed"}

@st.cache_resource
def get_storage():
    return create_storage()

def get_secret(name: str) -> str | None:
    v = os.getenv(name)
    if v: return v
    try: v = st.secrets.get(name)
    except: v = None
    return str(v) if v else None

# -----------------------------------------------------------------------
# OTIMIZAÇÃO DE PERFORMANCE (CACHE)
# Ao colocar o "_storage" com underscore, o Streamlit não tenta hashear a BD.
# Isto salva o resultado desta função complexa em memória, acelerando a pesquisa.
# -----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def compute_accumulated_sum(_storage, imports: pd.DataFrame, group_power: int, date_from: date | None = None, date_to: date | None = None) -> tuple[pd.DataFrame, str, str]:
    ordered = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    ordered["_d"] = pd.to_datetime(ordered["report_date"]).dt.date

    if date_from:
        ordered = ordered[ordered["_d"] >= date_from]
    if date_to:
        ordered = ordered[ordered["_d"] <= date_to]

    if ordered.empty:
        return pd.DataFrame(), "", ""

    first_date = str(ordered.iloc[0]["report_date"])
    last_date  = str(ordered.iloc[-1]["report_date"])

    sum_columns = [
        "t1_kills", "t2_kills", "t3_kills", "t4_kills", "t5_kills",
        "t1_deaths", "t2_deaths", "t3_deaths", "t4_deaths", "t5_deaths",
        "rallies_joined", "rallies_started", "helps",
        "resources_gathered", "resources_assisted",
        "barbarians_killed", "barbarians_killed_7", "barbarians_killed_8",
    ]

    accumulated = {}

    for _, imp_row in ordered.iterrows():
        stats = _storage.load_stats(imp_row["id"])
        for _, player in stats.iterrows():
            cid = str(player["character_id"])
            if cid not in accumulated:
                accumulated[cid] = {
                    "character_id": cid,
                    "username": player["username"],
                    "alliance": player.get("alliance", ""),
                }
                for col in sum_columns:
                    accumulated[cid][col] = 0
                accumulated[cid]["_report_count"] = 0
            
            for col in sum_columns:
                if col in player:
                    try:
                        val = player[col]
                        if pd.notna(val):
                            accumulated[cid][col] += int(float(val))
                    except (ValueError, TypeError):
                        pass
            
            accumulated[cid]["_report_count"] += 1

    if not accumulated:
        return pd.DataFrame(), "", ""

    result_df = pd.DataFrame(list(accumulated.values()))
    
    first_import_id = ordered.iloc[0]["id"]
    first_stats = _storage.load_stats(first_import_id)
    initial_power_map = {}
    for _, player in first_stats.iterrows():
        cid = str(player["character_id"])
        try:
            initial_power_map[cid] = int(float(player["power"])) if pd.notna(player["power"]) else 0
        except (ValueError, TypeError):
            initial_power_map[cid] = 0
    
    for idx, row in result_df.iterrows():
        cid = str(row["character_id"])
        if cid in initial_power_map:
            result_df.at[idx, "power"] = initial_power_map[cid]
        else:
            result_df.at[idx, "power"] = 0

    result_df = result_df.drop(columns=["_report_count"], errors="ignore")
    
    metrics = calculate_metrics(result_df, group_power=group_power)
    ranked  = apply_goals(add_rank(metrics, "kill_points"))

    status_map = {"Aprovado": "Goal Reached", "Pendente": "Pending", "Abaixo da meta": "Goal Missed"}
    if "status" in ranked.columns:
        ranked["status"] = ranked["status"].map(status_map).fillna(ranked["status"])
    
    return ranked, first_date, last_date

def compute_kvk_accumulated(_storage, imports, group_power, start_d, end_d):
    result, _, _ = compute_accumulated_sum(_storage, imports, group_power, date_from=start_d, date_to=end_d)
    return result

def prepare_imports(imports: pd.DataFrame) -> pd.DataFrame:
    out = imports.copy()
    out["report_date"] = pd.to_datetime(out["report_date"]).dt.date.astype(str)
    out["imported_at"] = out["imported_at"].astype(str)
    out["label"]       = out["report_date"] + " — " + out["filename"].astype(str)
    return out

@st.cache_data(ttl=300)
def _cached_gp(label: str, first_id: str) -> int:
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"], errors="coerce").fillna(0).sum())

def default_group_power(storage, imports: pd.DataFrame) -> int:
    ordered = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    return _cached_gp(storage.label, ordered.iloc[0]["id"])

def admin_panel() -> tuple[bool, bool]:
    pwd = get_secret("ADMIN_PASSWORD")
    if not pwd:
        st.caption("Configure ADMIN_PASSWORD in Secrets.")
        return False, False
    entered = st.text_input("Admin password", type="password", key="adm_pwd",
                             label_visibility="collapsed", placeholder="Admin password...")
    if is_admin_authenticated(pwd, entered):
        st.success("✓ Admin active"); return True, True
    if entered: st.error("Incorrect")
    return True, False

def fmt_int(v: float | int) -> str:   return f"{int(v):,}"
def fmt_k(v: int | float) -> str:
    v = float(v)
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}k"
    return str(int(v))
def fmt_m(v: int | float) -> str: return f"{float(v)/1_000_000:.0f}"

def _render_below_goals_table(df: pd.DataFrame) -> None:
    below_df = df[df["status"] != "Goal Reached"].copy()
    
    st.markdown('<div class="sec-label">⚠️ Players Pending or Below Goal</div>', unsafe_allow_html=True)
    
    if below_df.empty:
        st.success("🎉 All players reached 100% of their goals in the selected period!")
        return

    below_df["kp_missing_pct"] = below_df.apply(
        lambda r: max(0.0, (1.0 - (float(r.get("kill_points", 0)) / float(r["kp_goal"])))) * 100
        if pd.notna(r.get("kp_goal")) and float(r.get("kp_goal", 0)) > 0 else 0.0,
        axis=1
    )
    
    below_df["dead_missing_pct"] = below_df.apply(
        lambda r: max(0.0, (1.0 - (float(r.get("dead_equiv", 0)) / float(r["dead_t4_goal"])))) * 100
        if pd.notna(r.get("dead_t4_goal")) and float(r.get("dead_t4_goal", 0)) > 0 else 0.0,
        axis=1
    )

    table_data = pd.DataFrame({
        "Governor": below_df["username"],
        "ID": below_df["character_id"].astype(str),
        "Initial Power (1st Day)": below_df["power"].map(lambda p: f"{fmt_m(int(p))}M"),
        "KP (Current / Goal)": below_df.apply(lambda r: f"{fmt_k(int(r.get('kill_points', 0)))} / {fmt_k(int(r.get('kp_goal', 0)))}", axis=1),
        "Missing KP %": below_df["kp_missing_pct"],
        "Deaths (Current / Goal)": below_df.apply(lambda r: f"{fmt_k(int(r.get('dead_equiv', 0)))} / {fmt_k(int(r.get('dead_t4_goal', 0)))}", axis=1),
        "Missing Deaths %": below_df["dead_missing_pct"],
        "Overall Status": below_df["status"]
    })

    st.dataframe(
        table_data,
        column_config={
            "Missing KP %": st.column_config.ProgressColumn("Missing KP %", format="%.1f%%", min_value=0, max_value=100),
            "Missing Deaths %": st.column_config.ProgressColumn("Missing Deaths %", format="%.1f%%", min_value=0, max_value=100),
        },
        use_container_width=True, hide_index=True
    )

def main() -> None:
    st.html(_css())
    storage = get_storage()

    st.markdown("""
    <div class="rok-header">
      <div class="rok-header-emblem">⚔️</div>
      <div>
        <div class="rok-header-title">K1602 · KP Dashboard</div>
        <div class="rok-header-sub">Kill Points Operations Center · Rise of Kingdoms</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="tier-pills">
      <span class="tier-pill tp-t5">T5 ×20</span>
      <span class="tier-pill tp-t4">T4 ×10</span>
      <span class="tier-pill tp-t3">T3 ×4</span>
      <span class="tier-pill tp-t2">T2 ×2</span>
      <span class="tier-pill tp-t1">T1 ×0.2</span>
      <span class="tier-pill tp-eq">1 T5 death = 2 T4</span>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown('<div class="sb-sec">System</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:.68rem;color:#8398b5;margin-bottom:12px">Storage: <span style="color:#4a7cba;font-weight:bold;">{storage.label}</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sec">Reports</div>', unsafe_allow_html=True)
        _upload_section(storage)

    imports = storage.list_imports()
    if imports.empty:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-state-icon">⚔️</div>
          <div class="empty-state-title">No reports imported yet</div>
          <div class="empty-state-sub">Upload a statsExport file in the sidebar to get started.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    imports = prepare_imports(imports)

    with st.sidebar:
        st.markdown('<div class="sb-sec">Settings</div>', unsafe_allow_html=True)
        
        min_power = st.number_input("Power Min (Millions)", min_value=0, value=0, step=1, format="%d")
        min_power_value = min_power * 1_000_000
        
        min_kp = st.number_input("KP Min", min_value=0, value=0, step=1000, format="%d")
        min_kp_pct = st.slider("% KP Min", min_value=0, max_value=100, value=0, step=5)
        min_dead_pct = st.slider("% Deaths Min", min_value=0, max_value=100, value=0, step=5)
        
        if st.button("🔄 Reset Filters", use_container_width=True, type="secondary"):
            st.rerun()
        
        st.markdown('<div class="sb-sec">Admin</div>', unsafe_allow_html=True)
        admin_enabled, is_admin = admin_panel()

    gp = default_group_power(storage, imports)
    all_dates = sorted(imports["report_date"].unique())
    min_d = pd.to_datetime(all_dates[0]).date()
    max_d = pd.to_datetime(all_dates[-1]).date()

    # ---------------------------------------------------------
    # CALLBACKS PARA RESOLVER O StreamlitAPIException
    # Estes callbacks mudam as datas no estado de sessão ANTES da página recarregar
    # ---------------------------------------------------------
    def set_this_month():
        today = date.today()
        st.session_state.main_date_from = today.replace(day=1)
        st.session_state.main_date_to = today

    def set_all_time():
        st.session_state.main_date_from = min_d
        st.session_state.main_date_to = max_d

    st.markdown('<div class="sec-label" style="margin-top:0">Analysis Period</div>', unsafe_allow_html=True)
    
    with st.container():
        dcol1, dcol2, dcol3, dcol4, dcol5 = st.columns([1.5, 1.5, 1, 1, 3])
        
        with dcol1:
            date_from = st.date_input("Start Date", value=min_d, min_value=min_d, max_value=max_d, key="main_date_from")
        with dcol2:
            date_to = st.date_input("End Date", value=max_d, min_value=min_d, max_value=max_d, key="main_date_to")
        with dcol3:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("🔄 This Month", key="btn_this_month", use_container_width=True, on_click=set_this_month)
        with dcol4:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("📅 All Time", key="btn_all_time", use_container_width=True, on_click=set_all_time)
        with dcol5:
            n_imports_in_range = len(imports[(pd.to_datetime(imports["report_date"]).dt.date >= date_from) & (pd.to_datetime(imports["report_date"]).dt.date <= date_to)])
            st.markdown(f"""
            <div style="padding-top:8px;font-size:.72rem;color:#9ab0cc">
                <span style="color:#d4a847;font-weight:600">{n_imports_in_range}</span> reports in period
                <br><span style="font-size:.62rem">Initial power fixed on 1st day of period</span>
            </div>
            """, unsafe_allow_html=True)

    if date_from > date_to:
        st.error("⚠️ Start date must be before end date.")
        return

    ranked, first_date, last_date = compute_accumulated_sum(storage, imports, gp, date_from=date_from, date_to=date_to)

    if ranked.empty:
        st.warning("No reports found in the selected date range.")
        return

    filter_conditions = pd.Series(True, index=ranked.index)
    
    if min_power_value > 0:
        filter_conditions &= pd.to_numeric(ranked["power"], errors="coerce").fillna(0) >= min_power_value
    if min_kp > 0:
        filter_conditions &= pd.to_numeric(ranked["kill_points"], errors="coerce").fillna(0) >= min_kp
    if min_kp_pct > 0:
        filter_conditions &= (pd.to_numeric(ranked["kp_pct"], errors="coerce").fillna(0) * 100) >= min_kp_pct
    if min_dead_pct > 0:
        filter_conditions &= (pd.to_numeric(ranked["dead_pct"], errors="coerce").fillna(0) * 100) >= min_dead_pct
    
    ranked = ranked[filter_conditions]
    
    if ranked.empty:
        st.warning("No governors match the selected filters.")
        return

    active_filters = []
    if min_power_value > 0: active_filters.append(f"Power ≥ {min_power}M")
    if min_kp > 0: active_filters.append(f"KP ≥ {fmt_k(min_kp)}")
    if min_kp_pct > 0: active_filters.append(f"KP ≥ {min_kp_pct}%")
    if min_dead_pct > 0: active_filters.append(f"Deaths ≥ {min_dead_pct}%")
    
    if active_filters:
        st.markdown(f"""
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
            <span style="font-size:.62rem;color:#9ab0cc;font-weight:600">Active filters:</span>
            {''.join(f'<span class="filter-tag">{f}</span>' for f in active_filters)}
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">From <span class="rok-caption-val">{first_date}</span></div>
      <div class="rok-caption-sep">→</div>
      <div class="rok-caption-item"><span class="rok-caption-val">{last_date}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Members <span class="rok-caption-val">{len(ranked):,}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Reports in range <span class="rok-caption-val">{n_imports_in_range}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Base Power <span class="rok-caption-val">{first_date}</span></div>
    </div>
    """, unsafe_allow_html=True)

    tab_labels = ["⚔ Ranking", "🏰 My KvK", "🏆 Hall of Fame", "👑 Kingdom", "👤 Profile", "❓ Help"]
    if admin_enabled and is_admin:
        tab_labels.append("📈 History")
        tab_labels.append("📁 Imports")

    tabs = st.tabs(tab_labels)
    with tabs[0]: show_ranking(ranked, key_prefix="main")
    with tabs[1]: show_kvk(storage, imports, gp, ranked, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[2]: show_hof(storage, imports, gp, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[3]: show_kingdom(ranked, imports, storage, gp)
    with tabs[4]: show_profile(storage, imports, gp)
    with tabs[5]: show_help()
    if admin_enabled and is_admin:
        with tabs[6]: show_history(storage, imports, gp)
        with tabs[7]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)

def _upload_section(storage):
    upload_pwd = get_secret("UPLOAD_PASSWORD")
    admin_pwd  = get_secret("ADMIN_PASSWORD")
        
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.markdown("""
        <div class="upload-lock">
          <div class="upload-lock-icon">🔒</div>
          <div class="upload-lock-text">Upload restricted to leadership</div>
        </div>
        """, unsafe_allow_html=True)
        up_pwd = st.text_input("Upload Password", type="password", key="up_pwd", label_visibility="collapsed", placeholder="Enter upload password...")
        if st.button("Unlock Upload", use_container_width=True):
            is_admin = admin_pwd and is_admin_authenticated(admin_pwd, up_pwd)
            is_uploader = upload_pwd and up_pwd == upload_pwd
            if is_admin or is_uploader:
                st.session_state.upload_auth = True
                st.rerun()
            else:
                st.error("Incorrect password")
        return

    st.success("✓ Upload access granted")
    if st.button("🔒 Lock", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False
        st.rerun()

    uploaded = st.file_uploader("statsExport (.xlsx)", type=["xlsx","xls"])
    if not uploaded:
        return
    
    safe_name = re.sub(r"[^\w.\-]", "_", uploaded.name)
    report_date = st.date_input("Report Date", value=extract_report_date_from_name(safe_name) or date.today())
    
    if st.button("💾 Save Report", type="primary", use_container_width=True):
        with st.spinner("Processing..."):
            try:
                fb = uploaded.getvalue()
                if len(fb) > 50*1024*1024:
                    st.error("File is too large (max 50 MB).")
                    return
                
                stats = load_stats_file(BytesIO(fb), filename=safe_name)
                import_id, created = storage.save_import(
                    filename=safe_name,
                    report_date=report_date.isoformat(),
                    file_hash=file_sha256(fb),
                    stats=stats
                )
                if created:
                    maybe_archive(storage, import_id, stats, None)
                    st.success("Report successfully saved!")
                    st.rerun()
                else:
                    st.warning("Duplicate file detected.")
            except Exception as e:
                st.error(f"Upload error: {e}")

def show_ranking(ranked_full: pd.DataFrame, key_prefix: str = "main") -> None:
    fc1, fc2, fc3 = st.columns([5, 2, 2])
    with fc1:
        search = st.text_input("search", placeholder="Search member or Character ID…",
                                key=f"{key_prefix}_rank_search", label_visibility="collapsed")
    with fc2:
        sf = st.selectbox("status", ["All", "Goal Reached", "Pending", "Goal Missed"],
                          key=f"{key_prefix}_rank_sf", label_visibility="collapsed")
    with fc3:
        sort_by = st.selectbox("sort",
                               ["KP ↓","Power ↓","% KP ↓","% Deaths ↓","Name ↑"],
                               key=f"{key_prefix}_rank_sort", label_visibility="collapsed")

    df = ranked_full.copy()

    if 'dead_equiv' in df.columns:
        top_5_pct_deaths = df['dead_equiv'].quantile(0.95) if len(df) > 0 else float('inf')
    else:
        top_5_pct_deaths = float('inf')
    
    df['emblems'] = ""
    for idx, row in df.iterrows():
        emb = ""
        if row.get('dead_equiv', 0) >= top_5_pct_deaths and row.get('dead_equiv', 0) > 0:
            emb += '<span title="Top 5% Deaths">🛡️</span> '
        if row.get('kill_points', 0) >= (row.get('kp_goal', 1) * 2) and row.get('kp_goal', 0) > 0:
            emb += '<span title="2x KP Goal">🔥</span> '
        if row.get('power', 0) >= 100_000_000:
            emb += '<span title="Whale (100M+ Power)">🐋</span> '
        df.at[idx, 'emblems'] = emb

    # -----------------------------------------------------------------------
    # OTIMIZAÇÃO: PESQUISA VETORIZADA NO PANDAS (MUITO MAIS RÁPIDA)
    # -----------------------------------------------------------------------
    if search.strip():
        n = search.strip()
        mask = df["username"].astype(str).str.contains(n, case=False, na=False) | \
               df["character_id"].astype(str).str.contains(n, case=False, na=False)
        df = df[mask]

    if sf != "All":
        df = df[df["status"] == sf]

    sort_map = {
        "KP ↓":("kill_points",False),"Power ↓":("power",False),
        "% KP ↓":("kp_pct",False),"% Deaths ↓":("dead_pct",False),"Name ↑":("username",True),
    }
    scol, sasc = sort_map.get(sort_by, ("kill_points",False))
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    _render_below_goals_table(ranked_full)

    st.markdown(f'<div class="sec-label">Governors · {len(df):,} of {len(ranked_full):,}</div>', unsafe_allow_html=True)

    page_size = st.selectbox("Per page",[10,25,50,100],index=1, key=f"{key_prefix}_rank_ps",label_visibility="collapsed")
    total_pg  = max(1,-(-len(df)//page_size))
    col_pg1, col_pg2 = st.columns([1,5])
    with col_pg1:
        page = st.number_input("Page",min_value=1,max_value=total_pg,value=1, key=f"{key_prefix}_rank_pg",label_visibility="collapsed")
    with col_pg2:
        st.markdown(f'<div style="font-size:.65rem;color:#9ab0cc;padding-top:8px">Page {page} of {total_pg}</div>', unsafe_allow_html=True)

    start = (page-1)*page_size
    _render_members(df.iloc[start:start+page_size], key_prefix=key_prefix)

    with st.expander("Export full table →", expanded=False):
        export_df = df.copy()
        
        export_df["KP Goal Status"] = export_df.apply(
            lambda r: "Goal Reached" if float(r.get("kill_points", 0)) >= float(r.get("kp_goal", 1)) else f"Goal Missed ({min(float(r.get('kp_pct', 0))*100, 100):.1f}%)", axis=1
        )
        export_df["Death Goal Status"] = export_df.apply(
            lambda r: "Goal Reached" if float(r.get("dead_equiv", 0)) >= float(r.get("dead_t4_goal", 1)) else f"Goal Missed ({min(float(r.get('dead_pct', 0))*100, 100):.1f}%)", axis=1
        )

        cols_show = {
            "username": "Name",
            "character_id": "ID",
            "kill_points": "KP",
            "KP Goal Status": "KP Goal Status",
            "dead_equiv": "Deaths",
            "Death Goal Status": "Death Goal Status"
        }
        
        avail = {k:v for k,v in cols_show.items() if k in export_df.columns}
        out = export_df[list(avail.keys())].rename(columns=avail)
        
        st.dataframe(out, use_container_width=True, hide_index=True)
        st.download_button("⬇ Download CSV", data=out.to_csv(index=False).encode(), file_name="ranking_simplified.csv", mime="text/csv", key=f"{key_prefix}_dl_csv", use_container_width=True)

# -----------------------------------------------------------------------
# OTIMIZAÇÃO DE PERFORMANCE: Adicionado Cache no carregamento dos gráficos
# -----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _render_member_chart(_storage, imports, username, character_id, key_prefix):
    if px is None or go is None: return
    ordered = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    history_rows = []
    for _, imp_row in ordered.iterrows():
        try:
            stats = _storage.load_stats(imp_row["id"])
            player_stats = stats[(stats["username"] == username) | (stats["character_id"].astype(str) == str(character_id))]
            if player_stats.empty: continue
            metrics = calculate_metrics(player_stats, group_power=100_000_000)
            ranked  = apply_goals(add_rank(metrics, "kill_points"))
            ranked["report_date"] = imp_row["report_date"]
            if "dead_equiv" not in ranked.columns: ranked["dead_equiv"] = 0
            history_rows.append(ranked)
        except Exception: continue

    if not history_rows: return
    player_data = pd.concat(history_rows, ignore_index=True).sort_values("report_date")
    if player_data.empty or len(player_data) < 1: return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data['kill_points'], mode='lines+markers', name='Kill Points', line=dict(color='#d4a847', width=2, shape='spline'), marker=dict(size=6, color='#d4a847')))
    fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data['dead_equiv'], mode='lines+markers', name='Deaths (T4 Equiv)', line=dict(color='#4a7cba', width=2, shape='spline'), marker=dict(size=6, color='#4a7cba')))

    fig.update_layout(title=f"Evolution - {username}", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ab0cc", family="Inter", size=11), yaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)", zeroline=False), xaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)", zeroline=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"), margin=dict(l=0, r=0, t=40, b=0), height=250)
    
    st.plotly_chart(fig, use_container_width=True, key=f"chart_{key_prefix}_{character_id}")

def _render_members(df: pd.DataFrame, key_prefix: str = "main") -> None:
    storage = get_storage()
    imports = prepare_imports(storage.list_imports())

    for i, (_, row) in enumerate(df.iterrows()):
        cls    = STATUS_CLS.get(row["status"], "er")
        kp_w   = min(float(row.get("kp_pct",0))*100, 100)
        dead_w = min(float(row.get("dead_pct",0))*100, 100)
        kp_gap   = int(row.get("kp_gap",0))
        dead_gap = int(row.get("dead_gap_t4",0))

        kp_fc   = "full" if kp_w >= 100 else "kp"
        dead_fc = "full" if dead_w >= 100 else "dead"

        badge_cls = f"sbadge-{cls}"
        badge = (f'<span class="sbadge {badge_cls}">{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</span>')

        with st.expander(label=f"#{int(row['rank'])}  {row['username']}", expanded=False):
            st.markdown(f"""
            <div class="mrow {cls}" style="margin-bottom:10px">
              <div class="mrow-sum" style="cursor:default">
                <div class="mrow-rank">#{int(row['rank'])}</div>
                <div class="mrow-info">
                  <div class="mrow-name">{row['username']} {row.get('emblems', '')}</div>
                  <div class="mrow-meta">{fmt_m(int(row['power']))}M power (1st day) · {row.get('power_band','—')} · ID {row.get('character_id','—')}</div>
                </div>
                <div class="mrow-gauges">
                  <div>
                    <div class="gauge-head"><span>KP {kp_w:.0f}%</span><span>{fmt_k(int(row['kill_points']))}</span></div>
                    <div class="gauge-track"><div class="gauge-fill {kp_fc}" style="width:{kp_w:.1f}%"></div></div>
                  </div>
                  <div>
                    <div class="gauge-head"><span>D {dead_w:.0f}%</span><span>{fmt_k(int(row.get('dead_equiv',0)))} T4eq</span></div>
                    <div class="gauge-track"><div class="gauge-fill {dead_fc}" style="width:{dead_w:.1f}%"></div></div>
                  </div>
                </div>
                <div class="mrow-kp">{fmt_k(int(row['kill_points']))}</div>
                <div>{badge}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            _render_member_chart(storage, imports, row['username'], row.get('character_id', ''), key_prefix)

            t5d = int(row.get("t5_deaths",0)); t4d = int(row.get("t4_deaths",0))
            t3d = int(row.get("t3_deaths",0)); t2d = int(row.get("t2_deaths",0)); t1d = int(row.get("t1_deaths",0))
            dead_equiv = int(row.get("dead_equiv",0))

            kp_gap_html = (f'<div class="mdet-gap ok">✓ KP goal reached</div>' if kp_gap == 0 else f'<div class="mdet-gap warn">⚠ {fmt_k(kp_gap)} KP missing</div>')
            dead_gap_html = (f'<div class="mdet-gap ok">✓ Death goal reached</div>' if dead_gap == 0 else f'<div class="mdet-gap warn">⚠ {fmt_k(dead_gap)} T4eq missing</div>')

            st.markdown(f"""
            <div class="mdet">
              <div class="mdet-grid">
                <div>
                  <div class="mdet-block-label">Kill Points</div>
                  <div class="mdet-block-val">{fmt_int(int(row['kill_points']))}</div>
                  <div class="mdet-block-sub">Goal: {fmt_int(int(row['kp_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head"><span>{kp_w:.1f}% reached</span><span>{fmt_int(int(row['kill_points']))} / {fmt_int(int(row['kp_goal']))}</span></div>
                    <div class="mdet-prog-track"><div class="mdet-prog-fill kp" style="width:{kp_w:.1f}%"></div></div>
                  </div>
                  {kp_gap_html}
                </div>
                <div>
                  <div class="mdet-block-label">Deaths (T4 equiv.)</div>
                  <div class="mdet-block-val">{fmt_int(dead_equiv)}</div>
                  <div class="mdet-block-sub">Goal: {fmt_int(int(row['dead_t4_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head"><span>{dead_w:.1f}% reached</span><span>{fmt_int(dead_equiv)} / {fmt_int(int(row['dead_t4_goal']))}</span></div>
                    <div class="mdet-prog-track"><div class="mdet-prog-fill dead" style="width:{dead_w:.1f}%"></div></div>
                  </div>
                  {dead_gap_html}
                </div>
              </div>
            """, unsafe_allow_html=True)

            dc1, dc2 = st.columns(2)
            with dc1:
                t5k = int(row.get("t5_kills",0)); t4k = int(row.get("t4_kills",0))
                t3k = int(row.get("t3_kills",0)); t2k = int(row.get("t2_kills",0)); t1k = int(row.get("t1_kills",0))
                st.markdown(f"""
                <div class="mdet-block-label" style="margin-top:0">Kills by Tier</div>
                <table class="tier-table">
                  <tr><th>Tier</th><th>Kills</th><th>KP gen.</th></tr>
                  <tr><td>T5</td><td class="amber">{fmt_k(t5k)}</td><td class="amber">{fmt_k(t5k*20)}</td></tr>
                  <tr><td>T4</td><td class="amber">{fmt_k(t4k)}</td><td class="amber">{fmt_k(t4k*10)}</td></tr>
                  <tr><td>T3</td><td>{fmt_k(t3k)}</td><td>{fmt_k(t3k*4)}</td></tr>
                  <tr><td>T2</td><td>{fmt_k(t2k)}</td><td>{fmt_k(t2k*2)}</td></tr>
                  <tr><td>T1</td><td>{fmt_k(t1k)}</td><td>{fmt_k(int(t1k*.2))}</td></tr>
                </table>
                """, unsafe_allow_html=True)
            with dc2:
                st.markdown(f"""
                <div class="mdet-block-label" style="margin-top:0">Deaths by Tier</div>
                <table class="tier-table">
                  <tr><th>Tier</th><th>Deaths</th><th>T4 Equiv.</th></tr>
                  <tr><td>T5</td><td class="blue">{fmt_k(t5d)}</td><td class="equiv">≡ {fmt_k(t5d*2)}</td></tr>
                  <tr><td>T4</td><td class="blue">{fmt_k(t4d)}</td><td class="equiv">≡ {fmt_k(t4d)}</td></tr>
                  <tr><td>T3</td><td>{fmt_k(t3d)}</td><td class="equiv">—</td></tr>
                  <tr><td>T2</td><td>{fmt_k(t2d)}</td><td class="equiv">—</td></tr>
                  <tr><td>T1</td><td>{fmt_k(t1d)}</td><td class="equiv">—</td></tr>
                </table>
                <div style="font-size:.62rem;color:#9ab0cc;margin-top:8px">
                  Total equiv: <span style="color:#4a7cba;font-family:monospace">{fmt_int(dead_equiv)}</span>
                  / Goal: <span style="color:#5a7294;font-family:monospace">{fmt_int(int(row['dead_t4_goal']))}</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

def show_kvk(storage, imports, group_power, ranked_alliance, *, is_admin, admin_enabled):
    st.markdown('''
    <div class="rok-header" style="border-left-color:#4a7cba">
      <div class="rok-header-emblem" style="background:#162233; border-color:#4a7cba">🏰</div>
      <div>
        <div class="rok-header-title">My KvK</div>
        <div class="rok-header-sub">Manage Events and View Kingdom Performance</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    if admin_enabled and is_admin:
        with st.expander("➕ Create / Manage KvK Event", expanded=False):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1: kvk_name = st.text_input("KvK Name", placeholder="Ex: KvK 5 - Heroic Anthem")
            with c2: kvk_start = st.date_input("Start Date")
            with c3: kvk_end = st.date_input("End Date")
            
            if st.button("🚀 Create KvK Event", type="primary", use_container_width=True):
                if not kvk_name.strip():
                    st.error("Enter a name.")
                elif kvk_end < kvk_start:
                    st.error("End date must be after start date.")
                else:
                    try:
                        storage.create_kvk_event(name=kvk_name.strip(), start_date=kvk_start.isoformat(), end_date=kvk_end.isoformat())
                    except AttributeError:
                        storage.save_kvk_structure(name=kvk_name.strip(), story_type="Heroic Anthem", start_date=kvk_start.isoformat(), end_date=kvk_end.isoformat(), camps=[])
                    st.success(f"✅ Event '{kvk_name}' created!")
                    st.rerun()

    try:
        events = storage.list_kvk_events()
    except AttributeError:
        events = storage.list_campaigns()

    if events.empty:
        st.markdown('''
        <div class="empty-state">
          <div class="empty-state-icon">🏰</div>
          <div class="empty-state-title">No Active Events</div>
          <div class="empty-state-sub">Create an event by defining dates to start the analysis.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    events["label"] = events["name"] + "  (" + events["start_date"] + " → " + events["end_date"] + ")"
    chosen_label = st.selectbox("Select KvK for Analysis", events["label"].tolist(), label_visibility="collapsed")
    event_row = events.loc[events["label"].eq(chosen_label)].iloc[0]
    e_start = pd.to_datetime(event_row["start_date"]).date()
    e_end = pd.to_datetime(event_row["end_date"]).date()

    if admin_enabled and is_admin:
        if st.button("🗑️ Delete Selected Event", type="secondary", use_container_width=True):
            try: storage.delete_kvk_event(event_row["id"])
            except AttributeError: storage.delete_campaign(event_row["id"])
            st.rerun()

    imports_kvk = imports.copy()
    imports_kvk["_d"] = pd.to_datetime(imports_kvk["report_date"]).dt.date
    imports_kvk = imports_kvk[(imports_kvk["_d"] >= e_start) & (imports_kvk["_d"] <= e_end)].sort_values("report_date")

    st.markdown("---")
    if imports_kvk.empty:
        st.warning(f"There are no reports imported between {e_start} and {e_end}.")
        return

    ranked_kvk, _, _ = compute_accumulated_sum(storage, imports, group_power, date_from=e_start, date_to=e_end)
    kvk_kp = int(ranked_kvk["kill_points"].sum())
    kvk_deaths = int(ranked_kvk["dead_equiv"].sum()) if "dead_equiv" in ranked_kvk else 0
    kvk_active = len(ranked_kvk[ranked_kvk["kill_points"] > 0])

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("🏆 KP Generated in KvK", fmt_k(kvk_kp))
    with c2: st.metric("💀 Total Deaths (T4eq)", fmt_k(kvk_deaths))
    with c3: st.metric("🛡️ Active Players", f"{kvk_active:,}")
    with c4: st.metric("📂 Reports in Period", len(imports_kvk))

    st.markdown('<div class="sec-label">📈 Kingdom Evolution during KvK</div>', unsafe_allow_html=True)
    
    if px is not None:
        trend_data = []
        for _, imp in imports_kvk.iterrows():
            st_df = storage.load_stats(imp["id"])
            m = calculate_metrics(st_df, group_power=1)
            kp_dia = int(m["kill_points"].sum())
            deaths_dia = int((m.get("t4_deaths",0) + m.get("t5_deaths",0)*2).sum())
            trend_data.append({"Date": imp["report_date"], "Total KP": kp_dia, "Total Deaths": deaths_dia})
        
        trend_df = pd.DataFrame(trend_data)
        if not trend_df.empty:
            tc1, tc2 = st.columns(2)
            with tc1:
                fig1 = px.area(trend_df, x="Date", y="Total KP", color_discrete_sequence=["#d4a847"])
                fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ab0cc"), margin=dict(l=0,r=0,t=10,b=0), height=300)
                st.plotly_chart(fig1, use_container_width=True)
            with tc2:
                fig2 = px.area(trend_df, x="Date", y="Total Deaths", color_discrete_sequence=["#4a7cba"])
                fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ab0cc"), margin=dict(l=0,r=0,t=10,b=0), height=300)
                st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<div class="sec-label">⚔️ Governors Performance in this KvK</div>', unsafe_allow_html=True)

    if not ranked_kvk.empty:
        search_kvk = st.text_input("Search member or Character ID...", key="kvk_search", label_visibility="collapsed")
        
        df_kvk = ranked_kvk.copy()
        
        df_kvk['emblems'] = ""
        top_5_pct_deaths_kvk = df_kvk['dead_equiv'].quantile(0.95) if len(df_kvk) > 0 and 'dead_equiv' in df_kvk.columns else float('inf')
        for idx, row in df_kvk.iterrows():
            emb = ""
            if row.get('dead_equiv', 0) >= top_5_pct_deaths_kvk and row.get('dead_equiv', 0) > 0:
                emb += '<span title="Top 5% Deaths">🛡️</span> '
            if row.get('kill_points', 0) >= (row.get('kp_goal', 1) * 2) and row.get('kp_goal', 0) > 0:
                emb += '<span title="2x KP Goal">🔥</span> '
            if row.get('power', 0) >= 100_000_000:
                emb += '<span title="Whale (100M+ Power)">🐋</span> '
            df_kvk.at[idx, 'emblems'] = emb
        
        # OTIMIZAÇÃO NA PESQUISA KVK
        if search_kvk.strip():
            n_kvk = search_kvk.strip()
            mask_kvk = df_kvk["username"].astype(str).str.contains(n_kvk, case=False, na=False) | \
                       df_kvk["character_id"].astype(str).str.contains(n_kvk, case=False, na=False)
            df_kvk = df_kvk[mask_kvk]

        df_kvk = df_kvk.sort_values("kill_points", ascending=False).reset_index(drop=True)
        df_kvk["rank"] = range(1, len(df_kvk) + 1)

        st.markdown(f'<div class="sec-label" style="margin-top: 0;">Governors · {len(df_kvk):,} of {len(ranked_kvk):,}</div>', unsafe_allow_html=True)

        if not df_kvk.empty:
            page_size_kvk = st.selectbox("Per page", [10, 25, 50, 100], index=1, key="kvk_ps", label_visibility="collapsed")
            total_pg_kvk  = max(1, -(-len(df_kvk) // page_size_kvk))
            col_pg1_kvk, col_pg2_kvk = st.columns([1, 5])
            with col_pg1_kvk:
                page_kvk = st.number_input("Page", min_value=1, max_value=total_pg_kvk, value=1, key="kvk_pg", label_visibility="collapsed")
            with col_pg2_kvk:
                st.markdown(f'<div style="font-size:.65rem;color:#9ab0cc;padding-top:8px">Page {page_kvk} of {total_pg_kvk}</div>', unsafe_allow_html=True)

            start_kvk = (page_kvk - 1) * page_size_kvk
            _render_members(df_kvk.iloc[start_kvk : start_kvk + page_size_kvk], key_prefix="kvk")
        else:
            st.info("No governors found matching your search.")

def show_hof(storage, imports, group_power, *, is_admin, admin_enabled):
    st.markdown('''
    <div class="rok-header" style="border-left-color:#d4a847">
      <div class="rok-header-emblem" style="background:#162233; border-color:#d4a847">🏆</div>
      <div>
        <div class="rok-header-title">Hall of Fame — K1602</div>
        <div class="rok-header-sub">Top 10 KP · Top 10 Deaths · By KvK Event</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)
    try: events = storage.list_kvk_events()
    except AttributeError: events = storage.list_campaigns()
    if events.empty:
        st.markdown('<div class="empty-state"><div class="empty-state-icon">🏆</div><div class="empty-state-title">No KvK events</div><div class="empty-state-sub">Create a KvK event first.</div></div>', unsafe_allow_html=True)
        return
    events = events.copy()
    events["start_date"] = pd.to_datetime(events["start_date"]).dt.date.astype(str)
    events["end_date"]   = pd.to_datetime(events["end_date"]).dt.date.astype(str)
    events["label"]      = events["name"] + "  (" + events["start_date"] + " → " + events["end_date"] + ")"
    chosen_label = st.selectbox("KvK Event", events["label"].tolist(), key="hof_kvk", label_visibility="collapsed")
    event_row = events.loc[events["label"].eq(chosen_label)].iloc[0]
    start_d, end_d = pd.to_datetime(event_row["start_date"]).date(), pd.to_datetime(event_row["end_date"]).date()
    imports_cp = imports.copy()
    imports_cp["_d"] = pd.to_datetime(imports_cp["report_date"]).dt.date
    in_window = imports_cp[(imports_cp["_d"] >= start_d) & (imports_cp["_d"] <= end_d)]
    if in_window.empty:
        if start_d > date.today(): st.info(f"⏳ This KvK hasn't started yet.")
        else: st.warning("No reports uploaded within this KvK's date range yet.")
        return
    ranked = compute_kvk_accumulated(storage, imports, group_power, start_d, end_d)
    if ranked.empty:
        st.info("No player data available for this KvK yet.")
        return
    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">Event <span class="rok-caption-val">{event_row['name']}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">{event_row['start_date']} → {event_row['end_date']}</div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Reports <span class="rok-caption-val">{len(in_window)}</span></div>
    </div>
    """, unsafe_allow_html=True)
    if "dead_equiv" not in ranked.columns:
        ranked["dead_equiv"] = (ranked.get("t4_deaths", 0) + ranked.get("t5_deaths", 0) * 2).fillna(0).astype(int)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:#d4a847;margin-bottom:10px">⚔ Top 10 Kill Points</div>', unsafe_allow_html=True)
        _render_hof_list(ranked.sort_values("kill_points", ascending=False).head(10).reset_index(drop=True), "kp")
    with c2:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:#4a7cba;margin-bottom:10px">💀 Top 10 Deaths</div>', unsafe_allow_html=True)
        _render_hof_list(ranked.sort_values("dead_equiv", ascending=False).head(10).reset_index(drop=True), "deaths")

def _render_hof_list(df, category):
    if df.empty: return
    medals = {1:"🥇", 2:"🥈", 3:"🥉"}
    color, unit, val_col = ("#d4a847", "KP", "kill_points") if category == "kp" else ("#4a7cba", "T4eq", "dead_equiv")
    for pos, (_, row) in enumerate(df.iterrows(), start=1):
        is_top, medal = pos <= 3, medals.get(pos, f"#{pos}")
        st.markdown(f'''
        <div style="display:flex;align-items:center;gap:10px;padding:{"12px 14px" if is_top else "9px 14px"};background:{"rgba(212, 168, 71, 0.08)" if is_top else "transparent"};border:1px solid {"rgba(212, 168, 71, 0.2)" if is_top else "rgba(42, 63, 94, 0.5)"};border-radius:6px;margin-bottom:5px;">
          <div style="font-size:{"1.2rem" if is_top else ".85rem"};min-width:28px;text-align:center">{medal}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:{"0.88rem" if is_top else "0.82rem"};font-weight:{"700" if is_top else "500"};color:#f0f4fa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{row["username"]}</div>
            <div style="font-size:.62rem;color:#9ab0cc;margin-top:1px">{fmt_m(int(row.get("power",0)))}M power</div>
          </div>
          <div style="font-family:JetBrains Mono,monospace;font-size:{"1rem" if is_top else "0.85rem"};font-weight:600;color:{color};white-space:nowrap">{fmt_k(int(row.get(val_col,0)))} {unit}</div>
        </div>
        ''', unsafe_allow_html=True)

def show_kingdom(ranked, imports, storage, group_power):
    total, approved, pending, below, active = len(ranked), int((ranked["status"]=="Goal Reached").sum()), int((ranked["status"]=="Pending").sum()), int((ranked["status"]=="Goal Missed").sum()), int((ranked["kill_points"]>0).sum())
    kp_total, power_total = int(ranked["kill_points"].sum()), int(ranked["power"].sum())
    st.markdown('<div class="sec-label">Kingdom Operations</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kd-row">
      <div class="kd-card amber"><div class="kd-card-label">Total Kill Points</div><div class="kd-card-value">{fmt_k(kp_total)}</div><div class="kd-card-sub">accumulated points</div></div>
      <div class="kd-card blue"><div class="kd-card-label">Total Power</div><div class="kd-card-value">{fmt_m(power_total)}M</div><div class="kd-card-sub">combined initial power</div></div>
      <div class="kd-card green"><div class="kd-card-label">Governors</div><div class="kd-card-value">{total:,}</div><div class="kd-card-sub">{active} active in period</div></div>
      <div class="kd-card green"><div class="kd-card-label">Approval Rate</div><div class="kd-card-value">{approved/total*100 if total else 0:.1f}%</div><div class="kd-card-sub">{approved} of {total} members</div></div>
      <div class="kd-card red"><div class="kd-card-label">Below Goal</div><div class="kd-card-value">{below}</div><div class="kd-card-sub">{pending} pending</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Power bands</div>', unsafe_allow_html=True)
    bands = []
    for pmin, pmax, _, _, kp in GOAL_TABLE:
        lbl = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax!=float("inf") else f"{pmin//1_000_000}M+"
        sub = ranked[ranked["power_band"]==lbl] if "power_band" in ranked else pd.DataFrame()
        if not sub.empty:
            bands.append({"Band":lbl,"Total":len(sub),"✅":int((sub["status"]=="Goal Reached").sum()),"🟡":int((sub["status"]=="Pending").sum()),"❌":int((sub["status"]=="Goal Missed").sum()),"Total KP":fmt_k(int(sub["kill_points"].sum())),"KP Goal":fmt_k(kp)})
    if bands: st.markdown('<table class="band-table"><tr><th>Band</th><th>Total</th><th>✅</th><th>🟡</th><th>❌</th><th>Total KP</th><th>KP Goal</th></tr>' + "".join(f'<tr><td>{b["Band"]}</td><td>{b["Total"]}</td><td>{b["✅"]}</td><td>{b["🟡"]}</td><td>{b["❌"]}</td><td>{b["Total KP"]}</td><td>{b["KP Goal"]}</td></tr>' for b in bands) + '</table>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Need attention & Mailing List</div>', unsafe_allow_html=True)
    c_att, c_mail = st.columns([2, 1])
    att = ranked[ranked["status"]!="Goal Reached"].sort_values("kp_pct").head(8)
    with c_att:
        if att.empty: st.success("All members are approved!")
        else:
            for _, r in att.iterrows():
                cls = STATUS_CLS.get(r["status"],"er")
                st.markdown(f'<div class="att-row {cls}"><div class="att-name">{r["username"]}</div><div class="att-pow">{fmt_m(int(r["power"]))}M</div><div class="att-pcts">KP {min(float(r.get("kp_pct",0))*100,100):.0f}% · D {min(float(r.get("dead_pct",0))*100,100):.0f}%</div><div class="sbadge sbadge-{cls}">{STATUS_ICON.get(r["status"],"○")} {STATUS_LABEL.get(r["status"],"—")}</div></div>', unsafe_allow_html=True)
    with c_mail:
        st.markdown("<div style='font-size:0.75rem;color:#9ab0cc;margin-bottom:10px;'>Player IDs pending or below goal:</div>", unsafe_allow_html=True)
        abaixo = ranked[ranked['status'] != 'Goal Reached']
        if not abaixo.empty: st.code(",".join(abaixo['character_id'].astype(str).tolist()), language="text")
        else: st.success("No mails needed.")

def show_profile(storage, imports, gp):
    st.markdown('<div class="sec-label">Player Tracker</div>', unsafe_allow_html=True)
    if imports.empty: return st.info("Import more reports to track evolution.")
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    player_list = sorted(set(storage.load_stats(i)["username"].dropna().tolist()[0] for i in ordered["id"] if not storage.load_stats(i).empty)) if not ordered.empty else []
    selected_player = st.selectbox("Select or search Governor:", player_list)
    if not selected_player: return
    history_rows = []
    for _, imp in ordered.iterrows():
        try:
            stats = storage.load_stats(imp["id"])
            p_stats = stats[stats["username"] == selected_player]
            if not p_stats.empty:
                m = calculate_metrics(p_stats, group_power=gp)
                r = apply_goals(add_rank(m, "kill_points"))
                r["report_date"] = imp["report_date"]
                history_rows.append(r)
        except Exception: continue
    if not history_rows: return st.warning("No data found.")
    player_data = pd.concat(history_rows, ignore_index=True).sort_values("report_date")
    latest = player_data.iloc[-1]
    
    status_translation = {"Aprovado": "Goal Reached", "Pendente": "Pending", "Abaixo da meta": "Goal Missed"}
    l_status = status_translation.get(latest['status'], latest['status'])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Power", f"{fmt_m(int(latest['power']))}M")
    c2.metric("KP (Latest)", fmt_k(int(latest['kill_points'])))
    c3.metric("Deaths T4eq (Latest)", fmt_k(int(latest.get('dead_equiv', 0))))
    c4.metric("Current Status", l_status)
    if px is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data['kill_points'], mode='lines+markers', name='KP', line=dict(color='#d4a847')))
        fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data.get('dead_equiv',0), mode='lines+markers', name='Deaths T4eq', line=dict(color='#4a7cba')))
        fig.update_layout(title=f"Cumulative stats — {selected_player}", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ab0cc", family="Inter"))
        st.plotly_chart(fig, use_container_width=True)

def show_history(storage, imports, group_power):
    st.markdown('<div class="sec-label">Compare two reports</div>', unsafe_allow_html=True)
    if len(imports) < 2: return st.info("Import at least 2 reports to compare.")
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    labels = ordered["label"].tolist()
    ca, cb = st.columns(2)
    with ca: la = st.selectbox("Base", labels, index=0, key="ha")
    with cb: lb = st.selectbox("Compare to", labels, index=min(1,len(labels)-1), key="hb")
    if la != lb:
        id_a, id_b = ordered.loc[ordered["label"].eq(la),"id"].iloc[0], ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
        delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
        top = calculate_metrics(delta, group_power=group_power).sort_values("kill_points",ascending=False).head(15)
        if not top.empty and px is not None:
            fig = px.bar(top.sort_values("kill_points",ascending=True), x="kill_points", y="username", orientation="h", color_discrete_sequence=["#d4a847"])
            fig.update_layout(showlegend=False, margin=dict(t=10,b=0,l=0,r=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ab0cc",family="Inter"))
            st.plotly_chart(fig, use_container_width=True)

def show_imports(imports, storage, *, is_admin, admin_enabled):
    st.markdown('<div class="sec-label">Imported reports</div>', unsafe_allow_html=True)
    st.dataframe(imports[["report_date","filename","row_count","imported_at"]], use_container_width=True, hide_index=True)
    if admin_enabled and is_admin:
        st.markdown('<div class="sec-label">Delete import</div>', unsafe_allow_html=True)
        to_del = st.selectbox("Select",["— —", *imports["label"].tolist()])
        if to_del != "— —" and st.button("Confirm delete", type="secondary", use_container_width=True):
            if storage.delete_import(imports.loc[imports["label"].eq(to_del)].iloc[0]["id"]): st.success("Deleted."); st.rerun()

def show_help():
    st.markdown('<div class="sec-label">Quick Reference</div>', unsafe_allow_html=True)
    st.markdown("**KP Formula:** `T5×20 + T4×10 + T3×4 + T2×2 + T1×0.2`\n\n**Base Power Rule:** Fixed on first report date.")

if __name__ == "__main__":
    main()
