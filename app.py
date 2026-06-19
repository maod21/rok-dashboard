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
#  Palette: Obsidian (#0d0f14) + Stone (#1c1f2b) + Parchment (#e8e0cc)
#  Accent:  Amber (#c8922a) + Ember (#e84545)
#  Type:    Inter (Google Fonts) + JetBrains Mono for numbers
#  Signature: dual-gauge row — KP bar + Deaths bar always visible
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">

<style>
/* ─── RESET / BASE ─────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [class*="css"], .stApp {
  font-family: 'Inter', system-ui, sans-serif !important;
  background: #0d0f14 !important;
  color: #e8e0cc !important;
}

.main .block-container {
  padding: 1.2rem 2rem 3rem !important;
  max-width: 1500px !important;
}

/* ─── SIDEBAR ───────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background: #0d0f14 !important;
  border-right: 1px solid rgba(200,146,42,0.15) !important;
}
section[data-testid="stSidebar"] > div { padding: 1.5rem 1rem !important; }

/* ─── METRICS ───────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: #1c1f2b !important;
  border: 1px solid rgba(200,146,42,0.18) !important;
  border-radius: 10px !important;
  padding: 18px 20px !important;
  position: relative; overflow: hidden;
}
[data-testid="stMetric"]::after {
  content: '';
  position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, #c8922a 0%, transparent 100%);
}
[data-testid="stMetricLabel"] {
  font-size: .62rem !important; font-weight: 600 !important;
  text-transform: uppercase; letter-spacing: .12em;
  color: #7a7060 !important;
}
[data-testid="stMetricValue"] {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 1.5rem !important; font-weight: 600 !important;
  color: #e8e0cc !important; letter-spacing: -.03em;
}

/* ─── TABS ──────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 1px solid rgba(200,146,42,0.20);
  gap: 0; background: transparent;
}
[data-testid="stTabs"] button[role="tab"] {
  font-size: .68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .10em; color: #5a5448 !important;
  padding: 10px 20px; border-bottom: 2px solid transparent;
  border-radius: 0; background: transparent !important;
  transition: color .2s, border-color .2s;
}
[data-testid="stTabs"] button[role="tab"]:hover { color: #c8922a !important; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
  color: #c8922a !important;
  border-bottom-color: #c8922a !important;
  background: transparent !important;
}

/* ─── INPUTS ────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input {
  background: #1c1f2b !important;
  border: 1px solid rgba(200,146,42,0.20) !important;
  border-radius: 8px !important;
  color: #e8e0cc !important;
  font-family: 'Inter', sans-serif !important;
  font-size: .82rem !important;
}
[data-testid="stTextInput"] input::placeholder { color: #4a4438 !important; }
[data-testid="stTextInput"] input:focus,
[data-testid="stSelectbox"] > div > div:focus-within {
  border-color: #c8922a !important;
  box-shadow: 0 0 0 2px rgba(200,146,42,0.15) !important;
}

/* ─── BUTTONS ───────────────────────────────────────────── */
[data-testid="stButton"] button {
  background: #c8922a !important; color: #0d0f14 !important;
  border: none !important; border-radius: 8px !important;
  font-weight: 700 !important; font-size: .78rem !important;
  text-transform: uppercase; letter-spacing: .08em;
  transition: opacity .2s, transform .1s;
}
[data-testid="stButton"] button:hover { opacity: .85; transform: translateY(-1px); }
[data-testid="stButton"] button[kind="secondary"] {
  background: transparent !important;
  border: 1px solid rgba(200,146,42,0.35) !important;
  color: #c8922a !important;
}

/* ─── EXPANDER ──────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
}
[data-testid="stExpander"] > details > summary {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
}

/* ─── DATAFRAME ─────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid rgba(200,146,42,0.15) !important;
  border-radius: 10px !important; overflow: hidden;
}

/* ─── DIVIDER ───────────────────────────────────────────── */
hr { border-color: rgba(200,146,42,0.15) !important; margin: 1.2rem 0 !important; }

/* ─── SCROLLBAR ─────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0d0f14; }
::-webkit-scrollbar-thumb { background: rgba(200,146,42,0.3); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #c8922a; }


/* ══════════════════════════════════════════════════════════
   COMPONENT LIBRARY
   ══════════════════════════════════════════════════════════ */

/* ─── HEADER ────────────────────────────────────────────── */
.rok-header {
  display: flex; align-items: center; gap: 18px;
  padding: 18px 24px; margin-bottom: 18px;
  background: linear-gradient(135deg, #1c1f2b 0%, #15181f 100%);
  border: 1px solid rgba(200,146,42,0.22);
  border-radius: 12px;
  position: relative; overflow: hidden;
}
.rok-header::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, #c8922a, transparent);
}
.rok-header-emblem {
  width: 52px; height: 52px; flex-shrink: 0;
  background: linear-gradient(135deg, #c8922a, #b07820);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6rem;
}
.rok-header-title {
  font-size: 1.4rem; font-weight: 900; color: #e8e0cc;
  letter-spacing: -.03em; line-height: 1;
}
.rok-header-sub {
  font-size: .7rem; color: #7a7060;
  letter-spacing: .05em; margin-top: 4px; text-transform: uppercase;
}
.rok-header-right { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }

/* ─── WEIGHT PILLS ──────────────────────────────────────── */
.tier-pills { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 18px; }
.tier-pill {
  padding: 3px 10px; border-radius: 4px;
  font-size: .64rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; white-space: nowrap;
  border: 1px solid;
}
.tp-t5 { color: #f59e0b; border-color: rgba(245,158,11,.35); background: rgba(245,158,11,.08); }
.tp-t4 { color: #fb923c; border-color: rgba(251,146,60,.35); background: rgba(251,146,60,.08); }
.tp-t3 { color: #a78bfa; border-color: rgba(167,139,250,.35); background: rgba(167,139,250,.08); }
.tp-t2 { color: #60a5fa; border-color: rgba(96,165,250,.35); background: rgba(96,165,250,.08); }
.tp-t1 { color: #6b7280; border-color: rgba(107,114,128,.35); background: rgba(107,114,128,.08); }
.tp-eq { color: #7a7060; border-color: rgba(122,112,96,.35); background: rgba(122,112,96,.08); }

/* ─── SECTION LABEL ─────────────────────────────────────── */
.sec-label {
  font-size: .6rem; font-weight: 800; letter-spacing: .16em;
  text-transform: uppercase; color: #5a5448;
  display: flex; align-items: center; gap: 10px;
  margin: 20px 0 12px;
}
.sec-label::after {
  content: ''; flex: 1; height: 1px;
  background: rgba(200,146,42,0.15);
}

/* ─── KPI STAT BOX ──────────────────────────────────────── */
.stat-box {
  background: #1c1f2b;
  border: 1px solid rgba(200,146,42,0.15);
  border-radius: 10px; padding: 16px 18px;
  position: relative; overflow: hidden;
  height: 100%;
}
.stat-box-icon { font-size: 1.3rem; margin-bottom: 8px; }
.stat-box-label {
  font-size: .6rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .12em; color: #5a5448; margin-bottom: 4px;
}
.stat-box-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.4rem; font-weight: 600;
  color: #e8e0cc; line-height: 1; letter-spacing: -.03em;
}
.stat-box-sub { font-size: .67rem; color: #5a5448; margin-top: 5px; }
.stat-box-bar {
  position: absolute; bottom: 0; left: 0; height: 2px;
  background: linear-gradient(90deg, #c8922a, transparent);
}

/* ─── STATUS BADGE ──────────────────────────────────────── */
.sbadge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 9px; border-radius: 4px;
  font-size: .63rem; font-weight: 700; letter-spacing: .05em;
  text-transform: uppercase; white-space: nowrap; border: 1px solid;
}
.sbadge-ok  { color: #4ade80; border-color: rgba(74,222,128,.3); background: rgba(74,222,128,.08); }
.sbadge-wa  { color: #fbbf24; border-color: rgba(251,191,36,.3); background: rgba(251,191,36,.08); }
.sbadge-er  { color: #f87171; border-color: rgba(248,113,113,.3); background: rgba(248,113,113,.08); }

/* ─── MEMBER ROW ────────────────────────────────────────── */
.mrow {
  background: #1c1f2b;
  border: 1px solid rgba(200,146,42,0.12);
  border-radius: 10px; margin-bottom: 6px;
  overflow: hidden;
  transition: border-color .2s, background .2s;
}
.mrow:hover { border-color: rgba(200,146,42,0.35); background: #20232f; }
.mrow.ok { border-left: 3px solid #4ade80; }
.mrow.wa { border-left: 3px solid #fbbf24; }
.mrow.er { border-left: 3px solid #f87171; }

/* summary — always visible */
.mrow-sum {
  display: grid;
  grid-template-columns: 36px 1fr 90px 80px auto;
  align-items: center; gap: 12px;
  padding: 12px 16px;
}
.mrow-rank {
  font-family: 'JetBrains Mono', monospace;
  font-size: .85rem; font-weight: 600;
  color: #3a3428; text-align: right;
}
.mrow-info { min-width: 0; }
.mrow-name {
  font-size: .88rem; font-weight: 700;
  color: #e8e0cc; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.mrow-meta { font-size: .64rem; color: #5a5448; margin-top: 2px; }

/* dual gauge — the signature element */
.mrow-gauges { display: flex; flex-direction: column; gap: 5px; }
.gauge-wrap {}
.gauge-head {
  display: flex; justify-content: space-between;
  font-size: .58rem; color: #4a4438; margin-bottom: 2px;
}
.gauge-track {
  height: 5px; background: rgba(255,255,255,0.05);
  border-radius: 99px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.04);
}
.gauge-fill {
  height: 100%; border-radius: 99px;
  transition: width .6s cubic-bezier(.4,0,.2,1);
}
.gauge-fill.kp   { background: linear-gradient(90deg, #c8922a, #f0b040); }
.gauge-fill.dead { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.gauge-fill.full { background: linear-gradient(90deg, #15803d, #4ade80); }

.mrow-kp {
  font-family: 'JetBrains Mono', monospace;
  font-size: .9rem; font-weight: 600;
  color: #c8922a; text-align: right; white-space: nowrap;
}

/* detail panel */
.mdet {
  border-top: 1px solid rgba(200,146,42,0.10);
  background: #15181f;
  padding: 16px 20px 20px;
}
.mdet-accent-bar { height: 1px; margin-bottom: 16px; }
.mdet-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 16px; }
.mdet-block-label {
  font-size: .58rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .12em; color: #4a4438; margin-bottom: 6px;
}
.mdet-block-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.6rem; font-weight: 600; color: #e8e0cc;
  letter-spacing: -.04em; line-height: 1;
}
.mdet-block-sub { font-size: .65rem; color: #5a5448; margin-top: 4px; }
.mdet-prog { margin-top: 8px; }
.mdet-prog-head {
  display: flex; justify-content: space-between;
  font-size: .6rem; color: #4a4438; margin-bottom: 3px;
}
.mdet-prog-track {
  height: 8px; background: rgba(255,255,255,0.05);
  border-radius: 99px; overflow: hidden;
}
.mdet-prog-fill {
  height: 100%; border-radius: 99px;
  transition: width .6s cubic-bezier(.4,0,.2,1);
}
.mdet-prog-fill.kp   { background: linear-gradient(90deg, #c8922a, #f0b040); }
.mdet-prog-fill.dead { background: linear-gradient(90deg, #1d4ed8, #60a5fa); }
.mdet-prog-fill.full-kp   { background: linear-gradient(90deg, #15803d, #4ade80); }
.mdet-prog-fill.full-dead { background: linear-gradient(90deg, #15803d, #4ade80); }
.mdet-gap { font-size: .62rem; color: #5a5448; margin-top: 4px; }
.mdet-gap.warn { color: #f87171; }
.mdet-gap.ok   { color: #4ade80; }

/* tier table in detail */
.tier-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
.tier-table th {
  font-size: .58rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .10em; color: #3a3428;
  padding: 5px 8px; text-align: right; border-bottom: 1px solid rgba(200,146,42,0.10);
}
.tier-table th:first-child { text-align: left; }
.tier-table td {
  font-family: 'JetBrains Mono', monospace;
  font-size: .75rem; color: #b0a898;
  padding: 5px 8px; text-align: right;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.tier-table td:first-child { text-align: left; color: #6a6050; font-weight: 600; }
.tier-table tr:last-child td { border-bottom: none; }
.tier-table td.amber { color: #c8922a; }
.tier-table td.blue  { color: #60a5fa; }
.tier-table td.equiv { color: #4a4438; font-size: .68rem; }

/* ─── KINGDOM CARDS ─────────────────────────────────────── */
.kd-row { display: grid; grid-template-columns: repeat(5,1fr); gap: 10px; margin-bottom: 18px; }
.kd-card {
  background: #1c1f2b;
  border: 1px solid rgba(200,146,42,0.15);
  border-radius: 10px; padding: 16px 18px;
  position: relative; overflow: hidden;
}
.kd-card::before {
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
}
.kd-card.amber::before { background: linear-gradient(90deg,#c8922a,transparent); }
.kd-card.green::before { background: linear-gradient(90deg,#4ade80,transparent); }
.kd-card.yellow::before{ background: linear-gradient(90deg,#fbbf24,transparent); }
.kd-card.red::before   { background: linear-gradient(90deg,#f87171,transparent); }
.kd-card.blue::before  { background: linear-gradient(90deg,#60a5fa,transparent); }
.kd-card-icon { font-size: 1.2rem; margin-bottom: 8px; opacity: .7; }
.kd-card-label {
  font-size: .58rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .12em; color: #5a5448; margin-bottom: 5px;
}
.kd-card-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.45rem; font-weight: 600;
  color: #e8e0cc; letter-spacing: -.03em; line-height: 1;
}
.kd-card-sub { font-size: .65rem; color: #4a4438; margin-top: 4px; }

/* status meter card */
.sm-card {
  background: #1c1f2b;
  border: 1px solid rgba(200,146,42,0.12);
  border-radius: 10px; padding: 16px 18px;
}
.sm-label { font-size: .62rem; font-weight: 700; text-transform: uppercase; letter-spacing: .10em; color: #5a5448; margin-bottom: 8px; }
.sm-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2rem; font-weight: 600; color: #e8e0cc;
  letter-spacing: -.04em; line-height: 1;
}
.sm-denom { font-size: 1rem; color: #3a3428; }
.sm-bar { background: rgba(255,255,255,0.05); border-radius: 99px; height: 6px; overflow: hidden; margin-top: 10px; }
.sm-fill { height: 100%; border-radius: 99px; }
.sm-pct { font-size: .6rem; color: #4a4438; margin-top: 4px; }

/* attention row */
.att-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px;
  background: #1c1f2b;
  border: 1px solid rgba(200,146,42,0.10);
  border-radius: 8px; margin-bottom: 5px;
}
.att-row.er { border-left: 3px solid #f87171; }
.att-row.wa { border-left: 3px solid #fbbf24; }
.att-name { flex: 1; font-size: .82rem; font-weight: 600; color: #e8e0cc; }
.att-pow  { font-size: .68rem; color: #5a5448; white-space: nowrap; }
.att-pcts { font-size: .65rem; color: #4a4438; white-space: nowrap; }

/* power band table */
.band-table { width: 100%; border-collapse: collapse; }
.band-table th {
  font-size: .58rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .10em; color: #4a4438;
  padding: 8px 12px; text-align: right;
  border-bottom: 1px solid rgba(200,146,42,0.15);
}
.band-table th:first-child { text-align: left; }
.band-table td {
  font-family: 'JetBrains Mono', monospace;
  font-size: .76rem; color: #9a9080;
  padding: 8px 12px; text-align: right;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.band-table td:first-child { text-align: left; color: #7a7060; font-weight: 600; font-family: 'Inter', sans-serif; font-size: .78rem; }
.band-table tr:last-child td { border-bottom: none; }

/* ─── UPLOAD LOCK ───────────────────────────────────────── */
.upload-lock {
  background: #15181f;
  border: 1px solid rgba(200,146,42,0.18);
  border-radius: 8px; padding: 14px;
  text-align: center; margin-bottom: 10px;
}
.upload-lock-icon { font-size: 1.3rem; margin-bottom: 6px; }
.upload-lock-text { font-size: .72rem; color: #5a5448; margin-bottom: 10px; }

/* ─── SIDEBAR SECTION LABEL ─────────────────────────────── */
.sb-sec {
  font-size: .58rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .14em; color: #3a3428;
  border-bottom: 1px solid rgba(200,146,42,0.12);
  padding-bottom: 6px; margin: 14px 0 10px;
}

/* ─── CAPTION ───────────────────────────────────────────── */
.rok-caption {
  display: flex; align-items: center; gap: 14px;
  padding: 8px 14px; margin-bottom: 16px;
  background: #15181f;
  border: 1px solid rgba(200,146,42,0.10);
  border-radius: 6px; flex-wrap: wrap;
}
.rok-caption-item { font-size: .68rem; color: #5a5448; }
.rok-caption-val  { color: #9a8060; font-weight: 600; }
.rok-caption-sep  { color: #2a2418; font-size: .7rem; }

/* ─── KVK EVENT CARD ────────────────────────────────────── */
.kvk-event-card {
  background: linear-gradient(135deg,#1c1f2b,#15181f);
  border: 1px solid rgba(200,146,42,0.18);
  border-radius: 10px; padding: 14px 18px; margin-bottom: 8px;
  display: flex; align-items: center; gap: 14px;
  transition: border-color .2s;
}
.kvk-event-card:hover { border-color: rgba(200,146,42,0.4); }
.kvk-event-name { font-size: .92rem; font-weight: 700; color: #e8e0cc; }
.kvk-event-dates { font-size: .68rem; color: #7a7060; margin-top: 2px; }
.kvk-event-badge {
  margin-left: auto; padding: 4px 10px; border-radius: 4px;
  font-size: .6rem; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
  background: rgba(200,146,42,0.1); color: #c8922a; border: 1px solid rgba(200,146,42,0.3);
  white-space: nowrap;
}

/* ─── HISTORY COMPARE ───────────────────────────────────── */
.compare-header {
  background: #1c1f2b;
  border: 1px solid rgba(200,146,42,0.15);
  border-radius: 10px; padding: 14px 18px; margin-bottom: 16px;
  font-size: .72rem; color: #7a7060;
}

/* ─── EMPTY STATE ───────────────────────────────────────── */
.empty-state {
  text-align: center; padding: 60px 20px;
  color: #3a3428;
}
.empty-state-icon { font-size: 3rem; margin-bottom: 14px; opacity: .4; }
.empty-state-title { font-size: 1rem; font-weight: 700; color: #5a5448; margin-bottom: 6px; }
.empty-state-sub   { font-size: .75rem; color: #3a3428; }
</style>
""", unsafe_allow_html=True)

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
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    storage = get_storage()

    # Header
    st.markdown("""
    <div class="rok-header">
      <div class="rok-header-emblem">⚔️</div>
      <div>
        <div class="rok-header-title">K1602 · KP Dashboard</div>
        <div class="rok-header-sub">Kill Points Operations Center · Rise of Kingdoms</div>
      </div>
    </div>
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
        st.markdown(f'<div style="font-size:.68rem;color:#5a5448;margin-bottom:12px">Storage: <span style="color:#c8922a">{storage.label}</span></div>', unsafe_allow_html=True)
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

    # Caption bar
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

    tab_labels = ["⚔ Ranking", "🛡 KvK", "🏆 Hall of Fame", "🏰 Kingdom", "❓ Help"]
    if admin_enabled and is_admin:
        tab_labels.append("📈 History")
        tab_labels.append("📁 Imports")

    tabs = st.tabs(tab_labels)
    with tabs[0]: show_ranking(ranked)
    with tabs[1]: show_kvk(storage, gp, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[2]: show_hof(storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[3]: show_kingdom(ranked, imports, storage, gp)
    with tabs[4]: show_help()
    if admin_enabled and is_admin:
        with tabs[5]: show_history(storage, imports, gp)
        with tabs[6]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)


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
        # Archive Hall of Fame for this import
        try:
            imports_df = storage.list_imports()
            imports_df = prepare_imports(imports_df)
            prev = load_previous_report(storage, imports_df,
                                        imports_df.loc[imports_df["id"].eq(import_id_saved)].iloc[0])                    if not imports_df.empty else None
            archived = maybe_archive(storage, import_id_saved, stats, prev)
            if archived:
                st.info(f"🏆 Hall of Fame: {archived} entries archived")
        except Exception as _hof_err:
            pass  # HOF is best-effort, doesn't block upload
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

def show_ranking(ranked_full: pd.DataFrame) -> None:

    # Filter bar
    fc1, fc2, fc3 = st.columns([5, 2, 2])
    with fc1:
        search = st.text_input("search", placeholder="Search member or Character ID…",
                                key="rank_search", label_visibility="collapsed")
    with fc2:
        sf = st.selectbox("status", ["All","Approved","Pending","Below goal"],
                          key="rank_sf", label_visibility="collapsed")
    with fc3:
        sort_by = st.selectbox("sort",
                               ["KP ↓","Power ↓","% KP ↓","% Deaths ↓","Name ↑"],
                               key="rank_sort", label_visibility="collapsed")

    with st.expander("Filter by import date", expanded=False):
        dc1, dc2, dc3 = st.columns([2,2,1])
        with dc1: date_from = st.date_input("From", value=None, key="df_from")
        with dc2: date_to   = st.date_input("To",   value=None, key="df_to")
        with dc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Clear", key="clr_dt"):
                st.session_state.df_from = None; st.session_state.df_to = None; st.rerun()

    # Apply
    df = ranked_full.copy()
    if search.strip():
        n = search.strip().lower()
        df = df[df["username"].astype(str).str.lower().str.contains(n,regex=False,na=False)
                |df["character_id"].astype(str).str.lower().str.contains(n,regex=False,na=False)]
    status_map_en2pt = {"Approved":"Aprovado","Pending":"Pendente","Below goal":"Abaixo da meta"}
    if sf != "All":
        df = df[df["status"] == status_map_en2pt.get(sf, sf)]
    if "imported_at" in df.columns and (date_from or date_to):
        df["_dt"] = pd.to_datetime(df["imported_at"],errors="coerce").dt.date
        if date_from: df = df[df["_dt"] >= date_from]
        if date_to:   df = df[df["_dt"] <= date_to]
        df = df.drop(columns=["_dt"])

    sort_map = {
        "KP ↓":("kill_points",False),"Power ↓":("power",False),
        "% KP ↓":("kp_pct",False),"% Deaths ↓":("dead_pct",False),"Name ↑":("username",True),
    }
    scol, sasc = sort_map.get(sort_by, ("kill_points",False))
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    st.markdown(f'<div class="sec-label">Governors · {len(df):,} of {len(ranked_full):,}</div>',
                unsafe_allow_html=True)

    # Pagination
    page_size = st.selectbox("Per page",[25,50,100],index=0,key="rank_ps",label_visibility="collapsed")
    total_pg  = max(1,-(-len(df)//page_size))
    col_pg1, col_pg2 = st.columns([1,5])
    with col_pg1:
        page = st.number_input("Page",min_value=1,max_value=total_pg,value=1,key="rank_pg",label_visibility="collapsed")
    with col_pg2:
        st.markdown(f'<div style="font-size:.65rem;color:#3a3428;padding-top:8px">Page {page} of {total_pg}</div>',unsafe_allow_html=True)

    start = (page-1)*page_size
    _render_members(df.iloc[start:start+page_size])

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
        st.download_button("⬇ Download CSV", data=df.to_csv(index=False).encode(), file_name="ranking.csv", mime="text/csv")


def _render_members(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        cls   = STATUS_CLS.get(row["status"], "er")
        kp_w   = min(float(row.get("kp_pct",0))*100, 100)
        dead_w = min(float(row.get("dead_pct",0))*100, 100)
        kp_gap   = int(row.get("kp_gap",0))
        dead_gap = int(row.get("dead_gap_t4",0))

        # gauge fill class
        kp_fc   = "full" if kp_w   >= 100 else "kp"
        dead_fc = "full" if dead_w >= 100 else "dead"

        # badge html
        badge_cls = f"sbadge-{cls}"
        badge = (f'<span class="sbadge {badge_cls}">'
                 f'{STATUS_ICON.get(row["status"],"○")} {STATUS_LABEL.get(row["status"],"—")}</span>')

        # summary row HTML
        st.markdown(f"""
        <div class="mrow {cls}">
          <div class="mrow-sum">
            <div class="mrow-rank">#{int(row['rank'])}</div>
            <div class="mrow-info">
              <div class="mrow-name">{row['username']}</div>
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

        # Expander for detail
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
              <div class="mdet-accent-bar" style="background:{'#4ade80' if cls=='ok' else '#fbbf24' if cls=='wa' else '#f87171'}"></div>
              <div class="mdet-grid">
                <!-- KP block -->
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
                <!-- Deaths block -->
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

            # Tier tables side by side
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
                <div style="font-size:.62rem;color:#4a4438;margin-top:8px">
                  Total equiv: <span style="color:#60a5fa;font-family:monospace">{fmt_int(dead_equiv)}</span>
                  / Goal: <span style="color:#7a7060;font-family:monospace">{fmt_int(int(row['dead_t4_goal']))}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab — KvK  (NEW)
# ══════════════════════════════════════════════════════════════════════════════

def show_kvk(storage, group_power: int, *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#c8922a">
      <div class="rok-header-emblem" style="background:linear-gradient(135deg,#c8922a,#a07018)">🛡</div>
      <div>
        <div class="rok-header-title">KvK Events</div>
        <div class="rok-header-sub">Performance windows for Kingdom vs Kingdom</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    # ── Admin: create new KvK event ──
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

    # ── Event selector ──
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

    # ── Admin: delete event ──
    if admin_enabled and is_admin:
        with st.expander("🗑 Delete this event", expanded=False):
            st.warning("Irreversible — this only deletes the event window, not the underlying reports.")
            if st.button("Confirm delete event", type="secondary", key="kvk_del_btn"):
                if storage.delete_kvk_event(event_row["id"]):
                    st.success("Deleted."); st.rerun()
                else:
                    st.error("Not found.")

    # ── Pull imports inside the window ──
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
        # only one report in window — show totals, not deltas
        stats_window = storage.load_stats(first_id)
        basis_note = "totals (only 1 report in window)"
    else:
        stats_first = storage.load_stats(first_id)
        stats_last  = storage.load_stats(last_id)
        stats_window = compute_period_deltas(stats_last, stats_first)
        basis_note = f"delta between first and last report in window"

    st.caption(f"📐 Basis: {basis_note}")

    metrics_window = calculate_metrics(stats_window, group_power=group_power)
    ranked_window  = apply_goals(add_rank(metrics_window, "kill_points"))

    # ── Optional sub-filter by date within the window ──
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

    # ── Kingdom summary for this event ──
    total    = len(ranked_window)
    approved = int((ranked_window["status"]=="Aprovado").sum())
    pending  = int((ranked_window["status"]=="Pendente").sum())
    below    = int((ranked_window["status"]=="Abaixo da meta").sum())
    kp_total = int(ranked_window["kill_points"].sum())

    st.markdown('<div class="sec-label">Kingdom performance — this event</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kd-row">
      <div class="kd-card amber">
        <div class="kd-card-icon">⚔️</div>
        <div class="kd-card-label">Total Kill Points</div>
        <div class="kd-card-value">{fmt_k(kp_total)}</div>
        <div class="kd-card-sub">earned in this event</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-icon">✅</div>
        <div class="kd-card-label">Approved</div>
        <div class="kd-card-value">{approved}</div>
        <div class="kd-card-sub">of {total} members</div>
      </div>
      <div class="kd-card yellow">
        <div class="kd-card-icon">🟡</div>
        <div class="kd-card-label">Pending</div>
        <div class="kd-card-value">{pending}</div>
        <div class="kd-card-sub">close to goal</div>
      </div>
      <div class="kd-card red">
        <div class="kd-card-icon">⚠️</div>
        <div class="kd-card-label">Below Goal</div>
        <div class="kd-card-value">{below}</div>
        <div class="kd-card-sub">needs attention</div>
      </div>
      <div class="kd-card blue">
        <div class="kd-card-icon">👥</div>
        <div class="kd-card-label">Governors</div>
        <div class="kd-card-value">{total:,}</div>
        <div class="kd-card-sub">tracked in window</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if px is not None and not ranked_window.empty:
        st.markdown('<div class="sec-label">Top performers — this event</div>', unsafe_allow_html=True)
        top20 = ranked_window.sort_values("kill_points",ascending=True).tail(20)
        cmap = {"Aprovado":"#4ade80","Pendente":"#fbbf24","Abaixo da meta":"#f87171"}
        fig = px.bar(top20, x="kill_points", y="username", orientation="h",
                     color="status", color_discrete_map=cmap,
                     labels={"kill_points":"Kill Points","username":""})
        fig.update_layout(showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#7a7060", family="Inter"),
            yaxis=dict(tickfont=dict(size=11,color="#9a9080"), gridcolor="rgba(200,146,42,0.06)"),
            xaxis=dict(tickfont=dict(size=10), gridcolor="rgba(200,146,42,0.06)"))
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    # ── Individual ranking for this event ──
    st.markdown('<div class="sec-label">Individual ranking — this event</div>', unsafe_allow_html=True)
    show_ranking(ranked_window)


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

    # KPI cards
    st.markdown(f"""
    <div class="kd-row">
      <div class="kd-card amber">
        <div class="kd-card-icon">⚔️</div>
        <div class="kd-card-label">Total Kill Points</div>
        <div class="kd-card-value">{fmt_k(kp_total)}</div>
        <div class="kd-card-sub">accumulated points</div>
      </div>
      <div class="kd-card blue">
        <div class="kd-card-icon">🏰</div>
        <div class="kd-card-label">Total Power</div>
        <div class="kd-card-value">{fmt_m(power_total)}M</div>
        <div class="kd-card-sub">combined city power</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-icon">👥</div>
        <div class="kd-card-label">Governors</div>
        <div class="kd-card-value">{total:,}</div>
        <div class="kd-card-sub">{active} active in period</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-icon">✅</div>
        <div class="kd-card-label">Approval Rate</div>
        <div class="kd-card-value">{aprov_pct:.1f}%</div>
        <div class="kd-card-sub">{approved} of {total} members</div>
      </div>
      <div class="kd-card red">
        <div class="kd-card-icon">⚠️</div>
        <div class="kd-card-label">Below Goal</div>
        <div class="kd-card-value">{below}</div>
        <div class="kd-card-sub">{pending} pending</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Status meters
    st.markdown('<div class="sec-label">Goal status</div>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    for col, lbl, count, color in [
        (m1,"Approved",  approved,"#4ade80"),
        (m2,"Pending",  pending, "#fbbf24"),
        (m3,"Below goal", below, "#f87171"),
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

    # Charts
    if px is not None:
        st.markdown('<div class="sec-label">Kill Points distribution</div>', unsafe_allow_html=True)
        g1, g2 = st.columns([3,2])
        cmap = {"Aprovado":"#4ade80","Pendente":"#fbbf24","Abaixo da meta":"#f87171"}

        with g1:
            top20 = ranked.sort_values("kill_points",ascending=True).tail(20)
            fig = px.bar(top20, x="kill_points", y="username", orientation="h",
                         color="status", color_discrete_map=cmap,
                         labels={"kill_points":"Kill Points","username":""})
            fig.update_layout(
                showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#7a7060", family="Inter"),
                yaxis=dict(tickfont=dict(size=11,color="#9a9080"), gridcolor="rgba(200,146,42,0.06)"),
                xaxis=dict(tickfont=dict(size=10), gridcolor="rgba(200,146,42,0.06)"),
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with g2:
            fig2 = px.pie(
                values=[approved,pending,below],
                names=["Approved","Pending","Below goal"],
                hole=0.65, color_discrete_sequence=["#4ade80","#fbbf24","#f87171"],
            )
            fig2.update_traces(textposition="inside", textinfo="percent", textfont_size=11,
                               marker=dict(line=dict(color="#0d0f14",width=2)))
            fig2.update_layout(
                showlegend=True, margin=dict(t=10,b=0,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#7a7060", family="Inter"),
                legend=dict(orientation="h",y=-0.08,font=dict(size=10,color="#7a7060")),
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Power bands
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

    # Attention
    st.markdown('<div class="sec-label">Need attention</div>', unsafe_allow_html=True)
    att = ranked[ranked["status"]!="Aprovado"].sort_values("kp_pct").head(8)
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


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Hall of Fame
# ══════════════════════════════════════════════════════════════════════════════

def show_hof(storage, *, is_admin: bool, admin_enabled: bool) -> None:
    st.markdown('''
    <div class="rok-header" style="border-left-color:#c8922a">
      <div class="rok-header-emblem" style="background:linear-gradient(135deg,#c8922a,#a07018)">🏆</div>
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

    # KVK selector
    col_sel, col_info = st.columns([3,3])
    with col_sel:
        selected_kvk = st.selectbox("KVK", kvks, key="hof_kvk", label_visibility="collapsed")
    with col_info:
        total_kvks = len(kvks)
        st.markdown(
            f'<div style="font-size:.68rem;color:#5a5448;padding-top:8px">'            f'<span style="color:#c8922a;font-weight:700">{total_kvks}</span> KVK(s) archived'            f'</div>',
            unsafe_allow_html=True,
        )

    kvk_data = hof[hof["kvk_name"] == selected_kvk]

    kp_df    = kvk_data[kvk_data["category"] == "kp"   ].sort_values("position")
    dead_df  = kvk_data[kvk_data["category"] == "deaths"].sort_values("position")

    st.markdown(f'<div class="sec-label">{selected_kvk}</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    # ── TOP 10 KP ──
    with c1:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;'                    'letter-spacing:.14em;color:#c8922a;margin-bottom:10px">⚔ Top 10 Kill Points</div>',
                    unsafe_allow_html=True)
        _render_hof_list(kp_df, "kp")

    # ── TOP 10 DEATHS ──
    with c2:
        st.markdown('<div style="font-size:.62rem;font-weight:800;text-transform:uppercase;'                    'letter-spacing:.14em;color:#60a5fa;margin-bottom:10px">💀 Top 10 Deaths</div>',
                    unsafe_allow_html=True)
        _render_hof_list(dead_df, "deaths")

    # ── History of all KVKs ──
    if len(kvks) > 1:
        st.markdown('<div class="sec-label">Full history</div>', unsafe_allow_html=True)
        with st.expander("View all KVKs →", expanded=False):
            for kvk in kvks:
                sub = hof[hof["kvk_name"] == kvk]
                kp_top3 = sub[sub["category"]=="kp"].sort_values("position").head(3)
                st.markdown(f'<div style="font-size:.7rem;font-weight:700;color:#7a7060;margin:10px 0 4px">{kvk}</div>',
                            unsafe_allow_html=True)
                if not kp_top3.empty:
                    medals = ["🥇","🥈","🥉"]
                    for i,(_, r) in enumerate(kp_top3.iterrows()):
                        st.markdown(
                            f'<div style="font-size:.75rem;color:#9a9080;margin-left:8px">'                            f'{medals[i]} {r["username"]} — '                            f'<span style="color:#c8922a;font-family:monospace">{fmt_k(int(r["value"]))} KP</span>'                            f'</div>',
                            unsafe_allow_html=True,
                        )

    # Admin — re-archive
    if admin_enabled and is_admin:
        st.markdown('<div class="sec-label">Admin</div>', unsafe_allow_html=True)
        st.caption("Re-archiving overwrites the Hall of Fame for the selected import.")


def _render_hof_list(df: pd.DataFrame, category: str) -> None:
    if df.empty:
        st.caption("No data for this KVK.")
        return

    medals = {1:"🥇", 2:"🥈", 3:"🥉"}
    color  = "#c8922a" if category == "kp" else "#60a5fa"
    unit   = "KP" if category == "kp" else "T4eq"

    for _, row in df.iterrows():
        pos    = int(row["position"])
        medal  = medals.get(pos, f"#{pos}")
        is_top = pos <= 3

        st.markdown(f'''
        <div style="display:flex;align-items:center;gap:10px;
                    padding:{'12px 14px' if is_top else '9px 14px'};
                    background:{"rgba(200,146,42,0.06)" if is_top else "#15181f"};
                    border:1px solid {"rgba(200,146,42,0.25)" if is_top else "rgba(255,255,255,0.04)"};
                    border-radius:8px;margin-bottom:5px;">
          <div style="font-size:{'1.2rem' if is_top else '.85rem'};min-width:28px;text-align:center">{medal}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:{'0.88rem' if is_top else '0.82rem'};
                        font-weight:{'700' if is_top else '500'};
                        color:#e8e0cc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              {row["username"]}
            </div>
            <div style="font-size:.62rem;color:#4a4438;margin-top:1px">
              {fmt_m(int(row["power"]))}M power
            </div>
          </div>
          <div style="font-family:'JetBrains Mono',monospace;
                      font-size:{'1rem' if is_top else '0.85rem'};
                      font-weight:600;color:{color};white-space:nowrap">
            {fmt_k(int(row["value"]))} {unit}
          </div>
        </div>
        ''', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab — History  (admin only)
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
    if la == lb: st.warning("Select two different reports."); return

    id_a = ordered.loc[ordered["label"].eq(la),"id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
    delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
    met   = calculate_metrics(delta, group_power=group_power)
    top   = met.sort_values("kill_points",ascending=False).head(15)

    if not top.empty and px is not None:
        fig = px.bar(top.sort_values("kill_points",ascending=True),
                     x="kill_points", y="username", orientation="h",
                     color_discrete_sequence=["#c8922a"],
                     labels={"kill_points":"Kill Points Gained","username":""})
        fig.update_layout(
            showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#7a7060",family="Inter"),
            yaxis=dict(tickfont=dict(size=11,color="#9a9080"),gridcolor="rgba(200,146,42,0.06)"),
            xaxis=dict(gridcolor="rgba(200,146,42,0.06)"),
        )
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        met[["username","power","kill_points","t5_kills","t4_kills","t3_kills","t2_kills","t1_kills"]]
           .sort_values("kill_points",ascending=False)
           .rename(columns={"username":"Governor","power":"Power","kill_points":"KP",
                             "t5_kills":"T5","t4_kills":"T4","t3_kills":"T3","t2_kills":"T2","t1_kills":"T1"}),
        use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab — Imports  (admin only)
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

**Dual gauge in ranking:** each member shows two bars — KP (amber) and Deaths (blue) — always visible without expanding, for fast reading.

**KvK tab:** an admin creates an event with a name and a date range. The system automatically pulls every report inside that window and computes the individual ranking and kingdom summary for that specific period.
""")

    st.markdown('<div class="sec-label">Goal table</div>', unsafe_allow_html=True)
    st.markdown("""
| City Power | Death Goal | KP Goal |
|---|---|---|
| ≤49M | 900k T4 / 450k T5 | 80M |
| 50–59M | 900k T4 / 450k T5 | 100M |
| 60–69M | 1M T4 / 500k T5 | 140M |
| 70–79M | 1.4M T4 / 700k T5 | 180M |
| 80–89M | 1.6M T4 / 800k T5 | 200M |
| 90–99M | 2M T4 / 1M T5 | 280M |
| ≥100M | 2M T4 / 1M T5 | 320M |
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
