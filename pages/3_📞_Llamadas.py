"""
Página: Análisis de Llamadas
Métricas de llamadas realizadas, conectadas, duración promedio
y transcripciones de las mejores llamadas.
"""

import calendar
import unicodedata
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

from utils.hubspot import load_all_accounts
from utils.sheets import get_maestra_activos
from utils.auth import require_login


def _norm(s: str) -> str:
    """Minúsculas + sin tildes para comparación robusta de nombres SDR."""
    s = (s or "").strip().lower()
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()

st.set_page_config(page_title="Llamadas", page_icon="📞", layout="wide")
require_login()

today = date.today()

_PRESET_OPTS = [
    "Este mes", "Mes pasado", "Últimos 3 meses", "Últimos 6 meses",
    "Este año", "Año pasado", "Últimos 12 meses", "Personalizado",
]
_PRESET_DAYS = {
    "Este mes": 60, "Mes pasado": 60, "Últimos 3 meses": 90,
    "Últimos 6 meses": 180, "Este año": 365, "Año pasado": 730,
    "Últimos 12 meses": 365, "Personalizado": 730,
}

def _period_dates(preset: str):
    t = today
    if preset == "Este mes":
        last_day = calendar.monthrange(t.year, t.month)[1]
        return date(t.year, t.month, 1), date(t.year, t.month, last_day)
    elif preset == "Mes pasado":
        first = date(t.year, t.month, 1)
        last  = first - timedelta(days=1)
        return date(last.year, last.month, 1), last
    elif preset == "Últimos 3 meses":
        return t - timedelta(days=90), t
    elif preset == "Últimos 6 meses":
        return t - timedelta(days=180), t
    elif preset == "Este año":
        return date(t.year, 1, 1), t
    elif preset == "Año pasado":
        return date(t.year - 1, 1, 1), date(t.year - 1, 12, 31)
    elif preset == "Últimos 12 meses":
        return t - timedelta(days=365), t
    else:
        return t - timedelta(days=180), t

# ── Sidebar ──────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Bullseye Dashboard")
    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("### 🔍 Filtros")
    preset = st.selectbox("Período", _PRESET_OPTS, index=3)  # default: Últimos 6 meses
    days = _PRESET_DAYS.get(preset, 180)

    if preset == "Personalizado":
        dr = st.date_input("Rango de fechas", value=(today - timedelta(days=180), today))
        start_date, end_date = (dr[0], dr[1]) if len(dr) == 2 else (today - timedelta(days=180), today)
    else:
        start_date, end_date = _period_dates(preset)

# ── Carga de datos ────────────────────────
with st.spinner("Cargando llamadas..."):
    try:
        data          = load_all_accounts(st.secrets, days=days)
        df_all        = data["calls"]
        account_names = data["account_names"]
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

# ── SDRs activos desde Maestra IA ─────────
maestra = get_maestra_activos(st.secrets)
active_sdrs = maestra.get("sdrs", [])

# ── Filtrar por fecha ─────────────────────
if not df_all.empty and "fecha" in df_all.columns:
    _fecha = df_all["fecha"].dt.tz_localize(None).dt.date if df_all["fecha"].dt.tz is not None \
             else df_all["fecha"].dt.date
    df_all = df_all[(_fecha >= start_date) & (_fecha <= end_date)]

# ── Filtrar solo SDRs activos (desde Maestra IA) ──────────────────────────
# Mantiene: (a) activos con nombre resuelto, (b) sin asignar (sdr="")
# Excluye: SDRs con nombre que NO está en la lista de activos (p.ej. inactivos)
if not df_all.empty and active_sdrs:
    active_set  = {_norm(s) for s in active_sdrs}
    norm_sdr    = df_all["sdr"].apply(_norm)
    mask_active = norm_sdr.isin(active_set) | (df_all["sdr"].str.strip() == "")
    df_all      = df_all[mask_active]
    # Estandarizar nombres según Maestra (corrige tildes/capitalización)
    norm_to_official = {_norm(s): s for s in active_sdrs}
    df_all["sdr"] = df_all["sdr"].apply(
        lambda x: norm_to_official.get(_norm(x), x)
    )

# ── Filtros sidebar ───────────────────────
with st.sidebar:
    st.divider()
    sel_account = st.selectbox("Cuenta", ["Todas"] + account_names)
    # Solo mostrar SDRs activos en el filtro (ya filtrado en df_all)
    sdrs_disponibles = sorted([s for s in df_all["sdr"].dropna().unique() if str(s).strip()]) \
                       if not df_all.empty else []
    sel_sdr = st.selectbox("SDR", ["Todos"] + sdrs_disponibles)
    only_connected = st.checkbox("Solo llamadas conectadas", value=False)
    periodo_str = f"{start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}"
    st.caption(f"Período: **{periodo_str}**")

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
    with st.expander("🔍 Diagnóstico"):
        total_raw = len(data["calls"]) if "calls" in data else 0
        st.write(f"**Total llamadas en HubSpot (últimos {days} días):** {total_raw:,}")
        if not df_all.empty:
            st.write(f"**Después de filtro de fecha ({start_date} → {end_date}):** {len(df_all):,}")
            sdr_counts = df_all["sdr"].value_counts(dropna=False).head(20)
            st.write("**SDRs encontrados en ese período:**", sdr_counts.to_dict())
        else:
            st.write(f"**Sin llamadas en el período {start_date} → {end_date}**")
        st.write(f"**SDRs activos en Maestra IA ({len(active_sdrs)}):**", active_sdrs)
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

# Para los charts: reemplazar sdr="" con "Sin asignar" para que siempre
# haya algo visible aunque el enriquecimiento no haya resuelto el nombre.
df_named = df.copy() if not df.empty else df
if not df_named.empty:
    df_named["sdr"] = df_named["sdr"].apply(
        lambda x: x.strip() if str(x).strip() else "Sin asignar"
    )

with col_a:
    st.subheader("Llamadas totales vs conectadas por SDR")
    sdr_stats = df_named.groupby("sdr").agg(
        Total=("id", "count"),
        Conectadas=("conectada", "sum")
    ).reset_index().sort_values("Total", ascending=False)
    sdr_stats["Tasa %"] = (sdr_stats["Conectadas"] / sdr_stats["Total"] * 100).round(1)

    sdr_stats["sdr"] = sdr_stats["sdr"].astype(str)
    fig1 = go.Figure()
    fig1.add_bar(x=sdr_stats["sdr"], y=sdr_stats["Total"], name="Total", marker_color="#a8dadc")
    fig1.add_bar(x=sdr_stats["sdr"], y=sdr_stats["Conectadas"], name="Conectadas", marker_color="#457b9d")
    fig1.update_layout(barmode="group", height=340, xaxis_title="SDR", yaxis_title="Llamadas",
                       xaxis=dict(type="category"))
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    st.subheader("Tasa de conexión por SDR")
    fig2 = px.bar(sdr_stats, x="sdr", y="Tasa %",
                  color="Tasa %", color_continuous_scale="RdYlGn",
                  range_color=[0, 50], height=340, text="Tasa %",
                  category_orders={"sdr": sdr_stats["sdr"].tolist()})
    fig2.update_traces(texttemplate="%{text}%", textposition="outside")
    fig2.update_layout(coloraxis_showscale=False, xaxis_title="SDR",
                       xaxis=dict(type="category"))
    st.plotly_chart(fig2, use_container_width=True)

# ── Duración promedio por SDR ─────────────
st.subheader("Duración promedio de llamadas conectadas por SDR (minutos)")
if connected > 0:
    dur_sdr = df_named[df_named["conectada"] == True].groupby("sdr")["duracion_min"].mean().round(1).reset_index()
    dur_sdr.columns = ["SDR", "Duración promedio (min)"]
    dur_sdr = dur_sdr.sort_values("Duración promedio (min)", ascending=False)
    dur_sdr["SDR"] = dur_sdr["SDR"].astype(str)
    fig3 = px.bar(dur_sdr, x="SDR", y="Duración promedio (min)",
                  color="Duración promedio (min)", color_continuous_scale="Blues",
                  text="Duración promedio (min)", height=320)
    fig3.update_traces(texttemplate="%{text} min", textposition="outside")
    fig3.update_layout(coloraxis_showscale=False, xaxis=dict(type="category"))
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
