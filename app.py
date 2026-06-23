from __future__ import annotations
import os, re
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import streamlit as st

# Importações dos seus módulos existentes
from member_goals import apply_goals, GOAL_TABLE
from rok_metrics import (
    POINT_WEIGHTS, add_rank, calculate_metrics, compute_period_deltas,
    extract_report_date_from_name, file_sha256, load_stats_file,
)
from security import is_admin_authenticated
from hall_of_fame import load_hall, list_kvks
from storage import create_storage

# Tabela de Histórias de KvK (Pedido pelo usuário)
KVK_STORIES = {
    "Heroic Anthem": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Heroic Anthem: Power Up": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Desert Conquest": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Orleans Campaign": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Nile": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Warriors Unbound": {"camps": ["Fire", "Water", "Earth", "Wind"]},
    "Kingdom of Aurics": {"camps": ["Aurics", "Glaciers", "Storms", "Embers", "Tides", "Verdure"]},
    "Strife of the Eight": {"camps": ["Dragon", "Tiger", "Lion", "Bear", "Wolf", "Raven", "Lotus", "Viper"]},
}

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
#  DESIGN SYSTEM — THEME: "SOVEREIGN SLATE"
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _css() -> str:
    bg_main        = "#0e1a2b"; bg_surface = "#162233"; bg_surface_alt = "#1c2a3f"
    border_color   = "#2a3f5e"; text_main = "#f0f4fa"; text_sub = "#9ab0cc"; text_muted = "#5a7294"
    gold = "#d4a847"; blue_accent = "#4a7cba"; green_ok = "#3ba37a"; yellow_pend = "#d4a03a"; red_alert = "#c95a4e"
    sb_bg = "#0a131f"; sb_text = "#8398b5"
    t5_color, t4_color, t3_color, t2_color, t1_color = gold, "#cf6f3a", "#7d5eb8", "#3f93a6", text_muted

    return f"""
<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body, [class*="css"], .stApp {{ font-family: 'Inter', system-ui, sans-serif !important; background: {bg_main} !important; color: {text_main} !important; }}
.main .block-container {{ padding: 1.2rem 2rem 3rem !important; max-width: 1500px !important; background:{bg_main} !important; }}
section[data-testid="stSidebar"] {{ background: {sb_bg} !important; border-right: 1px solid {border_color} !important; }}
section[data-testid="stSidebar"] > div {{ padding: 1.5rem 1rem !important; }}
section[data-testid="stSidebar"] * {{ color: {sb_text} !important; }}
section[data-testid="stSidebar"] .stSuccess p {{ color: {green_ok} !important; }}
section[data-testid="stSidebar"] .stError p {{ color: {red_alert} !important; }}
section[data-testid="stSidebar"] .stWarning p {{ color: {yellow_pend} !important; }}
.sb-sec {{ font-size: .58rem; font-weight: 700; text-transform: uppercase; letter-spacing: .14em; color: {sb_text}; border-bottom: 1px solid {border_color}; padding-bottom: 6px; margin: 14px 0 10px; }}
[data-testid="stMetric"] {{ background: {bg_surface} !important; border: 1px solid {border_color} !important; border-radius: 8px !important; padding: 16px 20px !important; position: relative; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }}
[data-testid="stMetric"]::after {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background:{blue_accent}; }}
[data-testid="stMetricLabel"] {{ font-size:.62rem !important; font-weight:600 !important; text-transform:uppercase; letter-spacing:.08em; color:{text_sub} !important; }}
[data-testid="stMetricValue"] {{ font-family:'JetBrains Mono',monospace !important; font-size:1.6rem !important; font-weight:600 !important; color:{text_main} !important; letter-spacing:-.03em; }}
[data-testid="stTabs"] [role="tablist"] {{ border-bottom: 1px solid {border_color}; gap: 0; background: transparent; flex-wrap: wrap; }}
[data-testid="stTabs"] button[role="tab"] {{ font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em; color: {text_muted} !important; padding: 10px 20px; border-bottom: 2px solid transparent; border-radius: 0; background: transparent !important; transition: color .2s, border-color .2s; }}
[data-testid="stTabs"] button[role="tab"]:hover {{ color: {gold} !important; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{ color: {gold} !important; border-bottom-color: {gold} !important; background: transparent !important; }}
[data-testid="stTextInput"] input, [data-testid="stSelectbox"] > div > div, [data-testid="stNumberInput"] input {{ background: {bg_surface_alt} !important; border: 1px solid {border_color} !important; border-radius: 6px !important; color: {text_main} !important; font-family: 'Inter', sans-serif !important; font-size: .82rem !important; }}
[data-testid="stTextInput"] input::placeholder {{ color: {text_muted} !important; }}
[data-testid="stTextInput"] input:focus, [data-testid="stSelectbox"] > div > div:focus-within {{ border-color: {blue_accent} !important; box-shadow: 0 0 0 2px rgba(74, 124, 186, 0.2) !important; }}
[data-testid="stButton"] button {{ background: {blue_accent} !important; color: #fff !important; border: none !important; border-radius: 6px !important; font-weight: 700 !important; font-size: .78rem !important; text-transform: uppercase; letter-spacing: .08em; transition: all .2s; box-shadow: 0 2px 6px rgba(0,0,0,0.3); }}
[data-testid="stButton"] button:hover {{ background: {gold} !important; transform: translateY(-1px); color: #000 !important; }}
[data-testid="stButton"] button[kind="secondary"] {{ background: transparent !important; border: 1px solid {border_color} !important; color: {text_sub} !important; }}
[data-testid="stDataFrame"] {{ border: 1px solid {border_color} !important; border-radius: 8px !important; overflow: hidden; background: {bg_surface}; }}
[data-testid="stDataFrame"] th {{ background: {bg_surface_alt} !important; color: {text_sub} !important; }}
[data-testid="stDataFrame"] td {{ color: {text_main} !important; }}
hr {{ border-color: {border_color} !important; margin: 1.2rem 0 !important; }}
.rok-header {{ display: flex; align-items: center; gap: 18px; padding: 16px 24px; margin-bottom: 18px; background: {bg_surface} !important; border: 1px solid {border_color}; border-radius: 8px; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
.rok-header::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background: linear-gradient(90deg, {blue_accent} 0%, {gold} 100%); }}
.rok-header-emblem {{ width: 48px; height: 48px; flex-shrink: 0; background: {bg_surface_alt}; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; border: 1px solid {gold}; }}
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
.filter-tag {{ display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: .62rem; font-weight: 600; background: rgba(74, 124, 186, 0.15); color: {blue_accent}; border: 1px solid rgba(74, 124, 186, 0.3); }}
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
.kvk-glass-card {{
    background: rgba(22, 34, 51, 0.6);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
}}
.kvk-glass-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, {gold}, {blue_accent});
}}
</style>
"""

# ══════════════════════════════════════════════════════════════════════════════
# Storage / State / Globals
# ══════════════════════════════════════════════════════════════════════════════

STATUS_CLS   = {"Aprovado":"ok","Pendente":"wa","Abaixo da meta":"er"}
STATUS_ICON  = {"Aprovado":"●","Pendente":"◐","Abaixo da meta":"○"}
STATUS_LABEL = {"Aprovado":"Approved","Pendente":"Pending","Abaixo da meta":"Below"}

@st.cache_resource
def get_storage(): return create_storage()

def get_secret(name):
    v = os.getenv(name)
    if v: return v
    try: v = st.secrets.get(name)
    except: v = None
    return str(v) if v else None

# ══════════════════════════════════════════════════════════════════════════════
# Formatters
# ══════════════════════════════════════════════════════════════════════════════

def fmt_int(v) -> str:   return f"{int(v):,}"
def fmt_k(v: int) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}k"
    return str(v)

def fmt_m(v: int) -> str: return f"{v/1_000_000:.0f}"

# ══════════════════════════════════════════════════════════════════════════════
# Accumulated ranking helpers (Iguais ao seu original)
# ══════════════════════════════════════════════════════════════════════════════

def compute_accumulated_sum(storage, imports: pd.DataFrame, group_power: int,
                            date_from: date | None = None,
                            date_to: date | None = None) -> tuple[pd.DataFrame, str, str]:
    ordered = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    ordered["_d"] = pd.to_datetime(ordered["report_date"]).dt.date
    if date_from: ordered = ordered[ordered["_d"] >= date_from]
    if date_to: ordered = ordered[ordered["_d"] <= date_to]
    if ordered.empty: return pd.DataFrame(), "", ""

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
        stats = storage.load_stats(imp_row["id"])
        for _, player in stats.iterrows():
            cid = str(player["character_id"])
            if cid not in accumulated:
                accumulated[cid] = {"character_id": cid, "username": player["username"], "alliance": player.get("alliance", ""),}
                for col in sum_columns: accumulated[cid][col] = 0
                accumulated[cid]["_report_count"] = 0
            for col in sum_columns:
                if col in player:
                    try:
                        val = player[col]
                        if pd.notna(val): accumulated[cid][col] += int(float(val))
                    except: pass
            accumulated[cid]["_report_count"] += 1

    if not accumulated: return pd.DataFrame(), "", ""
    result_df = pd.DataFrame(list(accumulated.values()))
    
    last_import_id = ordered.iloc[-1]["id"]
    last_stats = storage.load_stats(last_import_id)
    last_power_map = {}
    for _, player in last_stats.iterrows():
        cid = str(player["character_id"])
        try: last_power_map[cid] = int(float(player["power"])) if pd.notna(player["power"]) else 0
        except: last_power_map[cid] = 0
    for idx, row in result_df.iterrows():
        cid = str(row["character_id"])
        result_df.at[idx, "power"] = last_power_map.get(cid, 0)

    result_df = result_df.drop(columns=["_report_count"], errors="ignore")
    metrics = calculate_metrics(result_df, group_power=group_power)
    ranked  = apply_goals(add_rank(metrics, "kill_points"))
    return ranked, first_date, last_date

def compute_kvk_accumulated(storage, imports: pd.DataFrame, group_power: int, start_d: date, end_d: date) -> pd.DataFrame:
    result, _, _ = compute_accumulated_sum(storage, imports, group_power, start_d, end_d)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# Sidebar Helpers (UPLOAD COM DUAS SENHAS)
# ══════════════════════════════════════════════════════════════════════════════

def handle_upload(storage, active_kvk_id: str | None = None, active_camps: pd.DataFrame | None = None):
    upload_pwd = get_secret("UPLOAD_PASSWORD")
    admin_pwd  = get_secret("ADMIN_PASSWORD")
    
    if "upload_auth" not in st.session_state: st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.markdown("""
        <div class="upload-lock">
          <div class="upload-lock-icon">🔒</div>
          <div class="upload-lock-text">Upload restrito à liderança</div>
        </div>
        """, unsafe_allow_html=True)
        up_pwd = st.text_input("Senha de Upload", type="password", key="up_pwd", label_visibility="collapsed", placeholder="Digite a senha de upload...")
        
        if st.button("Desbloquear Upload", use_container_width=True):
            is_admin = admin_pwd and is_admin_authenticated(admin_pwd, up_pwd)
            is_uploader = upload_pwd and up_pwd == upload_pwd
            if is_admin or is_uploader:
                st.session_state.upload_auth = True
                st.rerun()
            else:
                st.error("Senha incorreta")
        return

    st.success("✓ Acesso de upload liberado")
    if st.button("🔒 Bloquear", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False
        st.rerun()

    uploaded = st.file_uploader("statsExport (.xlsx)", type=["xlsx","xls"])
    if not uploaded: return
    safe_name   = re.sub(r"[^\w.\-]","_", uploaded.name)
    report_date = st.date_input("Data do relatório", value=extract_report_date_from_name(safe_name) or date.today())

    kingdom_name = None
    camp_id = None
    if active_kvk_id and active_camps is not None and not active_camps.empty:
        st.markdown("---")
        st.markdown("#### 🏰 Importação de Reino Inimigo")
        camp_options = active_camps["camp_name"].tolist()
        selected_camp = st.selectbox("Selecione o Acampamento deste Reino:", camp_options)
        
        camp_row = active_camps[active_camps["camp_name"] == selected_camp].iloc[0]
        existing_kingdom = camp_row.get("kingdom", "")
        if existing_kingdom:
            st.info(f"Reino já cadastrado neste acampamento: **{existing_kingdom}**")
            kingdom_name = existing_kingdom
        else:
            kingdom_name = st.text_input("Digite o nome do Reino (ex: K1501):", placeholder="K1501")
        
        if kingdom_name:
            camp_id = camp_row["id"]

    if not st.button("💾 Salvar relatório", type="primary", use_container_width=True): return

    with st.spinner("Processando..."):
        try:
            fb = uploaded.getvalue()
            if len(fb) > 50*1024*1024: st.error("Arquivo muito grande (máx 50 MB)."); return
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            import_id, created = storage.save_import(
                filename=safe_name, report_date=report_date.isoformat(),
                file_hash=file_sha256(fb), stats=stats,
            )
            
            if created and camp_id and kingdom_name:
                metrics = calculate_metrics(stats, group_power=100_000_000)
                total_kp = int(metrics["kill_points"].sum())
                total_deaths = int(metrics["death_points"].sum())
                player_count = len(metrics)
                
                storage.save_kingdom_stats(
                    kvk_camp_id=camp_id,
                    import_id=import_id,
                    kingdom_name=kingdom_name,
                    total_kp=total_kp,
                    total_deaths=total_deaths,
                    player_count=player_count
                )
                st.success(f"✓ Reino **{kingdom_name}** importado e vinculado ao acampamento **{selected_camp}**!")
            elif created:
                st.success(f"✓ {len(stats):,} membros do seu reino salvos")
            else:
                st.warning("Arquivo já foi importado anteriormente.")
        except Exception as e:
            st.error(f"Erro: {e}")
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
        st.caption("Configure ADMIN_PASSWORD nas Secrets.")
        return False, False
    entered = st.text_input("Senha Admin", type="password", key="adm_pwd", label_visibility="collapsed", placeholder="Senha Mestra...")
    if is_admin_authenticated(pwd, entered):
        st.success("✓ Admin ativo"); return True, True
    if entered: st.error("Incorreta")
    return True, False

# ══════════════════════════════════════════════════════════════════════════════
# Gráficos Individuais (Curva Suave + Hover com números exatos)
# ══════════════════════════════════════════════════════════════════════════════

def _render_member_chart(storage, imports, username, character_id):
    if px is None or go is None: return st.caption("Plotly indisponível.")
    ordered = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    history_rows = []
    for _, imp_row in ordered.iterrows():
        try:
            stats = storage.load_stats(imp_row["id"])
            player_stats = stats[(stats["username"] == username) | (stats["character_id"].astype(str) == str(character_id))]
            if player_stats.empty: continue
            metrics = calculate_metrics(player_stats, group_power=100_000_000)
            ranked  = apply_goals(add_rank(metrics, "kill_points"))
            ranked["report_date"] = imp_row["report_date"]
            if "dead_equiv" not in ranked.columns: ranked["dead_equiv"] = 0
            history_rows.append(ranked)
        except Exception: continue

    if not history_rows: return st.caption("⚠️ Dados históricos insuficientes.")
    player_data = pd.concat(history_rows, ignore_index=True).sort_values("report_date")
    if player_data.empty: return st.caption("Dados insuficientes para gráfico.")

    fig = go.Figure()
    # KP (Ouro) - Curva Suave (shape='spline') e hover com número exato
    fig.add_trace(go.Scatter(
        x=player_data['report_date'], y=player_data['kill_points'],
        mode='lines+markers', name='Kill Points',
        line=dict(color='#d4a847', width=2, shape='spline'), marker=dict(size=6, color='#d4a847'),
        hovertemplate='<b>%{x|%d/%m/%Y}</b><br>KP: <b>%{y:,}</b><extra></extra>'
    ))
    # Mortes T4eq (Azul) - Curva Suave e hover com número exato
    fig.add_trace(go.Scatter(
        x=player_data['report_date'], y=player_data['dead_equiv'],
        mode='lines+markers', name='Deaths (T4 Equiv)',
        line=dict(color='#4a7cba', width=2, shape='spline'), marker=dict(size=6, color='#4a7cba'),
        hovertemplate='<b>%{x|%d/%m/%Y}</b><br>Mortos: <b>%{y:,}</b><extra></extra>'
    ))
    fig.update_layout(
        title=f"Evolução de {username}", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9ab0cc", family="Inter", size=11),
        yaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)", zeroline=False),
        xaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=0, t=40, b=0), height=250
    )
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB — RANKING (Estrutura original)
# ══════════════════════════════════════════════════════════════════════════════

def show_ranking(ranked_full: pd.DataFrame, key_prefix: str = "main") -> None:
    fc1, fc2, fc3 = st.columns([5, 2, 2])
    with fc1:
        search = st.text_input("search", placeholder="Buscar membro ou ID...", key=f"{key_prefix}_rank_search", label_visibility="collapsed")
    with fc2:
        sf = st.selectbox("status", ["All","Approved","Pending","Below goal"], key=f"{key_prefix}_rank_sf", label_visibility="collapsed")
    with fc3:
        sort_by = st.selectbox("sort", ["KP ↓","Power ↓","% KP ↓","% Deaths ↓","Name ↑"], key=f"{key_prefix}_rank_sort", label_visibility="collapsed")

    df = ranked_full.copy()
    top_5_pct_deaths = df['dead_equiv'].quantile(0.95) if 'dead_equiv' in df.columns else float('inf')
    df['emblems'] = ""
    for idx, row in df.iterrows():
        emb = ""
        if row.get('dead_equiv', 0) >= top_5_pct_deaths and row.get('dead_equiv', 0) > 0: emb += '<span title="Top 5% Deaths">🛡️</span> '
        if row.get('kill_points', 0) >= (row.get('kp_goal', 1) * 2) and row.get('kp_goal', 0) > 0: emb += '<span title="2x KP Goal">🔥</span> '
        if row.get('power', 0) >= 100_000_000: emb += '<span title="Whale (100M+ Power)">🐋</span> '
        df.at[idx, 'emblems'] = emb

    if search.strip():
        n = search.strip().lower()
        df = df[df["username"].astype(str).str.lower().str.contains(n,regex=False,na=False) | df["character_id"].astype(str).str.lower().str.contains(n,regex=False,na=False)]
    status_map_en2pt = {"Approved":"Aprovado","Pending":"Pendente","Below goal":"Abaixo da meta"}
    if sf != "All": df = df[df["status"] == status_map_en2pt.get(sf, sf)]
    sort_map = {"KP ↓":("kill_points",False),"Power ↓":("power",False),"% KP ↓":("kp_pct",False),"% Deaths ↓":("dead_pct",False),"Name ↑":("username",True)}
    scol, sasc = sort_map.get(sort_by, ("kill_points",False))
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    st.markdown(f'<div class="sec-label">Governadores · {len(df):,} of {len(ranked_full):,}</div>', unsafe_allow_html=True)
    page_size = st.selectbox("Por página",[10,25,50,100],index=1, key=f"{key_prefix}_rank_ps",label_visibility="collapsed")
    total_pg  = max(1,-(-len(df)//page_size))
    col_pg1, col_pg2 = st.columns([1,5])
    with col_pg1: page = st.number_input("Página",min_value=1,max_value=total_pg,value=1, key=f"{key_prefix}_rank_pg",label_visibility="collapsed")
    with col_pg2: st.markdown(f'<div style="font-size:.65rem;color:#9ab0cc;padding-top:8px">Página {page} de {total_pg}</div>', unsafe_allow_html=True)
    
    start = (page-1)*page_size
    _render_members(df.iloc[start:start+page_size], key_prefix=key_prefix)

    with st.expander("Exportar tabela completa →", expanded=False):
        cols_show = {
            "rank":"#","username":"Governador","character_id":"ID","power":"Poder","power_band":"Faixa",
            "kill_points":"KP","kp_goal":"Meta KP","t5_kills":"T5K","t4_kills":"T4K",
            "t3_kills":"T3K","t2_kills":"T2K","t1_kills":"T1K",
            "t5_deaths":"T5D","t4_deaths":"T4D","t3_deaths":"T3D","t2_deaths":"T2D","t1_deaths":"T1D",
            "dead_t4_goal":"Meta Morte","dead_equiv":"T4 Equiv.","status":"Status",
        }
        avail = {k:v for k,v in cols_show.items() if k in df.columns}
        out   = df[list(avail.keys())].rename(columns=avail)
        st.dataframe(out, use_container_width=True, hide_index=True)
        st.download_button("⬇ Baixar CSV", data=df.to_csv(index=False).encode(), file_name="ranking.csv", mime="text/csv", key=f"{key_prefix}_dl_csv")

def _render_members(df: pd.DataFrame, key_prefix: str = "main") -> None:
    storage = get_storage()
    imports = prepare_imports(storage.list_imports())
    for i, (_, row) in enumerate(df.iterrows()):
        cls    = STATUS_CLS.get(row["status"], "er")
        kp_w   = min(float(row.get("kp_pct",0))*100, 100)
        dead_w = min(float(row.get("dead_pct",0))*100, 100)
        kp_gap = int(row.get("kp_gap",0)); dead_gap = int(row.get("dead_gap_t4",0))
        kp_fc   = "full" if kp_w >= 100 else "kp"
        dead_fc = "full" if dead_w >= 100 else "dead"
        badge_cls = f"sbadge-{cls}"
        badge = (f'<span class="sbadge {badge_cls}">' f'{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</span>')

        with st.expander(label=f"#{int(row['rank'])}  {row['username']}", expanded=False):
            st.markdown(f"""
            <div class="mrow {cls}" style="margin-bottom:10px">
              <div class="mrow-sum" style="cursor:default">
                <div class="mrow-rank">#{int(row['rank'])}</div>
                <div class="mrow-info">
                  <div class="mrow-name">{row['username']} {row.get('emblems', '')}</div>
                  <div class="mrow-meta">{fmt_m(int(row['power']))}M power · {row.get('power_band','—')} · ID {row.get('character_id','—')}</div>
                </div>
                <div class="mrow-gauges">
                  <div><div class="gauge-head"><span>KP {kp_w:.0f}%</span><span>{fmt_k(int(row['kill_points']))}</span></div><div class="gauge-track"><div class="gauge-fill {kp_fc}" style="width:{kp_w:.1f}%"></div></div></div>
                  <div><div class="gauge-head"><span>D {dead_w:.0f}%</span><span>{fmt_k(int(row.get('dead_equiv',0)))} T4eq</span></div><div class="gauge-track"><div class="gauge-fill {dead_fc}" style="width:{dead_w:.1f}%"></div></div></div>
                </div>
                <div class="mrow-kp">{fmt_k(int(row['kill_points']))}</div>
                <div>{badge}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            _render_member_chart(storage, imports, row['username'], row.get('character_id', ''))

            t5d = int(row.get("t5_deaths",0)); t4d = int(row.get("t4_deaths",0))
            t3d = int(row.get("t3_deaths",0)); t2d = int(row.get("t2_deaths",0)); t1d = int(row.get("t1_deaths",0))
            dead_equiv = int(row.get("dead_equiv",0)); kp_fc_det = "full-kp" if kp_w >= 100 else "kp"
            dead_fc_det = "full-dead" if dead_w >= 100 else "dead"
            kp_gap_html = (f'<div class="mdet-gap ok">✓ Meta KP alcançada</div>' if kp_gap == 0 else f'<div class="mdet-gap warn">⚠ {fmt_k(kp_gap)} KP faltando</div>')
            dead_gap_html = (f'<div class="mdet-gap ok">✓ Meta morte alcançada</div>' if dead_gap == 0 else f'<div class="mdet-gap warn">⚠ {fmt_k(dead_gap)} T4eq faltando</div>')
            accent = '#3ba37a' if cls=='ok' else '#d4a03a' if cls=='wa' else '#c95a4e'
            
            st.markdown(f"""
            <div class="mdet">
              <div class="mdet-accent-bar" style="background:{accent}"></div>
              <div class="mdet-grid">
                <div>
                  <div class="mdet-block-label">Kill Points</div>
                  <div class="mdet-block-val">{fmt_int(int(row['kill_points']))}</div>
                  <div class="mdet-block-sub">Meta: {fmt_int(int(row['kp_goal']))}</div>
                  <div class="mdet-prog"><div class="mdet-prog-head"><span>{kp_w:.1f}%</span><span>{fmt_int(int(row['kill_points']))} / {fmt_int(int(row['kp_goal']))}</span></div><div class="mdet-prog-track"><div class="mdet-prog-fill {kp_fc_det}" style="width:{kp_w:.1f}%"></div></div></div>
                  {kp_gap_html}
                </div>
                <div>
                  <div class="mdet-block-label">Deaths (T4 equiv.)</div>
                  <div class="mdet-block-val">{fmt_int(dead_equiv)}</div>
                  <div class="mdet-block-sub">Meta: {fmt_int(int(row['dead_t4_goal']))}</div>
                  <div class="mdet-prog"><div class="mdet-prog-head"><span>{dead_w:.1f}%</span><span>{fmt_int(dead_equiv)} / {fmt_int(int(row['dead_t4_goal']))}</span></div><div class="mdet-prog-track"><div class="mdet-prog-fill {dead_fc_det}" style="width:{dead_w:.1f}%"></div></div></div>
                  {dead_gap_html}
                </div>
              </div>
            """, unsafe_allow_html=True)

            dc1, dc2 = st.columns(2)
            with dc1:
                t5k = int(row.get("t5_kills",0)); t4k = int(row.get("t4_kills",0)); t3k = int(row.get("t3_kills",0)); t2k = int(row.get("t2_kills",0)); t1k = int(row.get("t1_kills",0))
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
                <div style="font-size:.62rem;color:#9ab0cc;margin-top:8px">Total equiv: <span style="color:#4a7cba;font-family:monospace">{fmt_int(dead_equiv)}</span> / Meta: <span style="color:#5a7294;font-family:monospace">{fmt_int(int(row['dead_t4_goal']))}</span></div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB — KVK (NOVO SISTEMA MULTI-REINO COM GLASSMORPHISM)
# ══════════════════════════════════════════════════════════════════════════════

def show_kvk(storage, imports: pd.DataFrame, group_power: int, *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#4a7cba">
      <div class="rok-header-emblem" style="background:#162233; border-color:#4a7cba">🛡</div>
      <div>
        <div class="rok-header-title">Guerra dos Reinos (KvK)</div>
        <div class="rok-header-sub">Acompanhamento de campanhas por Acampamento e Reino</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    if admin_enabled and is_admin:
        with st.expander("➕ Criar nova Campanha (KvK)", expanded=False):
            c1, c2 = st.columns([3, 2])
            with c1:
                kvk_name = st.text_input("Nome da Campanha", placeholder="ex: #C13121 - Heroic Anthem", key="kvk_new_name")
                story_type = st.selectbox("História (Acampamentos)", list(KVK_STORIES.keys()), key="kvk_story_type")
            with c2:
                kvk_start = st.date_input("Início", key="kvk_new_start")
                kvk_end = st.date_input("Fim", key="kvk_new_end")
            
            camps_from_story = KVK_STORIES[story_type]["camps"]
            
            st.markdown("#### ⚔️ Defina os Reinos de cada Acampamento")
            camp_inputs = []
            cols = st.columns(4) if len(camps_from_story) <= 4 else st.columns(len(camps_from_story))
            for i, camp_name in enumerate(camps_from_story):
                with cols[i % len(cols)]:
                    kingdom = st.text_input(f"{camp_name}", placeholder="K1602", key=f"camp_{i}")
                    camp_inputs.append({"name": camp_name, "kingdom": kingdom, "sort_order": i})
            
            if st.button("Criar Campanha", type="primary", key="kvk_create_btn"):
                if not kvk_name.strip(): st.error("Digite um nome.")
                elif kvk_end < kvk_start: st.error("Data fim deve ser após início.")
                else:
                    storage.save_kvk_structure(
                        name=kvk_name.strip(), story_type=story_type,
                        start_date=kvk_start.isoformat(), end_date=kvk_end.isoformat(), camps=camp_inputs
                    )
                    st.success(f"✓ Campanha '{kvk_name}' criada com {len(camps_from_story)} acampamentos!")
                    st.rerun()

    structures = storage.list_kvk_structures()
    if structures.empty:
        st.markdown('<div class="empty-state"><div class="empty-state-icon">🛡</div><div class="empty-state-title">Nenhuma Campanha criada</div><div class="empty-state-sub">Um Admin pode criar uma campanha acima.</div></div>', unsafe_allow_html=True)
        return

    structures["label"] = structures["name"] + "  (" + structures["start_date"] + " → " + structures["end_date"] + ")"
    chosen_label = st.selectbox("Selecionar Campanha", structures["label"].tolist(), key="kvk_select", label_visibility="collapsed")
    kvk_row = structures.loc[structures["label"].eq(chosen_label)].iloc[0]
    kvk_id = kvk_row["id"]

    st.info("💡 Para importar planilhas de Reinos Inimigos, use o upload na barra lateral. O sistema identificará automaticamente a campanha ativa.")

    camps_df = storage.load_kvk_camps(kvk_id)
    st.markdown(f"""
    <div class="kvk-glass-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap;">
            <div>
                <h2 style="margin: 0; color: #d4a847; font-weight: 900; font-size: 1.6rem;">{kvk_row['name']}</h2>
                <div style="color: #9ab0cc; margin-top: 4px;">{kvk_row['story_type']} · {kvk_row['start_date']} → {kvk_row['end_date']}</div>
            </div>
            <div style="display: flex; gap: 30px; margin-top: 10px;">
                <div style="text-align: center;">
                    <div style="font-size: 0.65rem; color: #9ab0cc; text-transform: uppercase; letter-spacing: 0.1em;">KP Total</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; color: #d4a847;">Agregando...</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 0.65rem; color: #9ab0cc; text-transform: uppercase; letter-spacing: 0.1em;">Mortes (T4)</div>
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; color: #4a7cba;">Agregando...</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if camps_df.empty:
        st.warning("Esta campanha não possui acampamentos definidos.")
        return

    camp_tabs = st.tabs([f"🏕️ {row['camp_name']} ({row['kingdom']})" for _, row in camps_df.iterrows()])
    
    for idx, (_, camp_row) in enumerate(camps_df.iterrows()):
        with camp_tabs[idx]:
            st.markdown(f'<div class="sec-label">Acampamento: {camp_row["camp_name"]}</div>', unsafe_allow_html=True)
            
            kingdom_stats = storage.load_kingdom_stats(camp_row["id"])
            
            if kingdom_stats.empty:
                st.info(f"Nenhum relatório de reino inimigo foi importado para o acampamento **{camp_row['camp_name']}** ainda. Use a barra lateral para importar.")
            else:
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    total_kp = int(kingdom_stats["total_kp"].sum())
                    st.metric("🎯 KP Total do Acampamento", fmt_k(total_kp))
                with c2:
                    total_deaths = int(kingdom_stats["total_deaths"].sum())
                    st.metric("💀 Mortes Totais (T4)", fmt_k(total_deaths))
                with c3:
                    st.metric("👥 Reinos", len(kingdom_stats))
                
                st.markdown("#### 📊 Reinos neste Acampamento")
                st.dataframe(
                    kingdom_stats[["kingdom_name", "total_kp", "total_deaths", "player_count", "uploaded_at"]].rename(columns={
                        "kingdom_name": "Reino", "total_kp": "KP Total", "total_deaths": "Mortes T4", "player_count": "Jogadores", "uploaded_at": "Atualizado"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
    
    if admin_enabled and is_admin:
        with st.expander("🗑️ Excluir esta campanha", expanded=False):
            st.warning("Isso apagará a campanha e todos os dados de reinos importados nela. Os relatórios brutos permanecem.")
            if st.button("Confirmar exclusão da campanha", type="secondary", key="kvk_del_btn"):
                if storage.delete_kvk_event(kvk_id):
                    st.success("Excluída."); st.rerun()
                else: st.error("Falha ao excluir.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB — Hall of Fame (Original)
# ══════════════════════════════════════════════════════════════════════════════

def show_hof(storage, imports: pd.DataFrame, group_power: int, *, is_admin: bool, admin_enabled: bool) -> None:
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
        st.markdown('<div class="empty-state"><div class="empty-state-icon">🏆</div><div class="empty-state-title">Nenhum KvK criado</div><div class="empty-state-sub">Crie um KvK na aba 🛡 KvK.</div></div>', unsafe_allow_html=True)
        return

    events = events.copy()
    events["start_date"] = pd.to_datetime(events["start_date"]).dt.date.astype(str)
    events["end_date"]   = pd.to_datetime(events["end_date"]).dt.date.astype(str)
    events["label"]      = events["name"] + "  (" + events["start_date"] + " → " + events["end_date"] + ")"

    chosen_label = st.selectbox("KvK Event", events["label"].tolist(), key="hof_kvk", label_visibility="collapsed")
    event_row = events.loc[events["label"].eq(chosen_label)].iloc[0]
    start_d   = pd.to_datetime(event_row["start_date"]).date()
    end_d     = pd.to_datetime(event_row["end_date"]).date()

    imports_cp = imports.copy()
    imports_cp["_d"] = pd.to_datetime(imports_cp["report_date"]).dt.date
    in_window = imports_cp[(imports_cp["_d"] >= start_d) & (imports_cp["_d"] <= end_d)]

    if in_window.empty:
        st.warning("Nenhum relatório encontrado para este evento.")
        return

    ranked = compute_kvk_accumulated(storage, imports, group_power, start_d, end_d)
    if ranked.empty:
        st.info("Sem dados para este KvK.")
        return

    if "dead_equiv" not in ranked.columns:
        ranked["dead_equiv"] = (ranked.get("t4_deaths", 0) + ranked.get("t5_deaths", 0) * 2).fillna(0).astype(int)

    top10_kp   = ranked.sort_values("kill_points", ascending=False).head(10).reset_index(drop=True)
    top10_dead = ranked.sort_values("dead_equiv", ascending=False).head(10).reset_index(drop=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:#d4a847;margin-bottom:10px">⚔ Top 10 Kill Points</div>', unsafe_allow_html=True)
        _render_hof_list(top10_kp, "kp")
    with c2:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:#4a7cba;margin-bottom:10px">💀 Top 10 Deaths</div>', unsafe_allow_html=True)
        _render_hof_list(top10_dead, "deaths")

def _render_hof_list(df: pd.DataFrame, category: str) -> None:
    if df.empty: return
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
        <div style="display:flex;align-items:center;gap:10px;padding:{"12px 14px" if is_top else "9px 14px"};background:{"rgba(212, 168, 71, 0.08)" if is_top else "transparent"};border:1px solid {"rgba(212, 168, 71, 0.2)" if is_top else "rgba(42, 63, 94, 0.5)"};border-radius:6px;margin-bottom:5px;">
          <div style="font-size:{"1.2rem" if is_top else ".85rem"};min-width:28px;text-align:center">{medal}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:{"0.88rem" if is_top else "0.82rem"};font-weight:{"700" if is_top else "500"};color:#f0f4fa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{row["username"]}</div>
            <div style="font-size:.62rem;color:#9ab0cc;margin-top:1px">{fmt_m(power)}M power</div>
          </div>
          <div style="font-family:"JetBrains Mono",monospace;font-size:{"1rem" if is_top else "0.85rem"};font-weight:600;color:{color};white-space:nowrap">{fmt_k(value)} {unit}</div>
        </div>
        ''', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB — Kingdom (Original)
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

    st.markdown('<div class="sec-label">Operações do Reino</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kd-row">
      <div class="kd-card amber"><div class="kd-card-label">Total Kill Points</div><div class="kd-card-value">{fmt_k(kp_total)}</div><div class="kd-card-sub">pontos acumulados</div></div>
      <div class="kd-card blue"><div class="kd-card-label">Total Power</div><div class="kd-card-value">{fmt_m(power_total)}M</div><div class="kd-card-sub">poder combinado</div></div>
      <div class="kd-card green"><div class="kd-card-label">Governadores</div><div class="kd-card-value">{total:,}</div><div class="kd-card-sub">{active} ativos</div></div>
      <div class="kd-card green"><div class="kd-card-label">Taxa de Aprovação</div><div class="kd-card-value">{aprov_pct:.1f}%</div><div class="kd-card-sub">{approved} de {total}</div></div>
      <div class="kd-card red"><div class="kd-card-label">Abaixo da Meta</div><div class="kd-card-value">{below}</div><div class="kd-card-sub">{pending} pendentes</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Status das Metas</div>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    for col, lbl, count, color in [(m1,"Aprovados", approved,"#3ba37a"),(m2,"Pendentes", pending,"#d4a03a"),(m3,"Abaixo", below,"#c95a4e")]:
        pct = count/total*100 if total else 0
        with col:
            st.markdown(f'<div class="sm-card"><div class="sm-label">{lbl}</div><div><span class="sm-count" style="color:{color}">{count}</span><span class="sm-denom">/ {total}</span></div><div class="sm-bar"><div class="sm-fill" style="width:{pct:.1f}%;background:{color}"></div></div><div class="sm-pct">{pct:.1f}% da aliança</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Faixas de Poder</div>', unsafe_allow_html=True)
    bands = []
    for pmin, pmax, dead_t4, _, kp in GOAL_TABLE:
        lbl = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax!=float("inf") else f"{pmin//1_000_000}M+"
        sub = ranked[ranked["power_band"]==lbl] if "power_band" in ranked else pd.DataFrame()
        if sub.empty: continue
        ok  = int((sub["status"]=="Aprovado").sum()); wa  = int((sub["status"]=="Pendente").sum()); er  = int((sub["status"]=="Abaixo da meta").sum())
        bands.append({"Band":lbl,"Total":len(sub),"✅":ok,"🟡":wa,"❌":er,"Total KP":fmt_k(int(sub["kill_points"].sum())), "KP Goal":fmt_k(kp)})
    if bands:
        st.markdown('<table class="band-table"><tr><th>Faixa</th><th>Total</th><th>✅</th><th>🟡</th><th>❌</th><th>Total KP</th><th>Meta KP</th></tr>' + "".join(f'<tr><td>{b["Band"]}</td><td>{b["Total"]}</td><td>{b["✅"]}</td><td>{b["🟡"]}</td><td>{b["❌"]}</td><td>{b["Total KP"]}</td><td>{b["KP Goal"]}</td></tr>' for b in bands) + '</table>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Precisam de Atenção & Lista de Email</div>', unsafe_allow_html=True)
    col_att, col_mail = st.columns([2, 1])
    att = ranked[ranked["status"]!="Aprovado"].sort_values("kp_pct").head(8)
    with col_att:
        if att.empty: st.success("Todos os membros estão aprovados!")
        else:
            for _, row in att.iterrows():
                cls  = STATUS_CLS.get(row["status"],"er")
                kp_p = min(float(row.get("kp_pct",0))*100, 100)
                dp_p = min(float(row.get("dead_pct",0))*100, 100)
                st.markdown(f'<div class="att-row {cls}"><div class="att-name">{row["username"]}</div><div class="att-pow">{fmt_m(int(row["power"]))}M</div><div class="att-pcts">KP {kp_p:.0f}% · Deaths {dp_p:.0f}%</div><div class="sbadge sbadge-{cls}">{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</div></div>', unsafe_allow_html=True)
    with col_mail:
        abaixo = ranked[ranked['status'] != 'Aprovado']
        if not abaixo.empty:
            st.code(",".join(abaixo['character_id'].astype(str).tolist()), language="text")
        else: st.success("Sem envio de email necessário.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB — Profile (Original)
# ══════════════════════════════════════════════════════════════════════════════

def show_profile(storage, imports, gp):
    st.markdown('<div class="sec-label">Rastreador de Jogador</div>', unsafe_allow_html=True)
    if imports.empty: st.info("Importe mais relatórios."); return
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)

    @st.cache_data(ttl=300)
    def _all_player_names(storage_label, import_ids_key):
        all_names = set(); storage = get_storage()
        for imp_id in import_ids_key:
            try: all_names.update(storage.load_stats(imp_id)["username"].dropna().tolist())
            except: pass
        return sorted(all_names)
    
    player_list = _all_player_names(storage.label, tuple(ordered["id"].tolist()))
    if not player_list: st.info("Nenhum jogador encontrado."); return
    selected_player = st.selectbox("Selecione ou busque:", player_list, key="profile_player")
    if not selected_player: return

    history_rows = []
    for _, imp_row in ordered.iterrows():
        try:
            stats = storage.load_stats(imp_row["id"])
            player_stats = stats[stats["username"] == selected_player]
            if player_stats.empty: continue
            metrics = calculate_metrics(player_stats, group_power=gp)
            ranked  = apply_goals(add_rank(metrics, "kill_points"))
            ranked["report_date"] = imp_row["report_date"]
            history_rows.append(ranked)
        except Exception: continue

    if not history_rows: st.warning(f"Sem dados para **{selected_player}**."); return
    player_data = pd.concat(history_rows, ignore_index=True).sort_values("report_date")
    latest = player_data.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Poder Atual", f"{fmt_m(int(latest['power']))}M")
    with c2: st.metric("KP (Atual)", fmt_k(int(latest['kill_points'])))
    with c3: st.metric("Mortes T4eq", fmt_k(int(latest.get('dead_equiv', 0))))
    with c4: st.metric("Status", STATUS_LABEL.get(latest['status'], latest['status']))

    if px is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data['kill_points'], mode='lines+markers', name='Kill Points (cumulativo)', line=dict(color='#d4a847', shape='spline')))
        fig.add_trace(go.Scatter(x=player_data['report_date'], y=player_data.get('dead_equiv', 0), mode='lines+markers', name='Mortes T4eq (cumulativo)', line=dict(color='#4a7cba', shape='spline')))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#9ab0cc", family="Inter"), yaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)"), xaxis=dict(gridcolor="rgba(42, 63, 94, 0.5)"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Tabela de histórico completa", expanded=False):
        cols = {"report_date":"Data","kill_points":"KP","dead_equiv":"Mortes T4eq","power":"Poder","status":"Status"}
        avail = {k:v for k,v in cols.items() if k in player_data.columns}
        st.dataframe(player_data[list(avail.keys())].rename(columns=avail), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB — Help
# ══════════════════════════════════════════════════════════════════════════════

def show_help():
    st.markdown("""
    <div class="sec-label">Guia Rápido</div>
    <ul style="color: #9ab0cc;">
        <li><b>Nova Senha de Upload:</b> A senha para importar planilhas é: <code>UXUI1602!</code></li>
        <li><b>KvK:</b> Administradores podem criar campanhas. Escolha a história para gerar os acampamentos automaticamente.</li>
        <li><b>Upload Multi-Reino:</b> Ao importar uma planilha dentro de uma campanha ativa, o sistema perguntará a qual acampamento ela pertence.</li>
    </ul>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    st.html(_css())
    storage = get_storage()

    st.markdown("""
    <div class="rok-header">
      <div class="rok-header-emblem">⚔️</div>
      <div><div class="rok-header-title">K1602 · KP Dashboard</div><div class="rok-header-sub">Kill Points Operations Center · Rise of Kingdoms</div></div>
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
        st.markdown('<div class="sb-sec">Sistema</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:.68rem;color:#8398b5;margin-bottom:12px">Armazenamento: <span style="color:#4a7cba;font-weight:bold;">{storage.label}</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sec">Relatórios</div>', unsafe_allow_html=True)
        
        active_kvk_id = None; active_camps = None
        structures = storage.list_kvk_structures()
        if not structures.empty:
            latest = structures.iloc[0]
            today = date.today()
            start = pd.to_datetime(latest["start_date"]).date()
            end   = pd.to_datetime(latest["end_date"]).date()
            if start <= today <= end:
                active_kvk_id = latest["id"]
                active_camps = storage.load_kvk_camps(active_kvk_id)

        handle_upload(storage, active_kvk_id, active_camps)

    imports = storage.list_imports()
    if imports.empty:
        st.markdown('<div class="empty-state"><div class="empty-state-icon">⚔️</div><div class="empty-state-title">Nenhum relatório importado</div><div class="empty-state-sub">Faça o upload de um statsExport na barra lateral.</div></div>', unsafe_allow_html=True)
        return
    imports = prepare_imports(imports)

    with st.sidebar:
        st.markdown('<div class="sb-sec">Filtros</div>', unsafe_allow_html=True)
        min_power = st.number_input("Poder Mínimo (Milhões)", min_value=0, value=0, step=1, format="%d", help="Filtra governadores abaixo deste poder") * 1_000_000
        min_kp = st.number_input("KP Mínimo", min_value=0, value=0, step=1000, format="%d", help="Filtra governadores com KP abaixo disto")
        min_kp_pct = st.slider("% KP Mínimo", min_value=0, max_value=100, value=0, step=5, help="Filtra por % mínima da meta de KP")
        min_dead_pct = st.slider("% Mortes Mínimo", min_value=0, max_value=100, value=0, step=5, help="Filtra por % mínima da meta de mortes")
        if st.button("🔄 Resetar Filtros", use_container_width=True, type="secondary"):
            st.session_state.min_power = 0; st.session_state.min_kp = 0; st.session_state.min_kp_pct = 0; st.session_state.min_dead_pct = 0; st.rerun()
        st.markdown('<div class="sb-sec">Admin</div>', unsafe_allow_html=True)
        admin_enabled, is_admin = admin_panel()

    gp = default_group_power(storage, imports)

    all_dates = sorted(imports["report_date"].unique())
    min_d = pd.to_datetime(all_dates[0]).date(); max_d = pd.to_datetime(all_dates[-1]).date()
    st.markdown('<div class="sec-label" style="margin-top:0">Período de Análise</div>', unsafe_allow_html=True)
    with st.container():
        dcol1, dcol2, dcol3, dcol4, dcol5 = st.columns([1.5, 1.5, 1, 1, 3])
        with dcol1: date_from = st.date_input("Início", value=min_d, min_value=min_d, max_value=max_d, key="main_date_from", format="YYYY-MM-DD")
        with dcol2: date_to = st.date_input("Fim", value=max_d, min_value=min_d, max_value=max_d, key="main_date_to", format="YYYY-MM-DD")
        with dcol3: st.markdown("<br>", unsafe_allow_html=True); 
        if st.button("🔄 Este Mês", key="btn_this_month", use_container_width=True):
            today = date.today(); date_from = today.replace(day=1); date_to = today; st.rerun()
        with dcol4: st.markdown("<br>", unsafe_allow_html=True); 
        if st.button("📅 Todos", key="btn_all_time", use_container_width=True):
            date_from = min_d; date_to = max_d; st.rerun()
        with dcol5: st.markdown(f'<div style="padding-top:8px;font-size:.72rem;color:#9ab0cc"><span style="color:#d4a847;font-weight:600">{len(imports[(pd.to_datetime(imports["report_date"]).dt.date >= date_from) & (pd.to_datetime(imports["report_date"]).dt.date <= date_to)])}</span> relatórios no período</div>', unsafe_allow_html=True)

    if date_from > date_to: st.error("⚠️ Data de início deve ser anterior à data final."); return
    ranked, first_date, last_date = compute_accumulated_sum(storage, imports, gp, date_from=date_from, date_to=date_to)
    if ranked.empty: st.warning("Nenhum relatório encontrado no período."); return

    filter_conditions = pd.Series(True, index=ranked.index)
    if min_power > 0: filter_conditions &= pd.to_numeric(ranked["power"], errors="coerce").fillna(0) >= min_power
    if min_kp > 0: filter_conditions &= pd.to_numeric(ranked["kill_points"], errors="coerce").fillna(0) >= min_kp
    if min_kp_pct > 0: filter_conditions &= (pd.to_numeric(ranked["kp_pct"], errors="coerce").fillna(0) * 100) >= min_kp_pct
    if min_dead_pct > 0: filter_conditions &= (pd.to_numeric(ranked["dead_pct"], errors="coerce").fillna(0) * 100) >= min_dead_pct
    ranked = ranked[filter_conditions]
    if ranked.empty: st.warning("Nenhum governador corresponde aos filtros."); return

    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">De <span class="rok-caption-val">{first_date}</span></div>
      <div class="rok-caption-sep">→</div>
      <div class="rok-caption-item"><span class="rok-caption-val">{last_date}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Membros <span class="rok-caption-val">{len(ranked):,}</span></div>
    </div>
    """, unsafe_allow_html=True)

    tab_labels = ["⚔ Ranking", "🛡 KvK", "🏆 Hall of Fame", "🏰 Reino", "👤 Perfil", "❓ Ajuda"]
    if admin_enabled and is_admin: tab_labels.extend(["📈 Histórico", "📁 Imports"])

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

if __name__ == "__main__":
    main()
