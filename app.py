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
# OTIMIZAÇÃO DE PERFORMANCE (CACHE E VETORIZAÇÃO)
# Utilizamos pd.concat e groupby nativos do Pandas para evitar loops (iterrows),
# reduzindo drasticamente o tempo de processamento das planilhas.
# -----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def compute_accumulated_sum(_storage, imports: pd.DataFrame, group_power: int, date_from: date | None = None, date_to: date | None = None) -> tuple[pd.DataFrame, str, str]:
    ordered = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    ordered["_d"] = pd.to_datetime(ordered["report_date"]).dt.date

    # Filtra as datas
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

    # Passo 1: Carregar todos os DataFrames e colocá-los em uma lista
    all_stats_dfs = []
    for _, imp_row in ordered.iterrows():
        # Carrega a planilha a partir do storage
        stats = _storage.load_stats(imp_row["id"])
        
        # Garante que o character_id seja string para não dar erro no agrupamento
        stats["character_id"] = stats["character_id"].astype(str)
        all_stats_dfs.append(stats)

    if not all_stats_dfs:
        return pd.DataFrame(), "", ""

    # Passo 2: Juntar tudo em um único super DataFrame
    combined_df = pd.concat(all_stats_dfs, ignore_index=True)

    # Passo 3: Limpar e converter as colunas numéricas de uma só vez (muito mais rápido)
    for col in sum_columns:
        if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0)

    # Passo 4: Definir regras de agregação
    # Para as colunas numéricas, queremos a soma. Para username e aliança, o último valor registrado.
    agg_funcs = {col: 'sum' for col in sum_columns if col in combined_df.columns}
    agg_funcs["username"] = 'last'
    
    if "alliance" in combined_df.columns:
        agg_funcs["alliance"] = 'last'

    # Passo 5: Agrupar por jogador e aplicar a soma em C (C engine do Pandas)
    result_df = combined_df.groupby("character_id").agg(agg_funcs).reset_index()

    # Passo 6: Pegar o poder do primeiro dia
    first_import_id = ordered.iloc[0]["id"]
    first_stats = _storage.load_stats(first_import_id)
    first_stats["character_id"] = first_stats["character_id"].astype(str)
    first_stats["power"] = pd.to_numeric(first_stats["power"], errors='coerce').fillna(0)

    # Cria um dicionário mapeando o ID do personagem ao poder inicial para busca instantânea (O(1))
    power_map = dict(zip(first_stats["character_id"], first_stats["power"]))
    
    # Aplica o poder inicial ao resultado (se não existir no 1º dia, fica 0)
    result_df["power"] = result_df["character_id"].map(power_map).fillna(0)

    # Passo 7: Aplicar cálculos de métricas e ranking (usando suas funções customizadas originais)
    metrics = calculate_metrics(result_df, group_power=group_power)
    ranked  = apply_goals(add_rank(metrics, "kill_points"))

    # Tradução do status
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
        
        # Certifique-se de que a função _upload_section() existe no seu código completo importado
        try:
            _upload_section(storage)
        except NameError:
            st.caption("Upload block hidden for now. Please ensure `_upload_section` is defined.")

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
    with tabs[0]: 
        # try/except incluído para caso você ainda precise definir as funções show_* em outro lugar
        try: show_ranking(ranked, key_prefix="main")
        except NameError: st.info("Defina a função show_ranking()")
    with tabs[1]: 
        try: show_kvk(storage, imports, gp, ranked, is_admin=is_admin, admin_enabled=admin_enabled)
        except NameError: pass
    with tabs[2]: 
        try: show_hof(storage, imports, gp, is_admin=is_admin, admin_enabled=admin_enabled)
        except NameError: pass
    with tabs[3]: 
        try: show_kingdom(ranked, imports, storage, gp)
        except NameError: pass
    with tabs[4]: 
        try: show_profile(storage, imports, gp)
        except NameError: pass
    with tabs[5]: 
        try: show_help()
        except NameError: pass
    if admin_enabled and is_admin:
        with tabs[6]: 
            try: show_history(storage, imports, gp)
            except NameError: pass
        with tabs[7]: 
            # Correção do erro de corte aplicado aqui:
            try: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
            except NameError: pass

if __name__ == "__main__":
    main()
