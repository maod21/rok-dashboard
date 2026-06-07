from __future__ import annotations

import os
import re
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

# ══════════════════════════════════════════════════════════════════════════════
# Page config
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="K1602 · KP Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── Design tokens ── */
:root {
  --bg:#fff;--surf:#f8fafc;--brd:rgba(0,0,0,0.09);
  --txt:#0f172a;--muted:#64748b;--acc:#1d4ed8;--acc-lt:#eff6ff;
  --gold:#92400e;--gold-lt:#fef3c7;
  --ok:#15803d;--ok-bg:#f0fdf4;--ok-b:#86efac;
  --wa:#92400e;--wa-bg:#fffbeb;--wa-b:#fcd34d;
  --er:#991b1b;--er-bg:#fff1f2;--er-b:#fca5a5;
  --t5:#92400e;--t4:#9a3412;--t3:#6d28d9;--t2:#1d4ed8;--t1:#475569;
}
[data-theme="dark"] {
  --bg:#0f172a;--surf:#1e293b;--brd:rgba(255,255,255,0.08);
  --txt:#f1f5f9;--muted:#94a3b8;--acc:#60a5fa;--acc-lt:#1e3a5f;
  --gold:#fbbf24;--gold-lt:#1c1400;
  --ok:#4ade80;--ok-bg:#052e16;--ok-b:#166534;
  --wa:#fcd34d;--wa-bg:#1c1400;--wa-b:#854d0e;
  --er:#f87171;--er-bg:#1a0000;--er-b:#991b1b;
  --t5:#fbbf24;--t4:#fb923c;--t3:#a78bfa;--t2:#60a5fa;--t1:#94a3b8;
}

.main .block-container{padding-top:.9rem;padding-bottom:2rem;max-width:1440px;}

/* metrics */
[data-testid="stMetric"]{background:var(--surf)!important;border:1px solid var(--brd)!important;
  border-radius:12px;padding:14px 18px!important;position:relative;overflow:hidden;}
[data-testid="stMetric"]::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--acc),var(--gold));}
[data-testid="stMetricLabel"]{font-size:.66rem!important;text-transform:uppercase;
  letter-spacing:.09em;font-weight:700;color:var(--muted)!important;}
[data-testid="stMetricValue"]{font-size:1.35rem!important;font-weight:800;color:var(--txt)!important;}

/* tabs */
[data-testid="stTabs"] button{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;}

/* header */
.hdr{display:flex;align-items:center;gap:14px;padding:12px 20px;margin-bottom:12px;
  background:var(--surf);border:1px solid var(--brd);border-left:4px solid var(--acc);border-radius:12px;}
.hdr-icon{font-size:1.9rem;line-height:1;}
.hdr-title{font-size:1.25rem;font-weight:800;color:var(--txt);margin:0;}
.hdr-sub{font-size:.7rem;color:var(--muted);margin:2px 0 0;}

/* weight pills */
.wpills{display:flex;gap:5px;flex-wrap:wrap;margin:0 0 14px;}
.wp{padding:2px 9px;border-radius:20px;font-size:.67rem;font-weight:700;
    background:var(--surf);border:1px solid var(--brd);color:var(--muted);}
.wp-t5{color:var(--t5);border-color:var(--t5);}
.wp-t4{color:var(--t4);border-color:var(--t4);}
.wp-t3{color:var(--t3);border-color:var(--t3);}
.wp-t2{color:var(--t2);border-color:var(--t2);}
.wp-t1{color:var(--t1);border-color:var(--t1);}

/* ── Member card ── */
.mc{border:1px solid var(--brd);border-radius:12px;margin-bottom:8px;
    background:var(--surf);overflow:hidden;}
.mc.ok{border-left:5px solid var(--ok);background:var(--ok-bg);}
.mc.wa{border-left:5px solid var(--wa);background:var(--wa-bg);}
.mc.er{border-left:5px solid var(--er);background:var(--er-bg);}

/* summary row */
.mc-sum{display:flex;align-items:center;gap:10px;padding:13px 16px;flex-wrap:wrap;}
.mc-rank{font-size:.95rem;font-weight:800;color:var(--muted);min-width:28px;}
.mc-name{font-size:.95rem;font-weight:700;color:var(--txt);flex:1;min-width:100px;}
.mc-pow{font-size:.72rem;color:var(--muted);white-space:nowrap;}
.mc-band{font-size:.62rem;font-weight:700;padding:2px 7px;border-radius:20px;
          background:rgba(128,128,128,.1);color:var(--muted);white-space:nowrap;}
.mc-kp{font-size:.85rem;font-weight:800;color:var(--acc);white-space:nowrap;}
.mc-stat{font-size:.68rem;font-weight:800;padding:3px 9px;border-radius:20px;white-space:nowrap;}
.mc-stat.ok{background:var(--ok-bg);color:var(--ok);border:1px solid var(--ok-b);}
.mc-stat.wa{background:var(--wa-bg);color:var(--wa);border:1px solid var(--wa-b);}
.mc-stat.er{background:var(--er-bg);color:var(--er);border:1px solid var(--er-b);}

/* progress */
.pb-wrap{margin-top:5px;}
.pb-meta{display:flex;justify-content:space-between;font-size:.6rem;color:var(--muted);margin-bottom:3px;}
.pb-trk{background:var(--brd);border-radius:99px;height:6px;overflow:hidden;}
.pb-fill{height:100%;border-radius:99px;}
.pb-fill.ok{background:linear-gradient(90deg,#15803d,#22c55e);}
.pb-fill.wa{background:linear-gradient(90deg,#92400e,#f59e0b);}
.pb-fill.er{background:linear-gradient(90deg,#991b1b,#ef4444);}
.pb-gap{font-size:.6rem;color:var(--muted);margin-top:3px;}

/* tier pills */
.tp-row{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px;}
.tp{padding:2px 7px;border-radius:4px;font-size:.66rem;font-weight:700;}
.tp-t5k,.tp-t5d{background:rgba(146,64,14,.12);color:var(--t5);border:1px solid rgba(146,64,14,.25);}
.tp-t4k,.tp-t4d{background:rgba(154,52,18,.12);color:var(--t4);border:1px solid rgba(154,52,18,.25);}
.tp-t3k,.tp-t3d{background:rgba(109,40,217,.12);color:var(--t3);border:1px solid rgba(109,40,217,.25);}
.tp-t2k,.tp-t2d{background:rgba(29,78,216,.12);color:var(--t2);border:1px solid rgba(29,78,216,.25);}
.tp-t1k,.tp-t1d{background:rgba(71,85,105,.10);color:var(--t1);border:1px solid rgba(71,85,105,.20);}

/* section header */
.sh{font-size:.65rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;
    color:var(--muted);border-bottom:1px solid var(--brd);padding-bottom:5px;margin:14px 0 10px;}

/* kingdom overview cards */
.kd-stat{background:var(--surf);border:1px solid var(--brd);border-radius:14px;
          padding:20px 22px;position:relative;overflow:hidden;text-align:center;}
.kd-stat::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
                  background:linear-gradient(90deg,var(--acc),var(--gold));}
.kd-icon{font-size:1.6rem;margin-bottom:6px;}
.kd-lbl{font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);}
.kd-val{font-size:1.55rem;font-weight:900;color:var(--txt);margin:4px 0 2px;}
.kd-sub{font-size:.68rem;color:var(--muted);}

/* kingdom section divider */
.kd-sec{font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.1em;
         color:var(--muted);border-bottom:1px solid var(--brd);padding-bottom:6px;margin:20px 0 14px;}

/* attention mini card */
.att-card{display:flex;align-items:center;gap:10px;padding:10px 14px;
           border:1px solid var(--brd);border-radius:10px;background:var(--surf);margin-bottom:6px;}
.att-card.ok{border-left:4px solid var(--ok);}
.att-card.wa{border-left:4px solid var(--wa);}
.att-card.er{border-left:4px solid var(--er);}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Storage / constants
# ══════════════════════════════════════════════════════════════════════════════

STATUS_EMOJI = {"Aprovado":"✅","Pendente":"🟡","Abaixo da meta":"❌"}
STATUS_CLS   = {"Aprovado":"ok","Pendente":"wa","Abaixo da meta":"er"}

@st.cache_resource
def get_storage():
    return create_storage()


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    storage = get_storage()

    st.markdown("""
    <div class="hdr">
      <div class="hdr-icon">⚔️</div>
      <div><p class="hdr-title">K1602 · KP Dashboard</p>
           <p class="hdr-sub">Kingdom Kill Points Tracker — Rise of Kingdoms</p></div>
    </div>
    <div class="wpills">
      <span class="wp wp-t5">T5 Kill ×20</span><span class="wp wp-t4">T4 Kill ×10</span>
      <span class="wp wp-t3">T3 Kill ×4</span><span class="wp wp-t2">T2 Kill ×2</span>
      <span class="wp wp-t1">T1 Kill ×0.2</span><span class="wp">Morte T5 = 2×T4</span>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(f"**Storage:** `{storage.label}`")
        st.markdown('<div class="sh">📂 Relatórios</div>', unsafe_allow_html=True)
        handle_upload(storage)

    imports = storage.list_imports()
    if imports.empty:
        st.info("👈 Faça upload do primeiro statsExport na barra lateral para começar.")
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
    gp          = default_group_power(storage, imports)
    metrics_raw = calculate_metrics(stats_basis, group_power=gp)
    if min_power > 0:
        metrics_raw = metrics_raw[pd.to_numeric(metrics_raw["power"], errors="coerce").fillna(0) >= min_power]

    ranked = apply_goals(add_rank(metrics_raw, "kill_points"))

    n  = len(imports)
    dl = f" · +{n-1} anterior{'es' if n>2 else ''}" if n > 1 else ""
    st.caption(f"📅 **{selected['report_date']}** · Base: **{basis}** · Membros: **{len(ranked):,}** · Imports: **{n}**{dl}")

    tabs = st.tabs(["🏆 Ranking","🏰 Reino","📈 Histórico","📁 Imports","❓ Ajuda"])
    with tabs[0]: show_ranking(ranked)
    with tabs[1]: show_kingdom(ranked, imports, storage, gp)
    with tabs[2]: show_history(storage, imports, gp)
    with tabs[3]: show_imports(imports, storage, is_admin=is_admin, admin_enabled=admin_enabled)
    with tabs[4]: show_help()


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════════════════════════════════════

def handle_upload(storage):
    pwd = get_secret("ADMIN_PASSWORD")
    if "upload_auth" not in st.session_state:
        st.session_state.upload_auth = False
    if not st.session_state.upload_auth:
        st.caption("🔒 Upload restrito à liderança")
        up_pwd = st.text_input("Senha", type="password", key="up_pwd", placeholder="Digite a senha...")
        if st.button("🔓 Desbloquear", use_container_width=True):
            if (not pwd) or is_admin_authenticated(pwd, up_pwd):
                st.session_state.upload_auth = True; st.rerun()
            else:
                st.error("❌ Senha incorreta")
        return
    st.success("✅ Upload desbloqueado")
    if st.button("🔒 Bloquear", use_container_width=True, type="secondary"):
        st.session_state.upload_auth = False; st.rerun()
    uploaded = st.file_uploader("Upload statsExport", type=["xlsx","xls"])
    if not uploaded: return
    safe_name   = re.sub(r"[^\w.\-]","_", uploaded.name)
    report_date = st.date_input("Data", value=extract_report_date_from_name(safe_name) or date.today())
    if not st.button("💾 Salvar", type="primary", use_container_width=True): return
    with st.spinner("Processando..."):
        try:
            fb = uploaded.getvalue()
            if len(fb) > 50*1024*1024: st.error("❌ Arquivo muito grande."); return
            stats = load_stats_file(BytesIO(fb), filename=safe_name)
            _, created = storage.save_import(filename=safe_name, report_date=report_date.isoformat(),
                                              file_hash=file_sha256(fb), stats=stats)
        except Exception as e: st.error(f"❌ {e}"); return
    st.success(f"✅ {len(stats):,} membros!") if created else st.warning("⚠️ Já importado.")
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
    ordered   = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    positions = ordered.index[ordered["id"].eq(selected["id"])].tolist()
    if not positions or positions[0] == 0: return None
    prev_id = ordered.loc[positions[0]-1,"id"]
    return None if prev_id == selected["id"] else storage.load_stats(prev_id)

@st.cache_data(ttl=300)
def _cached_gp(label, first_id):
    first = get_storage().load_stats(first_id)
    return int(pd.to_numeric(first["power"], errors="coerce").fillna(0).sum())

def default_group_power(storage, imports):
    ordered  = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    return _cached_gp(storage.label, ordered.iloc[0]["id"])

def admin_panel():
    st.markdown('<div class="sh">🔒 Admin</div>', unsafe_allow_html=True)
    pwd = get_secret("ADMIN_PASSWORD")
    if not pwd: st.caption("Configure ADMIN_PASSWORD nos Secrets."); return False, False
    entered = st.text_input("Senha admin", type="password", key="adm_pwd")
    if is_admin_authenticated(pwd, entered): st.success("✅ Admin ativo"); return True, True
    if entered: st.error("❌ Incorreta")
    return True, False

def get_secret(name):
    v = os.getenv(name)
    if v: return v
    try: v = st.secrets.get(name)
    except: v = None
    return str(v) if v else None


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Ranking (accordion)
# ══════════════════════════════════════════════════════════════════════════════

def show_ranking(ranked_full: pd.DataFrame) -> None:

    # ── Barra de filtros ──
    c1, c2, c3, c4 = st.columns([3,2,2,1])
    with c1:
        search = st.text_input("🔍", placeholder="Buscar por nome ou Character ID…",
                                key="rank_search", label_visibility="collapsed")
    with c2:
        sf = st.selectbox("Status", ["Todos","✅ Aprovado","🟡 Pendente","❌ Abaixo da meta"],
                          key="rank_sf", label_visibility="collapsed")
    with c3:
        sort_by = st.selectbox("Ordenar",
                               ["Kill Points ↓","Power ↓","% KP ↓","% Mortes ↓","Nome ↑"],
                               key="rank_sort", label_visibility="collapsed")
    with c4:
        view_mode = st.radio("Modo",["🃏","📋"], horizontal=True, key="rank_view",
                             label_visibility="collapsed",
                             help="🃏 Cards com detalhes   📋 Tabela compacta")

    # ── Filtro de datas ──
    with st.expander("📅 Filtrar por data de importação", expanded=False):
        dc1,dc2,dc3 = st.columns([2,2,1])
        with dc1: date_from = st.date_input("De",  value=None, key="df_from")
        with dc2: date_to   = st.date_input("Até", value=None, key="df_to")
        with dc3:
            if st.button("✖ Limpar", use_container_width=True, key="clr_dt"):
                st.session_state.df_from = None; st.session_state.df_to = None; st.rerun()

    # ── Aplicar filtros ──
    df = ranked_full.copy()
    if search.strip():
        n = search.strip().lower()
        df = df[df["username"].astype(str).str.lower().str.contains(n, regex=False, na=False)
                | df["character_id"].astype(str).str.lower().str.contains(n, regex=False, na=False)]
    if sf != "Todos":
        df = df[df["status"] == sf.split(" ",1)[1]]
    if "imported_at" in df.columns and (date_from or date_to):
        df["_dt"] = pd.to_datetime(df["imported_at"], errors="coerce").dt.date
        if date_from: df = df[df["_dt"] >= date_from]
        if date_to:   df = df[df["_dt"] <= date_to]
        df = df.drop(columns=["_dt"])

    sort_map = {"Kill Points ↓":("kill_points",False),"Power ↓":("power",False),
                "% KP ↓":("kp_pct",False),"% Mortes ↓":("dead_pct",False),"Nome ↑":("username",True)}
    scol, sasc = sort_map[sort_by]
    df = df.sort_values(scol, ascending=sasc).reset_index(drop=True)
    df["rank"] = range(1, len(df)+1)

    af = []
    if search.strip():       af.append(f'"{search.strip()}"')
    if sf != "Todos":        af.append(sf.split(" ",1)[1])
    if date_from:            af.append(f"de {date_from}")
    if date_to:              af.append(f"até {date_to}")
    note = f" · filtros: {', '.join(af)}" if af else ""
    st.caption(f"Mostrando **{len(df):,}** de **{len(ranked_full):,}** membros{note}")

    if view_mode == "🃏":
        page_size = st.selectbox("Cards por página",[25,50,100], index=0, key="rank_ps")
        total_pg  = max(1, -(-len(df)//page_size))
        page      = st.number_input("Página", min_value=1, max_value=total_pg, value=1, key="rank_pg")
        start     = (page-1)*page_size
        _render_accordion(df.iloc[start:start+page_size])
    else:
        _render_table(df)


def _render_accordion(df: pd.DataFrame) -> None:
    """Each member = a Streamlit expander with summary in label + full detail inside."""
    for _, row in df.iterrows():
        cls   = STATUS_CLS.get(row["status"],"er")
        emoji = STATUS_EMOJI.get(row["status"],"❌")

        kp_w   = min(float(row.get("kp_pct",0))*100, 100)
        dead_w = min(float(row.get("dead_pct",0))*100, 100)
        kp_gap   = int(row.get("kp_gap",0))
        dead_gap = int(row.get("dead_gap_t4",0))

        # ── Expander label (summary line) ──
        label = (
            f"{emoji}  #{int(row['rank'])} · **{row['username']}**"
            f"  —  ⚔️ {fmt_k(int(row['kill_points']))} KP"
            f"  ·  💀 {fmt_k(int(row.get('dead_equiv',0)))} T4eq"
            f"  ·  {fmt_m(int(row['power']))} power"
        )

        with st.expander(label, expanded=False):
            # ── Colour strip at top ──
            color_map = {"ok":"#22c55e","wa":"#f59e0b","er":"#ef4444"}
            color = color_map.get(cls,"#94a3b8")
            st.markdown(
                f'<div style="height:3px;background:{color};border-radius:99px;margin-bottom:14px"></div>',
                unsafe_allow_html=True
            )

            # ── Row 1: identity ──
            r1c1, r1c2, r1c3, r1c4 = st.columns([3,2,2,2])
            with r1c1:
                st.markdown(f"**Governor:** {row['username']}")
                st.caption(f"ID: `{row.get('character_id','—')}`")
            with r1c2:
                st.markdown(f"**City Power**")
                st.markdown(f"### {fmt_m(int(row['power']))}M")
            with r1c3:
                st.markdown(f"**Faixa**")
                st.markdown(f"### {row.get('power_band','—')}")
            with r1c4:
                st.markdown(f"**Status**")
                st.markdown(f"### {emoji} {row['status']}")

            st.divider()

            # ── Row 2: KP + mortes progress ──
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                st.markdown("**⚔️ Kill Points**")
                st.markdown(f"## {fmt_int(int(row['kill_points']))}")
                st.caption(f"Meta: {fmt_int(int(row['kp_goal']))} · {kp_w:.0f}% atingido")
                prog = st.progress(int(kp_w))
                if kp_gap > 0:
                    st.caption(f"⚠️ Faltam {fmt_k(kp_gap)} KP")
                else:
                    st.caption("✅ Meta de KP atingida!")

            with r2c2:
                dead_equiv = int(row.get("dead_equiv",0))
                st.markdown("**💀 Mortes (T4 equivalente)**")
                st.markdown(f"## {fmt_int(dead_equiv)}")
                st.caption(f"Meta: {fmt_int(int(row['dead_t4_goal']))} · {dead_w:.0f}% atingido")
                st.progress(int(dead_w))
                if dead_gap > 0:
                    st.caption(f"⚠️ Faltam {fmt_k(dead_gap)} T4eq")
                else:
                    st.caption("✅ Meta de mortes atingida!")

            st.divider()

            # ── Row 3: kills por tier ──
            st.markdown("**Kills por Tier**")
            kc = st.columns(5)
            for col, tier, key in zip(kc, ["T5","T4","T3","T2","T1"],
                                      ["t5_kills","t4_kills","t3_kills","t2_kills","t1_kills"]):
                val = int(row.get(key,0))
                pts = int(val * POINT_WEIGHTS.get(key, 0))
                with col:
                    st.metric(label=tier, value=fmt_k(val), delta=f"+{fmt_k(pts)} KP" if pts else None,
                               delta_color="normal")

            st.divider()

            # ── Row 4: mortes por tier ──
            st.markdown("**Mortes por Tier**")
            dc = st.columns(5)
            for col, tier, key, equiv in zip(
                dc,
                ["T5","T4","T3","T2","T1"],
                ["t5_deaths","t4_deaths","t3_deaths","t2_deaths","t1_deaths"],
                [2, 1, 0, 0, 0],
            ):
                val = int(row.get(key,0))
                with col:
                    eq_txt = f"≡{fmt_k(val*equiv)} T4" if equiv > 1 else ("T4 base" if equiv==1 else "—")
                    st.metric(label=tier, value=fmt_k(val), delta=eq_txt if val > 0 else None,
                               delta_color="off")

            # ── Row 5: metas detalhadas ──
            st.divider()
            mc1, mc2 = st.columns(2)
            with mc1:
                st.caption(f"**Meta KP:** {fmt_int(int(row['kp_goal']))}")
                st.caption(f"**Meta mortes T4:** {fmt_int(int(row['dead_t4_goal']))}")
                st.caption(f"**Meta mortes T5:** {fmt_int(int(row['dead_t5_goal']))}")
            with mc2:
                t5d = int(row.get("t5_deaths",0))
                t4d = int(row.get("t4_deaths",0))
                st.caption(f"**T5 mortes:** {fmt_int(t5d)} (≡ {fmt_int(t5d*2)} T4)")
                st.caption(f"**T4 mortes:** {fmt_int(t4d)}")
                st.caption(f"**Total equiv.:** {fmt_int(dead_equiv)} / {fmt_int(int(row['dead_t4_goal']))}")


def _render_table(df: pd.DataFrame) -> None:
    cols_show = {
        "rank":"#","username":"Membro","character_id":"ID",
        "power":"City Power","power_band":"Faixa",
        "kill_points":"Kill Points","kp_goal":"Meta KP",
        "t5_kills":"T5 Kills","t4_kills":"T4 Kills","t3_kills":"T3 Kills",
        "t2_kills":"T2 Kills","t1_kills":"T1 Kills",
        "t5_deaths":"T5 Mortes","t4_deaths":"T4 Mortes",
        "t3_deaths":"T3 Mortes","t2_deaths":"T2 Mortes","t1_deaths":"T1 Mortes",
        "dead_t4_goal":"Meta Mortes T4eq","dead_equiv":"Mortes Equiv. T4",
        "status":"Status",
    }
    avail = {k:v for k,v in cols_show.items() if k in df.columns}
    out   = df[list(avail.keys())].rename(columns=avail).copy()
    st.dataframe(out, use_container_width=True, hide_index=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="ranking.csv", mime="text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Reino (Kingdom Command)
# ══════════════════════════════════════════════════════════════════════════════

def show_kingdom(ranked: pd.DataFrame, imports: pd.DataFrame, storage, group_power: int) -> None:

    total    = len(ranked)
    approved = int((ranked["status"]=="Aprovado").sum())
    pending  = int((ranked["status"]=="Pendente").sum())
    below    = int((ranked["status"]=="Abaixo da meta").sum())
    active   = int((ranked["kill_points"]>0).sum())
    kp_total = int(ranked["kill_points"].sum())
    power_total = int(ranked["power"].sum())
    aprov_pct = approved/total*100 if total else 0

    # ── Banner ──────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:linear-gradient(135deg,var(--acc-lt) 0%,var(--surf) 100%);
                border:1px solid var(--brd);border-left:5px solid var(--acc);
                border-radius:14px;padding:20px 28px;margin-bottom:20px;">
      <div style="font-size:1.5rem;font-weight:900;color:var(--txt)">🏰 War Room — K1602</div>
      <div style="font-size:.78rem;color:var(--muted);margin-top:3px">
        Visão geral do reino · Rise of Kingdoms
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI cards ────────────────────────────────────────────────────────────
    kd_cols = st.columns(5)
    kd_data = [
        ("⚔️","Total Kill Points", fmt_int(kp_total), "pontos acumulados"),
        ("🏰","Power Total",        fmt_m(power_total)+"M", "city power somado"),
        ("👥","Governadores",      fmt_int(total),    f"{active} ativos"),
        ("✅","Taxa de aprovação", f"{aprov_pct:.1f}%", f"{approved} aprovados"),
        ("⚠️","Abaixo da meta",    fmt_int(below),    f"{pending} pendentes"),
    ]
    for col,(icon,lbl,val,sub) in zip(kd_cols, kd_data):
        with col:
            st.markdown(f"""
            <div class="kd-stat">
              <div class="kd-icon">{icon}</div>
              <div class="kd-lbl">{lbl}</div>
              <div class="kd-val">{val}</div>
              <div class="kd-sub">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")  # spacing

    # ── Status progress bars ─────────────────────────────────────────────────
    st.markdown('<div class="kd-sec">Status das metas</div>', unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    for col, label, count, color in [
        (s1,"✅ Aprovados",  approved,"#22c55e"),
        (s2,"🟡 Pendentes", pending, "#f59e0b"),
        (s3,"❌ Abaixo",    below,   "#ef4444"),
    ]:
        pct = count/total*100 if total else 0
        with col:
            st.markdown(f"""
            <div style="background:var(--surf);border:1px solid var(--brd);
                        border-radius:12px;padding:16px 18px;">
              <div style="font-size:.7rem;font-weight:700;color:var(--muted);
                          text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">{label}</div>
              <div style="font-size:1.7rem;font-weight:900;color:var(--txt)">
                {count} <span style="font-size:.85rem;font-weight:500;color:var(--muted)">/{total}</span>
              </div>
              <div style="background:var(--brd);border-radius:99px;height:8px;overflow:hidden;margin-top:8px">
                <div style="width:{pct:.1f}%;height:100%;background:{color};border-radius:99px"></div>
              </div>
              <div style="font-size:.62rem;color:var(--muted);margin-top:4px">{pct:.1f}% da aliança</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Gráficos ─────────────────────────────────────────────────────────────
    if px is not None:
        st.markdown('<div class="kd-sec">Distribuição de Kill Points</div>', unsafe_allow_html=True)
        g1, g2 = st.columns([3,2])

        with g1:
            top20 = ranked.sort_values("kill_points", ascending=True).tail(20)
            cmap  = {"Aprovado":"#22c55e","Pendente":"#f59e0b","Abaixo da meta":"#ef4444"}
            fig   = px.bar(top20, x="kill_points", y="username", orientation="h",
                           color="status", color_discrete_map=cmap,
                           title="Top 20 Governors — Kill Points",
                           labels={"kill_points":"Kill Points","username":""})
            fig.update_layout(showlegend=False, margin=dict(t=40,b=0,l=0,r=0),
                              yaxis=dict(tickfont=dict(size=10)))
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)

        with g2:
            fig2 = px.pie(values=[approved,pending,below],
                          names=["Aprovado","Pendente","Abaixo da meta"], hole=0.62,
                          color_discrete_sequence=["#22c55e","#f59e0b","#ef4444"],
                          title="Status das metas")
            fig2.update_traces(textposition="inside", textinfo="percent", textfont_size=11)
            fig2.update_layout(showlegend=True, margin=dict(t=40,b=0,l=0,r=0),
                               legend=dict(orientation="h",y=-0.1,font=dict(size=10)))
            st.plotly_chart(fig2, use_container_width=True)

    # ── Evolução histórica ───────────────────────────────────────────────────
    if len(imports) >= 2:
        st.markdown('<div class="kd-sec">Evolução histórica</div>', unsafe_allow_html=True)
        ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
        hist_rows = []
        with st.spinner("Carregando evolução..."):
            for _, imp in ordered.iterrows():
                s  = storage.load_stats(imp["id"])
                m  = calculate_metrics(s, group_power=group_power)
                gm = apply_goals(m)
                hist_rows.append({
                    "Data":      imp["report_date"],
                    "KP Total":  int(m["kill_points"].sum()),
                    "Aprovados": int((gm["status"]=="Aprovado").sum()),
                    "Pendentes": int((gm["status"]=="Pendente").sum()),
                    "Abaixo":    int((gm["status"]=="Abaixo da meta").sum()),
                    "Membros":   len(m),
                })
        hist = pd.DataFrame(hist_rows)
        if px is not None and len(hist) >= 2:
            hc1, hc2 = st.columns(2)
            with hc1:
                fig3 = px.line(hist, x="Data", y="KP Total", markers=True,
                               title="Kill Points por relatório",
                               color_discrete_sequence=["#1d4ed8"])
                fig3.update_layout(margin=dict(t=40,b=0,l=0,r=0))
                st.plotly_chart(fig3, use_container_width=True)
            with hc2:
                melt = hist[["Data","Aprovados","Pendentes","Abaixo"]].melt(
                    id_vars="Data", var_name="Status", value_name="N")
                fig4 = px.bar(melt, x="Data", y="N", color="Status", barmode="stack",
                              title="Status por relatório",
                              color_discrete_map={"Aprovados":"#22c55e","Pendentes":"#f59e0b","Abaixo":"#ef4444"})
                fig4.update_layout(margin=dict(t=40,b=0,l=0,r=0), showlegend=True,
                                   legend=dict(orientation="h",y=-0.15,font=dict(size=10)))
                st.plotly_chart(fig4, use_container_width=True)

    # ── Resumo por faixa ─────────────────────────────────────────────────────
    st.markdown('<div class="kd-sec">Resumo por faixa de power</div>', unsafe_allow_html=True)
    bands = []
    for pmin, pmax, dead_t4, _, kp in GOAL_TABLE:
        label = f"{pmin//1_000_000}M–{(pmax+1)//1_000_000}M" if pmax != float("inf") else f"{pmin//1_000_000}M+"
        sub   = ranked[ranked["power_band"]==label] if "power_band" in ranked else pd.DataFrame()
        if sub.empty: continue
        bands.append({
            "Faixa":label,"Membros":len(sub),
            "✅":int((sub["status"]=="Aprovado").sum()),
            "🟡":int((sub["status"]=="Pendente").sum()),
            "❌":int((sub["status"]=="Abaixo da meta").sum()),
            "KP Total":fmt_int(int(sub["kill_points"].sum())),
            "Meta KP": fmt_int(kp),
        })
    if bands:
        st.dataframe(pd.DataFrame(bands), use_container_width=True, hide_index=True)

    # ── Atenção ───────────────────────────────────────────────────────────────
    st.markdown('<div class="kd-sec">⚠️ Precisam de atenção</div>', unsafe_allow_html=True)
    att = ranked[ranked["status"]!="Aprovado"].sort_values("kp_pct").head(8)
    if att.empty:
        st.success("🎉 Todos os membros estão aprovados!")
    else:
        for _, row in att.iterrows():
            cls  = STATUS_CLS.get(row["status"],"er")
            kp_p = min(float(row.get("kp_pct",0))*100, 100)
            dp_p = min(float(row.get("dead_pct",0))*100, 100)
            st.markdown(f"""
            <div class="att-card {cls}">
              <div style="flex:1;font-weight:700;color:var(--txt)">{row['username']}</div>
              <div style="font-size:.7rem;color:var(--muted)">{fmt_m(int(row['power']))}</div>
              <div style="font-size:.68rem;color:var(--muted)">
                KP {kp_p:.0f}% · Mortes {dp_p:.0f}%
              </div>
              <div class="mc-stat {cls}">{STATUS_EMOJI.get(row['status'],'❌')} {row['status']}</div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Histórico
# ══════════════════════════════════════════════════════════════════════════════

def show_history(storage, imports, group_power):
    st.subheader("📈 Comparar dois relatórios")
    if len(imports) < 2:
        st.info("Importe pelo menos 2 relatórios.")
        return
    ordered = imports.sort_values(["report_date","imported_at"]).reset_index(drop=True)
    labels  = ordered["label"].tolist()
    ca, cb  = st.columns(2)
    with ca: la = st.selectbox("Base",     labels, index=0,              key="ha")
    with cb: lb = st.selectbox("Comparado",labels, index=min(1,len(labels)-1), key="hb")
    if la == lb: st.warning("Selecione dois relatórios diferentes."); return
    id_a = ordered.loc[ordered["label"].eq(la),"id"].iloc[0]
    id_b = ordered.loc[ordered["label"].eq(lb),"id"].iloc[0]
    delta = compute_period_deltas(storage.load_stats(id_b), storage.load_stats(id_a))
    met   = calculate_metrics(delta, group_power=group_power)
    top   = met.sort_values("kill_points", ascending=False).head(15)
    if not top.empty and px is not None:
        fig = px.bar(top.sort_values("kill_points",ascending=True), x="kill_points", y="username",
                     orientation="h", title=f"Top 15 — Ganho no período ({la} → {lb})",
                     color_discrete_sequence=["#1d4ed8"])
        fig.update_layout(margin=dict(t=40,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        met[["username","power","kill_points","t5_kills","t4_kills","t3_kills","t2_kills","t1_kills"]]
           .sort_values("kill_points",ascending=False)
           .rename(columns={"username":"Membro","power":"Power","kill_points":"KP Ganho",
                             "t5_kills":"T5","t4_kills":"T4","t3_kills":"T3","t2_kills":"T2","t1_kills":"T1"}),
        use_container_width=True, hide_index=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Imports
# ══════════════════════════════════════════════════════════════════════════════

def show_imports(imports, storage, *, is_admin, admin_enabled):
    st.subheader("Relatórios importados")
    st.dataframe(
        imports[["report_date","filename","row_count","imported_at"]].rename(columns={
            "report_date":"Data","filename":"Arquivo","row_count":"Membros","imported_at":"Importado em"}),
        use_container_width=True, hide_index=True)
    if admin_enabled and is_admin:
        st.divider()
        st.subheader("🗑️ Deletar import")
        st.warning("⚠️ Irreversível.")
        labels = imports["label"].tolist()
        to_del = st.selectbox("Selecionar",["— selecionar —",*labels])
        if to_del != "— selecionar —":
            row = imports.loc[imports["label"].eq(to_del)].iloc[0]
            if st.button("🗑️ Confirmar exclusão", type="secondary"):
                if storage.delete_import(row["id"]):
                    st.success("Deletado!"); st.rerun()
                else:
                    st.error("Não encontrado.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 5 — Ajuda
# ══════════════════════════════════════════════════════════════════════════════

def show_help():
    st.header("❓ Como usar")
    st.markdown("""
## Tabela de metas por City Power

| City Power   | Meta Mortes           | Meta KP |
|--------------|-----------------------|---------|
| ≤ 49M        | 900k T4 ou 450k T5    | 80M     |
| 50M – 59M    | 900k T4 ou 450k T5    | 100M    |
| 60M – 69M    | 1M T4 ou 500k T5      | 140M    |
| 70M – 79M    | 1.4M T4 ou 700k T5    | 180M    |
| 80M – 89M    | 1.6M T4 ou 800k T5    | 200M    |
| 90M – 99M    | 2M T4 ou 1M T5        | 280M    |
| ≥ 100M       | 2M T4 ou 1M T5        | 320M    |

## Equivalência de mortes
**1 T5 = 2 T4** · Exemplo: 700k T5 + 200k T4 = 1.6M T4 equivalente ✅

## Kill Points
T5×20 · T4×10 · T3×4 · T2×2 · T1×0.2

## Status
- ✅ **Aprovado** — KP e mortes atingidos
- 🟡 **Pendente** — ≥75% em ambas as metas
- ❌ **Abaixo da meta** — falta mais de 25%

## Ranking — accordion
Clique em qualquer membro para expandir e ver **todos os detalhes**: kills por tier, mortes por tier, barras de progresso e metas individuais.
""")


# ══════════════════════════════════════════════════════════════════════════════
# Formatadores
# ══════════════════════════════════════════════════════════════════════════════

def fmt_int(v) -> str: return f"{int(v):,}"
def fmt_k(v: int) -> str:
    if v>=1_000_000: return f"{v/1_000_000:.1f}M"
    if v>=1_000:     return f"{v/1_000:.0f}k"
    return str(v)
def fmt_m(v: int) -> str: return f"{v/1_000_000:.0f}"
def fmt_pct(v) -> str: return f"{float(v)*100:.1f}%"


if __name__ == "__main__":
    main()
