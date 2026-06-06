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

DISPLAY_COLUMNS = [
    "rank", "username", "character_id", "power",
    "t5_kills", "t4_kills", "t5_deaths", "t4_deaths",
    "kill_points", "death_points", "combined_points",
    "dkpi", "personal_dkpi",
]

DISPLAY_NAMES: dict[str, str] = {
    "rank": "Rank", "username": "Username", "character_id": "Character ID",
    "power": "Power", "t5_kills": "T5 Kills", "t4_kills": "T4 Kills",
    "t3_kills": "T3 Kills", "t5_deaths": "T5 Deaths", "t4_deaths": "T4 Deaths",
    "t3_deaths": "T3 Deaths", "kill_points": "Kill Points",
    "death_points": "Death Points", "combined_points": "Combined Points",
    "dkpi": "DKPi", "personal_dkpi": "Personal DKPi",
    "kill_share": "Kill Share %", "death_share": "Death Share %",
    "combined_share": "Combined Share %", "power_band": "Power Band",
    "target_dkpi": "Target DKPi", "target_points": "Target Points",
    "progress_pct": "Progress %", "gap_to_goal": "Gap to Goal",
    "over_goal_points": "Over Goal", "goal_status": "Status",
    "death_kill_ratio": "Death/Kill Ratio", "activity_score": "Activity Score",
}

GOAL_COLUMNS = [
    "username", "character_id", "power", "power_band",
    "target_dkpi", "target_points", "combined_points",
    "progress_pct", "gap_to_goal", "over_goal_points", "goal_status",
]

STATUS_ICON = {
    "Met": "🟢", "In Progress": "🟡",
    "No Points": "🔴", "No Target": "⚪", "Unassigned": "⚫",
}

THEME_KILL   = "#f59e0b"
THEME_DEATH  = "#3b82f6"
THEME_COMBO  = "#8b5cf6"
THEME_GREEN  = "#22c55e"

# ─────────────────────────────────────────────────────────────────────────────
# App bootstrap
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="RoK KP Dashboard", page_icon="⚔️", layout="wide")


@st.cache_resource
def get_storage():
    return create_storage()


def main() -> None:
    storage = get_storage()

    st.title("⚔️ RoK KP Dashboard")
    st.caption(
        f"T4 Kills ×{POINT_WEIGHTS['t4_kills']} | "
        f"T5 Kills ×{POINT_WEIGHTS['t5_kills']} | "
        f"T4 Deaths ×{POINT_WEIGHTS['t4_deaths']} | "
        f"T5 Deaths ×{POINT_WEIGHTS['t5_deaths']}"
    )

    with st.sidebar:
        st.header("📂 Relatórios")
        st.caption(f"Storage: {storage.label}")
        handle_upload(storage)

    imports = storage.list_imports()
    if imports.empty:
        _empty_state()
        return

    imports = prepare_imports(imports)
    selected = select_report(imports)
    current = storage.load_stats(selected["id"])
    previous = load_previous_report(storage, imports, selected)

    basis_options = ["Totais do relatório"]
    if previous is not None and not previous.empty:
        basis_options.insert(0, "Delta do período")

    with st.sidebar:
        basis     = st.radio("Base das métricas", basis_options, index=0)
        search    = st.text_input("🔍 Buscar jogador")
        min_power = st.number_input("Power mínimo", min_value=0, value=0, step=1_000_000)

    stats_basis = compute_period_deltas(current, previous) if basis == "Delta do período" else current
    filtered    = apply_filters(stats_basis, search=search, min_power=min_power)
    gp_default  = default_group_power(storage, imports)

    with st.sidebar:
        group_power = st.number_input(
            "Power inicial do grupo",
            min_value=1,
            value=max(1, int(gp_default)),
            step=1_000_000,
        )
        admin_enabled, is_admin = admin_panel()

    metrics = calculate_metrics(filtered, group_power=group_power)

    try:
        goal_bands         = storage.load_goal_bands()
        goal_storage_error = None
    except Exception as exc:
        goal_bands         = default_goal_bands()
        goal_storage_error = str(exc)

    n_import    = len(imports)
    delta_label = f" (+{n_import - 1} anterior{'es' if n_import > 2 else ''})" if n_import > 1 else ""
    st.caption(
        f"📅 Relatório: **{selected['report_date']}** | "
        f"Base: **{basis}** | "
        f"Jogadores: **{len(metrics):,}** | "
        f"Imports: **{n_import}**{delta_label}"
    )

    tabs = st.tabs([
        "⚔️ KP Geral", "🎯 Metas",
        "💀 Kill Points", "🛡️ Death Points", "📊 Combined",
        "📈 Histórico", "👥 Jogadores", "📁 Imports", "❓ Como usar",
    ])

    with tabs[0]: show_kp_metrics(metrics, group_power)
    with tabs[1]: show_goals(
        metrics=metrics, goal_bands=goal_bands, storage=storage,
        is_admin=is_admin, admin_enabled=admin_enabled,
        storage_error=goal_storage_error,
    )
    with tabs[2]: show_points_tab(
        metrics, title="Kill Points", total_column="kill_points",
        detail_columns=["t5_kills", "t4_kills", "kill_points", "kill_share"],
    )
    with tabs[3]: show_points_tab(
        metrics, title="Death Points", total_column="death_points",
        detail_columns=["t5_deaths", "t4_deaths", "death_points", "death_share"],
    )
    with tabs[4]: show_combined(metrics)
    with tabs[5]: show_history(storage, imports, group_power)
    with tabs[6]: show_players(metrics)
    with tabs[7]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[8]: show_help()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar helpers
# ─────────────────────────────────────────────────────────────────────────────

def _empty_state() -> None:
    st.info("📤 Faça upload do primeiro arquivo `statsExport` para começar.")
    st.markdown("""
    **Como obter o statsExport:**
    1. Abra Rise of Kingdoms
    2. Vá em **More > Kingdom > Kingdom Overview > Stats**
    3. Toque em **Export** e salve o arquivo `.xlsx`
    4. Faça upload aqui na barra lateral ←
    """)


def handle_upload(storage) -> None:
    uploaded = st.file_uploader("Upload statsExport", type=["xlsx", "xls"])
    if uploaded is None:
        return

    # Sanitize filename to prevent path traversal
    safe_name    = re.sub(r"[^\w.\-]", "_", uploaded.name)
    report_guess = extract_report_date_from_name(safe_name) or date.today()
    report_date  = st.date_input("Data do relatório", value=report_guess)

    if not st.button("💾 Salvar relatório", type="primary"):
        return

    with st.spinner("Processando..."):
        try:
            file_bytes = uploaded.getvalue()
            if len(file_bytes) > 50 * 1024 * 1024:  # 50 MB guard
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
        st.success(f"✅ {len(stats):,} jogadores salvos!")
    else:
        st.warning("⚠️ Este arquivo já foi importado.")
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


def load_previous_report(storage, imports: pd.DataFrame, selected: pd.Series) -> pd.DataFrame | None:
    # Sort by (report_date, imported_at) to handle ties correctly
    ordered   = imports.sort_values(
        ["report_date", "imported_at"], ascending=[True, True]
    ).reset_index(drop=True)
    positions = ordered.index[ordered["id"].eq(selected["id"])].tolist()
    if not positions or positions[0] == 0:
        return None
    prev_id = ordered.loc[positions[0] - 1, "id"]
    # Do not use the same import as previous (same-date edge case)
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
    st.divider()
    st.header("🔒 Admin")
    pwd = get_secret("ADMIN_PASSWORD")
    if not pwd:
        st.caption("Edição bloqueada. Configure ADMIN_PASSWORD nos Secrets para ativar.")
        return False, False
    entered = st.text_input("Senha admin", type="password")
    if is_admin_authenticated(pwd, entered):
        st.success("✅ Admin ativado")
        return True, True
    if entered:
        st.error("❌ Senha incorreta")
    return True, False


def get_secret(name: str) -> str | None:
    val = os.getenv(name)
    if val:
        return val
    try:
        val = st.secrets.get(name)
    except Exception:
        val = None
    return str(val) if val else None


# ─────────────────────────────────────────────────────────────────────────────
# Tab: KP Geral
# ─────────────────────────────────────────────────────────────────────────────

def show_kp_metrics(metrics: pd.DataFrame, group_power: int) -> None:
    kill_total     = int(metrics["kill_points"].sum())
    death_total    = int(metrics["death_points"].sum())
    combined_total = int(metrics["combined_points"].sum())
    group_dkpi     = combined_total / group_power if group_power else 0.0
    active_players = int((metrics["combined_points"] > 0).sum())
    participation  = active_players / len(metrics) if len(metrics) else 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("DKPi do Grupo",    format_dkpi(group_dkpi))
    c2.metric("Combined Points",  format_int(combined_total))
    c3.metric("Kill Points",      format_int(kill_total))
    c4.metric("Death Points",     format_int(death_total))
    c5.metric("Jogadores Ativos", format_int(active_players))
    c6.metric("Participação",     format_percent(participation))

    ranked = add_rank(metrics, "combined_points")
    _top3_medals(ranked)

    st.divider()

    if px is not None and (kill_total + death_total) > 0:
        left, right = st.columns([1, 2])
        with left:
            fig = px.pie(
                values=[kill_total, death_total],
                names=["Kill Points", "Death Points"],
                hole=0.55,
                color_discrete_sequence=[THEME_KILL, THEME_DEATH],
                title="Composição dos pontos",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        with right:
            show_bar(ranked.head(20), "combined_points", "Top 20 — Combined Points")
    else:
        show_bar(ranked.head(20), "combined_points", "Top 20 — Combined Points")

    st.divider()
    st.subheader("Ranking completo")

    # Pagination
    page_size = st.selectbox("Jogadores por página", [25, 50, 100, 200], index=0, key="kp_page_size")
    total_pages = max(1, -(-len(ranked) // page_size))  # ceiling division
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, key="kp_page")
    start_i = (page - 1) * page_size
    st.caption(f"Mostrando {start_i + 1}–{min(start_i + page_size, len(ranked))} de {len(ranked):,} jogadores")
    st.dataframe(display_table(ranked.iloc[start_i: start_i + page_size]), use_container_width=True, hide_index=True)


def _top3_medals(ranked: pd.DataFrame) -> None:
    if ranked.empty:
        return
    medals = ["🥇", "🥈", "🥉"]
    cols   = st.columns(3)
    for i, (_, row) in enumerate(ranked.head(3).iterrows()):
        cols[i].metric(
            label=f"{medals[i]} {row['username']}",
            value=format_int(int(row["combined_points"])),
            help=f"Personal DKPi: {format_dkpi(float(row['personal_dkpi']))} | Power: {format_int(int(row['power']))}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Metas
# ─────────────────────────────────────────────────────────────────────────────

def show_goals(*, metrics, goal_bands, storage, is_admin, admin_enabled, storage_error) -> None:
    if storage_error:
        st.error("Configuração de metas não pôde ser carregada. Rode o schema do Supabase atualizado.")
        st.caption(storage_error)

    gp      = calculate_goal_progress(metrics, goal_bands)
    summary = summarize_goal_bands(gp)

    t_pts = int(gp["target_points"].sum())  if not gp.empty else 0
    c_pts = int(gp["combined_points"].sum()) if not gp.empty else 0
    gap   = int(gp["gap_to_goal"].sum())    if not gp.empty else 0
    met   = int((gp["goal_status"] == "Met").sum()) if not gp.empty else 0
    pct   = c_pts / t_pts if t_pts else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Progresso Geral", format_percent(pct))
    c2.metric("Cumpriram Meta",  f"{met}/{len(gp):,}")
    c3.metric("Target Points",  format_int(t_pts))
    c4.metric("Pontos Atuais",  format_int(c_pts))
    c5.metric("Gap Total",      format_int(gap))

    if not gp.empty and px is not None:
        left, right = st.columns(2)
        with left:
            band_counts = (
                gp.groupby("power_band")["character_id"].count()
                .reset_index().rename(columns={"character_id": "players"})
            )
            fig = px.pie(band_counts, names="power_band", values="players",
                         title="Jogadores por faixa de power", hole=0.45)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        with right:
            status_counts = (
                gp.groupby("goal_status")["character_id"].count()
                .reset_index().rename(columns={"character_id": "players"})
            )
            color_map = {
                "Met": "#22c55e", "In Progress": "#eab308",
                "No Points": "#ef4444", "No Target": "#94a3b8", "Unassigned": "#64748b",
            }
            fig2 = px.bar(
                status_counts, x="goal_status", y="players",
                color="goal_status", color_discrete_map=color_map,
                title="Jogadores por status de meta",
            )
            fig2.update_layout(showlegend=False, xaxis_title="", yaxis_title="Jogadores")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Resumo por faixa de power")
    st.dataframe(format_goal_summary(summary), use_container_width=True, hide_index=True)

    over_goal = gp.sort_values("over_goal_points", ascending=False).head(15)
    needs_pts = gp[gp["gap_to_goal"].gt(0)].sort_values("gap_to_goal", ascending=False).head(15)

    left2, right2 = st.columns(2)
    with left2:
        st.subheader("🏆 Mais acima da meta")
        if over_goal.empty or int(over_goal["over_goal_points"].sum()) <= 0:
            st.info("Nenhum jogador acima da meta ainda.")
        else:
            show_bar(over_goal, "over_goal_points", "Acima da meta")
    with right2:
        st.subheader("⚠️ Maiores gaps")
        if needs_pts.empty:
            st.success("Todos os jogadores visíveis cumpriram a meta! 🎉")
        else:
            show_bar(needs_pts, "gap_to_goal", "Gap até a meta")

    st.subheader("Tabela de metas por jogador")
    statuses    = ["Todos", "Met", "In Progress", "No Points", "No Target"]
    sf          = st.selectbox("Filtrar por status", statuses, key="goal_sf")
    filtered_gp = gp if sf == "Todos" else gp[gp["goal_status"] == sf]
    st.dataframe(format_goal_table(filtered_gp), use_container_width=True, hide_index=True)

    # Export goal table
    if not filtered_gp.empty:
        csv = filtered_gp.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Exportar metas CSV", data=csv,
                           file_name="rok_metas.csv", mime="text/csv")

    st.divider()
    st.subheader("🛠️ Configurar faixas de meta")
    if not admin_enabled:
        st.info("Edição bloqueada. Configure ADMIN_PASSWORD para habilitar.")
        st.dataframe(format_band_table(goal_bands), use_container_width=True, hide_index=True)
        return
    if not is_admin:
        st.info("Digite a senha admin na barra lateral para editar.")
        st.dataframe(format_band_table(goal_bands), use_container_width=True, hide_index=True)
        return

    edited = st.data_editor(
        goal_bands, use_container_width=True, hide_index=True, num_rows="dynamic",
        column_config={
            "band_id":     st.column_config.TextColumn("Band ID", required=True),
            "label":       st.column_config.TextColumn("Label", required=True),
            "min_power":   st.column_config.NumberColumn("Min Power", min_value=0, step=1_000_000, required=True),
            "max_power":   st.column_config.NumberColumn("Max Power", min_value=0, step=1_000_000),
            "target_dkpi": st.column_config.NumberColumn("Target DKPi", min_value=0.0, step=0.001, format="%.4f"),
            "sort_order":  st.column_config.NumberColumn("Ordem", min_value=0, step=1, required=True),
        }, key="band_editor",
    )
    s1, s2 = st.columns([1, 3])
    with s1:
        if st.button("💾 Salvar metas", type="primary"):
            try:
                storage.save_goal_bands(edited)
                st.success("Metas salvas!")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro ao salvar: {exc}")
    with s2:
        if st.button("🔄 Restaurar preset Balanceado"):
            try:
                storage.reset_goal_bands()
                st.success("Preset Balanceado restaurado!")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Kill / Death Points
# ─────────────────────────────────────────────────────────────────────────────

def show_points_tab(metrics: pd.DataFrame, *, title: str, total_column: str, detail_columns: list[str]) -> None:
    total = int(metrics[total_column].sum())
    top   = metrics.sort_values(total_column, ascending=False).head(20)

    c1, c2, c3 = st.columns(3)
    c1.metric(title, format_int(total))
    c2.metric("Top Player", top.iloc[0]["username"] if not top.empty else "—")
    c3.metric("Top Score",  format_int(int(top.iloc[0][total_column])) if not top.empty else "0")

    show_bar(top, total_column, f"Top 20 — {title}")
    cols = ["username", "character_id", "power", *detail_columns]
    st.dataframe(
        metrics[[c for c in cols if c in metrics.columns]].rename(columns=DISPLAY_NAMES),
        use_container_width=True, hide_index=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Combined
# ─────────────────────────────────────────────────────────────────────────────

def show_combined(metrics: pd.DataFrame) -> None:
    top = metrics.sort_values("combined_points", ascending=False).head(20)
    c1, c2, c3 = st.columns(3)
    c1.metric("Combined Total", format_int(int(metrics["combined_points"].sum())))
    c2.metric("De Kills",       format_int(int(metrics["kill_points"].sum())))
    c3.metric("De Deaths",      format_int(int(metrics["death_points"].sum())))

    if not top.empty and px is not None:
        melted = top[["username", "kill_points", "death_points"]].melt(
            id_vars="username", var_name="Tipo", value_name="Pontos"
        )
        melted["Tipo"] = melted["Tipo"].map({"kill_points": "Kill Points", "death_points": "Death Points"})
        fig = px.bar(
            melted, x="Pontos", y="username", color="Tipo", orientation="h",
            title="Kill + Death por jogador (Top 20)",
            color_discrete_map={"Kill Points": THEME_KILL, "Death Points": THEME_DEATH},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    else:
        show_bar(top, "combined_points", "Top 20 — Combined Points")

    st.dataframe(display_table(add_rank(metrics, "combined_points")), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Histórico
# ─────────────────────────────────────────────────────────────────────────────

def show_history(storage, imports: pd.DataFrame, group_power: int) -> None:
    st.subheader("📈 Evolução histórica do reino")

    if len(imports) < 2:
        st.info("Importe pelo menos 2 relatórios para ver o histórico de evolução.")
        return

    ordered = imports.sort_values(["report_date", "imported_at"], ascending=[True, True]).reset_index(drop=True)

    # Build time series of kingdom-level aggregates
    rows = []
    for _, imp in ordered.iterrows():
        stats   = storage.load_stats(imp["id"])
        metrics = calculate_metrics(stats, group_power=group_power)
        rows.append({
            "Data":            imp["report_date"],
            "Import ID":       imp["id"],
            "Jogadores":       len(metrics),
            "Combined Points": int(metrics["combined_points"].sum()),
            "Kill Points":     int(metrics["kill_points"].sum()),
            "Death Points":    int(metrics["death_points"].sum()),
            "DKPi":            metrics["combined_points"].sum() / group_power if group_power else 0,
            "Ativos":          int((metrics["combined_points"] > 0).sum()),
        })

    history = pd.DataFrame(rows)

    if px is not None:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.line(
                history, x="Data", y="Combined Points",
                title="Combined Points ao longo do tempo",
                markers=True, color_discrete_sequence=[THEME_COMBO],
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.line(
                history, x="Data", y="DKPi",
                title="DKPi do grupo ao longo do tempo",
                markers=True, color_discrete_sequence=[THEME_GREEN],
            )
            st.plotly_chart(fig2, use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            melted = history[["Data", "Kill Points", "Death Points"]].melt(
                id_vars="Data", var_name="Tipo", value_name="Pontos"
            )
            fig3 = px.bar(
                melted, x="Data", y="Pontos", color="Tipo", barmode="stack",
                title="Kill vs Death Points por período",
                color_discrete_map={"Kill Points": THEME_KILL, "Death Points": THEME_DEATH},
            )
            st.plotly_chart(fig3, use_container_width=True)
        with col4:
            fig4 = px.line(
                history, x="Data", y="Ativos",
                title="Jogadores ativos ao longo do tempo",
                markers=True, color_discrete_sequence=[THEME_KILL],
            )
            st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Comparação entre dois relatórios")
    labels  = ordered["label"].tolist()
    c1, c2  = st.columns(2)
    with c1:
        label_a = st.selectbox("Relatório base", labels, index=0, key="hist_a")
    with c2:
        label_b = st.selectbox("Relatório comparado", labels, index=min(1, len(labels) - 1), key="hist_b")

    id_a = ordered.loc[ordered["label"].eq(label_a), "id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(label_b), "id"].iloc[0]

    if id_a == id_b:
        st.warning("Selecione dois relatórios diferentes para comparar.")
        return

    stats_a  = storage.load_stats(id_a)
    stats_b  = storage.load_stats(id_b)
    delta_df = compute_period_deltas(stats_b, stats_a)
    metrics  = calculate_metrics(delta_df, group_power=group_power)

    top = metrics.sort_values("combined_points", ascending=False).head(15)
    if not top.empty:
        show_bar(top, "combined_points", f"Top 15 — Ganho no período ({label_a} → {label_b})")
    st.dataframe(display_table(add_rank(metrics, "combined_points")), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Jogadores
# ─────────────────────────────────────────────────────────────────────────────

def show_players(metrics: pd.DataFrame) -> None:
    ranked = add_rank(metrics, "combined_points")

    # Extra derived metric: death/kill ratio
    kill_sum  = ranked["kill_points"].replace(0, pd.NA)
    ranked["death_kill_ratio"] = (ranked["death_points"] / kill_sum).fillna(0.0).round(3)

    if px is not None and not ranked.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.scatter(
                ranked, x="power", y="combined_points",
                hover_name="username",
                color="personal_dkpi",
                color_continuous_scale="Viridis",
                title="Power vs Combined Points (cor = Personal DKPi)",
                labels={"power": "Power", "combined_points": "Combined Points", "personal_dkpi": "Personal DKPi"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig2 = px.scatter(
                ranked, x="kill_points", y="death_points",
                hover_name="username",
                color="combined_points",
                color_continuous_scale="Plasma",
                title="Kill Points vs Death Points",
                labels={"kill_points": "Kill Points", "death_points": "Death Points"},
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Tabela completa de jogadores")
    cols_extra = DISPLAY_COLUMNS + ["death_kill_ratio"]
    avail      = [c for c in cols_extra if c in ranked.columns]
    st.dataframe(
        ranked[avail].rename(columns=DISPLAY_NAMES),
        use_container_width=True, hide_index=True,
    )

    csv = metrics.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Baixar CSV completo", data=csv,
                       file_name="rok_kp_metrics.csv", mime="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Imports
# ─────────────────────────────────────────────────────────────────────────────

def show_imports(imports: pd.DataFrame, storage, *, is_admin: bool, admin_enabled: bool) -> None:
    st.subheader("Relatórios importados")
    st.dataframe(
        imports[["report_date", "filename", "row_count", "imported_at"]].rename(columns={
            "report_date": "Data", "filename": "Arquivo",
            "row_count": "Jogadores", "imported_at": "Importado em",
        }),
        use_container_width=True, hide_index=True,
    )

    if admin_enabled and is_admin:
        st.divider()
        st.subheader("🗑️ Deletar import")
        st.warning("⚠️ Irreversível — remove o import e todos os dados de jogadores associados.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Selecionar import", ["— selecionar —", *labels], key="del_sel")
        if to_del != "— selecionar —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            col_confirm, _ = st.columns([1, 3])
            with col_confirm:
                if st.button("🗑️ Confirmar exclusão", type="secondary"):
                    if storage.delete_import(row["id"]):
                        st.success(f"Import deletado: {to_del}")
                        st.rerun()
                    else:
                        st.error("Import não encontrado.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Como usar
# ─────────────────────────────────────────────────────────────────────────────

def show_help() -> None:
    st.header("❓ Como usar o dashboard")

    st.markdown("""
## 1. Obter o arquivo de export do RoK

1. No jogo, vá em **More → Kingdom → Kingdom Overview → Stats**
2. Toque em **Export** (ícone de download no canto superior)
3. Salve o arquivo `.xlsx` ou `.xls` no seu celular/PC

---

## 2. Fazer upload

- Na **barra lateral esquerda**, clique em **Upload statsExport**
- Selecione o arquivo exportado
- Confirme ou corrija a **data do relatório**
- Clique em **Salvar relatório**

> 💡 **Dica:** Faça uploads periódicos (ex: a cada KVK). O dashboard mantém histórico e permite comparar períodos.

---

## 3. Entender as métricas

| Métrica | Fórmula |
|---|---|
| Kill Points | T4 Kills × 5 + T5 Kills × 10 |
| Death Points | T4 Deaths × 30 + T5 Deaths × 70 |
| Combined Points | Kill Points + Death Points |
| DKPi (grupo) | Combined Points / Power inicial do grupo |
| Personal DKPi | Combined Points / Power próprio do jogador |
| Death/Kill Ratio | Death Points / Kill Points |

---

## 4. Delta do período

Se você tiver **2 ou mais relatórios** importados, aparece a opção **"Delta do período"** na barra lateral.

- **Totais do relatório:** mostra os valores acumulados do relatório selecionado
- **Delta do período:** mostra apenas o que foi **ganho entre o relatório anterior e o atual** — ideal para medir desempenho de um KVK específico

---

## 5. Aba Metas (Goals)

- Cada jogador recebe uma **meta de pontos** baseada na sua faixa de power
- A liderança pode **editar as faixas** (requer senha admin)
- Status possíveis: 🟢 Met | 🟡 In Progress | 🔴 No Points | ⚪ No Target

---

## 6. Aba Histórico

- Visualize a **evolução do reino** ao longo de múltiplos KVKs
- Compare dois relatórios específicos para ver o delta de qualquer período

---

## 7. Filtros disponíveis

| Filtro | Onde | Para quê |
|---|---|---|
| Buscar jogador | Sidebar | Encontrar um jogador específico |
| Power mínimo | Sidebar | Excluir jogadores com pouco poder |
| Power inicial do grupo | Sidebar | Ajustar o cálculo do DKPi |
| Status de meta | Aba Metas | Focar em quem ainda não cumpriu |

---

## 8. Para a liderança — configurar online (gratuito)

### Passo 1 — GitHub
1. Crie uma conta em [github.com](https://github.com) e crie um repositório **privado** chamado `rok-dashboard`
2. Faça upload de todos os arquivos deste projeto

### Passo 2 — Supabase (banco de dados online)
1. Crie uma conta em [supabase.com](https://supabase.com) (gratuito)
2. Crie um projeto → vá em **SQL Editor** → cole e execute `supabase_schema.sql`
3. Copie a **Project URL** e a **service_role key**

### Passo 3 — Streamlit Cloud
1. Crie conta em [streamlit.io](https://streamlit.io) (login com GitHub)
2. **New app** → selecione o repositório e `app.py`
3. Em **Advanced settings → Secrets**, adicione:

```toml
SUPABASE_URL = "https://seu-projeto.supabase.co"
SUPABASE_KEY = "sua-service-role-key"
ADMIN_PASSWORD = "senha-forte-que-so-a-lideranca-sabe"
```

4. **Deploy** — em 1-2 minutos o dashboard estará online!

---

## 9. Rodando localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Sem Supabase, os dados ficam em `data/rok_dashboard.sqlite`.

---

> 🔒 **Segurança:** Nunca coloque a `SUPABASE_KEY` no GitHub. Use sempre os Secrets do Streamlit Cloud.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

def show_bar(frame: pd.DataFrame, value_column: str, title: str) -> None:
    if frame.empty:
        st.info("Sem dados para exibir.")
        return
    ordered = frame.sort_values(value_column, ascending=True)
    if px is not None:
        fig = px.bar(
            ordered, x=value_column, y="username", orientation="h", title=title,
            labels={value_column: DISPLAY_NAMES.get(value_column, value_column), "username": ""},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(ordered.set_index("username")[value_column])


# ─────────────────────────────────────────────────────────────────────────────
# Table formatters
# ─────────────────────────────────────────────────────────────────────────────

def display_table(frame: pd.DataFrame) -> pd.DataFrame:
    avail = [c for c in DISPLAY_COLUMNS if c in frame.columns]
    out   = frame[avail].copy()
    for col in ("dkpi", "personal_dkpi"):
        if col in out:
            out[col] = out[col].map(format_dkpi)
    for col in ("kill_share", "death_share", "combined_share"):
        if col in out:
            out[col] = out[col].map(format_percent)
    return out.rename(columns=DISPLAY_NAMES)


def format_goal_table(frame: pd.DataFrame) -> pd.DataFrame:
    avail = [c for c in GOAL_COLUMNS if c in frame.columns]
    out   = frame[avail].copy()
    if "target_dkpi" in out:
        out["target_dkpi"] = out["target_dkpi"].map(lambda v: f"{float(v):.4f}")
    if "progress_pct" in out:
        out["progress_pct"] = out["progress_pct"].map(format_percent)
    if "goal_status" in out:
        out["goal_status"] = out["goal_status"].map(lambda s: f"{STATUS_ICON.get(s, '')} {s}")
    return out.rename(columns=DISPLAY_NAMES)


def format_goal_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    if "progress_pct" in out:
        out["progress_pct"] = out["progress_pct"].map(format_percent)
    return out.rename(columns={
        "power_band": "Faixa", "players": "Jogadores", "met_goal": "Cumpriram",
        "no_points": "Sem Pontos", "combined_points": "Combined Points",
        "target_points": "Target Points", "gap_to_goal": "Gap", "progress_pct": "Progresso",
    })


def format_band_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["target_dkpi"] = out["target_dkpi"].map(lambda v: f"{float(v):.4f}")
    return out.rename(columns={
        "band_id": "ID", "label": "Label", "min_power": "Min Power",
        "max_power": "Max Power", "target_dkpi": "Target DKPi", "sort_order": "Ordem",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Formatting utilities
# ─────────────────────────────────────────────────────────────────────────────

def format_percent(value: int | float) -> str:
    return f"{float(value) * 100:.1f}%"


def format_int(value: int | float) -> str:
    return f"{value:,.0f}"


def format_dkpi(value: int | float) -> str:
    f = float(value)
    if f == 0.0:
        return "0.0000"
    if f < 0.0001:
        return f"{f:.2e}"
    return f"{f:.6f}"


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
