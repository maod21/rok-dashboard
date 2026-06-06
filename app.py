from __future__ import annotations

import os
import re
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from goal_metrics import calculate_goal_progress, default_goal_bands, summarize_goal_bands
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

TIER_COLORS = {
    "T5": "#f59e0b",
    "T4": "#ea580c",
    "T3": "#8b5cf6",
    "T2": "#3b82f6",
    "T1": "#64748b",
}

DISPLAY_COLUMNS = [
    "rank", "username", "character_id", "power",
    "t5_kills", "t4_kills", "t3_kills", "t2_kills", "t1_kills",
    "kill_points", "personal_dkpi", "kill_share",
]

DISPLAY_NAMES: dict[str, str] = {
    "rank": "#", "username": "Governor", "character_id": "ID",
    "power": "Power", "t5_kills": "T5 Kills", "t4_kills": "T4 Kills",
    "t3_kills": "T3 Kills", "t2_kills": "T2 Kills", "t1_kills": "T1 Kills",
    "kill_points": "Kill Points", "personal_dkpi": "KP/Power",
    "kill_share": "Share %", "power_band": "Faixa",
    "target_dkpi": "Target KP/Power", "target_points": "Meta KP",
    "progress_pct": "Progresso", "gap_to_goal": "Gap",
    "over_goal_points": "Acima da Meta", "goal_status": "Status",
    "combined_points": "Kill Points", "combined_share": "Share %",
    "dkpi": "KPi", "death_points": "—",
}

STATUS_ICON = {
    "Met": "🟢", "In Progress": "🟡",
    "No Points": "🔴", "No Target": "⚪", "Unassigned": "⚫",
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
/* Base */
html, body, [class*="css"] { font-family: 'Segoe UI', system-ui, sans-serif; }
.main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
section[data-testid="stSidebar"] {
    background: #0a1628 !important;
    border-right: 1px solid #1e3a5f;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1e293b 0%, #162032 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 18px 20px !important;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
}
[data-testid="stMetric"]:hover { border-color: #f59e0b55; }
[data-testid="stMetric"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #f59e0b, #ea580c);
}
[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 600;
}
[data-testid="stMetricValue"] {
    color: #f1f5f9 !important;
    font-size: 1.55rem !important;
    font-weight: 800;
    letter-spacing: -0.02em;
}

/* Tabs */
[data-testid="stTabs"] button {
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #64748b !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #f59e0b !important;
    border-bottom-color: #f59e0b !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    overflow: hidden;
}

/* Divider */
hr { border-color: #1e3a5f !important; margin: 1.2rem 0 !important; }

/* Title banner */
.title-banner {
    background: linear-gradient(135deg, #1a2744 0%, #0f172a 100%);
    border: 1px solid #1e3a5f;
    border-left: 4px solid #f59e0b;
    border-radius: 10px;
    padding: 16px 24px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 16px;
}
.title-banner h1 { margin: 0; font-size: 1.5rem; font-weight: 800; color: #f1f5f9; }
.title-banner p  { margin: 4px 0 0; font-size: 0.78rem; color: #94a3b8; }

/* Weight pills */
.weight-pills { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0 12px; }
.pill {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 0.05em;
}
.pill.t5 { border-color: #f59e0b55; color: #f59e0b; }
.pill.t4 { border-color: #ea580c55; color: #ea580c; }
.pill.t3 { border-color: #8b5cf655; color: #8b5cf6; }
.pill.t2 { border-color: #3b82f655; color: #3b82f6; }
.pill.t1 { border-color: #64748b55; color: #94a3b8; }

/* Top 3 podium */
.podium { display: flex; gap: 12px; margin: 12px 0; }
.podium-card {
    flex: 1;
    background: linear-gradient(135deg, #1e293b, #162032);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.podium-card.gold   { border-color: #f59e0b88; }
.podium-card.silver { border-color: #94a3b888; }
.podium-card.bronze { border-color: #b4530988; }
.podium-medal { font-size: 1.8rem; }
.podium-name  { font-size: 0.9rem; font-weight: 700; color: #f1f5f9; margin: 6px 0 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.podium-kp   { font-size: 1.1rem; font-weight: 800; color: #f59e0b; }
.podium-sub  { font-size: 0.7rem; color: #64748b; margin-top: 2px; }

/* Stat row pills */
.tier-row { display: flex; gap: 6px; margin: 4px 0; flex-wrap: wrap; }
.tier-badge {
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.05em;
}

/* Section headers */
.section-header {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #64748b;
    border-bottom: 1px solid #1e3a5f;
    padding-bottom: 6px;
    margin-bottom: 12px;
}

/* Password unlock box */
.unlock-box {
    background: linear-gradient(135deg, #1a2744, #0f172a);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    margin: 12px 0;
}
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

    # ── Title banner ──
    st.markdown("""
    <div class="title-banner">
        <div style="font-size:2.2rem">⚔️</div>
        <div>
            <h1>K1602 · KP Dashboard</h1>
            <p>Kingdom Kill Points Tracker — Rise of Kingdoms</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Weight pills
    st.markdown("""
    <div class="weight-pills">
        <span class="pill t5">T5 × 20</span>
        <span class="pill t4">T4 × 10</span>
        <span class="pill t3">T3 × 4</span>
        <span class="pill t2">T2 × 2</span>
        <span class="pill t1">T1 × 0.2</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:8px 0 16px">
            <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.1em;color:#475569;font-weight:700">Storage</div>
            <div style="color:#f59e0b;font-size:0.85rem;font-weight:600">{'🟢 ' + storage.label}</div>
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
        basis     = st.radio("Base das métricas", basis_options, index=0)
        search    = st.text_input("🔍 Buscar governor")
        min_power = st.number_input("Power mínimo", min_value=0, value=0, step=1_000_000,
                                     format="%d")

    stats_basis = compute_period_deltas(current, previous) if basis == "Delta do período" else current
    filtered    = apply_filters(stats_basis, search=search, min_power=min_power)
    gp_default  = default_group_power(storage, imports)

    with st.sidebar:
        st.divider()
        st.markdown('<div class="section-header">📊 Configuração</div>', unsafe_allow_html=True)
        group_power = st.number_input(
            "Power inicial do grupo",
            min_value=1,
            value=max(1, int(gp_default)),
            step=1_000_000,
            format="%d",
        )
        st.divider()
        admin_enabled, is_admin = admin_panel()

    metrics = calculate_metrics(filtered, group_power=group_power)

    try:
        goal_bands         = storage.load_goal_bands()
        goal_storage_error = None
    except Exception as exc:
        goal_bands         = default_goal_bands()
        goal_storage_error = str(exc)

    # Caption bar
    n_import    = len(imports)
    delta_label = f" (+{n_import - 1} anterior{'es' if n_import > 2 else ''})" if n_import > 1 else ""
    st.caption(
        f"📅 **{selected['report_date']}** · Base: **{basis}** · "
        f"Governors: **{len(metrics):,}** · Imports: **{n_import}**{delta_label}"
    )

    tabs = st.tabs([
        "🏆 Kill Points", "🎯 Metas", "📈 Histórico",
        "👥 Governors", "📁 Imports", "❓ Ajuda",
    ])

    with tabs[0]: show_kp_main(metrics, group_power)
    with tabs[1]: show_goals(
        metrics=metrics, goal_bands=goal_bands, storage=storage,
        is_admin=is_admin, admin_enabled=admin_enabled,
        storage_error=goal_storage_error,
    )
    with tabs[2]: show_history(storage, imports, group_power)
    with tabs[3]: show_governors(metrics)
    with tabs[4]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[5]: show_help()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar helpers
# ─────────────────────────────────────────────────────────────────────────────

def _empty_state() -> None:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px">
        <div style="font-size:4rem">⚔️</div>
        <h3 style="color:#f1f5f9;margin:12px 0 8px">Nenhum relatório ainda</h3>
        <p style="color:#64748b">Faça upload do primeiro statsExport para começar a rastrear os KPs do reino.</p>
    </div>
    """, unsafe_allow_html=True)
    st.info("👈 Use o painel lateral para fazer upload do arquivo `.xlsx` exportado do jogo.")


def handle_upload(storage) -> None:
    pwd = get_secret("ADMIN_PASSWORD")

    # Check if already authenticated for upload this session
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.markdown('<div class="unlock-box">', unsafe_allow_html=True)
        st.markdown("🔒 **Área restrita**\n\nInsira a senha para fazer upload de relatórios.")
        upload_pwd = st.text_input("Senha", type="password", key="upload_pwd_input",
                                    placeholder="Digite a senha...")
        if st.button("🔓 Desbloquear", use_container_width=True):
            if pwd and is_admin_authenticated(pwd, upload_pwd):
                st.session_state.upload_auth = True
                st.rerun()
            elif not pwd:
                st.session_state.upload_auth = True
                st.rerun()
            else:
                st.error("❌ Senha incorreta")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # Unlocked — show upload
    st.success("✅ Upload desbloqueado")
    if st.button("🔒 Bloquear", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False
        st.rerun()

    uploaded = st.file_uploader("Upload statsExport", type=["xlsx", "xls"])
    if uploaded is None:
        return

    safe_name    = re.sub(r"[^\w.\-]", "_", uploaded.name)
    report_guess = extract_report_date_from_name(safe_name) or date.today()
    report_date  = st.date_input("Data do relatório", value=report_guess)

    if not st.button("💾 Salvar relatório", type="primary", use_container_width=True):
        return

    with st.spinner("Processando..."):
        try:
            file_bytes = uploaded.getvalue()
            if len(file_bytes) > 50 * 1024 * 1024:
                st.error("❌ Arquivo muito grande (limite 50 MB).")
                return
            stats = load_stats_file(BytesIO(file_bytes), filename=safe_name)
            _, created = storage.save_import(
                filename=safe_name,
                report_date=report_date.isoformat(),
                file_hash=file_sha256(file_bytes),
                stats=stats,
            )
        except Exception as exc:
            st.error(f"❌ Falha no import: {exc}")
            return

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
    chosen = st.sidebar.selectbox("Relatório atual", labels, index=0)
    return imports.loc[imports["label"].eq(chosen)].iloc[0]


def load_previous_report(storage, imports: pd.DataFrame, selected: pd.Series):
    ordered   = imports.sort_values(["report_date", "imported_at"], ascending=[True, True]).reset_index(drop=True)
    positions = ordered.index[ordered["id"].eq(selected["id"])].tolist()
    if not positions or positions[0] == 0:
        return None
    prev_id = ordered.loc[positions[0] - 1, "id"]
    if prev_id == selected["id"]:
        return None
    return storage.load_stats(prev_id)


@st.cache_data(ttl=300)
def _cached_group_power(storage_label: str, first_id: str) -> int:
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"], errors="coerce").fillna(0).sum())


def default_group_power(storage, imports: pd.DataFrame) -> int:
    ordered  = imports.sort_values(["report_date", "imported_at"], ascending=[True, True]).reset_index(drop=True)
    first_id = ordered.iloc[0]["id"]
    return _cached_group_power(storage.label, first_id)


def apply_filters(stats: pd.DataFrame, *, search: str, min_power: int) -> pd.DataFrame:
    out = stats.copy()
    if search:
        needle = search.strip().lower()
        out = out[
            out["username"].astype(str).str.lower().str.contains(needle, regex=False)
            | out["character_id"].astype(str).str.contains(needle, regex=False)
        ]
    if min_power:
        out = out[pd.to_numeric(out["power"], errors="coerce").fillna(0) >= min_power]
    return out


def admin_panel() -> tuple[bool, bool]:
    st.markdown('<div class="section-header">🔒 Admin</div>', unsafe_allow_html=True)
    pwd = get_secret("ADMIN_PASSWORD")
    if not pwd:
        st.caption("Configure ADMIN_PASSWORD nos Secrets para ativar.")
        return False, False
    entered = st.text_input("Senha admin", type="password", key="admin_pwd")
    if is_admin_authenticated(pwd, entered):
        st.success("✅ Admin ativo")
        return True, True
    if entered:
        st.error("❌ Senha incorreta")
    return True, False


def get_secret(name: str):
    val = os.getenv(name)
    if val:
        return val
    try:
        val = st.secrets.get(name)
    except Exception:
        val = None
    return str(val) if val else None


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Kill Points principal
# ─────────────────────────────────────────────────────────────────────────────

def show_kp_main(metrics: pd.DataFrame, group_power: int) -> None:
    kp_total     = int(metrics["kill_points"].sum())
    active       = int((metrics["kill_points"] > 0).sum())
    participation = active / len(metrics) if len(metrics) else 0
    group_kpi    = kp_total / group_power if group_power else 0

    # Top KPI bar
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("⚔️ Total Kill Points", fmt_int(kp_total))
    c2.metric("📊 KPi do Reino",      fmt_dkpi(group_kpi))
    c3.metric("👥 Governors Ativos",  fmt_int(active))
    c4.metric("📈 Participação",      fmt_pct(participation))
    c5.metric("🏰 Governors",        fmt_int(len(metrics)))

    st.divider()

    # Tier breakdown
    st.markdown('<div class="section-header">Contribuição por tier</div>', unsafe_allow_html=True)
    tier_data = []
    tier_config = [
        ("t5_kills", "T5", POINT_WEIGHTS.get("t5_kills", 20), TIER_COLORS["T5"]),
        ("t4_kills", "T4", POINT_WEIGHTS.get("t4_kills", 10), TIER_COLORS["T4"]),
        ("t3_kills", "T3", POINT_WEIGHTS.get("t3_kills", 4),  TIER_COLORS["T3"]),
        ("t2_kills", "T2", POINT_WEIGHTS.get("t2_kills", 2),  TIER_COLORS["T2"]),
        ("t1_kills", "T1", POINT_WEIGHTS.get("t1_kills", 0.2),TIER_COLORS["T1"]),
    ]
    for col, label, weight, color in tier_config:
        total_kills = int(metrics[col].sum()) if col in metrics else 0
        tier_pts    = int(total_kills * weight)
        tier_data.append({"Tier": label, "Kills": total_kills, "KP": tier_pts,
                           "Peso": f"×{weight}", "color": color})

    t_cols = st.columns(5)
    for i, td in enumerate(tier_data):
        with t_cols[i]:
            st.markdown(f"""
            <div style="background:#1e293b;border:1px solid #334155;border-top:3px solid {td['color']};
                        border-radius:10px;padding:14px 16px;text-align:center">
                <div style="font-size:0.7rem;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.08em">
                    {td['Tier']} Kills <span style="color:{td['color']}">{td['Peso']}</span>
                </div>
                <div style="font-size:1.4rem;font-weight:800;color:#f1f5f9;margin:6px 0 2px">
                    {fmt_int(td['Kills'])}
                </div>
                <div style="font-size:0.8rem;color:{td['color']};font-weight:700">
                    {fmt_int(td['KP'])} KP
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Podium Top 3
    ranked = add_rank(metrics, "kill_points")
    st.markdown('<div class="section-header">🏆 Top Governors</div>', unsafe_allow_html=True)

    if len(ranked) >= 3:
        podium_styles = [
            ("gold",   "🥇", THEME_GOLD),
            ("silver", "🥈", "#94a3b8"),
            ("bronze", "🥉", "#b45309"),
        ]
        cols = st.columns(3)
        for i, (style, medal, color) in enumerate(podium_styles):
            row = ranked.iloc[i]
            with cols[i]:
                st.markdown(f"""
                <div class="podium-card {style}">
                    <div class="podium-medal">{medal}</div>
                    <div class="podium-name">{row['username']}</div>
                    <div class="podium-kp" style="color:{color}">{fmt_int(int(row['kill_points']))}</div>
                    <div class="podium-sub">KP/Power: {fmt_dkpi(float(row['personal_dkpi']))}</div>
                    <div class="podium-sub">Power: {fmt_int(int(row['power']))}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()

    # Charts
    if px is not None and not ranked.empty:
        left, right = st.columns([3, 2])
        with left:
            st.markdown('<div class="section-header">Top 20 — Kill Points</div>', unsafe_allow_html=True)
            top20 = ranked.head(20).sort_values("kill_points", ascending=True)
            fig = px.bar(
                top20, x="kill_points", y="username", orientation="h",
                color="kill_points", color_continuous_scale=["#1e3a5f", "#f59e0b"],
                labels={"kill_points": "Kill Points", "username": ""},
            )
            fig.update_layout(
                plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                font_color="#94a3b8", showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor="#1e3a5f", color="#64748b"),
                yaxis=dict(gridcolor="#1e3a5f", color="#e2e8f0"),
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.markdown('<div class="section-header">Contribuição por tier</div>', unsafe_allow_html=True)
            pie_data = [td for td in tier_data if td["KP"] > 0]
            if pie_data:
                fig2 = px.pie(
                    values=[td["KP"] for td in pie_data],
                    names=[td["Tier"] for td in pie_data],
                    color=[td["Tier"] for td in pie_data],
                    color_discrete_map={td["Tier"]: td["color"] for td in pie_data},
                    hole=0.6,
                )
                fig2.update_layout(
                    plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                    font_color="#94a3b8", showlegend=True,
                    legend=dict(font=dict(color="#94a3b8")),
                    margin=dict(l=0, r=0, t=10, b=0),
                )
                fig2.update_traces(textposition="inside", textinfo="percent+label",
                                   textfont_color="white")
                st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Full ranking table
    st.markdown('<div class="section-header">Ranking completo</div>', unsafe_allow_html=True)
    page_size = st.selectbox("Por página", [25, 50, 100], index=0, key="kp_ps")
    total_pages = max(1, -(-len(ranked) // page_size))
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, key="kp_pg")
    start_i = (page - 1) * page_size
    st.caption(f"Mostrando {start_i+1}–{min(start_i+page_size, len(ranked))} de {len(ranked):,}")
    st.dataframe(display_table(ranked.iloc[start_i: start_i + page_size]),
                 use_container_width=True, hide_index=True)

    # Download
    csv = ranked.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="kp_ranking.csv", mime="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Metas
# ─────────────────────────────────────────────────────────────────────────────

def show_goals(*, metrics, goal_bands, storage, is_admin, admin_enabled, storage_error) -> None:
    if storage_error:
        st.error(f"Erro ao carregar metas: {storage_error}")

    gp      = calculate_goal_progress(metrics, goal_bands)
    summary = summarize_goal_bands(gp)

    t_pts = int(gp["target_points"].sum())  if not gp.empty else 0
    c_pts = int(gp["kill_points"].sum())    if not gp.empty and "kill_points" in gp else int(gp["combined_points"].sum()) if not gp.empty else 0
    gap   = int(gp["gap_to_goal"].sum())    if not gp.empty else 0
    met   = int((gp["goal_status"] == "Met").sum()) if not gp.empty else 0
    pct   = c_pts / t_pts if t_pts else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Progresso Geral", fmt_pct(pct))
    c2.metric("Cumpriram Meta",  f"{met}/{len(gp):,}")
    c3.metric("Meta Total KP",   fmt_int(t_pts))
    c4.metric("KP Atual",        fmt_int(c_pts))
    c5.metric("Gap Total",       fmt_int(gap))

    if not gp.empty and px is not None:
        left, right = st.columns(2)
        with left:
            status_counts = (gp.groupby("goal_status")["character_id"].count()
                             .reset_index().rename(columns={"character_id": "Governors"}))
            color_map = {"Met": "#22c55e", "In Progress": "#eab308",
                         "No Points": "#ef4444", "No Target": "#94a3b8", "Unassigned": "#64748b"}
            fig = px.bar(status_counts, x="goal_status", y="Governors",
                         color="goal_status", color_discrete_map=color_map,
                         title="Governors por status")
            fig.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                              font_color="#94a3b8", showlegend=False,
                              xaxis_title="", yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig, use_container_width=True)
        with right:
            band_counts = (gp.groupby("power_band")["character_id"].count()
                           .reset_index().rename(columns={"character_id": "Governors"}))
            fig2 = px.pie(band_counts, names="power_band", values="Governors",
                          title="Governors por faixa de power", hole=0.5)
            fig2.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                               font_color="#94a3b8")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Resumo por faixa")
    st.dataframe(summary.rename(columns={
        "power_band": "Faixa", "players": "Governors", "met_goal": "Cumpriram",
        "no_points": "Sem KP", "combined_points": "KP Atual",
        "target_points": "Meta KP", "gap_to_goal": "Gap",
        "progress_pct": "Progresso",
    }), use_container_width=True, hide_index=True)

    st.divider()

    # Filter by status
    sf = st.selectbox("Filtrar", ["Todos", "Met", "In Progress", "No Points", "No Target"])
    fgp = gp if sf == "Todos" else gp[gp["goal_status"] == sf]

    goal_cols = ["username", "character_id", "power", "power_band",
                 "target_dkpi", "target_points", "combined_points",
                 "progress_pct", "gap_to_goal", "over_goal_points", "goal_status"]
    avail = [c for c in goal_cols if c in fgp.columns]
    out   = fgp[avail].copy()
    if "progress_pct" in out: out["progress_pct"] = out["progress_pct"].map(fmt_pct)
    if "goal_status"  in out: out["goal_status"]  = out["goal_status"].map(lambda s: f"{STATUS_ICON.get(s,'')} {s}")
    st.dataframe(out.rename(columns=DISPLAY_NAMES), use_container_width=True, hide_index=True)

    csv = fgp.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="metas.csv", mime="text/csv")

    st.divider()
    st.subheader("🛠️ Configurar faixas de meta")
    if not admin_enabled or not is_admin:
        st.info("Digite a senha admin na barra lateral para editar as faixas.")
        return

    edited = st.data_editor(goal_bands, use_container_width=True, hide_index=True,
                             num_rows="dynamic", key="band_editor")
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("💾 Salvar", type="primary"):
            try:
                storage.save_goal_bands(edited)
                st.success("Salvo!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
    with c2:
        if st.button("🔄 Restaurar preset"):
            try:
                storage.reset_goal_bands()
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Histórico
# ─────────────────────────────────────────────────────────────────────────────

def show_history(storage, imports: pd.DataFrame, group_power: int) -> None:
    st.subheader("📈 Evolução histórica do reino")
    if len(imports) < 2:
        st.info("Importe pelo menos 2 relatórios para ver a evolução.")
        return

    ordered = imports.sort_values(["report_date", "imported_at"], ascending=[True, True]).reset_index(drop=True)
    rows = []
    with st.spinner("Carregando histórico..."):
        for _, imp in ordered.iterrows():
            stats   = storage.load_stats(imp["id"])
            metrics = calculate_metrics(stats, group_power=group_power)
            rows.append({
                "Data":        imp["report_date"],
                "KP Total":    int(metrics["kill_points"].sum()),
                "KPi":         metrics["kill_points"].sum() / group_power if group_power else 0,
                "Ativos":      int((metrics["kill_points"] > 0).sum()),
                "Governors":   len(metrics),
                "T5 Kills":    int(metrics["t5_kills"].sum()) if "t5_kills" in metrics else 0,
                "T4 Kills":    int(metrics["t4_kills"].sum()) if "t4_kills" in metrics else 0,
            })

    history = pd.DataFrame(rows)

    if px is not None:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.line(history, x="Data", y="KP Total", title="Kill Points ao longo do tempo",
                          markers=True, color_discrete_sequence=[THEME_GOLD])
            fig.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                              font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                              yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.line(history, x="Data", y="KPi", title="KPi do reino ao longo do tempo",
                           markers=True, color_discrete_sequence=[THEME_GREEN])
            fig2.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                               font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                               yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig2, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            melted = history[["Data", "T5 Kills", "T4 Kills"]].melt(
                id_vars="Data", var_name="Tier", value_name="Kills")
            fig3 = px.bar(melted, x="Data", y="Kills", color="Tier", barmode="stack",
                          title="T5 vs T4 Kills por período",
                          color_discrete_map={"T5 Kills": THEME_GOLD, "T4 Kills": THEME_ORANGE})
            fig3.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                               font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                               yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig3, use_container_width=True)
        with c4:
            fig4 = px.line(history, x="Data", y="Ativos", title="Governors ativos por período",
                           markers=True, color_discrete_sequence=[THEME_PURPLE])
            fig4.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                               font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                               yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig4, use_container_width=True)

    st.divider()
    st.subheader("Comparar dois relatórios")
    labels = ordered["label"].tolist()
    c1, c2 = st.columns(2)
    with c1: label_a = st.selectbox("Base", labels, index=0, key="ha")
    with c2: label_b = st.selectbox("Comparado", labels, index=min(1, len(labels)-1), key="hb")

    id_a = ordered.loc[ordered["label"].eq(label_a), "id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(label_b), "id"].iloc[0]

    if id_a == id_b:
        st.warning("Selecione dois relatórios diferentes.")
        return

    stats_a  = storage.load_stats(id_a)
    stats_b  = storage.load_stats(id_b)
    delta_df = compute_period_deltas(stats_b, stats_a)
    metrics  = calculate_metrics(delta_df, group_power=group_power)
    top      = metrics.sort_values("kill_points", ascending=False).head(15)

    if not top.empty and px is not None:
        fig = px.bar(top.sort_values("kill_points", ascending=True),
                     x="kill_points", y="username", orientation="h",
                     title=f"Top 15 — Ganho no período",
                     color_discrete_sequence=[THEME_GOLD])
        fig.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                          font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                          yaxis=dict(gridcolor="#1e3a5f"))
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(display_table(add_rank(metrics, "kill_points")), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Governors
# ─────────────────────────────────────────────────────────────────────────────

def show_governors(metrics: pd.DataFrame) -> None:
    ranked = add_rank(metrics, "kill_points")

    if px is not None and not ranked.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.scatter(
                ranked, x="power", y="kill_points", hover_name="username",
                color="personal_dkpi", color_continuous_scale="YlOrRd",
                title="Power vs Kill Points (cor = KP/Power)",
            )
            fig.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                              font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                              yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.scatter(
                ranked, x="t5_kills", y="t4_kills", hover_name="username",
                color="kill_points", color_continuous_scale="Plasma",
                title="T5 Kills vs T4 Kills",
            )
            fig2.update_layout(plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                               font_color="#94a3b8", xaxis=dict(gridcolor="#1e3a5f"),
                               yaxis=dict(gridcolor="#1e3a5f"))
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Tabela de governors")
    st.dataframe(display_table(ranked), use_container_width=True, hide_index=True)
    csv = ranked.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Baixar CSV", data=csv, file_name="governors.csv", mime="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Imports
# ─────────────────────────────────────────────────────────────────────────────

def show_imports(imports: pd.DataFrame, storage, *, is_admin: bool, admin_enabled: bool) -> None:
    st.subheader("Relatórios importados")
    st.dataframe(
        imports[["report_date", "filename", "row_count", "imported_at"]].rename(columns={
            "report_date": "Data", "filename": "Arquivo",
            "row_count": "Governors", "imported_at": "Importado em",
        }),
        use_container_width=True, hide_index=True,
    )

    if admin_enabled and is_admin:
        st.divider()
        st.subheader("🗑️ Deletar import")
        st.warning("⚠️ Irreversível — remove todos os dados associados.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Selecionar import", ["— selecionar —", *labels])
        if to_del != "— selecionar —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            if st.button("🗑️ Confirmar exclusão", type="secondary"):
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
## Fórmula de Kill Points

| Tier | Multiplicador | Exemplo |
|------|--------------|---------|
| T5   | × 20         | 1.000 T5 kills = 20.000 KP |
| T4   | × 10         | 1.000 T4 kills = 10.000 KP |
| T3   | × 4          | 1.000 T3 kills = 4.000 KP |
| T2   | × 2          | 1.000 T2 kills = 2.000 KP |
| T1   | × 0.2        | 1.000 T1 kills = 200 KP |

## Como exportar do jogo
1. **More → Kingdom → Kingdom Overview → Stats**
2. Toque no ícone de **Export**
3. Salve o arquivo `.xlsx`

## Upload
O upload exige senha — apenas a liderança pode inserir novos relatórios.

## KPi (Kill Points index)
```
KPi = Total Kill Points / Power inicial do grupo
```
Mede o desempenho do reino em relação ao seu tamanho.

## Personal KP/Power
```
KP/Power = Kill Points do governor / Power próprio
```
Mede o desempenho individual independente do tamanho do governor.

## Delta do período
Com 2+ relatórios importados, selecione **"Delta do período"** para ver apenas o que foi conquistado entre os dois relatórios — ideal para medir um KVK específico.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Formatters & table helpers
# ─────────────────────────────────────────────────────────────────────────────

def display_table(frame: pd.DataFrame) -> pd.DataFrame:
    avail = [c for c in DISPLAY_COLUMNS if c in frame.columns]
    out   = frame[avail].copy()
    if "personal_dkpi" in out: out["personal_dkpi"] = out["personal_dkpi"].map(fmt_dkpi)
    if "kill_share"    in out: out["kill_share"]     = out["kill_share"].map(fmt_pct)
    return out.rename(columns=DISPLAY_NAMES)


def fmt_int(v) -> str:
    return f"{int(v):,}"

def fmt_pct(v) -> str:
    return f"{float(v)*100:.1f}%"

def fmt_dkpi(v) -> str:
    f = float(v)
    if f == 0: return "0.0000"
    if f < 0.0001: return f"{f:.2e}"
    return f"{f:.6f}"


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
