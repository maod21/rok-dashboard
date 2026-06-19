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
from hall_of_fame import maybe_archive, load_hall, list_kvks
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
#  DESIGN SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

def _css() -> str:
    # Paleta "Azul Estático" (Única)
    bg = "#F0F4F8"           
    surface = "#FFFFFF"      
    surface2 = "#E1E8EF"     
    border = "rgba(30, 136, 229, 0.15)" 
    border_hi = "rgba(30, 136, 229, 0.5)"
    
    text = "#102A43"         
    text_sub = "#334E68"     
    text_dim = "#627D98"
    text_mut = "#829AB1"
    
    # Cores de Ação e Identidade
    blue = "#1E88E5"         
    blue_dark = "#1565C0"
    amber = "#F59E0B"        
    amber_hi = "#D97706"
    green, yellow, red = "#10B981", "#F59E0B", "#EF4444"
    
    gauge_bg, gauge_bdr = "rgba(30, 136, 229, 0.05)", "rgba(30, 136, 229, 0.1)"
    sidebar_bg = "#FFFFFF"
    
    # Badges
    ok_bg, ok_br, ok_tx = "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.3)", "#10B981"
    wa_bg, wa_br, wa_tx = "rgba(245, 158, 11, 0.1)", "rgba(245, 158, 11, 0.3)", "#F59E0B"
    er_bg, er_br, er_tx = "rgba(239, 68, 68, 0.1)", "rgba(239, 68, 68, 0.3)", "#EF4444"
    
    t5_tx, t5_br, t5_bg = "#D97706", "rgba(245, 158, 11, 0.4)", "rgba(245, 158, 11, 0.1)"
    t4_tx, t4_br, t4_bg = "#E8590C", "rgba(232, 89, 12, 0.4)", "rgba(232, 89, 12, 0.1)"
    t3_tx, t3_br, t3_bg = "#845EF7", "rgba(132, 94, 247, 0.4)", "rgba(132, 94, 247, 0.1)"
    t2_tx, t2_br, t2_bg = "#1C7ED6", "rgba(28, 126, 214, 0.4)", "rgba(28, 126, 214, 0.1)"
    t1_tx, t1_br, t1_bg = "#627D98", "rgba(98, 125, 152, 0.4)", "rgba(98, 125, 152, 0.1)"
    eq_tx, eq_br, eq_bg = "#829AB1", "rgba(130, 154, 177, 0.4)", "rgba(130, 154, 177, 0.1)"
    
    hdr1, hdr2 = "#FFFFFF", "#F0F4F8"
    metric_line = "linear-gradient(90deg, #1E88E5 0%, transparent 100%)"
    tbl_th, tbl_td, tbl_td1 = "#627D98", "#E1E8EF", "#102A43"
    tbl_rowsep = "rgba(30, 136, 229, 0.08)"

    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;800&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body, [class*="css"], .stApp {{ font-family: 'Inter', system-ui, sans-serif !important; background: {bg} !important; color: {text} !important; }}
.main .block-container {{ padding: 1.5rem 2.5rem 3rem !important; max-width: 1500px !important; background:{bg} !important; }}
section[data-testid="stSidebar"] {{ background: {sidebar_bg} !important; border-right: 1px solid {border} !important; box-shadow: 2px 0 12px rgba(30,136,229,0.05); }}
section[data-testid="stSidebar"] > div {{ padding: 2rem 1.5rem !important; }}
section[data-testid="stSidebar"] * {{ color: {text_sub} !important; }}

/* Cartões de Métrica Refinados */
[data-testid="stMetric"] {{ 
  background: {surface} !important; 
  border: 1px solid {border} !important; 
  border-radius: 12px !important; 
  padding: 20px 24px !important; 
  position: relative; 
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(30,136,229,0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
[data-testid="stMetric"]:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(30,136,229,0.08);
}}
[data-testid="stMetric"]::after {{ content:''; position:absolute; bottom:0; left:0; right:0; height:3px; background:{metric_line}; }}
[data-testid="stMetricLabel"] {{ font-size:0.7rem !important; font-weight:700 !important; text-transform:uppercase; letter-spacing:0.15em; color:{text_dim} !important; }}
[data-testid="stMetricValue"] {{ font-family:'JetBrains Mono',monospace !important; font-size:1.8rem !important; font-weight:800 !important; color:{text} !important; letter-spacing:-0.04em; }}

/* Abas (Tabs) Modernizadas */
[data-testid="stTabs"] [role="tablist"] {{ border-bottom: 2px solid {border}; gap: 1rem; background: transparent; padding-bottom: 4px; }}
[data-testid="stTabs"] button[role="tab"] {{ 
  font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; 
  color: {text_dim} !important; padding: 8px 12px; border: none; border-radius: 6px;
  background: transparent !important; transition: all 0.2s ease;
}}
[data-testid="stTabs"] button[role="tab"]:hover {{ color: {blue} !important; background: {surface2} !important; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ color: {blue} !important; background: {surface} !important; box-shadow: 0 2px 8px rgba(30,136,229,0.1); border-bottom: 2px solid {blue} !important; }}

/* Inputs e Botões */
[data-testid="stTextInput"] input, [data-testid="stSelectbox"] > div > div, [data-testid="stNumberInput"] input {{ 
  background: {surface} !important; border: 1px solid {border} !important; border-radius: 8px !important; 
  color: {text} !important; font-size: 0.85rem !important; transition: border-color 0.2s ease;
}}
[data-testid="stTextInput"] input:focus, [data-testid="stSelectbox"] > div > div:focus-within {{ border-color: {blue} !important; box-shadow: 0 0 0 3px rgba(30, 136, 229, 0.15) !important; }}
[data-testid="stButton"] button {{ background: {blue} !important; color: #fff !important; border: none !important; border-radius: 8px !important; font-weight: 800 !important; font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.1em; padding: 0.5rem 1rem !important; transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(30, 136, 229, 0.2); }}
[data-testid="stButton"] button:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(30, 136, 229, 0.3); }}

/* Expander Clean */
[data-testid="stExpander"] {{ border: 1px solid {border} !important; border-radius: 12px !important; background: {surface} !important; overflow: hidden; }}
[data-testid="stExpander"] > details > summary {{ background: {surface2} !important; padding: 12px 16px !important; color: {text} !important; font-weight: 600 !important; }}

/* Header Principal */
.rok-header {{ display: flex; align-items: center; gap: 20px; padding: 24px; margin-bottom: 24px; background: linear-gradient(135deg, {hdr1} 0%, {hdr2} 100%); border: 1px solid {border}; border-radius: 16px; box-shadow: 0 8px 32px rgba(30,136,229,0.05); position: relative; overflow: hidden; }}
.rok-header::before {{ content:''; position:absolute; top:0; left:0; width: 4px; height: 100%; background: {blue}; }}
.rok-header-emblem {{ width: 60px; height: 60px; flex-shrink: 0; background: linear-gradient(135deg, {blue}, {blue_dark}); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 2rem; box-shadow: 0 8px 24px rgba(30, 136, 229, 0.3); color: white; }}
.rok-header-title {{ font-size: 1.8rem; font-weight: 900; color: {text}; letter-spacing: -0.04em; line-height: 1; }}
.rok-header-sub {{ font-size: 0.8rem; font-weight: 600; color: {text_dim}; letter-spacing: 0.08em; margin-top: 6px; text-transform: uppercase; }}

/* Badges e Pílulas */
.tier-pills {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }}
.tier-pill {{ padding: 4px 12px; border-radius: 6px; font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap; border: 1px solid; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }}
.tp-t5 {{ color:{t5_tx}; border-color:{t5_br}; background:{t5_bg}; }}
.tp-t4 {{ color:{t4_tx}; border-color:{t4_br}; background:{t4_bg}; }}
.tp-t3 {{ color:{t3_tx}; border-color:{t3_br}; background:{t3_bg}; }}
.tp-t2 {{ color:{t2_tx}; border-color:{t2_br}; background:{t2_bg}; }}
.tp-t1 {{ color:{t1_tx}; border-color:{t1_br}; background:{t1_bg}; }}
.tp-eq {{ color:{eq_tx}; border-color:{eq_br}; background:{eq_bg}; }}

.sbadge {{ padding: 4px 10px; border-radius: 6px; font-size: 0.65rem; font-weight: 700; border: 1px solid; }}
.sbadge-ok {{ background: {ok_bg}; border-color: {ok_br}; color: {ok_tx}; }}
.sbadge-wa {{ background: {wa_bg}; border-color: {wa_br}; color: {wa_tx}; }}
.sbadge-er {{ background: {er_bg}; border-color: {er_br}; color: {er_tx}; }}

/* Linha de Jogador (Ranking) */
.mrow {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; margin-bottom: 8px; overflow: hidden; transition: transform 0.2s ease, box-shadow 0.2s ease; box-shadow: 0 2px 8px rgba(30,136,229,0.03); }}
.mrow:hover {{ transform: scale(1.002) translateX(4px); border-color: {border_hi}; box-shadow: 0 6px 16px rgba(30,136,229,0.08); z-index: 2; position: relative; }}
.mrow.ok {{ border-left: 4px solid {ok_tx}; }}
.mrow.wa {{ border-left: 4px solid {wa_tx}; }}
.mrow.er {{ border-left: 4px solid {er_tx}; }}
.mrow-sum {{ display: grid; grid-template-columns: 40px 1fr 120px 90px auto; align-items: center; gap: 16px; padding: 14px 20px; }}
.mrow-rank {{ font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 800; color: {text_mut}; text-align: left; }}
.mrow-name {{ font-size: 0.95rem; font-weight: 700; color: {text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.mrow-meta {{ font-size: 0.68rem; font-weight: 500; color: {text_dim}; margin-top: 4px; }}

/* Barras de Progresso Embutidas (Gauges) */
.mrow-gauges {{ display: flex; flex-direction: column; gap: 8px; }}
.gauge-head {{ display: flex; justify-content: space-between; font-size: 0.6rem; font-weight: 700; color: {text_sub}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 3px; }}
.gauge-track {{ height: 6px; background: {gauge_bg}; border-radius: 99px; overflow: hidden; border: 1px solid {gauge_bdr}; box-shadow: inset 0 1px 3px rgba(0,0,0,0.05); }}
.gauge-fill {{ height: 100%; border-radius: 99px; transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1); }}
.gauge-fill.kp {{ background: linear-gradient(90deg, {amber}, {amber_hi}); box-shadow: 0 0 8px rgba(245,158,11,0.4); }}
.gauge-fill.dead {{ background: linear-gradient(90deg, {blue_dark}, {blue}); box-shadow: 0 0 8px rgba(30,136,229,0.4); }}
.gauge-fill.full {{ background: linear-gradient(90deg, {green}, #34D399); box-shadow: 0 0 8px rgba(16,185,129,0.4); }}

.mrow-kp {{ font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 800; color: {amber}; text-align: right; white-space: nowrap; }}

/* Mdet (Detalhes) */
.mdet {{ padding: 16px 20px; background: {surface2}; border-top: 1px solid {border}; display: flex; flex-direction: column; gap: 16px; position: relative; }}
.mdet-accent-bar {{ position: absolute; left: 0; top: 0; bottom: 0; width: 4px; }}
.mdet-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.mdet-block-label {{ font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: {text_dim}; margin-bottom: 4px; }}
.mdet-block-val {{ font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 800; color: {text}; line-height: 1.1; }}
.mdet-block-sub {{ font-size: 0.7rem; color: {text_mut}; margin-bottom: 12px; }}

.mdet-prog {{ margin-bottom: 8px; }}
.mdet-prog-head {{ display: flex; justify-content: space-between; font-size: 0.65rem; font-weight: 700; color: {text_sub}; margin-bottom: 4px; }}
.mdet-prog-track {{ height: 8px; background: {border}; border-radius: 4px; overflow: hidden; }}
.mdet-prog-fill {{ height: 100%; border-radius: 4px; }}
.mdet-prog-fill.kp {{ background: {amber}; }}
.mdet-prog-fill.dead {{ background: {blue}; }}
.mdet-prog-fill.full-kp {{ background: {green}; }}
.mdet-prog-fill.full-dead {{ background: {green}; }}

.mdet-gap {{ font-size: 0.75rem; font-weight: 700; padding: 6px 10px; border-radius: 6px; display: inline-block; }}
.mdet-gap.ok {{ background: {ok_bg}; color: {ok_tx}; border: 1px solid {ok_br}; }}
.mdet-gap.warn {{ background: {er_bg}; color: {er_tx}; border: 1px solid {er_br}; }}

/* Tabelas Internas */
.tier-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; background: {surface}; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(30,136,229,0.03); }}
.tier-table th {{ text-align: left; padding: 8px 12px; background: {surface2}; color: {text_dim}; font-weight: 700; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid {border}; }}
.tier-table td {{ padding: 8px 12px; border-bottom: 1px solid {tbl_rowsep}; font-family: 'JetBrains Mono', monospace; font-weight: 600; color: {text_sub}; }}
.tier-table td:first-child {{ font-family: 'Inter', sans-serif; font-weight: 800; color: {text}; }}
.tier-table td.amber {{ color: {amber}; }}
.tier-table td.blue {{ color: {blue}; }}
.tier-table td.equiv {{ color: {text_mut}; font-weight: 500; }}

/* Seções e Separadores */
.sec-label {{ font-size: 0.7rem; font-weight: 900; letter-spacing: 0.2em; text-transform: uppercase; color: {blue}; display: flex; align-items: center; gap: 12px; margin: 32px 0 16px; }}
.sec-label::after {{ content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, {blue} 0%, transparent 100%); opacity: 0.3; }}

/* Tabela de Bandas */
.band-table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: {surface}; border-radius: 12px; overflow: hidden; border: 1px solid {border}; box-shadow: 0 4px 16px rgba(30,136,229,0.04); }}
.band-table th {{ font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.12em; background: {surface2}; color: {text_sub}; padding: 12px 16px; text-align: right; border-bottom: 1px solid {border}; }}
.band-table th:first-child {{ text-align: left; }}
.band-table td {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: {text}; padding: 12px 16px; text-align: right; border-bottom: 1px solid {tbl_rowsep}; }}
.band-table td:first-child {{ text-align: left; font-family: 'Inter', sans-serif; font-weight: 700; }}

/* Cards de Resumo */
.kd-card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; padding: 20px; position: relative; overflow: hidden; box-shadow: 0 4px 16px rgba(30,136,229,0.04); transition: transform 0.2s; }}
.kd-card:hover {{ transform: translateY(-4px); box-shadow: 0 8px 24px rgba(30,136,229,0.08); }}
.kd-card.amber::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg,{amber},transparent); }}
.kd-card.blue::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg,{blue},transparent); }}
.kd-card.green::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg,{green},transparent); }}
.kd-card.red::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg,{red},transparent); }}
.kd-card.yellow::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg,{amber_hi},transparent); }}
.kd-card-label {{ font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.15em; color: {text_dim}; margin-bottom: 6px; }}
.kd-card-value {{ font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 800; color: {text}; letter-spacing: -0.04em; line-height: 1; }}
.kd-card-sub {{ font-size: 0.7rem; color: {text_mut}; margin-top: 4px; }}

.kd-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}

/* SM Cards */
.sm-card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(30,136,229,0.03); }}
.sm-label {{ font-size: 0.7rem; font-weight: 800; text-transform: uppercase; color: {text_dim}; margin-bottom: 4px; }}
.sm-count {{ font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 800; }}
.sm-denom {{ font-size: 0.8rem; color: {text_mut}; }}
.sm-bar {{ height: 6px; background: {border}; border-radius: 3px; margin: 8px 0; overflow: hidden; }}
.sm-fill {{ height: 100%; border-radius: 3px; }}
.sm-pct {{ font-size: 0.65rem; color: {text_sub}; font-weight: 600; }}

/* Att Row */
.att-row {{ display: grid; grid-template-columns: 1fr 60px 140px auto; align-items: center; gap: 12px; padding: 10px 16px; background: {surface}; border: 1px solid {border}; border-radius: 8px; margin-bottom: 6px; }}
.att-row.er {{ border-left: 3px solid {er_tx}; }}
.att-row.wa {{ border-left: 3px solid {wa_tx}; }}
.att-name {{ font-weight: 700; color: {text}; font-size: 0.85rem; }}
.att-pow {{ font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: {text_sub}; }}
.att-pcts {{ font-size: 0.75rem; color: {text_dim}; }}

/* Upload and Empty States */
.upload-lock {{ display: flex; align-items: center; gap: 12px; background: {surface2}; padding: 12px; border-radius: 8px; margin-bottom: 12px; border: 1px solid {border}; }}
.upload-lock-icon {{ font-size: 1.2rem; }}
.upload-lock-text {{ font-size: 0.75rem; font-weight: 600; color: {text_dim}; }}

.empty-state {{ padding: 40px 20px; text-align: center; background: {surface}; border: 1px dashed {border_hi}; border-radius: 12px; margin: 20px 0; }}
.empty-state-icon {{ font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5; }}
.empty-state-title {{ font-size: 1.1rem; font-weight: 700; color: {text}; margin-bottom: 4px; }}
.empty-state-sub {{ font-size: 0.85rem; color: {text_dim}; }}

/* KVK Event Card */
.kvk-event-card {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; background: linear-gradient(90deg, {surface}, {surface2}); border: 1px solid {border}; border-left: 4px solid {blue}; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(30,136,229,0.05); }}
.kvk-event-name {{ font-size: 1.2rem; font-weight: 800; color: {text}; }}
.kvk-event-dates {{ font-size: 0.8rem; font-weight: 600; color: {text_dim}; margin-top: 4px; }}
.kvk-event-badge {{ background: {blue}; color: white; padding: 4px 12px; border-radius: 99px; font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; }}

/* Rok Caption */
.rok-caption {{ display: flex; gap: 12px; align-items: center; background: {surface2}; padding: 10px 16px; border-radius: 8px; margin-bottom: 24px; font-size: 0.75rem; border: 1px solid {border}; }}
.rok-caption-item {{ font-weight: 600; color: {text_sub}; }}
.rok-caption-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 800; color: {text}; margin-left: 4px; }}
.rok-caption-sep {{ color: {border_hi}; }}

.sb-sec {{ font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: {blue}; margin: 24px 0 12px; padding-bottom: 4px; border-bottom: 1px solid {border}; }}
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

def get_all_history_metrics(storage, imports, gp):
    all_data = []
    for _, row in imports.iterrows():
        try:
            stats = storage.load_stats(row['id'])
            mets = calculate_metrics(stats, group_power=gp)
            ranked = apply_goals(add_rank(mets, "kill_points"))
            ranked['report_date'] = row['report_date']
            all_data.append(ranked)
        except Exception:
            continue
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.html(_css())

    storage = get_storage()

    # Header estático
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

    # Sidebar
    with st.sidebar:
        st.markdown(f'<div class="sb-sec">System</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:.68rem;color:#627D98;margin-bottom:12px">Storage: <span style="color:#1E88E5;font-weight:bold;">{storage.label}</span></div>', unsafe_allow_html=True)
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

    imports  = prepare_imports(imports)
    selected = select_report(imports)
    current  = storage.load_stats(selected["id"])
    previous = load_previous_report(storage, imports, selected)

    basis_options = ["Report totals"]
    if previous is not None and not previous.empty:
        basis_options.insert(0, "Period delta")

    with st.sidebar:
        st.markdown('<div class="sb-sec">Settings</div>', unsafe_allow_html=True)
        basis     = st.radio("Metrics basis", basis_options, index=0)
        min_power = st.number_input("Minimum power", min_value=0, value=0, step=1_000_000, format="%d")
        st.markdown('<div class="sb-sec">Admin</div>', unsafe_allow_html=True)
        admin_enabled, is_admin = admin_panel()

    stats_basis = compute_period_deltas(current, previous) if basis == "Period delta" else current
    gp          = default_group_power(storage, imports)
    metrics_raw = calculate_metrics(stats_basis, group_power=gp)
    if min_power > 0:
        metrics_raw = metrics_raw[pd.to_numeric(metrics_raw["power"],errors="coerce").fillna(0) >= min_power]

    ranked = apply_goals(add_rank(metrics_raw, "kill_points"))

    n  = len(imports)
    dl = f"+{n-1} reports" if n > 1 else "1 report"
    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">Date <span class="rok-caption-val">{selected['report_date']}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Basis <span class="rok-caption-val">{basis}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Members <span class="rok-caption-val">{len(ranked):,}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Imports <span class="rok-caption-val">{dl}</span></div>
    </div>
    """, unsafe_allow_html=True)

    tab_labels = ["⚔ Ranking", "🛡 KvK", "🏆 Hall of Fame", "🏰 Kingdom", "👤 Profile", "❓ Help"]
    if admin_enabled and is_admin:
        tab_labels.append("📈 History")
        tab_labels.append("📁 Imports")

    tabs = st.tabs(tab_labels)
    with tabs[0]: show_ranking(ranked, key_prefix="main")
    with tabs[1]: show_kvk(storage, gp, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[2]: show_hof(storage, is_admin=is_admin, admin_enabled=admin_enabled)
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
        up_pwd = st.text_input("Password", type="password", key="up_pwd", label_visibility="collapsed", placeholder="Access password...")
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
    report_date = st.date_input("Report date", value=extract_report_date_from_name(safe_name) or date.today())
    if not st.button("Save report", type="primary", use_container_width=True): return

    with st.spinner("Processing..."):
        try:
            fb = uploaded.getvalue()
            if len(fb) > 50*1024*1024: st.error("File too large (max 50 MB)."); return
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            import_id_saved, created = storage.save_import(filename=safe_name, report_date=report_date.isoformat(),
                                                             file_hash=file_sha256(fb), stats=stats)
        except Exception as e: st.error(f"Error: {e}"); return
    if created:
        try:
            imports_df = storage.list_imports()
            imports_df = prepare_imports(imports_df)
            prev = load_previous_report(storage, imports_df,
                                        imports_df.loc[imports_df["id"].eq(import_id_saved)].iloc[0]) if not imports_df.empty else None
            archived = maybe_archive(storage, import_id_saved, stats, prev)
            if archived:
                st.info(f"🏆 Hall of Fame: {archived} entries archived")
        except Exception as _hof_err:
            pass
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

def select_report(imports):
    labels = imports["label"].tolist()
    chosen = st.sidebar.selectbox("Report", labels, index=0)
    return imports.loc[imports["label"].eq(chosen)].iloc[0]

def load_previous_report(storage, imports, selected):
    ordered   = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    positions = ordered.index[ordered["id"].eq(selected["id"])].tolist()
    if not positions or positions[0] == 0: return None
    prev_id = ordered.loc[positions[0]-1,"id"]
    return None if prev_id == selected["id"] else storage.load_stats(prev_id)

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
    entered = st.text_input("Admin password", type="password", key="adm_pwd", label_visibility="collapsed", placeholder="Admin password...")
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
    
    # Pré-cálculo para badges de gamificação
    top_5_pct_deaths = df['dead_equiv'].quantile(0.95) if 'dead_equiv' in df.columns else float('inf')
    df['emblems'] = ""
    for idx, row in df.iterrows():
        emb = ""
        if row.get('dead_equiv', 0) >= top_5_pct_deaths and row.get('dead_equiv', 0) > 0:
            emb += '<span title="Escudo de Carne (Top 5% Mortes)">🛡️</span> '
        if row.get('kill_points', 0) >= (row.get('kp_goal', 1) * 2) and row.get('kp_goal', 0) > 0:
            emb += '<span title="Máquina de Guerra (2x Meta KP)">🔥</span> '
        if row.get('power', 0) >= 100_000_000:
            emb += '<span title="Baleia (100M+ Poder)">🐋</span> '
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

    page_size = st.selectbox("Per page",[25,50,100],index=0,key=f"{key_prefix}_rank_ps",label_visibility="collapsed")
    total_pg  = max(1,-(-len(df)//page_size))
    col_pg1, col_pg2 = st.columns([1,5])
    with col_pg1:
        page = st.number_input("Page",min_value=1,max_value=total_pg,value=1,key=f"{key_prefix}_rank_pg",label_visibility="collapsed")
    with col_pg2:
        st.markdown(f'<div style="font-size:.65rem;color:#627D98;padding-top:8px">Page {page} of {total_pg}</div>',unsafe_allow_html=True)

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
                            file_name="ranking.csv", mime="text/csv", key=f"{key_prefix}_dl_csv")

def _render_members(df: pd.DataFrame, key_prefix: str = "main") -> None:
    for i, (_, row) in enumerate(df.iterrows()):
        cls   = STATUS_CLS.get(row["status"], "er")
        kp_w   = min(float(row.get("kp_pct",0))*100, 100)
        dead_w = min(float(row.get("dead_pct",0))*100, 100)
        kp_gap   = int(row.get("kp_gap",0))
        dead_gap = int(row.get("dead_gap_t4",0))

        kp_fc   = "full" if kp_w   >= 100 else "kp"
        dead_fc = "full" if dead_w >= 100 else "dead"

        badge_cls = f"sbadge-{cls}"
        badge = (f'<span class="sbadge {badge_cls}">'
                 f'{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</span>')

        st.markdown(f"""
        <div class="mrow {cls}">
          <div class="mrow-sum">
            <div class="mrow-rank">#{int(row['rank'])}</div>
            <div class="mrow-info">
              <div class="mrow-name">{row['username']} {row.get('emblems', '')}</div>
              <div class="mrow-meta">{fmt_m(int(row['power']))}M power · {row.get('power_band','—')} · ID {row.get('character_id','—')}</div>
            </div>
            <div class="mrow-gauges">
              <div class="gauge-wrap">
                <div class="gauge-head"><span>KP {kp_w:.0f}%</span><span>{fmt_k(int(row['kill_points']))}</span></div>
                <div class="gauge-track"><div class="gauge-fill {kp_fc}" style="width:{kp_w:.1f}%"></div></div>
              </div>
              <div class="gauge-wrap">
                <div class="gauge-head"><span>D {dead_w:.0f}%</span><span>{fmt_k(int(row.get('dead_equiv',0)))} T4eq</span></div>
                <div class="gauge-track"><div class="gauge-fill {dead_fc}" style="width:{dead_w:.1f}%"></div></div>
              </div>
            </div>
            <div class="mrow-kp">{fmt_k(int(row['kill_points']))}</div>
            <div>{badge}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"↳ details · {row['username']}", expanded=False):
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

            st.markdown(f"""
            <div class="mdet">
              <div class="mdet-accent-bar" style="background:{'#10B981' if cls=='ok' else '#F59E0B' if cls=='wa' else '#EF4444'}"></div>
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
                <div style="font-size:.62rem;color:#627D98;margin-top:8px">
                  Total equiv: <span style="color:#1E88E5;font-family:monospace">{fmt_int(dead_equiv)}</span>
                  / Goal: <span style="color:#829AB1;font-family:monospace">{fmt_int(int(row['dead_t4_goal']))}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab — KvK
# ══════════════════════════════════════════════════════════════════════════════

def show_kvk(storage, group_power: int, *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#1E88E5">
      <div class="rok-header-emblem" style="background:linear-gradient(135deg,#1E88E5,#1565C0)">🛡</div>
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
                kvk_name = st.text_input("Event name", placeholder="e.g. KvK Heroic Anthem", key="kvk_new_name")
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
    chosen_label = st.selectbox("Event", events["label"].tolist(), key="kvk_select", label_visibility="collapsed")
    event_row = events.loc[events["label"].eq(chosen_label)].iloc[0]

    st.markdown(f'''
    <div class="kvk-event-card">
      <div>
        <div class="kvk-event-name">{event_row["name"]}</div>
        <div class="kvk-event-dates">{event_row["start_date"]} → {event_row["end_date"]}</div>
      </div>
      <div class="kvk-event-badge">KvK Window</div>
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

    all_imports = storage.list_imports()
    if all_imports.empty:
        st.info("No reports available yet.")
        return
    all_imports = prepare_imports(all_imports)
    all_imports["_d"] = pd.to_datetime(all_imports["report_date"]).dt.date

    start_d = pd.to_datetime(event_row["start_date"]).date()
    end_d   = pd.to_datetime(event_row["end_date"]).date()
    in_window = all_imports[(all_imports["_d"] >= start_d) & (all_imports["_d"] <= end_d)].sort_values("_d")

    if in_window.empty:
        st.warning("No reports fall within this event's date range yet.")
        return

    first_id = in_window.iloc[0]["id"]
    last_id  = in_window.iloc[-1]["id"]

    st.caption(f"📊 Calculated from **{len(in_window)}** report(s) between **{in_window.iloc[0]['report_date']}** and **{in_window.iloc[-1]['report_date']}**")

    if len(in_window) == 1:
        stats_window = storage.load_stats(first_id)
        basis_note = "totals (only 1 report in window)"
    else:
        stats_first = storage.load_stats(first_id)
        stats_last  = storage.load_stats(last_id)
        stats_window = compute_period_deltas(stats_last, stats_first)
        basis_note = "delta between first and last report in window"

    metrics_window = calculate_metrics(stats_window, group_power=group_power)
    ranked_window  = apply_goals(add_rank(metrics_window, "kill_points"))

    with st.expander("🔎 Narrow by date within this event", expanded=False):
        wc1, wc2 = st.columns(2)
        with wc1:
            sub_from = st.date_input("From", value=start_d, min_value=start_d, max_value=end_d, key="kvk_sub_from")
        with wc2:
            sub_to   = st.date_input("To", value=end_d, min_value=start_d, max_value=end_d, key="kvk_sub_to")
        if (sub_from != start_d) or (sub_to != end_d):
            sub_window = all_imports[(all_imports["_d"] >= sub_from) & (all_imports["_d"] <= sub_to)].sort_values("_d")
            if not sub_window.empty:
                sf_id, sl_id = sub_window.iloc[0]["id"], sub_window.iloc[-1]["id"]
                if len(sub_window) == 1:
                    stats_window = storage.load_stats(sf_id)
                else:
                    stats_window = compute_period_deltas(storage.load_stats(sl_id), storage.load_stats(sf_id))
                metrics_window = calculate_metrics(stats_window, group_power=group_power)
                ranked_window  = apply_goals(add_rank(metrics_window, "kill_points"))
                st.caption(f"Narrowed to {len(sub_window)} report(s): {sub_window.iloc[0]['report_date']} → {sub_window.iloc[-1]['report_date']}")

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
        discord_text = f"""**🛡️ {event_row['name']} · Resumo do KvK 🛡️**

**Performance do Reino (K1602)**
⚔️ **Total KP Ganhos:** {fmt_k(kp_total)}
✅ **Aprovação:** {aprov_pct:.1f}% ({approved}/{total} aprovados)
⚠️ **Abaixo da meta:** {below} governadores

**🏆 Top 3 Matadores (KP):**
🥇 {top3.iloc[0]['username'] if len(top3)>0 else '-'} : {fmt_k(top3.iloc[0]['kill_points']) if len(top3)>0 else 0} KP
🥈 {top3.iloc[1]['username'] if len(top3)>1 else '-'} : {fmt_k(top3.iloc[1]['kill_points']) if len(top3)>1 else 0} KP
🥉 {top3.iloc[2]['username'] if len(top3)>2 else '-'} : {fmt_k(top3.iloc[2]['kill_points']) if len(top3)>2 else 0} KP"""
        
        with st.expander("💬 Gerar Resumo para o Discord"):
            st.code(discord_text, language="markdown")

    if px is not None and not ranked_window.empty:
        st.markdown('<div class="sec-label">Top performers — this event</div>', unsafe_allow_html=True)
        top20 = ranked_window.sort_values("kill_points",ascending=True).tail(20)
        cmap = {"Aprovado":"#10B981","Pendente":"#F59E0B","Abaixo da meta":"#EF4444"}
        fig = px.bar(top20, x="kill_points", y="username", orientation="h",
                     color="status", color_discrete_map=cmap,
                     labels={"kill_points":"Kill Points","username":""})
        fig.update_layout(showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#627D98", family="Inter"),
            yaxis=dict(tickfont=dict(size=11,color="#627D98"), gridcolor="rgba(30,136,229,0.08)"),
            xaxis=dict(tickfont=dict(size=10), gridcolor="rgba(30,136,229,0.08)"))
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="sec-label">Individual ranking — this event</div>', unsafe_allow_html=True)
    show_ranking(ranked_window, key_prefix=f"kvk_{event_row['id']}")

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
        (m1,"Approved",  approved,"#10B981"),
        (m2,"Pending",  pending, "#F59E0B"),
        (m3,"Below goal", below, "#EF4444"),
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
        st.markdown("<div style='font-size:0.75rem; color:#627D98; margin-bottom:10px;'>Lista de IDs de jogadores pendentes ou abaixo da meta para enviar Mails no jogo:</div>", unsafe_allow_html=True)
        abaixo_da_meta = ranked[ranked['status'] != 'Aprovado']
        if not abaixo_da_meta.empty:
            ids_correio = ",".join(abaixo_da_meta['character_id'].astype(str).tolist())
            st.code(ids_correio, language="text")
        else:
            st.success("Nenhum mail necessário.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab — Profile (Tracker)
# ══════════════════════════════════════════════════════════════════════════════

def show_profile(storage, imports, gp):
    st.markdown('<div class="sec-label">Player Tracker</div>', unsafe_allow_html=True)
    st.caption("Busque o histórico completo de desempenho de um jogador.")
    
    hist_df = get_all_history_metrics(storage, imports, gp)
    if hist_df.empty:
        st.info("Importe mais relatórios para rastrear a evolução.")
        return

    player_list = hist_df['username'].unique().tolist()
    selected_player = st.selectbox("Selecione ou busque o Governador:", player_list)

    if selected_player and px is not None:
        player_data = hist_df[hist_df['username'] == selected_player].sort_values('report_date')
        
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Power Atual", f"{fmt_m(int(player_data.iloc[-1]['power']))}M")
        with c2: st.metric("Kill Points (Último)", fmt_k(int(player_data.iloc[-1]['kill_points'])))
        with c3: st.metric("Status Atual", player_data.iloc[-1]['status'])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data['kill_points'],
                                 mode='lines+markers', name='Kill Points', line=dict(color='#F59E0B')))
        fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data['dead_equiv'],
                                 mode='lines+markers', name='Deaths (T4eq)', line=dict(color='#1E88E5')))
        
        fig.update_layout(
            title=f"Evolução de {selected_player}",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#627D98", family="Inter"),
            yaxis=dict(gridcolor="rgba(30,136,229,0.08)"),
            xaxis=dict(gridcolor="rgba(30,136,229,0.08)")
        )
        st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab — Hall of Fame
# ══════════════════════════════════════════════════════════════════════════════

def show_hof(storage, *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#F59E0B">
      <div class="rok-header-emblem" style="background:linear-gradient(135deg,#F59E0B,#D97706)">🏆</div>
      <div>
        <div class="rok-header-title">Hall of Fame — K1602</div>
        <div class="rok-header-sub">Top 10 KP · Top 10 Deaths · By KvK</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    hof = load_hall(storage)

    if hof.empty:
        st.markdown('''
        <div class="empty-state">
          <div class="empty-state-icon">🏆</div>
          <div class="empty-state-title">No KvK archived yet</div>
          <div class="empty-state-sub">The Hall of Fame fills automatically when a report is imported.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    kvks = list_kvks(hof)
    col_sel, col_info = st.columns([3,3])
    with col_sel:
        selected_kvk = st.selectbox("KVK", kvks, key="hof_kvk", label_visibility="collapsed")
    with col_info:
        total_kvks = len(kvks)
        st.markdown(
            f'<div style="font-size:.68rem;color:#627D98;padding-top:8px">' f'<span style="color:#1E88E5;font-weight:700">{total_kvks}</span> KVK(s) archived' f'</div>',
            unsafe_allow_html=True,
        )

    kvk_data = hof[hof["kvk_name"] == selected_kvk]
    kp_df    = kvk_data[kvk_data["category"] == "kp"   ].sort_values("position")
    dead_df  = kvk_data[kvk_data["category"] == "deaths"].sort_values("position")

    st.markdown(f'<div class="sec-label">{selected_kvk}</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;' 'letter-spacing:.14em;color:#F59E0B;margin-bottom:10px">⚔ Top 10 Kill Points</div>',
                    unsafe_allow_html=True)
        _render_hof_list(kp_df, "kp")

    with c2:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;' 'letter-spacing:.14em;color:#1E88E5;margin-bottom:10px">💀 Top 10 Deaths</div>',
                    unsafe_allow_html=True)
        _render_hof_list(dead_df, "deaths")

def _render_hof_list(df: pd.DataFrame, category: str) -> None:
    if df.empty:
        st.caption("No data for this KVK.")
        return
    medals = {1:"🥇", 2:"🥈", 3:"🥉"}
    color  = "#F59E0B" if category == "kp" else "#1E88E5"
    unit   = "KP" if category == "kp" else "T4eq"

    for _, row in df.iterrows():
        pos    = int(row["position"])
        medal  = medals.get(pos, f"#{pos}")
        is_top = pos <= 3

        st.markdown(f'''
        <div style="display:flex;align-items:center;gap:10px;
                    padding:{'12px 14px' if is_top else '9px 14px'};
                    background:{"rgba(30,136,229,0.03)" if is_top else "transparent"};
                    border:1px solid {"rgba(30,136,229,0.15)" if is_top else "rgba(30,136,229,0.05)"};
                    border-radius:8px;margin-bottom:5px;">
          <div style="font-size:{'1.2rem' if is_top else '.85rem'};min-width:28px;text-align:center">{medal}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:{'0.88rem' if is_top else '0.82rem'}; font-weight:{'700' if is_top else '500'}; color:#102A43;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              {row["username"]}
            </div>
            <div style="font-size:.62rem;color:#627D98;margin-top:1px">{fmt_m(int(row["power"]))}M power</div>
          </div>
          <div style="font-family:'JetBrains Mono',monospace; font-size:{'1rem' if is_top else '0.85rem'}; font-weight:600;color:{color};white-space:nowrap">
            {fmt_k(int(row["value"]))} {unit}
          </div>
        </div>
        ''', unsafe_allow_html=True)


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
    with ca: la = st.selectbox("Base",      labels, index=0,                   key="ha")
    with cb: lb = st.selectbox("Compare to", labels, index=min(1,len(labels)-1),key="hb")
    if la != lb:
        id_a = ordered.loc[ordered["label"].eq(la),"id"].iloc[0]
        id_b = ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
        delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
        met   = calculate_metrics(delta, group_power=group_power)
        top   = met.sort_values("kill_points",ascending=False).head(15)

        if not top.empty and px is not None:
            fig = px.bar(top.sort_values("kill_points",ascending=True),
                         x="kill_points", y="username", orientation="h",
                         color_discrete_sequence=["#F59E0B"],
                         labels={"kill_points":"Kill Points Gained","username":""})
            fig.update_layout(
                showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#627D98",family="Inter"),
                yaxis=dict(tickfont=dict(size=11,color="#627D98"),gridcolor="rgba(30,136,229,0.08)"),
                xaxis=dict(gridcolor="rgba(30,136,229,0.08)"),
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

    # NOVO: Deadweight Tracker
    st.markdown('<div class="sec-label">Rastreador de "Deadweight" (Peso Morto)</div>', unsafe_allow_html=True)
    st.caption("Jogadores que ficaram 'Abaixo da meta' em 2 ou mais relatórios importados.")
    
    hist_df = get_all_history_metrics(storage, imports, group_power)
    if not hist_df.empty:
        deadweight_df = hist_df[hist_df['status'] == 'Abaixo da meta']
        infratores = deadweight_df.groupby(['character_id', 'username']).size().reset_index(name='Falhas na Meta')
        infratores_frequentes = infratores[infratores['Falhas na Meta'] >= 2].sort_values('Falhas na Meta', ascending=False)
        
        if not infratores_frequentes.empty:
            st.dataframe(infratores_frequentes, use_container_width=True, hide_index=True)
        else:
            st.success("Nenhum peso morto repetido detectado! Seu reino está saudável.")

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
                else: st.error("Not found.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab — Help
# ══════════════════════════════════════════════════════════════════════════════

def show_help():
    st.markdown('<div class="sec-label">Quick reference</div>', unsafe_allow_html=True)
    st.markdown("""
**Kill Points formula:** `KP = T5×20 + T4×10 + T3×4 + T2×2 + T1×0.2`

**Death equivalence:** 1 T5 death = 2 T4 deaths.
The system converts automatically: `equiv = (T5deaths × 2) + T4deaths`

**Status:**
- ✅ Approved — reached both KP and death goals
- 🟡 Pending — ≥75% on both goals
- ❌ Below goal — <75% on either goal

**Gamification:**
- 🛡️ Top 5% Mortes  |  🔥 2x Meta de KP  |  🐋 Mais de 100M Poder
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
