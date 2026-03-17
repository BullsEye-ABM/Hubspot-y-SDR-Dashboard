"""
Página: Actividades por SDR
Muestra un breakdown detallado de todas las actividades (llamadas, reuniones, emails)
por SDR, por período y por cuenta HubSpot.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils.hubspot import load_all_accounts

st.set_page_config(page_title="Actividades SDR", page_icon="📊", layout="wide")

# ── Sidebar ──────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Bullseye Dashboard")
    st.divider()
    days = st.selectbox("Período", [7, 14, 30, 60, 90, 180], index=2,
                        format_func=lambda x: f"Últimos {x} días")
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Carga de datos ────────────────────────
with st.spinner("Cargando actividades..."):
    try:
        data = load_all_accounts(st.secrets, days=days)
        activities_df = data["activities"]
        calls_df = data["calls"]
        account_names = data["account_names"]
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

# ── Filtros sidebar ───────────────────────
with st.sidebar:
    accounts_opt = ["Todas"] + account_names
    sel_account = st.selectbox("Cuenta", accounts_opt)

    if not activities_df.empty:
        sdrs = ["Todos"] + sorted(activities_df["sdr"].dropna().unique().tolist())
    else:
        sdrs = ["Todos"]
    sel_sdr = st.selectbox("SDR", sdrs)

    activity_types = ["Todos"] + (sorted(activities_df["tipo"].unique().tolist()) if not activities_df.empty else [])
    sel_type = st.selectbox("Tipo de actividad", activity_types)

# ── Combinar actividades + llamadas (calls ya no están en activities_df) ──────
if not calls_df.empty:
    calls_as_act = calls_df[["id", "account", "fecha", "sdr", "dia", "semana", "mes"]].copy()
    calls_as_act["tipo"] = "Llamada"
    # Unir con activities (meetings + emails)
    if not activities_df.empty:
        activities_df = pd.concat([activities_df, calls_as_act], ignore_index=True)
    else:
        activities_df = calls_as_act

# ── Aplicar filtros ───────────────────────
df = activities_df.copy()
if not df.empty:
    if sel_account != "Todas":
        df = df[df["account"] == sel_account]
    if sel_sdr != "Todos":
        df = df[df["sdr"] == sel_sdr]
    if sel_type != "Todos":
        df = df[df["tipo"] == sel_type]

# ── Header ────────────────────────────────
st.title("📊 Actividades por SDR")
st.caption(f"Últimos {days} días · {len(account_names)} cuenta(s) HubSpot")
st.divider()

if df.empty:
    st.warning("No hay actividades para los filtros seleccionados.")
    st.stop()

# ── KPIs ──────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
total = len(df)
by_type = df["tipo"].value_counts()
calls_n = by_type.get("Llamada", 0)
meetings_n = by_type.get("Reunión", 0)
emails_n = by_type.get("Email", 0)

col1.metric("Total actividades", f"{total:,}")
col2.metric("📞 Llamadas", f"{calls_n:,}")
col3.metric("📅 Reuniones", f"{meetings_n:,}")
col4.metric("📧 Emails", f"{emails_n:,}")

st.divider()

# ── Actividades por SDR ───────────────────
st.subheader("Actividades por SDR y tipo")
sdr_type = df.groupby(["sdr", "tipo"]).size().reset_index(name="cantidad")
fig1 = px.bar(
    sdr_type, x="sdr", y="cantidad", color="tipo",
    barmode="group",
    color_discrete_map={"Llamada": "#457b9d", "Reunión": "#2a9d8f", "Email": "#e9c46a"},
    height=380,
)
fig1.update_layout(xaxis_title="SDR", yaxis_title="Cantidad", legend_title="Tipo")
st.plotly_chart(fig1, use_container_width=True)

# ── Actividades en el tiempo ──────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Tendencia semanal")
    if "semana" in df.columns and "mes" in df.columns:
        weekly = df.groupby(["mes", "semana", "sdr"]).size().reset_index(name="cantidad")
        weekly["período"] = weekly["mes"].astype(str) + "-S" + weekly["semana"].astype(str)
        fig2 = px.line(weekly, x="período", y="cantidad", color="sdr", markers=True, height=320)
        fig2.update_layout(xaxis_title="Semana", yaxis_title="Actividades")
        st.plotly_chart(fig2, use_container_width=True)

with col_b:
    st.subheader("Distribución por tipo de actividad")
    type_dist = df.groupby("tipo").size().reset_index(name="cantidad")
    fig3 = px.pie(type_dist, values="cantidad", names="tipo", hole=0.4,
                  color_discrete_map={"Llamada": "#457b9d", "Reunión": "#2a9d8f", "Email": "#e9c46a"},
                  height=320)
    st.plotly_chart(fig3, use_container_width=True)

# ── Tabla resumen por SDR ─────────────────
st.subheader("Detalle por SDR")
pivot = df.pivot_table(index="sdr", columns="tipo", values="id", aggfunc="count", fill_value=0)
pivot.columns.name = None
pivot["Total"] = pivot.sum(axis=1)
pivot = pivot.sort_values("Total", ascending=False).reset_index()
pivot = pivot.rename(columns={"sdr": "SDR"})
st.dataframe(pivot, use_container_width=True, hide_index=True)

# ── Actividades por mes ───────────────────
st.subheader("Actividades por mes")
monthly = df.groupby(["mes", "tipo"]).size().reset_index(name="cantidad")
fig4 = px.bar(monthly, x="mes", y="cantidad", color="tipo", barmode="stack",
              color_discrete_map={"Llamada": "#457b9d", "Reunión": "#2a9d8f", "Email": "#e9c46a"},
              height=320)
fig4.update_layout(xaxis_title="Mes", yaxis_title="Actividades")
st.plotly_chart(fig4, use_container_width=True)
