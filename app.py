from __future__ import annotations
import os, re
from datetime import date
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

st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — Dual-theme (Dark / Light)
#  Dark:  Obsidian (#0d0f14) + Stone (#1c1f2b) + Parchment (#e8e0cc) + Amber
#  Light: Parchment (#f5f0e8) + White (#ffffff) + Ink (#1a1410) + Amber dark
#  Signature: dual-gauge row sempre visível, sem expand
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN SYSTEM — Executive Dual Theme
#  Dark:  Midnight Navy + Slate surfaces + Imperial Gold accent
#  Light: Cloud White + Slate ink + Warm Gold accent
#  Objetivo: contraste alto, visual premium e leitura confortável nos 2 modos.
# ══════════════════════════════════════════════════════════════════════════════

def ui_tokens(dark: bool | None = None) -> dict:
    """Tokens visuais centralizados para CSS, gráficos e pequenos componentes HTML."""
    if dark is None:
        dark = bool(st.session_state.get("dark_mode", True))

    if dark:
        return {
            "mode": "dark",
            "bg": "#080D1A",
            "bg_soft": "#0D1424",
            "surface": "#111827",
            "surface2": "#172033",
            "surface3": "#1E293B",
            "sidebar_bg": "#0B1020",
            "sidebar_text": "#CBD5E1",
            "sidebar_dim": "#64748B",
            "sidebar_border": "rgba(245,158,11,0.18)",
            "input_bg": "#0F172A",
            "border": "rgba(148,163,184,0.16)",
            "border_hi": "rgba(245,158,11,0.38)",
            "shadow": "0 18px 55px rgba(0,0,0,.38)",
            "shadow_sm": "0 10px 28px rgba(0,0,0,.24)",
            "text": "#F8FAFC",
            "text_sub": "#CBD5E1",
            "text_dim": "#94A3B8",
            "text_muted": "#64748B",
            "text_faint": "#475569",
            "accent": "#F59E0B",
            "accent_hi": "#FBBF24",
            "accent_soft": "rgba(245,158,11,.12)",
            "green": "#22C55E",
            "yellow": "#FACC15",
            "red": "#F87171",
            "blue": "#38BDF8",
            "blue_dark": "#2563EB",
            "purple": "#A78BFA",
            "gauge_bg": "rgba(226,232,240,.08)",
            "gauge_bdr": "rgba(226,232,240,.05)",
            "plot_grid": "rgba(148,163,184,.14)",
            "plot_axis": "#94A3B8",
            "pie_line": "#080D1A",
            "button_text": "#111827",
            "table_header": "#CBD5E1",
            "table_cell": "#CBD5E1",
            "table_dim": "#94A3B8",
        }

    return {
        "mode": "light",
        "bg": "#F6F8FC",
        "bg_soft": "#EEF2F7",
        "surface": "#FFFFFF",
        "surface2": "#F1F5F9",
        "surface3": "#E2E8F0",
        "sidebar_bg": "#FFFFFF",
        "sidebar_text": "#334155",
        "sidebar_dim": "#64748B",
        "sidebar_border": "rgba(15,23,42,0.10)",
        "input_bg": "#FFFFFF",
        "border": "rgba(15,23,42,0.10)",
        "border_hi": "rgba(180,83,9,0.28)",
        "shadow": "0 18px 45px rgba(15,23,42,.09)",
        "shadow_sm": "0 8px 22px rgba(15,23,42,.07)",
        "text": "#0F172A",
        "text_sub": "#334155",
        "text_dim": "#64748B",
        "text_muted": "#94A3B8",
        "text_faint": "#CBD5E1",
        "accent": "#B45309",
        "accent_hi": "#D97706",
        "accent_soft": "rgba(180,83,9,.09)",
        "green": "#15803D",
        "yellow": "#B45309",
        "red": "#B91C1C",
        "blue": "#0369A1",
        "blue_dark": "#1D4ED8",
        "purple": "#6D28D9",
        "gauge_bg": "rgba(15,23,42,.08)",
        "gauge_bdr": "rgba(15,23,42,.06)",
        "plot_grid": "rgba(100,116,139,.18)",
        "plot_axis": "#64748B",
        "pie_line": "#FFFFFF",
        "button_text": "#FFFFFF",
        "table_header": "#334155",
        "table_cell": "#334155",
        "table_dim": "#64748B",
    }


def _css(dark: bool) -> str:
    t = ui_tokens(dark)

    bg = t["bg"]; bg_soft = t["bg_soft"]
    surface = t["surface"]; surface2 = t["surface2"]; surface3 = t["surface3"]
    sidebar_bg = t["sidebar_bg"]; sidebar_text = t["sidebar_text"]; sidebar_dim = t["sidebar_dim"]; sidebar_border = t["sidebar_border"]
    input_bg = t["input_bg"]
    border = t["border"]; border_hi = t["border_hi"]
    shadow = t["shadow"]; shadow_sm = t["shadow_sm"]
    text = t["text"]; text_sub = t["text_sub"]; text_dim = t["text_dim"]; text_muted = t["text_muted"]; text_faint = t["text_faint"]
    accent = t["accent"]; accent_hi = t["accent_hi"]; accent_soft = t["accent_soft"]
    green = t["green"]; yellow = t["yellow"]; red = t["red"]
    blue = t["blue"]; blue_dark = t["blue_dark"]; purple = t["purple"]
    gauge_bg = t["gauge_bg"]; gauge_bdr = t["gauge_bdr"]
    plot_grid = t["plot_grid"]
    button_text = t["button_text"]
    table_header = t["table_header"]; table_cell = t["table_cell"]; table_dim = t["table_dim"]

    ok_bg = "rgba(34,197,94,.13)" if dark else "rgba(21,128,61,.10)"
    ok_br = "rgba(34,197,94,.32)" if dark else "rgba(21,128,61,.24)"
    wa_bg = "rgba(250,204,21,.14)" if dark else "rgba(180,83,9,.10)"
    wa_br = "rgba(250,204,21,.34)" if dark else "rgba(180,83,9,.24)"
    er_bg = "rgba(248,113,113,.14)" if dark else "rgba(185,28,28,.10)"
    er_br = "rgba(248,113,113,.34)" if dark else "rgba(185,28,28,.24)"

    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --rok-bg: {bg};
  --rok-bg-soft: {bg_soft};
  --rok-surface: {surface};
  --rok-surface-2: {surface2};
  --rok-surface-3: {surface3};
  --rok-border: {border};
  --rok-border-hi: {border_hi};
  --rok-text: {text};
  --rok-text-sub: {text_sub};
  --rok-text-dim: {text_dim};
  --rok-text-muted: {text_muted};
  --rok-accent: {accent};
  --rok-accent-hi: {accent_hi};
  --rok-green: {green};
  --rok-yellow: {yellow};
  --rok-red: {red};
  --rok-blue: {blue};
  --rok-blue-dark: {blue_dark};
}}

/* ─── RESET / BASE ─────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; }}
html, body, [class*="css"], .stApp {{
  font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif !important;
  background:
    radial-gradient(circle at 12% 0%, {accent_soft} 0, transparent 32%),
    radial-gradient(circle at 90% 0%, rgba(56,189,248,.08) 0, transparent 28%),
    {bg} !important;
  color: {text} !important;
}}
.main .block-container {{
  padding: 1.35rem 2rem 3.2rem !important;
  max-width: 1540px !important;
}}

/* ─── SIDEBAR ───────────────────────────────────────────── */
section[data-testid="stSidebar"] {{
  background: {sidebar_bg} !important;
  border-right: 1px solid {sidebar_border} !important;
  box-shadow: {shadow_sm};
}}
section[data-testid="stSidebar"] > div {{ padding: 1.35rem .95rem !important; }}
section[data-testid="stSidebar"] * {{ color: {sidebar_text} !important; }}
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ color: {sidebar_dim} !important; }}
section[data-testid="stSidebar"] .stSuccess p {{ color: {green} !important; }}
section[data-testid="stSidebar"] .stError p {{ color: {red} !important; }}
section[data-testid="stSidebar"] .stWarning p {{ color: {yellow} !important; }}
.sidebar-storage {{ font-size:.70rem; color:{sidebar_dim}; margin-bottom:12px; }}
.sidebar-storage span {{ color:{accent_hi}; font-weight:800; }}

/* ─── STREAMLIT CORE COMPONENTS ─────────────────────────── */
[data-testid="stMetric"], [data-testid="stDataFrame"], .stAlert {{
  background: {surface} !important;
  border: 1px solid {border} !important;
  border-radius: 14px !important;
  box-shadow: {shadow_sm};
}}
[data-testid="stMetric"] {{ padding: 18px 20px !important; position: relative; overflow: hidden; }}
[data-testid="stMetric"]::after {{
  content:''; position:absolute; left:0; right:0; bottom:0; height:3px;
  background: linear-gradient(90deg,{accent},{accent_hi},transparent);
}}
[data-testid="stMetricLabel"] {{
  font-size:.64rem !important; font-weight:800 !important; text-transform:uppercase;
  letter-spacing:.12em; color:{text_dim} !important;
}}
[data-testid="stMetricValue"] {{
  font-family:'JetBrains Mono', monospace !important; font-size:1.55rem !important;
  font-weight:700 !important; color:{text} !important; letter-spacing:-.04em;
}}

[data-testid="stTabs"] [role="tablist"] {{
  border-bottom:1px solid {border}; gap:4px; background:transparent;
}}
[data-testid="stTabs"] button[role="tab"] {{
  font-size:.70rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em;
  color:{text_dim} !important; padding:11px 18px; border-bottom:2px solid transparent;
  border-radius:10px 10px 0 0; background:transparent !important;
  transition:color .2s, background .2s, border-color .2s;
}}
[data-testid="stTabs"] button[role="tab"]:hover {{ color:{accent} !important; background:{accent_soft} !important; }}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  color:{accent} !important; border-bottom-color:{accent} !important; background:{surface} !important;
}}

[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {{
  background:{input_bg} !important; border:1px solid {border} !important; border-radius:10px !important;
  color:{text} !important; font-family:'Inter', sans-serif !important; font-size:.84rem !important;
  min-height: 38px;
}}
[data-testid="stTextInput"] input::placeholder {{ color:{text_muted} !important; }}
[data-testid="stTextInput"] input:focus,
[data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stNumberInput"] input:focus,
[data-testid="stDateInput"] input:focus {{
  border-color:{accent} !important; box-shadow:0 0 0 3px {accent_soft} !important;
}}
[data-testid="stButton"] button {{
  background:linear-gradient(135deg,{accent},{accent_hi}) !important; color:{button_text} !important;
  border:none !important; border-radius:10px !important; font-weight:800 !important; font-size:.76rem !important;
  text-transform:uppercase; letter-spacing:.07em; box-shadow:0 10px 24px {accent_soft};
  transition: transform .12s ease, opacity .2s ease, box-shadow .2s ease;
}}
[data-testid="stButton"] button:hover {{ opacity:.92; transform:translateY(-1px); box-shadow:0 14px 30px {accent_soft}; }}
[data-testid="stButton"] button[kind="secondary"] {{
  background:{surface} !important; border:1px solid {border_hi} !important; color:{accent} !important; box-shadow:none;
}}
[data-testid="stExpander"] {{ border:none !important; border-radius:0 !important; background:transparent !important; }}
[data-testid="stExpander"] > details > summary {{
  background:transparent !important; border:none !important; padding:0 !important; color:{text_sub} !important;
}}
hr {{ border-color:{border} !important; margin:1.2rem 0 !important; }}
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:{bg_soft}; }}
::-webkit-scrollbar-thumb {{ background:{text_faint}; border-radius:999px; }}
::-webkit-scrollbar-thumb:hover {{ background:{accent}; }}
[data-testid="stRadio"] label, [data-testid="stCheckbox"] label {{ color:{text_sub} !important; font-size:.78rem !important; }}

/* ─── HEADER ────────────────────────────────────────────── */
.rok-header {{
  display:flex; align-items:center; gap:18px; padding:20px 24px; margin-bottom:18px;
  background:
    linear-gradient(135deg, {surface} 0%, {surface2} 100%);
  border:1px solid {border_hi}; border-radius:18px; position:relative; overflow:hidden;
  box-shadow:{shadow};
}}
.rok-header::before {{ content:''; position:absolute; inset:0 0 auto 0; height:1px; background:linear-gradient(90deg,transparent,{accent_hi},transparent); }}
.rok-header::after {{ content:''; position:absolute; width:220px; height:220px; right:-90px; top:-120px; background:{accent_soft}; border-radius:50%; filter:blur(2px); }}
.rok-header-emblem {{
  width:56px; height:56px; flex-shrink:0; background:linear-gradient(135deg,{accent},{accent_hi});
  border-radius:16px; display:flex; align-items:center; justify-content:center; font-size:1.75rem;
  box-shadow:0 12px 30px {accent_soft}; position:relative; z-index:1;
}}
.rok-header-title {{ font-size:1.55rem; font-weight:900; color:{text}; letter-spacing:-.045em; line-height:1; position:relative; z-index:1; }}
.rok-header-sub {{ font-size:.72rem; color:{text_dim}; letter-spacing:.08em; margin-top:6px; text-transform:uppercase; position:relative; z-index:1; }}
.rok-header-right {{ margin-left:auto; display:flex; gap:6px; flex-wrap:wrap; align-items:center; }}

/* ─── GLOBAL LABELS / PILLS ─────────────────────────────── */
.tier-pills {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }}
.tier-pill {{
  padding:5px 11px; border-radius:999px; font-size:.66rem; font-weight:800; letter-spacing:.055em;
  text-transform:uppercase; white-space:nowrap; border:1px solid; background:{surface}; box-shadow:{shadow_sm};
}}
.tp-t5 {{ color:{accent_hi}; border-color:rgba(245,158,11,.34); background:{accent_soft}; }}
.tp-t4 {{ color:{accent}; border-color:rgba(217,119,6,.30); background:{accent_soft}; }}
.tp-t3 {{ color:{purple}; border-color:rgba(167,139,250,.28); background:rgba(167,139,250,.10); }}
.tp-t2 {{ color:{blue}; border-color:rgba(56,189,248,.28); background:rgba(56,189,248,.10); }}
.tp-t1 {{ color:{text_dim}; border-color:{border}; background:{surface2}; }}
.tp-eq {{ color:{text_sub}; border-color:{border_hi}; background:{surface}; }}
.sec-label {{
  font-size:.62rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; color:{text_dim};
  display:flex; align-items:center; gap:12px; margin:22px 0 12px;
}}
.sec-label::after {{ content:''; flex:1; height:1px; background:linear-gradient(90deg,{border},transparent); }}
.page-hint {{ font-size:.66rem; color:{text_dim}; padding-top:8px; }}

/* ─── STAT / BADGE / CARD COMPONENTS ────────────────────── */
.stat-box, .kd-card, .sm-card, .mrow, .att-row, .upload-lock {{
  background:{surface}; border:1px solid {border}; box-shadow:{shadow_sm};
}}
.stat-box {{ border-radius:14px; padding:17px 18px; position:relative; overflow:hidden; height:100%; }}
.stat-box-label, .kd-card-label, .sm-label, .mdet-block-label {{
  font-size:.60rem; font-weight:900; text-transform:uppercase; letter-spacing:.12em; color:{text_dim};
}}
.stat-box-value, .kd-card-value, .sm-count, .mdet-block-val {{
  font-family:'JetBrains Mono', monospace; font-weight:700; color:{text}; letter-spacing:-.045em; line-height:1;
}}
.stat-box-value {{ font-size:1.45rem; }}
.stat-box-sub, .kd-card-sub, .sm-pct, .mrow-meta, .mdet-block-sub, .mdet-gap {{ font-size:.67rem; color:{text_dim}; }}
.stat-box-bar {{ position:absolute; bottom:0; left:0; height:3px; background:linear-gradient(90deg,{accent},transparent); }}
.sbadge {{
  display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px;
  font-size:.64rem; font-weight:900; letter-spacing:.045em; text-transform:uppercase; white-space:nowrap; border:1px solid;
}}
.sbadge-ok {{ color:{green}; border-color:{ok_br}; background:{ok_bg}; }}
.sbadge-wa {{ color:{yellow}; border-color:{wa_br}; background:{wa_bg}; }}
.sbadge-er {{ color:{red}; border-color:{er_br}; background:{er_bg}; }}

/* ─── MEMBER ROW ────────────────────────────────────────── */
.mrow {{ border-radius:14px; margin-bottom:8px; overflow:hidden; transition:border-color .2s, background .2s, transform .15s; }}
.mrow:hover {{ border-color:{border_hi}; background:{surface2}; transform:translateY(-1px); }}
.mrow.ok {{ border-left:4px solid {green}; }}
.mrow.wa {{ border-left:4px solid {yellow}; }}
.mrow.er {{ border-left:4px solid {red}; }}
.mrow-sum {{ display:grid; grid-template-columns:42px 1fr 110px 92px auto; align-items:center; gap:14px; padding:13px 16px; }}
.mrow-rank {{ font-family:'JetBrains Mono', monospace; font-size:.86rem; font-weight:700; color:{text_muted}; text-align:right; }}
.mrow-name {{ font-size:.91rem; font-weight:800; color:{text}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.mrow-kp {{ font-family:'JetBrains Mono', monospace; font-size:.92rem; font-weight:700; color:{accent}; text-align:right; white-space:nowrap; }}
.gauge-head {{ display:flex; justify-content:space-between; font-size:.59rem; color:{text_dim}; margin-bottom:3px; }}
.gauge-track {{ height:6px; background:{gauge_bg}; border-radius:999px; overflow:hidden; border:1px solid {gauge_bdr}; }}
.gauge-fill {{ height:100%; border-radius:999px; transition:width .6s cubic-bezier(.4,0,.2,1); }}
.gauge-fill.kp {{ background:linear-gradient(90deg,{accent},{accent_hi}); }}
.gauge-fill.dead {{ background:linear-gradient(90deg,{blue_dark},{blue}); }}
.gauge-fill.full {{ background:linear-gradient(90deg,{green},{green}); }}

/* detail panel */
.mdet {{ border-top:1px solid {border}; background:{surface2}; padding:17px 20px 20px; }}
.mdet-accent-bar {{ height:2px; margin-bottom:16px; border-radius:999px; }}
.mdet-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:16px; }}
.mdet-block-val {{ font-size:1.65rem; }}
.mdet-prog {{ margin-top:9px; }}
.mdet-prog-head {{ display:flex; justify-content:space-between; font-size:.62rem; color:{text_dim}; margin-bottom:4px; }}
.mdet-prog-track {{ height:9px; background:{gauge_bg}; border-radius:999px; overflow:hidden; }}
.mdet-prog-fill {{ height:100%; border-radius:999px; transition:width .6s cubic-bezier(.4,0,.2,1); }}
.mdet-prog-fill.kp {{ background:linear-gradient(90deg,{accent},{accent_hi}); }}
.mdet-prog-fill.dead {{ background:linear-gradient(90deg,{blue_dark},{blue}); }}
.mdet-prog-fill.full-kp, .mdet-prog-fill.full-dead {{ background:linear-gradient(90deg,{green},{green}); }}
.mdet-gap.warn {{ color:{red}; }}
.mdet-gap.ok {{ color:{green}; }}

/* tables */
.tier-table, .band-table {{ width:100%; border-collapse:collapse; }}
.tier-table th, .band-table th {{
  font-size:.59rem; font-weight:900; text-transform:uppercase; letter-spacing:.10em; color:{table_header};
  padding:7px 9px; text-align:right; border-bottom:1px solid {border};
}}
.tier-table th:first-child, .band-table th:first-child {{ text-align:left; }}
.tier-table td, .band-table td {{
  font-family:'JetBrains Mono', monospace; font-size:.76rem; color:{table_cell}; padding:7px 9px;
  text-align:right; border-bottom:1px solid {border};
}}
.tier-table td:first-child, .band-table td:first-child {{ text-align:left; color:{table_dim}; font-weight:800; }}
.band-table td:first-child {{ font-family:'Inter', sans-serif; font-size:.80rem; }}
.tier-table tr:last-child td, .band-table tr:last-child td {{ border-bottom:none; }}
.tier-table td.amber {{ color:{accent}; }}
.tier-table td.blue {{ color:{blue}; }}
.tier-table td.equiv {{ color:{text_dim}; font-size:.69rem; }}

/* ─── KINGDOM AREA ──────────────────────────────────────── */
.kd-row {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:20px; }}
.kd-card {{ border-radius:16px; padding:17px 18px; position:relative; overflow:hidden; }}
.kd-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; }}
.kd-card.amber::before {{ background:linear-gradient(90deg,{accent},transparent); }}
.kd-card.green::before {{ background:linear-gradient(90deg,{green},transparent); }}
.kd-card.yellow::before {{ background:linear-gradient(90deg,{yellow},transparent); }}
.kd-card.red::before {{ background:linear-gradient(90deg,{red},transparent); }}
.kd-card.blue::before {{ background:linear-gradient(90deg,{blue},transparent); }}
.kd-card-icon {{ font-size:1.25rem; margin-bottom:9px; opacity:.84; }}
.kd-card-value {{ font-size:1.48rem; }}
.sm-card {{ border-radius:16px; padding:17px 18px; }}
.sm-count {{ font-size:2.05rem; }}
.sm-denom {{ font-size:1rem; color:{text_muted}; }}
.sm-bar {{ background:{gauge_bg}; border-radius:999px; height:7px; overflow:hidden; margin-top:11px; }}
.sm-fill {{ height:100%; border-radius:999px; }}
.att-row {{ display:flex; align-items:center; gap:12px; padding:11px 14px; border-radius:12px; margin-bottom:7px; }}
.att-row.er {{ border-left:4px solid {red}; }}
.att-row.wa {{ border-left:4px solid {yellow}; }}
.att-name {{ flex:1; font-size:.84rem; font-weight:800; color:{text}; }}
.att-pow, .att-pcts {{ font-size:.68rem; color:{text_dim}; white-space:nowrap; }}

/* ─── SIDEBAR / STATES / CAPTION ────────────────────────── */
.upload-lock {{ border-radius:12px; padding:15px; text-align:center; margin-bottom:10px; background:{surface2}; }}
.upload-lock-icon {{ font-size:1.35rem; margin-bottom:6px; }}
.upload-lock-text {{ font-size:.74rem; color:{text_dim}; margin-bottom:10px; }}
.sb-sec {{
  font-size:.59rem; font-weight:900; text-transform:uppercase; letter-spacing:.14em; color:{sidebar_dim};
  border-bottom:1px solid {sidebar_border}; padding-bottom:7px; margin:15px 0 10px;
}}
.rok-caption {{
  display:flex; align-items:center; gap:14px; padding:10px 14px; margin-bottom:18px;
  background:{surface}; border:1px solid {border}; border-radius:12px; flex-wrap:wrap; box-shadow:{shadow_sm};
}}
.rok-caption-item {{ font-size:.70rem; color:{text_dim}; }}
.rok-caption-val {{ color:{accent}; font-weight:900; }}
.rok-caption-sep {{ color:{text_muted}; font-size:.72rem; }}
.empty-state {{ text-align:center; padding:64px 20px; }}
.empty-state-icon {{ font-size:3rem; margin-bottom:14px; opacity:.45; }}
.empty-state-title {{ font-size:1.05rem; font-weight:800; color:{text_sub}; margin-bottom:6px; }}
.empty-state-sub {{ font-size:.78rem; color:{text_dim}; }}

@media (max-width: 1100px) {{
  .kd-row {{ grid-template-columns:repeat(2,1fr); }}
  .mrow-sum {{ grid-template-columns:34px 1fr; }}
  .mrow-gauges, .mrow-kp, .mrow-sum > div:last-child {{ grid-column:2; }}
  .mdet-grid {{ grid-template-columns:1fr; }}
}}
</style>
"""

# ══════════════════════════════════════════════════════════════════════════════
# Storage / State
# ══════════════════════════════════════════════════════════════════════════════

STATUS_CLS   = {"Aprovado":"ok","Pendente":"wa","Abaixo da meta":"er"}
STATUS_ICON  = {"Aprovado":"●","Pendente":"◐","Abaixo da meta":"○"}
STATUS_LABEL = {"Aprovado":"Aprovado","Pendente":"Pendente","Abaixo da meta":"Abaixo"}

@st.cache_resource
def get_storage():
    return create_storage()

def get_secret(name):
    v = os.getenv(name)
    if v: return v
    try: v = st.secrets.get(name)
    except: v = None
    return str(v) if v else None

def inject_css(dark: bool) -> None:
    """Injeta o CSS do app sem deixar o código aparecer como texto na tela."""
    css = _css(dark).strip()

    # Streamlit mais novo: melhor forma para HTML/CSS puro.
    if hasattr(st, "html"):
        st.html(css)
    else:
        # Compatibilidade com versões antigas do Streamlit.
        st.markdown(css, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # ── Theme state ──────────────────────────────────────────────────────────
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = True
    dark = st.session_state.dark_mode

    # inject CSS before anything renders
    inject_css(dark)

    storage = get_storage()

    # ── Header with theme toggle ─────────────────────────────────────────────
    moon_sun = "☀️ Claro" if dark else "🌙 Escuro"
    h1, h2 = st.columns([6, 1])
    with h1:
        st.markdown("""
        <div class="rok-header">
          <div class="rok-header-emblem">⚔️</div>
          <div>
            <div class="rok-header-title">K1602 · KP Dashboard</div>
            <div class="rok-header-sub">Kill Points Operations Center · Rise of Kingdoms</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with h2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(moon_sun, key="theme_toggle", use_container_width=True):
            st.session_state.dark_mode = not dark
            st.rerun()

    st.markdown("""
    <div class="tier-pills">
      <span class="tier-pill tp-t5">T5 ×20</span>
      <span class="tier-pill tp-t4">T4 ×10</span>
      <span class="tier-pill tp-t3">T3 ×4</span>
      <span class="tier-pill tp-t2">T2 ×2</span>
      <span class="tier-pill tp-t1">T1 ×0.2</span>
      <span class="tier-pill tp-eq">1 morte T5 = 2 T4</span>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown(f'<div class="sb-sec">Sistema</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sidebar-storage">Storage: <span>{storage.label}</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sec">Relatórios</div>', unsafe_allow_html=True)
        handle_upload(storage)

    imports = storage.list_imports()
    if imports.empty:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-state-icon">⚔️</div>
          <div class="empty-state-title">Nenhum relatório importado</div>
          <div class="empty-state-sub">Faça upload do statsExport na barra lateral para começar.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    imports  = prepare_imports(imports)
    selected = select_report(imports)
    current  = storage.load_stats(selected["id"])
    previous = load_previous_report(storage, imports, selected)

    basis_options = ["Totais do relatório"]
    if previous is not None and not previous.empty:
        basis_options.insert(0, "Delta do período")

    with st.sidebar:
        st.markdown('<div class="sb-sec">Configuração</div>', unsafe_allow_html=True)
        basis     = st.radio("Base das métricas", basis_options, index=0)
        min_power = st.number_input("Power mínimo", min_value=0, value=0, step=1_000_000, format="%d")
        st.markdown('<div class="sb-sec">Admin</div>', unsafe_allow_html=True)
        admin_enabled, is_admin = admin_panel()

    stats_basis = compute_period_deltas(current, previous) if basis == "Delta do período" else current
    gp          = default_group_power(storage, imports)
    metrics_raw = calculate_metrics(stats_basis, group_power=gp)
    if min_power > 0:
        metrics_raw = metrics_raw[pd.to_numeric(metrics_raw["power"],errors="coerce").fillna(0) >= min_power]

    ranked = apply_goals(add_rank(metrics_raw, "kill_points"))

    # Caption bar
    n  = len(imports)
    dl = f"+{n-1} relat." if n > 1 else "1 relat."
    st.markdown(f"""
    <div class="rok-caption">
      <div class="rok-caption-item">Data <span class="rok-caption-val">{selected['report_date']}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Base <span class="rok-caption-val">{basis}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Membros <span class="rok-caption-val">{len(ranked):,}</span></div>
      <div class="rok-caption-sep">·</div>
      <div class="rok-caption-item">Imports <span class="rok-caption-val">{dl}</span></div>
    </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs(["⚔ Ranking", "🏰 Reino", "📈 Histórico", "📁 Imports", "❓ Ajuda"])
    with tabs[0]: show_ranking(ranked)
    with tabs[1]: show_kingdom(ranked, imports, storage, gp)
    with tabs[2]: show_history(storage, imports, gp)
    with tabs[3]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[4]: show_help()


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar helpers  (idênticos ao original)
# ══════════════════════════════════════════════════════════════════════════════

def handle_upload(storage):
    pwd = get_secret("ADMIN_PASSWORD")
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.markdown("""
        <div class="upload-lock">
          <div class="upload-lock-icon">🔒</div>
          <div class="upload-lock-text">Upload restrito à liderança</div>
        </div>
        """, unsafe_allow_html=True)
        up_pwd = st.text_input("Senha", type="password", key="up_pwd", label_visibility="collapsed", placeholder="Senha de acesso...")
        if st.button("Desbloquear", use_container_width=True):
            if (not pwd) or is_admin_authenticated(pwd, up_pwd):
                st.session_state.upload_auth = True; st.rerun()
            else:
                st.error("Senha incorreta")
        return

    st.success("✓ Acesso liberado")
    if st.button("Bloquear", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False; st.rerun()

    uploaded = st.file_uploader("statsExport (.xlsx)", type=["xlsx","xls"])
    if not uploaded: return
    safe_name   = re.sub(r"[^\w.\-]","_", uploaded.name)
    report_date = st.date_input("Data do relatório", value=extract_report_date_from_name(safe_name) or date.today())
    if not st.button("Salvar relatório", type="primary", use_container_width=True): return

    with st.spinner("Processando..."):
        try:
            fb = uploaded.getvalue()
            if len(fb) > 50*1024*1024: st.error("Arquivo muito grande (max 50 MB)."); return
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            _, created = storage.save_import(filename=safe_name, report_date=report_date.isoformat(),
                                              file_hash=file_sha256(fb), stats=stats)
        except Exception as e: st.error(f"Erro: {e}"); return
    if created: st.success(f"✓ {len(stats):,} membros salvos")
    else: st.warning("Arquivo já importado")
    st.rerun()


def prepare_imports(imports):
    out = imports.copy()
    out["report_date"] = pd.to_datetime(out["report_date"]).dt.date.astype(str)
    out["imported_at"] = out["imported_at"].astype(str)
    out["label"]       = out["report_date"] + " — " + out["filename"].astype(str)
    return out

def select_report(imports):
    labels = imports["label"].tolist()
    chosen = st.sidebar.selectbox("Relatório", labels, index=0)
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
        st.caption("Configure ADMIN_PASSWORD nos Secrets.")
        return False, False
    entered = st.text_input("Senha admin", type="password", key="adm_pwd", label_visibility="collapsed", placeholder="Senha admin...")
    if is_admin_authenticated(pwd, entered):
        st.success("✓ Admin ativo"); return True, True
    if entered: st.error("Incorreta")
    return True, False


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Ranking  (idêntico ao original)
# ══════════════════════════════════════════════════════════════════════════════

def show_ranking(ranked_full: pd.DataFrame) -> None:
    fc1, fc2, fc3 = st.columns([5, 2, 2])
    with fc1:
        search = st.text_input("search", placeholder="Buscar membro ou Character ID…",
                                key="rank_search", label_visibility="collapsed")
    with fc2:
        sf = st.selectbox("status", ["Todos","Aprovado","Pendente","Abaixo da meta"],
                          key="rank_sf", label_visibility="collapsed")
    with fc3:
        sort_by = st.selectbox("sort",
                               ["KP ↓","Power ↓","% KP ↓","% Mortes ↓","Nome ↑"],
                               key="rank_sort", label_visibility="collapsed")

    with st.expander("Filtrar por data de importação", expanded=False):
        dc1, dc2, dc3 = st.columns([2,2,1])
        with dc1: date_from = st.date_input("De",  value=None, key="df_from")
        with dc2: date_to   = st.date_input("Até", value=None, key="df_to")
        with dc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Limpar", key="clr_dt"):
                st.session_state.df_from = None; st.session_state.df_to = None; st.rerun()

    df = ranked_full.copy()
    if search.strip():
        n = search.strip().lower()
        df = df[df["username"].astype(str).str.lower().str.contains(n,regex=False,na=False)
                |df["character_id"].astype(str).str.lower().str.contains(n,regex=False,na=False)]
    if sf != "Todos":
        df = df[df["status"] == sf]
    if "imported_at" in df.columns and (date_from or date_to):
        df["_dt"] = pd.to_datetime(df["imported_at"],errors="coerce").dt.date
        if date_from: df = df[df["_dt"] >= date_from]
        if date_to:   df = df[df["_dt"] <= date_to]
        df = df.drop(columns=["_dt"])

    sort_map = {
        "KP ↓":("kill_points",False),"Power ↓":("power",False),
        "% KP ↓":("kp_pct",False),"% Mortes ↓":("dead_pct",False),"Nome ↑":("username",True),
    }
    scol, sasc = sort_map.get(sort_by, ("kill_points",False))
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    st.markdown(f'<div class="sec-label">Governors · {len(df):,} de {len(ranked_full):,}</div>',
                unsafe_allow_html=True)

    page_size = st.selectbox("Por página",[25,50,100],index=0,key="rank_ps",label_visibility="collapsed")
    total_pg  = max(1,-(-len(df)//page_size))
    col_pg1, col_pg2 = st.columns([1,5])
    with col_pg1:
        page = st.number_input("Página",min_value=1,max_value=total_pg,value=1,key="rank_pg",label_visibility="collapsed")
    with col_pg2:
        st.markdown(f'<div class="page-hint">Página {page} de {total_pg}</div>', unsafe_allow_html=True)

    start = (page-1)*page_size
    _render_members(df.iloc[start:start+page_size])

    with st.expander("Exportar tabela completa →", expanded=False):
        cols_show = {
            "rank":"#","username":"Governor","character_id":"ID","power":"Power","power_band":"Faixa",
            "kill_points":"KP","kp_goal":"Meta KP","t5_kills":"T5K","t4_kills":"T4K",
            "t3_kills":"T3K","t2_kills":"T2K","t1_kills":"T1K",
            "t5_deaths":"T5D","t4_deaths":"T4D","t3_deaths":"T3D","t2_deaths":"T2D","t1_deaths":"T1D",
            "dead_t4_goal":"Meta D.","dead_equiv":"Equiv. T4","status":"Status",
        }
        avail = {k:v for k,v in cols_show.items() if k in df.columns}
        out   = df[list(avail.keys())].rename(columns=avail)
        st.dataframe(out, use_container_width=True, hide_index=True)
        st.download_button("⬇ Baixar CSV", data=df.to_csv(index=False).encode(), file_name="ranking.csv", mime="text/csv")


def _render_members(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
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

        with st.expander(f"↳ detalhes · {row['username']}", expanded=False):
            t5d = int(row.get("t5_deaths",0)); t4d = int(row.get("t4_deaths",0))
            t3d = int(row.get("t3_deaths",0)); t2d = int(row.get("t2_deaths",0)); t1d = int(row.get("t1_deaths",0))
            dead_equiv = int(row.get("dead_equiv",0))
            kp_fc_det   = "full-kp"   if kp_w   >= 100 else "kp"
            dead_fc_det = "full-dead" if dead_w >= 100 else "dead"
            kp_gap_html   = (f'<div class="mdet-gap ok">✓ Meta de KP atingida</div>'
                             if kp_gap == 0
                             else f'<div class="mdet-gap warn">⚠ Faltam {fmt_k(kp_gap)} KP</div>')
            dead_gap_html = (f'<div class="mdet-gap ok">✓ Meta de mortes atingida</div>'
                             if dead_gap == 0
                             else f'<div class="mdet-gap warn">⚠ Faltam {fmt_k(dead_gap)} T4eq</div>')

            st.markdown(f"""
            <div class="mdet">
              <div class="mdet-accent-bar" style="background:{ui_tokens()['green'] if cls=='ok' else ui_tokens()['yellow'] if cls=='wa' else ui_tokens()['red']}"></div>
              <div class="mdet-grid">
                <div>
                  <div class="mdet-block-label">Kill Points</div>
                  <div class="mdet-block-val">{fmt_int(int(row['kill_points']))}</div>
                  <div class="mdet-block-sub">Meta: {fmt_int(int(row['kp_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head">
                      <span>{kp_w:.1f}% atingido</span>
                      <span>{fmt_int(int(row['kill_points']))} / {fmt_int(int(row['kp_goal']))}</span>
                    </div>
                    <div class="mdet-prog-track">
                      <div class="mdet-prog-fill {kp_fc_det}" style="width:{kp_w:.1f}%"></div>
                    </div>
                  </div>
                  {kp_gap_html}
                </div>
                <div>
                  <div class="mdet-block-label">Mortes (equiv. T4)</div>
                  <div class="mdet-block-val">{fmt_int(dead_equiv)}</div>
                  <div class="mdet-block-sub">Meta: {fmt_int(int(row['dead_t4_goal']))}</div>
                  <div class="mdet-prog">
                    <div class="mdet-prog-head">
                      <span>{dead_w:.1f}% atingido</span>
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
                t5k=int(row.get("t5_kills",0)); t4k=int(row.get("t4_kills",0))
                t3k=int(row.get("t3_kills",0)); t2k=int(row.get("t2_kills",0)); t1k=int(row.get("t1_kills",0))
                st.markdown(f"""
                <div class="mdet-block-label" style="margin-top:0">Kills por Tier</div>
                <table class="tier-table">
                  <tr><th>Tier</th><th>Kills</th><th>KP gerado</th></tr>
                  <tr><td>T5</td><td class="amber">{fmt_k(t5k)}</td><td class="amber">{fmt_k(t5k*20)}</td></tr>
                  <tr><td>T4</td><td class="amber">{fmt_k(t4k)}</td><td class="amber">{fmt_k(t4k*10)}</td></tr>
                  <tr><td>T3</td><td>{fmt_k(t3k)}</td><td>{fmt_k(t3k*4)}</td></tr>
                  <tr><td>T2</td><td>{fmt_k(t2k)}</td><td>{fmt_k(t2k*2)}</td></tr>
                  <tr><td>T1</td><td>{fmt_k(t1k)}</td><td>{fmt_k(int(t1k*.2))}</td></tr>
                </table>
                """, unsafe_allow_html=True)
            with dc2:
                st.markdown(f"""
                <div class="mdet-block-label" style="margin-top:0">Mortes por Tier</div>
                <table class="tier-table">
                  <tr><th>Tier</th><th>Mortes</th><th>Equiv. T4</th></tr>
                  <tr><td>T5</td><td class="blue">{fmt_k(t5d)}</td><td class="equiv">≡ {fmt_k(t5d*2)}</td></tr>
                  <tr><td>T4</td><td class="blue">{fmt_k(t4d)}</td><td class="equiv">≡ {fmt_k(t4d)}</td></tr>
                  <tr><td>T3</td><td>{fmt_k(t3d)}</td><td class="equiv">—</td></tr>
                  <tr><td>T2</td><td>{fmt_k(t2d)}</td><td class="equiv">—</td></tr>
                  <tr><td>T1</td><td>{fmt_k(t1d)}</td><td class="equiv">—</td></tr>
                </table>
                <div style="font-size:.62rem;color:#4a4438;margin-top:8px">
                  Total equiv: <span style="font-family:monospace">{fmt_int(dead_equiv)}</span>
                  / Meta: <span style="font-family:monospace">{fmt_int(int(row['dead_t4_goal']))}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Reino  (idêntico ao original)
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
      <div class="kd-card amber">
        <div class="kd-card-icon">⚔️</div>
        <div class="kd-card-label">Total Kill Points</div>
        <div class="kd-card-value">{fmt_k(kp_total)}</div>
        <div class="kd-card-sub">pontos acumulados</div>
      </div>
      <div class="kd-card blue">
        <div class="kd-card-icon">🏰</div>
        <div class="kd-card-label">Power Total</div>
        <div class="kd-card-value">{fmt_m(power_total)}M</div>
        <div class="kd-card-sub">city power somado</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-icon">👥</div>
        <div class="kd-card-label">Governadores</div>
        <div class="kd-card-value">{total:,}</div>
        <div class="kd-card-sub">{active} ativos no período</div>
      </div>
      <div class="kd-card green">
        <div class="kd-card-icon">✅</div>
        <div class="kd-card-label">Taxa de Aprovação</div>
        <div class="kd-card-value">{aprov_pct:.1f}%</div>
        <div class="kd-card-sub">{approved} de {total} membros</div>
      </div>
      <div class="kd-card red">
        <div class="kd-card-icon">⚠️</div>
        <div class="kd-card-label">Abaixo da Meta</div>
        <div class="kd-card-value">{below}</div>
        <div class="kd-card-sub">{pending} pendentes</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Status das metas</div>', unsafe_allow_html=True)
    theme = ui_tokens()
    m1, m2, m3 = st.columns(3)
    for col, lbl, count, color in [
        (m1,"Aprovados",  approved, theme["green"]),
        (m2,"Pendentes",  pending, theme["yellow"]),
        (m3,"Abaixo da meta", below, theme["red"]),
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
              <div class="sm-pct">{pct:.1f}% da aliança</div>
            </div>
            """, unsafe_allow_html=True)

    if px is not None:
        st.markdown('<div class="sec-label">Distribuição de Kill Points</div>', unsafe_allow_html=True)
        g1, g2 = st.columns([3,2])
        cmap = {"Aprovado": theme["green"], "Pendente": theme["yellow"], "Abaixo da meta": theme["red"]}

        with g1:
            top20 = ranked.sort_values("kill_points",ascending=True).tail(20)
            fig = px.bar(top20, x="kill_points", y="username", orientation="h",
                         color="status", color_discrete_map=cmap,
                         labels={"kill_points":"Kill Points","username":""})
            fig.update_layout(showlegend=False, margin=dict(t=10,b=0,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=theme["plot_axis"], family="Inter"),
                yaxis=dict(tickfont=dict(size=11, color=theme["plot_axis"]), gridcolor=theme["plot_grid"]),
                xaxis=dict(tickfont=dict(size=10, color=theme["plot_axis"]), gridcolor=theme["plot_grid"]))
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with g2:
            fig2 = px.pie(values=[approved,pending,below],
                names=["Aprovado","Pendente","Abaixo da meta"],
                hole=0.65, color_discrete_sequence=[theme["green"], theme["yellow"], theme["red"]])
            fig2.update_traces(textposition="inside",textinfo="percent",textfont_size=11,
                               marker=dict(line=dict(color=theme["pie_line"], width=2)))
            fig2.update_layout(showlegend=True,margin=dict(t=10,b=0,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=theme["plot_axis"], family="Inter"),
                legend=dict(orientation="h", y=-0.08, font=dict(size=10, color=theme["plot_axis"])))
            st.plotly_chart(fig2, use_container_width=True)

    if len(imports) >= 2:
        st.markdown('<div class="sec-label">Evolução histórica</div>', unsafe_allow_html=True)
        ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
        hist_rows = []
        with st.spinner("Carregando..."):
            for _, imp in ordered.iterrows():
                s  = storage.load_stats(imp["id"])
                m  = calculate_metrics(s, group_power=group_power)
                gm = apply_goals(m)
                hist_rows.append({"Data":imp["report_date"],"KP":int(m["kill_points"].sum()),
                    "Aprovados":int((gm["status"]=="Aprovado").sum()),
                    "Pendentes":int((gm["status"]=="Pendente").sum()),
                    "Abaixo":int((gm["status"]=="Abaixo da meta").sum())})
        hist = pd.DataFrame(hist_rows)
        if px is not None and len(hist) >= 2:
            hc1, hc2 = st.columns(2)
            plot_cfg = dict(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=theme["plot_axis"], family="Inter"), margin=dict(t=10,b=0,l=0,r=0),
                xaxis=dict(gridcolor=theme["plot_grid"], tickfont=dict(color=theme["plot_axis"])),
                yaxis=dict(gridcolor=theme["plot_grid"], tickfont=dict(color=theme["plot_axis"])))
            with hc1:
                fig3 = px.line(hist, x="Data", y="KP", markers=True, color_discrete_sequence=[theme["accent"]])
                fig3.update_layout(**plot_cfg)
                fig3.update_traces(line_width=2,marker_size=6)
                st.plotly_chart(fig3,use_container_width=True)
            with hc2:
                melt = hist[["Data","Aprovados","Pendentes","Abaixo"]].melt(id_vars="Data",var_name="Status",value_name="N")
                fig4 = px.bar(melt,x="Data",y="N",color="Status",barmode="stack",
                    color_discrete_map={"Aprovados": theme["green"], "Pendentes": theme["yellow"], "Abaixo": theme["red"]})
                fig4.update_layout(**{**plot_cfg,"showlegend":True,
                    "legend":dict(orientation="h",y=-0.15,font=dict(size=10))})
                fig4.update_traces(marker_line_width=0)
                st.plotly_chart(fig4,use_container_width=True)

    st.markdown('<div class="sec-label">Faixas de power</div>', unsafe_allow_html=True)
    bands = []
    for pmin, pmax, dead_t4, _, kp in GOAL_TABLE:
        lbl = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax!=float("inf") else f"{pmin//1_000_000}M+"
        sub = ranked[ranked["power_band"]==lbl] if "power_band" in ranked else pd.DataFrame()
        if sub.empty: continue
        ok=int((sub["status"]=="Aprovado").sum()); wa=int((sub["status"]=="Pendente").sum()); er=int((sub["status"]=="Abaixo da meta").sum())
        bands.append({"Faixa":lbl,"Total":len(sub),"✅":ok,"🟡":wa,"❌":er,
                      "KP Total":fmt_k(int(sub["kill_points"].sum())),"Meta KP":fmt_k(kp)})
    if bands:
        st.markdown('<table class="band-table"><tr>'
                    '<th>Faixa</th><th>Total</th><th>✅</th><th>🟡</th><th>❌</th><th>KP Total</th><th>Meta KP</th>'
                    '</tr>' +
                    "".join(f'<tr><td>{b["Faixa"]}</td><td>{b["Total"]}</td>'
                            f'<td>{b["✅"]}</td><td>{b["🟡"]}</td><td>{b["❌"]}</td>'
                            f'<td>{b["KP Total"]}</td><td>{b["Meta KP"]}</td></tr>' for b in bands) +
                    '</table>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Precisam de atenção</div>', unsafe_allow_html=True)
    att = ranked[ranked["status"]!="Aprovado"].sort_values("kp_pct").head(8)
    if att.empty:
        st.success("Todos os membros estão aprovados!")
    else:
        for _, row in att.iterrows():
            cls  = STATUS_CLS.get(row["status"],"er")
            kp_p = min(float(row.get("kp_pct",0))*100,100)
            dp_p = min(float(row.get("dead_pct",0))*100,100)
            st.markdown(f"""
            <div class="att-row {cls}">
              <div class="att-name">{row['username']}</div>
              <div class="att-pow">{fmt_m(int(row['power']))}M</div>
              <div class="att-pcts">KP {kp_p:.0f}% · Mortes {dp_p:.0f}%</div>
              <div class="sbadge sbadge-{cls}">{STATUS_ICON.get(row['status'],'○')} {STATUS_LABEL.get(row['status'],'—')}</div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Histórico  (idêntico ao original)
# ══════════════════════════════════════════════════════════════════════════════

def show_history(storage, imports, group_power):
    st.markdown('<div class="sec-label">Comparar dois relatórios</div>', unsafe_allow_html=True)
    if len(imports) < 2:
        st.info("Importe pelo menos 2 relatórios para comparar."); return

    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    labels  = ordered["label"].tolist()
    ca, cb  = st.columns(2)
    with ca: la = st.selectbox("Base",      labels, index=0,                   key="ha")
    with cb: lb = st.selectbox("Comparado", labels, index=min(1,len(labels)-1),key="hb")
    if la == lb: st.warning("Selecione dois relatórios diferentes."); return

    id_a = ordered.loc[ordered["label"].eq(la),"id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
    delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
    met   = calculate_metrics(delta, group_power=group_power)
    top   = met.sort_values("kill_points",ascending=False).head(15)

    if not top.empty and px is not None:
        theme = ui_tokens()
        fig = px.bar(top.sort_values("kill_points",ascending=True),
                     x="kill_points",y="username",orientation="h",
                     color_discrete_sequence=[theme["accent"]],
                     labels={"kill_points":"Kill Points Ganhos","username":""})
        fig.update_layout(showlegend=False,margin=dict(t=10,b=0,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=theme["plot_axis"], family="Inter"),
            yaxis=dict(tickfont=dict(size=11, color=theme["plot_axis"]), gridcolor=theme["plot_grid"]),
            xaxis=dict(tickfont=dict(color=theme["plot_axis"]), gridcolor=theme["plot_grid"]))
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig,use_container_width=True)

    st.dataframe(
        met[["username","power","kill_points","t5_kills","t4_kills","t3_kills","t2_kills","t1_kills"]]
           .sort_values("kill_points",ascending=False)
           .rename(columns={"username":"Governor","power":"Power","kill_points":"KP",
                             "t5_kills":"T5","t4_kills":"T4","t3_kills":"T3","t2_kills":"T2","t1_kills":"T1"}),
        use_container_width=True,hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Imports  (idêntico ao original)
# ══════════════════════════════════════════════════════════════════════════════

def show_imports(imports, storage, *, is_admin, admin_enabled):
    st.markdown('<div class="sec-label">Relatórios importados</div>', unsafe_allow_html=True)
    st.dataframe(
        imports[["report_date","filename","row_count","imported_at"]].rename(columns={
            "report_date":"Data","filename":"Arquivo","row_count":"Membros","imported_at":"Importado em"}),
        use_container_width=True,hide_index=True)

    if admin_enabled and is_admin:
        st.markdown('<div class="sec-label">Deletar import</div>', unsafe_allow_html=True)
        st.warning("Irreversível — remove todos os dados associados.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Selecionar",["— —",*labels])
        if to_del != "— —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            if st.button("Confirmar exclusão",type="secondary"):
                if storage.delete_import(row["id"]):
                    st.success("Deletado."); st.rerun()
                else: st.error("Não encontrado.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Ajuda  (idêntico ao original)
# ══════════════════════════════════════════════════════════════════════════════

def show_help():
    st.markdown('<div class="sec-label">Referência rápida</div>', unsafe_allow_html=True)
    st.markdown("""
**Fórmula de Kill Points:** `KP = T5×20 + T4×10 + T3×4 + T2×2 + T1×0.2`

**Equivalência de mortes:** 1 morte T5 = 2 mortes T4.
O sistema converte automaticamente: `equiv = (T5deaths × 2) + T4deaths`

**Status:**
- ✅ Aprovado — atingiu KP e mortes
- 🟡 Pendente — ≥75% em ambas as metas
- ❌ Abaixo da meta — <75% em alguma meta
""")

    st.markdown('<div class="sec-label">Tabela de metas</div>', unsafe_allow_html=True)
    st.markdown("""
| City Power | Meta Mortes | Meta KP |
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
# Formatters  (idênticos ao original)
# ══════════════════════════════════════════════════════════════════════════════

def fmt_int(v) -> str: return f"{int(v):,}"
def fmt_k(v: int) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}k"
    return str(v)
def fmt_m(v: int) -> str: return f"{v/1_000_000:.0f}"

if __name__ == "__main__":
    main()
