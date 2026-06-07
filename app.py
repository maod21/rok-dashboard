from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
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

# ══════════════════════════════════════════════════════════════════════════════
# Page config
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ── adaptável a modo claro E escuro via media query + variáveis CSS ──
st.markdown("""
<style>
/* ── Tokens de cor ── */
:root {
  --c-bg:        #ffffff;
  --c-surface:   #f8fafc;
  --c-border:    rgba(0,0,0,0.10);
  --c-text:      #0f172a;
  --c-muted:     #64748b;
  --c-accent:    #2563eb;     /* azul principal */
  --c-gold:      #b45309;
  --c-ok:        #15803d;
  --c-ok-bg:     #f0fdf4;
  --c-ok-border: #86efac;
  --c-warn:      #92400e;
  --c-warn-bg:   #fffbeb;
  --c-warn-border:#fcd34d;
  --c-err:       #991b1b;
  --c-err-bg:    #fff1f2;
  --c-err-border:#fca5a5;
  --c-t5:        #b45309;
  --c-t4:        #9a3412;
  --c-t3:        #6d28d9;
  --c-t2:        #1d4ed8;
  --c-t1:        #475569;
}
@media (prefers-color-scheme: dark) {
  :root {
    --c-bg:        #0f172a;
    --c-surface:   #1e293b;
    --c-border:    rgba(255,255,255,0.09);
    --c-text:      #f1f5f9;
    --c-muted:     #94a3b8;
    --c-accent:    #60a5fa;
    --c-gold:      #fbbf24;
    --c-ok:        #4ade80;
    --c-ok-bg:     #052e16;
    --c-ok-border: #166534;
    --c-warn:      #fcd34d;
    --c-warn-bg:   #1c1400;
    --c-warn-border:#854d0e;
    --c-err:       #f87171;
    --c-err-bg:    #1a0000;
    --c-err-border:#991b1b;
    --c-t5:        #fbbf24;
    --c-t4:        #fb923c;
    --c-t3:        #a78bfa;
    --c-t2:        #60a5fa;
    --c-t1:        #94a3b8;
  }
}
/* Override Streamlit dark-mode detection via data attribute */
[data-theme="dark"] {
  --c-bg:#0f172a; --c-surface:#1e293b; --c-border:rgba(255,255,255,0.09);
  --c-text:#f1f5f9; --c-muted:#94a3b8; --c-accent:#60a5fa; --c-gold:#fbbf24;
  --c-ok:#4ade80; --c-ok-bg:#052e16; --c-ok-border:#166534;
  --c-warn:#fcd34d; --c-warn-bg:#1c1400; --c-warn-border:#854d0e;
  --c-err:#f87171; --c-err-bg:#1a0000; --c-err-border:#991b1b;
  --c-t5:#fbbf24; --c-t4:#fb923c; --c-t3:#a78bfa; --c-t2:#60a5fa; --c-t1:#94a3b8;
}

/* ── Layout ── */
.main .block-container { padding-top:1rem; padding-bottom:2rem; max-width:1440px; }

/* ── Metric cards ── */
[data-testid="stMetric"] {
  background: var(--c-surface) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: 12px;
  padding: 16px 18px !important;
  position: relative;
  overflow: hidden;
}
[data-testid="stMetric"]::before {
  content:''; position:absolute; top:0; left:0; right:0; height:3px;
  background: linear-gradient(90deg, var(--c-accent), var(--c-gold));
}
[data-testid="stMetricLabel"] {
  font-size:0.68rem !important; text-transform:uppercase;
  letter-spacing:.09em; font-weight:700; color:var(--c-muted) !important;
}
[data-testid="stMetricValue"] {
  font-size:1.4rem !important; font-weight:800; color:var(--c-text) !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] button {
  font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em;
}

/* ── Header banner ── */
.hdr {
  display:flex; align-items:center; gap:14px;
  padding:14px 20px; margin-bottom:14px;
  background:var(--c-surface);
  border:1px solid var(--c-border);
  border-left:4px solid var(--c-accent);
  border-radius:12px;
}
.hdr-icon { font-size:2rem; line-height:1; }
.hdr-title { font-size:1.3rem; font-weight:800; color:var(--c-text); margin:0; }
.hdr-sub   { font-size:0.72rem; color:var(--c-muted); margin:2px 0 0; }

/* ── Weight pills ── */
.wpills { display:flex; gap:6px; flex-wrap:wrap; margin:0 0 16px; }
.wp { padding:3px 10px; border-radius:20px; font-size:0.68rem; font-weight:700;
      background:var(--c-surface); border:1px solid var(--c-border); color:var(--c-muted); }
.wp-t5{color:var(--c-t5);border-color:var(--c-t5);opacity:.85;}
.wp-t4{color:var(--c-t4);border-color:var(--c-t4);opacity:.85;}
.wp-t3{color:var(--c-t3);border-color:var(--c-t3);opacity:.85;}
.wp-t2{color:var(--c-t2);border-color:var(--c-t2);opacity:.85;}
.wp-t1{color:var(--c-t1);border-color:var(--c-t1);opacity:.85;}

/* ── Search bar ── */
.search-wrap { position:relative; margin-bottom:12px; }
.search-clear {
  position:absolute; right:10px; top:50%; transform:translateY(-50%);
  cursor:pointer; font-size:1rem; color:var(--c-muted);
  background:none; border:none; padding:0; line-height:1;
}

/* ── Filter bar ── */
.filter-bar {
  display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;
  padding:12px 16px; background:var(--c-surface);
  border:1px solid var(--c-border); border-radius:10px; margin-bottom:14px;
}

/* ── Member card ── */
.mc {
  border:1px solid var(--c-border); border-radius:14px;
  padding:16px 20px; margin-bottom:10px;
  background:var(--c-surface);
  position:relative; overflow:hidden;
  transition: box-shadow .15s, border-color .15s;
}
.mc:hover { box-shadow:0 4px 24px rgba(0,0,0,0.10); }
.mc.ok   { border-left:5px solid var(--c-ok);   background:var(--c-ok-bg);   }
.mc.warn { border-left:5px solid var(--c-warn);  background:var(--c-warn-bg); }
.mc.err  { border-left:5px solid var(--c-err);   background:var(--c-err-bg);  }

.mc-hdr  { display:flex; align-items:center; gap:10px; margin-bottom:12px; flex-wrap:wrap; }
.mc-rank { font-size:1rem; font-weight:800; color:var(--c-muted); min-width:28px; }
.mc-name { font-size:1rem; font-weight:700; color:var(--c-text); flex:1; min-width:120px; }
.mc-pow  { font-size:0.75rem; color:var(--c-muted); }
.mc-band { font-size:0.65rem; font-weight:700; padding:2px 8px;
           border-radius:20px; background:var(--c-border); color:var(--c-muted);
           letter-spacing:.05em; white-space:nowrap; }
.mc-id   { font-size:0.62rem; color:var(--c-muted); font-family:monospace; }
.mc-stat { font-size:0.7rem; font-weight:800; padding:3px 10px;
           border-radius:20px; letter-spacing:.05em; white-space:nowrap; }
.mc-stat.ok   { background:var(--c-ok-bg);   color:var(--c-ok);   border:1px solid var(--c-ok-border);   }
.mc-stat.warn { background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-border); }
.mc-stat.err  { background:var(--c-err-bg);  color:var(--c-err);  border:1px solid var(--c-err-border);  }

.mc-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.mc-lbl  { font-size:0.63rem; font-weight:700; text-transform:uppercase;
           letter-spacing:.08em; color:var(--c-muted); margin-bottom:3px; }
.mc-val  { font-size:0.92rem; font-weight:700; color:var(--c-text); }

/* progress bar */
.pb-wrap { margin-top:5px; }
.pb-meta { display:flex; justify-content:space-between; font-size:0.6rem; color:var(--c-muted); margin-bottom:3px; }
.pb-trk  { background:var(--c-border); border-radius:99px; height:6px; overflow:hidden; }
.pb-fill { height:100%; border-radius:99px; transition:width .4s; }
.pb-fill.ok   { background:linear-gradient(90deg,#15803d,#22c55e); }
.pb-fill.warn { background:linear-gradient(90deg,#92400e,#f59e0b); }
.pb-fill.err  { background:linear-gradient(90deg,#991b1b,#ef4444); }
.pb-gap  { font-size:0.62rem; color:var(--c-muted); margin-top:3px; }

/* tier pills */
.tp-row { display:flex; gap:5px; flex-wrap:wrap; margin-top:5px; }
.tp { padding:2px 8px; border-radius:5px; font-size:0.67rem; font-weight:700; }
.tp-t5k{background:color-mix(in srgb,var(--c-t5) 15%,transparent);color:var(--c-t5);border:1px solid color-mix(in srgb,var(--c-t5) 30%,transparent);}
.tp-t4k{background:color-mix(in srgb,var(--c-t4) 15%,transparent);color:var(--c-t4);border:1px solid color-mix(in srgb,var(--c-t4) 30%,transparent);}
.tp-t3k{background:color-mix(in srgb,var(--c-t3) 15%,transparent);color:var(--c-t3);border:1px solid color-mix(in srgb,var(--c-t3) 30%,transparent);}
.tp-t2k{background:color-mix(in srgb,var(--c-t2) 15%,transparent);color:var(--c-t2);border:1px solid color-mix(in srgb,var(--c-t2) 30%,transparent);}
.tp-t1k{background:color-mix(in srgb,var(--c-t1) 12%,transparent);color:var(--c-t1);border:1px solid color-mix(in srgb,var(--c-t1) 25%,transparent);}
.tp-d   {background:color-mix(in srgb,var(--c-muted) 10%,transparent);color:var(--c-muted);border:1px solid color-mix(in srgb,var(--c-muted) 20%,transparent);}

/* ── Section header ── */
.sh {
  font-size:0.65rem; font-weight:800; text-transform:uppercase;
  letter-spacing:.1em; color:var(--c-muted);
  border-bottom:1px solid var(--c-border);
  padding-bottom:5px; margin:12px 0 10px;
}

/* ── Date range chip ── */
.date-chip {
  display:inline-flex; align-items:center; gap:6px;
  padding:4px 12px; border-radius:20px;
  background:var(--c-surface); border:1px solid var(--c-accent);
  font-size:0.72rem; font-weight:600; color:var(--c-accent);
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Storage
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_storage():
    return create_storage()


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

STATUS_EMOJI = {"Aprovado": "✅", "Pendente": "🟡", "Abaixo da meta": "❌"}
STATUS_CLS   = {"Aprovado": "ok", "Pendente": "warn", "Abaixo da meta": "err"}


def main() -> None:
    storage = get_storage()

    # Header
    st.markdown("""
    <div class="hdr">
      <div class="hdr-icon">⚔️</div>
      <div>
        <p class="hdr-title">K1602 · KP Dashboard</p>
        <p class="hdr-sub">Kingdom Kill Points Tracker — Rise of Kingdoms</p>
      </div>
    </div>
    <div class="wpills">
      <span class="wp wp-t5">T5 Kill × 20</span>
      <span class="wp wp-t4">T4 Kill × 10</span>
      <span class="wp wp-t3">T3 Kill × 4</span>
      <span class="wp wp-t2">T2 Kill × 2</span>
      <span class="wp wp-t1">T1 Kill × 0.2</span>
      <span class="wp">Morte T5 = 2× T4</span>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown(f"**Storage:** `{storage.label}`")
        st.markdown('<div class="sh">📂 Relatórios</div>', unsafe_allow_html=True)
        handle_upload(storage)

    imports = storage.list_imports()
    if imports.empty:
        _empty_state()
        return

    imports  = prepare_imports(imports)
    selected = select_report(imports)
    current  = storage.load_stats(selected["id"])
    previous = load_previous_report(storage, imports, selected)

    basis_options = ["Totais do relatório"]
    if previous is not None and not previous.empty:
        basis_options.insert(0, "Delta do período")

    with st.sidebar:
        st.divider()
        st.markdown('<div class="sh">⚙️ Configuração</div>', unsafe_allow_html=True)
        basis     = st.radio("Base das métricas", basis_options, index=0)
        min_power = st.number_input("Power mínimo", min_value=0, value=0, step=1_000_000, format="%d")
        st.divider()
        admin_enabled, is_admin = admin_panel()

    stats_basis = compute_period_deltas(current, previous) if basis == "Delta do período" else current
    gp_default  = default_group_power(storage, imports)
    metrics_raw = calculate_metrics(stats_basis, group_power=gp_default)

    # Apply power filter
    if min_power > 0:
        metrics_raw = metrics_raw[
            pd.to_numeric(metrics_raw["power"], errors="coerce").fillna(0) >= min_power
        ]

    ranked_full = apply_goals(add_rank(metrics_raw, "kill_points"))

    n_import    = len(imports)
    delta_label = f" · +{n_import-1} anterior{'es' if n_import>2 else ''}" if n_import > 1 else ""
    st.caption(
        f"📅 **{selected['report_date']}** · Base: **{basis}** · "
        f"Membros: **{len(ranked_full):,}** · Imports: **{n_import}**{delta_label}"
    )

    tabs = st.tabs(["🏆 Ranking", "📊 Resumo", "📈 Histórico", "📁 Imports", "❓ Ajuda"])

    with tabs[0]: show_ranking(ranked_full)
    with tabs[1]: show_kingdom_summary(ranked_full)
    with tabs[2]: show_history(storage, imports, gp_default)
    with tabs[3]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[4]: show_help()


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar helpers
# ══════════════════════════════════════════════════════════════════════════════

def _empty_state():
    st.info("👈 Faça upload do primeiro statsExport na barra lateral para começar.")


def handle_upload(storage):
    pwd = get_secret("ADMIN_PASSWORD")
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False

    if not st.session_state.upload_auth:
        st.caption("🔒 Upload restrito à liderança")
        up_pwd = st.text_input("Senha", type="password", key="up_pwd", placeholder="Digite a senha...")
        if st.button("🔓 Desbloquear", use_container_width=True):
            if (not pwd) or is_admin_authenticated(pwd, up_pwd):
                st.session_state.upload_auth = True
                st.rerun()
            else:
                st.error("❌ Senha incorreta")
        return

    st.success("✅ Upload desbloqueado")
    if st.button("🔒 Bloquear", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False
        st.rerun()

    uploaded = st.file_uploader("Upload statsExport", type=["xlsx", "xls"])
    if not uploaded:
        return

    safe_name   = re.sub(r"[^\w.\-]", "_", uploaded.name)
    report_date = st.date_input("Data do relatório",
                                 value=extract_report_date_from_name(safe_name) or date.today())
    if not st.button("💾 Salvar", type="primary", use_container_width=True):
        return

    with st.spinner("Processando..."):
        try:
            fb = uploaded.getvalue()
            if len(fb) > 50 * 1024 * 1024:
                st.error("❌ Arquivo muito grande (max 50 MB).")
                return
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            _, created = storage.save_import(
                filename=safe_name, report_date=report_date.isoformat(),
                file_hash=file_sha256(fb), stats=stats,
            )
        except Exception as exc:
            st.error(f"❌ {exc}")
            return

    if created:
        st.success(f"✅ {len(stats):,} membros salvos!")
    else:
        st.warning("⚠️ Arquivo já importado.")
    st.rerun()


def prepare_imports(imports):
    out = imports.copy()
    out["report_date"] = pd.to_datetime(out["report_date"]).dt.date.astype(str)
    out["imported_at"] = out["imported_at"].astype(str)
    out["label"]       = out["report_date"] + " — " + out["filename"].astype(str)
    return out


def select_report(imports):
    labels = imports["label"].tolist()
    chosen = st.sidebar.selectbox("Relatório atual", labels, index=0)
    return imports.loc[imports["label"].eq(chosen)].iloc[0]


def load_previous_report(storage, imports, selected):
    ordered   = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    positions = ordered.index[ordered["id"].eq(selected["id"])].tolist()
    if not positions or positions[0] == 0:
        return None
    prev_id = ordered.loc[positions[0] - 1, "id"]
    return None if prev_id == selected["id"] else storage.load_stats(prev_id)


@st.cache_data(ttl=300)
def _cached_group_power(label, first_id):
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"], errors="coerce").fillna(0).sum())


def default_group_power(storage, imports):
    ordered  = imports.sort_values(["report_date", "imported_at"]).reset_index(drop=True)
    first_id = ordered.iloc[0]["id"]
    return _cached_group_power(storage.label, first_id)


def admin_panel():
    st.markdown('<div class="sh">🔒 Admin</div>', unsafe_allow_html=True)
    pwd = get_secret("ADMIN_PASSWORD")
    if not pwd:
        st.caption("Configure ADMIN_PASSWORD nos Secrets.")
        return False, False
    entered = st.text_input("Senha admin", type="password", key="adm_pwd")
    if is_admin_authenticated(pwd, entered):
        st.success("✅ Admin ativo")
        return True, True
    if entered:
        st.error("❌ Incorreta")
    return True, False


def get_secret(name):
    v = os.getenv(name)
    if v: return v
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return str(v) if v else None


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Ranking de Membros
# ══════════════════════════════════════════════════════════════════════════════

def show_ranking(ranked_full: pd.DataFrame) -> None:

    # ── Barra de busca + filtros inline ──────────────────────────────────────
    c_search, c_status, c_sort, c_view = st.columns([3, 2, 2, 1])

    with c_search:
        search = st.text_input(
            "🔍 Buscar membro",
            placeholder="Nome ou Character ID…",
            key="rank_search",
            label_visibility="collapsed",
        )

    with c_status:
        status_filter = st.selectbox(
            "Status",
            ["Todos", "✅ Aprovado", "🟡 Pendente", "❌ Abaixo da meta"],
            key="rank_sf",
            label_visibility="collapsed",
        )

    with c_sort:
        sort_by = st.selectbox(
            "Ordenar por",
            ["Kill Points ↓", "Power ↓", "% KP ↓", "% Mortes ↓", "Nome ↑"],
            key="rank_sort",
            label_visibility="collapsed",
        )

    with c_view:
        view_mode = st.radio(
            "Modo",
            ["🃏", "📋"],
            horizontal=True,
            key="rank_view",
            label_visibility="collapsed",
            help="🃏 Cards detalhados   📋 Tabela compacta",
        )

    # ── Filtro de datas ───────────────────────────────────────────────────────
    with st.expander("📅 Filtrar por data de importação", expanded=False):
        all_dates = sorted(ranked_full["imported_at"].dropna().astype(str).unique()) \
            if "imported_at" in ranked_full else []

        dc1, dc2, dc3 = st.columns([2, 2, 1])
        with dc1:
            date_from = st.date_input(
                "De", value=None, key="df_from",
                help="Filtra membros cujo import foi feito a partir desta data"
            )
        with dc2:
            date_to = st.date_input(
                "Até", value=None, key="df_to",
                help="Filtra membros cujo import foi feito até esta data"
            )
        with dc3:
            if st.button("✖ Limpar datas", use_container_width=True, key="clear_dates"):
                st.session_state.df_from = None
                st.session_state.df_to   = None
                st.rerun()

    # ── Aplicar filtros ───────────────────────────────────────────────────────
    df = ranked_full.copy()

    # Busca por nome ou ID
    if search and search.strip():
        needle = search.strip().lower()
        df = df[
            df["username"].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            | df["character_id"].astype(str).str.lower().str.contains(needle, regex=False, na=False)
        ]

    # Status
    if status_filter != "Todos":
        s = status_filter.split(" ", 1)[1]
        df = df[df["status"] == s]

    # Data
    if "imported_at" in df.columns and (date_from or date_to):
        df["_dt"] = pd.to_datetime(df["imported_at"], errors="coerce").dt.date
        if date_from:
            df = df[df["_dt"] >= date_from]
        if date_to:
            df = df[df["_dt"] <= date_to]
        df = df.drop(columns=["_dt"])

    # Ordenação
    sort_map = {
        "Kill Points ↓": ("kill_points", False),
        "Power ↓":       ("power",       False),
        "% KP ↓":        ("kp_pct",      False),
        "% Mortes ↓":    ("dead_pct",    False),
        "Nome ↑":        ("username",    True),
    }
    scol, sasc = sort_map[sort_by]
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    # ── Contador ─────────────────────────────────────────────────────────────
    active_filters = []
    if search.strip():       active_filters.append(f"busca: \"{search.strip()}\"")
    if status_filter != "Todos": active_filters.append(status_filter.split(" ",1)[1])
    if date_from:            active_filters.append(f"de {date_from}")
    if date_to:              active_filters.append(f"até {date_to}")
    filter_note = f" · filtros: {', '.join(active_filters)}" if active_filters else ""
    st.caption(f"Mostrando **{len(df):,}** de **{len(ranked_full):,}** membros{filter_note}")

    # ── Render ────────────────────────────────────────────────────────────────
    if view_mode == "🃏":
        # Paginação apenas para cards (evita lag com 500+ membros)
        page_size = st.selectbox("Cards por página", [25, 50, 100], index=0, key="rank_ps")
        total_pages = max(1, -(-len(df) // page_size))
        page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, key="rank_pg")
        start = (page - 1) * page_size
        _render_cards(df.iloc[start: start + page_size])
    else:
        _render_table(df)


def _render_cards(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        cls   = STATUS_CLS.get(row["status"], "err")
        emoji = STATUS_EMOJI.get(row["status"], "❌")

        kp_w   = min(float(row.get("kp_pct",   0)) * 100, 100)
        dead_w = min(float(row.get("dead_pct",  0)) * 100, 100)
        kp_gap   = int(row.get("kp_gap",       0))
        dead_gap = int(row.get("dead_gap_t4",  0))

        kp_gap_txt   = f"faltam {fmt_k(kp_gap)} KP"      if kp_gap   > 0 else "✓ meta atingida"
        dead_gap_txt = f"faltam {fmt_k(dead_gap)} (T4 eq.)" if dead_gap > 0 else "✓ meta atingida"

        t5d = int(row.get("t5_deaths", 0))

        st.markdown(f"""
        <div class="mc {cls}">
          <div class="mc-hdr">
            <div class="mc-rank">#{int(row['rank'])}</div>
            <div class="mc-name">{row['username']}</div>
            <div class="mc-pow">{fmt_m(int(row['power']))} power</div>
            <div class="mc-band">{row.get('power_band','—')}</div>
            <div class="mc-id">{row.get('character_id','')}</div>
            <div class="mc-stat {cls}">{emoji} {row['status']}</div>
          </div>

          <div class="mc-grid">
            <div>
              <div class="mc-lbl">Kill Points</div>
              <div class="mc-val">{fmt_int(int(row['kill_points']))}</div>
              <div class="pb-wrap">
                <div class="pb-meta">
                  <span>Meta {fmt_int(int(row['kp_goal']))}</span>
                  <span>{kp_w:.0f}%</span>
                </div>
                <div class="pb-trk"><div class="pb-fill {cls}" style="width:{kp_w:.1f}%"></div></div>
                <div class="pb-gap">{kp_gap_txt}</div>
              </div>
            </div>
            <div>
              <div class="mc-lbl">Mortes (equiv. T4)</div>
              <div class="mc-val">{fmt_int(int(row.get('dead_equiv',0)))}</div>
              <div class="pb-wrap">
                <div class="pb-meta">
                  <span>Meta {fmt_int(int(row['dead_t4_goal']))}</span>
                  <span>{dead_w:.0f}%</span>
                </div>
                <div class="pb-trk"><div class="pb-fill {cls}" style="width:{dead_w:.1f}%"></div></div>
                <div class="pb-gap">{dead_gap_txt}</div>
              </div>
            </div>
          </div>

          <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
              <div class="mc-lbl">Kills por tier</div>
              <div class="tp-row">
                <span class="tp tp-t5k">T5 {fmt_k(int(row.get('t5_kills',0)))}</span>
                <span class="tp tp-t4k">T4 {fmt_k(int(row.get('t4_kills',0)))}</span>
                <span class="tp tp-t3k">T3 {fmt_k(int(row.get('t3_kills',0)))}</span>
                <span class="tp tp-t2k">T2 {fmt_k(int(row.get('t2_kills',0)))}</span>
                <span class="tp tp-t1k">T1 {fmt_k(int(row.get('t1_kills',0)))}</span>
              </div>
            </div>
            <div>
              <div class="mc-lbl">Mortes por tier</div>
              <div class="tp-row">
                <span class="tp tp-t5k">T5 {fmt_k(t5d)}<span style="font-size:.58rem;opacity:.7"> ≡{fmt_k(t5d*2)}T4</span></span>
                <span class="tp tp-t4k">T4 {fmt_k(int(row.get('t4_deaths',0)))}</span>
                <span class="tp tp-t3k">T3 {fmt_k(int(row.get('t3_deaths',0)))}</span>
                <span class="tp tp-t2k">T2 {fmt_k(int(row.get('t2_deaths',0)))}</span>
                <span class="tp tp-t1k">T1 {fmt_k(int(row.get('t1_deaths',0)))}</span>
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)


def _render_table(df: pd.DataFrame) -> None:
    cols_show = {
        "rank": "#", "username": "Membro", "character_id": "ID",
        "power": "City Power", "power_band": "Faixa",
        "kill_points": "Kill Points", "kp_goal": "Meta KP",
        "t5_kills": "T5 Kills", "t4_kills": "T4 Kills",
        "t3_kills": "T3 Kills", "t2_kills": "T2 Kills", "t1_kills": "T1 Kills",
        "t5_deaths": "T5 Mortes", "t4_deaths": "T4 Mortes",
        "t3_deaths": "T3 Mortes", "t2_deaths": "T2 Mortes", "t1_deaths": "T1 Mortes",
        "dead_t4_goal": "Meta Mortes T4 eq.", "dead_equiv": "Mortes Equiv. T4",
        "status": "Status",
    }
    avail = {k: v for k, v in cols_show.items() if k in df.columns}
    out   = df[list(avail.keys())].rename(columns=avail).copy()
    st.dataframe(out, use_container_width=True, hide_index=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="ranking.csv", mime="text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Resumo do Reino
# ══════════════════════════════════════════════════════════════════════════════

def show_kingdom_summary(ranked: pd.DataFrame) -> None:
    total    = len(ranked)
    approved = int((ranked["status"] == "Aprovado").sum())
    pending  = int((ranked["status"] == "Pendente").sum())
    below    = int((ranked["status"] == "Abaixo da meta").sum())
    active   = int((ranked["kill_points"] > 0).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("⚔️ Total KP",       fmt_int(int(ranked["kill_points"].sum())))
    c2.metric("✅ Aprovados",       f"{approved}/{total}")
    c3.metric("🟡 Pendentes",       fmt_int(pending))
    c4.metric("❌ Abaixo da meta",  fmt_int(below))
    c5.metric("🔥 Ativos",          fmt_int(active))

    st.divider()

    if px is not None:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.pie(
                values=[approved, pending, below],
                names=["✅ Aprovado", "🟡 Pendente", "❌ Abaixo"],
                hole=0.58,
                color_discrete_sequence=["#22c55e", "#f59e0b", "#ef4444"],
                title="Status das metas",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=11)
            fig.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            top15 = ranked.sort_values("kill_points", ascending=True).tail(15)
            cmap  = {"Aprovado": "#22c55e", "Pendente": "#f59e0b", "Abaixo da meta": "#ef4444"}
            fig2  = px.bar(
                top15, x="kill_points", y="username", orientation="h",
                color="status", color_discrete_map=cmap,
                title="Top 15 — Kill Points",
                labels={"kill_points": "Kill Points", "username": ""},
            )
            fig2.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("Resumo por faixa de power")
    bands = []
    for pmin, pmax, dead_t4, dead_t5, kp in GOAL_TABLE:
        label = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax != float("inf") else f"{pmin//1_000_000}M+"
        sub   = ranked[ranked["power_band"] == label] if "power_band" in ranked else pd.DataFrame()
        if sub.empty: continue
        bands.append({
            "Faixa": label, "Membros": len(sub),
            "✅": int((sub["status"]=="Aprovado").sum()),
            "🟡": int((sub["status"]=="Pendente").sum()),
            "❌": int((sub["status"]=="Abaixo da meta").sum()),
            "KP Total": fmt_int(int(sub["kill_points"].sum())),
            "Meta KP":  fmt_int(kp),
            "Meta Mortes (T4)": fmt_int(dead_t4),
        })
    if bands:
        st.dataframe(pd.DataFrame(bands), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("⚠️ Precisam de atenção")
    att = ranked[ranked["status"] != "Aprovado"].sort_values("kp_pct").head(10)
    if att.empty:
        st.success("🎉 Todos os membros estão aprovados!")
        return
    for _, row in att.iterrows():
        cls  = STATUS_CLS.get(row["status"], "err")
        em   = STATUS_EMOJI.get(row["status"], "❌")
        kp_p = min(float(row.get("kp_pct", 0)) * 100, 100)
        dp_p = min(float(row.get("dead_pct", 0)) * 100, 100)
        st.markdown(f"""
        <div class="mc {cls}" style="padding:12px 16px">
          <div class="mc-hdr" style="margin-bottom:4px">
            <div class="mc-name">{row['username']}</div>
            <div class="mc-pow">{fmt_m(int(row['power']))}</div>
            <div class="mc-stat {cls}">{em} {row['status']}</div>
          </div>
          <div style="font-size:0.68rem;color:var(--c-muted)">
            KP {kp_p:.0f}% · {fmt_int(int(row['kill_points']))} / {fmt_int(int(row['kp_goal']))} &nbsp;|&nbsp;
            Mortes {dp_p:.0f}% · {fmt_int(int(row.get('dead_equiv',0)))} / {fmt_int(int(row['dead_t4_goal']))} T4 eq.
          </div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Histórico
# ══════════════════════════════════════════════════════════════════════════════

def show_history(storage, imports, group_power):
    st.subheader("📈 Evolução histórica")
    if len(imports) < 2:
        st.info("Importe pelo menos 2 relatórios para ver a evolução.")
        return

    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    rows = []
    with st.spinner("Carregando..."):
        for _, imp in ordered.iterrows():
            stats   = storage.load_stats(imp["id"])
            metrics = calculate_metrics(stats, group_power=group_power)
            gm      = apply_goals(metrics)
            rows.append({
                "Data":      imp["report_date"],
                "KP Total":  int(metrics["kill_points"].sum()),
                "Aprovados": int((gm["status"]=="Aprovado").sum()),
                "Pendentes": int((gm["status"]=="Pendente").sum()),
                "Abaixo":    int((gm["status"]=="Abaixo da meta").sum()),
                "T5 Kills":  int(metrics.get("t5_kills", pd.Series([0])).sum()),
                "T4 Kills":  int(metrics.get("t4_kills", pd.Series([0])).sum()),
            })
    history = pd.DataFrame(rows)

    if px is None:
        st.dataframe(history, use_container_width=True, hide_index=True)
        return

    c1, c2 = st.columns(2)
    with c1:
        fig = px.line(history, x="Data", y="KP Total", title="Kill Points ao longo do tempo",
                      markers=True, color_discrete_sequence=["#2563eb"])
        fig.update_layout(margin=dict(t=40,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        m = history[["Data","Aprovados","Pendentes","Abaixo"]].melt(id_vars="Data", var_name="Status", value_name="N")
        fig2 = px.bar(m, x="Data", y="N", color="Status", barmode="stack",
                      title="Status de metas por relatório",
                      color_discrete_map={"Aprovados":"#22c55e","Pendentes":"#f59e0b","Abaixo":"#ef4444"})
        fig2.update_layout(margin=dict(t=40,b=0,l=0,r=0))
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("Comparar dois relatórios")
    labels = ordered["label"].tolist()
    ca, cb = st.columns(2)
    with ca: la = st.selectbox("Base", labels, index=0, key="ha")
    with cb: lb = st.selectbox("Comparado", labels, index=min(1,len(labels)-1), key="hb")
    if la == lb:
        st.warning("Selecione dois relatórios diferentes.")
        return
    id_a = ordered.loc[ordered["label"].eq(la),"id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
    delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
    met   = calculate_metrics(delta, group_power=group_power)
    top   = met.sort_values("kill_points", ascending=False).head(15)
    if not top.empty:
        fig3 = px.bar(top.sort_values("kill_points",ascending=True), x="kill_points", y="username",
                      orientation="h", title="Top 15 — Ganho no período",
                      color_discrete_sequence=["#2563eb"])
        st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Imports
# ══════════════════════════════════════════════════════════════════════════════

def show_imports(imports, storage, *, is_admin, admin_enabled):
    st.subheader("Relatórios importados")
    st.dataframe(
        imports[["report_date","filename","row_count","imported_at"]].rename(columns={
            "report_date":"Data","filename":"Arquivo",
            "row_count":"Membros","imported_at":"Importado em",
        }),
        use_container_width=True, hide_index=True,
    )
    if admin_enabled and is_admin:
        st.divider()
        st.subheader("🗑️ Deletar import")
        st.warning("⚠️ Irreversível.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Selecionar", ["— selecionar —", *labels])
        if to_del != "— selecionar —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            if st.button("🗑️ Confirmar exclusão", type="secondary"):
                if storage.delete_import(row["id"]):
                    st.success("Deletado!")
                    st.rerun()
                else:
                    st.error("Não encontrado.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Ajuda
# ══════════════════════════════════════════════════════════════════════════════

def show_help():
    st.header("❓ Como usar")
    st.markdown("""
## Tabela de metas por City Power

| City Power       | Meta Mortes               | Meta KP |
|-----------------|---------------------------|---------|
| ≤ 49M           | 900k T4 ou 450k T5        | 80M     |
| 50M – 59M       | 900k T4 ou 450k T5        | 100M    |
| 60M – 69M       | 1M T4 ou 500k T5          | 140M    |
| 70M – 79M       | 1.4M T4 ou 700k T5        | 180M    |
| 80M – 89M       | 1.6M T4 ou 800k T5        | 200M    |
| 90M – 99M       | 2M T4 ou 1M T5            | 280M    |
| ≥ 100M          | 2M T4 ou 1M T5            | 320M    |

## Equivalência de mortes
**1 morte T5 = 2 mortes T4**

Exemplo: 700k T5 + 200k T4 = (700k × 2) + 200k = 1.6M T4 equivalente ✅

## Kill Points
| Tier | Multiplicador |
|------|--------------|
| T5   | × 20         |
| T4   | × 10         |
| T3   | × 4          |
| T2   | × 2          |
| T1   | × 0.2        |

## Status dos membros
- ✅ **Aprovado** — atingiu KP e mortes
- 🟡 **Pendente** — atingiu ≥ 75% em ambas as metas
- ❌ **Abaixo da meta** — falta mais de 25% em alguma das metas

## Barra de pesquisa
Pesquise pelo **nome** ou **Character ID** do membro diretamente na aba Ranking.

## Filtro de data
Use o painel "Filtrar por data de importação" para recortar membros por quando o relatório foi importado.

## Upload
O upload exige a senha admin. Acesse o Streamlit via `kingom1602.streamlit.app`.
""")


# ══════════════════════════════════════════════════════════════════════════════
# Formatadores
# ══════════════════════════════════════════════════════════════════════════════

def fmt_int(v) -> str:
    return f"{int(v):,}"

def fmt_k(v: int) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}k"
    return str(v)

def fmt_m(v: int) -> str:
    return f"{v/1_000_000:.0f}M"

def fmt_pct(v) -> str:
    return f"{float(v)*100:.1f}%"


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
