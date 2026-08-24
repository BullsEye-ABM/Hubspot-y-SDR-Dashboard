"""
ALLO · Gestion Telefonica
Bullseye (SOi Digital) · ALLO API · Cache 15 min
Actividad de llamadas por SDR y por numero/cliente, tasas de conexion
(sin voicemail), reuniones agendadas y desglose por etiquetas.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime

from utils.auth import require_login
from utils.allo import (
    list_numbers, list_users, list_tags, fetch_conversation_items,
    items_to_dataframe, connection_rate_excl_voicemail, meetings_booked_count,
    tag_breakdown, breakdown_by, CONNECTED_RESULTS, MEETING_TAG,
)
from utils.periods import PERIOD_OPTIONS, get_period_dates


# ─────────────────────────────────────────
#  Page config & CSS (mismo sistema de diseno dark que el resto del dashboard)
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Bullseye · ALLO",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_login()

st.markdown("""
<style>
:root {
  --bg: #0b1020; --card: #161e3d; --border: #243056;
  --text: #e6eaf2; --text-dim: #93a0c2;
  --accent: #e63946; --accent-2: #f4a261;
  --green: #34d399; --amber: #fbbf24; --red: #f87171;
  --purple: #a78bfa; --pink: #f472b6;
}
html, body, [data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg, #0a0e22 0%, #0b1020 100%);
  color: var(--text);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.5rem; padding-bottom: 4rem; max-width: 1400px; }
.brand-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 24px;
  gap: 20px; flex-wrap: wrap;
}
.brand-left { display: flex; align-items: center; gap: 14px; }
.brand-logo {
  width: 48px; height: 48px; border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 22px; color: #fff;
}
.brand-title { font-size: 22px; font-weight: 700; margin: 0; color: var(--text); }
.brand-sub { font-size: 13px; color: var(--text-dim); margin: 2px 0 0; }
.brand-right { text-align: right; font-size: 13px; color: var(--text-dim); }
.brand-right strong { color: var(--text); display: block; font-size: 14px; }
.pill {
  display: inline-block; padding: 4px 10px; border-radius: 999px;
  background: rgba(230,57,70,.12); color: var(--accent);
  font-size: 11px; font-weight: 600; margin-top: 6px;
}
.section-title {
  font-size: 12px; text-transform: uppercase; letter-spacing: 1.4px;
  color: var(--text-dim); font-weight: 600; margin: 32px 0 12px;
}
.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 8px; }
@media (max-width: 1100px) { .kpi-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 600px)  { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 16px;
}
.kpi-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); margin-bottom: 8px; font-weight: 600; }
.kpi-value { font-size: 28px; font-weight: 700; letter-spacing: -.5px; line-height: 1.1; }
.kpi-sub { font-size: 11.5px; color: var(--text-dim); margin-top: 4px; }
.kpi.accent .kpi-value { color: var(--accent); }
.kpi.green  .kpi-value { color: var(--green); }
.kpi.amber  .kpi-value { color: var(--amber); }
.kpi.red    .kpi-value { color: var(--red); }
.kpi.purple .kpi-value { color: var(--purple); }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px;
}
.tag-pill {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 600; margin: 2px;
}
[data-testid="stSidebar"] { background: var(--card) !important; border-right: 1px solid var(--border); }
[data-testid="stSidebar"] * { color: var(--text) !important; }
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] small {
  color: var(--text-dim) !important;
}
[data-testid="stSidebar"] h3 { color: var(--text) !important; font-size: 14px !important; letter-spacing: 1px; }
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="input"] > div {
  background: rgba(255,255,255,0.03) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] svg { fill: var(--text-dim) !important; }
[data-testid="stSidebar"] [data-baseweb="popover"] li { color: var(--text) !important; }
[data-testid="stSidebar"] hr { border-color: var(--border) !important; }
[data-testid="stSidebar"] .stButton button {
  background: linear-gradient(135deg, var(--accent), var(--accent-2)) !important;
  color: #fff !important;
  border: none !important;
  font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] { padding: 8px 16px; }
hr { margin: 1.2rem 0; border-color: var(--border); }
.dt {
  width: 100%; border-collapse: collapse; font-size: 13px;
  background: var(--card); border-radius: 12px; overflow: hidden;
  border: 1px solid var(--border); margin-bottom: 8px;
}
.dt th, .dt td {
  padding: 10px 14px; text-align: left;
  border-bottom: 1px solid var(--border);
}
.dt th {
  color: var(--text-dim); font-weight: 600; font-size: 11px;
  text-transform: uppercase; letter-spacing: 1px;
  background: rgba(255,255,255,.02);
}
.dt td { color: var(--text); }
.dt tr:last-child td { border-bottom: none; }
.dt tr:hover td { background: rgba(255,255,255,.02); }
.dt-wrap { max-height: 460px; overflow-y: auto; border-radius: 12px; }
[data-testid="stMain"] [data-baseweb="select"] > div,
section.main [data-baseweb="select"] > div {
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
}
[data-testid="stMain"] [data-baseweb="select"] svg,
section.main [data-baseweb="select"] svg { fill: var(--text-dim) !important; }
[data-baseweb="popover"], [data-baseweb="popover"] *,
[data-baseweb="menu"], [data-baseweb="menu"] *,
[role="listbox"], [role="listbox"] * {
  background-color: var(--card) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}
[data-baseweb="popover"] {
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  box-shadow: 0 10px 30px rgba(0,0,0,.5) !important;
}
[data-baseweb="popover"] li:hover, [data-baseweb="menu"] li:hover,
[role="option"]:hover, [role="option"][aria-selected="true"] {
  background-color: rgba(230,57,70,.20) !important;
  color: var(--text) !important;
}
[data-testid="stAudio"] audio, audio {
  width: 100% !important;
  filter: invert(.88) hue-rotate(180deg) saturate(.7);
  border-radius: 8px;
}
[data-testid="stExpander"] {
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  margin-bottom: 6px;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] { color: var(--text) !important; }
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] { color: var(--text-dim); }
</style>
""", unsafe_allow_html=True)


PLOT_TEMPLATE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#93a0c2", family="Inter, sans-serif"),
    margin=dict(t=50, b=20, l=20, r=20),
)


def _data_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df is None or df.empty:
        return '<div class="card"><em style="color:var(--text-dim)">Sin datos.</em></div>'
    headers = "".join(f"<th>{c}</th>" for c in columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{row[c]}</td>" for c in columns)
        rows.append(f"<tr>{cells}</tr>")
    return (
        f'<div class="dt-wrap"><table class="dt">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table></div>'
    )


def fmt_duration(mins: float) -> str:
    if not mins:
        return "–"
    m = int(mins)
    s = int((mins - m) * 60)
    return f"{m}:{s:02d}"


# ─────────────────────────────────────────
#  Reference data
# ─────────────────────────────────────────
numbers = list_numbers()
users = list_users()
tags_catalog = list_tags()

number_name_map = {n["number"]: n.get("name") or n["number"] for n in numbers}
user_name_map = {u["id"]: u["name"] for u in users}


# ─────────────────────────────────────────
#  Sidebar filters
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎛️ Filtros")
    period = st.selectbox(
        "Periodo", PERIOD_OPTIONS, index=2,
        help="Cambia el rango temporal del informe completo",
    )
    start_date, end_date = get_period_dates(period)
    st.caption(f"📅 {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}")
    st.divider()

    sdr_options = ["Todos"] + [u["name"] for u in users]
    sdr_choice = st.multiselect("SDR", sdr_options, default=["Todos"])

    number_labels = [f"{n.get('name') or n['number']} ({n['number']})" for n in numbers]
    number_label_to_number = {
        f"{n.get('name') or n['number']} ({n['number']})": n["number"] for n in numbers
    }
    number_choice = st.multiselect("Número / Cliente", ["Todos"] + number_labels, default=["Todos"])

    st.divider()
    if st.button("🔄 Forzar actualizacion", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱️ Cache: 15 min · Datos en vivo desde ALLO")
    st.caption(f"🕐 Ultima carga: {datetime.now().strftime('%H:%M:%S')}")


# ─────────────────────────────────────────
#  Header
# ─────────────────────────────────────────
st.markdown(
    f'<div class="brand-header"><div class="brand-left"><div class="brand-logo">📞</div>'
    f'<div><div class="brand-title">ALLO · Gestion Telefonica</div>'
    f'<div class="brand-sub">Bullseye (SOi Digital) · Actividad de llamadas por SDR y por cliente</div></div></div>'
    f'<div class="brand-right"><strong>Reporteria ALLO</strong>'
    f'<span>Datos al {datetime.now().strftime("%d %b %Y")}</span><br>'
    f'<span>Periodo: {start_date.strftime("%d %b %Y")} → {end_date.strftime("%d %b %Y")}</span>'
    f'<div class="pill">{len(numbers)} numeros · {len(users)} SDRs</div></div></div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────
#  Fetch + filter data
# ─────────────────────────────────────────
raw_items, truncated = fetch_conversation_items(start_date, end_date, item_type="ALL")
df_all = items_to_dataframe(raw_items)

if truncated:
    st.warning(
        f"⚠️ El periodo seleccionado tiene mas actividad de la que se puede cargar de una vez "
        f"(limite {len(raw_items):,} registros). Los datos mostrados corresponden solo a una parte "
        f"del periodo; reduce el rango de fechas para ver el total exacto."
    )

df = df_all.copy()
if not df.empty:
    df["client_name"] = df["allo_number"].map(number_name_map).fillna(df["allo_number"])

    if sdr_choice and "Todos" not in sdr_choice:
        df = df[df["user_name"].isin(sdr_choice)]

    if number_choice and "Todos" not in number_choice:
        selected_numbers = [number_label_to_number[lbl] for lbl in number_choice if lbl in number_label_to_number]
        df = df[df["allo_number"].isin(selected_numbers)]

    df["date_local"] = df["date"].dt.tz_convert("America/Santiago")
    df["date_day"] = df["date_local"].dt.date


# ─────────────────────────────────────────
#  KPIs
# ─────────────────────────────────────────
total_activities = len(df)
calls_df = df[df["type"] == "CALL"] if not df.empty else df
outbound_calls = calls_df[calls_df["direction"] == "OUTBOUND"] if not calls_df.empty else calls_df
conn_rate, connected_n, voicemail_n, denom = connection_rate_excl_voicemail(df)
meetings_n = meetings_booked_count(df)
avg_conn_dur = (
    outbound_calls.loc[outbound_calls["result"].isin(CONNECTED_RESULTS), "duration_min"].mean()
    if not outbound_calls.empty else 0
)

st.markdown('<div class="section-title">Indicadores clave</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="kpi-row">'
    f'<div class="kpi accent"><div class="kpi-label">Actividades</div><div class="kpi-value">{total_activities}</div>'
    f'<div class="kpi-sub">Llamadas + SMS en el periodo</div></div>'
    f'<div class="kpi"><div class="kpi-label">Llamadas salientes</div><div class="kpi-value">{len(outbound_calls)}</div>'
    f'<div class="kpi-sub">Dial-outs del equipo</div></div>'
    f'<div class="kpi green"><div class="kpi-label">Tasa de conexion</div><div class="kpi-value">{conn_rate:.1f}%</div>'
    f'<div class="kpi-sub">Sin contar voicemail · {connected_n}/{denom}</div></div>'
    f'<div class="kpi amber"><div class="kpi-label">Voicemail</div><div class="kpi-value">{voicemail_n}</div>'
    f'<div class="kpi-sub">Excluidos de la tasa de conexion</div></div>'
    f'<div class="kpi purple"><div class="kpi-label">Reuniones agendadas</div><div class="kpi-value">{meetings_n}</div>'
    f'<div class="kpi-sub">Etiqueta "Meeting booked"</div></div>'
    f'<div class="kpi"><div class="kpi-label">Duracion prom. conectadas</div><div class="kpi-value">{fmt_duration(avg_conn_dur)}</div>'
    f'<div class="kpi-sub">Llamadas ANSWERED/TRANSFERRED</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

if df.empty:
    st.info("📭 No hay actividad de ALLO en este periodo con los filtros seleccionados.")
    st.stop()


# ─────────────────────────────────────────
#  Charts: temporal
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Actividad temporal</div>', unsafe_allow_html=True)
col_a, col_b = st.columns([2, 1])

with col_a:
    daily = (
        calls_df.assign(
            conectada=lambda x: x["result"].isin(CONNECTED_RESULTS).astype(int),
            voicemail=lambda x: (x["result"] == "VOICEMAIL").astype(int),
            otro=lambda x: (~x["result"].isin(CONNECTED_RESULTS) & (x["result"] != "VOICEMAIL")).astype(int),
        )
        .groupby("date_day")[["conectada", "voicemail", "otro"]].sum().reset_index()
        .sort_values("date_day")
    ) if not calls_df.empty else pd.DataFrame()

    fig = go.Figure()
    if not daily.empty:
        fig.add_bar(x=daily["date_day"], y=daily["conectada"], name="Conectadas", marker_color="#34d399")
        fig.add_bar(x=daily["date_day"], y=daily["voicemail"], name="Voicemail", marker_color="#fbbf24")
        fig.add_bar(x=daily["date_day"], y=daily["otro"], name="Otros", marker_color="#f87171")
    fig.update_layout(
        title=dict(text="Llamadas por dia", font=dict(color="#e6eaf2", size=15)),
        barmode="stack", height=380,
        legend=dict(orientation="h", y=-0.2),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        **PLOT_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    daily_rate = (
        outbound_calls.assign(
            is_vm=lambda x: (x["result"] == "VOICEMAIL"),
            is_conn=lambda x: x["result"].isin(CONNECTED_RESULTS),
        )
        .groupby("date_day")
        .apply(lambda g: pd.Series({
            "denom": (~g["is_vm"]).sum(),
            "connected": g["is_conn"].sum(),
        }))
        .reset_index()
    ) if not outbound_calls.empty else pd.DataFrame()

    if not daily_rate.empty:
        daily_rate["rate"] = daily_rate.apply(
            lambda r: (r["connected"] / r["denom"] * 100) if r["denom"] > 0 else 0, axis=1
        )

        def color_for(v):
            if v >= 40: return "#34d399"
            if v >= 20: return "#6c8cff"
            if v >= 10: return "#fbbf24"
            return "#f87171"

        fig2 = go.Figure()
        fig2.add_bar(
            x=daily_rate["date_day"], y=daily_rate["rate"],
            marker_color=[color_for(v) for v in daily_rate["rate"]],
            text=[f"{v:.0f}%" for v in daily_rate["rate"]], textposition="outside",
            textfont=dict(color="#e6eaf2"),
        )
        fig2.update_layout(
            title=dict(text="% Conexion por dia (sin voicemail)", font=dict(color="#e6eaf2", size=15)),
            height=380,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", range=[0, 110], ticksuffix="%"),
            **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sin llamadas salientes en este periodo.")


# ─────────────────────────────────────────
#  Tags breakdown
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Agrupacion por etiquetas</div>', unsafe_allow_html=True)
tags_df = tag_breakdown(calls_df, tags_catalog)

if tags_df.empty:
    st.info("Sin llamadas etiquetadas en este periodo.")
else:
    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        fig3 = px.pie(
            tags_df, names="tag_name", values="count",
            color="tag_name",
            color_discrete_map=dict(zip(tags_df["tag_name"], tags_df["color"])),
            hole=0.55,
        )
        fig3.update_traces(textinfo="percent+label", textposition="outside",
                           marker=dict(line=dict(color="#161e3d", width=3)))
        fig3.update_layout(
            title=dict(text="Distribucion de etiquetas", font=dict(color="#e6eaf2", size=15)),
            height=380, **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig3, use_container_width=True)
    with col_t2:
        show_tags = tags_df[["tag_name", "count"]].rename(columns={"tag_name": "Etiqueta", "count": "Llamadas"})
        st.markdown(_data_table(show_tags, show_tags.columns.tolist()), unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Ranking por SDR y por numero/cliente
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Ranking por SDR</div>', unsafe_allow_html=True)
sdr_rank = breakdown_by(calls_df, "user_name")
if sdr_rank.empty:
    st.info("Sin datos por SDR en este periodo.")
else:
    show_sdr = sdr_rank.rename(columns={
        "user_name": "SDR", "actividades": "Llamadas", "conectadas": "Conectadas",
        "voicemail": "Voicemail", "tasa_conexion": "Tasa conexion (%)",
        "reuniones_agendadas": "Reuniones agendadas", "duracion_prom_min": "Dur. prom. (min)",
    })
    st.markdown(_data_table(show_sdr, show_sdr.columns.tolist()), unsafe_allow_html=True)

st.markdown('<div class="section-title">Ranking por numero / cliente</div>', unsafe_allow_html=True)
client_rank = breakdown_by(calls_df, "client_name")
if client_rank.empty:
    st.info("Sin datos por numero en este periodo.")
else:
    show_client = client_rank.rename(columns={
        "client_name": "Cliente / Numero", "actividades": "Llamadas", "conectadas": "Conectadas",
        "voicemail": "Voicemail", "tasa_conexion": "Tasa conexion (%)",
        "reuniones_agendadas": "Reuniones agendadas", "duracion_prom_min": "Dur. prom. (min)",
    })
    st.markdown(_data_table(show_client, show_client.columns.tolist()), unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Detail tabs
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Detalle</div>', unsafe_allow_html=True)
tab1, tab2 = st.tabs([
    f"📋 Actividades ({total_activities})",
    f"📅 Reuniones agendadas ({meetings_n})",
])

TAG_NAME_MAP = {t["id"]: t["name"] for t in tags_catalog}

with tab1:
    show = df[[
        "date_local", "user_name", "client_name", "contact_number",
        "type", "direction", "result", "duration_min", "summary", "tags",
    ]].copy()
    show["date_local"] = show["date_local"].dt.strftime("%Y-%m-%d %H:%M")
    show["duration_min"] = show["duration_min"].round(1)
    show["tags"] = show["tags"].apply(lambda ts: ", ".join(TAG_NAME_MAP.get(t, t) for t in ts) if ts else "")
    show.columns = [
        "Fecha/Hora", "SDR", "Cliente/Numero", "Contacto", "Tipo", "Direccion",
        "Resultado", "Duracion (min)", "Resumen", "Etiquetas",
    ]
    st.markdown(_data_table(show.head(500), show.columns.tolist()), unsafe_allow_html=True)
    if len(show) > 500:
        st.caption(f"Mostrando las primeras 500 de {len(show)} actividades. Ajusta los filtros para acotar.")

with tab2:
    meetings_df = df[df["tags"].apply(lambda t: MEETING_TAG in t)]
    if meetings_df.empty:
        st.info("Sin reuniones agendadas en este periodo con los filtros seleccionados.")
    else:
        for _, m in meetings_df.sort_values("date", ascending=False).iterrows():
            date_str = m["date_local"].strftime("%d %b %Y %H:%M")
            with st.expander(f"📅 {m['user_name']} · {m['client_name']} · {date_str}"):
                st.markdown(f"**Contacto:** {m['contact_number']}")
                st.markdown(f"**Duracion:** {fmt_duration(m['duration_min'])}")
                if m.get("summary"):
                    st.markdown("**Resumen**")
                    st.markdown(m["summary"])
                if m.get("recording_url"):
                    st.audio(m["recording_url"])


# Footer
st.divider()
st.caption(
    "🔐 Datos en vivo desde ALLO · Bullseye (SOi Digital) · Cache 15 min · "
    "Tasa de conexion excluye voicemail del numerador y del denominador · "
    "Más reportes se iran agregando a esta pagina."
)
