"""
Página: Reuniones SDR
Sheet: "Metas equipo BullsEye / reuniones / oportunidades"
Pestaña: "Gestión de reuniones"
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils.sheets import get_meetings_from_sheets

st.set_page_config(page_title="Reuniones SDR", page_icon="📅", layout="wide")

# ── Sidebar ──────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Bullseye Dashboard")
    st.divider()
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Carga de datos ────────────────────────
with st.spinner("Cargando reuniones..."):
    try:
        df_raw = get_meetings_from_sheets(st.secrets)
    except Exception as e:
        st.error(f"Error cargando Google Sheets: {e}")
        st.stop()

if df_raw.empty:
    st.warning("No se encontraron reuniones en el Google Sheet.")
    st.info("Verifica que el sheet_id, la pestaña y el api_key sean correctos en los secrets.")
    st.stop()

# ── Filtros sidebar ───────────────────────
with st.sidebar:
    min_date = df_raw["fecha"].min().date()
    max_date = df_raw["fecha"].max().date()
    date_range = st.date_input("Rango de fechas", value=(min_date, max_date),
                               min_value=min_date, max_value=max_date)

    sdrs = ["Todos"] + sorted(df_raw["sdr"].dropna().unique().tolist())
    sel_sdr = st.selectbox("Responsable (SDR)", sdrs)

    if "cliente" in df_raw.columns:
        clients = ["Todos"] + sorted(df_raw["cliente"].replace("", pd.NA).dropna().unique().tolist())
        sel_client = st.selectbox("Cliente", clients)
    else:
        sel_client = "Todos"

    if "kam" in df_raw.columns:
        kams = ["Todos"] + sorted(df_raw["kam"].replace("", pd.NA).dropna().unique().tolist())
        sel_kam = st.selectbox("KAM", kams)
    else:
        sel_kam = "Todos"

    solo_realizadas = st.checkbox("Solo reuniones realizadas", value=False)

# ── Aplicar filtros ───────────────────────
df = df_raw.copy()
if len(date_range) == 2:
    s, e = date_range
    df = df[(df["fecha"].dt.date >= s) & (df["fecha"].dt.date <= e)]
if sel_sdr != "Todos":
    df = df[df["sdr"] == sel_sdr]
if sel_client != "Todos" and "cliente" in df.columns:
    df = df[df["cliente"] == sel_client]
if sel_kam != "Todos" and "kam" in df.columns:
    df = df[df["kam"] == sel_kam]
if solo_realizadas and "reunión_realizada" in df.columns:
    df = df[df["reunión_realizada"] == True]

# ── Header ────────────────────────────────
st.title("📅 Gestión de Reuniones SDR")
st.caption(f"{len(df):,} reuniones encontradas con los filtros actuales")
st.divider()

# ── KPIs ──────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total reuniones", f"{len(df):,}")

sdrs_activos = df["sdr"].nunique() if "sdr" in df.columns else 0
col2.metric("SDRs activos", f"{sdrs_activos}")

clientes_unicos = df["cliente"].replace("", pd.NA).nunique() if "cliente" in df.columns else 0
col3.metric("Clientes cubiertos", f"{clientes_unicos}")

realizadas = int(df["reunión_realizada"].sum()) if "reunión_realizada" in df.columns else 0
col4.metric("Reuniones realizadas", f"{realizadas:,}")

tasa = round(realizadas / len(df) * 100, 1) if len(df) > 0 else 0
col5.metric("Tasa de realización", f"{tasa}%")

st.divider()

# ── Reuniones por SDR y por cliente ──────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Reuniones por Responsable (SDR)")
    sdr_count = df.groupby("sdr").agg(
        Total=("fecha", "count"),
        Realizadas=("reunión_realizada", "sum"),
    ).reset_index().sort_values("Total", ascending=False)

    fig1 = go.Figure()
    fig1.add_bar(x=sdr_count["sdr"], y=sdr_count["Total"], name="Total", marker_color="#a8dadc")
    fig1.add_bar(x=sdr_count["sdr"], y=sdr_count["Realizadas"], name="Realizadas", marker_color="#457b9d")
    fig1.update_layout(barmode="group", height=340, xaxis_title="SDR", yaxis_title="Reuniones")
    st.plotly_chart(fig1, use_container_width=True)

with col_right:
    st.subheader("Reuniones por Cliente")
    if "cliente" in df.columns:
        cl_count = df[df["cliente"].ne("")].groupby("cliente").size().reset_index(name="Reuniones")
        cl_count = cl_count.sort_values("Reuniones", ascending=False)
        fig2 = px.bar(cl_count, x="Reuniones", y="cliente", orientation="h",
                      color="Reuniones", color_continuous_scale="Blues", height=340)
        fig2.update_layout(coloraxis_showscale=False, yaxis_title="")
        st.plotly_chart(fig2, use_container_width=True)

# ── Heatmap: Día × Hora ───────────────────
st.subheader("Mejores días y horarios para agendar reuniones")

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
day_esp   = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
             "Thursday": "Jueves", "Friday": "Viernes"}

if "hora_num" in df.columns and df["hora_num"].notna().any():
    df_heat = df.copy()
    df_heat["dia_esp"] = df_heat["dia_semana"].map(day_esp)
    heat = df_heat.groupby(["dia_esp", "hora_num"]).size().reset_index(name="reuniones")
    heat_pivot = heat.pivot_table(index="dia_esp", columns="hora_num",
                                  values="reuniones", fill_value=0)
    dias_ord = [day_esp[d] for d in day_order if day_esp[d] in heat_pivot.index]
    heat_pivot = heat_pivot.reindex(dias_ord)
    fig3 = px.imshow(heat_pivot,
                     labels=dict(x="Hora del día", y="Día", color="Reuniones"),
                     color_continuous_scale="YlOrRd", aspect="auto", height=280)
    fig3.update_xaxes(tickmode="linear", tick0=8, dtick=1)
    st.plotly_chart(fig3, use_container_width=True)
    st.caption("Las celdas más oscuras = más reuniones agendadas en ese bloque horario.")
else:
    df_heat = df.copy()
    df_heat["dia_esp"] = df_heat["dia_semana"].map(day_esp)
    by_day = df_heat.groupby("dia_semana").size().reset_index(name="Reuniones")
    by_day["dia_esp"] = by_day["dia_semana"].map(day_esp)
    by_day["orden"] = by_day["dia_semana"].map({d: i for i, d in enumerate(day_order)})
    by_day = by_day.sort_values("orden")
    fig3 = px.bar(by_day, x="dia_esp", y="Reuniones", color="Reuniones",
                  color_continuous_scale="YlOrRd", height=300)
    fig3.update_layout(coloraxis_showscale=False, xaxis_title="Día de la semana")
    st.plotly_chart(fig3, use_container_width=True)

# ── Tendencia mensual ─────────────────────
st.subheader("Tendencia mensual de reuniones")
monthly = df.groupby(["mes", "sdr"]).size().reset_index(name="Reuniones")
fig4 = px.line(monthly, x="mes", y="Reuniones", color="sdr", markers=True, height=300)
fig4.update_layout(xaxis_title="Mes")
st.plotly_chart(fig4, use_container_width=True)

# ── Oportunidades / Propuestas ────────────
if "propuesta" in df.columns and df["propuesta"].replace("", pd.NA).notna().any():
    st.subheader("Propuestas / Oportunidades generadas")
    prop_count = df[df["propuesta"].ne("")].groupby(["sdr", "propuesta"]).size().reset_index(name="n")
    st.dataframe(prop_count.sort_values("n", ascending=False), use_container_width=True, hide_index=True)

# ── Tabla detalle ─────────────────────────
st.subheader("Tabla completa de reuniones")
show_cols = [c for c in [
    "fecha", "hora", "sdr", "ejecutivo", "kam", "cliente", "empresa",
    "contacto", "cargo", "pais", "realizado", "asiste",
    "propuesta", "piloto", "fuente", "origen", "comentarios"
] if c in df.columns]

display = df[show_cols].copy()
if "fecha" in display.columns:
    display["fecha"] = display["fecha"].dt.strftime("%d/%m/%Y")
    display = display.sort_values("fecha", ascending=False)

st.dataframe(display, use_container_width=True, hide_index=True)
