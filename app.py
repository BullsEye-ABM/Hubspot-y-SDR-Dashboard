"""
Bullseye Dashboard - Página Principal
Panel de control central con KPIs globales de todas las cuentas HubSpot + Google Sheets.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from utils.hubspot import load_all_accounts
from utils.sheets import get_meetings_from_sheets

# ─────────────────────────────────────────
#  Configuración de la página
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Bullseye Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS personalizado
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 16px;
        border-left: 4px solid #e63946;
    }
    .stMetric label { font-size: 13px !important; }
    div[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 700; }
    .main-title { color: #1d3557; font-size: 2rem; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
#  Sidebar - Filtros globales
# ─────────────────────────────────────────
with st.sidebar:
    st.image("https://i.imgur.com/nXXPY3L.png", width=140) if False else None
    st.markdown("## 🎯 Bullseye Dashboard")
    st.divider()

    days = st.selectbox(
        "Período",
        options=[7, 14, 30, 60, 90, 180],
        index=2,
        format_func=lambda x: f"Últimos {x} días",
    )

    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Datos actualizados cada 30 min")

# ─────────────────────────────────────────
#  Carga de datos
# ─────────────────────────────────────────
with st.spinner("Cargando datos de HubSpot..."):
    try:
        data = load_all_accounts(st.secrets, days=days)
        calls_df = data["calls"]
        contacts_df = data["contacts"]
        companies_df = data["companies"]
        activities_df = data["activities"]
        account_names = data["account_names"]
    except Exception as e:
        st.error(f"Error conectando a HubSpot: {e}")
        st.info("Verifica que los tokens estén bien configurados en los secrets.")
        st.stop()

with st.spinner("Cargando reuniones desde Google Sheets..."):
    try:
        meetings_df = get_meetings_from_sheets(st.secrets)
    except Exception as e:
        st.warning(f"No se pudieron cargar las reuniones: {e}")
        meetings_df = pd.DataFrame()

# ─────────────────────────────────────────
#  Filtro de cuenta
# ─────────────────────────────────────────
with st.sidebar:
    all_accounts = ["Todas"] + account_names
    selected_account = st.selectbox("Cuenta HubSpot", all_accounts)

    # Filtrar SDRs disponibles
    if not calls_df.empty and "sdr" in calls_df.columns:
        sdrs = ["Todos"] + sorted(calls_df["sdr"].dropna().unique().tolist())
    else:
        sdrs = ["Todos"]
    selected_sdr = st.selectbox("SDR", sdrs)


def apply_filters(df, account_col="account", sdr_col="sdr"):
    if df.empty:
        return df
    if selected_account != "Todas" and account_col in df.columns:
        df = df[df[account_col] == selected_account]
    if selected_sdr != "Todos" and sdr_col in df.columns:
        df = df[df[sdr_col] == selected_sdr]
    return df


calls = apply_filters(calls_df)
contacts = apply_filters(contacts_df)
companies = apply_filters(companies_df)
activities = apply_filters(activities_df)
meetings = meetings_df.copy()
if not meetings.empty and selected_sdr != "Todos" and "sdr" in meetings.columns:
    meetings = meetings[meetings["sdr"] == selected_sdr]

# ─────────────────────────────────────────
#  Header
# ─────────────────────────────────────────
st.markdown('<p class="main-title">🎯 Bullseye — Panel de Control</p>', unsafe_allow_html=True)
st.caption(f"Mostrando datos de los últimos **{days} días** · {len(account_names)} cuenta(s) HubSpot conectada(s)")
st.divider()

# ─────────────────────────────────────────
#  KPIs principales
# ─────────────────────────────────────────
col1, col2, col3, col4, col5, col6 = st.columns(6)

total_calls = len(calls) if not calls.empty else 0
connected_calls = int(calls["conectada"].sum()) if not calls.empty and "conectada" in calls.columns else 0
connection_rate = round(connected_calls / total_calls * 100, 1) if total_calls > 0 else 0
total_meetings = len(meetings) if not meetings.empty else 0
total_contacts = len(contacts) if not contacts.empty else 0
total_companies = len(companies) if not companies.empty else 0
avg_duration = round(calls[calls["conectada"] == True]["duracion_min"].mean(), 1) if not calls.empty and connected_calls > 0 else 0

col1.metric("📞 Llamadas totales", f"{total_calls:,}")
col2.metric("✅ Llamadas conectadas", f"{connected_calls:,}", f"{connection_rate}% tasa")
col3.metric("📅 Reuniones agendadas", f"{total_meetings:,}")
col4.metric("👤 Contactos nuevos", f"{total_contacts:,}")
col5.metric("🏢 Empresas prospectadas", f"{total_companies:,}")
col6.metric("⏱️ Duración prom. llamada", f"{avg_duration} min")

st.divider()

# ─────────────────────────────────────────
#  Gráficos principales
# ─────────────────────────────────────────
col_left, col_right = st.columns(2)

# Llamadas por SDR
with col_left:
    st.subheader("📞 Llamadas por SDR")
    if not calls.empty and "sdr" in calls.columns:
        sdr_calls = calls.groupby("sdr").agg(
            Total=("id", "count"),
            Conectadas=("conectada", "sum"),
        ).reset_index().sort_values("Total", ascending=False)
        sdr_calls["Tasa %"] = (sdr_calls["Conectadas"] / sdr_calls["Total"] * 100).round(1)

        fig = go.Figure()
        fig.add_bar(x=sdr_calls["sdr"], y=sdr_calls["Total"], name="Total", marker_color="#457b9d")
        fig.add_bar(x=sdr_calls["sdr"], y=sdr_calls["Conectadas"], name="Conectadas", marker_color="#e63946")
        fig.update_layout(barmode="group", height=320, margin=dict(t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos de llamadas para este período.")

# Reuniones agendadas por SDR
with col_right:
    st.subheader("📅 Reuniones por SDR")
    if not meetings.empty and "sdr" in meetings.columns:
        sdr_meet = meetings.groupby("sdr").size().reset_index(name="Reuniones").sort_values("Reuniones", ascending=False)
        fig2 = px.bar(sdr_meet, x="sdr", y="Reuniones", color_discrete_sequence=["#2a9d8f"], height=320)
        fig2.update_layout(margin=dict(t=10, b=40))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sin datos de reuniones para este período.")

# Tendencia de actividades en el tiempo
st.subheader("📈 Tendencia de actividades diarias")
if not calls.empty and "dia" in calls.columns:
    daily = calls.groupby("dia").agg(
        Llamadas=("id", "count"),
        Conectadas=("conectada", "sum"),
    ).reset_index()
    daily["dia"] = pd.to_datetime(daily["dia"])

    fig3 = go.Figure()
    fig3.add_scatter(x=daily["dia"], y=daily["Llamadas"], mode="lines+markers", name="Llamadas totales", line=dict(color="#457b9d", width=2))
    fig3.add_scatter(x=daily["dia"], y=daily["Conectadas"], mode="lines+markers", name="Conectadas", line=dict(color="#e63946", width=2))

    if not meetings.empty and "dia" in meetings.columns:
        m_daily = meetings.groupby("dia").size().reset_index(name="Reuniones")
        m_daily["dia"] = pd.to_datetime(m_daily["dia"])
        fig3.add_scatter(x=m_daily["dia"], y=m_daily["Reuniones"], mode="lines+markers", name="Reuniones", line=dict(color="#2a9d8f", width=2, dash="dash"))

    fig3.update_layout(height=300, margin=dict(t=10, b=40), hovermode="x unified")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("Sin datos de actividad para mostrar tendencia.")

# ─────────────────────────────────────────
#  Tabla resumen por SDR
# ─────────────────────────────────────────
st.subheader("📊 Resumen por SDR")

rows_summary = []
sdrs_list = sorted(calls["sdr"].dropna().unique().tolist()) if not calls.empty and "sdr" in calls.columns else []
sheets_sdrs = sorted(meetings["sdr"].dropna().unique().tolist()) if not meetings.empty and "sdr" in meetings.columns else []
all_sdrs = sorted(set(sdrs_list + sheets_sdrs))

for sdr in all_sdrs:
    sdr_c = calls[calls["sdr"] == sdr] if not calls.empty else pd.DataFrame()
    sdr_m = meetings[meetings["sdr"] == sdr] if not meetings.empty else pd.DataFrame()

    t_calls = len(sdr_c)
    t_connected = int(sdr_c["conectada"].sum()) if not sdr_c.empty and "conectada" in sdr_c.columns else 0
    t_rate = round(t_connected / t_calls * 100, 1) if t_calls > 0 else 0
    t_meetings = len(sdr_m)
    avg_dur = round(sdr_c[sdr_c["conectada"] == True]["duracion_min"].mean(), 1) if not sdr_c.empty and t_connected > 0 else 0
    t_contacts = len(contacts[contacts["sdr"] == sdr]) if not contacts.empty else 0

    rows_summary.append({
        "SDR": sdr,
        "Llamadas": t_calls,
        "Conectadas": t_connected,
        "Tasa conexión": f"{t_rate}%",
        "Reuniones": t_meetings,
        "Duración prom.": f"{avg_dur} min",
        "Contactos nuevos": t_contacts,
    })

if rows_summary:
    summary_df = pd.DataFrame(rows_summary)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
else:
    st.info("Configura tus cuentas HubSpot para ver el resumen.")

st.divider()
st.caption("🎯 Bullseye Dashboard · Datos en tiempo real desde HubSpot y Google Sheets")
