"""
ALLO · Gestion Telefonica
Bullseye · ALLO API · Cache 15 min
Actividad de llamadas por SDR y por numero/cliente, tasas de conexion
(sin voicemail), reuniones agendadas y desglose por etiquetas.
Diseno: sistema de marca BullsEye (navy #251762 / turquesa #62E0D8).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime

from utils.auth import require_login
from utils.allo import (
    list_numbers, list_users, list_tags, fetch_conversation_items,
    items_to_dataframe, connection_rate_excl_voicemail, meetings_booked_count,
    tag_breakdown, breakdown_by, CONNECTED_RESULTS, MEETING_TAG,
    get_outbound_funnel, get_outbound_funnel_per_user, get_outbound_funnel_per_number,
)
from utils.periods import PERIOD_OPTIONS, get_period_dates


# ─────────────────────────────────────────
#  Page config & CSS (sistema de marca BullsEye)
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Bullseye · ALLO",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_login()

st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800&display=swap");

:root {
  --be-navy-900:#150C3A; --be-navy-800:#1C1049; --be-navy-700:#251762;
  --be-navy-600:#3A2A82; --be-navy-500:#5344A3;
  --be-teal-100:#EAF9F7; --be-teal-200:#C7EDE9; --be-teal-300:#8FE9E3;
  --be-teal-400:#62E0D8; --be-teal-600:#1FA39B;
  --be-white:#FFFFFF; --be-surface:#F6F7FB; --be-surface-alt:#FAFAFD;
  --be-border-subtle:#EEEFF6; --be-border:#E6E7F1; --be-border-strong:#C9CAD8;
  --be-grey-500:#9795AD; --be-grey-600:#6E6B8A; --be-grey-700:#54516E; --be-grey-800:#3A3752;
  --be-positive:#22A06B; --be-warning:#E0A030; --be-negative:#C4404A;
}
html, body, [data-testid="stAppViewContainer"] {
  background: var(--be-surface);
  color: var(--be-grey-700);
  font-family: 'Montserrat', system-ui, -apple-system, sans-serif;
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.5rem; padding-bottom: 4rem; max-width: 1360px; }
p, span, div, label { font-family: 'Montserrat', system-ui, -apple-system, sans-serif; }

/* ── Header ── */
.brand-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  border-bottom: 1px solid var(--be-border); padding-bottom: 20px; margin-bottom: 28px;
  gap: 20px; flex-wrap: wrap;
}
.brand-left { display: flex; align-items: center; gap: 14px; }
.brand-logo {
  width: 44px; height: 44px; border-radius: 12px;
  background: var(--be-navy-700);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 15px; color: var(--be-teal-400); letter-spacing: -.02em;
}
.brand-overline {
  font-size: 11px; text-transform: uppercase; letter-spacing: .18em;
  color: var(--be-teal-600); font-weight: 700; margin: 0 0 2px;
}
.brand-title { font-size: 22px; font-weight: 800; margin: 0; color: var(--be-navy-800); letter-spacing: -.01em; }
.brand-sub { font-size: 13px; color: var(--be-grey-600); margin: 3px 0 0; font-weight: 500; }
.brand-right { text-align: right; font-size: 12.5px; color: var(--be-grey-600); font-weight: 500; }
.brand-right strong { color: var(--be-navy-800); display: block; font-size: 13.5px; font-weight: 700; }
.pill {
  display: inline-block; padding: 4px 12px; border-radius: 999px;
  background: var(--be-teal-100); color: var(--be-teal-600);
  font-size: 11px; font-weight: 700; margin-top: 8px;
}

/* ── Section labels ── */
.section-title {
  font-size: 11.5px; text-transform: uppercase; letter-spacing: .14em;
  color: var(--be-grey-600); font-weight: 700; margin: 36px 0 14px;
  display: flex; align-items: center; gap: 8px;
}
.section-title::before {
  content: ""; width: 20px; height: 3px; border-radius: 2px;
  background: var(--be-teal-400); display: inline-block;
}

/* ── KPI cards ── */
.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; margin-bottom: 8px; }
@media (max-width: 1100px) { .kpi-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 600px)  { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi {
  background: var(--be-white); border: 1px solid var(--be-border);
  border-radius: 18px; padding: 18px 20px;
  box-shadow: 0 2px 14px rgba(37,23,98,.05);
}
.kpi-label {
  font-size: 10.5px; text-transform: uppercase; letter-spacing: .1em;
  color: var(--be-grey-500); margin-bottom: 10px; font-weight: 700;
}
.kpi-value { font-size: 28px; font-weight: 800; letter-spacing: -.01em; line-height: 1.1; color: var(--be-navy-800); }
.kpi-sub { font-size: 11.5px; color: var(--be-grey-500); margin-top: 6px; font-weight: 500; }
.kpi.hero { background: var(--be-navy-700); border-color: var(--be-navy-700); }
.kpi.hero .kpi-label { color: rgba(255,255,255,.62); }
.kpi.hero .kpi-value { color: var(--be-white); }
.kpi.hero .kpi-sub { color: rgba(255,255,255,.62); }

/* ── Generic card ── */
.card {
  background: var(--be-white); border: 1px solid var(--be-border);
  border-radius: 18px; padding: 20px;
  box-shadow: 0 2px 14px rgba(37,23,98,.05);
}

/* ── Sidebar ── */
[data-testid="stSidebar"] { background: var(--be-white) !important; border-right: 1px solid var(--be-border); }
[data-testid="stSidebar"] * { color: var(--be-grey-700) !important; font-family: 'Montserrat', sans-serif !important; }
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] small {
  color: var(--be-grey-500) !important; font-weight: 600 !important;
}
[data-testid="stSidebar"] h3 {
  color: var(--be-navy-800) !important; font-size: 11px !important;
  text-transform: uppercase; letter-spacing: .14em; font-weight: 800 !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="input"] > div {
  background: var(--be-surface) !important;
  border: 1px solid var(--be-border) !important;
  color: var(--be-navy-800) !important; border-radius: 8px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] svg { fill: var(--be-grey-500) !important; }
[data-testid="stSidebar"] [data-baseweb="tag"],
[data-testid="stSidebar"] [data-baseweb="tag"] > span,
[data-testid="stSidebar"] span[data-baseweb="tag"] {
  background-color: var(--be-navy-700) !important;
  background: var(--be-navy-700) !important;
  border-radius: 6px !important;
}
[data-testid="stSidebar"] [data-baseweb="tag"] * { color: var(--be-white) !important; fill: var(--be-white) !important; }
[data-testid="stSidebar"] [data-baseweb="popover"] li { color: var(--be-navy-800) !important; }
[data-testid="stSidebar"] hr { border-color: var(--be-border) !important; }
[data-testid="stSidebar"] .stButton button {
  background-color: var(--be-navy-700) !important;
  background: var(--be-navy-700) !important;
  border: none !important; border-radius: 8px !important;
  transition: background 160ms ease;
}
[data-testid="stSidebar"] .stButton button:hover {
  background-color: var(--be-navy-800) !important;
  background: var(--be-navy-800) !important;
}
[data-testid="stSidebar"] .stButton button * {
  color: var(--be-white) !important; font-weight: 700 !important; opacity: 1 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--be-border); }
.stTabs [data-baseweb="tab"] { padding: 8px 16px; color: var(--be-grey-600); font-weight: 600; }
.stTabs [aria-selected="true"] { color: var(--be-navy-800) !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--be-teal-400) !important; }

hr { margin: 1.2rem 0; border-color: var(--be-border); }

/* ── Tables ── */
.dt {
  width: 100%; border-collapse: collapse; font-size: 13px;
  background: var(--be-white); border-radius: 14px; overflow: hidden;
  border: 1px solid var(--be-border); margin-bottom: 8px;
}
.dt th, .dt td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--be-border-subtle); }
.dt th {
  color: var(--be-grey-500); font-weight: 700; font-size: 10.5px;
  text-transform: uppercase; letter-spacing: .08em; background: var(--be-surface-alt);
}
.dt td { color: var(--be-grey-700); font-weight: 500; }
.dt tr:last-child td { border-bottom: none; }
.dt tr:hover td { background: var(--be-surface-alt); }
.dt-wrap { max-height: 460px; overflow-y: auto; border-radius: 14px; }

/* ── Ranking (avatar + progress bar) ── */
.rk-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.rk-table td { padding: 12px 10px; border-bottom: 1px solid var(--be-border-subtle); vertical-align: middle; }
.rk-table tr:last-child td { border-bottom: none; }
.rk-name { display: flex; align-items: center; gap: 12px; min-width: 200px; }
.rk-avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  background: var(--be-teal-100); color: var(--be-navy-700);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 12px;
}
.rk-name span { font-weight: 700; color: var(--be-navy-800); }
.rk-bar-wrap { min-width: 140px; }
.rk-bar { height: 6px; border-radius: 4px; background: var(--be-border-subtle); overflow: hidden; }
.rk-bar i { display: block; height: 100%; background: var(--be-navy-700); border-radius: 4px; }
.rk-num { font-weight: 700; color: var(--be-navy-800); text-align: right; }
.rk-num-sub { font-weight: 500; color: var(--be-grey-500); text-align: right; font-size: 12px; }

[data-testid="stMain"] [data-baseweb="select"] > div,
section.main [data-baseweb="select"] > div {
  background: var(--be-white) !important; border: 1px solid var(--be-border) !important;
  color: var(--be-navy-800) !important; border-radius: 8px !important;
}
[data-baseweb="popover"], [data-baseweb="popover"] *,
[data-baseweb="menu"], [data-baseweb="menu"] *,
[role="listbox"], [role="listbox"] * {
  background-color: var(--be-white) !important; color: var(--be-navy-800) !important;
  border-color: var(--be-border) !important;
}
[data-baseweb="popover"] {
  border: 1px solid var(--be-border) !important; border-radius: 10px !important;
  box-shadow: 0 10px 30px rgba(37,23,98,.14) !important;
}
[data-baseweb="popover"] li:hover, [data-baseweb="menu"] li:hover,
[role="option"]:hover, [role="option"][aria-selected="true"] {
  background-color: var(--be-teal-100) !important; color: var(--be-navy-800) !important;
}
[data-testid="stExpander"] {
  background: var(--be-white) !important; border: 1px solid var(--be-border) !important;
  border-radius: 12px !important; margin-bottom: 8px;
  box-shadow: 0 2px 14px rgba(37,23,98,.05);
}
[data-testid="stExpander"] summary { color: var(--be-navy-800) !important; font-weight: 600; }
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] { color: var(--be-grey-700); }
[data-testid="stAlert"] { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)


BRAND_CATEGORICAL = [
    "#251762", "#1FA39B", "#E0A030", "#5344A3", "#9795AD", "#62E0D8", "#C4404A", "#3A2A82",
]

PLOT_TEMPLATE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#54516E", family="Montserrat, sans-serif"),
    margin=dict(t=50, b=20, l=20, r=20),
)


def _data_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df is None or df.empty:
        return '<div class="card"><em style="color:var(--be-grey-500)">Sin datos.</em></div>'
    headers = "".join(f"<th>{c}</th>" for c in columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{row[c]}</td>" for c in columns)
        rows.append(f"<tr>{cells}</tr>")
    return (
        f'<div class="dt-wrap"><table class="dt">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table></div>'
    )


def _initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _ranking_table(df: pd.DataFrame, name_col: str, name_label: str) -> str:
    """Ranking con avatar + barra de progreso, ordenado por actividades desc."""
    if df is None or df.empty:
        return '<div class="card"><em style="color:var(--be-grey-500)">Sin datos.</em></div>'
    max_val = df["actividades"].max() or 1
    rows = []
    for _, r in df.iterrows():
        pct = round(r["actividades"] / max_val * 100)
        rows.append(
            "<tr>"
            f'<td><div class="rk-name"><div class="rk-avatar">{_initials(str(r[name_col]))}</div>'
            f'<span>{r[name_col]}</span></div></td>'
            f'<td class="rk-bar-wrap"><div class="rk-bar"><i style="width:{pct}%"></i></div></td>'
            f'<td class="rk-num">{int(r["actividades"])}</td>'
            f'<td class="rk-num-sub">{int(r["conectadas"])} conect.</td>'
            f'<td class="rk-num">{r["tasa_conexion"]:.0f}%</td>'
            f'<td class="rk-num">{int(r["reuniones_agendadas"])}</td>'
            "</tr>"
        )
    return (
        '<div class="card"><table class="rk-table">'
        f'<thead><tr><th style="text-align:left;color:var(--be-grey-500);font-size:10.5px;'
        f'text-transform:uppercase;letter-spacing:.08em">{name_label}</th>'
        '<th></th><th class="rk-num" style="color:var(--be-grey-500);font-size:10.5px;'
        'text-transform:uppercase;letter-spacing:.08em">Llamadas</th>'
        '<th class="rk-num" style="color:var(--be-grey-500);font-size:10.5px"></th>'
        '<th class="rk-num" style="color:var(--be-grey-500);font-size:10.5px;'
        'text-transform:uppercase;letter-spacing:.08em">Conexion</th>'
        '<th class="rk-num" style="color:var(--be-grey-500);font-size:10.5px;'
        'text-transform:uppercase;letter-spacing:.08em">Reuniones</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def fmt_duration(mins: float) -> str:
    if not mins:
        return "–"
    m = int(mins)
    s = int((mins - m) * 60)
    return f"{m}:{s:02d}"


# ─────────────────────────────────────────
#  Reference data
# ─────────────────────────────────────────
numbers = list_numbers()
users = list_users()
tags_catalog = list_tags()

number_name_map = {n["number"]: n.get("name") or n["number"] for n in numbers}
user_name_map = {u["id"]: u["name"] for u in users}
user_id_by_name = {u["name"]: u["id"] for u in users}
all_user_ids = [u["id"] for u in users]
all_numbers_list = [n["number"] for n in numbers]


# ─────────────────────────────────────────
#  Sidebar filters
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filtros")
    period = st.selectbox(
        "Periodo", PERIOD_OPTIONS, index=2,
        help="Cambia el rango temporal del informe completo",
    )
    start_date, end_date = get_period_dates(period)
    st.caption(f"{start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}")
    st.divider()

    sdr_options = ["Todos"] + [u["name"] for u in users]
    sdr_choice = st.multiselect("SDR", sdr_options, default=["Todos"])

    number_labels = [f"{n.get('name') or n['number']} ({n['number']})" for n in numbers]
    number_label_to_number = {
        f"{n.get('name') or n['number']} ({n['number']})": n["number"] for n in numbers
    }
    number_choice = st.multiselect("Número / Cliente", ["Todos"] + number_labels, default=["Todos"])

    st.divider()
    if st.button("Forzar actualización", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache: 15 min · Datos en vivo desde ALLO")
    st.caption(f"Última carga: {datetime.now().strftime('%H:%M:%S')}")


# ─────────────────────────────────────────
#  Filter state — ALLO's own analytics API rejects combining a SDR filter
#  with a numero/cliente filter in one call (its own dashboard has the same
#  "By User / By Phone" mutually exclusive toggle). So official numbers are
#  used whenever at most one of the two dimensions is narrowed; when both
#  are narrowed at once, everything falls back to the raw call log.
# ─────────────────────────────────────────
sdr_narrowed = bool(sdr_choice) and "Todos" not in sdr_choice
number_narrowed = bool(number_choice) and "Todos" not in number_choice
both_narrowed = sdr_narrowed and number_narrowed

selected_user_ids = [user_id_by_name[n] for n in sdr_choice if n in user_id_by_name] if sdr_narrowed else []
selected_numbers_list = [
    number_label_to_number[lbl] for lbl in number_choice if lbl in number_label_to_number
] if number_narrowed else []


# ─────────────────────────────────────────
#  Header
# ─────────────────────────────────────────
st.markdown(
    f'<div class="brand-header"><div class="brand-left"><div class="brand-logo">BE</div>'
    f'<div><div class="brand-overline">Reportería ALLO</div>'
    f'<div class="brand-title">Gestión telefónica</div>'
    f'<div class="brand-sub">Actividad de llamadas por SDR y por cliente</div></div></div>'
    f'<div class="brand-right"><strong>Datos al {datetime.now().strftime("%d %b %Y")}</strong>'
    f'<span>Periodo: {start_date.strftime("%d %b %Y")} → {end_date.strftime("%d %b %Y")}</span>'
    f'<div class="pill">{len(numbers)} números · {len(users)} SDRs</div></div></div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────
#  Fetch + filter data
# ─────────────────────────────────────────
raw_items, truncated = fetch_conversation_items(start_date, end_date, item_type="ALL")
df_all = items_to_dataframe(raw_items)

if truncated:
    st.warning(
        f"El periodo seleccionado tiene más actividad de la que se puede cargar de una vez "
        f"(límite {len(raw_items):,} registros). Los datos mostrados corresponden solo a una parte "
        f"del periodo; reduce el rango de fechas para ver el total exacto."
    )

df = df_all.copy()
if not df.empty:
    df["client_name"] = df["allo_number"].map(number_name_map).fillna(df["allo_number"])

    if sdr_choice and "Todos" not in sdr_choice:
        df = df[df["user_name"].isin(sdr_choice)]

    if number_choice and "Todos" not in number_choice:
        selected_numbers = [number_label_to_number[lbl] for lbl in number_choice if lbl in number_label_to_number]
        df = df[df["allo_number"].isin(selected_numbers)]

    df["date_local"] = df["date"].dt.tz_convert("America/Santiago")
    df["date_day"] = df["date_local"].dt.date


# ─────────────────────────────────────────
#  KPIs — sourced from ALLO's own official analytics whenever possible
# ─────────────────────────────────────────
total_activities = len(df)
calls_df = df[df["type"] == "CALL"] if not df.empty else df
outbound_calls = calls_df[calls_df["direction"] == "OUTBOUND"] if not calls_df.empty else calls_df

# Voicemail count is informational only (ALLO's funnel API doesn't expose it
# as a standalone number) — always read from the raw, already-filtered log.
_, _, voicemail_n, _ = connection_rate_excl_voicemail(df)

official_funnel = None
if not both_narrowed:
    official_funnel = get_outbound_funnel(
        start_date, end_date,
        user_ids=tuple(selected_user_ids) if selected_user_ids else None,
        allo_numbers=tuple(selected_numbers_list) if selected_numbers_list else None,
    )
    dials_n = official_funnel["dials"]
    connected_n = official_funnel["connected"]
    conn_rate = official_funnel["connected_rate"]
    meetings_n = official_funnel["meetings"]
    avg_conn_dur = official_funnel["avg_conversation_seconds"] / 60
else:
    conn_rate, connected_n, _, denom = connection_rate_excl_voicemail(df)
    dials_n = denom + voicemail_n
    meetings_n = meetings_booked_count(df)
    avg_conn_dur = (
        outbound_calls.loc[outbound_calls["result"].isin(CONNECTED_RESULTS), "duration_min"].mean()
        if not outbound_calls.empty else 0
    )

st.markdown('<div class="section-title">Indicadores clave</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="kpi-row">'
    f'<div class="kpi"><div class="kpi-label">Actividades</div><div class="kpi-value">{total_activities}</div>'
    f'<div class="kpi-sub">Llamadas + SMS en el periodo</div></div>'
    f'<div class="kpi"><div class="kpi-label">Llamadas salientes</div><div class="kpi-value">{dials_n}</div>'
    f'<div class="kpi-sub">Dial-outs del equipo</div></div>'
    f'<div class="kpi hero"><div class="kpi-label">Tasa de conexión</div><div class="kpi-value">{conn_rate:.1f}%</div>'
    f'<div class="kpi-sub">Conectadas: {connected_n}</div></div>'
    f'<div class="kpi"><div class="kpi-label">Voicemail</div><div class="kpi-value">{voicemail_n}</div>'
    f'<div class="kpi-sub">Informativo, no oficial de ALLO</div></div>'
    f'<div class="kpi"><div class="kpi-label">Reuniones agendadas</div><div class="kpi-value">{meetings_n}</div>'
    f'<div class="kpi-sub">Etiqueta "Meeting booked"</div></div>'
    f'<div class="kpi"><div class="kpi-label">Duración prom. conectadas</div><div class="kpi-value">{fmt_duration(avg_conn_dur)}</div>'
    f'<div class="kpi-sub">Llamadas conectadas</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

if both_narrowed:
    st.caption(
        "Estos indicadores se calculan desde el detalle de llamadas: ALLO no permite "
        "combinar un filtro de SDR con uno de número/cliente en su propia analítica oficial. "
        "Con un solo filtro a la vez, los indicadores vienen directo de ALLO."
    )
else:
    st.caption("Indicadores calculados por la analítica oficial de ALLO (los mismos números que su propio dashboard).")

if df.empty:
    st.info("No hay actividad de ALLO en este periodo con los filtros seleccionados.")
    st.stop()


# ─────────────────────────────────────────
#  Charts: temporal
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Actividad temporal</div>', unsafe_allow_html=True)
col_a, col_b = st.columns([2, 1])

if official_funnel is not None:
    # Official ALLO time series (exact match with their own dashboard).
    ts = official_funnel["time_series"]
    daily = pd.DataFrame(ts["dials"]).rename(columns={"value": "dials"}) if ts["dials"] else pd.DataFrame()
    if not daily.empty:
        connected_map = {d["date"]: d["value"] for d in ts["connected"]}
        rate_map = {d["date"]: d["value"] * 100 for d in ts["connection_rate"]}
        daily["connected"] = daily["date"].map(connected_map).fillna(0)
        daily["no_conectadas"] = daily["dials"] - daily["connected"]
        daily["rate"] = daily["date"].map(rate_map).fillna(0)
        daily["date"] = pd.to_datetime(daily["date"]).dt.date
        daily = daily.sort_values("date")

    with col_a:
        fig = go.Figure()
        if not daily.empty:
            fig.add_bar(x=daily["date"], y=daily["connected"], name="Conectadas", marker_color="#22A06B")
            fig.add_bar(x=daily["date"], y=daily["no_conectadas"], name="No conectadas", marker_color="#C9CAD8")
        fig.update_layout(
            title=dict(text="Llamadas por día (oficial ALLO)", font=dict(color="#1C1049", size=15, family="Montserrat, sans-serif")),
            barmode="stack", height=380,
            legend=dict(orientation="h", y=-0.2),
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#EEEFF6"),
            **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig2 = go.Figure()
        if not daily.empty:
            fig2.add_bar(
                x=daily["date"], y=daily["rate"],
                marker_color="#1FA39B",
                text=[f"{v:.0f}%" for v in daily["rate"]], textposition="outside",
                textfont=dict(color="#54516E"),
            )
        fig2.update_layout(
            title=dict(text="% Conexión por día (oficial ALLO)", font=dict(color="#1C1049", size=15, family="Montserrat, sans-serif")),
            height=380,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="#EEEFF6", range=[0, 110], ticksuffix="%"),
            **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig2, use_container_width=True)
        if daily.empty:
            st.info("Sin llamadas salientes en este periodo.")

else:
    # Fallback: both SDR and numero/cliente filters active at once — computed
    # from the raw call log using the same voicemail-excluding formula.
    with col_a:
        daily = (
            calls_df.assign(
                conectada=lambda x: x["result"].isin(CONNECTED_RESULTS).astype(int),
                voicemail=lambda x: (x["result"] == "VOICEMAIL").astype(int),
                otro=lambda x: (~x["result"].isin(CONNECTED_RESULTS) & (x["result"] != "VOICEMAIL")).astype(int),
            )
            .groupby("date_day")[["conectada", "voicemail", "otro"]].sum().reset_index()
            .sort_values("date_day")
        ) if not calls_df.empty else pd.DataFrame()

        fig = go.Figure()
        if not daily.empty:
            fig.add_bar(x=daily["date_day"], y=daily["conectada"], name="Conectadas", marker_color="#22A06B")
            fig.add_bar(x=daily["date_day"], y=daily["voicemail"], name="Voicemail", marker_color="#E0A030")
            fig.add_bar(x=daily["date_day"], y=daily["otro"], name="Otros", marker_color="#C9CAD8")
        fig.update_layout(
            title=dict(text="Llamadas por día (detalle)", font=dict(color="#1C1049", size=15, family="Montserrat, sans-serif")),
            barmode="stack", height=380,
            legend=dict(orientation="h", y=-0.2),
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#EEEFF6"),
            **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        daily_rate = (
            outbound_calls.assign(
                is_vm=lambda x: (x["result"] == "VOICEMAIL"),
                is_conn=lambda x: x["result"].isin(CONNECTED_RESULTS),
            )
            .groupby("date_day")
            .apply(lambda g: pd.Series({
                "denom": (~g["is_vm"]).sum(),
                "connected": g["is_conn"].sum(),
            }))
            .reset_index()
        ) if not outbound_calls.empty else pd.DataFrame()

        if not daily_rate.empty:
            daily_rate["rate"] = daily_rate.apply(
                lambda r: (r["connected"] / r["denom"] * 100) if r["denom"] > 0 else 0, axis=1
            )

            fig2 = go.Figure()
            fig2.add_bar(
                x=daily_rate["date_day"], y=daily_rate["rate"],
                marker_color="#1FA39B",
                text=[f"{v:.0f}%" for v in daily_rate["rate"]], textposition="outside",
                textfont=dict(color="#54516E"),
            )
            fig2.update_layout(
                title=dict(text="% Conexión por día (sin voicemail, detalle)", font=dict(color="#1C1049", size=15, family="Montserrat, sans-serif")),
                height=380,
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor="#EEEFF6", range=[0, 110], ticksuffix="%"),
                **PLOT_TEMPLATE,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sin llamadas salientes en este periodo.")


# ─────────────────────────────────────────
#  Tags breakdown
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Agrupación por etiquetas</div>', unsafe_allow_html=True)
tags_df = tag_breakdown(calls_df, tags_catalog)

if tags_df.empty:
    st.info("Sin llamadas etiquetadas en este periodo.")
else:
    tags_df = tags_df.reset_index(drop=True)
    tags_df["brand_color"] = [BRAND_CATEGORICAL[i % len(BRAND_CATEGORICAL)] for i in tags_df.index]

    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        fig3 = px.pie(
            tags_df, names="tag_name", values="count",
            color="tag_name",
            color_discrete_map=dict(zip(tags_df["tag_name"], tags_df["brand_color"])),
            hole=0.6,
        )
        fig3.update_traces(textinfo="percent+label", textposition="outside",
                           marker=dict(line=dict(color="#FFFFFF", width=3)))
        fig3.update_layout(
            title=dict(text="Distribución de etiquetas", font=dict(color="#1C1049", size=15, family="Montserrat, sans-serif")),
            height=380, showlegend=False, **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig3, use_container_width=True)
    with col_t2:
        show_tags = tags_df[["tag_name", "count"]].rename(columns={"tag_name": "Etiqueta", "count": "Llamadas"})
        st.markdown(_data_table(show_tags, show_tags.columns.tolist()), unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Ranking por SDR y por numero/cliente — analitica oficial de ALLO cuando
#  la otra dimension no esta restringida; detalle de llamadas si no.
# ─────────────────────────────────────────
def _official_ranking(rows: list[dict], id_col: str, name_col: str, id_to_name: dict) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame([{
        name_col: id_to_name.get(r[id_col], r[id_col]),
        "actividades": r["dials"],
        "conectadas": r["connected"],
        "tasa_conexion": round(r["connected_rate"], 1),
        "reuniones_agendadas": r["meetings"],
    } for r in rows])
    return out.sort_values("actividades", ascending=False)


st.markdown('<div class="section-title">Ranking por SDR</div>', unsafe_allow_html=True)
if number_narrowed:
    sdr_rank = breakdown_by(calls_df, "user_name")
    st.caption("Fuente: detalle de llamadas (ALLO no permite un ranking por SDR combinado con filtro de número).")
else:
    sdr_ids = selected_user_ids if sdr_narrowed else all_user_ids
    sdr_rows = get_outbound_funnel_per_user(start_date, end_date, sdr_ids)
    sdr_rank = _official_ranking(sdr_rows, "user_id", "user_name", user_name_map)
    st.caption("Fuente: analítica oficial de ALLO.")
st.markdown(_ranking_table(sdr_rank, "user_name", "SDR"), unsafe_allow_html=True)

st.markdown('<div class="section-title">Ranking por número / cliente</div>', unsafe_allow_html=True)
if sdr_narrowed:
    client_rank = breakdown_by(calls_df, "client_name")
    st.caption("Fuente: detalle de llamadas (ALLO no permite un ranking por número combinado con filtro de SDR).")
else:
    number_ids = selected_numbers_list if number_narrowed else all_numbers_list
    client_rows = get_outbound_funnel_per_number(start_date, end_date, number_ids)
    client_rank = _official_ranking(client_rows, "allo_number", "client_name", number_name_map)
    st.caption("Fuente: analítica oficial de ALLO.")
st.markdown(_ranking_table(client_rank, "client_name", "Cliente / Número"), unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Detail tabs
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Detalle</div>', unsafe_allow_html=True)
tab1, tab2 = st.tabs([
    f"Actividades ({total_activities})",
    f"Reuniones agendadas ({meetings_n})",
])

TAG_NAME_MAP = {t["id"]: t["name"] for t in tags_catalog}

with tab1:
    show = df[[
        "date_local", "user_name", "client_name", "contact_number",
        "type", "direction", "result", "duration_min", "summary", "tags",
    ]].copy()
    show["date_local"] = show["date_local"].dt.strftime("%Y-%m-%d %H:%M")
    show["duration_min"] = show["duration_min"].round(1)
    show["tags"] = show["tags"].apply(lambda ts: ", ".join(TAG_NAME_MAP.get(t, t) for t in ts) if ts else "")
    show.columns = [
        "Fecha/Hora", "SDR", "Cliente/Número", "Contacto", "Tipo", "Dirección",
        "Resultado", "Duración (min)", "Resumen", "Etiquetas",
    ]
    st.markdown(_data_table(show.head(500), show.columns.tolist()), unsafe_allow_html=True)
    if len(show) > 500:
        st.caption(f"Mostrando las primeras 500 de {len(show)} actividades. Ajusta los filtros para acotar.")

with tab2:
    meetings_df = df[df["tags"].apply(lambda t: MEETING_TAG in t)]
    if meetings_df.empty:
        st.info("Sin reuniones agendadas en este periodo con los filtros seleccionados.")
    else:
        for _, m in meetings_df.sort_values("date", ascending=False).iterrows():
            date_str = m["date_local"].strftime("%d %b %Y %H:%M")
            with st.expander(f"{m['user_name']} · {m['client_name']} · {date_str}"):
                st.markdown(f"**Contacto:** {m['contact_number']}")
                st.markdown(f"**Duración:** {fmt_duration(m['duration_min'])}")
                if m.get("summary"):
                    st.markdown("**Resumen**")
                    st.markdown(m["summary"])
                if m.get("recording_url"):
                    st.audio(m["recording_url"])


# Footer
st.divider()
st.caption(
    "Datos en vivo desde ALLO · Bullseye · Cache 15 min · "
    "Indicadores, gráficos y rankings usan la analítica oficial de ALLO (misma fuente que su dashboard) "
    "salvo al combinar filtro de SDR + número a la vez, caso en que ALLO no ofrece un numero oficial "
    "combinado y se calcula desde el detalle de llamadas · "
    "Más reportes se irán agregando a esta página."
)
