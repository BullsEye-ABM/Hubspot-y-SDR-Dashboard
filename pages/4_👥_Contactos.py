"""
Página: Contactos y Empresas Prospectadas
Muestra los contactos y empresas creados/trabajados por período,
desglosado por SDR y cuenta HubSpot.
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.hubspot import load_all_accounts
from utils.auth import require_login

st.set_page_config(page_title="Contactos & Empresas", page_icon="👥", layout="wide")
require_login()

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
with st.spinner("Cargando contactos y empresas..."):
    try:
        data = load_all_accounts(st.secrets, days=days)
        contacts_df = data["contacts"]
        companies_df = data["companies"]
        account_names = data["account_names"]
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

# ── Filtros sidebar ───────────────────────
with st.sidebar:
    sel_account = st.selectbox("Cuenta", ["Todas"] + account_names)
    sdrs = ["Todos"] + (sorted(contacts_df["sdr"].dropna().unique().tolist()) if not contacts_df.empty else [])
    sel_sdr = st.selectbox("SDR", sdrs)

# ── Aplicar filtros ───────────────────────
def filter_df(df):
    if df.empty:
        return df
    if sel_account != "Todas" and "account" in df.columns:
        df = df[df["account"] == sel_account]
    if sel_sdr != "Todos" and "sdr" in df.columns:
        df = df[df["sdr"] == sel_sdr]
    return df

contacts = filter_df(contacts_df.copy())
companies = filter_df(companies_df.copy())

# ── Header ────────────────────────────────
st.title("👥 Contactos y Empresas Prospectadas")
st.caption(f"Últimos {days} días · {len(account_names)} cuenta(s) HubSpot")
st.divider()

# ── KPIs ──────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total contactos nuevos", f"{len(contacts):,}")
col2.metric("Total empresas nuevas", f"{len(companies):,}")
if not contacts.empty and "sdr" in contacts.columns:
    col3.metric("SDRs activos", f"{contacts['sdr'].nunique()}")
if not contacts.empty and "empresa" in contacts.columns:
    col4.metric("Empresas únicas en contactos", f"{contacts['empresa'].nunique()}")

st.divider()

# ── Contactos por SDR ─────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Contactos nuevos por SDR")
    if not contacts.empty and "sdr" in contacts.columns:
        c_sdr = contacts.groupby("sdr").size().reset_index(name="Contactos").sort_values("Contactos", ascending=False)
        fig1 = px.bar(c_sdr, x="sdr", y="Contactos",
                      color="Contactos", color_continuous_scale="Blues",
                      height=340)
        fig1.update_layout(coloraxis_showscale=False, xaxis_title="SDR")
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info("Sin datos de contactos.")

with col_right:
    st.subheader("Empresas nuevas por SDR")
    if not companies.empty and "sdr" in companies.columns:
        co_sdr = companies.groupby("sdr").size().reset_index(name="Empresas").sort_values("Empresas", ascending=False)
        fig2 = px.bar(co_sdr, x="sdr", y="Empresas",
                      color="Empresas", color_continuous_scale="Greens",
                      height=340)
        fig2.update_layout(coloraxis_showscale=False, xaxis_title="SDR")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sin datos de empresas.")

# ── Contactos por mes ─────────────────────
st.subheader("Contactos y empresas nuevas por mes")
col_a, col_b = st.columns(2)

with col_a:
    if not contacts.empty and "mes" in contacts.columns:
        c_monthly = contacts.groupby(["mes", "sdr"]).size().reset_index(name="Contactos")
        fig3 = px.line(c_monthly, x="mes", y="Contactos", color="sdr", markers=True, height=300)
        fig3.update_layout(xaxis_title="Mes", title="Contactos nuevos / mes")
        st.plotly_chart(fig3, use_container_width=True)

with col_b:
    if not companies.empty and "mes" in companies.columns:
        co_monthly = companies.groupby(["mes", "sdr"]).size().reset_index(name="Empresas")
        fig4 = px.line(co_monthly, x="mes", y="Empresas", color="sdr", markers=True, height=300)
        fig4.update_layout(xaxis_title="Mes", title="Empresas nuevas / mes")
        st.plotly_chart(fig4, use_container_width=True)

# ── Por industria ─────────────────────────
if not companies.empty and "industria" in companies.columns:
    st.subheader("Empresas prospectadas por industria")
    ind = companies["industria"].value_counts().reset_index()
    ind.columns = ["Industria", "Cantidad"]
    ind = ind[ind["Industria"].ne("") & ind["Industria"].notna()].head(15)
    if not ind.empty:
        fig5 = px.bar(ind, x="Cantidad", y="Industria", orientation="h",
                      color="Cantidad", color_continuous_scale="Purples", height=400)
        fig5.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig5, use_container_width=True)

# ── Tablas ────────────────────────────────
tab1, tab2 = st.tabs(["Contactos", "Empresas"])

with tab1:
    if not contacts.empty:
        show_cols = [c for c in ["fecha_local", "sdr", "account", "nombre", "empresa", "cargo", "email", "estado_lead"] if c in contacts.columns]
        disp = contacts[show_cols].copy()
        if "fecha_local" in disp.columns:
            disp["fecha_local"] = disp["fecha_local"].dt.strftime("%d/%m/%Y")
            disp = disp.rename(columns={"fecha_local": "Fecha"})
        st.dataframe(disp.head(500), use_container_width=True, hide_index=True)
    else:
        st.info("Sin contactos para el período seleccionado.")

with tab2:
    if not companies.empty:
        show_cols = [c for c in ["fecha_local", "sdr", "account", "empresa", "industria", "ciudad"] if c in companies.columns]
        disp2 = companies[show_cols].copy()
        if "fecha_local" in disp2.columns:
            disp2["fecha_local"] = disp2["fecha_local"].dt.strftime("%d/%m/%Y")
            disp2 = disp2.rename(columns={"fecha_local": "Fecha"})
        st.dataframe(disp2.head(500), use_container_width=True, hide_index=True)
    else:
        st.info("Sin empresas para el período seleccionado.")
