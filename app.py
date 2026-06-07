from __future__ import annotations

import os
import re
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from goal_metrics import (
    calculate_member_goals,
    calculate_goal_progress,
    default_goal_bands,
    summarize_goal_bands,
    POWER_GOAL_BANDS,
)
from rok_metrics import (
    POINT_WEIGHTS,
    add_rank,
    calculate_metrics,
    compute_period_deltas,
    extract_report_date_from_name,
    file_sha256,
    load_stats_file,
)
from security import is_admin_authenticated
from storage import create_storage

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:
    px = None
    go = None

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
THEME_GOLD   = "#f59e0b"
THEME_ORANGE = "#ea580c"
THEME_RED    = "#ef4444"
THEME_GREEN  = "#22c55e"
THEME_BLUE   = "#3b82f6"
THEME_PURPLE = "#8b5cf6"
THEME_YELLOW = "#eab308"

STATUS_COLOR = {
    "Aprovado":       "#22c55e",
    "Pendente":       "#eab308",
    "Abaixo da meta": "#ef4444",
}
STATUS_ICON = {
    "Aprovado":       "✅",
    "Pendente":       "⚠️",
    "Abaixo da meta": "❌",
}
TIER_COLORS = {
    "T5": "#f59e0b",
    "T4": "#ea580c",
    "T3": "#8b5cf6",
    "T2": "#3b82f6",
    "T1": "#64748b",
}

# ─────────────────────────────────────────────────────────────────────────────
# Page config & CSS
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── Base ── */
html, body, [class*="css"] { font-family: 'Segoe UI', system-ui, sans-serif; }
.main .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#0a1628 0%,#0f1f3a 100%) !important;
    border-right: 1px solid #1e3a5f;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg,#1e293b 0%,#162032 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px 18px !important;
    position: relative; overflow: hidden;
    transition: border-color .2s;
}
[data-testid="stMetric"]:hover { border-color: #f59e0b55; }
[data-testid="stMetric"]::before {
    content:''; position:absolute; top:0; left:0; right:0; height:3px;
    background: linear-gradient(90deg,#f59e0b,#ea580c);
}
[data-testid="stMetricLabel"] { color:#94a3b8!important; font-size:.72rem!important; text-transform:uppercase; letter-spacing:.1em; font-weight:600; }
[data-testid="stMetricValue"] { color:#f1f5f9!important; font-size:1.45rem!important; font-weight:800; letter-spacing:-.02em; }

/* ── Tabs ── */
[data-testid="stTabs"] button { font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; color:#64748b!important; }
[data-testid="stTabs"] button[aria-selected="true"] { color:#f59e0b!important; border-bottom-color:#f59e0b!important; }

/* ── DataFrames ── */
[data-testid="stDataFrame"] { border:1px solid #1e3a5f; border-radius:10px; overflow:hidden; }

/* ── Dividers ── */
hr { border-color:#1e3a5f!important; margin:1.2rem 0!important; }

/* ── Title banner ── */
.title-banner {
    background: linear-gradient(135deg,#1a2744 0%,#0f172a 100%);
    border:1px solid #1e3a5f; border-left:4px solid #f59e0b;
    border-radius:10px; padding:14px 22px; margin-bottom:1.2rem;
    display:flex; align-items:center; gap:14px;
}
.title-banner h1 { margin:0; font-size:1.4rem; font-weight:800; color:#f1f5f9; }
.title-banner p  { margin:3px 0 0; font-size:.75rem; color:#94a3b8; }

/* ── Section headers ── */
.section-header {
    font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.1em;
    color:#64748b; border-bottom:1px solid #1e3a5f; padding-bottom:5px; margin-bottom:10px;
}

/* ── Member ranking cards ── */
.member-card {
    background: linear-gradient(135deg,#1e293b,#162032);
    border:1px solid #334155; border-radius:12px;
    padding:14px 16px; margin-bottom:10px;
    position:relative; overflow:hidden;
    transition: border-color .2s, transform .1s;
}
.member-card:hover { transform: translateY(-1px); }
.member-card.aprovado  { border-left:4px solid #22c55e; }
.member-card.pendente  { border-left:4px solid #eab308; }
.member-card.abaixo    { border-left:4px solid #ef4444; }

.member-rank   { font-size:.7rem; color:#64748b; font-weight:700; text-transform:uppercase; }
.member-name   { font-size:1.05rem; font-weight:800; color:#f1f5f9; margin:2px 0 4px; }
.member-power  { font-size:.78rem; color:#94a3b8; }
.member-badge  {
    display:inline-block; padding:3px 10px; border-radius:20px;
    font-size:.68rem; font-weight:700; letter-spacing:.05em;
}
.badge-aprovado  { background:#22c55e22; color:#22c55e; border:1px solid #22c55e55; }
.badge-pendente  { background:#eab30822; color:#eab308; border:1px solid #eab30855; }
.badge-abaixo    { background:#ef444422; color:#ef4444; border:1px solid #ef444455; }

.stat-grid { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
.stat-pill {
    background:#0f172a; border:1px solid #334155; border-radius:6px;
    padding:4px 9px; font-size:.65rem; font-weight:600; color:#94a3b8;
    white-space:nowrap;
}
.stat-pill span { font-weight:800; }

.progress-bar-bg {
    background:#1e293b; border-radius:4px; height:6px;
    margin:4px 0; overflow:hidden; border:1px solid #334155;
}
.progress-bar-fill { height:100%; border-radius:4px; transition:width .4s; }

/* ── Unlock box ── */
.unlock-box {
    background:linear-gradient(135deg,#1a2744,#0f172a);
    border:1px solid #1e3a5f; border-radius:12px;
    padding:22px; text-align:center; margin:10px 0;
}

/* ── Summary tiles ── */
.summary-tile {
    background:linear-gradient(135deg,#1e293b,#162032);
    border:1px solid #334155; border-radius:10px;
    padding:14px 16px; text-align:center;
}
.summary-tile .stile-num { font-size:1.6rem; font-weight:800; }
.summary-tile .stile-lbl { font-size:.68rem; color:#94a3b8; font-weight:600; text-transform:uppercase; letter-spacing:.08em; margin-top:2px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_storage():
    return create_storage()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    storage = get_storage()

    st.markdown("""
    <div class="title-banner">
        <div style="font-size:2rem">⚔️</div>
        <div>
            <h1>K1602 · KP Dashboard</h1>
            <p>Kingdom Kill Points Tracker — Rise of Kingdoms</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:6px 0 14px">
            <div style="font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:#475569;font-weight:700">Storage</div>
            <div style="color:#f59e0b;font-size:.82rem;font-weight:600">🟢 {storage.label}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-header">📂 Relatórios</div>', unsafe_allow_html=True)
        handle_upload(storage)

    imports = storage.list_imports()
    if imports.empty:
        _empty_state()
        return

    imports = prepare_imports(imports)
    selected = select_report(imports)
    current  = storage.load_stats(selected["id"])
    previous = load_previous_report(storage, imports, selected)

    basis_options = ["Totais do relatório"]
    if previous is not None and not previous.empty:
        basis_options.insert(0, "Delta do período")

    with st.sidebar:
        st.divider()
        st.markdown('<div class="section-header">⚙️ Filtros</div>', unsafe_allow_html=True)
        basis      = st.radio("Base das métricas", basis_options, index=0)
        search     = st.text_input("🔍 Buscar membro")
        min_power  = st.number_input("Power mínimo", min_value=0, value=0, step=1_000_000, format="%d")
        filter_status = st.selectbox("Filtrar por status", ["Todos", "Aprovado", "Pendente", "Abaixo da meta"])

    stats_basis = compute_period_deltas(current, previous) if basis == "Delta do período" else current
    filtered    = apply_filters(stats_basis, search=search, min_power=min_power)

    gp_default = default_group_power(storage, imports)
    with st.sidebar:
        st.divider()
        st.markdown('<div class="section-header">📊 Config</div>', unsafe_allow_html=True)
        group_power = st.number_input(
            "Power inicial do grupo",
            min_value=1, value=max(1, int(gp_default)),
            step=1_000_000, format="%d",
        )
        st.divider()
        admin_enabled, is_admin = admin_panel()

  metrics = calculate_metrics(filtered, group_power=group_power)

# Merge das colunas de mortes do stats bruto para o goals
death_cols = ["character_id", "t5_deaths", "t4_deaths", "t3_deaths", "t2_deaths", "t1_deaths"]
deaths_raw = filtered[[c for c in death_cols if c in filtered.columns]].copy()
metrics_with_deaths = metrics.merge(deaths_raw, on="character_id", how="left")
for col in ["t5_deaths","t4_deaths","t3_deaths","t2_deaths","t1_deaths"]:
    if col not in metrics_with_deaths.columns:
        metrics_with_deaths[col] = 0
    metrics_with_deaths[col] = metrics_with_deaths[col].fillna(0)

goals = calculate_member_goals(metrics_with_deaths)

    # Apply status filter
    if filter_status != "Todos":
        goals = goals[goals["goal_status"] == filter_status]

    n_import   = len(imports)
    delta_lbl  = f" (+{n_import-1} anterior{'es' if n_import > 2 else ''})" if n_import > 1 else ""
    st.caption(
        f"📅 **{selected['report_date']}** · Base: **{basis}** · "
        f"Membros: **{len(goals):,}** · Imports: **{n_import}**{delta_lbl}"
    )

    tabs = st.tabs([
        "🎯 Ranking de Membros",
        "🏆 Kill Points",
        "📈 Histórico",
        "👥 Governors",
        "📁 Imports",
        "❓ Ajuda",
    ])

    with tabs[0]: show_member_ranking(goals)
    with tabs[1]: show_kp_main(metrics, group_power)
    with tabs[2]: show_history(storage, imports, group_power)
    with tabs[3]: show_governors(metrics)
    with tabs[4]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[5]: show_help()


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Ranking de Membros (NOVA ABA PRINCIPAL)
# ─────────────────────────────────────────────────────────────────────────────
def show_member_ranking(goals: pd.DataFrame) -> None:
    if goals.empty:
        st.info("Nenhum membro encontrado com os filtros selecionados.")
        return

    # ── Summary row ──
    total   = len(goals)
    aprov   = int((goals["goal_status"] == "Aprovado").sum())
    pend    = int((goals["goal_status"] == "Pendente").sum())
    abaixo  = int((goals["goal_status"] == "Abaixo da meta").sum())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="summary-tile">
            <div class="stile-num" style="color:#f59e0b">{total}</div>
            <div class="stile-lbl">Total de Membros</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="summary-tile">
            <div class="stile-num" style="color:#22c55e">{aprov}</div>
            <div class="stile-lbl">✅ Aprovados</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="summary-tile">
            <div class="stile-num" style="color:#eab308">{pend}</div>
            <div class="stile-lbl">⚠️ Pendentes</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="summary-tile">
            <div class="stile-num" style="color:#ef4444">{abaixo}</div>
            <div class="stile-lbl">❌ Abaixo da Meta</div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Goal table reference ──
    with st.expander("📋 Tabela de Metas por City Power", expanded=False):
        tbl_data = []
        for band in POWER_GOAL_BANDS:
            t4eq = band["target_deaths_t4eq"]
            t5_eq = t4eq // 2
            tbl_data.append({
                "Faixa de Power": band["label"],
                "Meta Mortes T4": f"{t4eq:,}",
                "ou Meta Mortes T5": f"{t5_eq:,}",
                "Meta KP": f"{band['target_kp']:,}",
            })
        st.dataframe(pd.DataFrame(tbl_data), use_container_width=True, hide_index=True)
        st.caption("Equivalência: 1 morte T5 = 2 mortes T4. Soma T5+T4 é aceita proporcionalmente.")

    st.divider()

    # ── Sort order: Abaixo → Pendente → Aprovado, then by power desc ──
    order_map = {"Abaixo da meta": 0, "Pendente": 1, "Aprovado": 2}
    display = goals.copy()
    display["_order"] = display["goal_status"].map(order_map).fillna(0)
    display = display.sort_values(["_order", "power"], ascending=[True, False]).reset_index(drop=True)

    # ── View toggle ──
    view_mode = st.radio("Visualização", ["Cards detalhados", "Tabela compacta"], horizontal=True)

    st.divider()

    if view_mode == "Cards detalhados":
        _render_cards(display)
    else:
        _render_table(display)

    # Export
    st.divider()
    csv_cols = [
        "username", "power", "power_band",
        "kill_points", "target_kp", "kp_gap", "kp_pct",
        "t5_kills", "t4_kills", "t3_kills", "t2_kills", "t1_kills",
        "t5_deaths", "t4_deaths", "t3_deaths", "t2_deaths", "t1_deaths",
        "deaths_t4eq", "target_deaths_t4eq", "deaths_gap", "deaths_pct",
        "goal_status",
    ]
    avail_cols = [c for c in csv_cols if c in display.columns]
    csv = display[avail_cols].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="ranking_membros.csv", mime="text/csv")


def _render_cards(df: pd.DataFrame) -> None:
    """Render detailed member cards."""
    page_size = st.selectbox("Cards por página", [10, 25, 50], index=0, key="card_ps")
    total_p   = max(1, -(-len(df) // page_size))
    page      = st.number_input("Página", min_value=1, max_value=total_p, value=1, key="card_pg")
    start_i   = (page - 1) * page_size
    st.caption(f"Mostrando {start_i+1}–{min(start_i+page_size, len(df))} de {len(df):,}")

    page_df = df.iloc[start_i: start_i + page_size]

    for idx, row in page_df.iterrows():
        status      = str(row.get("goal_status", "Abaixo da meta"))
        card_class  = {"Aprovado": "aprovado", "Pendente": "pendente", "Abaixo da meta": "abaixo"}.get(status, "abaixo")
        badge_class = {"Aprovado": "badge-aprovado", "Pendente": "badge-pendente", "Abaixo da meta": "badge-abaixo"}.get(status, "badge-abaixo")
        color       = STATUS_COLOR.get(status, "#ef4444")
        icon        = STATUS_ICON.get(status, "❌")

        power        = int(row.get("power", 0))
        kp           = int(row.get("kill_points", 0))
        target_kp    = int(row.get("target_kp", 0))
        kp_gap       = int(row.get("kp_gap", 0))
        kp_pct       = float(row.get("kp_pct", 0))

        deaths_t4eq  = int(row.get("deaths_t4eq", 0))
        target_deaths = int(row.get("target_deaths_t4eq", 0))
        deaths_gap   = int(row.get("deaths_gap", 0))
        deaths_pct   = float(row.get("deaths_pct", 0))

        t5k = int(row.get("t5_kills", 0))
        t4k = int(row.get("t4_kills", 0))
        t3k = int(row.get("t3_kills", 0))
        t2k = int(row.get("t2_kills", 0))
        t1k = int(row.get("t1_kills", 0))

        t5d = int(row.get("t5_deaths", 0))
        t4d = int(row.get("t4_deaths", 0))
        t3d = int(row.get("t3_deaths", 0))
        t2d = int(row.get("t2_deaths", 0))
        t1d = int(row.get("t1_deaths", 0))

        band = str(row.get("power_band", "—"))
        rank_n = idx + 1

        kp_bar_w     = int(kp_pct * 100)
        deaths_bar_w = int(deaths_pct * 100)

        kp_bar_color     = color if kp_pct < 1.0 else "#22c55e"
        deaths_bar_color = color if deaths_pct < 1.0 else "#22c55e"

        gap_deaths_txt = f"Faltam {deaths_gap:,} T4-eq" if deaths_gap > 0 else "✓ Meta atingida"
        gap_kp_txt     = f"Faltam {kp_gap:,} KP" if kp_gap > 0 else "✓ Meta atingida"

        st.markdown(f"""
        <div class="member-card {card_class}">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <div class="member-rank">#{rank_n} · {band}</div>
                    <div class="member-name">{row.get('username','—')}</div>
                    <div class="member-power">City Power: {power:,}</div>
                </div>
                <div style="text-align:right">
                    <span class="member-badge {badge_class}">{icon} {status}</span>
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px">

                <!-- KP -->
                <div>
                    <div style="font-size:.65rem;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Kill Points</div>
                    <div style="font-size:1rem;font-weight:800;color:#f1f5f9">{kp:,}</div>
                    <div style="font-size:.65rem;color:#94a3b8">Meta: {target_kp:,}</div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width:{kp_bar_w}%;background:{kp_bar_color}"></div>
                    </div>
                    <div style="font-size:.62rem;color:{kp_bar_color}">{kp_bar_w}% · {gap_kp_txt}</div>
                </div>

                <!-- Mortes -->
                <div>
                    <div style="font-size:.65rem;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Mortes (T4-eq)</div>
                    <div style="font-size:1rem;font-weight:800;color:#f1f5f9">{deaths_t4eq:,}</div>
                    <div style="font-size:.65rem;color:#94a3b8">Meta: {target_deaths:,} T4-eq</div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width:{deaths_bar_w}%;background:{deaths_bar_color}"></div>
                    </div>
                    <div style="font-size:.62rem;color:{deaths_bar_color}">{deaths_bar_w}% · {gap_deaths_txt}</div>
                </div>
            </div>

            <!-- Kills breakdown -->
            <div style="margin-top:10px">
                <div style="font-size:.62rem;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Kills por tier</div>
                <div class="stat-grid">
                    <div class="stat-pill">T5 <span style="color:{TIER_COLORS['T5']}">{t5k:,}</span></div>
                    <div class="stat-pill">T4 <span style="color:{TIER_COLORS['T4']}">{t4k:,}</span></div>
                    <div class="stat-pill">T3 <span style="color:{TIER_COLORS['T3']}">{t3k:,}</span></div>
                    <div class="stat-pill">T2 <span style="color:{TIER_COLORS['T2']}">{t2k:,}</span></div>
                    <div class="stat-pill">T1 <span style="color:{TIER_COLORS['T1']}">{t1k:,}</span></div>
                </div>
            </div>

            <!-- Deaths breakdown -->
            <div style="margin-top:8px">
                <div style="font-size:.62rem;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Mortes por tier</div>
                <div class="stat-grid">
                    <div class="stat-pill">T5 <span style="color:{TIER_COLORS['T5']}">{t5d:,}</span></div>
                    <div class="stat-pill">T4 <span style="color:{TIER_COLORS['T4']}">{t4d:,}</span></div>
                    <div class="stat-pill">T3 <span style="color:{TIER_COLORS['T3']}">{t3d:,}</span></div>
                    <div class="stat-pill">T2 <span style="color:{TIER_COLORS['T2']}">{t2d:,}</span></div>
                    <div class="stat-pill">T1 <span style="color:{TIER_COLORS['T1']}">{t1d:,}</span></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


def _render_table(df: pd.DataFrame) -> None:
    """Render compact sortable table."""
    tbl = df.copy()

    # Select & rename columns
    col_map = {
        "username":             "Membro",
        "power":                "City Power",
        "power_band":           "Faixa",
        "kill_points":          "KP Total",
        "target_kp":            "Meta KP",
        "kp_pct":               "KP %",
        "kp_gap":               "Falta KP",
        "t5_kills":             "Kills T5",
        "t4_kills":             "Kills T4",
        "t3_kills":             "Kills T3",
        "t2_kills":             "Kills T2",
        "t1_kills":             "Kills T1",
        "t5_deaths":            "Mortes T5",
        "t4_deaths":            "Mortes T4",
        "t3_deaths":            "Mortes T3",
        "t2_deaths":            "Mortes T2",
        "t1_deaths":            "Mortes T1",
        "deaths_t4eq":          "Mortes T4-eq",
        "target_deaths_t4eq":   "Meta Mortes",
        "deaths_pct":           "Mortes %",
        "deaths_gap":           "Falta Mortes",
        "goal_status":          "Status",
    }
    avail = [c for c in col_map if c in tbl.columns]
    out   = tbl[avail].copy()

    if "kp_pct" in out:
        out["kp_pct"] = out["kp_pct"].map(lambda v: f"{v*100:.1f}%")
    if "deaths_pct" in out:
        out["deaths_pct"] = out["deaths_pct"].map(lambda v: f"{v*100:.1f}%")
    if "goal_status" in out:
        out["goal_status"] = out["goal_status"].map(
            lambda s: f"{STATUS_ICON.get(s,'')} {s}"
        )

    out.rename(columns=col_map, inplace=True)

    page_size = st.selectbox("Linhas por página", [25, 50, 100], index=0, key="tbl_ps")
    total_p   = max(1, -(-len(out) // page_size))
    page      = st.number_input("Página", min_value=1, max_value=total_p, value=1, key="tbl_pg")
    start_i   = (page - 1) * page_size
    st.caption(f"Mostrando {start_i+1}–{min(start_i+page_size, len(out))} de {len(out):,}")

    st.dataframe(out.iloc[start_i: start_i + page_size], use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Kill Points (mantida do original)
# ─────────────────────────────────────────────────────────────────────────────
DISPLAY_COLUMNS = [
    "rank","username","character_id","power",
    "t5_kills","t4_kills","t3_kills","t2_kills","t1_kills",
    "kill_points","kill_share",
]
DISPLAY_NAMES = {
    "rank":"#","username":"Governor","character_id":"ID",
    "power":"Power","t5_kills":"T5 Kills","t4_kills":"T4 Kills",
    "t3_kills":"T3 Kills","t2_kills":"T2 Kills","t1_kills":"T1 Kills",
    "kill_points":"Kill Points","kill_share":"Share %",
}

def show_kp_main(metrics: pd.DataFrame, group_power: int) -> None:
    kp_total    = int(metrics["kill_points"].sum())
    active      = int((metrics["kill_points"] > 0).sum())
    participation = active / len(metrics) if len(metrics) else 0
    group_kpi   = kp_total / group_power if group_power else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("⚔️ Total Kill Points", fmt_int(kp_total))
    c2.metric("📊 KPi do Reino", fmt_dkpi(group_kpi))
    c3.metric("👥 Governors Ativos", fmt_int(active))
    c4.metric("📈 Participação", fmt_pct(participation))
    c5.metric("🏰 Total Governors", fmt_int(len(metrics)))

    st.divider()

    # Tier breakdown
    st.markdown('<div class="section-header">Contribuição por tier</div>', unsafe_allow_html=True)
    tier_config = [
        ("t5_kills","T5",POINT_WEIGHTS.get("t5_kills",20),TIER_COLORS["T5"]),
        ("t4_kills","T4",POINT_WEIGHTS.get("t4_kills",10),TIER_COLORS["T4"]),
        ("t3_kills","T3",POINT_WEIGHTS.get("t3_kills",4), TIER_COLORS["T3"]),
        ("t2_kills","T2",POINT_WEIGHTS.get("t2_kills",2), TIER_COLORS["T2"]),
        ("t1_kills","T1",POINT_WEIGHTS.get("t1_kills",0.2),TIER_COLORS["T1"]),
    ]
    tier_data = []
    t_cols = st.columns(5)
    for i,(col,label,weight,color) in enumerate(tier_config):
        total_kills = int(metrics[col].sum()) if col in metrics else 0
        tier_pts    = int(total_kills * weight)
        tier_data.append({"Tier":label,"Kills":total_kills,"KP":tier_pts,"Peso":f"×{weight}","color":color})
        with t_cols[i]:
            st.markdown(f"""
            <div style="background:#1e293b;border:1px solid #334155;border-top:3px solid {color};
                border-radius:10px;padding:12px 14px;text-align:center">
                <div style="font-size:.68rem;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.08em">
                    {label} <span style="color:{color}">{weight}</span>
                </div>
                <div style="font-size:1.3rem;font-weight:800;color:#f1f5f9;margin:5px 0 2px">{fmt_int(total_kills)}</div>
                <div style="font-size:.78rem;color:{color};font-weight:700">{fmt_int(tier_pts)} KP</div>
            </div>""", unsafe_allow_html=True)

    st.divider()

    # Top 3 podium
    ranked = add_rank(metrics, "kill_points")
    st.markdown('<div class="section-header">🏆 Top Governors</div>', unsafe_allow_html=True)
    if len(ranked) >= 3:
        podium_styles = [("gold","🥇",THEME_GOLD),("silver","🥈","#94a3b8"),("bronze","🥉","#b45309")]
        cols = st.columns(3)
        for i,(style,medal,color) in enumerate(podium_styles):
            row = ranked.iloc[i]
            with cols[i]:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#1e293b,#162032);border:1px solid #334155;
                    border-radius:12px;padding:14px;text-align:center;border-top:3px solid {color}">
                    <div style="font-size:1.7rem">{medal}</div>
                    <div style="font-size:.88rem;font-weight:700;color:#f1f5f9;margin:4px 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{row['username']}</div>
                    <div style="font-size:1rem;font-weight:800;color:{color}">{fmt_int(int(row['kill_points']))}</div>
                    <div style="font-size:.68rem;color:#64748b;margin-top:2px">Power: {fmt_int(int(row['power']))}</div>
                </div>""", unsafe_allow_html=True)

    st.divider()

    if px is not None and not ranked.empty:
        left, right = st.columns([3,2])
        with left:
            st.markdown('<div class="section-header">Top 20 — Kill Points</div>', unsafe_allow_html=True)
            top20 = ranked.head(20).sort_values("kill_points", ascending=True)
            fig = px.bar(top20, x="kill_points", y="username", orientation="h",
                         color="kill_points", color_continuous_scale=["#1e3a5f","#f59e0b"],
                         labels={"kill_points":"Kill Points","username":""})
            fig.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                              font_color="#94a3b8", showlegend=False, coloraxis_showscale=False,
                              margin=dict(l=0,r=0,t=10,b=0),
                              xaxis=dict(gridcolor="#1e3a5f",color="#64748b"),
                              yaxis=dict(gridcolor="#1e3a5f",color="#e2e8f0"))
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown('<div class="section-header">Contribuição por tier</div>', unsafe_allow_html=True)
            pie_data = [td for td in tier_data if td["KP"]>0]
            if pie_data:
                fig2 = px.pie(values=[td["KP"] for td in pie_data],names=[td["Tier"] for td in pie_data],
                              color=[td["Tier"] for td in pie_data],
                              color_discrete_map={td["Tier"]:td["color"] for td in pie_data}, hole=0.6)
                fig2.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                                   font_color="#94a3b8", showlegend=True,
                                   legend=dict(font=dict(color="#94a3b8")),
                                   margin=dict(l=0,r=0,t=10,b=0))
                fig2.update_traces(textposition="inside", textinfo="percent+label", textfont_color="white")
                st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown('<div class="section-header">Ranking completo</div>', unsafe_allow_html=True)
    page_size = st.selectbox("Por página",[25,50,100],index=0,key="kp_ps")
    total_pages = max(1,-(-len(ranked)//page_size))
    page = st.number_input("Página",min_value=1,max_value=total_pages,value=1,key="kp_pg")
    start_i = (page-1)*page_size
    st.caption(f"Mostrando {start_i+1}–{min(start_i+page_size,len(ranked))} de {len(ranked):,}")
    st.dataframe(display_table(ranked.iloc[start_i:start_i+page_size]), use_container_width=True, hide_index=True)
    csv = ranked.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="kp_ranking.csv", mime="text/csv")


def display_table(frame: pd.DataFrame) -> pd.DataFrame:
    avail = [c for c in DISPLAY_COLUMNS if c in frame.columns]
    out   = frame[avail].copy()
    if "kill_share" in out: out["kill_share"] = out["kill_share"].map(fmt_pct)
    return out.rename(columns=DISPLAY_NAMES)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Histórico
# ─────────────────────────────────────────────────────────────────────────────
def show_history(storage, imports: pd.DataFrame, group_power: int) -> None:
    st.subheader("📈 Evolução histórica do reino")
    if len(imports) < 2:
        st.info("Importe pelo menos 2 relatórios para ver a evolução.")
        return
    ordered = imports.sort_values(["report_date","imported_at"],ascending=[True,True]).reset_index(drop=True)
    rows = []
    with st.spinner("Carregando histórico..."):
        for _,imp in ordered.iterrows():
            stats   = storage.load_stats(imp["id"])
            metrics = calculate_metrics(stats, group_power=group_power)
            rows.append({
                "Data":      imp["report_date"],
                "KP Total":  int(metrics["kill_points"].sum()),
                "Ativos":    int((metrics["kill_points"]>0).sum()),
                "Governors": len(metrics),
                "T5 Kills":  int(metrics["t5_kills"].sum()) if "t5_kills" in metrics else 0,
                "T4 Kills":  int(metrics["t4_kills"].sum()) if "t4_kills" in metrics else 0,
            })
    history = pd.DataFrame(rows)
    if px is not None:
        c1,c2 = st.columns(2)
        with c1:
            fig = px.line(history,x="Data",y="KP Total",title="Kill Points ao longo do tempo",
                          markers=True,color_discrete_sequence=[THEME_GOLD])
            fig.update_layout(plot_bgcolor="#0f172a",paper_bgcolor="#0f172a",font_color="#94a3b8",
                              xaxis=dict(gridcolor="#1e3a5f"),yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig,use_container_width=True)
        with c2:
            melted = history[["Data","T5 Kills","T4 Kills"]].melt(id_vars="Data",var_name="Tier",value_name="Kills")
            fig2 = px.bar(melted,x="Data",y="Kills",color="Tier",barmode="stack",
                          title="T5 vs T4 Kills por período",
                          color_discrete_map={"T5 Kills":THEME_GOLD,"T4 Kills":THEME_ORANGE})
            fig2.update_layout(plot_bgcolor="#0f172a",paper_bgcolor="#0f172a",font_color="#94a3b8",
                               xaxis=dict(gridcolor="#1e3a5f"),yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig2,use_container_width=True)

    st.divider()
    st.subheader("Comparar dois relatórios")
    labels = ordered["label"].tolist()
    c1,c2 = st.columns(2)
    with c1: label_a = st.selectbox("Base",labels,index=0,key="ha")
    with c2: label_b = st.selectbox("Comparado",labels,index=min(1,len(labels)-1),key="hb")
    id_a = ordered.loc[ordered["label"].eq(label_a),"id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(label_b),"id"].iloc[0]
    if id_a == id_b:
        st.warning("Selecione dois relatórios diferentes.")
        return
    stats_a   = storage.load_stats(id_a)
    stats_b   = storage.load_stats(id_b)
    delta_df  = compute_period_deltas(stats_b, stats_a)
    metrics   = calculate_metrics(delta_df, group_power=group_power)
    top = metrics.sort_values("kill_points",ascending=False).head(15)
    if not top.empty and px is not None:
        fig = px.bar(top.sort_values("kill_points",ascending=True),
                     x="kill_points",y="username",orientation="h",
                     title="Top 15 — Ganho no período",color_discrete_sequence=[THEME_GOLD])
        fig.update_layout(plot_bgcolor="#0f172a",paper_bgcolor="#0f172a",font_color="#94a3b8",
                          xaxis=dict(gridcolor="#1e3a5f"),yaxis=dict(gridcolor="#1e3a5f"))
        st.plotly_chart(fig,use_container_width=True)
    st.dataframe(display_table(add_rank(metrics,"kill_points")),use_container_width=True,hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Governors
# ─────────────────────────────────────────────────────────────────────────────
def show_governors(metrics: pd.DataFrame) -> None:
    ranked = add_rank(metrics,"kill_points")
    if px is not None and not ranked.empty:
        c1,c2 = st.columns(2)
        with c1:
            fig = px.scatter(ranked,x="power",y="kill_points",hover_name="username",
                             color="kill_points",color_continuous_scale="YlOrRd",
                             title="Power vs Kill Points")
            fig.update_layout(plot_bgcolor="#0f172a",paper_bgcolor="#0f172a",font_color="#94a3b8",
                              xaxis=dict(gridcolor="#1e3a5f"),yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig,use_container_width=True)
        with c2:
            fig2 = px.scatter(ranked,x="t5_kills",y="t4_kills",hover_name="username",
                              color="kill_points",color_continuous_scale="Plasma",title="T5 vs T4 Kills")
            fig2.update_layout(plot_bgcolor="#0f172a",paper_bgcolor="#0f172a",font_color="#94a3b8",
                               xaxis=dict(gridcolor="#1e3a5f"),yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig2,use_container_width=True)
    st.subheader("Tabela de governors")
    st.dataframe(display_table(ranked),use_container_width=True,hide_index=True)
    csv = ranked.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Baixar CSV",data=csv,file_name="governors.csv",mime="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Imports
# ─────────────────────────────────────────────────────────────────────────────
def show_imports(imports: pd.DataFrame, storage, *, is_admin: bool, admin_enabled: bool) -> None:
    st.subheader("Relatórios importados")
    st.dataframe(
        imports[["report_date","filename","row_count","imported_at"]].rename(columns={
            "report_date":"Data","filename":"Arquivo","row_count":"Governors","imported_at":"Importado em",
        }), use_container_width=True, hide_index=True,
    )
    if admin_enabled and is_admin:
        st.divider()
        st.subheader("🗑️ Deletar import")
        st.warning("⚠️ Irreversível — remove todos os dados associados.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Selecionar import",["— selecionar —",*labels])
        if to_del != "— selecionar —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            if st.button("🗑️ Confirmar exclusão",type="secondary"):
                if storage.delete_import(row["id"]):
                    st.success(f"Deletado: {to_del}")
                    st.rerun()
                else:
                    st.error("Não encontrado.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Ajuda
# ─────────────────────────────────────────────────────────────────────────────
def show_help() -> None:
    st.header("❓ Como usar")
    st.markdown("""
## Tabela de Metas por City Power

| Faixa de Power | Meta Mortes T4 | ou Meta Mortes T5 | Meta KP |
|---|---|---|---|
| ≤ 49M | 900k T4 | 450k T5 | 80M |
| 50M–59M | 900k T4 | 450k T5 | 100M |
| 60M–69M | 1M T4 | 500k T5 | 140M |
| 70M–79M | 1.4M T4 | 700k T5 | 180M |
| 80M–89M | 1.6M T4 | 800k T5 | 200M |
| 90M–99M | 2M T4 | 1M T5 | 280M |
| ≥ 100M | 2M T4 | 1M T5 | 320M |

**Equivalência:** 1 morte T5 = 2 mortes T4. A soma de T4 + T5 é aceita (ex: 300k T5 + 300k T4 = 900k T4-eq).

## Status de Meta
- ✅ **Aprovado** — Bateu tanto mortes quanto KP
- ⚠️ **Pendente** — ≥ 75% de progresso em ambos, mas não 100%
- ❌ **Abaixo da meta** — Abaixo de 75% em mortes ou KP

## Como exportar do jogo
1. **More → Kingdom → Kingdom Overview → Stats**
2. Toque no ícone de **Export**
3. Salve o arquivo `.xlsx`

## Kill Points (Pesos dos tiers)
| Tier | Multiplicador |
|------|--------------|
| T5 | × 20 |
| T4 | × 10 |
| T3 | × 4 |
| T2 | × 2 |
| T1 | × 0.2 |
""")


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar helpers
# ─────────────────────────────────────────────────────────────────────────────
def _empty_state() -> None:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px">
        <div style="font-size:3.5rem">⚔️</div>
        <h3 style="color:#f1f5f9;margin:12px 0 8px">Nenhum relatório ainda</h3>
        <p style="color:#64748b">Faça upload do primeiro statsExport para começar.</p>
    </div>""", unsafe_allow_html=True)
    st.info("👈 Use o painel lateral para fazer upload do arquivo `.xlsx` exportado do jogo.")


def handle_upload(storage) -> None:
    pwd = get_secret("ADMIN_PASSWORD")
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False
    if not st.session_state.upload_auth:
        st.markdown('<div class="unlock-box">', unsafe_allow_html=True)
        st.markdown("🔒 **Área restrita**\n\nInsira a senha para fazer upload.")
        upload_pwd = st.text_input("Senha",type="password",key="upload_pwd_input",placeholder="Digite a senha...")
        if st.button("🔓 Desbloquear",use_container_width=True):
            if pwd and is_admin_authenticated(pwd,upload_pwd):
                st.session_state.upload_auth = True; st.rerun()
            elif not pwd:
                st.session_state.upload_auth = True; st.rerun()
            else:
                st.error("❌ Senha incorreta")
        st.markdown('</div>',unsafe_allow_html=True)
        return

    st.success("✅ Upload desbloqueado")
    if st.button("🔒 Bloquear",use_container_width=True,type="secondary"):
        st.session_state.upload_auth = False; st.rerun()

    uploaded = st.file_uploader("Upload statsExport",type=["xlsx","xls"])
    if uploaded is None: return

    safe_name   = re.sub(r"[^\w.\-]","_",uploaded.name)
    report_guess = extract_report_date_from_name(safe_name) or date.today()
    report_date  = st.date_input("Data do relatório",value=report_guess)

    if not st.button("💾 Salvar relatório",type="primary",use_container_width=True): return

    with st.spinner("Processando..."):
        try:
            file_bytes = uploaded.getvalue()
            if len(file_bytes) > 50*1024*1024:
                st.error("❌ Arquivo muito grande (limite 50 MB)."); return
            stats = load_stats_file(BytesIO(file_bytes),filename=safe_name)
            _,created = storage.save_import(
                filename=safe_name, report_date=report_date.isoformat(),
                file_hash=file_sha256(file_bytes), stats=stats,
            )
        except Exception as exc:
            st.error(f"❌ Falha no import: {exc}"); return

    if created:
        st.success(f"✅ {len(stats):,} governors salvos!")
    else:
        st.warning("⚠️ Arquivo já importado.")
    st.rerun()


def prepare_imports(imports: pd.DataFrame) -> pd.DataFrame:
    out = imports.copy()
    out["report_date"] = pd.to_datetime(out["report_date"]).dt.date.astype(str)
    out["imported_at"] = out["imported_at"].astype(str)
    out["label"]       = out["report_date"] + " — " + out["filename"].astype(str)
    return out


def select_report(imports: pd.DataFrame) -> pd.Series:
    labels = imports["label"].tolist()
    chosen = st.sidebar.selectbox("Relatório atual",labels,index=0)
    return imports.loc[imports["label"].eq(chosen)].iloc[0]


def load_previous_report(storage, imports: pd.DataFrame, selected: pd.Series):
    ordered   = imports.sort_values(["report_date","imported_at"],ascending=[True,True]).reset_index(drop=True)
    positions = ordered.index[ordered["id"].eq(selected["id"])].tolist()
    if not positions or positions[0] == 0: return None
    prev_id = ordered.loc[positions[0]-1,"id"]
    if prev_id == selected["id"]: return None
    return storage.load_stats(prev_id)


@st.cache_data(ttl=300)
def _cached_group_power(storage_label: str, first_id: str) -> int:
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"],errors="coerce").fillna(0).sum())


def default_group_power(storage, imports: pd.DataFrame) -> int:
    ordered  = imports.sort_values(["report_date","imported_at"],ascending=[True,True]).reset_index(drop=True)
    first_id = ordered.iloc[0]["id"]
    return _cached_group_power(storage.label, first_id)


def apply_filters(stats: pd.DataFrame, *, search: str, min_power: int) -> pd.DataFrame:
    out = stats.copy()
    if search:
        needle = search.strip().lower()
        out = out[
            out["username"].astype(str).str.lower().str.contains(needle,regex=False)
            | out["character_id"].astype(str).str.contains(needle,regex=False)
        ]
    if min_power:
        out = out[pd.to_numeric(out["power"],errors="coerce").fillna(0) >= min_power]
    return out


def admin_panel() -> tuple[bool, bool]:
    st.markdown('<div class="section-header">🔒 Admin</div>',unsafe_allow_html=True)
    pwd = get_secret("ADMIN_PASSWORD")
    if not pwd:
        st.caption("Configure ADMIN_PASSWORD nos Secrets para ativar.")
        return False, False
    entered = st.text_input("Senha admin",type="password",key="admin_pwd")
    if is_admin_authenticated(pwd,entered):
        st.success("✅ Admin ativo")
        return True, True
    if entered:
        st.error("❌ Senha incorreta")
    return True, False


def get_secret(name: str):
    val = os.getenv(name)
    if val: return val
    try:
        val = st.secrets.get(name)
    except Exception:
        val = None
    return str(val) if val else None


# ─────────────────────────────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────────────────────────────
def fmt_int(v)    -> str: return f"{int(v):,}"
def fmt_pct(v)    -> str: return f"{float(v)*100:.1f}%"
def fmt_dkpi(v)   -> str:
    f = float(v)
    if f == 0: return "0.0000"
    if f < 0.0001: return f"{f:.2e}"
    return f"{f:.6f}"


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
