
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
from storage import create_storage

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:
    px = None; go = None

KVK_STORIES = {
    "Heroic Anthem":           ["Fire", "Water", "Earth", "Wind"],
    "Heroic Anthem: Power Up": ["Fire", "Water", "Earth", "Wind"],
    "Desert Conquest":         ["Fire", "Water", "Earth", "Wind"],
    "Orleans Campaign":        ["Fire", "Water", "Earth", "Wind"],
    "Nile":                    ["Fire", "Water", "Earth", "Wind"],
    "Warriors Unbound":        ["Fire", "Water", "Earth", "Wind"],
    "Kingdom of Aurics":       ["Aurics", "Glaciers", "Storms", "Embers", "Tides", "Verdure"],
    "Strife of the Eight":     ["Dragon", "Tiger", "Lion", "Bear", "Wolf", "Raven", "Lotus", "Viper"],
}

CAMP_ICONS = {
    "Fire":"🔥","Water":"💧","Earth":"🌍","Wind":"🌪️",
    "Aurics":"✨","Glaciers":"❄️","Storms":"⚡","Embers":"🔥",
    "Tides":"🌊","Verdure":"🌿","Dragon":"🐉","Tiger":"🐅",
    "Lion":"🦁","Bear":"🐻","Wolf":"🐺","Raven":"🐦","Lotus":"🪷","Viper":"🐍",
}

st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_resource
def _css() -> str:
    bg      = "#0e1a2b"
    surf    = "#162233"
    surf2   = "#1c2a3f"
    bdr     = "#2a3f5e"
    txt     = "#f0f4fa"
    sub     = "#9ab0cc"
    mut     = "#5a7294"
    gold    = "#d4a847"
    blue    = "#4a7cba"
    green   = "#3ba37a"
    yellow  = "#d4a03a"
    red     = "#c95a4e"
    sb      = "#0a131f"
    sbt     = "#8398b5"
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body,[class*="css"],.stApp{{font-family:'Inter',system-ui,sans-serif!important;background:{bg}!important;color:{txt}!important}}
.main .block-container{{padding:1.2rem 2rem 3rem!important;max-width:1500px!important;background:{bg}!important}}
section[data-testid="stSidebar"]{{background:{sb}!important;border-right:1px solid {bdr}!important}}
section[data-testid="stSidebar"]>div{{padding:1.5rem 1rem!important}}
section[data-testid="stSidebar"] *{{color:{sbt}!important}}
section[data-testid="stSidebar"] .stSuccess p{{color:{green}!important}}
section[data-testid="stSidebar"] .stError p{{color:{red}!important}}
section[data-testid="stSidebar"] .stWarning p{{color:{yellow}!important}}
.sb-sec{{font-size:.58rem;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:{sbt};border-bottom:1px solid {bdr};padding-bottom:6px;margin:14px 0 10px}}
[data-testid="stMetric"]{{background:{surf}!important;border:1px solid {bdr}!important;border-radius:8px!important;padding:16px 20px!important;position:relative;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
[data-testid="stMetric"]::after{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:{blue}}}
[data-testid="stMetricLabel"]{{font-size:.62rem!important;font-weight:600!important;text-transform:uppercase;letter-spacing:.08em;color:{sub}!important}}
[data-testid="stMetricValue"]{{font-family:'JetBrains Mono',monospace!important;font-size:1.6rem!important;font-weight:600!important;color:{txt}!important;letter-spacing:-.03em}}
[data-testid="stTabs"] [role="tablist"]{{border-bottom:1px solid {bdr};gap:0;background:transparent;flex-wrap:wrap}}
[data-testid="stTabs"] button[role="tab"]{{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.10em;color:{mut}!important;padding:10px 20px;border-bottom:2px solid transparent;border-radius:0;background:transparent!important;transition:color .2s,border-color .2s}}
[data-testid="stTabs"] button[role="tab"]:hover{{color:{gold}!important}}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"]{{color:{gold}!important;border-bottom-color:{gold}!important;background:transparent!important}}
[data-testid="stTextInput"] input,[data-testid="stSelectbox"]>div>div,[data-testid="stNumberInput"] input{{background:{surf2}!important;border:1px solid {bdr}!important;border-radius:6px!important;color:{txt}!important;font-family:'Inter',sans-serif!important;font-size:.82rem!important}}
[data-testid="stButton"] button{{background:{blue}!important;color:#fff!important;border:none!important;border-radius:6px!important;font-weight:700!important;font-size:.78rem!important;text-transform:uppercase;letter-spacing:.08em;transition:all .2s;box-shadow:0 2px 6px rgba(0,0,0,.3)}}
[data-testid="stButton"] button:hover{{background:{gold}!important;transform:translateY(-1px);color:#000!important}}
[data-testid="stButton"] button[kind="secondary"]{{background:transparent!important;border:1px solid {bdr}!important;color:{sub}!important}}
[data-testid="stDataFrame"]{{border:1px solid {bdr}!important;border-radius:8px!important;overflow:hidden;background:{surf}}}
hr{{border-color:{bdr}!important;margin:1.2rem 0!important}}
.rok-header{{display:flex;align-items:center;gap:18px;padding:16px 24px;margin-bottom:18px;background:{surf}!important;border:1px solid {bdr};border-radius:8px;position:relative;box-shadow:0 4px 12px rgba(0,0,0,.3)}}
.rok-header::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,{blue} 0%,{gold} 100%)}}
.rok-header-emblem{{width:48px;height:48px;flex-shrink:0;background:{surf2};border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:1.6rem;border:1px solid {gold}}}
.rok-header-title{{font-size:1.4rem;font-weight:900;color:{txt};letter-spacing:-.03em;line-height:1}}
.rok-header-sub{{font-size:.7rem;color:{sub};letter-spacing:.05em;margin-top:4px;text-transform:uppercase}}
.tier-pills{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:18px}}
.tier-pill{{padding:4px 12px;border-radius:4px;font-size:.65rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;border:1px solid}}
.tp-t5{{color:{gold};border-color:{gold};background:rgba(212,168,71,.1)}}
.tp-t4{{color:#cf6f3a;border-color:#cf6f3a;background:rgba(207,111,58,.1)}}
.tp-t3{{color:#7d5eb8;border-color:#7d5eb8;background:rgba(125,94,184,.1)}}
.tp-t2{{color:#3f93a6;border-color:#3f93a6;background:rgba(63,147,166,.1)}}
.tp-t1{{color:{mut};border-color:{mut};background:rgba(90,114,148,.1)}}
.tp-eq{{color:{mut};border-color:{bdr};background:rgba(255,255,255,.03)}}
.sec-label{{font-size:.6rem;font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:{gold};display:flex;align-items:center;gap:10px;margin:20px 0 12px}}
.sec-label::after{{content:'';flex:1;height:1px;background:{bdr}}}
.sbadge{{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:4px;font-size:.63rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;white-space:nowrap;border:1px solid}}
.sbadge-ok{{color:{green};border-color:{green};background:rgba(59,163,122,.15)}}
.sbadge-wa{{color:{yellow};border-color:{yellow};background:rgba(212,160,58,.15)}}
.sbadge-er{{color:{red};border-color:{red};background:rgba(201,90,78,.15)}}
.mrow{{background:{surf};border:1px solid {bdr};border-radius:6px;margin-bottom:4px;overflow:hidden;transition:border-color .2s}}
.mrow:hover{{border-color:{gold};background:{surf2}}}
.mrow.ok{{border-left:3px solid {green}}}
.mrow.wa{{border-left:3px solid {yellow}}}
.mrow.er{{border-left:3px solid {red}}}
.mrow-sum{{display:grid;grid-template-columns:36px 1fr 90px 80px auto;align-items:center;gap:12px;padding:12px 16px}}
.mrow-rank{{font-family:'JetBrains Mono',monospace;font-size:.85rem;font-weight:600;color:{mut};text-align:right}}
.mrow-name{{font-size:.88rem;font-weight:700;color:{txt};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mrow-meta{{font-size:.64rem;color:{sub};margin-top:2px}}
.mrow-gauges{{display:flex;flex-direction:column;gap:5px}}
.gauge-head{{display:flex;justify-content:space-between;font-size:.58rem;color:{sub};margin-bottom:2px}}
.gauge-track{{height:5px;background:{bg};border-radius:99px;overflow:hidden;border:1px solid {bdr}}}
.gauge-fill{{height:100%;border-radius:99px}}
.gauge-fill.kp{{background:{gold}}}
.gauge-fill.dead{{background:{blue}}}
.gauge-fill.full{{background:{green}}}
.mrow-kp{{font-family:'JetBrains Mono',monospace;font-size:.9rem;font-weight:600;color:{gold};text-align:right;white-space:nowrap}}
.mdet{{border-top:1px solid {bdr};background:{bg};padding:16px 20px 20px;border-radius:0 0 6px 6px}}
.mdet-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:16px}}
.mdet-block-label{{font-size:.58rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:{sub};margin-bottom:6px}}
.mdet-block-val{{font-family:'JetBrains Mono',monospace;font-size:1.6rem;font-weight:600;color:{txt};letter-spacing:-.04em;line-height:1}}
.mdet-block-sub{{font-size:.65rem;color:{mut};margin-top:4px}}
.mdet-prog{{margin-top:8px}}
.mdet-prog-head{{display:flex;justify-content:space-between;font-size:.6rem;color:{sub};margin-bottom:3px}}
.mdet-prog-track{{height:8px;background:{bg};border-radius:99px;overflow:hidden;border:1px solid {bdr}}}
.mdet-prog-fill{{height:100%;border-radius:99px}}
.mdet-prog-fill.kp{{background:{gold}}}
.mdet-prog-fill.dead{{background:{blue}}}
.mdet-gap{{font-size:.62rem;color:{sub};margin-top:4px}}
.mdet-gap.warn{{color:{red}}}
.mdet-gap.ok{{color:{green}}}
.tier-table{{width:100%;border-collapse:collapse;margin-top:4px}}
.tier-table th{{font-size:.58rem;font-weight:700;text-transform:uppercase;letter-spacing:.10em;color:{sub};padding:5px 8px;text-align:right;border-bottom:1px solid {bdr}}}
.tier-table th:first-child{{text-align:left}}
.tier-table td{{font-family:'JetBrains Mono',monospace;font-size:.75rem;color:{txt};padding:5px 8px;text-align:right;border-bottom:1px solid {surf2}}}
.tier-table td:first-child{{text-align:left;color:{sub};font-weight:600}}
.tier-table tr:last-child td{{border-bottom:none}}
.tier-table td.amber{{color:{gold}}}
.tier-table td.blue{{color:{blue}}}
.tier-table td.equiv{{color:{mut};font-size:.68rem}}
.kd-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:18px}}
.kd-card{{background:{surf};border:1px solid {bdr};border-radius:8px;padding:14px 16px;position:relative;overflow:hidden}}
.kd-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
.kd-card.amber::before{{background:{gold}}}
.kd-card.green::before{{background:{green}}}
.kd-card.yellow::before{{background:{yellow}}}
.kd-card.red::before{{background:{red}}}
.kd-card.blue::before{{background:{blue}}}
.kd-card-label{{font-size:.56rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:{sub};margin-bottom:4px}}
.kd-card-value{{font-family:'JetBrains Mono',monospace;font-size:1.35rem;font-weight:600;color:{txt};letter-spacing:-.03em;line-height:1}}
.kd-card-sub{{font-size:.62rem;color:{mut};margin-top:3px}}
.rok-caption{{display:flex;align-items:center;gap:14px;padding:8px 14px;margin-bottom:16px;background:{surf};border:1px solid {bdr};border-radius:6px;flex-wrap:wrap}}
.rok-caption-item{{font-size:.68rem;color:{sub}}}
.rok-caption-val{{color:{gold};font-weight:600}}
.rok-caption-sep{{color:{mut};font-size:.7rem}}
.empty-state{{text-align:center;padding:60px 20px;background:{surf};border:1px dashed {bdr};border-radius:12px}}
.empty-state-icon{{font-size:3rem;margin-bottom:14px;opacity:.4}}
.empty-state-title{{font-size:1rem;font-weight:700;color:{sub};margin-bottom:6px}}
.empty-state-sub{{font-size:.75rem;color:{mut}}}
.filter-tag{{display:inline-block;padding:3px 10px;border-radius:4px;font-size:.62rem;font-weight:600;background:rgba(74,124,186,.15);color:{blue};border:1px solid rgba(74,124,186,.3)}}
.att-row{{display:grid;grid-template-columns:1fr 60px 140px auto;align-items:center;gap:12px;padding:10px 14px;background:{surf};border:1px solid {bdr};border-radius:6px;margin-bottom:5px}}
.att-row.er{{border-left:3px solid {red}}}
.att-row.wa{{border-left:3px solid {yellow}}}
.upload-lock{{background:{surf};border:1px solid {bdr};border-radius:6px;padding:14px;text-align:center;margin-bottom:10px}}
.upload-lock-icon{{font-size:1.3rem;margin-bottom:6px}}
.upload-lock-text{{font-size:.72rem;color:{sub};margin-bottom:10px}}
.band-table{{width:100%;border-collapse:collapse}}
.band-table th{{font-size:.58rem;font-weight:700;text-transform:uppercase;letter-spacing:.10em;color:{sub};padding:8px 12px;text-align:right;border-bottom:1px solid {bdr}}}
.band-table th:first-child{{text-align:left}}
.band-table td{{font-family:'JetBrains Mono',monospace;font-size:.76rem;color:{txt};padding:8px 12px;text-align:right;border-bottom:1px solid {surf2}}}
.band-table td:first-child{{text-align:left;color:{sub};font-weight:600;font-family:'Inter',sans-serif;font-size:.78rem}}
.band-table tr:last-child td{{border-bottom:none}}
.realm-card{{background:{surf};border:1px solid {bdr};border-radius:8px;margin-bottom:8px;overflow:hidden}}
.realm-card-header{{display:grid;grid-template-columns:1fr auto auto auto auto;align-items:center;gap:12px;padding:12px 16px;background:{surf2}}}
.realm-title{{font-size:.9rem;font-weight:700;color:{txt}}}
.realm-stat{{font-family:'JetBrains Mono',monospace;font-size:.8rem;color:{sub};white-space:nowrap}}
.realm-stat span{{color:{gold};font-weight:600}}
</style>
"""

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

def fmt_int(v):   return f"{int(v):,}"
def fmt_k(v):
    v = int(v)
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}k"
    return str(v)
def fmt_m(v): return f"{int(v)/1_000_000:.0f}"


def compute_accumulated_sum(storage, imports, group_power, date_from=None, date_to=None):
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    ordered["_d"] = pd.to_datetime(ordered["report_date"]).dt.date
    if date_from: ordered = ordered[ordered["_d"] >= date_from]
    if date_to:   ordered = ordered[ordered["_d"] <= date_to]
    if ordered.empty: return pd.DataFrame(), "", ""

    first_date = str(ordered.iloc[0]["report_date"])
    last_date  = str(ordered.iloc[-1]["report_date"])

    sum_cols = ["t1_kills","t2_kills","t3_kills","t4_kills","t5_kills",
                "t1_deaths","t2_deaths","t3_deaths","t4_deaths","t5_deaths","resources_gathered"]
    acc = {}

    for _, imp_row in ordered.iterrows():
        stats = storage.load_stats(imp_row["id"])
        for _, p in stats.iterrows():
            cid = str(p["character_id"])
            if cid not in acc:
                acc[cid] = {"character_id": cid, "username": p["username"]}
                for c in sum_cols: acc[cid][c] = 0
            for c in sum_cols:
                if c in p:
                    try:
                        val = p[c]
                        if pd.notna(val): acc[cid][c] += int(float(val))
                    except: pass

    if not acc: return pd.DataFrame(), "", ""
    result = pd.DataFrame(list(acc.values()))

    last_stats = storage.load_stats(ordered.iloc[-1]["id"])
    pmap = {}
    for _, p in last_stats.iterrows():
        try: pmap[str(p["character_id"])] = int(float(p["power"])) if pd.notna(p["power"]) else 0
        except: pmap[str(p["character_id"])] = 0
    result["power"] = result["character_id"].map(pmap).fillna(0).astype(int)

    metrics = calculate_metrics(result, group_power=group_power)
    ranked  = apply_goals(add_rank(metrics, "kill_points"))
    if "dead_equiv" not in ranked.columns:
        ranked["dead_equiv"] = (ranked.get("t4_deaths", pd.Series(0, index=ranked.index)) +
                                ranked.get("t5_deaths", pd.Series(0, index=ranked.index)) * 2).fillna(0).astype(int)
    return ranked, first_date, last_date

def compute_kvk_accumulated(storage, imports, group_power, start_d, end_d):
    r, _, _ = compute_accumulated_sum(storage, imports, group_power, start_d, end_d)
    return r

def prepare_imports(imports):
    out = imports.copy()
    out["report_date"] = pd.to_datetime(out["report_date"]).dt.date.astype(str)
    out["imported_at"] = out["imported_at"].astype(str)
    out["label"]       = out["report_date"] + " — " + out["filename"].astype(str)
    return out

@st.cache_data(ttl=300)
def _cached_gp(label, first_id):
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"], errors="coerce").fillna(0).sum())

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


def main():
    st.html(_css())
    storage = get_storage()

    st.markdown("""
    <div class="rok-header">
      <div class="rok-header-emblem">⚔️</div>
      <div>
        <div class="rok-header-title">K1602 · KP Dashboard</div>
        <div class="rok-header-sub">Kill Points Operations Center · Rise of Kingdoms</div>
      </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div class="tier-pills">
      <span class="tier-pill tp-t5">T5 ×20</span>
      <span class="tier-pill tp-t4">T4 ×10</span>
      <span class="tier-pill tp-t3">T3 ×4</span>
      <span class="tier-pill tp-t2">T2 ×2</span>
      <span class="tier-pill tp-t1">T1 ×0.2</span>
      <span class="tier-pill tp-eq">1 T5 death = 2 T4</span>
    </div>""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown('<div class="sb-sec">System</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:.68rem;color:#8398b5;margin-bottom:12px">Storage: <span style="color:#4a7cba;font-weight:bold;">{storage.label}</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sec">Reports</div>', unsafe_allow_html=True)
        _upload_section(storage)

    imports = storage.list_imports()
    if imports.empty:
        st.markdown('<div class="empty-state"><div class="empty-state-icon">⚔️</div><div class="empty-state-title">No reports imported yet</div><div class="empty-state-sub">Upload a statsExport file in the sidebar.</div></div>', unsafe_allow_html=True)
        return

    imports = prepare_imports(imports)

    with st.sidebar:
        st.markdown('<div class="sb-sec">Settings</div>', unsafe_allow_html=True)
        min_power    = st.number_input("Power Min (M)",  min_value=0, value=0, step=1,    format="%d")
        min_kp       = st.number_input("KP Min",         min_value=0, value=0, step=1000, format="%d")
        min_kp_pct   = st.slider("% KP Min",     0, 100, 0, 5)
        min_dead_pct = st.slider("% Deaths Min", 0, 100, 0, 5)
        if st.button("🔄 Reset Filters", use_container_width=True, type="secondary"):
            st.rerun()
        st.markdown('<div class="sb-sec">Admin</div>', unsafe_allow_html=True)
        admin_enabled, is_admin = admin_panel()

    gp = default_group_power(storage, imports)

    all_dates = sorted(imports["report_date"].unique())
    min_d = pd.to_datetime(all_dates[0]).date()
    max_d = pd.to_datetime(all_dates[-1]).date()

    st.markdown('<div class="sec-label" style="margin-top:0">Analysis Period</div>', unsafe_allow_html=True)
    d1, d2, d3, d4, d5 = st.columns([1.5, 1.5, 1, 1, 3])
    with d1: date_from = st.date_input("Start", value=min_d, min_value=min_d, max_value=max_d, key="main_date_from")
    with d2: date_to   = st.date_input("End",   value=max_d, min_value=min_d, max_value=max_d, key="main_date_to")
    with d3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("This Month", key="btn_month", use_container_width=True):
            t = date.today()
            st.session_state.main_date_from = t.replace(day=1)
            st.session_state.main_date_to   = t
            st.rerun()
    with d4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("All Time", key="btn_all", use_container_width=True):
            st.session_state.main_date_from = min_d
            st.session_state.main_date_to   = max_d
            st.rerun()
    with d5:
        n_range = len(imports[(pd.to_datetime(imports["report_date"]).dt.date >= date_from) &
                               (pd.to_datetime(imports["report_date"]).dt.date <= date_to)])
        st.markdown(f'<div style="padding-top:8px;font-size:.72rem;color:#9ab0cc"><span style="color:#d4a847;font-weight:600">{n_range}</span> reports · sum of all kills/deaths</div>', unsafe_allow_html=True)

    if date_from > date_to:
        st.error("Start date must be before end date."); return

    ranked, first_date, last_date = compute_accumulated_sum(storage, imports, gp, date_from, date_to)
    if ranked.empty:
        st.warning("No reports found in the selected date range."); return

    fc = pd.Series(True, index=ranked.index)
    if min_power > 0:    fc &= pd.to_numeric(ranked["power"],      errors="coerce").fillna(0) >= min_power * 1_000_000
    if min_kp > 0:       fc &= pd.to_numeric(ranked["kill_points"],errors="coerce").fillna(0) >= min_kp
    if min_kp_pct > 0:   fc &= (pd.to_numeric(ranked["kp_pct"],    errors="coerce").fillna(0) * 100) >= min_kp_pct
    if min_dead_pct > 0: fc &= (pd.to_numeric(ranked["dead_pct"],  errors="coerce").fillna(0) * 100) >= min_dead_pct
    ranked = ranked[fc]
    if ranked.empty:
        st.warning("No governors match the selected filters."); return

    af = []
    if min_power > 0:    af.append(f"Power ≥ {min_power}M")
    if min_kp > 0:       af.append(f"KP ≥ {fmt_k(min_kp)}")
    if min_kp_pct > 0:   af.append(f"KP ≥ {min_kp_pct}%")
    if min_dead_pct > 0: af.append(f"Deaths ≥ {min_dead_pct}%")
    if af:
        tags = " ".join(f'<span class="filter-tag">{f}</span>' for f in af)
        st.markdown(f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px"><span style="font-size:.62rem;color:#9ab0cc;font-weight:600">Filters:</span>{tags}</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">From <span class="rok-caption-val">{first_date}</span></div>
      <div class="rok-caption-sep">→</div>
      <div class="rok-caption-item"><span class="rok-caption-val">{last_date}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Members <span class="rok-caption-val">{len(ranked):,}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Reports <span class="rok-caption-val">{n_range}</span></div>
    </div>""", unsafe_allow_html=True)

    tab_labels = ["⚔ Ranking", "🏰 KvK", "🏆 Hall of Fame", "👑 Kingdom", "👤 Profile", "❓ Help"]
    if admin_enabled and is_admin:
        tab_labels += ["📈 History", "📁 Imports"]

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


def _upload_section(storage):
    upload_pwd = get_secret("UPLOAD_PASSWORD")
    admin_pwd  = get_secret("ADMIN_PASSWORD")

    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.markdown('<div class="upload-lock"><div class="upload-lock-icon">🔒</div><div class="upload-lock-text">Upload restrito à liderança</div></div>', unsafe_allow_html=True)
        up_pwd = st.text_input("Senha", type="password", key="up_pwd",
                                label_visibility="collapsed", placeholder="Senha de acesso...")
        if st.button("Desbloquear", use_container_width=True):
            ok = (admin_pwd and is_admin_authenticated(admin_pwd, up_pwd)) or \
                 (upload_pwd and up_pwd == upload_pwd)
            if ok: st.session_state.upload_auth = True; st.rerun()
            else:  st.error("Senha incorreta")
        return

    st.success("✓ Acesso liberado")
    if st.button("🔒 Bloquear", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False; st.rerun()

    campaigns = storage.list_kvk_events()
    today = date.today()

    if not campaigns.empty:
        active = campaigns[
            (pd.to_datetime(campaigns["start_date"]).dt.date <= today) &
            (pd.to_datetime(campaigns["end_date"]).dt.date >= today)
        ]
        if not active.empty:
            st.markdown("#### 🏰 Upload por Reino")
            active["label"] = active["name"] + " (" + active["start_date"] + " → " + active["end_date"] + ")"
            kvk_label = st.selectbox("Campanha", active["label"].tolist(), key="upload_kvk")
            kvk_row   = active.loc[active["label"] == kvk_label].iloc[0]
            kvk_id    = kvk_row["id"]

            camps_df = storage.load_kvk_camps(kvk_id)
            if not camps_df.empty:
                camp_names   = camps_df["camp_name"].tolist()
                camp_display = [f"{CAMP_ICONS.get(c,'🏕️')} {c}" for c in camp_names]
                sel_display  = st.selectbox("Acampamento", camp_display, key="upload_camp")
                sel_camp     = camp_names[camp_display.index(sel_display)]
                camp_id      = camps_df[camps_df["camp_name"] == sel_camp].iloc[0]["id"]

                kingdoms_df = storage.load_kingdom_stats(camp_id)
                st.markdown("**Reino:**")
                if not kingdoms_df.empty:
                    existing = kingdoms_df["kingdom_name"].tolist()
                    mode = st.radio("", ["Existente", "Novo"], key="k_mode", horizontal=True)
                    if mode == "Existente":
                        kingdom_name = st.selectbox("Reino", existing, key="sel_kingdom")
                    else:
                        nk = st.text_input("Número", placeholder="1501", key="new_kingdom", max_chars=4)
                        kingdom_name = nk.strip() if nk and nk.strip().isdigit() and len(nk.strip()) >= 3 else None
                        if nk and not kingdom_name: st.warning("Digite apenas números (ex: 1501)")
                        if kingdom_name and kingdom_name in existing:
                            st.warning(f"Reino {kingdom_name} já existe."); kingdom_name = None
                else:
                    nk = st.text_input("Número", placeholder="1501", key="new_kingdom_first", max_chars=4)
                    kingdom_name = nk.strip() if nk and nk.strip().isdigit() and len(nk.strip()) >= 3 else None
                    if nk and not kingdom_name: st.warning("Digite apenas números (ex: 1501)")

                uploaded = st.file_uploader("statsExport (.xlsx)", type=["xlsx","xls"], key="kvk_uploader")
                if uploaded:
                    safe_name   = re.sub(r"[^\w.\-]","_", uploaded.name)
                    report_date = st.date_input("Data", value=extract_report_date_from_name(safe_name) or today, key="kvk_up_date")
                    if st.button("💾 Salvar para KvK", type="primary", use_container_width=True):
                        if not kingdom_name:
                            st.error("Selecione ou crie um reino válido."); return
                        with st.spinner("Processando..."):
                            try:
                                fb    = uploaded.getvalue()
                                stats = load_stats_file(BytesIO(fb), filename=safe_name)
                                import_id, created = storage.save_import(
                                    filename=safe_name, report_date=report_date.isoformat(),
                                    file_hash=file_sha256(fb), stats=stats,
                                )
                                if created:
                                    existing_k = storage.load_kingdom_stats(camp_id)
                                    if existing_k.empty or kingdom_name not in existing_k["kingdom_name"].astype(str).values:
                                        storage.add_empty_kingdom(camp_id, kingdom_name)

                                    existing_k2 = storage.load_kingdom_stats(camp_id)
                                    realm_row   = existing_k2[existing_k2["kingdom_name"].astype(str) == kingdom_name]
                                    realm_id    = realm_row.iloc[0]["id"] if not realm_row.empty else None

                                    if realm_id:
                                        metrics      = calculate_metrics(stats, group_power=1)
                                        total_kp     = int(metrics["kill_points"].sum()) if "kill_points" in metrics else 0
                                        if "dead_equiv" not in metrics.columns:
                                            metrics["dead_equiv"] = (metrics.get("t4_deaths",0) + metrics.get("t5_deaths",0)*2).fillna(0)
                                        total_deaths = int(metrics["dead_equiv"].sum())
                                        player_count = len(stats)
                                        storage.add_upload_to_realm(
                                            realm_id=realm_id, import_id=import_id,
                                            filename=safe_name, report_date=report_date.isoformat(),
                                            total_kp=total_kp, total_deaths=total_deaths, player_count=player_count,
                                        )
                                    st.success(f"✅ Reino K{kingdom_name} importado!"); st.rerun()
                                else:
                                    st.warning("Arquivo já importado.")
                            except Exception as e:
                                st.error(f"Erro: {e}")
                return

    st.markdown("---")
    st.markdown("#### 📤 Upload K1602")
    uploaded = st.file_uploader("statsExport (.xlsx)", type=["xlsx","xls"], key="k1602_uploader")
    if not uploaded: return
    safe_name   = re.sub(r"[^\w.\-]","_", uploaded.name)
    report_date = st.date_input("Data", value=extract_report_date_from_name(safe_name) or today, key="k1602_date")
    if not st.button("💾 Salvar K1602", type="primary", use_container_width=True): return
    with st.spinner("Processando..."):
        try:
            fb    = uploaded.getvalue()
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            _, created = storage.save_import(filename=safe_name, report_date=report_date.isoformat(),
                                              file_hash=file_sha256(fb), stats=stats)
        except Exception as e: st.error(f"Erro: {e}"); return
    if created: st.success(f"✓ {len(stats):,} membros salvos")
    else:        st.warning("Arquivo já importado.")
    st.rerun()


def show_ranking(ranked_full, key_prefix="main"):
    fc1, fc2, fc3 = st.columns([5, 2, 2])
    with fc1:
        search = st.text_input("search", placeholder="Search member or ID…",
                                key=f"{key_prefix}_rank_search", label_visibility="collapsed")
    with fc2:
        sf = st.selectbox("status", ["All","Approved","Pending","Below goal"],
                          key=f"{key_prefix}_rank_sf", label_visibility="collapsed")
    with fc3:
        sort_by = st.selectbox("sort", ["KP ↓","Deaths ↓","Power ↓","% KP ↓","% Deaths ↓","Name ↑"],
                               key=f"{key_prefix}_rank_sort", label_visibility="collapsed")

    df = ranked_full.copy()
    top5 = df["dead_equiv"].quantile(0.95) if "dead_equiv" in df.columns and len(df) > 0 else float("inf")
    df["emblems"] = ""
    for idx, row in df.iterrows():
        e = ""
        if row.get("dead_equiv",0) >= top5 and row.get("dead_equiv",0) > 0: e += "🛡️ "
        if row.get("kill_points",0) >= row.get("kp_goal",1)*2 and row.get("kp_goal",0) > 0: e += "🔥 "
        if row.get("power",0) >= 100_000_000: e += "🐋 "
        df.at[idx,"emblems"] = e

    if search.strip():
        n = search.strip().lower()
        df = df[df["username"].astype(str).str.lower().str.contains(n,regex=False,na=False) |
                df["character_id"].astype(str).str.lower().str.contains(n,regex=False,na=False)]

    sm = {"Approved":"Aprovado","Pending":"Pendente","Below goal":"Abaixo da meta"}
    if sf != "All": df = df[df["status"] == sm.get(sf,sf)]

    smap = {"KP ↓":("kill_points",False),"Deaths ↓":("dead_equiv",False),"Power ↓":("power",False),
            "% KP ↓":("kp_pct",False),"% Deaths ↓":("dead_pct",False),"Name ↑":("username",True)}
    scol, sasc = smap.get(sort_by,("kill_points",False))
    if scol in df.columns: df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    st.markdown(f'<div class="sec-label">Governors · {len(df):,} of {len(ranked_full):,}</div>', unsafe_allow_html=True)

    ps = st.selectbox("Per page",[10,25,50,100],index=1,key=f"{key_prefix}_rank_ps",label_visibility="collapsed")
    tp = max(1,-(-len(df)//ps))
    pc1, pc2 = st.columns([1,5])
    with pc1: pg = st.number_input("Page",min_value=1,max_value=tp,value=1,key=f"{key_prefix}_rank_pg",label_visibility="collapsed")
    with pc2: st.markdown(f'<div style="font-size:.65rem;color:#9ab0cc;padding-top:8px">Page {pg} of {tp}</div>', unsafe_allow_html=True)

    start = (pg-1)*ps
    _render_members(df.iloc[start:start+ps], key_prefix=key_prefix)

    with st.expander("Export →"):
        cols_show = {"rank":"#","username":"Governor","character_id":"ID","power":"Power","power_band":"Band",
                     "kill_points":"KP","kp_goal":"KP Goal","t5_kills":"T5K","t4_kills":"T4K","t3_kills":"T3K",
                     "t2_kills":"T2K","t1_kills":"T1K","t5_deaths":"T5D","t4_deaths":"T4D","t3_deaths":"T3D",
                     "t2_deaths":"T2D","t1_deaths":"T1D","dead_t4_goal":"Death Goal","dead_equiv":"T4 Equiv.","status":"Status"}
        avail = {k:v for k,v in cols_show.items() if k in df.columns}
        st.dataframe(df[list(avail.keys())].rename(columns=avail), use_container_width=True, hide_index=True)
        st.download_button("⬇ CSV", data=df.to_csv(index=False).encode(),
                            file_name="ranking.csv", mime="text/csv", key=f"{key_prefix}_csv")


def _render_member_chart(storage, imports, username, character_id):
    if go is None: return
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    rows = []
    for _, ir in ordered.iterrows():
        try:
            stats = storage.load_stats(ir["id"])
            ps = stats[(stats["username"]==username)|(stats["character_id"].astype(str)==str(character_id))]
            if ps.empty: continue
            m = calculate_metrics(ps, group_power=100_000_000)
            r = apply_goals(add_rank(m,"kill_points"))
            r["report_date"] = ir["report_date"]
            if "dead_equiv" not in r.columns: r["dead_equiv"] = 0
            rows.append(r)
        except: continue
    if len(rows) < 2: return
    pd_data = pd.concat(rows,ignore_index=True).sort_values("report_date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd_data["report_date"],y=pd_data["kill_points"],mode="lines+markers",
        name="KP",line=dict(color="#d4a847",width=2,shape="spline"),marker=dict(size=5)))
    fig.add_trace(go.Scatter(x=pd_data["report_date"],y=pd_data["dead_equiv"],mode="lines+markers",
        name="Deaths T4eq",line=dict(color="#4a7cba",width=2,shape="spline"),marker=dict(size=5)))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9ab0cc",family="Inter",size=11),height=200,
        yaxis=dict(gridcolor="rgba(42,63,94,0.5)",zeroline=False),
        xaxis=dict(gridcolor="rgba(42,63,94,0.5)",zeroline=False),
        legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1,bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0,r=0,t=30,b=0))
    st.plotly_chart(fig, use_container_width=True)


def _render_members(df, key_prefix="main"):
    storage = get_storage()
    imports = prepare_imports(storage.list_imports())
    for _, row in df.iterrows():
        cls    = STATUS_CLS.get(row["status"],"er")
        kp_w   = min(float(row.get("kp_pct",0))*100,100)
        dead_w = min(float(row.get("dead_pct",0))*100,100)
        kp_gap   = int(row.get("kp_gap",0))
        dead_gap = int(row.get("dead_gap_t4",0))
        kp_fc    = "full" if kp_w>=100 else "kp"
        dead_fc  = "full" if dead_w>=100 else "dead"
        badge    = f'<span class="sbadge sbadge-{cls}">{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</span>'

        with st.expander(f"#{int(row['rank'])}  {row['username']}", expanded=False):
            st.markdown(f"""
            <div class="mrow {cls}" style="margin-bottom:10px">
              <div class="mrow-sum" style="cursor:default">
                <div class="mrow-rank">#{int(row['rank'])}</div>
                <div>
                  <div class="mrow-name">{row['username']} {row.get('emblems','')}</div>
                  <div class="mrow-meta">{fmt_m(int(row['power']))}M power · {row.get('power_band','—')} · ID {row.get('character_id','—')}</div>
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
            </div>""", unsafe_allow_html=True)

            _render_member_chart(storage, imports, row["username"], row.get("character_id",""))

            t5d=int(row.get("t5_deaths",0)); t4d=int(row.get("t4_deaths",0))
            t3d=int(row.get("t3_deaths",0)); t2d=int(row.get("t2_deaths",0)); t1d=int(row.get("t1_deaths",0))
            dead_equiv=int(row.get("dead_equiv",0))
            kp_gh   = '<div class="mdet-gap ok">✓ KP goal reached</div>' if kp_gap==0 else f'<div class="mdet-gap warn">⚠ {fmt_k(kp_gap)} KP missing</div>'
            dead_gh = '<div class="mdet-gap ok">✓ Death goal reached</div>' if dead_gap==0 else f'<div class="mdet-gap warn">⚠ {fmt_k(dead_gap)} T4eq missing</div>'

            st.markdown(f"""
            <div class="mdet">
              <div class="mdet-grid">
                <div>
                  <div class="mdet-block-label">Kill Points</div>
                  <div class="mdet-block-val">{fmt_int(int(row['kill_points']))}</div>
                  <div class="mdet-block-sub">Goal: {fmt_int(int(row['kp_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head"><span>{kp_w:.1f}%</span><span>{fmt_int(int(row['kill_points']))} / {fmt_int(int(row['kp_goal']))}</span></div>
                    <div class="mdet-prog-track"><div class="mdet-prog-fill kp" style="width:{kp_w:.1f}%"></div></div>
                  </div>{kp_gh}
                </div>
                <div>
                  <div class="mdet-block-label">Deaths (T4 equiv.)</div>
                  <div class="mdet-block-val">{fmt_int(dead_equiv)}</div>
                  <div class="mdet-block-sub">Goal: {fmt_int(int(row['dead_t4_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head"><span>{dead_w:.1f}%</span><span>{fmt_int(dead_equiv)} / {fmt_int(int(row['dead_t4_goal']))}</span></div>
                    <div class="mdet-prog-track"><div class="mdet-prog-fill dead" style="width:{dead_w:.1f}%"></div></div>
                  </div>{dead_gh}
                </div>
              </div>""", unsafe_allow_html=True)

            dc1, dc2 = st.columns(2)
            with dc1:
                t5k=int(row.get("t5_kills",0)); t4k=int(row.get("t4_kills",0))
                t3k=int(row.get("t3_kills",0)); t2k=int(row.get("t2_kills",0)); t1k=int(row.get("t1_kills",0))
                st.markdown(f"""
                <div class="mdet-block-label" style="margin-top:0">Kills by Tier</div>
                <table class="tier-table">
                  <tr><th>Tier</th><th>Kills</th><th>KP</th></tr>
                  <tr><td>T5</td><td class="amber">{fmt_k(t5k)}</td><td class="amber">{fmt_k(t5k*20)}</td></tr>
                  <tr><td>T4</td><td class="amber">{fmt_k(t4k)}</td><td class="amber">{fmt_k(t4k*10)}</td></tr>
                  <tr><td>T3</td><td>{fmt_k(t3k)}</td><td>{fmt_k(t3k*4)}</td></tr>
                  <tr><td>T2</td><td>{fmt_k(t2k)}</td><td>{fmt_k(t2k*2)}</td></tr>
                  <tr><td>T1</td><td>{fmt_k(t1k)}</td><td>{fmt_k(int(t1k*.2))}</td></tr>
                </table>""", unsafe_allow_html=True)
            with dc2:
                st.markdown(f"""
                <div class="mdet-block-label" style="margin-top:0">Deaths by Tier</div>
                <table class="tier-table">
                  <tr><th>Tier</th><th>Deaths</th><th>T4 eq.</th></tr>
                  <tr><td>T5</td><td class="blue">{fmt_k(t5d)}</td><td class="equiv">≡ {fmt_k(t5d*2)}</td></tr>
                  <tr><td>T4</td><td class="blue">{fmt_k(t4d)}</td><td class="equiv">≡ {fmt_k(t4d)}</td></tr>
                  <tr><td>T3</td><td>{fmt_k(t3d)}</td><td class="equiv">—</td></tr>
                  <tr><td>T2</td><td>{fmt_k(t2d)}</td><td class="equiv">—</td></tr>
                  <tr><td>T1</td><td>{fmt_k(t1d)}</td><td class="equiv">—</td></tr>
                </table>
                <div style="font-size:.62rem;color:#9ab0cc;margin-top:8px">Equiv: <span style="color:#4a7cba;font-family:monospace">{fmt_int(dead_equiv)}</span> / Goal: <span style="color:#5a7294;font-family:monospace">{fmt_int(int(row['dead_t4_goal']))}</span></div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)


def show_kvk(storage, imports, group_power, *, is_admin, admin_enabled):
    st.markdown('''
    <div class="rok-header" style="border-left-color:#4a7cba">
      <div class="rok-header-emblem" style="background:#162233;border-color:#4a7cba">🏰</div>
      <div>
        <div class="rok-header-title">Guerra dos Reinos (KvK)</div>
        <div class="rok-header-sub">Campanhas · Acampamentos · Reinos Inimigos</div>
      </div>
    </div>''', unsafe_allow_html=True)

    if admin_enabled and is_admin:
        with st.expander("➕ Criar Nova Campanha", expanded=False):
            c1, c2 = st.columns([3,2])
            with c1:
                kvk_name   = st.text_input("Nome", placeholder="ex: KvK #5 - Heroic Anthem", key="kvk_new_name")
                story_type = st.selectbox("Tipo", list(KVK_STORIES.keys()), key="kvk_story")
            with c2:
                kvk_start = st.date_input("Início", key="kvk_start")
                kvk_end   = st.date_input("Fim",    key="kvk_end")
            if st.button("🚀 Criar Campanha", type="primary", key="kvk_create"):
                if not kvk_name.strip(): st.error("Digite um nome.")
                elif kvk_end < kvk_start: st.error("Fim deve ser após início.")
                else:
                    storage.save_kvk_structure(name=kvk_name.strip(), story_type=story_type,
                                                start_date=kvk_start.isoformat(), end_date=kvk_end.isoformat(), camps=[])
                    st.success(f"✅ '{kvk_name}' criada!"); st.rerun()

    campaigns = storage.list_kvk_events()
    if campaigns.empty:
        st.markdown('<div class="empty-state"><div class="empty-state-icon">🏰</div><div class="empty-state-title">Nenhuma campanha</div><div class="empty-state-sub">Crie uma campanha KvK acima.</div></div>', unsafe_allow_html=True)
        return

    campaigns = campaigns.copy()
    campaigns["start_date"] = pd.to_datetime(campaigns["start_date"]).dt.date.astype(str)
    campaigns["end_date"]   = pd.to_datetime(campaigns["end_date"]).dt.date.astype(str)
    campaigns["label"]      = campaigns["name"] + " (" + campaigns["start_date"] + " → " + campaigns["end_date"] + ")"

    chosen    = st.selectbox("Campanha", campaigns["label"].tolist(), key="kvk_sel", label_visibility="collapsed")
    camp_row  = campaigns.loc[campaigns["label"]==chosen].iloc[0]
    kvk_id    = camp_row["id"]

    today = date.today()
    sd    = pd.to_datetime(camp_row["start_date"]).date()
    ed    = pd.to_datetime(camp_row["end_date"]).date()
    slbl  = "🟢 Ativa" if sd<=today<=ed else ("🔵 Futura" if sd>today else "⚫ Encerrada")

    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 18px;
                background:#162233;border:1px solid #2a3f5e;border-left:3px solid #4a7cba;
                border-radius:8px;margin-bottom:16px">
      <div>
        <div style="font-size:1rem;font-weight:800;color:#f0f4fa">{camp_row['name']}</div>
        <div style="font-size:.72rem;color:#9ab0cc;margin-top:3px">{camp_row['start_date']} → {camp_row['end_date']}</div>
      </div>
      <div style="font-size:.75rem;color:#9ab0cc">{slbl}</div>
    </div>""", unsafe_allow_html=True)

    if admin_enabled and is_admin:
        with st.expander("🗑 Excluir campanha", expanded=False):
            st.warning("Irreversível.")
            if st.button("Confirmar exclusão", type="secondary", key="kvk_del"):
                if storage.delete_kvk_event(kvk_id):
                    st.success("Excluída."); st.rerun()

    camps_df = storage.load_kvk_camps(kvk_id)
    if camps_df.empty:
        st.warning("Nenhum acampamento."); return

    all_k = []
    for _, cr in camps_df.iterrows():
        kdf = storage.load_kingdom_stats(cr["id"])
        if not kdf.empty: all_k.append(kdf)
    if all_k:
        combined = pd.concat(all_k, ignore_index=True)
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("⚔️ KP Total",    fmt_k(int(combined["total_kp"].sum())))
        with c2: st.metric("💀 Mortes",       fmt_k(int(combined["total_deaths"].sum())))
        with c3: st.metric("👑 Reinos",       len(combined))
        with c4: st.metric("📂 Uploads",      int(combined["upload_count"].sum()) if "upload_count" in combined.columns else "—")

    st.markdown("---")
    camp_tabs = st.tabs([f"{CAMP_ICONS.get(r['camp_name'],'🏕️')} {r['camp_name']}" for _, r in camps_df.iterrows()])
    for tidx, (_, cr) in enumerate(camps_df.iterrows()):
        with camp_tabs[tidx]:
            _render_camp_tab(storage, cr["id"], cr["camp_name"], is_admin, admin_enabled)


def _render_camp_tab(storage, camp_id, camp_name, is_admin, admin_enabled):
    kingdoms_df = storage.load_kingdom_stats(camp_id)

    if kingdoms_df.empty:
        st.markdown('<div class="empty-state" style="padding:30px"><div class="empty-state-icon">🏕️</div><div class="empty-state-title">Nenhum reino</div><div class="empty-state-sub">Adicione um reino abaixo.</div></div>', unsafe_allow_html=True)
    else:
        camp_kp     = int(kingdoms_df["total_kp"].sum())
        camp_deaths = int(kingdoms_df["total_deaths"].sum())
        n_k         = len(kingdoms_df)
        c1,c2,c3,c4,c5,c6 = st.columns(6)
        with c1: st.metric("⚔️ KP",         fmt_k(camp_kp))
        with c2: st.metric("💀 Mortes",      fmt_k(camp_deaths))
        with c3: st.metric("👑 Reinos",      n_k)
        with c4: st.metric("📂 Uploads",     int(kingdoms_df["upload_count"].sum()) if "upload_count" in kingdoms_df else "—")
        with c5: st.metric("📊 Média KP",    fmt_k(camp_kp//n_k) if n_k else "—")
        with c6: st.metric("📊 Média Mortes",fmt_k(camp_deaths//n_k) if n_k else "—")

        st.markdown("#### 🏆 Ranking dos Reinos")
        ranking = kingdoms_df.sort_values("total_kp", ascending=False).reset_index(drop=True)
        medals  = {0:"🥇",1:"🥈",2:"🥉"}
        for i, (_, rrow) in enumerate(ranking.iterrows()):
            with st.expander(f"{medals.get(i, f'#{i+1}')} Reino K{rrow['kingdom_name']} — {fmt_k(int(rrow['total_kp']))} KP", expanded=False):
                _render_realm_detail(storage, rrow, camp_id, is_admin, admin_enabled)

        if px is not None and len(ranking) > 1:
            fig = px.bar(ranking, x="kingdom_name", y="total_kp",
                         color="total_kp", color_continuous_scale="Viridis",
                         labels={"kingdom_name":"Reino","total_kp":"KP Total"})
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                               font=dict(color="#9ab0cc",family="Inter"),showlegend=False,height=280)
            st.plotly_chart(fig, use_container_width=True)

    if admin_enabled and is_admin:
        st.markdown("---")
        st.markdown("#### ➕ Adicionar Reino")
        ca, cb = st.columns([2,1])
        with ca: new_k = st.text_input("Número", placeholder="1501", key=f"newk_{camp_id}")
        with cb:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Adicionar", key=f"addk_{camp_id}"):
                kclean = re.sub(r"^[Kk]","", new_k.strip())
                if kclean.isdigit() and len(kclean) >= 3:
                    existing = storage.load_kingdom_stats(camp_id)
                    if not existing.empty and kclean in existing["kingdom_name"].astype(str).values:
                        st.error(f"Reino {kclean} já cadastrado!")
                    else:
                        storage.add_empty_kingdom(camp_id, kclean)
                        st.success(f"✅ K{kclean} adicionado!"); st.rerun()
                else:
                    st.error("Mínimo 3 dígitos (ex: 1501)")


def _render_realm_detail(storage, krow, camp_id, is_admin, admin_enabled):
    realm_id    = str(krow["id"])
    kname       = str(krow["kingdom_name"])
    uploads_df  = storage.get_uploads_by_realm(realm_id)

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("KP",          fmt_k(int(krow.get("total_kp",0))))
    with c2: st.metric("Mortes T4eq", fmt_k(int(krow.get("total_deaths",0))))
    with c3: st.metric("Uploads",     len(uploads_df))

    if not uploads_df.empty:
        st.markdown("**Relatórios importados:**")
        for _, urow in uploads_df.iterrows():
            uid   = str(urow.get("id",""))
            fname = str(urow.get("filename",""))
            rdate = str(urow.get("report_date",""))
            ukp   = int(urow.get("total_kp",0))
            udead = int(urow.get("total_deaths",0))
            uplc  = int(urow.get("player_count",0))
            rc1,rc2,rc3,rc4,rc5 = st.columns([3,1.5,2,2,0.7])
            with rc1: st.markdown(f'<div style="font-size:.75rem;color:#f0f4fa;padding-top:6px">{fname[:35]}</div>', unsafe_allow_html=True)
            with rc2: st.markdown(f'<div style="font-size:.7rem;color:#9ab0cc;padding-top:6px">{rdate}</div>', unsafe_allow_html=True)
            with rc3: st.markdown(f'<div style="font-size:.7rem;color:#d4a847;font-family:monospace;padding-top:6px">{fmt_k(ukp)} KP · {uplc} jogadores</div>', unsafe_allow_html=True)
            with rc4: st.markdown(f'<div style="font-size:.7rem;color:#4a7cba;font-family:monospace;padding-top:6px">{fmt_k(udead)} mortes</div>', unsafe_allow_html=True)
            with rc5:
                if admin_enabled and is_admin:
                    if st.button("🗑", key=f"del_up_{uid}", help="Remover upload"):
                        storage.delete_upload(uid); st.rerun()

        with st.expander(f"📊 Ver ranking K{kname}"):
            try:
                all_rows = []
                for _, urow in uploads_df.iterrows():
                    imp_id = str(urow.get("import_id",""))
                    if not imp_id: continue
                    s = storage.load_stats(imp_id)
                    if not s.empty: all_rows.append(s)
                if all_rows:
                    combined = pd.concat(all_rows, ignore_index=True)
                    agg = combined.groupby("character_id").agg({
                        "username":"last","power":"last",
                        "t5_kills":"sum","t4_kills":"sum","t3_kills":"sum","t2_kills":"sum","t1_kills":"sum",
                        "t5_deaths":"sum","t4_deaths":"sum","t3_deaths":"sum","t2_deaths":"sum","t1_deaths":"sum",
                        "resources_gathered":"sum",
                    }).reset_index()
                    m = calculate_metrics(agg, group_power=1)
                    if "dead_equiv" not in m.columns:
                        m["dead_equiv"] = (m.get("t4_deaths",0)+m.get("t5_deaths",0)*2).fillna(0).astype(int)
                    m = m.sort_values("kill_points",ascending=False).reset_index(drop=True)
                    m["#"] = range(1,len(m)+1)
                    sc = {"#":"#","username":"Jogador","power":"Power","kill_points":"KP","dead_equiv":"Deaths T4eq","t5_kills":"T5K","t4_kills":"T4K"}
                    av = {k:v for k,v in sc.items() if k in m.columns}
                    st.dataframe(m[list(av.keys())].rename(columns=av), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Erro: {e}")

    if admin_enabled and is_admin:
        st.markdown("---")
        st.markdown("**Upload novo relatório:**")
        up_file = st.file_uploader(f"statsExport K{kname}", type=["xlsx","xls"], key=f"up_{realm_id}")
        if up_file:
            up_date = st.date_input("Data", value=date.today(), key=f"upd_{realm_id}")
            if st.button(f"💾 Salvar K{kname}", type="primary", key=f"sav_{realm_id}", use_container_width=True):
                with st.spinner(f"Processando K{kname}..."):
                    try:
                        fb        = up_file.getvalue()
                        safe_name = re.sub(r"[^\w.\-]","_", up_file.name)
                        stats     = load_stats_file(BytesIO(fb), filename=safe_name)
                        import_id, _ = storage.save_import(filename=safe_name, report_date=up_date.isoformat(),
                                                            file_hash=file_sha256(fb), stats=stats)
                        metrics      = calculate_metrics(stats, group_power=1)
                        total_kp     = int(metrics["kill_points"].sum()) if "kill_points" in metrics else 0
                        if "dead_equiv" not in metrics.columns:
                            metrics["dead_equiv"] = (metrics.get("t4_deaths",0)+metrics.get("t5_deaths",0)*2).fillna(0)
                        total_deaths = int(metrics["dead_equiv"].sum())
                        storage.add_upload_to_realm(realm_id=realm_id, import_id=import_id,
                                                     filename=safe_name, report_date=up_date.isoformat(),
                                                     total_kp=total_kp, total_deaths=total_deaths, player_count=len(stats))
                        st.success(f"✅ {len(stats):,} jogadores de K{kname} importados!"); st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
        st.markdown("---")
        if st.button(f"🗑 Remover Reino K{kname}", type="secondary", key=f"del_realm_{realm_id}"):
            storage.delete_kingdom_from_camp(camp_id, kname); st.rerun()


def show_hof(storage, imports, group_power, *, is_admin, admin_enabled):
    st.markdown('''
    <div class="rok-header" style="border-left-color:#d4a847">
      <div class="rok-header-emblem" style="background:#162233;border-color:#d4a847">🏆</div>
      <div>
        <div class="rok-header-title">Hall of Fame — K1602</div>
        <div class="rok-header-sub">Top 10 KP · Top 10 Deaths · Por Campanha KvK</div>
      </div>
    </div>''', unsafe_allow_html=True)

    events = storage.list_kvk_events()
    if events.empty:
        st.markdown('<div class="empty-state"><div class="empty-state-icon">🏆</div><div class="empty-state-title">Nenhuma campanha</div><div class="empty-state-sub">Crie uma campanha KvK primeiro.</div></div>', unsafe_allow_html=True)
        return

    events = events.copy()
    events["start_date"] = pd.to_datetime(events["start_date"]).dt.date.astype(str)
    events["end_date"]   = pd.to_datetime(events["end_date"]).dt.date.astype(str)
    events["label"]      = events["name"] + " (" + events["start_date"] + " → " + events["end_date"] + ")"

    cs, ci = st.columns([3,3])
    with cs: chosen = st.selectbox("Campanha", events["label"].tolist(), key="hof_kvk", label_visibility="collapsed")
    with ci: st.markdown(f'<div style="font-size:.68rem;color:#9ab0cc;padding-top:8px"><span style="color:#d4a847;font-weight:700">{len(events)}</span> campanha(s)</div>', unsafe_allow_html=True)

    ev   = events.loc[events["label"]==chosen].iloc[0]
    sd   = pd.to_datetime(ev["start_date"]).date()
    ed   = pd.to_datetime(ev["end_date"]).date()

    imp_cp = imports.copy()
    imp_cp["_d"] = pd.to_datetime(imp_cp["report_date"]).dt.date
    in_win = imp_cp[(imp_cp["_d"]>=sd)&(imp_cp["_d"]<=ed)]

    if in_win.empty:
        st.info(f"⏳ Nenhum relatório K1602 no período ({ev['start_date']} → {ev['end_date']})."); return

    ranked = compute_kvk_accumulated(storage, imports, group_power, sd, ed)
    if ranked.empty:
        st.info("Sem dados para este KvK."); return
    if "dead_equiv" not in ranked.columns:
        ranked["dead_equiv"] = (ranked.get("t4_deaths",0)+ranked.get("t5_deaths",0)*2).fillna(0).astype(int)

    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">Campanha <span class="rok-caption-val">{ev['name']}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">{ev['start_date']} → {ev['end_date']}</div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Relatórios K1602 <span class="rok-caption-val">{len(in_win)}</span></div>
    </div>""", unsafe_allow_html=True)

    top10_kp   = ranked.sort_values("kill_points",ascending=False).head(10).reset_index(drop=True)
    top10_dead = ranked.sort_values("dead_equiv",  ascending=False).head(10).reset_index(drop=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:#d4a847;margin-bottom:10px">⚔ Top 10 Kill Points</div>', unsafe_allow_html=True)
        _render_hof_list(top10_kp,"kp")
    with c2:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:#4a7cba;margin-bottom:10px">💀 Top 10 Deaths</div>', unsafe_allow_html=True)
        _render_hof_list(top10_dead,"deaths")


def _render_hof_list(df, category):
    if df.empty: return
    medals  = {1:"🥇",2:"🥈",3:"🥉"}
    color   = "#d4a847" if category=="kp" else "#4a7cba"
    unit    = "KP" if category=="kp" else "T4eq"
    val_col = "kill_points" if category=="kp" else "dead_equiv"
    for pos,(_, row) in enumerate(df.iterrows(),start=1):
        medal  = medals.get(pos,f"#{pos}")
        is_top = pos<=3
        value  = int(row.get(val_col,0))
        power  = int(row.get("power",0))
        st.markdown(f'''
        <div style="display:flex;align-items:center;gap:10px;padding:{"12px 14px" if is_top else "9px 14px"};
             background:{"rgba(212,168,71,.08)" if is_top else "transparent"};
             border:1px solid {"rgba(212,168,71,.2)" if is_top else "rgba(42,63,94,.5)"};
             border-radius:6px;margin-bottom:5px">
          <div style="font-size:{"1.2rem" if is_top else ".85rem"};min-width:28px;text-align:center">{medal}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:{"0.88rem" if is_top else "0.82rem"};font-weight:{"700" if is_top else "500"};color:#f0f4fa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{row["username"]}</div>
            <div style="font-size:.62rem;color:#9ab0cc;margin-top:1px">{fmt_m(power)}M power</div>
          </div>
          <div style="font-family:JetBrains Mono,monospace;font-size:{"1rem" if is_top else ".85rem"};font-weight:600;color:{color};white-space:nowrap">{fmt_k(value)} {unit}</div>
        </div>''', unsafe_allow_html=True)


def show_kingdom(ranked, imports, storage, group_power):
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
      <div class="kd-card amber"><div class="kd-card-label">Total KP</div><div class="kd-card-value">{fmt_k(kp_total)}</div><div class="kd-card-sub">acumulado</div></div>
      <div class="kd-card blue"><div class="kd-card-label">Total Power</div><div class="kd-card-value">{fmt_m(power_total)}M</div><div class="kd-card-sub">combinado</div></div>
      <div class="kd-card green"><div class="kd-card-label">Governors</div><div class="kd-card-value">{total:,}</div><div class="kd-card-sub">{active} ativos</div></div>
      <div class="kd-card green"><div class="kd-card-label">Aprovação</div><div class="kd-card-value">{aprov_pct:.1f}%</div><div class="kd-card-sub">{approved}/{total}</div></div>
      <div class="kd-card red"><div class="kd-card-label">Abaixo Meta</div><div class="kd-card-value">{below}</div><div class="kd-card-sub">{pending} pendentes</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Goal status</div>', unsafe_allow_html=True)
    m1,m2,m3 = st.columns(3)
    for col,lbl,count,color in [(m1,"Approved",approved,"#3ba37a"),(m2,"Pending",pending,"#d4a03a"),(m3,"Below goal",below,"#c95a4e")]:
        pct = count/total*100 if total else 0
        with col:
            st.markdown(f"""
            <div style="background:#162233;border:1px solid #2a3f5e;border-radius:8px;padding:16px;text-align:center">
              <div style="font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#9ab0cc;margin-bottom:8px">{lbl}</div>
              <div style="font-size:1.8rem;font-weight:700;color:{color};font-family:JetBrains Mono,monospace">{count}<span style="font-size:.9rem;color:#5a7294">/{total}</span></div>
              <div style="height:4px;background:#0e1a2b;border-radius:99px;margin-top:8px"><div style="width:{pct:.1f}%;height:100%;background:{color};border-radius:99px"></div></div>
              <div style="font-size:.62rem;color:#5a7294;margin-top:4px">{pct:.1f}%</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Power bands</div>', unsafe_allow_html=True)
    bands=[]
    for pmin,pmax,dead_t4,_,kp in GOAL_TABLE:
        lbl = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax!=float("inf") else f"{pmin//1_000_000}M+"
        sub = ranked[ranked["power_band"]==lbl] if "power_band" in ranked else pd.DataFrame()
        if sub.empty: continue
        ok=int((sub["status"]=="Aprovado").sum()); wa=int((sub["status"]=="Pendente").sum()); er=int((sub["status"]=="Abaixo da meta").sum())
        bands.append({"Band":lbl,"Total":len(sub),"✅":ok,"🟡":wa,"❌":er,"Total KP":fmt_k(int(sub["kill_points"].sum())),"KP Goal":fmt_k(kp)})
    if bands:
        st.markdown('<table class="band-table"><tr><th>Band</th><th>Total</th><th>✅</th><th>🟡</th><th>❌</th><th>Total KP</th><th>KP Goal</th></tr>'+
                    "".join(f'<tr><td>{b["Band"]}</td><td>{b["Total"]}</td><td>{b["✅"]}</td><td>{b["🟡"]}</td><td>{b["❌"]}</td><td>{b["Total KP"]}</td><td>{b["KP Goal"]}</td></tr>' for b in bands)+
                    '</table>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Need attention & Mailing List</div>', unsafe_allow_html=True)
    ca, cm = st.columns([2,1])
    att = ranked[ranked["status"]!="Aprovado"].sort_values("kp_pct").head(8)
    with ca:
        if att.empty: st.success("All members are approved!")
        else:
            for _,row in att.iterrows():
                cls=STATUS_CLS.get(row["status"],"er")
                st.markdown(f"""
                <div class="att-row {cls}">
                  <div style="flex:1;font-size:.82rem;font-weight:600;color:#f0f4fa">{row['username']}</div>
                  <div style="font-size:.68rem;color:#9ab0cc">{fmt_m(int(row['power']))}M</div>
                  <div style="font-size:.65rem;color:#9ab0cc">KP {min(float(row.get('kp_pct',0))*100,100):.0f}% · D {min(float(row.get('dead_pct',0))*100,100):.0f}%</div>
                  <div class="sbadge sbadge-{cls}">{STATUS_ICON.get(row['status'],'○')} {STATUS_LABEL.get(row['status'],'—')}</div>
                </div>""", unsafe_allow_html=True)
    with cm:
        st.markdown('<div style="font-size:.75rem;color:#9ab0cc;margin-bottom:10px">IDs para Mail no jogo:</div>', unsafe_allow_html=True)
        abaixo = ranked[ranked["status"]!="Aprovado"]
        if not abaixo.empty: st.code(",".join(abaixo["character_id"].astype(str).tolist()), language="text")
        else: st.success("Sem mails necessários.")


def show_profile(storage, imports, gp):
    st.markdown('<div class="sec-label">Player Tracker</div>', unsafe_allow_html=True)
    if imports.empty: st.info("Importe mais relatórios."); return
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)

    @st.cache_data(ttl=300)
    def _names(slabel, ids):
        names=set(); s=get_storage()
        for i in ids:
            try: names.update(s.load_stats(i)["username"].dropna().tolist())
            except: pass
        return sorted(names)

    plist = _names(storage.label, tuple(ordered["id"].tolist()))
    if not plist: st.info("Sem jogadores."); return
    sel = st.selectbox("Governador:", plist, key="profile_player")
    if not sel: return

    rows=[]
    for _,ir in ordered.iterrows():
        try:
            stats=storage.load_stats(ir["id"]); ps=stats[stats["username"]==sel]
            if ps.empty: continue
            m=calculate_metrics(ps,group_power=gp); r=apply_goals(add_rank(m,"kill_points"))
            r["report_date"]=ir["report_date"]
            if "dead_equiv" not in r.columns: r["dead_equiv"]=(r.get("t4_deaths",0)+r.get("t5_deaths",0)*2).fillna(0).astype(int)
            rows.append(r)
        except: continue
    if not rows: st.warning(f"Sem dados para **{sel}**."); return

    pd_data=pd.concat(rows,ignore_index=True).sort_values("report_date")
    lat=pd_data.iloc[-1]
    c1,c2,c3,c4=st.columns(4)
    with c1: st.metric("Power",f"{fmt_m(int(lat['power']))}M")
    with c2: st.metric("KP",fmt_k(int(lat["kill_points"])))
    with c3: st.metric("Deaths T4eq",fmt_k(int(lat.get("dead_equiv",0))))
    with c4: st.metric("Status",STATUS_LABEL.get(lat["status"],lat["status"]))

    if go is not None:
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=pd_data["report_date"],y=pd_data["kill_points"],mode="lines+markers",name="KP",line=dict(color="#d4a847")))
        fig.add_trace(go.Scatter(x=pd_data["report_date"],y=pd_data["dead_equiv"], mode="lines+markers",name="Deaths T4eq",line=dict(color="#4a7cba")))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ab0cc",family="Inter"),
            yaxis=dict(gridcolor="rgba(42,63,94,0.5)"),xaxis=dict(gridcolor="rgba(42,63,94,0.5)"),
            legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1))
        st.plotly_chart(fig,use_container_width=True)

    with st.expander("Tabela histórica"):
        cols={"report_date":"Data","kill_points":"KP","dead_equiv":"Deaths T4eq","power":"Power","status":"Status"}
        avail={k:v for k,v in cols.items() if k in pd_data.columns}
        st.dataframe(pd_data[list(avail.keys())].rename(columns=avail),use_container_width=True,hide_index=True)


def show_history(storage, imports, group_power):
    st.markdown('<div class="sec-label">Comparar dois relatórios</div>', unsafe_allow_html=True)
    if len(imports)<2: st.info("Importe pelo menos 2 relatórios."); return
    ordered=imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    labels=ordered["label"].tolist()
    ca,cb=st.columns(2)
    with ca: la=st.selectbox("Base",     labels,index=0,                   key="ha")
    with cb: lb=st.selectbox("Comparar", labels,index=min(1,len(labels)-1),key="hb")
    if la!=lb:
        ia=ordered.loc[ordered["label"]==la,"id"].iloc[0]
        ib=ordered.loc[ordered["label"]==lb,"id"].iloc[0]
        delta=compute_period_deltas(storage.load_stats(ib),storage.load_stats(ia))
        met=calculate_metrics(delta,group_power=group_power)
        top=met.sort_values("kill_points",ascending=False).head(15)
        if not top.empty and px is not None:
            fig=px.bar(top.sort_values("kill_points",ascending=True),x="kill_points",y="username",orientation="h",color_discrete_sequence=["#d4a847"])
            fig.update_layout(showlegend=False,margin=dict(t=10,b=0,l=0,r=0),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#9ab0cc",family="Inter"))
            st.plotly_chart(fig,use_container_width=True)

    st.markdown('<div class="sec-label">Deadweight Tracker</div>', unsafe_allow_html=True)
    all_rows=[]
    for _,ir in imports.sort_values(["report_date","imported_at"]).iterrows():
        try:
            stats=storage.load_stats(ir["id"]); m=calculate_metrics(stats,group_power=group_power)
            r=apply_goals(add_rank(m,"kill_points")); r["report_date"]=ir["report_date"]; all_rows.append(r)
        except: continue
    if all_rows:
        hist=pd.concat(all_rows,ignore_index=True)
        dw=hist[hist["status"]=="Abaixo da meta"]
        inf=dw.groupby(["character_id","username"]).size().reset_index(name="Falhas")
        freq=inf[inf["Falhas"]>=2].sort_values("Falhas",ascending=False)
        if not freq.empty: st.dataframe(freq,use_container_width=True,hide_index=True)
        else: st.success("Nenhum deadweight repetido detectado.")


def show_imports(imports, storage, *, is_admin, admin_enabled):
    st.markdown('<div class="sec-label">Relatórios importados</div>', unsafe_allow_html=True)
    st.dataframe(imports[["report_date","filename","row_count","imported_at"]].rename(columns={
        "report_date":"Data","filename":"Arquivo","row_count":"Membros","imported_at":"Importado em"}),
        use_container_width=True,hide_index=True)
    if admin_enabled and is_admin:
        st.markdown('<div class="sec-label">Excluir import</div>', unsafe_allow_html=True)
        st.warning("Irreversível.")
        labels=imports["label"].tolist()
        to_del=st.selectbox("Selecionar",["— —",*labels])
        if to_del!="— —":
            row=imports.loc[imports["label"]==to_del].iloc[0]
            if st.button("Confirmar exclusão",type="secondary"):
                if storage.delete_import(row["id"]): st.success("Excluído."); st.rerun()
                else: st.error("Não encontrado.")


def show_help():
    st.markdown('<div class="sec-label">Referência Rápida</div>', unsafe_allow_html=True)
    st.markdown("""
**Fórmula KP:** `KP = T5×20 + T4×10 + T3×4 + T2×2 + T1×0.2`

**Equivalência mortes:** 1 T5 death = 2 T4 → `equiv = (T5×2) + T4`

**Ranking:** Soma de kills/mortes em todos os relatórios do período selecionado.

**Filtros sidebar:** Power Min · KP Min · % KP Min · % Deaths Min

**Sort:** KP ↓ · Deaths ↓ · Power ↓ · % KP ↓ · % Deaths ↓ · Name ↑

**Status:** ✅ Aprovado · 🟡 Pendente · ❌ Abaixo da meta

**Gamificação:** 🛡️ Top 5% Deaths · 🔥 2× KP Goal · 🐋 100M+ Power

""")


if __name__ == "__main__":
    main()
