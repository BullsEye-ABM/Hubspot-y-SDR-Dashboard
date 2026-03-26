"""
Página: Reuniones SDR — Dashboard completo
Sheet: "Metas equipo BullsEye / reuniones / oportunidades"
Pestaña: "Gestión Reuniones"
"""

import calendar
import json
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.sheets import get_meetings_from_sheets, get_maestra_activos

st.set_page_config(page_title="Reuniones SDR", page_icon="📅", layout="wide")

# ── Constantes de metas ────────────────────────────────────────────────────────
_GOALS_YEAR   = 2026
_MONTH_KEYS   = [f"{_GOALS_YEAR}-{m:02d}" for m in range(1, 13)]
_MONTH_LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# ── Rutas ──────────────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
GOALS_FILE   = os.path.join(PROJECT_ROOT, "data", "goals.json")
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

# ── Debug (expandible) ─────────────────────────────────────────────────────────
with st.expander("🔧 Diagnóstico técnico", expanded=False):
    method   = df_raw.attrs.get("_fetch_method", "desconocido")
    v4_err   = df_raw.attrs.get("_v4_error")
    row_raw  = df_raw.attrs.get("_row_count_raw", len(df_raw))
    orig_cols   = df_raw.attrs.get("_debug_cols_original", [])
    mapped_cols = df_raw.attrs.get("_debug_cols_mapped", [])

    st.markdown(f"**Método de lectura:** {method}")
    st.markdown(f"**Filas leídas del sheet:** {row_raw}")
    if v4_err:
        st.warning(f"API v4 falló → {v4_err}")
        st.info(
            "Para ignorar filtros del equipo 100%, habilita la Sheets API v4:\n\n"
            "1. Ve a https://console.cloud.google.com\n"
            "2. Selecciona el proyecto de tu API key\n"
            "3. APIs y servicios → Habilitar APIs\n"
            "4. Busca **Google Sheets API** → Habilitar"
        )
    st.write("**Columnas leídas:**", orig_cols)
    st.write("**Columnas mapeadas:**", mapped_cols)
    criticas = ["fecha_agendamiento", "fecha_reunion", "realizado", "sdr", "cliente"]
    faltantes = [c for c in criticas if c not in df_raw.columns]
    if faltantes:
        st.error(f"Columnas críticas NO encontradas: {faltantes}")
    else:
        st.success("Todas las columnas críticas encontradas ✅")

today = date.today()

# Valores que se consideran "propuesta enviada"
_SI_PROPUESTA = {"si", "sí", "yes", "y", "x", "✓", "true", "1"}

# ── Estado de cada reunión — directo desde columna "Realizado" (col J) ────────
_ESTADO_MAP = {
    "si":        "Realizada",
    "sí":        "Realizada",
    "pendiente": "Pendiente",
    "no":        "No realizada",
    "reagendar": "Reagendar",
}


def calcular_estado(row) -> str:
    val = str(row.get("realizado", "")).strip().lower()
    return _ESTADO_MAP.get(val, "No realizada")


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
        # Mes completo — incluye reuniones futuras (pendientes) del mes actual
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
        last_day_year = date(t.year, 12, 31)
        return date(t.year, 1, 1), last_day_year
    elif preset == "Año pasado":
        return date(t.year - 1, 1, 1), date(t.year - 1, 12, 31)
    elif preset == "Últimos 12 meses":
        return t - timedelta(days=365), t
    else:  # Todo
        col   = df_raw["fecha_reunion"] if "fecha_reunion" in df_raw.columns else df_raw.get("fecha")
        min_d = col.dropna().min()
        max_d = col.dropna().max()
        return (min_d.date() if pd.notna(min_d) else date(2023, 1, 1)), (max_d.date() if pd.notna(max_d) else t)


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
        ["Fecha de reunión", "Fecha de agendamiento"],
        horizontal=True,
        help="'Fecha de reunión' = día en que ocurre la reunión · 'Fecha de agendamiento' = día en que el SDR la agendó",
    )
    fecha_col = "fecha_agendamiento" if "agendamiento" in fecha_filtro else "fecha_reunion"

    preset_opts = [
        "Este mes", "Mes pasado", "Últimos 3 meses", "Últimos 6 meses",
        "Este año", "Año pasado", "Últimos 12 meses", "Todo", "Personalizado",
    ]
    preset = st.selectbox("Período", preset_opts, index=3)  # default: Últimos 6 meses

    if preset == "Personalizado":
        ref_col   = df_raw[fecha_col] if fecha_col in df_raw.columns else df_raw.get("fecha")
        min_avail = ref_col.dropna().min()
        min_avail = min_avail.date() if pd.notna(min_avail) else date(2023, 1, 1)
        max_avail = date(today.year + 1, 12, 31)   # permite seleccionar fechas futuras (reuniones pendientes)
        dr = st.date_input("Rango de fechas", value=(min_avail, today),
                           min_value=min_avail, max_value=max_avail)
        start_date, end_date = (dr[0], dr[1]) if len(dr) == 2 else (min_avail, today)
    else:
        start_date, end_date = get_period_dates(preset)

    st.caption(f"📅 {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}")
    st.divider()

    if "sdr" in df_raw.columns:
        sdrs_list = ["Todos"] + sorted(
            df_raw["sdr"].replace({"Sin asignar": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
        )
    else:
        # Fallback: buscar columna "Responsable" directamente si el mapeo no funcionó
        _col_sdr = next((c for c in df_raw.columns if "responsable" in c.lower() or c.lower() == "sdr"), None)
        if _col_sdr:
            sdrs_list = ["Todos"] + sorted(
                df_raw[_col_sdr].replace({"Sin asignar": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
            )
            df_raw = df_raw.rename(columns={_col_sdr: "sdr"})
        else:
            sdrs_list = ["Todos"]
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
        ["Realizada", "Pendiente", "No realizada", "Reagendar"],
        default=["Realizada", "Pendiente", "No realizada", "Reagendar"],
    )


# ── Aplicar filtros ────────────────────────────────────────────────────────────
df = df_raw.copy()

if fecha_col in df.columns:
    fallback      = df["fecha_agendamiento"] if "fecha_agendamiento" in df.columns else pd.Series(dtype="datetime64[ns]")
    fecha_efectiva = df[fecha_col].fillna(fallback)
else:
    fecha_efectiva = df.get("fecha", pd.Series(dtype="datetime64[ns]"))

df = df[fecha_efectiva.notna()]
df = df[(fecha_efectiva[df.index].dt.date >= start_date) & (fecha_efectiva[df.index].dt.date <= end_date)]

if sel_sdr    != "Todos" and "sdr"     in df.columns: df = df[df["sdr"]     == sel_sdr]
if sel_client != "Todos" and "cliente" in df.columns: df = df[df["cliente"] == sel_client]
if sel_pais   != "Todos" and "pais"    in df.columns: df = df[df["pais"]    == sel_pais]
if sel_estado:                                         df = df[df["estado"].isin(sel_estado)]


# ── Helpers base ───────────────────────────────────────────────────────────────
def _agg_by(source_df: pd.DataFrame, group_col: str, extra_fn=None) -> pd.DataFrame:
    rows = []
    for key, group in source_df.groupby(group_col):
        row = resumen(group).to_dict()
        row[group_col] = key
        if extra_fn:
            row.update(extra_fn(group))
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    cols = [group_col] + [c for c in result.columns if c != group_col]
    return result[cols]


def resumen(g: pd.DataFrame) -> pd.Series:
    total     = len(g)
    realizadas = (g["estado"] == "Realizada").sum()
    pendientes = (g["estado"] == "Pendiente").sum()
    no_real    = (g["estado"] == "No realizada").sum()
    propuestas = 0
    if "propuesta" in g.columns:
        propuestas = g["propuesta"].astype(str).str.strip().str.lower().isin(_SI_PROPUESTA).sum()
    return pd.Series({
        "Agendadas":     total,
        "Realizadas":    int(realizadas),
        "Pendientes":    int(pendientes),
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


# ── Helpers de metas ───────────────────────────────────────────────────────────
def get_months_in_period(start: date, end: date) -> list:
    """Lista de 'YYYY-MM' para todos los meses que toca el período."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def get_meta_periodo(name: str, goals_dict: dict, months: list) -> int:
    entity = goals_dict.get(name, {})
    if isinstance(entity, dict):
        return sum(int(entity.get(mo, 0)) for mo in months)
    # Formato antiguo (single int)
    return int(entity) * len(months) if entity else 0


def calculate_ideal_pct(start: date, end: date, hoy: date) -> float:
    """% del período que debería estar cumplido a día de hoy."""
    if hoy <= start:
        return 0.0
    if hoy >= end:
        return 100.0
    total   = (end - start).days
    elapsed = (hoy - start).days
    return round(elapsed / total * 100, 1) if total > 0 else 100.0


def add_cumplimiento(df_t: pd.DataFrame, key_col: str, goals_dict: dict,
                     months: list, ideal_pct: float) -> pd.DataFrame:
    df_t = df_t.copy()

    df_t["Meta período"] = df_t[key_col].apply(
        lambda n: get_meta_periodo(n, goals_dict, months)
    )
    df_t["% Agendadas"] = df_t.apply(
        lambda r: f"{round(r['Agendadas'] / r['Meta período'] * 100, 1)}%"
        if r["Meta período"] > 0 else "—", axis=1,
    )
    df_t["% Realizadas"] = df_t.apply(
        lambda r: f"{round(r['Realizadas'] / r['Meta período'] * 100, 1)}%"
        if r["Meta período"] > 0 else "—", axis=1,
    )
    df_t["% Ideal hoy"] = df_t["Meta período"].apply(
        lambda m: f"{ideal_pct}%" if m > 0 else "—"
    )
    return df_t


def build_meta_df(entities: list, goals_dict: dict) -> pd.DataFrame:
    """DataFrame editable con filas=entidades, columnas=meses."""
    rows = []
    for e in entities:
        eg = goals_dict.get(e, {})
        if not isinstance(eg, dict):
            eg = {}
        row = {"Nombre": e}
        for key, label in zip(_MONTH_KEYS, _MONTH_LABELS):
            row[label] = int(eg.get(key, 0))
        rows.append(row)
    if not rows:
        row = {"Nombre": "—"}
        for label in _MONTH_LABELS:
            row[label] = 0
        rows = [row]
    return pd.DataFrame(rows)


def extract_goals_from_df(edited_df: pd.DataFrame) -> dict:
    result = {}
    for _, row in edited_df.iterrows():
        name = str(row["Nombre"]).strip()
        if not name or name == "—":
            continue
        result[name] = {
            key: int(row.get(label, 0))
            for key, label in zip(_MONTH_KEYS, _MONTH_LABELS)
        }
    return result


# ── Cargar metas y calcular período ───────────────────────────────────────────
goals           = load_goals()
months_in_period = get_months_in_period(start_date, end_date)
ideal_pct       = calculate_ideal_pct(start_date, end_date, today)

# ── KPIs ───────────────────────────────────────────────────────────────────────
total            = len(df)
realizadas_total = (df["estado"] == "Realizada").sum()
pendientes_total = (df["estado"] == "Pendiente").sum()
no_real_total    = (df["estado"] == "No realizada").sum()
reagendar_total  = (df["estado"] == "Reagendar").sum()
tasa_total       = round(realizadas_total / total * 100, 1) if total > 0 else 0
prop_total       = 0
if "propuesta" in df.columns:
    prop_total = df["propuesta"].astype(str).str.strip().str.lower().isin(_SI_PROPUESTA).sum()

st.title("📅 Gestión de Reuniones SDR")
periodo_str = f"{start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}"
st.caption(f"Período: **{periodo_str}** · {total:,} reuniones con los filtros actuales")
st.divider()

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("📋 Agendadas",       f"{total:,}")
c2.metric("✅ Realizadas",       f"{realizadas_total:,}")
c3.metric("⏳ Pendientes",       f"{pendientes_total:,}")
c4.metric("🔄 Reagendar",        f"{reagendar_total:,}")
c5.metric("❌ No realizadas",    f"{no_real_total:,}")
c6.metric("📈 Tasa realización", f"{tasa_total}%")
c7.metric("📄 Con propuesta",    f"{prop_total:,}")

# ── KPIs de metas ──────────────────────────────────────────────────────────────
_sdr_goals = goals.get("sdr", {})
_cli_goals = goals.get("cliente", {})

# Si hay filtro activo de SDR, usar solo la meta de ese SDR.
# Si se filtra por cliente (sin SDR específico), sumar metas solo de los SDRs que trabajan ese cliente.
if sel_sdr != "Todos":
    meta_sdr_total = get_meta_periodo(sel_sdr, _sdr_goals, months_in_period)
elif sel_client != "Todos" and "sdr" in df.columns:
    sdrs_del_cliente = df["sdr"].replace({"": pd.NA, "nan": pd.NA}).dropna().unique().tolist()
    meta_sdr_total = sum(get_meta_periodo(sdr, _sdr_goals, months_in_period) for sdr in sdrs_del_cliente)
else:
    meta_sdr_total = sum(get_meta_periodo(n, _sdr_goals, months_in_period) for n in _sdr_goals)

# Si hay filtro activo de Cliente, usar solo la meta de ese cliente
if sel_client != "Todos":
    meta_cli_total = get_meta_periodo(sel_client, _cli_goals, months_in_period)
else:
    meta_cli_total = sum(get_meta_periodo(n, _cli_goals, months_in_period) for n in _cli_goals)

cump_sdr = f"{round(realizadas_total / meta_sdr_total * 100, 1)}%" if meta_sdr_total > 0 else "Sin meta"
cump_cli = f"{round(realizadas_total / meta_cli_total * 100, 1)}%" if meta_cli_total > 0 else "Sin meta"

st.markdown("")   # pequeño espacio visual
m1, m2, m3, m4 = st.columns(4)
m1.metric("🎯 Meta SDR",             f"{meta_sdr_total:,}",
          help=f"Meta de {'«' + sel_sdr + '»' if sel_sdr != 'Todos' else 'todos los SDR'} en el período filtrado")
m2.metric("🎯 Meta Clientes",        f"{meta_cli_total:,}",
          help=f"Meta de {'«' + sel_client + '»' if sel_client != 'Todos' else 'todos los clientes'} en el período filtrado")
m3.metric("📊 Cumplimiento SDR",     cump_sdr,
          help="Reuniones realizadas ÷ Meta SDR del período")
m4.metric("📊 Cumplimiento Clientes", cump_cli,
          help="Reuniones realizadas ÷ Meta Clientes del período")

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
    st.subheader(f"Evolución de reuniones — {preset}")

    # Usar la misma columna de fecha con la que se filtró, así los meses corresponden al período visible
    _fc = fecha_col if fecha_col in df.columns else ("fecha_reunion" if "fecha_reunion" in df.columns else None)
    if _fc:
        df_per = df[df[_fc].notna()].copy()
        df_per["_mes_periodo"] = df_per[_fc].dt.to_period("M").astype(str)
    else:
        df_per = df.copy()
        df_per["_mes_periodo"] = df_per.get("mes", pd.Series(dtype=str))

    df_per = df_per[df_per["_mes_periodo"].ne("") & df_per["_mes_periodo"].notna()]

    if not df_per.empty and df_per["_mes_periodo"].ne("").any():
        monthly = (
            _agg_by(df_per, "_mes_periodo")
            .rename(columns={"_mes_periodo": "Mes"})
            .sort_values("Mes")
        )

        # Calcular tasa numérica para la línea (usar NaN en vez de None para Plotly)
        import math
        monthly["_tasa_num"] = monthly.apply(
            lambda r: round(r["Realizadas"] / r["Agendadas"] * 100, 1)
            if r["Agendadas"] > 0 else float("nan"),
            axis=1,
        )

        # Etiquetas de mes más legibles: "2026-03" → "Mar 26"
        _MES_ES = {
            "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
            "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
            "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
        }
        def _mes_label(s):
            parts = str(s).split("-")
            if len(parts) == 2:
                return f"{_MES_ES.get(parts[1], parts[1])} {parts[0][2:]}"
            return s
        monthly["_label"] = monthly["Mes"].apply(_mes_label)

        fig = go.Figure()

        # Barra: Agendadas (fondo semitransparente)
        fig.add_bar(
            x=monthly["_label"],
            y=monthly["Agendadas"],
            name="Agendadas",
            marker=dict(color="rgba(168,218,220,0.55)", line=dict(color="#a8dadc", width=1.5)),
            text=monthly["Agendadas"],
            textposition="outside",
            textfont=dict(size=13, color="#2d7d9a", family="Inter, sans-serif"),
        )

        # Barra: Realizadas (superpuesta, más opaca)
        fig.add_bar(
            x=monthly["_label"],
            y=monthly["Realizadas"],
            name="Realizadas",
            marker=dict(color="rgba(69,123,157,0.90)", line=dict(color="#2d6a8f", width=1)),
            text=monthly["Realizadas"],
            textposition="inside",
            textfont=dict(size=12, color="white", family="Inter, sans-serif"),
        )

        # Línea: Tasa de realización (eje derecho)
        tasa_text = [
            f"{t:.0f}%" if (t == t and t is not None) else ""   # t == t descarta NaN
            for t in monthly["_tasa_num"]
        ]
        fig.add_scatter(
            x=monthly["_label"],
            y=monthly["_tasa_num"],
            name="Tasa realización",
            mode="lines+markers+text",
            yaxis="y2",
            line=dict(color="#f4a261", width=2.5),
            marker=dict(size=9, color="#f4a261", symbol="circle",
                        line=dict(color="white", width=2)),
            text=tasa_text,
            textposition="top center",
            textfont=dict(size=10, color="#f4a261"),
        )

        max_ag = int(monthly["Agendadas"].max()) if not monthly.empty else 10
        fig.update_layout(
            barmode="overlay",
            height=460,
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis=dict(
                title="",
                tickangle=-20,
                showgrid=False,
                linecolor="#e0e0e0",
                tickfont=dict(size=12),
            ),
            yaxis=dict(
                title="Reuniones",
                gridcolor="rgba(0,0,0,0.06)",
                zeroline=False,
                range=[0, max_ag * 1.35],   # espacio para labels "outside"
            ),
            yaxis2=dict(
                title=dict(text="Tasa realización %", font=dict(color="#f4a261")),
                overlaying="y",
                side="right",
                range=[0, 130],
                showgrid=False,
                ticksuffix="%",
                tickfont=dict(color="#f4a261"),
            ),
            legend=dict(
                orientation="h",
                y=1.06, x=0,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="#e0e0e0",
                borderwidth=1,
            ),
            margin=dict(t=60, b=40, l=50, r=60),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Resumen compacto bajo el gráfico
        resumen_cols = ["Mes", "Agendadas", "Realizadas", "Pendientes", "Reagendar",
                        "No realizadas", "Con propuesta"]
        monthly_disp = monthly[[c for c in resumen_cols if c in monthly.columns]].copy()
        monthly_disp["Tasa"] = monthly["_tasa_num"].apply(
            lambda t: f"{t:.1f}%" if (t == t) else "—"   # t != t detecta NaN
        )
        with st.expander("📋 Ver tabla de datos"):
            st.dataframe(monthly_disp, use_container_width=True, hide_index=True)
    else:
        st.info("No hay datos para el período seleccionado.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Por SDR
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sdr:
    st.subheader("Reuniones por SDR / Responsable")

    if "sdr" not in df.columns:
        st.warning("No se encontró la columna de SDR/Responsable.")
    else:
        sdr_df = _agg_by(df, "sdr").rename(columns={"sdr": "SDR"})
        sdr_df = add_tasa(sdr_df)
        sdr_df = add_cumplimiento(sdr_df, "SDR", goals.get("sdr", {}), months_in_period, ideal_pct)
        sdr_df = sdr_df.sort_values("Agendadas", ascending=False)

        display_cols = ["SDR", "Agendadas", "Realizadas", "Pendientes", "No realizadas", "Con propuesta", "Tasa realización"]
        if sdr_df["Meta período"].sum() > 0:
            display_cols += ["Meta período", "% Agendadas", "% Realizadas", "% Ideal hoy"]

        st.dataframe(sdr_df[display_cols], use_container_width=True, hide_index=True,
                     column_config={
                         "% Ideal hoy": st.column_config.TextColumn(
                             "% Ideal hoy",
                             help=f"Porcentaje que debería estar cumplido a hoy ({today.strftime('%d/%m/%Y')}) "
                                  f"según el avance del período ({ideal_pct}%)"
                         )
                     })

        # Desglose mensual
        with st.expander("📆 Ver desglose mensual por SDR"):
            mes_col2 = "mes_agenda" if "mes_agenda" in df.columns else "mes"
            if mes_col2 in df.columns:
                rows_sm = []
                for (mes, sdr), g in df.groupby([mes_col2, "sdr"]):
                    ag   = len(g)
                    re   = (g["estado"] == "Realizada").sum()
                    tasa = f"{round(re/ag*100,1)}%" if ag > 0 else "—"
                    rows_sm.append({"Mes": mes, "SDR": sdr, "Agendadas": ag, "Realizadas": int(re), "Tasa": tasa})
                if rows_sm:
                    sdr_monthly = pd.DataFrame(rows_sm).sort_values(["Mes", "Agendadas"], ascending=[True, False])
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

        cli_df = (
            _agg_by(
                df_cli, "cliente",
                extra_fn=lambda g: {"SDRs": int(g["sdr"].nunique()) if "sdr" in g.columns else 0},
            )
            .rename(columns={"cliente": "Cliente"})
        )
        cli_df = add_tasa(cli_df)
        cli_df = add_cumplimiento(cli_df, "Cliente", goals.get("cliente", {}), months_in_period, ideal_pct)
        cli_df = cli_df.sort_values("Agendadas", ascending=False)

        display_cols = ["Cliente", "Agendadas", "Realizadas", "Pendientes", "No realizadas",
                        "Con propuesta", "SDRs", "Tasa realización"]
        if cli_df["Meta período"].sum() > 0:
            display_cols += ["Meta período", "% Agendadas", "% Realizadas", "% Ideal hoy"]

        available = [c for c in display_cols if c in cli_df.columns]
        st.dataframe(cli_df[available], use_container_width=True, hide_index=True,
                     column_config={
                         "% Ideal hoy": st.column_config.TextColumn(
                             "% Ideal hoy",
                             help=f"Porcentaje que debería estar cumplido a hoy ({today.strftime('%d/%m/%Y')}) "
                                  f"según el avance del período ({ideal_pct}%)"
                         )
                     })

        # Desglose mensual
        with st.expander("📆 Ver desglose mensual por cliente"):
            mes_col3 = "mes_agenda" if "mes_agenda" in df_cli.columns else "mes"
            if mes_col3 in df_cli.columns:
                rows_cm = []
                for (mes, cli), g in df_cli.groupby([mes_col3, "cliente"]):
                    ag   = len(g)
                    re   = (g["estado"] == "Realizada").sum()
                    tasa = f"{round(re/ag*100,1)}%" if ag > 0 else "—"
                    rows_cm.append({"Mes": mes, "Cliente": cli, "Agendadas": ag, "Realizadas": int(re), "Tasa": tasa})
                if rows_cm:
                    cli_monthly = pd.DataFrame(rows_cm).sort_values(["Mes", "Agendadas"], ascending=[True, False])
                    st.dataframe(cli_monthly, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Análisis
# ═══════════════════════════════════════════════════════════════════════════════
with tab_analisis:
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_esp   = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
    }

    def _day_bar_chart(byday_df, count_col, bar_color, text_color, title):
        """Bar chart de reuniones por día con números encima."""
        max_val = int(byday_df[count_col].max()) if not byday_df.empty else 1
        fig = go.Figure(go.Bar(
            x=byday_df["Día"],
            y=byday_df[count_col],
            text=byday_df[count_col],
            textposition="outside",
            textfont=dict(size=14, color=text_color, family="Inter, sans-serif"),
            marker=dict(color=bar_color, line=dict(width=0), opacity=0.85),
        ))
        fig.update_layout(
            title=dict(text=title, font=dict(size=15, color="#333"), x=0),
            height=320,
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis=dict(
                title="", showgrid=False,
                linecolor="#e0e0e0", linewidth=1,
                tickfont=dict(size=13, color="#444"),
            ),
            yaxis=dict(
                showgrid=True, gridcolor="rgba(0,0,0,0.05)",
                showticklabels=False,
                range=[0, max_val * 1.28],
                zeroline=False,
            ),
            margin=dict(t=45, b=20, l=10, r=10),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    col_l, col_r = st.columns(2)

    if "dia_semana" in df.columns:
        # Datos agendadas
        by_ag = df.groupby("dia_semana").size().reset_index(name="N")
        by_ag["Día"]   = by_ag["dia_semana"].map(day_esp)
        by_ag["orden"] = by_ag["dia_semana"].map({d: i for i, d in enumerate(day_order)})
        by_ag = by_ag.sort_values("orden")

        # Datos realizadas
        by_re = (
            df[df["estado"] == "Realizada"]
            .groupby("dia_semana").size().reset_index(name="N")
        )
        by_re["Día"]   = by_re["dia_semana"].map(day_esp)
        by_re["orden"] = by_re["dia_semana"].map({d: i for i, d in enumerate(day_order)})
        by_re = by_re.sort_values("orden")

        with col_l:
            _day_bar_chart(by_ag, "N", "#457b9d", "#1a5276", "📅 Agendadas por día de semana")
        with col_r:
            _day_bar_chart(by_re, "N", "#52b788", "#1a6b3c", "✅ Realizadas por día de semana")
    else:
        col_l.info("No hay datos de día de semana.")

    st.divider()

    col_orig, _ = st.columns([1, 1])
    with col_orig:
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

    with col_l2:
        st.subheader("🌎 Reuniones por País")
        if "pais" in df.columns:
            pais_df = (
                df[df["pais"].replace({"": pd.NA, "nan": pd.NA}).notna()]
                .groupby("pais")
                .apply(lambda g: pd.Series({
                    "Agendadas":  len(g),
                    "Realizadas": (g["estado"] == "Realizada").sum(),
                    "Pendientes": (g["estado"] == "Pendiente").sum(),
                }))
                .reset_index()
                .rename(columns={"pais": "País"})
                .sort_values("Agendadas", ascending=False)
            )
            pais_df["Tasa realización"] = pais_df.apply(
                lambda r: f"{round(r['Realizadas']/r['Agendadas']*100,1)}%" if r["Agendadas"] > 0 else "—",
                axis=1,
            )
            fig = px.bar(pais_df, x="Agendadas", y="País", orientation="h",
                         color="Agendadas", color_continuous_scale="Blues", height=350)
            fig.update_layout(coloraxis_showscale=False, yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pais_df, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontró columna de País.")

    with col_r2:
        st.subheader("📄 Reuniones con Propuesta enviada")
        if "propuesta" in df.columns:
            df_prop  = df[df["propuesta"].astype(str).str.strip().str.lower().isin(_SI_PROPUESTA)].copy()
            n_prop   = len(df_prop)
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
    st.subheader(f"🎯 Configuración de Metas Mensuales — {_GOALS_YEAR}")

    # Obtener activos desde Maestra IA
    with st.spinner("Cargando activos desde Maestra IA..."):
        maestra        = get_maestra_activos(st.secrets)
    active_sdrs      = maestra.get("sdrs", [])
    active_clientes  = maestra.get("clientes", [])

    if not active_sdrs and not active_clientes:
        st.warning("No se pudieron cargar los activos desde la Maestra IA. "
                   "Verifica que la pestaña 'Maestra IA' exista y tenga datos.")

    # Tooltip explicativo del % ideal
    st.info(
        f"📌 **¿Cómo se calcula el % Ideal hoy?** "
        f"Divide los días transcurridos del período entre el total de días del período. "
        f"Para el período actual ({start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}), "
        f"el % ideal a hoy es **{ideal_pct}%**."
    )

    # ── Configuración de columnas del editor ──────────────────────────────────
    month_col_config = {
        label: st.column_config.NumberColumn(label, min_value=0, max_value=999, step=1, format="%d")
        for label in _MONTH_LABELS
    }

    # ──────────────────────────────────────────────────────────────────────────
    # Tabla SDR
    # ──────────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 👤 Metas por SDR")
    st.caption("Solo se muestran los SDR marcados como **Activo** en la Maestra IA.")

    if active_sdrs:
        sdr_meta_df = build_meta_df(active_sdrs, goals.get("sdr", {}))
        sdr_edited  = st.data_editor(
            sdr_meta_df,
            use_container_width=True,
            hide_index=True,
            disabled=["Nombre"],
            column_config={
                "Nombre": st.column_config.TextColumn("SDR", width="medium"),
                **month_col_config,
            },
            key="sdr_meta_editor",
        )
        if st.button("💾 Guardar metas SDR", use_container_width=True, type="primary", key="btn_save_sdr"):
            goals["sdr"] = extract_goals_from_df(sdr_edited)
            save_goals(goals)
            st.success("✅ Metas de SDR guardadas correctamente")
            st.rerun()
    else:
        st.info("No se encontraron SDR activos en la Maestra IA.")

    # ──────────────────────────────────────────────────────────────────────────
    # Tabla Clientes
    # ──────────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏢 Metas por Cliente")
    st.caption("Solo se muestran los clientes marcados como **Activo** en la Maestra IA.")

    if active_clientes:
        cli_meta_df = build_meta_df(active_clientes, goals.get("cliente", {}))
        cli_edited  = st.data_editor(
            cli_meta_df,
            use_container_width=True,
            hide_index=True,
            disabled=["Nombre"],
            column_config={
                "Nombre": st.column_config.TextColumn("Cliente", width="medium"),
                **month_col_config,
            },
            key="cli_meta_editor",
        )
        if st.button("💾 Guardar metas Clientes", use_container_width=True, type="primary", key="btn_save_cli"):
            goals["cliente"] = extract_goals_from_df(cli_edited)
            save_goals(goals)
            st.success("✅ Metas de clientes guardadas correctamente")
            st.rerun()
    else:
        st.info("No se encontraron clientes activos en la Maestra IA.")

    # ── Resumen cumplimiento mes actual ───────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### 📊 Cumplimiento — {today.strftime('%B %Y').capitalize()}")
    st.caption(
        f"Reuniones agendadas en el mes actual vs. meta de {today.strftime('%B %Y')}. "
        f"% Ideal hoy: **{calculate_ideal_pct(date(today.year, today.month, 1), date(today.year, today.month, calendar.monthrange(today.year, today.month)[1]), today)}%**"
    )

    this_month_key   = today.strftime("%Y-%m")
    this_month_start = date(today.year, today.month, 1)
    this_month_end   = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    ideal_mes_actual = calculate_ideal_pct(this_month_start, this_month_end, today)

    df_mes     = df_raw.copy()
    fecha_c    = "fecha_agendamiento" if "fecha_agendamiento" in df_mes.columns else "fecha"
    if fecha_c in df_mes.columns:
        df_mes = df_mes[df_mes[fecha_c].notna()]
        df_mes = df_mes[
            (df_mes[fecha_c].dt.date >= this_month_start) &
            (df_mes[fecha_c].dt.date <= today)
        ]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"**Por SDR**")
        sdr_goals_mes = goals.get("sdr", {})
        if "sdr" in df_mes.columns and sdr_goals_mes:
            rows_sdr = []
            for sdr_name in active_sdrs or sorted(df_mes["sdr"].dropna().unique()):
                ag   = int((df_mes["sdr"] == sdr_name).sum())
                re   = int(((df_mes["sdr"] == sdr_name) & (df_mes["estado"] == "Realizada")).sum())
                meta = int(sdr_goals_mes.get(sdr_name, {}).get(this_month_key, 0)) if isinstance(sdr_goals_mes.get(sdr_name), dict) else 0
                rows_sdr.append({
                    "SDR":          sdr_name,
                    "Agendadas":    ag,
                    "Realizadas":   re,
                    "Meta mes":     meta,
                    "% Agendadas":  f"{round(ag/meta*100,1)}%" if meta > 0 else "—",
                    "% Realizadas": f"{round(re/meta*100,1)}%" if meta > 0 else "—",
                    "% Ideal hoy":  f"{ideal_mes_actual}%"     if meta > 0 else "—",
                })
            if rows_sdr:
                st.dataframe(
                    pd.DataFrame(rows_sdr).sort_values("Agendadas", ascending=False),
                    use_container_width=True, hide_index=True,
                )
        else:
            st.info("Configura metas de SDR arriba para ver el cumplimiento.")

    with col_b:
        st.markdown(f"**Por Cliente**")
        cli_goals_mes = goals.get("cliente", {})
        if "cliente" in df_mes.columns and cli_goals_mes:
            df_mes_cli = df_mes[df_mes["cliente"].replace({"": pd.NA, "nan": pd.NA}).notna()]
            rows_cli = []
            for cli_name in active_clientes or sorted(df_mes_cli["cliente"].dropna().unique()):
                ag   = int((df_mes_cli["cliente"] == cli_name).sum())
                re   = int(((df_mes_cli["cliente"] == cli_name) & (df_mes_cli["estado"] == "Realizada")).sum())
                meta = int(cli_goals_mes.get(cli_name, {}).get(this_month_key, 0)) if isinstance(cli_goals_mes.get(cli_name), dict) else 0
                rows_cli.append({
                    "Cliente":      cli_name,
                    "Agendadas":    ag,
                    "Realizadas":   re,
                    "Meta mes":     meta,
                    "% Agendadas":  f"{round(ag/meta*100,1)}%" if meta > 0 else "—",
                    "% Realizadas": f"{round(re/meta*100,1)}%" if meta > 0 else "—",
                    "% Ideal hoy":  f"{ideal_mes_actual}%"     if meta > 0 else "—",
                })
            if rows_cli:
                st.dataframe(
                    pd.DataFrame(rows_cli).sort_values("Agendadas", ascending=False),
                    use_container_width=True, hide_index=True,
                )
        else:
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
    display   = df[show_cols].copy()

    for dc in ["fecha_agendamiento", "fecha_reunion"]:
        if dc in display.columns:
            display[dc] = display[dc].dt.strftime("%d/%m/%Y")

    display = display.rename(columns=col_labels)

    if "Fecha agendamiento" in display.columns:
        display = display.sort_values("Fecha agendamiento", ascending=False)

    st.dataframe(display, use_container_width=True, hide_index=True)
