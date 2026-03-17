"""
Bullseye Dashboard - Página Principal
Panel de control central con KPIs globales de todas las cuentas HubSpot + Google Sheets.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
import calendar

from utils.hubspot import load_all_accounts
from utils.sheets import get_meetings_from_sheets


# ─────────────────────────────────────────
#  Helper: calcular rango de fechas según período
# ─────────────────────────────────────────
def _period_range(period_key: str):
    """Retorna (start_date, end_date, days_for_hubspot)."""
    today = date.today()
    if period_key == "este_mes":
        start = today.replace(day=1)
        end   = today
    elif period_key == "mes_pasado":
        first_this = today.replace(day=1)
        end         = first_this - timedelta(days=1)
        start       = end.replace(day=1)
    elif period_key == "ultimos_3m":
        start = today - timedelta(days=90)
        end   = today
    elif period_key == "ultimos_6m":
        start = today - timedelta(days=180)
        end   = today
    elif period_key == "este_año":
        start = today.replace(month=1, day=1)
        end   = today
    else:  # todo
        start = date(2020, 1, 1)
        end   = today
    days_hs = max((today - start).days + 1, 1)
    return start, end, days_hs

# ─────────────────────────────────────────
#  Configuración de la página
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Bullseye Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stMetric label { font-size: 13px !important; }
    div[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 700; }
    .main-title { color: #1d3557; font-size: 2rem; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  Sidebar - Período y botón actualizar
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Bullseye Dashboard")
    st.divider()

    PERIOD_OPTIONS = {
        "Este mes":        "este_mes",
        "Mes pasado":      "mes_pasado",
        "Últimos 3 meses": "ultimos_3m",
        "Últimos 6 meses": "ultimos_6m",
        "Este año":        "este_año",
        "Todo":            "todo",
    }
    period_label = st.selectbox("Período", list(PERIOD_OPTIONS.keys()), index=0)
    period_key   = PERIOD_OPTIONS[period_label]
    start_date, end_date, days = _period_range(period_key)

    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Datos actualizados cada 30 min")

# ─────────────────────────────────────────
#  Carga de datos
# ─────────────────────────────────────────
with st.spinner("Cargando datos de HubSpot..."):
    try:
        data         = load_all_accounts(st.secrets, days=days)
        calls_df     = data["calls"]
        contacts_df  = data["contacts"]
        companies_df = data["companies"]
        activities_df= data["activities"]
        account_names= data["account_names"]
    except Exception as e:
        st.error(f"Error conectando a HubSpot: {e}")
        st.stop()

with st.spinner("Cargando reuniones desde Google Sheets..."):
    try:
        meetings_df = get_meetings_from_sheets(st.secrets)
    except Exception as e:
        st.warning(f"No se pudieron cargar las reuniones: {e}")
        meetings_df = pd.DataFrame()

# ─────────────────────────────────────────
#  Sidebar - Filtros (se llenan con los datos ya cargados)
# ─────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.markdown("### 🔎 Filtros")

    # Filtro por cuenta HubSpot
    all_accounts_opts = ["Todas"] + account_names
    selected_account = st.selectbox("Cuenta HubSpot", all_accounts_opts)

    # Filtro por Cliente BullsEye (propiedad de empresa en HubSpot)
    if not companies_df.empty and "cliente_bullseye" in companies_df.columns:
        clientes_hs = sorted([
            c for c in companies_df["cliente_bullseye"].dropna().unique()
            if c and c not in ("", "nan", "None")
        ])
    else:
        clientes_hs = []
    selected_cliente_hs = st.selectbox("🏢 Cliente BullsEye (HubSpot)", ["Todos"] + clientes_hs)

    # Filtro por SDR (de HubSpot)
    if not calls_df.empty and "sdr" in calls_df.columns:
        sdrs_hs = sorted([s for s in calls_df["sdr"].dropna().unique() if s and s != ""])
    else:
        sdrs_hs = []
    selected_sdr = st.selectbox("SDR (HubSpot)", ["Todos"] + sdrs_hs)

    # Filtro por SDR (de Reuniones / Sheets)
    if not meetings_df.empty and "sdr" in meetings_df.columns:
        sdrs_sh = sorted([s for s in meetings_df["sdr"].dropna().unique() if s and s not in ("", "nan")])
    else:
        sdrs_sh = []
    selected_sdr_sheet = st.selectbox("SDR (Reuniones)", ["Todos"] + sdrs_sh)

    # Filtro por Cliente (columna "cliente" del sheet)
    if not meetings_df.empty and "cliente" in meetings_df.columns:
        clientes = sorted([c for c in meetings_df["cliente"].dropna().unique() if c and c not in ("", "nan")])
        selected_cliente = st.selectbox("Cliente", ["Todos"] + clientes)
    else:
        selected_cliente = "Todos"


# ─────────────────────────────────────────
#  Aplicar filtros
# ─────────────────────────────────────────
def filter_hs(df, account_col="account", sdr_col="sdr"):
    if df.empty:
        return df
    if selected_account != "Todas" and account_col in df.columns:
        df = df[df[account_col] == selected_account]
    if selected_sdr != "Todos" and sdr_col in df.columns:
        df = df[df[sdr_col] == selected_sdr]
    # Filtro por Cliente BullsEye: aplica sobre companies y se propaga vía join si aplica
    if selected_cliente_hs != "Todos" and "cliente_bullseye" in df.columns:
        df = df[df["cliente_bullseye"] == selected_cliente_hs]
    return df.copy()


def filter_sheet(df):
    if df.empty:
        return df
    # Filtro por fecha usando "Fecha de la reunión reserva" → columna interna "fecha"
    if "fecha" in df.columns:
        fecha = pd.to_datetime(df["fecha"]).dt.date
        df = df[(fecha >= start_date) & (fecha <= end_date)]
    if selected_sdr_sheet != "Todos" and "sdr" in df.columns:
        df = df[df["sdr"] == selected_sdr_sheet]
    if selected_cliente != "Todos" and "cliente" in df.columns:
        df = df[df["cliente"] == selected_cliente]
    return df.copy()


calls      = filter_hs(calls_df)
contacts   = filter_hs(contacts_df)
companies  = filter_hs(companies_df)
activities = filter_hs(activities_df)
meetings   = filter_sheet(meetings_df)

# ─────────────────────────────────────────
#  Header
# ─────────────────────────────────────────
st.markdown('<p class="main-title">🎯 Bullseye — Panel de Control</p>', unsafe_allow_html=True)
st.caption(
    f"**{period_label}** ({start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}) · "
    f"{len(account_names)} cuenta(s) HubSpot · "
    f"Cuenta: **{selected_account}** · "
    f"Cliente HubSpot: **{selected_cliente_hs}**"
)
st.divider()

# ─────────────────────────────────────────
#  KPIs
# ─────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)

total_calls     = len(calls) if not calls.empty else 0
connected_calls = int(calls["conectada"].sum()) if not calls.empty and "conectada" in calls.columns else 0
conn_rate       = round(connected_calls / total_calls * 100, 1) if total_calls > 0 else 0
total_contacts  = len(contacts) if not contacts.empty else 0
total_companies = len(companies) if not companies.empty else 0
avg_dur         = round(
    calls[calls["conectada"] == True]["duracion_min"].mean(), 1
) if not calls.empty and connected_calls > 0 else 0

# Reuniones: total y realizadas
total_meetings    = len(meetings) if not meetings.empty else 0
realized_meetings = int(meetings["reunión_realizada"].sum()) if not meetings.empty and "reunión_realizada" in meetings.columns else 0

c1.metric("📞 Llamadas totales",    f"{total_calls:,}")
c2.metric("✅ Conectadas",          f"{connected_calls:,}", f"{conn_rate}% tasa")
c3.metric("📅 Reuniones agendadas", f"{total_meetings:,}")
c4.metric("✔️ Reuniones realizadas", f"{realized_meetings:,}")
c5.metric("👤 Contactos nuevos",    f"{total_contacts:,}")
c6.metric("⏱️ Duración prom.",      f"{avg_dur} min")

st.divider()

# ─────────────────────────────────────────
#  Gráficos fila 1: Llamadas por SDR | Reuniones por SDR
# ─────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📞 Llamadas por SDR")
    if not calls.empty and "sdr" in calls.columns:
        sdr_calls = (
            calls.groupby("sdr")
            .agg(Total=("id", "count"), Conectadas=("conectada", "sum"))
            .reset_index()
            .sort_values("Total", ascending=False)
        )
        sdr_calls["Tasa %"] = (sdr_calls["Conectadas"] / sdr_calls["Total"] * 100).round(1)
        fig = go.Figure()
        fig.add_bar(x=sdr_calls["sdr"], y=sdr_calls["Total"],     name="Total",      marker_color="#457b9d")
        fig.add_bar(x=sdr_calls["sdr"], y=sdr_calls["Conectadas"], name="Conectadas", marker_color="#e63946")
        fig.update_layout(barmode="group", height=320, margin=dict(t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de llamadas para este período.")

with col_right:
    st.subheader("📅 Reuniones por SDR (Google Sheets)")
    if not meetings.empty and "sdr" in meetings.columns:
        _m = meetings.copy()
        if "reunión_realizada" not in _m.columns:
            _m["reunión_realizada"] = False
        sdr_meet = _m.groupby("sdr").agg(
            Agendadas  = ("sdr", "count"),
            Realizadas = ("reunión_realizada", "sum"),
        ).reset_index().sort_values("Agendadas", ascending=False)
        sdr_meet["Realizadas"]   = sdr_meet["Realizadas"].astype(int)
        sdr_meet["Pendientes"]   = sdr_meet["Agendadas"] - sdr_meet["Realizadas"]
        sdr_meet["% Realizadas"] = (
            sdr_meet["Realizadas"] / sdr_meet["Agendadas"] * 100
        ).round(1).astype(str) + "%"
        sdr_meet = sdr_meet.rename(columns={"sdr": "SDR"})
        st.dataframe(
            sdr_meet[["SDR", "Agendadas", "Realizadas", "Pendientes", "% Realizadas"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin datos de reuniones. Verifica que el Google Sheet esté compartido como 'Cualquiera con el link puede ver'.")

# ─────────────────────────────────────────
#  Gráficos fila 2: Tendencia diaria
# ─────────────────────────────────────────
st.subheader("📈 Tendencia de actividades diarias")
if not calls.empty and "dia" in calls.columns:
    daily = calls.groupby("dia").agg(Llamadas=("id","count"), Conectadas=("conectada","sum")).reset_index()
    daily["dia"] = pd.to_datetime(daily["dia"])
    fig3 = go.Figure()
    fig3.add_scatter(x=daily["dia"], y=daily["Llamadas"],   mode="lines+markers", name="Llamadas",   line=dict(color="#457b9d", width=2))
    fig3.add_scatter(x=daily["dia"], y=daily["Conectadas"], mode="lines+markers", name="Conectadas", line=dict(color="#e63946", width=2))
    if not meetings.empty and "dia" in meetings.columns:
        m_daily = meetings.groupby("dia").size().reset_index(name="Reuniones")
        m_daily["dia"] = pd.to_datetime(m_daily["dia"])
        fig3.add_scatter(x=m_daily["dia"], y=m_daily["Reuniones"], mode="lines+markers", name="Reuniones", line=dict(color="#2a9d8f", width=2, dash="dash"))
    fig3.update_layout(height=300, margin=dict(t=10, b=40), hovermode="x unified")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Sin datos de actividad para mostrar tendencia.")

st.divider()

# ─────────────────────────────────────────
#  Tabla resumen por SDR — HubSpot
# ─────────────────────────────────────────
st.subheader("📊 Resumen por SDR — HubSpot")

sdrs_hs_list = sorted(calls["sdr"].dropna().unique().tolist()) if not calls.empty and "sdr" in calls.columns else []
rows_hs = []
for sdr in sdrs_hs_list:
    if not sdr or sdr in ("", "nan"):
        continue
    sc = calls[calls["sdr"] == sdr]     if not calls.empty     else pd.DataFrame()
    sco= contacts[contacts["sdr"] == sdr] if not contacts.empty else pd.DataFrame()
    t  = len(sc)
    cn = int(sc["conectada"].sum()) if not sc.empty and "conectada" in sc.columns else 0
    rows_hs.append({
        "SDR":             sdr,
        "Cuenta":          sc["account"].iloc[0] if not sc.empty and "account" in sc.columns else "",
        "Llamadas":        t,
        "Conectadas":      cn,
        "Tasa conexión":   f"{round(cn/t*100,1)}%" if t > 0 else "0%",
        "Dur. prom. (min)":round(sc[sc["conectada"]==True]["duracion_min"].mean(),1) if not sc.empty and cn > 0 else 0,
        "Contactos nuevos":len(sco),
    })

if rows_hs:
    st.dataframe(pd.DataFrame(rows_hs), use_container_width=True, hide_index=True)
else:
    st.info("Sin datos de HubSpot para este período y filtros.")

st.divider()

# ─────────────────────────────────────────
#  Tabla resumen por SDR — Google Sheets (Reuniones)
# ─────────────────────────────────────────
st.subheader("📊 Resumen por SDR — Reuniones (Google Sheets)")

if not meetings.empty and "sdr" in meetings.columns:
    sdrs_sh_list = sorted([s for s in meetings["sdr"].dropna().unique() if s and s not in ("", "nan")])
    rows_sh = []
    for sdr in sdrs_sh_list:
        sm = meetings[meetings["sdr"] == sdr]
        agendadas  = len(sm)
        realizadas = int(sm["reunión_realizada"].sum()) if "reunión_realizada" in sm.columns else 0
        pendientes = agendadas - realizadas
        clientes_u = sm["cliente"].dropna().nunique() if "cliente" in sm.columns else 0
        rows_sh.append({
            "SDR":         sdr,
            "Agendadas":   agendadas,
            "Realizadas":  realizadas,
            "Pendientes":  pendientes,
            "Tasa realiz.":f"{round(realizadas/agendadas*100,1)}%" if agendadas > 0 else "0%",
            "Clientes":    clientes_u,
        })
    st.dataframe(pd.DataFrame(rows_sh), use_container_width=True, hide_index=True)

    # Detalle de reuniones
    with st.expander("📋 Ver detalle de reuniones"):
        cols_show = [c for c in ["fecha", "sdr", "cliente", "empresa", "contacto", "cargo", "realizado", "ejecutivo", "kam", "comentarios"] if c in meetings.columns]
        st.dataframe(
            meetings[cols_show].sort_values("fecha", ascending=False) if "fecha" in meetings.columns else meetings[cols_show],
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("Sin datos de reuniones disponibles.")

st.divider()
st.caption("🎯 Bullseye Dashboard · HubSpot + Google Sheets")
