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
from hall_of_fame import load_hall, list_kvks
from storage import create_storage

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:
    px = None; go = None

st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — THEME: "SOVEREIGN SLATE" (Single Dark Blue Theme)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _css() -> str:
    # Cores Base
    bg_main        = "#0e1a2b"       # Fundo geral (Azul petróleo escuro)
    bg_surface     = "#162233"       # Fundo dos cards/tabelas (Azul meia-noite)
    bg_surface_alt = "#1c2a3f"       # Fundo para hover/destaques
    border_color   = "#2a3f5e"       # Cor das bordas
    text_main      = "#f0f4fa"       # Texto principal (Branco gelo)
    text_sub       = "#9ab0cc"       # Texto secundário
    text_muted     = "#5a7294"       # Texto escuro/mudo
    
    # Cores de Destaque
    gold           = "#d4a847"       # Ouro (KP, Topo)
    gold_hi        = "#e6c268"       # Ouro claro
    blue_accent    = "#4a7cba"       # Azul cobalto (Mortes, Ações)
    green_ok       = "#3ba37a"       # Verde (Aprovado)
    yellow_pend    = "#d4a03a"       # Amarelo (Pendente)
    red_alert      = "#c95a4e"       # Vermelho (Abaixo)
    
    # Sidebar
    sb_bg          = "#0a131f"
    sb_text        = "#8398b5"
    
    # Cores de Tier
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

/* ─── SIDEBAR ───────────────────────────────────────────── */
section[data-testid="stSidebar"] {{ background: {sb_bg} !important; border-right: 1px solid {border_color} !important; }}
section[data-testid="stSidebar"] > div {{ padding: 1.5rem 1rem !important; }}
section[data-testid="stSidebar"] * {{ color: {sb_text} !important; }}
section[data-testid="stSidebar"] .stSuccess p {{ color: {green_ok} !important; }}
section[data-testid="stSidebar"] .stError p {{ color: {red_alert} !important; }}
section[data-testid="stSidebar"] .stWarning p {{ color: {yellow_pend} !important; }}
.sb-sec {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .14em; color: {sb_text}; border-bottom: 1px solid {border_color}; padding-bottom: 6px; margin: 14px 0 10px; }}

/* ─── METRICS / KPIs ────────────────────────────────────── */
[data-testid="stMetric"] {{
  background: {bg_surface} !important; border: 1px solid {border_color} !important;
  border-radius: 8px !important; padding: 16px 20px !important;
  position: relative; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}}
[data-testid="stMetric"]::after {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background:{blue_accent}; }}
[data-testid="stMetricLabel"] {{ font-size:.62rem !important; font-weight:600 !important; text-transform:uppercase; letter-spacing:.08em; color:{text_sub} !important; }}
[data-testid="stMetricValue"] {{ font-family:'JetBrains Mono',monospace !important; font-size:1.6rem !important; font-weight:600 !important; color:{text_main} !important; letter-spacing:-.03em; }}

/* ─── TABS ──────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {{ border-bottom: 1px solid {border_color}; gap: 0; background: transparent; flex-wrap: wrap; }}
[data-testid="stTabs"] button[role="tab"] {{
  font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em;
  color: {text_muted} !important; padding: 10px 20px; border-bottom: 2px solid transparent;
  border-radius: 0; background: transparent !important; transition: color .2s, border-color .2s;
}}
[data-testid="stTabs"] button[role="tab"]:hover {{ color: {gold} !important; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ color: {gold} !important; border-bottom-color: {gold} !important; background: transparent !important; }}

/* ─── INPUTS ────────────────────────────────────────────── */
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

/* ─── BUTTONS ───────────────────────────────────────────── */
[data-testid="stButton"] button {{
  background: {blue_accent} !important; color: #fff !important; border: none !important; border-radius: 6px !important;
  font-weight: 700 !important; font-size: .78rem !important; text-transform: uppercase; letter-spacing: .08em;
  transition: all .2s; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}}
[data-testid="stButton"] button:hover {{ background: {gold} !important; transform: translateY(-1px); color: #000 !important; }}
[data-testid="stButton"] button[kind="secondary"] {{ background: transparent !important; border: 1px solid {border_color} !important; color: {text_sub} !important; }}

/* ─── TABLES & DATAFRAMES ──────────────────────────────── */
[data-testid="stDataFrame"] {{ border: 1px solid {border_color} !important; border-radius: 8px !important; overflow: hidden; background: {bg_surface}; }}
[data-testid="stDataFrame"] th {{ background: {bg_surface_alt} !important; color: {text_sub} !important; }}
[data-testid="stDataFrame"] td {{ color: {text_main} !important; }}

hr {{ border-color: {border_color} !important; margin: 1.2rem 0 !important; }}

/* ─── HEADER ────────────────────────────────────────────── */
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

/* ─── TIER PILLS ────────────────────────────────────────── */
.tier-pills {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 18px; }}
.tier-pill {{ padding: 4px 12px; border-radius: 4px; font-size: .65rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; white-space: nowrap; border: 1px solid; }}
.tp-t5 {{ color:{t5_color}; border-color:{t5_color}; background: rgba(212, 168, 71, 0.1); }}
.tp-t4 {{ color:{t4_color}; border-color:{t4_color}; background: rgba(207, 111, 58, 0.1); }}
.tp-t3 {{ color:{t3_color}; border-color:{t3_color}; background: rgba(125, 94, 184, 0.1); }}
.tp-t2 {{ color:{t2_color}; border-color:{t2_color}; background: rgba(63, 147, 166, 0.1); }}
.tp-t1 {{ color:{t1_color}; border-color:{t1_color}; background: rgba(90, 114, 148, 0.1); }}
.tp-eq {{ color:{text_muted}; border-color:{border_color}; background: rgba(255,255,255,0.03); }}

/* ─── SECTION LABELS ────────────────────────────────────── */
.sec-label {{ font-size: .6rem; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; color: {gold}; display: flex; align-items: center; gap: 10px; margin: 20px 0 12px; }}
.sec-label::after {{ content: ''; flex: 1; height: 1px; background: {border_color}; }}

/* ─── BADGES ────────────────────────────────────────────── */
.sbadge {{ display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 4px; font-size: .63rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; white-space: nowrap; border: 1px solid; }}
.sbadge-ok {{ color:{green_ok}; border-color:{green_ok}; background: rgba(59, 163, 122, 0.15); }}
.sbadge-wa {{ color:{yellow_pend}; border-color:{yellow_pend}; background: rgba(212, 160, 58, 0.15); }}
.sbadge-er {{ color:{red_alert}; border-color:{red_alert}; background: rgba(201, 90, 78, 0.15); }}

/* ─── MEMBER ROWS (RANKING) ────────────────────────────── */
.mrow {{ background: {bg_surface}; border: 1px solid {border_color}; border-radius: 6px; margin-bottom: 6px; overflow: hidden; transition: border-color .2s, background .2s; }}
.mrow:hover {{ border-color: {gold}; background: {bg_surface_alt}; }}
.mrow.ok {{ border-left: 3px solid {green_ok}; }}
.mrow.wa {{ border-left: 3px solid {yellow_pend}; }}
.mrow.er {{ border-left: 3px solid {red_alert}; }}

.mrow-sum {{ 
  display: grid; 
  grid-template-columns: 40px 1fr 200px 160px 90px; 
  align-items: center; 
  gap: 12px; 
  padding: 14px 18px !important; 
  cursor: pointer; 
}}
.mrow-rank {{ font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 600; color: {text_muted}; text-align: right; min-width: 40px; }}
.mrow-info {{ min-width: 0; }}
.mrow-name {{ font-size: .95rem; font-weight: 700; color: {text_main}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mrow-meta {{ font-size: .64rem; color: {text_sub}; margin-top: 2px; }}

.mrow-gauges {{ display: flex; flex-direction: column; gap: 5px; min-width: 180px; flex: 1; }}
.gauge-head {{ display: flex; justify-content: space-between; font-size: .58rem; color: {text_sub}; margin-bottom: 2px; }}
.gauge-track {{ height: 5px; background: {bg_main}; border-radius: 99px; overflow: hidden; border: 1px solid {border_color}; }}
.gauge-fill {{ height: 100%; border-radius: 99px; transition: width .6s cubic-bezier(.4,0,.2,1); }}
.gauge-fill.kp {{ background: {gold}; }}
.gauge-fill.dead {{ background: {blue_accent}; }}
.gauge-fill.full {{ background: {green_ok}; }}

/* ─── MEMBER DETAILS (EXPANDED) ────────────────────────── */
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

/* ─── TIER TABLES ───────────────────────────────────────── */
.tier-table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
.tier-table th {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em; color: {text_sub}; padding: 6px 10px; text-align: right; border-bottom: 1px solid {border_color}; }}
.tier-table th:first-child {{ text-align: left; }}
.tier-table td {{ font-family: 'JetBrains Mono', monospace; font-size: .75rem; color: {text_main}; padding: 6px 10px; text-align: right; border-bottom: 1px solid {bg_surface_alt}; }}
.tier-table td:first-child {{ text-align: left; color: {text_sub}; font-weight: 600; }}
.tier-table tr:last-child td {{ border-bottom: none; }}
.tier-table td.amber {{ color: {gold}; }}
.tier-table td.blue  {{ color: {blue_accent}; }}
.tier-table td.equiv {{ color: {text_muted}; font-size: .68rem; }}

/* ─── KINGDOM CARDS ────────────────────────────────────── */
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

/* ─── GENERAL UTILS ────────────────────────────────────── */
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

# ══════════════════════════════════════════════════════════════════════════════
# Storage / State
# ══════════════════════════════════════════════════════════════════════════════

STATUS_CLS   = {"Aprovado":"ok","Pendente":"wa","Abaixo da meta":"er"}
STATUS_ICON  = {"Aprovado":"●","Pendente":"◐","Abaixo da meta":"○"}
STATUS_LABEL = {"Aprovado":"Approved","Pendente":"Pending","Abaixo da meta":"Below"}

@st.cache_resource
def get_storage():
    return create_storage()

def get_secret(name):
    v = os.getenv(name)
    if v: return v
    try: v = st.secrets.get(name)
    except: v = None
    return str(v) if v else None


# ══════════════════════════════════════════════════════════════════════════════
# Accumulated ranking helpers — SOMATÓRIO REAL
# ══════════════════════════════════════════════════════════════════════════════

def compute_accumulated_sum(storage, imports: pd.DataFrame, group_power: int,
                            date_from: date | None = None,
                            date_to: date | None = None) -> tuple[pd.DataFrame, str, str]:
    """
    SOMA todos os KP e mortes de cada jogador em TODOS os relatórios dentro do período.
    Para cada jogador: KP_total = soma dos KP de cada relatório no intervalo.
    
    Colunas somadas: kills, deaths, rallies, helps, resources, barbarians
    Power: pega o valor do ÚLTIMO relatório no período
    
    Retorna (ranked_df, first_date_str, last_date_str).
    """
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

    # Colunas que serão SOMADAS em todos os relatórios
    sum_columns = [
        "t1_kills", "t2_kills", "t3_kills", "t4_kills", "t5_kills",
        "t1_deaths", "t2_deaths", "t3_deaths", "t4_deaths", "t5_deaths",
        "rallies_joined", "rallies_started", "helps",
        "resources_gathered", "resources_assisted",
        "barbarians_killed", "barbarians_killed_7", "barbarians_killed_8",
    ]

    # Dicionário para acumular stats por character_id
    accumulated = {}

    for _, imp_row in ordered.iterrows():
        stats = storage.load_stats(imp_row["id"])
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
            
            # Soma os valores numéricos
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

    # Converte para DataFrame
    result_df = pd.DataFrame(list(accumulated.values()))
    
    # Para POWER: pegamos o valor do ÚLTIMO relatório, não a soma
    last_import_id = ordered.iloc[-1]["id"]
    last_stats = storage.load_stats(last_import_id)
    last_power_map = {}
    for _, player in last_stats.iterrows():
        cid = str(player["character_id"])
        try:
            last_power_map[cid] = int(float(player["power"])) if pd.notna(player["power"]) else 0
        except (ValueError, TypeError):
            last_power_map[cid] = 0
    
    # Atualiza o power para o valor do último relatório
    for idx, row in result_df.iterrows():
        cid = str(row["character_id"])
        if cid in last_power_map:
            result_df.at[idx, "power"] = last_power_map[cid]
        else:
            result_df.at[idx, "power"] = 0

    # Remove colunas auxiliares
    result_df = result_df.drop(columns=["_report_count"], errors="ignore")
    
    # Calcula métricas (KP, dead_equiv, etc.)
    metrics = calculate_metrics(result_df, group_power=group_power)
    ranked  = apply_goals(add_rank(metrics, "kill_points"))
    
    return ranked, first_date, last_date


def compute_kvk_accumulated(storage, imports: pd.DataFrame, group_power: int,
                              start_d: date, end_d: date) -> pd.DataFrame:
    """Somatório de todos os relatórios na janela do KvK."""
    result, _, _ = compute_accumulated_sum(storage, imports, group_power, start_d, end_d)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

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
        handle_upload(storage)

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
        
        # Filtro de Poder Mínimo
        min_power = st.number_input(
            "Power Min (Millions)", 
            min_value=0, 
            value=0, 
            step=1, 
            format="%d",
            help="Filter governors with power below this value"
        )
        min_power_value = min_power * 1_000_000
        
        # Filtro de KP Mínimo
        min_kp = st.number_input(
            "KP Min", 
            min_value=0, 
            value=0, 
            step=1000, 
            format="%d",
            help="Filter governors with KP below this value"
        )
        
        # Filtro de % KP
        min_kp_pct = st.slider(
            "% KP Min", 
            min_value=0, 
            max_value=100, 
            value=0, 
            step=5,
            help="Filter by minimum % of KP goal reached"
        )
        
        # Filtro de % Mortes
        min_dead_pct = st.slider(
            "% Deaths Min", 
            min_value=0, 
            max_value=100, 
            value=0, 
            step=5,
            help="Filter by minimum % of death goal reached"
        )
        
        # Botão para resetar filtros
        if st.button("🔄 Reset Filters", use_container_width=True, type="secondary"):
            st.session_state.min_power = 0
            st.session_state.min_kp = 0
            st.session_state.min_kp_pct = 0
            st.session_state.min_dead_pct = 0
            st.rerun()
        
        st.markdown('<div class="sb-sec">Admin</div>', unsafe_allow_html=True)
        admin_enabled, is_admin = admin_panel()

    gp = default_group_power(storage, imports)

    # ── Date range filter ──
    all_dates = sorted(imports["report_date"].unique())
    min_d = pd.to_datetime(all_dates[0]).date()
    max_d = pd.to_datetime(all_dates[-1]).date()

    st.markdown('<div class="sec-label" style="margin-top:0">Analysis Period</div>', unsafe_allow_html=True)
    
    with st.container():
        dcol1, dcol2, dcol3, dcol4, dcol5 = st.columns([1.5, 1.5, 1, 1, 3])
        
        with dcol1:
            date_from = st.date_input(
                "Start Date", 
                value=min_d, 
                min_value=min_d, 
                max_value=max_d, 
                key="main_date_from",
                format="YYYY-MM-DD"
            )
        with dcol2:
            date_to = st.date_input(
                "End Date", 
                value=max_d, 
                min_value=min_d, 
                max_value=max_d, 
                key="main_date_to",
                format="YYYY-MM-DD"
            )
        with dcol3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 This Month", key="btn_this_month", use_container_width=True, 
                         help="Set period to current month"):
                today = date.today()
                date_from = today.replace(day=1)
                date_to = today
                st.rerun()
        with dcol4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📅 All Time", key="btn_all_time", use_container_width=True,
                         help="Set period to all available data"):
                date_from = min_d
                date_to = max_d
                st.rerun()
        with dcol5:
            n_imports_in_range = len(
                imports[
                    (pd.to_datetime(imports["report_date"]).dt.date >= date_from) &
                    (pd.to_datetime(imports["report_date"]).dt.date <= date_to)
                ]
            )
            st.markdown(f"""
            <div style="padding-top:8px;font-size:.72rem;color:#9ab0cc">
                <span style="color:#d4a847;font-weight:600">{n_imports_in_range}</span> reports in period
                <br><span style="font-size:.62rem">Sum of KP and deaths across all reports</span>
            </div>
            """, unsafe_allow_html=True)

    # Validação de data
    if date_from > date_to:
        st.error("⚠️ Start date must be before end date.")
        return

    # Usa a nova função de SOMATÓRIO
    ranked, first_date, last_date = compute_accumulated_sum(
        storage, imports, gp,
        date_from=date_from,
        date_to=date_to,
    )

    if ranked.empty:
        st.warning("No reports found in the selected date range.")
        return

    # Aplica filtros da sidebar
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

    # Mostra filtros ativos
    active_filters = []
    if min_power_value > 0:
        active_filters.append(f"Power ≥ {min_power}M")
    if min_kp > 0:
        active_filters.append(f"KP ≥ {fmt_k(min_kp)}")
    if min_kp_pct > 0:
        active_filters.append(f"KP ≥ {min_kp_pct}%")
    if min_dead_pct > 0:
        active_filters.append(f"Deaths ≥ {min_dead_pct}%")
    
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
      <div class="rok-caption-item">Method <span class="rok-caption-val">Sum of all reports</span></div>
    </div>
    """, unsafe_allow_html=True)

    tab_labels = ["⚔ Ranking", "🛡 KvK", "🏆 Hall of Fame", "🏰 Kingdom", "👤 Profile", "❓ Help"]
    if admin_enabled and is_admin:
        tab_labels.append("📈 History")
        tab_labels.append("📁 Imports")

    tabs = st.tabs(tab_labels)
    with tabs[0]: show_ranking(ranked, key_prefix="main")
    with tabs[1]: show_kvk(storage, imports, gp, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[2]: show_hof(storage, imports, gp, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[3]: show_kingdom(ranked, imports, storage, gp)
    with tabs[4]: show_profile(storage, imports, gp)
    with tabs[5]: show_help()
    if admin_enabled and is_admin:
        with tabs[6]: show_history(storage, imports, gp)
        with tabs[7]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar helpers
# ══════════════════════════════════════════════════════════════════════════════

def handle_upload(storage):
    pwd = get_secret("ADMIN_PASSWORD")
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.markdown("""
        <div class="upload-lock">
          <div class="upload-lock-icon">🔒</div>
          <div class="upload-lock-text">Upload restricted to leadership</div>
        </div>
        """, unsafe_allow_html=True)
        up_pwd = st.text_input("Password", type="password", key="up_pwd",
                                label_visibility="collapsed", placeholder="Access password...")
        if st.button("Unlock", use_container_width=True):
            if (not pwd) or is_admin_authenticated(pwd, up_pwd):
                st.session_state.upload_auth = True; st.rerun()
            else:
                st.error("Wrong password")
        return

    st.success("✓ Access granted")
    if st.button("Lock", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False; st.rerun()

    uploaded = st.file_uploader("statsExport (.xlsx)", type=["xlsx","xls"])
    if not uploaded: return
    safe_name   = re.sub(r"[^\w.\-]","_", uploaded.name)
    report_date = st.date_input("Report date",
                                 value=extract_report_date_from_name(safe_name) or date.today())
    if not st.button("Save report", type="primary", use_container_width=True): return

    with st.spinner("Processing..."):
        try:
            fb = uploaded.getvalue()
            if len(fb) > 50*1024*1024: st.error("File too large (max 50 MB)."); return
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            import_id_saved, created = storage.save_import(
                filename=safe_name, report_date=report_date.isoformat(),
                file_hash=file_sha256(fb), stats=stats,
            )
        except Exception as e: st.error(f"Error: {e}"); return

    if created:
        st.success(f"✓ {len(stats):,} members saved")
    else:
        st.warning("File already imported")
    st.rerun()


def prepare_imports(imports):
    out = imports.copy()
    out["report_date"] = pd.to_datetime(out["report_date"]).dt.date.astype(str)
    out["imported_at"] = out["imported_at"].astype(str)
    out["label"]       = out["report_date"] + " — " + out["filename"].astype(str)
    return out

@st.cache_data(ttl=300)
def _cached_gp(label, first_id):
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"],errors="coerce").fillna(0).sum())

def default_group_power(storage, imports):
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    return _cached_gp(storage.label, ordered.iloc[0]["id"])

def admin_panel():
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


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Ranking
# ══════════════════════════════════════════════════════════════════════════════

def show_ranking(ranked_full: pd.DataFrame, key_prefix: str = "main") -> None:
    fc1, fc2, fc3 = st.columns([5, 2, 2])
    with fc1:
        search = st.text_input("search", placeholder="Search member or Character ID…",
                                key=f"{key_prefix}_rank_search", label_visibility="collapsed")
    with fc2:
        sf = st.selectbox("status", ["All","Approved","Pending","Below goal"],
                          key=f"{key_prefix}_rank_sf", label_visibility="collapsed")
    with fc3:
        sort_by = st.selectbox("sort",
                               ["KP ↓","Power ↓","% KP ↓","% Deaths ↓","Name ↑"],
                               key=f"{key_prefix}_rank_sort", label_visibility="collapsed")

    df = ranked_full.copy()

    # Emblemas
    top_5_pct_deaths = df['dead_equiv'].quantile(0.95) if 'dead_equiv' in df.columns else float('inf')
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

    if search.strip():
        n = search.strip().lower()
        df = df[df["username"].astype(str).str.lower().str.contains(n,regex=False,na=False)
                |df["character_id"].astype(str).str.lower().str.contains(n,regex=False,na=False)]

    status_map_en2pt = {"Approved":"Aprovado","Pending":"Pendente","Below goal":"Abaixo da meta"}
    if sf != "All":
        df = df[df["status"] == status_map_en2pt.get(sf, sf)]

    sort_map = {
        "KP ↓":("kill_points",False),"Power ↓":("power",False),
        "% KP ↓":("kp_pct",False),"% Deaths ↓":("dead_pct",False),"Name ↑":("username",True),
    }
    scol, sasc = sort_map.get(sort_by, ("kill_points",False))
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    st.markdown(f'<div class="sec-label">Governors · {len(df):,} of {len(ranked_full):,}</div>',
                unsafe_allow_html=True)

    page_size = st.selectbox("Per page",[10,25,50,100],index=1,
                              key=f"{key_prefix}_rank_ps",label_visibility="collapsed")
    total_pg  = max(1,-(-len(df)//page_size))
    col_pg1, col_pg2 = st.columns([1,5])
    with col_pg1:
        page = st.number_input("Page",min_value=1,max_value=total_pg,value=1,
                                key=f"{key_prefix}_rank_pg",label_visibility="collapsed")
    with col_pg2:
        st.markdown(f'<div style="font-size:.65rem;color:#9ab0cc;padding-top:8px">Page {page} of {total_pg}</div>',
                    unsafe_allow_html=True)

    start = (page-1)*page_size
    _render_members(df.iloc[start:start+page_size], key_prefix=key_prefix)

    with st.expander("Export full table →", expanded=False):
        cols_show = {
            "rank":"#","username":"Governor","character_id":"ID","power":"Power","power_band":"Band",
            "kill_points":"KP","kp_goal":"KP Goal","t5_kills":"T5K","t4_kills":"T4K",
            "t3_kills":"T3K","t2_kills":"T2K","t1_kills":"T1K",
            "t5_deaths":"T5D","t4_deaths":"T4D","t3_deaths":"T3D","t2_deaths":"T2D","t1_deaths":"T1D",
            "dead_t4_goal":"Death Goal","dead_equiv":"T4 Equiv.","status":"Status",
        }
        avail = {k:v for k,v in cols_show.items() if k in df.columns}
        out   = df[list(avail.keys())].rename(columns=avail)
        st.dataframe(out, use_container_width=True, hide_index=True)
        st.download_button("⬇ Download CSV", data=df.to_csv(index=False).encode(),
                            file_name="ranking.csv", mime="text/csv",
                            key=f"{key_prefix}_dl_csv")


def _render_members(df: pd.DataFrame, key_prefix: str = "main") -> None:
    """
    Renders each member as a clickable expander.
    Clicking the row label (governor name) opens the detail panel.
    """
    for i, (_, row) in enumerate(df.iterrows()):
        cls    = STATUS_CLS.get(row["status"], "er")
        kp_w   = min(float(row.get("kp_pct",0))*100, 100)
        dead_w = min(float(row.get("dead_pct",0))*100, 100)
        kp_gap   = int(row.get("kp_gap",0))
        dead_gap = int(row.get("dead_gap_t4",0))

        kp_fc   = "full" if kp_w   >= 100 else "kp"
        dead_fc = "full" if dead_w >= 100 else "dead"

        badge_cls = f"sbadge-{cls}"
        badge = (f'<span class="sbadge {badge_cls}">'
                 f'{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</span>')

        # Calcular valores para exibição lateral
        total_kp = int(row['kill_points'])
        total_dead = int(row.get('dead_equiv', 0))

        with st.expander(
            label=f"#{int(row['rank'])}  {row['username']}",
            expanded=False,
        ):
            st.markdown(f"""
            <div class="mrow {cls}" style="margin-bottom:8px">
              <div class="mrow-sum" style="cursor:default; padding: 14px 18px;">
                <div class="mrow-rank" style="font-size: 1rem; min-width: 40px;">#{int(row['rank'])}</div>
                <div class="mrow-info">
                  <div class="mrow-name" style="font-size: 0.95rem;">{row['username']} {row.get('emblems', '')}</div>
                  <div class="mrow-meta">{fmt_m(int(row['power']))}M power · {row.get('power_band','—')} · ID {row.get('character_id','—')}</div>
                </div>
                
                <div class="mrow-gauges" style="min-width: 180px; flex: 1;">
                  <div>
                    <div class="gauge-head"><span>KP {kp_w:.0f}%</span><span>{fmt_k(int(row['kill_points']))}</span></div>
                    <div class="gauge-track"><div class="gauge-fill {kp_fc}" style="width:{kp_w:.1f}%"></div></div>
                  </div>
                  <div>
                    <div class="gauge-head"><span>D {dead_w:.0f}%</span><span>{fmt_k(int(row.get('dead_equiv',0)))} T4eq</span></div>
                    <div class="gauge-track"><div class="gauge-fill {dead_fc}" style="width:{dead_w:.1f}%"></div></div>
                  </div>
                </div>

                <div style="display: flex; gap: 20px; align-items: center; padding-left: 10px; border-left: 1px solid #2a3f5e;">
                    <div style="text-align: right;">
                        <div style="font-size: 0.55rem; color: #9ab0cc; text-transform: uppercase; font-weight: 700;">Total KP</div>
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; color: #d4a847; line-height: 1.2;">{fmt_k(total_kp)}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.55rem; color: #9ab0cc; text-transform: uppercase; font-weight: 700;">Mortos (T4)</div>
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; color: #4a7cba; line-height: 1.2;">{fmt_k(total_dead)}</div>
                    </div>
                </div>
                
                <div style="margin-left: 10px;">{badge}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            t5d = int(row.get("t5_deaths",0))
            t4d = int(row.get("t4_deaths",0))
            t3d = int(row.get("t3_deaths",0))
            t2d = int(row.get("t2_deaths",0))
            t1d = int(row.get("t1_deaths",0))
            dead_equiv = int(row.get("dead_equiv",0))

            kp_fc_det   = "full-kp"   if kp_w   >= 100 else "kp"
            dead_fc_det = "full-dead" if dead_w >= 100 else "dead"

            kp_gap_html   = (f'<div class="mdet-gap ok">✓ KP goal reached</div>'
                             if kp_gap == 0
                             else f'<div class="mdet-gap warn">⚠ {fmt_k(kp_gap)} KP missing</div>')
            dead_gap_html = (f'<div class="mdet-gap ok">✓ Death goal reached</div>'
                             if dead_gap == 0
                             else f'<div class="mdet-gap warn">⚠ {fmt_k(dead_gap)} T4eq missing</div>')

            accent = '#3ba37a' if cls=='ok' else '#d4a03a' if cls=='wa' else '#c95a4e'
            st.markdown(f"""
            <div class="mdet">
              <div class="mdet-accent-bar" style="background:{accent}"></div>
              <div class="mdet-grid">
                <div>
                  <div class="mdet-block-label">Kill Points</div>
                  <div class="mdet-block-val">{fmt_int(int(row['kill_points']))}</div>
                  <div class="mdet-block-sub">Goal: {fmt_int(int(row['kp_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head">
                      <span>{kp_w:.1f}% reached</span>
                      <span>{fmt_int(int(row['kill_points']))} / {fmt_int(int(row['kp_goal']))}</span>
                    </div>
                    <div class="mdet-prog-track">
                      <div class="mdet-prog-fill {kp_fc_det}" style="width:{kp_w:.1f}%"></div>
                    </div>
                  </div>
                  {kp_gap_html}
                </div>
                <div>
                  <div class="mdet-block-label">Deaths (T4 equiv.)</div>
                  <div class="mdet-block-val">{fmt_int(dead_equiv)}</div>
                  <div class="mdet-block-sub">Goal: {fmt_int(int(row['dead_t4_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head">
                      <span>{dead_w:.1f}% reached</span>
                      <span>{fmt_int(dead_equiv)} / {fmt_int(int(row['dead_t4_goal']))}</span>
                    </div>
                    <div class="mdet-prog-track">
                      <div class="mdet-prog-fill {dead_fc_det}" style="width:{dead_w:.1f}%"></div>
                    </div>
                  </div>
                  {dead_gap_html}
                </div>
              </div>
            """, unsafe_allow_html=True)

            dc1, dc2 = st.columns(2)
            with dc1:
                t5k = int(row.get("t5_kills",0)); t4k = int(row.get("t4_kills",0))
                t3k = int(row.get("t3_kills",0)); t2k = int(row.get("t2_kills",0))
                t1k = int(row.get("t1_kills",0))
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


# ══════════════════════════════════════════════════════════════════════════════
# Tab — KvK
# ══════════════════════════════════════════════════════════════════════════════

def show_kvk(storage, imports: pd.DataFrame, group_power: int,
             *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#4a7cba">
      <div class="rok-header-emblem" style="background:#162233; border-color:#4a7cba">🛡</div>
      <div>
        <div class="rok-header-title">KvK Events</div>
        <div class="rok-header-sub">Performance windows for Kingdom vs Kingdom</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    if admin_enabled and is_admin:
        with st.expander("➕ Create new KvK event", expanded=False):
            c1, c2, c3 = st.columns([3,2,2])
            with c1:
                kvk_name = st.text_input("Event name", placeholder="e.g. KvK Heroic Anthem",
                                          key="kvk_new_name")
            with c2:
                kvk_start = st.date_input("Start date", key="kvk_new_start")
            with c3:
                kvk_end = st.date_input("End date", key="kvk_new_end")
            if st.button("Create event", type="primary", key="kvk_create_btn"):
                if not kvk_name.strip():
                    st.error("Please enter an event name.")
                elif kvk_end < kvk_start:
                    st.error("End date must be after start date.")
                else:
                    storage.save_kvk_event(
                        name=kvk_name.strip(),
                        start_date=kvk_start.isoformat(),
                        end_date=kvk_end.isoformat(),
                    )
                    st.success(f"✓ Event '{kvk_name}' created")
                    st.rerun()

    events = storage.list_kvk_events()
    if events.empty:
        st.markdown('''
        <div class="empty-state">
          <div class="empty-state-icon">🛡</div>
          <div class="empty-state-title">No KvK events registered</div>
          <div class="empty-state-sub">An admin can create one above to start tracking kingdom performance.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    events = events.copy()
    events["start_date"] = pd.to_datetime(events["start_date"]).dt.date.astype(str)
    events["end_date"]   = pd.to_datetime(events["end_date"]).dt.date.astype(str)
    events["label"] = events["name"] + "  (" + events["start_date"] + " → " + events["end_date"] + ")"

    st.markdown('<div class="sec-label">Select event</div>', unsafe_allow_html=True)
    chosen_label = st.selectbox("Event", events["label"].tolist(), key="kvk_select",
                                 label_visibility="collapsed")
    event_row = events.loc[events["label"].eq(chosen_label)].iloc[0]

    start_d = pd.to_datetime(event_row["start_date"]).date()
    end_d   = pd.to_datetime(event_row["end_date"]).date()

    today = date.today()
    is_active  = start_d <= today <= end_d
    is_future  = start_d > today
    is_past    = end_d < today

    status_label = (
        "🟢 Active" if is_active else
        "🔵 Upcoming" if is_future else
        "⚫ Ended"
    )

    st.markdown(f'''
    <div class="kvk-event-card">
      <div>
        <div class="kvk-event-name">{event_row["name"]}</div>
        <div class="kvk-event-dates">{event_row["start_date"]} → {event_row["end_date"]}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <span style="font-size:.72rem;color:#9ab0cc">{status_label}</span>
        <div class="kvk-event-badge">KvK Window</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    if admin_enabled and is_admin:
        with st.expander("🗑 Delete this event", expanded=False):
            st.warning("Irreversible — this only deletes the event window, not the underlying reports.")
            if st.button("Confirm delete event", type="secondary", key="kvk_del_btn"):
                if storage.delete_kvk_event(event_row["id"]):
                    st.success("Deleted."); st.rerun()
                else:
                    st.error("Not found.")

    imports_cp = imports.copy()
    imports_cp["_d"] = pd.to_datetime(imports_cp["report_date"]).dt.date
    in_window = imports_cp[(imports_cp["_d"] >= start_d) & (imports_cp["_d"] <= end_d)].sort_values("_d")

    if in_window.empty:
        if is_future:
            st.info(f"⏳ This KvK starts on **{event_row['start_date']}**. Reports uploaded from that date onwards will appear here automatically.")
        else:
            st.warning("No reports fall within this event's date range yet.")
        return

    # Usa somatório real
    ranked_window = compute_kvk_accumulated(storage, imports, group_power, start_d, end_d)

    n_reports = len(in_window)
    st.caption(
        f"📊 **{n_reports}** report(s) in window · "
        f"**{in_window.iloc[0]['report_date']}** → **{in_window.iloc[-1]['report_date']}** · "
        f"Sum of all reports"
    )

    if ranked_window.empty:
        st.info("No player data available for this window yet.")
        return

    total    = len(ranked_window)
    approved = int((ranked_window["status"]=="Aprovado").sum())
    pending  = int((ranked_window["status"]=="Pendente").sum())
    below    = int((ranked_window["status"]=="Abaixo da meta").sum())
    kp_total = int(ranked_window["kill_points"].sum())
    aprov_pct = approved/total*100 if total else 0

    st.markdown('<div class="sec-label">Kingdom performance — this event</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kd-row">
      <div class="kd-card amber">
        <div class="kd-card-label">Total Kill Points</div>
        <div class="kd-card-value">{fmt_k(kp_total)}</div>
        <div class="kd-card-sub">earned in this event</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-label">Approved</div>
        <div class="kd-card-value">{approved}</div>
        <div class="kd-card-sub">of {total} members</div>
      </div>
      <div class="kd-card yellow">
        <div class="kd-card-label">Pending</div>
        <div class="kd-card-value">{pending}</div>
        <div class="kd-card-sub">close to goal</div>
      </div>
      <div class="kd-card red">
        <div class="kd-card-label">Below Goal</div>
        <div class="kd-card-value">{below}</div>
        <div class="kd-card-sub">needs attention</div>
      </div>
      <div class="kd-card blue">
        <div class="kd-card-label">Governors</div>
        <div class="kd-card-value">{total:,}</div>
        <div class="kd-card-sub">tracked in window</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not ranked_window.empty:
        top3 = ranked_window.sort_values("kill_points", ascending=False).head(3)
        discord_text = f"""**🛡️ {event_row['name']} · KvK Summary 🛡️**

**Kingdom Performance (K1602)**
⚔️ **Total KP Earned:** {fmt_k(kp_total)}
✅ **Approval Rate:** {aprov_pct:.1f}% ({approved}/{total} approved)
⚠️ **Below Goal:** {below} governors

**🏆 Top 3 Killers (KP):**
🥇 {top3.iloc[0]['username'] if len(top3)>0 else '-'} : {fmt_k(top3.iloc[0]['kill_points']) if len(top3)>0 else 0} KP
🥈 {top3.iloc[1]['username'] if len(top3)>1 else '-'} : {fmt_k(top3.iloc[1]['kill_points']) if len(top3)>1 else 0} KP
🥉 {top3.iloc[2]['username'] if len(top3)>2 else '-'} : {fmt_k(top3.iloc[2]['kill_points']) if len(top3)>2 else 0} KP"""

        with st.expander("💬 Generate Discord Summary"):
            st.code(discord_text, language="markdown")

    if px is not None and not ranked_window.empty:
        st.markdown('<div class="sec-label">Top performers — this event</div>', unsafe_allow_html=True)
        top20 = ranked_window.sort_values("kill_points",ascending=True).tail(20)
        cmap = {"Aprovado":"#3ba37a","Pendente":"#d4a03a","Abaixo da meta":"#c95a4e"}
        fig = px.bar(top20, x="kill_points", y="username", orientation="h",
                     color="status", color_discrete_map=cmap,
                     labels={"kill_points":"Kill Points","username":""})
        fig.update_layout(showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ab0cc", family="Inter"),
            yaxis=dict(tickfont=dict(size=11,color="#9ab0cc"),gridcolor="rgba(42, 63, 94, 0.5)"),
            xaxis=dict(tickfont=dict(size=10),gridcolor="rgba(42, 63, 94, 0.5)"))
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="sec-label">Individual ranking — this event</div>', unsafe_allow_html=True)
    show_ranking(ranked_window, key_prefix=f"kvk_{event_row['id']}")


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Hall of Fame
# ══════════════════════════════════════════════════════════════════════════════

def show_hof(storage, imports: pd.DataFrame, group_power: int,
             *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#d4a847">
      <div class="rok-header-emblem" style="background:#162233; border-color:#d4a847">🏆</div>
      <div>
        <div class="rok-header-title">Hall of Fame — K1602</div>
        <div class="rok-header-sub">Top 10 KP · Top 10 Deaths · By KvK Event</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    events = storage.list_kvk_events()
    if events.empty:
        st.markdown('''
        <div class="empty-state">
          <div class="empty-state-icon">🏆</div>
          <div class="empty-state-title">No KvK events created yet</div>
          <div class="empty-state-sub">An admin must create a KvK event in the 🛡 KvK tab first.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    events = events.copy()
    events["start_date"] = pd.to_datetime(events["start_date"]).dt.date.astype(str)
    events["end_date"]   = pd.to_datetime(events["end_date"]).dt.date.astype(str)
    events["label"]      = events["name"] + "  (" + events["start_date"] + " → " + events["end_date"] + ")"

    col_sel, col_info = st.columns([3, 3])
    with col_sel:
        chosen_label = st.selectbox("KvK Event", events["label"].tolist(),
                                     key="hof_kvk", label_visibility="collapsed")
    with col_info:
        st.markdown(
            f'<div style="font-size:.68rem;color:#9ab0cc;padding-top:8px">'
            f'<span style="color:#d4a847;font-weight:700">{len(events)}</span> KvK event(s) available'
            f'</div>',
            unsafe_allow_html=True,
        )

    event_row = events.loc[events["label"].eq(chosen_label)].iloc[0]
    start_d   = pd.to_datetime(event_row["start_date"]).date()
    end_d     = pd.to_datetime(event_row["end_date"]).date()

    imports_cp = imports.copy()
    imports_cp["_d"] = pd.to_datetime(imports_cp["report_date"]).dt.date
    in_window = imports_cp[(imports_cp["_d"] >= start_d) & (imports_cp["_d"] <= end_d)]

    if in_window.empty:
        today = date.today()
        if start_d > today:
            st.info(f"⏳ This KvK hasn't started yet. It begins on **{event_row['start_date']}**.")
        else:
            st.warning("No reports uploaded within this KvK's date range yet.")
        return

    # Usa somatório real
    ranked = compute_kvk_accumulated(storage, imports, group_power, start_d, end_d)

    if ranked.empty:
        st.info("No player data available for this KvK yet.")
        return

    n_reports = len(in_window)
    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">Event <span class="rok-caption-val">{event_row['name']}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Window <span class="rok-caption-val">{event_row['start_date']} → {event_row['end_date']}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Reports <span class="rok-caption-val">{n_reports}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Method <span class="rok-caption-val">Sum of all reports</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f'<div class="sec-label">{event_row["name"]}</div>', unsafe_allow_html=True)

    if "dead_equiv" not in ranked.columns:
        ranked["dead_equiv"] = (
            ranked.get("t4_deaths", 0) + ranked.get("t5_deaths", 0) * 2
        ).fillna(0).astype(int)

    top10_kp   = ranked.sort_values("kill_points", ascending=False).head(10).reset_index(drop=True)
    top10_dead = ranked.sort_values("dead_equiv",   ascending=False).head(10).reset_index(drop=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            '<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;'
            'letter-spacing:.14em;color:#d4a847;margin-bottom:10px">⚔ Top 10 Kill Points</div>',
            unsafe_allow_html=True,
        )
        _render_hof_list(top10_kp, "kp")

    with c2:
        st.markdown(
            '<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;'
            'letter-spacing:.14em;color:#4a7cba;margin-bottom:10px">💀 Top 10 Deaths</div>',
            unsafe_allow_html=True,
        )
        _render_hof_list(top10_dead, "deaths")


def _render_hof_list(df: pd.DataFrame, category: str) -> None:
    if df.empty:
        st.caption("No data for this KvK.")
        return
    medals = {1:"🥇", 2:"🥈", 3:"🥉"}
    color  = "#d4a847" if category == "kp" else "#4a7cba"
    unit   = "KP" if category == "kp" else "T4eq"
    val_col = "kill_points" if category == "kp" else "dead_equiv"

    for pos, (_, row) in enumerate(df.iterrows(), start=1):
        medal  = medals.get(pos, f"#{pos}")
        is_top = pos <= 3
        value  = int(row.get(val_col, 0))
        power  = int(row.get("power", 0))

        st.markdown(f'''
        <div style="display:flex;align-items:center;gap:10px;
                    padding:{"12px 14px" if is_top else "9px 14px"};
                    background:{"rgba(212, 168, 71, 0.08)" if is_top else "transparent"};
                    border:1px solid {"rgba(212, 168, 71, 0.2)" if is_top else "rgba(42, 63, 94, 0.5)"};
                    border-radius:6px;margin-bottom:5px;">
          <div style="font-size:{"1.2rem" if is_top else ".85rem"};min-width:28px;text-align:center">{medal}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:{"0.88rem" if is_top else "0.82rem"};font-weight:{"700" if is_top else "500"};color:#f0f4fa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              {row["username"]}
            </div>
            <div style="font-size:.62rem;color:#9ab0cc;margin-top:1px">{fmt_m(power)}M power</div>
          </div>
          <div style="font-family:"JetBrains Mono",monospace;font-size:{"1rem" if is_top else "0.85rem"};font-weight:600;color:{color};white-space:nowrap">
            {fmt_k(value)} {unit}
          </div>
        </div>
        ''', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Kingdom
# ══════════════════════════════════════════════════════════════════════════════

def show_kingdom(ranked: pd.DataFrame, imports, storage, group_power: int) -> None:
    total    = len(ranked)
    approved = int((ranked["status"]=="Aprovado").sum())
    pending  = int((ranked["status"]=="Pendente").sum())
    below    = int((ranked["status"]=="Abaixo da meta").sum())
    active   = int((ranked["kill_points"]>0).sum())
    kp_total    = int(ranked["kill_points"].sum())
    power_total = int(ranked["power"].sum())
    aprov_pct   = approved/total*100 if total else 0

    st.markdown('<div class="sec-label">Kingdom Operations</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="kd-row">
      <div class="kd-card amber">
        <div class="kd-card-label">Total Kill Points</div>
        <div class="kd-card-value">{fmt_k(kp_total)}</div>
        <div class="kd-card-sub">accumulated points</div>
      </div>
      <div class="kd-card blue">
        <div class="kd-card-label">Total Power</div>
        <div class="kd-card-value">{fmt_m(power_total)}M</div>
        <div class="kd-card-sub">combined city power</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-label">Governors</div>
        <div class="kd-card-value">{total:,}</div>
        <div class="kd-card-sub">{active} active in period</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-label">Approval Rate</div>
        <div class="kd-card-value">{aprov_pct:.1f}%</div>
        <div class="kd-card-sub">{approved} of {total} members</div>
      </div>
      <div class="kd-card red">
        <div class="kd-card-label">Below Goal</div>
        <div class="kd-card-value">{below}</div>
        <div class="kd-card-sub">{pending} pending</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Goal status</div>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    for col, lbl, count, color in [
        (m1,"Approved",  approved,"#3ba37a"),
        (m2,"Pending",  pending, "#d4a03a"),
        (m3,"Below goal", below, "#c95a4e"),
    ]:
        pct = count/total*100 if total else 0
        with col:
            st.markdown(f"""
            <div class="sm-card">
              <div class="sm-label">{lbl}</div>
              <div><span class="sm-count" style="color:{color}">{count}</span>
                   <span class="sm-denom">/ {total}</span></div>
              <div class="sm-bar">
                <div class="sm-fill" style="width:{pct:.1f}%;background:{color}"></div>
              </div>
              <div class="sm-pct">{pct:.1f}% of the alliance</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Power bands</div>', unsafe_allow_html=True)
    bands = []
    for pmin, pmax, dead_t4, _, kp in GOAL_TABLE:
        lbl = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax!=float("inf") else f"{pmin//1_000_000}M+"
        sub = ranked[ranked["power_band"]==lbl] if "power_band" in ranked else pd.DataFrame()
        if sub.empty: continue
        ok  = int((sub["status"]=="Aprovado").sum())
        wa  = int((sub["status"]=="Pendente").sum())
        er  = int((sub["status"]=="Abaixo da meta").sum())
        bands.append({"Band":lbl,"Total":len(sub),"✅":ok,"🟡":wa,"❌":er,
                      "Total KP":fmt_k(int(sub["kill_points"].sum())), "KP Goal":fmt_k(kp)})
    if bands:
        st.markdown('<table class="band-table"><tr>'
                    '<th>Band</th><th>Total</th><th>✅</th><th>🟡</th><th>❌</th><th>Total KP</th><th>KP Goal</th>'
                    '</tr>' +
                    "".join(f'<tr><td>{b["Band"]}</td><td>{b["Total"]}</td>'
                            f'<td>{b["✅"]}</td><td>{b["🟡"]}</td><td>{b["❌"]}</td>'
                            f'<td>{b["Total KP"]}</td><td>{b["KP Goal"]}</td></tr>'
                            for b in bands) +
                    '</table>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Need attention & Mailing List</div>', unsafe_allow_html=True)
    col_att, col_mail = st.columns([2, 1])

    att = ranked[ranked["status"]!="Aprovado"].sort_values("kp_pct").head(8)
    with col_att:
        if att.empty:
            st.success("All members are approved!")
        else:
            for _, row in att.iterrows():
                cls  = STATUS_CLS.get(row["status"],"er")
                kp_p = min(float(row.get("kp_pct",0))*100, 100)
                dp_p = min(float(row.get("dead_pct",0))*100, 100)
                st.markdown(f"""
                <div class="att-row {cls}">
                  <div class="att-name">{row['username']}</div>
                  <div class="att-pow">{fmt_m(int(row['power']))}M</div>
                  <div class="att-pcts">KP {kp_p:.0f}% · Deaths {dp_p:.0f}%</div>
                  <div class="sbadge sbadge-{cls}">{STATUS_ICON.get(row['status'],'○')} {STATUS_LABEL.get(row['status'],'—')}</div>
                </div>
                """, unsafe_allow_html=True)

    with col_mail:
        st.markdown(
            "<div style='font-size:0.75rem;color:#9ab0cc;margin-bottom:10px;'>"
            "Player IDs pending or below goal — paste in-game Mail:</div>",
            unsafe_allow_html=True,
        )
        abaixo = ranked[ranked['status'] != 'Aprovado']
        if not abaixo.empty:
            ids_correio = ",".join(abaixo['character_id'].astype(str).tolist())
            st.code(ids_correio, language="text")
        else:
            st.success("No mails needed.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Profile (Tracker)
# ══════════════════════════════════════════════════════════════════════════════

def show_profile(storage, imports, gp):
    st.markdown('<div class="sec-label">Player Tracker</div>', unsafe_allow_html=True)
    st.caption("Full performance history for any governor across all imported reports.")

    if imports.empty:
        st.info("Import more reports to track evolution.")
        return

    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)

    @st.cache_data(ttl=300)
    def _all_player_names(storage_label, import_ids_key):
        all_names = set()
        storage = get_storage()
        for imp_id in import_ids_key:
            try:
                df = storage.load_stats(imp_id)
                all_names.update(df["username"].dropna().tolist())
            except Exception:
                pass
        return sorted(all_names)

    import_ids_tuple = tuple(ordered["id"].tolist())
    player_list = _all_player_names(storage.label, import_ids_tuple)

    if not player_list:
        st.info("No players found.")
        return

    selected_player = st.selectbox("Select or search Governor:", player_list, key="profile_player")

    if not selected_player:
        return

    history_rows = []
    for _, imp_row in ordered.iterrows():
        try:
            stats = storage.load_stats(imp_row["id"])
            player_stats = stats[stats["username"] == selected_player]
            if player_stats.empty:
                continue
            metrics = calculate_metrics(player_stats, group_power=gp)
            ranked  = apply_goals(add_rank(metrics, "kill_points"))
            ranked["report_date"] = imp_row["report_date"]
            history_rows.append(ranked)
        except Exception:
            continue

    if not history_rows:
        st.warning(f"No data found for **{selected_player}**.")
        return

    player_data = pd.concat(history_rows, ignore_index=True).sort_values("report_date")

    latest = player_data.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Current Power",    f"{fmt_m(int(latest['power']))}M")
    with c2: st.metric("KP (Latest)",       fmt_k(int(latest['kill_points'])))
    with c3: st.metric("Deaths T4eq (Latest)", fmt_k(int(latest.get('dead_equiv', 0))))
    with c4: st.metric("Current Status",    STATUS_LABEL.get(latest['status'], latest['status']))

    if px is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=player_data['report_date'], y=player_data['kill_points'],
            mode='lines+markers', name='Kill Points (cumulative)',
            line=dict(color='#d4a847', width=2),
            marker=dict(size=6, color='#d4a847')
        ))
        fig.add_trace(go.Scatter(
            x=player_data['report_date'], y=player_data.get('dead_equiv', 0),
            mode='lines+markers', name='Deaths T4eq (cumulative)',
            line=dict(color='#4a7cba', width=2),
            marker=dict(size=6, color='#4a7cba')
        ))
        fig.update_layout(
            title=f"Cumulative stats — {selected_player}",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ab0cc", family="Inter", size=12),
            yaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)", zeroline=False),
            xaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)", zeroline=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Full history table", expanded=False):
        cols = {
            "report_date":"Date","kill_points":"KP","dead_equiv":"Deaths T4eq",
            "power":"Power","status":"Status",
        }
        avail = {k:v for k,v in cols.items() if k in player_data.columns}
        st.dataframe(
            player_data[list(avail.keys())].rename(columns=avail),
            use_container_width=True, hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tab — History (admin only)
# ══════════════════════════════════════════════════════════════════════════════

def show_history(storage, imports, group_power):
    st.markdown('<div class="sec-label">Compare two reports</div>', unsafe_allow_html=True)
    if len(imports) < 2:
        st.info("Import at least 2 reports to compare.")
        return

    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    labels  = ordered["label"].tolist()
    ca, cb  = st.columns(2)
    with ca: la = st.selectbox("Base",       labels, index=0,                    key="ha")
    with cb: lb = st.selectbox("Compare to", labels, index=min(1,len(labels)-1), key="hb")
    if la != lb:
        id_a  = ordered.loc[ordered["label"].eq(la),"id"].iloc[0]
        id_b  = ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
        delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
        met   = calculate_metrics(delta, group_power=group_power)
        top   = met.sort_values("kill_points",ascending=False).head(15)

        if not top.empty and px is not None:
            fig = px.bar(top.sort_values("kill_points",ascending=True),
                         x="kill_points", y="username", orientation="h",
                         color_discrete_sequence=["#d4a847"],
                         labels={"kill_points":"Kill Points Gained","username":""})
            fig.update_layout(
                showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#9ab0cc",family="Inter"),
                yaxis=dict(tickfont=dict(size=11,color="#9ab0cc"),gridcolor="rgba(42, 63, 94, 0.5)"),
                xaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)"),
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="sec-label">Deadweight Tracker</div>', unsafe_allow_html=True)
    st.caption("Players who were 'Below goal' in 2 or more imported reports.")

    all_rows = []
    ordered2 = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    for _, imp_row in ordered2.iterrows():
        try:
            stats   = storage.load_stats(imp_row["id"])
            metrics = calculate_metrics(stats, group_power=group_power)
            ranked  = apply_goals(add_rank(metrics, "kill_points"))
            ranked["report_date"] = imp_row["report_date"]
            all_rows.append(ranked)
        except Exception:
            continue

    if all_rows:
        hist_df = pd.concat(all_rows, ignore_index=True)
        deadweight_df = hist_df[hist_df['status'] == 'Abaixo da meta']
        infratores = (
            deadweight_df
            .groupby(['character_id','username'])
            .size()
            .reset_index(name='Goal Failures')
        )
        infratores_freq = infratores[infratores['Goal Failures'] >= 2].sort_values('Goal Failures', ascending=False)
        if not infratores_freq.empty:
            st.dataframe(infratores_freq, use_container_width=True, hide_index=True)
        else:
            st.success("No repeated deadweight detected. Your kingdom is healthy.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Imports (admin only)
# ══════════════════════════════════════════════════════════════════════════════

def show_imports(imports, storage, *, is_admin, admin_enabled):
    st.markdown('<div class="sec-label">Imported reports</div>', unsafe_allow_html=True)
    st.dataframe(
        imports[["report_date","filename","row_count","imported_at"]].rename(columns={
            "report_date":"Date","filename":"File","row_count":"Members","imported_at":"Imported at"}),
        use_container_width=True, hide_index=True)

    if admin_enabled and is_admin:
        st.markdown('<div class="sec-label">Delete import</div>', unsafe_allow_html=True)
        st.warning("Irreversible — removes all associated data.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Select",["— —",*labels])
        if to_del != "— —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            if st.button("Confirm delete", type="secondary"):
                if storage.delete_import(row["id"]):
                    st.success("Deleted."); st.rerun()
                else:
                    st.error("Not found.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Help
# ══════════════════════════════════════════════════════════════════════════════

def show_help():
    st.markdown('<div class="sec-label">Quick reference</div>', unsafe_allow_html=True)
    st.markdown("""
**Kill Points formula:** `KP = T5×20 + T4×10 + T3×4 + T2×2 + T1×0.2`

**Death equivalence:** 1 T5 death = 2 T4 deaths.
The system converts automatically: `equiv = (T5deaths × 2) + T4deaths`

**Main Ranking (⚔ Ranking tab):**
Uses **sum of all reports** in the selected date range.
All KP and deaths are summed across every report in the period.
Use the date pickers and sidebar filters to narrow down your analysis.

**Sidebar Filters:**
- **Power Min:** Minimum power to include (in millions)
- **KP Min:** Minimum kill points to include
- **% KP Min:** Minimum percentage of KP goal reached
- **% Deaths Min:** Minimum percentage of death goal reached

**Status:**
- ✅ Approved — reached both KP and death goals
- 🟡 Pending — ≥75% on both goals
- ❌ Below goal — <75% on either goal

**Gamification:**
- 🛡️ Top 5% Deaths  |  🔥 2× KP Goal  |  🐋 100M+ Power

**Hall of Fame:**
Automatically computed from the KvK events created in the 🛡 KvK tab.
Each KvK shows the top 10 KP and top 10 Deaths as a sum of all reports
within the event's date window.
""")


# ══════════════════════════════════════════════════════════════════════════════
# Formatters
# ══════════════════════════════════════════════════════════════════════════════

def fmt_int(v) -> str:   return f"{int(v):,}"
def fmt_k(v: int) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}k"
    return str(v)
def fmt_m(v: int) -> str: return f"{v/1_000_000:.0f}"

if __name__ == "__main__":
    main()
