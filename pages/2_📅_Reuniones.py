"""
Página: Reuniones SDR — Dashboard completo
Sheet: "Metas equipo BullsEye / reuniones / oportunidades"
Pestaña: "Gestión Reuniones"
"""

import json
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.sheets import get_meetings_from_sheets

st.set_page_config(page_title="Reuniones SDR", page_icon="📅", layout="wide")

# ── Rutas ──────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
GOALS_FILE = os.path.join(PROJECT_ROOT, "data", "goals.json")
os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)


def load_goals() -> dict:
    if os.path.exists(GOALS_FILE):
        with open(GOALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sdr": {}, "cliente": {}}


def save_goals(g: dict) -> None:
    with open(GOALS_FILE, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)


# ── Carga de datos ─────────────────────────────────────────────────────────────
with st.spinner("Cargando reuniones desde Google Sheets..."):
    try:
        df_raw = get_meetings_from_sheets(st.secrets)
    except Exception as e:
        st.error(f"Error cargando Google Sheets: {e}")
        st.stop()

if df_raw.empty:
    st.warning("No se encontraron reuniones en el Google Sheet.")
    st.info("Verifica que el sheet_id, la pestaña y el api_key sean correctos en secrets.toml.")
    st.stop()

today = date.today()

# ── Estado de cada reunión ─────────────────────────────────────────────────────
def calcular_estado(row) -> str:
    if row.get("reunión_realizada", False):
        return "Realizada"
    fecha_r = row.get("fecha_reunion")
    if pd.notna(fecha_r) and hasattr(fecha_r, "date") and fecha_r.date() >= today:
        return "Pendiente"
    return "No realizada"

df_raw["estado"] = df_raw.apply(calcular_estado, axis=1)

# Columna de mes basada en fecha_agendamiento
if "fecha_agendamiento" in df_raw.columns and df_raw["fecha_agendamiento"].notna().any():
    df_raw["mes_agenda"] = df_raw["fecha_agendamiento"].dt.to_period("M").astype(str)
else:
    df_raw["mes_agenda"] = df_raw.get("mes", pd.Series(dtype=str))


# ── Presets de período ─────────────────────────────────────────────────────────
def get_period_dates(preset: str):
    t = today
    if preset == "Este mes":
        return date(t.year, t.month, 1), t
    elif preset == "Mes pasado":
        first = date(t.year, t.month, 1)
        last = first - timedelta(days=1)
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
    else:  # Todo
        col = df_raw["fecha_agendamiento"] if "fecha_agendamiento" in df_raw.columns else df_raw.get("fecha")
        min_d = col.dropna().min()
        return (min_d.date() if pd.notna(min_d) else date(2023, 1, 1)), t


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Bullseye Dashboard")
    st.divider()

    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("### 🔍 Filtros")

    fecha_filtro = st.radio(
        "Filtrar por fecha",
        ["Fecha de agendamiento", "Fecha de reunión"],
        horizontal=True,
    )
    fecha_col = "fecha_agendamiento" if "agendamiento" in fecha_filtro else "fecha_reunion"

    preset_opts = [
        "Este mes", "Mes pasado", "Últimos 3 meses", "Últimos 6 meses",
        "Este año", "Año pasado", "Últimos 12 meses", "Todo", "Personalizado",
    ]
    preset = st.selectbox("Período", preset_opts, index=0)

    if preset == "Personalizado":
        ref_col = df_raw[fecha_col] if fecha_col in df_raw.columns else df_raw.get("fecha")
        min_avail = ref_col.dropna().min()
        min_avail = min_avail.date() if pd.notna(min_avail) else date(2023, 1, 1)
        dr = st.date_input("Rango de fechas", value=(min_avail, today),
                           min_value=min_avail, max_value=today)
        start_date, end_date = (dr[0], dr[1]) if len(dr) == 2 else (min_avail, today)
    else:
        start_date, end_date = get_period_dates(preset)

    st.caption(f"📅 {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}")
    st.divider()

    sdrs_list = ["Todos"] + sorted(
        df_raw["sdr"].replace({"Sin asignar": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
    )
    sel_sdr = st.selectbox("SDR / Responsable", sdrs_list)

    if "cliente" in df_raw.columns:
        clients_list = ["Todos"] + sorted(
            df_raw["cliente"].replace({"": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
        )
        sel_client = st.selectbox("Cliente", clients_list)
    else:
        sel_client = "Todos"

    if "pais" in df_raw.columns:
        paises_list = ["Todos"] + sorted(
            df_raw["pais"].replace({"": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
        )
        sel_pais = st.selectbox("País", paises_list)
    else:
        sel_pais = "Todos"

    sel_estado = st.multiselect(
        "Estado",
        ["Realizada", "Pendiente", "No realizada"],
        default=["Realizada", "Pendiente", "No realizada"],
    )


# ── Aplicar filtros ────────────────────────────────────────────────────────────
df = df_raw.copy()

if fecha_col in df.columns:
    df = df[df[fecha_col].notna()]
    df = df[(df[fecha_col].dt.date >= start_date) & (df[fecha_col].dt.date <= end_date)]
elif "fecha" in df.columns:
    df = df[df["fecha"].notna()]
    df = df[(df["fecha"].dt.date >= start_date) & (df["fecha"].dt.date <= end_date)]

if sel_sdr != "Todos" and "sdr" in df.columns:
    df = df[df["sdr"] == sel_sdr]
if sel_client != "Todos" and "cliente" in df.columns:
    df = df[df["cliente"] == sel_client]
if sel_pais != "Todos" and "pais" in df.columns:
    df = df[df["pais"] == sel_pais]
if sel_estado:
    df = df[df["estado"].isin(sel_estado)]


# ── Helpers ────────────────────────────────────────────────────────────────────
def resumen(g: pd.DataFrame) -> pd.Series:
    total = len(g)
    realizadas = (g["estado"] == "Realizada").sum()
    pendientes = (g["estado"] == "Pendiente").sum()
    no_real = (g["estado"] == "No realizada").sum()
    propuestas = 0
    if "propuesta" in g.columns:
        propuestas = g["propuesta"].replace({"": pd.NA, "nan": pd.NA}).notna().sum()
    return pd.Series({
        "Agendadas": total,
        "Realizadas": int(realizadas),
        "Pendientes": int(pendientes),
        "No realizadas": int(no_real),
        "Con propuesta": int(propuestas),
    })


def add_tasa(df_t: pd.DataFrame) -> pd.DataFrame:
    df_t = df_t.copy()
    df_t["Tasa realización"] = df_t.apply(
        lambda r: f"{round(r['Realizadas'] / r['Agendadas'] * 100, 1)}%"
        if r["Agendadas"] > 0 else "—",
        axis=1,
    )
    return df_t


def add_cumplimiento(df_t: pd.DataFrame, key_col: str, goals_dict: dict, months: int) -> pd.DataFrame:
    df_t = df_t.copy()
    df_t["Meta mensual"] = df_t[key_col].map(goals_dict).fillna(0).astype(int)
    df_t["Meta período"] = df_t["Meta mensual"] * months
    df_t["% Cumplimiento"] = df_t.apply(
        lambda r: f"{round(r['Agendadas'] / r['Meta período'] * 100, 1)}%"
        if r["Meta período"] > 0 else "—",
        axis=1,
    )
    return df_t


goals = load_goals()
months_count = max(1, round((end_date - start_date).days / 30))

# ── KPIs ───────────────────────────────────────────────────────────────────────
total = len(df)
realizadas_total = (df["estado"] == "Realizada").sum()
pendientes_total = (df["estado"] == "Pendiente").sum()
no_real_total = (df["estado"] == "No realizada").sum()
tasa_total = round(realizadas_total / total * 100, 1) if total > 0 else 0
prop_total = 0
if "propuesta" in df.columns:
    prop_total = df["propuesta"].replace({"": pd.NA, "nan": pd.NA}).notna().sum()

st.title("📅 Gestión de Reuniones SDR")
periodo_str = f"{start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}"
st.caption(f"Período: **{periodo_str}** · {total:,} reuniones con los filtros actuales")
st.divider()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("📋 Agendadas", f"{total:,}")
c2.metric("✅ Realizadas", f"{realizadas_total:,}")
c3.metric("⏳ Pendientes", f"{pendientes_total:,}")
c4.metric("❌ No realizadas", f"{no_real_total:,}")
c5.metric("📈 Tasa realización", f"{tasa_total}%")
c6.metric("📄 Con propuesta", f"{prop_total:,}")
st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_periodo, tab_sdr, tab_cliente, tab_analisis, tab_metas, tab_detalle = st.tabs([
    "📆 Por Período", "👤 Por SDR", "🏢 Por Cliente",
    "🔍 Análisis", "🎯 Metas", "📋 Detalle",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Por Período
# ═══════════════════════════════════════════════════════════════════════════════
with tab_periodo:
    st.subheader("Evolución mensual de reuniones")

    mes_col = "mes_agenda" if "mes_agenda" in df.columns and df["mes_agenda"].ne("").any() else "mes"

    if mes_col in df.columns and df[mes_col].ne("").any():
        monthly = (
            df.groupby(mes_col)
            .apply(resumen)
            .reset_index()
            .rename(columns={mes_col: "Mes"})
            .sort_values("Mes")
        )
        monthly = add_tasa(monthly)

        # Gráfico
        fig = go.Figure()
        fig.add_bar(x=monthly["Mes"], y=monthly["Agendadas"],   name="Agendadas",    marker_color="#a8dadc")
        fig.add_bar(x=monthly["Mes"], y=monthly["Realizadas"],  name="Realizadas",   marker_color="#457b9d")
        fig.add_bar(x=monthly["Mes"], y=monthly["Pendientes"],  name="Pendientes",   marker_color="#f4a261")
        fig.add_bar(x=monthly["Mes"], y=monthly["No realizadas"], name="No realizadas", marker_color="#e63946")
        fig.update_layout(
            barmode="group", height=380,
            xaxis_title="Mes", yaxis_title="Reuniones",
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tabla
        st.dataframe(
            monthly,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Mes":            st.column_config.TextColumn("Mes"),
                "Agendadas":      st.column_config.NumberColumn("Agendadas", format="%d"),
                "Realizadas":     st.column_config.NumberColumn("Realizadas", format="%d"),
                "Pendientes":     st.column_config.NumberColumn("Pendientes", format="%d"),
                "No realizadas":  st.column_config.NumberColumn("No realizadas", format="%d"),
                "Con propuesta":  st.column_config.NumberColumn("Con propuesta", format="%d"),
                "Tasa realización": st.column_config.TextColumn("Tasa realización"),
            },
        )
    else:
        st.info("No hay datos de período suficientes para generar este análisis.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Por SDR
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sdr:
    st.subheader("Reuniones por SDR / Responsable")

    if "sdr" not in df.columns:
        st.warning("No se encontró la columna de SDR/Responsable.")
    else:
        sdr_df = (
            df.groupby("sdr")
            .apply(resumen)
            .reset_index()
            .rename(columns={"sdr": "SDR"})
        )
        sdr_df = add_tasa(sdr_df)
        sdr_df = add_cumplimiento(sdr_df, "SDR", goals.get("sdr", {}), months_count)
        sdr_df = sdr_df.sort_values("Agendadas", ascending=False)

        # Gráfico
        fig = go.Figure()
        fig.add_bar(y=sdr_df["SDR"], x=sdr_df["Agendadas"],  name="Agendadas",  orientation="h", marker_color="#a8dadc")
        fig.add_bar(y=sdr_df["SDR"], x=sdr_df["Realizadas"], name="Realizadas", orientation="h", marker_color="#457b9d")
        if sdr_df["Meta período"].sum() > 0:
            fig.add_scatter(
                y=sdr_df["SDR"], x=sdr_df["Meta período"], name="Meta",
                mode="markers",
                marker=dict(symbol="line-ns-open", size=18, color="red", line=dict(width=3, color="red")),
            )
        fig.update_layout(
            barmode="group",
            height=max(300, len(sdr_df) * 55),
            xaxis_title="Reuniones", yaxis_title="",
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig, use_container_width=True)

        display_cols = ["SDR", "Agendadas", "Realizadas", "Pendientes", "No realizadas", "Con propuesta", "Tasa realización"]
        if sdr_df["Meta período"].sum() > 0:
            display_cols += ["Meta período", "% Cumplimiento"]

        st.dataframe(sdr_df[display_cols], use_container_width=True, hide_index=True)

        # Desglose mensual
        with st.expander("📆 Ver desglose mensual por SDR"):
            mes_col2 = "mes_agenda" if "mes_agenda" in df.columns else "mes"
            if mes_col2 in df.columns:
                sdr_monthly = (
                    df.groupby([mes_col2, "sdr"])
                    .apply(lambda g: pd.Series({"Agendadas": len(g), "Realizadas": (g["estado"] == "Realizada").sum()}))
                    .reset_index()
                    .rename(columns={mes_col2: "Mes", "sdr": "SDR"})
                    .sort_values(["Mes", "Agendadas"], ascending=[True, False])
                )
                sdr_monthly["Tasa"] = sdr_monthly.apply(
                    lambda r: f"{round(r['Realizadas']/r['Agendadas']*100,1)}%" if r['Agendadas'] > 0 else "—",
                    axis=1,
                )
                st.dataframe(sdr_monthly, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Por Cliente
# ═══════════════════════════════════════════════════════════════════════════════
with tab_cliente:
    st.subheader("Reuniones por Cliente")

    if "cliente" not in df.columns:
        st.warning("No se encontró la columna de Cliente.")
    else:
        df_cli = df[df["cliente"].replace({"": pd.NA, "nan": pd.NA}).notna()].copy()

        def resumen_cli(g):
            s = resumen(g)
            s["SDRs"] = int(g["sdr"].nunique()) if "sdr" in g.columns else 0
            return s

        cli_df = (
            df_cli.groupby("cliente")
            .apply(resumen_cli)
            .reset_index()
            .rename(columns={"cliente": "Cliente"})
        )
        cli_df = add_tasa(cli_df)
        cli_df = add_cumplimiento(cli_df, "Cliente", goals.get("cliente", {}), months_count)
        cli_df = cli_df.sort_values("Agendadas", ascending=False)

        # Gráfico
        fig = go.Figure()
        fig.add_bar(y=cli_df["Cliente"], x=cli_df["Agendadas"],  name="Agendadas",  orientation="h", marker_color="#a8dadc")
        fig.add_bar(y=cli_df["Cliente"], x=cli_df["Realizadas"], name="Realizadas", orientation="h", marker_color="#457b9d")
        if cli_df["Meta período"].sum() > 0:
            fig.add_scatter(
                y=cli_df["Cliente"], x=cli_df["Meta período"], name="Meta",
                mode="markers",
                marker=dict(symbol="line-ns-open", size=18, color="red", line=dict(width=3, color="red")),
            )
        fig.update_layout(
            barmode="group",
            height=max(300, len(cli_df) * 55),
            xaxis_title="Reuniones", yaxis_title="",
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig, use_container_width=True)

        display_cols = ["Cliente", "Agendadas", "Realizadas", "Pendientes", "No realizadas", "Con propuesta", "SDRs", "Tasa realización"]
        if cli_df["Meta período"].sum() > 0:
            display_cols += ["Meta período", "% Cumplimiento"]

        available = [c for c in display_cols if c in cli_df.columns]
        st.dataframe(cli_df[available], use_container_width=True, hide_index=True)

        # Desglose mensual
        with st.expander("📆 Ver desglose mensual por cliente"):
            mes_col3 = "mes_agenda" if "mes_agenda" in df_cli.columns else "mes"
            if mes_col3 in df_cli.columns:
                cli_monthly = (
                    df_cli.groupby([mes_col3, "cliente"])
                    .apply(lambda g: pd.Series({"Agendadas": len(g), "Realizadas": (g["estado"] == "Realizada").sum()}))
                    .reset_index()
                    .rename(columns={mes_col3: "Mes", "cliente": "Cliente"})
                    .sort_values(["Mes", "Agendadas"], ascending=[True, False])
                )
                cli_monthly["Tasa"] = cli_monthly.apply(
                    lambda r: f"{round(r['Realizadas']/r['Agendadas']*100,1)}%" if r['Agendadas'] > 0 else "—",
                    axis=1,
                )
                st.dataframe(cli_monthly, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Análisis
# ═══════════════════════════════════════════════════════════════════════════════
with tab_analisis:
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_esp = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
    }

    col_l, col_r = st.columns(2)

    # ── Días de la semana ──
    with col_l:
        st.subheader("📅 Días con más reuniones agendadas")
        if "dia_semana" in df.columns:
            by_day = df.groupby("dia_semana").size().reset_index(name="Reuniones")
            by_day["Día"] = by_day["dia_semana"].map(day_esp)
            by_day["orden"] = by_day["dia_semana"].map({d: i for i, d in enumerate(day_order)})
            by_day = by_day.sort_values("orden")
            fig = px.bar(by_day, x="Día", y="Reuniones",
                         color="Reuniones", color_continuous_scale="Blues", height=320)
            fig.update_layout(coloraxis_showscale=False, xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                by_day[["Día", "Reuniones"]].sort_values("Reuniones", ascending=False),
                use_container_width=True, hide_index=True,
            )

    # ── Origen de reuniones ──
    with col_r:
        st.subheader("🔗 Origen de reuniones")
        origen_col = next((c for c in ["origen", "fuente", "fuente_campana"] if c in df.columns), None)
        if origen_col:
            orig_df = (
                df[df[origen_col].replace({"": pd.NA, "nan": pd.NA}).notna()]
                .groupby(origen_col).size().reset_index(name="Reuniones")
                .sort_values("Reuniones", ascending=False)
            )
            fig = px.pie(orig_df, values="Reuniones", names=origen_col,
                         height=320, hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(orig_df.rename(columns={origen_col: "Origen"}),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No se encontró columna de Origen o Fuente campaña.")

    # ── Heatmap Día × Hora ──
    st.subheader("🗓️ Heatmap: Día × Hora de agendamiento")
    if "hora_num" in df.columns and df["hora_num"].notna().any() and "dia_semana" in df.columns:
        df_heat = df.copy()
        df_heat["Día"] = df_heat["dia_semana"].map(day_esp)
        heat = df_heat.groupby(["Día", "hora_num"]).size().reset_index(name="Reuniones")
        heat_pivot = heat.pivot_table(index="Día", columns="hora_num", values="Reuniones", fill_value=0)
        dias_ord = [day_esp[d] for d in day_order if day_esp.get(d) in heat_pivot.index]
        heat_pivot = heat_pivot.reindex(dias_ord)
        fig = px.imshow(heat_pivot, labels=dict(x="Hora", y="Día", color="Reuniones"),
                        color_continuous_scale="YlOrRd", aspect="auto", height=280)
        fig.update_xaxes(tickmode="linear", tick0=8, dtick=1)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Celdas más oscuras = mayor concentración de reuniones agendadas en ese bloque.")
    else:
        st.info("No hay datos de hora para generar el heatmap.")

    col_l2, col_r2 = st.columns(2)

    # ── País ──
    with col_l2:
        st.subheader("🌎 Reuniones por País")
        if "pais" in df.columns:
            pais_df = (
                df[df["pais"].replace({"": pd.NA, "nan": pd.NA}).notna()]
                .groupby("pais")
                .apply(lambda g: pd.Series({
                    "Agendadas": len(g),
                    "Realizadas": (g["estado"] == "Realizada").sum(),
                    "Pendientes": (g["estado"] == "Pendiente").sum(),
                }))
                .reset_index()
                .rename(columns={"pais": "País"})
                .sort_values("Agendadas", ascending=False)
            )
            pais_df["Tasa realización"] = pais_df.apply(
                lambda r: f"{round(r['Realizadas']/r['Agendadas']*100,1)}%" if r['Agendadas'] > 0 else "—",
                axis=1,
            )
            # Mapa de burbujas si hay datos suficientes
            fig = px.bar(pais_df, x="Agendadas", y="País", orientation="h",
                         color="Agendadas", color_continuous_scale="Blues", height=350)
            fig.update_layout(coloraxis_showscale=False, yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pais_df, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontró columna de País.")

    # ── Propuestas ──
    with col_r2:
        st.subheader("📄 Reuniones con Propuesta enviada")
        if "propuesta" in df.columns:
            df_prop = df[df["propuesta"].replace({"": pd.NA, "nan": pd.NA}).notna()].copy()
            n_prop = len(df_prop)
            pct_prop = round(n_prop / total * 100, 1) if total > 0 else 0
            st.metric("Con propuesta", f"{n_prop:,}", delta=f"{pct_prop}% del total filtrado")

            if "sdr" in df_prop.columns and not df_prop.empty:
                prop_sdr = (
                    df_prop.groupby("sdr").size()
                    .reset_index(name="Propuestas")
                    .sort_values("Propuestas", ascending=False)
                    .rename(columns={"sdr": "SDR"})
                )
                st.dataframe(prop_sdr, use_container_width=True, hide_index=True)

            if "cliente" in df_prop.columns and not df_prop.empty:
                st.markdown("**Por cliente:**")
                prop_cli = (
                    df_prop[df_prop["cliente"].replace({"": pd.NA, "nan": pd.NA}).notna()]
                    .groupby("cliente").size()
                    .reset_index(name="Propuestas")
                    .sort_values("Propuestas", ascending=False)
                    .rename(columns={"cliente": "Cliente"})
                )
                st.dataframe(prop_cli, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontró columna de Propuesta.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Metas
# ═══════════════════════════════════════════════════════════════════════════════
with tab_metas:
    st.subheader("🎯 Configuración de Metas Mensuales")
    st.info(
        "Define cuántas reuniones debe agendar cada SDR y cada cliente por mes. "
        "Las metas se guardan en el servidor y se usan en las pestañas de SDR y Cliente."
    )

    col_sdr_m, col_cli_m = st.columns(2)

    # ── Metas SDR ──
    with col_sdr_m:
        st.markdown("#### 👤 Meta mensual por SDR")
        sdrs_all = sorted(
            df_raw["sdr"].replace({"Sin asignar": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
        )
        sdr_goals_curr = goals.get("sdr", {})
        sdr_meta_df = pd.DataFrame({
            "SDR": sdrs_all,
            "Meta mensual": [int(sdr_goals_curr.get(s, 0)) for s in sdrs_all],
        })
        sdr_edited = st.data_editor(
            sdr_meta_df,
            use_container_width=True,
            hide_index=True,
            disabled=["SDR"],
            column_config={
                "Meta mensual": st.column_config.NumberColumn(
                    "Reuniones / mes", min_value=0, max_value=999, step=1, format="%d"
                )
            },
            key="sdr_meta_editor",
        )
        if st.button("💾 Guardar metas SDR", use_container_width=True, type="primary"):
            goals["sdr"] = dict(zip(sdr_edited["SDR"], sdr_edited["Meta mensual"].astype(int)))
            save_goals(goals)
            st.success("✅ Metas de SDR guardadas correctamente")
            st.rerun()

    # ── Metas Clientes ──
    with col_cli_m:
        st.markdown("#### 🏢 Meta mensual por Cliente")
        clientes_all = []
        if "cliente" in df_raw.columns:
            clientes_all = sorted(
                df_raw["cliente"].replace({"": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
            )
        cli_goals_curr = goals.get("cliente", {})
        cli_meta_df = pd.DataFrame({
            "Cliente": clientes_all,
            "Meta mensual": [int(cli_goals_curr.get(c, 0)) for c in clientes_all],
        })
        cli_edited = st.data_editor(
            cli_meta_df,
            use_container_width=True,
            hide_index=True,
            disabled=["Cliente"],
            column_config={
                "Meta mensual": st.column_config.NumberColumn(
                    "Reuniones / mes", min_value=0, max_value=999, step=1, format="%d"
                )
            },
            key="cli_meta_editor",
        )
        if st.button("💾 Guardar metas Clientes", use_container_width=True, type="primary"):
            goals["cliente"] = dict(zip(cli_edited["Cliente"], cli_edited["Meta mensual"].astype(int)))
            save_goals(goals)
            st.success("✅ Metas de clientes guardadas correctamente")
            st.rerun()

    # ── Cumplimiento mes actual ──
    st.divider()
    st.markdown("#### 📊 Cumplimiento — Mes actual")

    this_month_start = date(today.year, today.month, 1)
    df_mes = df_raw.copy()
    fecha_col_mes = "fecha_agendamiento" if "fecha_agendamiento" in df_mes.columns else "fecha"
    if fecha_col_mes in df_mes.columns:
        df_mes = df_mes[df_mes[fecha_col_mes].notna()]
        df_mes = df_mes[
            (df_mes[fecha_col_mes].dt.date >= this_month_start)
            & (df_mes[fecha_col_mes].dt.date <= today)
        ]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"**Por SDR — {today.strftime('%B %Y')}**")
        if "sdr" in df_mes.columns and goals.get("sdr"):
            sdr_m = (
                df_mes.groupby("sdr").size()
                .reset_index(name="Agendadas")
                .rename(columns={"sdr": "SDR"})
            )
            sdr_m["Meta"] = sdr_m["SDR"].map(goals["sdr"]).fillna(0).astype(int)
            sdr_m["Faltan"] = (sdr_m["Meta"] - sdr_m["Agendadas"]).clip(lower=0)
            sdr_m["% Cumplimiento"] = sdr_m.apply(
                lambda r: f"{round(r['Agendadas']/r['Meta']*100,1)}%" if r["Meta"] > 0 else "—",
                axis=1,
            )
            sdr_m = sdr_m.sort_values("Agendadas", ascending=False)
            st.dataframe(sdr_m, use_container_width=True, hide_index=True)
        elif not goals.get("sdr"):
            st.info("Configura metas de SDR arriba para ver el cumplimiento.")

    with col_b:
        st.markdown(f"**Por Cliente — {today.strftime('%B %Y')}**")
        if "cliente" in df_mes.columns and goals.get("cliente"):
            df_mes_cli = df_mes[df_mes["cliente"].replace({"": pd.NA, "nan": pd.NA}).notna()]
            cli_m = (
                df_mes_cli.groupby("cliente").size()
                .reset_index(name="Agendadas")
                .rename(columns={"cliente": "Cliente"})
            )
            cli_m["Meta"] = cli_m["Cliente"].map(goals["cliente"]).fillna(0).astype(int)
            cli_m["Faltan"] = (cli_m["Meta"] - cli_m["Agendadas"]).clip(lower=0)
            cli_m["% Cumplimiento"] = cli_m.apply(
                lambda r: f"{round(r['Agendadas']/r['Meta']*100,1)}%" if r["Meta"] > 0 else "—",
                axis=1,
            )
            cli_m = cli_m.sort_values("Agendadas", ascending=False)
            st.dataframe(cli_m, use_container_width=True, hide_index=True)
        elif not goals.get("cliente"):
            st.info("Configura metas de clientes arriba para ver el cumplimiento.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Detalle
# ═══════════════════════════════════════════════════════════════════════════════
with tab_detalle:
    st.subheader("📋 Tabla completa de reuniones")
    st.caption(f"{len(df):,} registros · Haz clic en el encabezado de cada columna para ordenar ↑↓")

    col_labels = {
        "fecha_agendamiento": "Fecha agendamiento",
        "fecha_reunion":      "Fecha reunión",
        "estado":             "Estado",
        "sdr":                "SDR",
        "ejecutivo":          "Ejecutivo",
        "kam":                "KAM",
        "cliente":            "Cliente",
        "empresa":            "Empresa",
        "contacto":           "Contacto",
        "cargo":              "Cargo",
        "pais":               "País",
        "realizado":          "Realizado",
        "asiste":             "Asiste",
        "propuesta":          "Propuesta",
        "piloto":             "Piloto",
        "fuente":             "Fuente campaña",
        "origen":             "Origen",
        "comentarios":        "Comentarios",
    }

    show_cols = [c for c in col_labels if c in df.columns]
    display = df[show_cols].copy()

    for dc in ["fecha_agendamiento", "fecha_reunion"]:
        if dc in display.columns:
            display[dc] = display[dc].dt.strftime("%d/%m/%Y")

    display = display.rename(columns=col_labels)

    if "Fecha agendamiento" in display.columns:
        display = display.sort_values("Fecha agendamiento", ascending=False)

    # Colorear estado
    def color_estado(val):
        colors = {"Realizada": "#d4edda", "Pendiente": "#fff3cd", "No realizada": "#f8d7da"}
        return f"background-color: {colors.get(val, 'white')}"

    st.dataframe(display, use_container_width=True, hide_index=True)
