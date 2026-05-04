"""
Bullseye Dashboard - Pagina Principal
Resumen ejecutivo de reuniones desde Google Sheets.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.auth import require_login
from utils.sheets import get_meetings_from_sheets

# -----------------------------------------
#  Page config
# -----------------------------------------
st.set_page_config(
    page_title="Bullseye Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_login()

st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 700; }
[data-testid="stMetricLabel"] { font-size: 13px !important; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------
#  Sidebar
# -----------------------------------------
with st.sidebar:
    st.markdown("## Bullseye Dashboard")
    st.divider()

    PERIOD_OPTIONS = {
        "Este mes":        ("este_mes",    0),
        "Mes pasado":      ("mes_pasado",  0),
        "Ultimos 3 meses": ("ultimos_3m",  0),
        "Este año":        ("este_año",    0),
        "Todo":            ("todo",        0),
    }

    def _period_range(period_key: str):
        today = date.today()
        if period_key == "este_mes":
            return today.replace(day=1), today
        if period_key == "mes_pasado":
            first_this = today.replace(day=1)
            end = first_this - timedelta(days=1)
            return end.replace(day=1), end
        if period_key == "ultimos_3m":
            return today - timedelta(days=90), today
        if period_key == "este_año":
            return today.replace(month=1, day=1), today
        # todo
        return date(2020, 1, 1), today

    period_label = st.selectbox("Periodo", list(PERIOD_OPTIONS.keys()), index=0)
    start_date, end_date = _period_range(PERIOD_OPTIONS[period_label][0])
    st.caption(f"📅 {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}")

    st.divider()
    if st.button("Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Datos actualizados cada 30 min")

# -----------------------------------------
#  Load data
# -----------------------------------------
with st.spinner("Cargando reuniones desde Google Sheets..."):
    try:
        meetings_df = get_meetings_from_sheets(st.secrets)
    except Exception as e:
        st.warning(f"No se pudieron cargar las reuniones: {e}")
        meetings_df = pd.DataFrame()

# -----------------------------------------
#  Filter by period
# -----------------------------------------
def filter_meetings(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "fecha" not in df.columns:
        return df
    fecha = pd.to_datetime(df["fecha"]).dt.date
    return df[(fecha >= start_date) & (fecha <= end_date)].copy()

meetings = filter_meetings(meetings_df)

# -----------------------------------------
#  Header
# -----------------------------------------
st.markdown(
    "<h1 style='color:#1d3557;font-size:2rem;font-weight:800;margin-bottom:0'>🎯 Bullseye — Panel de Control</h1>",
    unsafe_allow_html=True,
)
st.caption(
    f"**{period_label}** ({start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')})"
)
st.divider()

# -----------------------------------------
#  KPIs
# -----------------------------------------
total_meetings    = len(meetings) if not meetings.empty else 0
realized_meetings = int(meetings["reunion_realizada"].sum()) if not meetings.empty and "reunion_realizada" in meetings.columns else 0
pending_meetings  = total_meetings - realized_meetings
tasa_realizacion  = round(realized_meetings / total_meetings * 100, 1) if total_meetings > 0 else 0

sdrs_activos = meetings["sdr"].nunique() if not meetings.empty and "sdr" in meetings.columns else 0
clientes_u   = meetings["cliente"].nunique() if not meetings.empty and "cliente" in meetings.columns else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📋 Agendadas",   f"{total_meetings:,}")
c2.metric("✅ Realizadas",  f"{realized_meetings:,}")
c3.metric("⏳ Pendientes",  f"{pending_meetings:,}")
c4.metric("📈 Tasa realiz.", f"{tasa_realizacion}%")
c5.metric("👤 SDRs activos", f"{sdrs_activos}")

st.divider()

# -----------------------------------------
#  Charts
# -----------------------------------------
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Reuniones por SDR")
    if not meetings.empty and "sdr" in meetings.columns:
        _m = meetings.copy()
        if "reunion_realizada" not in _m.columns:
            _m["reunion_realizada"] = False
        sdr_meet = (
            _m.groupby("sdr")
            .agg(Agendadas=("sdr", "count"), Realizadas=("reunion_realizada", "sum"))
            .reset_index()
            .sort_values("Agendadas", ascending=False)
        )
        sdr_meet["Realizadas"] = sdr_meet["Realizadas"].astype(int)
        sdr_meet["Pendientes"] = sdr_meet["Agendadas"] - sdr_meet["Realizadas"]
        fig = go.Figure()
        fig.add_bar(x=sdr_meet["sdr"], y=sdr_meet["Realizadas"], name="Realizadas", marker_color="#2a9d8f")
        fig.add_bar(x=sdr_meet["sdr"], y=sdr_meet["Pendientes"], name="Pendientes", marker_color="#e9c46a")
        fig.update_layout(
            barmode="stack", height=340,
            margin=dict(t=10, b=40),
            legend=dict(orientation="h", y=-0.25),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de reuniones para este periodo.")

with col_right:
    st.subheader("Resumen por SDR")
    if not meetings.empty and "sdr" in meetings.columns:
        _m = meetings.copy()
        if "reunion_realizada" not in _m.columns:
            _m["reunion_realizada"] = False
        sdr_table = (
            _m.groupby("sdr")
            .agg(Agendadas=("sdr", "count"), Realizadas=("reunion_realizada", "sum"))
            .reset_index()
            .sort_values("Agendadas", ascending=False)
        )
        sdr_table["Realizadas"]   = sdr_table["Realizadas"].astype(int)
        sdr_table["Pendientes"]   = sdr_table["Agendadas"] - sdr_table["Realizadas"]
        sdr_table["% Realizadas"] = (
            sdr_table["Realizadas"] / sdr_table["Agendadas"] * 100
        ).round(1).astype(str) + "%"
        sdr_table = sdr_table.rename(columns={"sdr": "SDR"})
        st.dataframe(
            sdr_table[["SDR", "Agendadas", "Realizadas", "Pendientes", "% Realizadas"]],
            use_container_width=True,
            hide_index=True,
            height=320,
        )
    else:
        st.info("Sin datos disponibles.")

st.divider()

# -----------------------------------------
#  Clients breakdown
# -----------------------------------------
if not meetings.empty and "cliente" in meetings.columns:
    st.subheader("Reuniones por cliente")
    _m = meetings.copy()
    if "reunion_realizada" not in _m.columns:
        _m["reunion_realizada"] = False
    cli_table = (
        _m.groupby("cliente")
        .agg(Agendadas=("cliente", "count"), Realizadas=("reunion_realizada", "sum"))
        .reset_index()
        .sort_values("Agendadas", ascending=False)
    )
    cli_table["Realizadas"] = cli_table["Realizadas"].astype(int)
    cli_table["Pendientes"] = cli_table["Agendadas"] - cli_table["Realizadas"]
    cli_table["% Realizadas"] = (
        cli_table["Realizadas"] / cli_table["Agendadas"] * 100
    ).round(1).astype(str) + "%"
    cli_table = cli_table.rename(columns={"cliente": "Cliente"})
    st.dataframe(
        cli_table[["Cliente", "Agendadas", "Realizadas", "Pendientes", "% Realizadas"]],
        use_container_width=True,
        hide_index=True,
    )
    st.divider()

st.caption("Bullseye Dashboard · Google Sheets · Datos en vivo")
