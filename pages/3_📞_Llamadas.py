"""
Página: Análisis de Llamadas
Métricas de llamadas realizadas, conectadas, duración promedio
y transcripciones de las mejores llamadas.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils.hubspot import load_all_accounts

st.set_page_config(page_title="Llamadas", page_icon="📞", layout="wide")

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
with st.spinner("Cargando llamadas..."):
    try:
        data = load_all_accounts(st.secrets, days=days)
        df_all = data["calls"]
        account_names = data["account_names"]
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

# ── Filtros sidebar ───────────────────────
with st.sidebar:
    sel_account = st.selectbox("Cuenta", ["Todas"] + account_names)
    sdrs = ["Todos"] + (sorted(df_all["sdr"].dropna().unique().tolist()) if not df_all.empty else [])
    sel_sdr = st.selectbox("SDR", sdrs)
    only_connected = st.checkbox("Solo llamadas conectadas", value=False)

# ── Aplicar filtros ───────────────────────
df = df_all.copy()
if not df.empty:
    if sel_account != "Todas":
        df = df[df["account"] == sel_account]
    if sel_sdr != "Todos":
        df = df[df["sdr"] == sel_sdr]
    if only_connected:
        df = df[df["conectada"] == True]

# ── Header ────────────────────────────────
st.title("📞 Análisis de Llamadas")
st.divider()

if df.empty:
    st.warning("Sin datos de llamadas para los filtros seleccionados.")
    st.stop()

# ── KPIs ──────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
total = len(df)
connected = int(df["conectada"].sum())
rate = round(connected / total * 100, 1) if total > 0 else 0
avg_dur = round(df[df["conectada"] == True]["duracion_min"].mean(), 1) if connected > 0 else 0
outbound = int((df["direccion"].str.upper() == "OUTBOUND").sum()) if "direccion" in df.columns else 0

col1.metric("Total llamadas", f"{total:,}")
col2.metric("Conectadas", f"{connected:,}")
col3.metric("Tasa de conexión", f"{rate}%")
col4.metric("Duración prom. conectada", f"{avg_dur} min")
col5.metric("Llamadas salientes", f"{outbound:,}")

st.divider()

# ── Llamadas por SDR ──────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Llamadas totales vs conectadas por SDR")
    sdr_stats = df.groupby("sdr").agg(
        Total=("id", "count"),
        Conectadas=("conectada", "sum")
    ).reset_index().sort_values("Total", ascending=False)
    sdr_stats["Tasa %"] = (sdr_stats["Conectadas"] / sdr_stats["Total"] * 100).round(1)

    fig1 = go.Figure()
    fig1.add_bar(x=sdr_stats["sdr"], y=sdr_stats["Total"], name="Total", marker_color="#a8dadc")
    fig1.add_bar(x=sdr_stats["sdr"], y=sdr_stats["Conectadas"], name="Conectadas", marker_color="#457b9d")
    fig1.update_layout(barmode="group", height=340, xaxis_title="SDR", yaxis_title="Llamadas")
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("Tasa de conexión por SDR")
    fig2 = px.bar(sdr_stats, x="sdr", y="Tasa %",
                  color="Tasa %", color_continuous_scale="RdYlGn",
                  range_color=[0, 50], height=340, text="Tasa %")
    fig2.update_traces(texttemplate="%{text}%", textposition="outside")
    fig2.update_layout(coloraxis_showscale=False, xaxis_title="SDR")
    st.plotly_chart(fig2, use_container_width=True)

# ── Duración promedio por SDR ─────────────
st.subheader("Duración promedio de llamadas conectadas por SDR (minutos)")
if connected > 0:
    dur_sdr = df[df["conectada"] == True].groupby("sdr")["duracion_min"].mean().round(1).reset_index()
    dur_sdr.columns = ["SDR", "Duración promedio (min)"]
    dur_sdr = dur_sdr.sort_values("Duración promedio (min)", ascending=False)
    fig3 = px.bar(dur_sdr, x="SDR", y="Duración promedio (min)",
                  color="Duración promedio (min)", color_continuous_scale="Blues",
                  text="Duración promedio (min)", height=320)
    fig3.update_traces(texttemplate="%{text} min", textposition="outside")
    fig3.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No hay llamadas conectadas para mostrar duración.")

# ── Heatmap día × hora ────────────────────
st.subheader("Mejor horario para llamar (más conexiones)")
if "hora" in df.columns and "dia" in df.columns:
    connected_df = df[df["conectada"] == True].copy()
    if not connected_df.empty and "hora" in connected_df.columns:
        connected_df["dia_semana"] = pd.to_datetime(connected_df["dia"]).dt.day_name()
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        day_esp = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
                   "Thursday": "Jueves", "Friday": "Viernes"}
        connected_df["dia_esp"] = connected_df["dia_semana"].map(day_esp)
        heat = connected_df.groupby(["dia_esp", "hora"]).size().reset_index(name="conexiones")
        heat_pivot = heat.pivot_table(index="dia_esp", columns="hora", values="conexiones", fill_value=0)
        dias_ord = [day_esp[d] for d in day_order if day_esp[d] in heat_pivot.index]
        heat_pivot = heat_pivot.reindex(dias_ord)

        fig4 = px.imshow(
            heat_pivot,
            labels=dict(x="Hora del día", y="Día", color="Conexiones"),
            color_continuous_scale="YlOrRd",
            aspect="auto",
            height=280,
        )
        fig4.update_xaxes(tickmode="linear", tick0=8, dtick=1)
        st.plotly_chart(fig4, use_container_width=True)
        st.caption("Las celdas más oscuras representan los bloques horarios con más llamadas conectadas.")
    else:
        st.info("No hay suficientes llamadas conectadas para mostrar el heatmap.")

# ── Transcripciones / Notas ───────────────
st.subheader("📝 Notas de llamadas conectadas")
st.caption("Las llamadas conectadas con mayor duración suelen ser las mejores para analizar.")

connected_with_notes = df[(df["conectada"] == True) & (df["notas"].str.strip().ne(""))].copy()
connected_with_notes = connected_with_notes.sort_values("duracion_min", ascending=False)

if not connected_with_notes.empty:
    # Selector de llamada
    for _, row in connected_with_notes.head(20).iterrows():
        with st.expander(
            f"**{row.get('sdr', '?')}** · {str(row.get('dia', ''))[:10]} · {row.get('duracion_min', 0)} min · {row.get('titulo', 'Sin título')}"
        ):
            col_meta, col_rec = st.columns([3, 1])
            with col_meta:
                st.markdown(f"**Cuenta:** {row.get('account', '')}  |  **Estado:** {row.get('estado', '')}  |  **Dirección:** {row.get('direccion', '')}")
                st.markdown("**Notas / Transcripción:**")
                st.markdown(f"> {row.get('notas', '')}")
            with col_rec:
                if row.get("grabacion"):
                    st.markdown(f"[🎙️ Ver grabación]({row['grabacion']})")
else:
    st.info("No hay notas o transcripciones en las llamadas conectadas para el período seleccionado.")
    st.caption("HubSpot puede generar transcripciones automáticas si tienes el plan Sales Hub con Calling habilitado.")

# ── Tabla detalle ─────────────────────────
st.subheader("Tabla de llamadas")
show_cols = [c for c in ["dia", "sdr", "account", "estado", "duracion_min", "direccion", "titulo"] if c in df.columns]
display = df[show_cols].copy()
if "dia" in display.columns:
    display = display.sort_values("dia", ascending=False)
st.dataframe(display.head(500), use_container_width=True, hide_index=True)
