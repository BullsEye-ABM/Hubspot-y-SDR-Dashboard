"""
Gestion SDR - Actividad de llamadas por SDR
Bullseye (SOi Digital) - HubSpot API + Cache 15 min
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

from utils.auth import require_login
from utils.hubspot import (
    list_owners, get_calls, get_contacts, get_companies, count_owned_total,
)
from utils.periods import PERIOD_OPTIONS, get_period_dates, to_ms, to_ms_end

# -----------------------------------------
#  Page config & styling
# -----------------------------------------
st.set_page_config(
    page_title="Bullseye - Gestion SDR",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_login()

st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stMetricValue"] { font-size: 2rem; }
[data-testid="stMetricLabel"] { font-size: .85rem; text-transform: uppercase; letter-spacing: 1px; color: #93a0c2; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] { padding: 8px 16px; }
hr { margin: 1.2rem 0; }
.brand-header {
  display:flex;align-items:center;gap:14px;
  border-bottom:1px solid #243056;padding-bottom:14px;margin-bottom:18px;
}
.brand-logo {
  width:42px;height:42px;border-radius:10px;
  background:linear-gradient(135deg,#e63946,#f4a261);
  display:flex;align-items:center;justify-content:center;
  font-weight:800;color:#fff;font-size:18px;
}
.tag {display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;}
.tag-good {background:rgba(52,211,153,.12);color:#34d399;}
.tag-warn {background:rgba(251,191,36,.14);color:#fbbf24;}
.tag-bad {background:rgba(248,113,113,.12);color:#f87171;}
</style>
""", unsafe_allow_html=True)


# -----------------------------------------
#  Sidebar filters
# -----------------------------------------
with st.sidebar:
    st.markdown("### Filtros")

    # Periodo
    period = st.selectbox(
        "Periodo",
        PERIOD_OPTIONS,
        index=2,  # "Este mes" por defecto
        help="Cambia el rango temporal del informe completo",
    )
    start_date, end_date = get_period_dates(period)
    st.caption(
        f"📅 {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}"
    )

    st.divider()

    # Owner
    owners = list_owners()
    if not owners:
        st.error("No se encontraron usuarios en HubSpot.")
        st.stop()

    owner_labels = [f"{o['name']} · ID {o['id']}" for o in owners]
    owner_choice = st.selectbox("Usuario (SDR)", owner_labels, index=0)
    owner = owners[owner_labels.index(owner_choice)]

    st.divider()

    # Refresh
    if st.button("Forzar actualizacion", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption("Cache: 15 min · Datos en vivo desde HubSpot.")
    st.caption(f"Ultima carga: {datetime.now().strftime('%H:%M:%S')}")


# -----------------------------------------
#  Header
# -----------------------------------------
st.markdown(f"""
<div class="brand-header">
  <div class="brand-logo">BE</div>
  <div>
    <h1 style="margin:0;font-size:24px">Gestion SDR · Actividad de Llamadas</h1>
    <p style="margin:0;color:#93a0c2;font-size:13px">
      <strong>{owner['name']}</strong> · Bullseye (SOi Digital)
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

st.caption(
    f"Periodo: **{period}** · {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}"
)


# -----------------------------------------
#  Fetch data
# -----------------------------------------
start_ms = to_ms(start_date)
end_ms = to_ms_end(end_date)

calls = get_calls(owner["id"], start_ms, end_ms)
contacts = get_contacts(owner["id"], start_ms, end_ms)
companies = get_companies(owner["id"], start_ms, end_ms)
total_contacts = count_owned_total("contacts", owner["id"])
total_companies = count_owned_total("companies", owner["id"])


# -----------------------------------------
#  KPIs
# -----------------------------------------
df_calls = pd.DataFrame(calls)
if not df_calls.empty:
    df_calls["timestamp"] = pd.to_datetime(df_calls["timestamp"], errors="coerce", utc=True)
    df_calls = df_calls.dropna(subset=["timestamp"])
    df_calls["date"] = df_calls["timestamp"].dt.tz_convert("America/Santiago").dt.date
    df_calls["week"] = df_calls["timestamp"].dt.isocalendar().week
    df_calls["duration_min"] = df_calls["duration_ms"] / 60000

connected = df_calls[df_calls["disposition"] == "Conectado"] if not df_calls.empty else pd.DataFrame()
outbound = df_calls[df_calls["direction"] == "OUTBOUND"] if not df_calls.empty else pd.DataFrame()

total_calls = len(df_calls)
total_connected = len(connected)
conn_rate = (total_connected / len(outbound) * 100) if len(outbound) > 0 else 0
avg_duration = connected["duration_min"].mean() if not connected.empty else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Llamadas", f"{total_calls}", help="2FA filtrado automaticamente")
c2.metric("Conectadas", f"{total_connected}")
c3.metric("Tasa conexion", f"{conn_rate:.1f}%", help="Conectadas / Outbound")
c4.metric(
    "Duracion promedio",
    f"{int(avg_duration)}:{int((avg_duration%1)*60):02d}" if avg_duration else "-",
    help="Sobre llamadas conectadas",
)
c5.metric("Contactos (periodo)", f"{len(contacts)}", help=f"Total asignados: {total_contacts}")
c6.metric("Empresas (periodo)", f"{len(companies)}", help=f"Total asignadas: {total_companies}")

st.divider()

if df_calls.empty:
    st.info("No hay llamadas en este periodo para el usuario seleccionado.")
    st.stop()


# -----------------------------------------
#  Charts: Activity timeline
# -----------------------------------------
st.subheader("Actividad temporal")

col_a, col_b = st.columns([2, 1])

with col_a:
    daily = (
        df_calls.assign(
            connected=lambda x: (x["disposition"] == "Conectado").astype(int),
            no_answer=lambda x: (x["disposition"] == "Sin respuesta").astype(int),
            other=lambda x: (~x["disposition"].isin(["Conectado", "Sin respuesta"])).astype(int),
        )
        .groupby("date")[["connected", "no_answer", "other"]]
        .sum()
        .reset_index()
    )
    fig = go.Figure()
    fig.add_bar(x=daily["date"], y=daily["connected"], name="Conectadas", marker_color="#34d399")
    fig.add_bar(x=daily["date"], y=daily["no_answer"], name="Sin respuesta", marker_color="#fbbf24")
    fig.add_bar(x=daily["date"], y=daily["other"], name="Otros/Failed", marker_color="#f87171")
    fig.update_layout(
        barmode="stack",
        title="Llamadas por dia",
        height=380,
        margin=dict(t=50, b=20, l=20, r=20),
        legend=dict(orientation="h", y=-0.2),
        xaxis_title=None,
        yaxis_title="Llamadas",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    weekly = (
        df_calls.assign(week=df_calls["timestamp"].dt.tz_convert("America/Santiago").dt.strftime("W%V"))
        .groupby("week")
        .size()
        .reset_index(name="calls")
        .sort_values("week")
    )
    fig2 = px.area(
        weekly, x="week", y="calls",
        title="Volumen por semana ISO",
        markers=True,
    )
    fig2.update_traces(
        line_color="#e63946",
        fillcolor="rgba(230,57,70,0.15)",
        marker=dict(size=10, color="#e63946"),
    )
    fig2.update_layout(
        height=380,
        margin=dict(t=50, b=20, l=20, r=20),
        xaxis_title=None,
        yaxis_title="Llamadas",
    )
    st.plotly_chart(fig2, use_container_width=True)


# -----------------------------------------
#  Charts: Outcomes
# -----------------------------------------
st.subheader("Resultados de llamadas")

col_d, col_e = st.columns([1, 1])

with col_d:
    disp = df_calls["disposition"].value_counts().reset_index()
    disp.columns = ["disposition", "count"]
    color_map = {
        "Conectado": "#34d399",
        "Sin respuesta": "#fbbf24",
        "Sin disposicion": "#f87171",
        "Ocupado": "#a78bfa",
        "Dejo mensaje en directo": "#4cc9f0",
        "Dejo mensaje de voz": "#4cc9f0",
        "Numero incorrecto": "#93a0c2",
    }
    fig3 = px.pie(
        disp, names="disposition", values="count",
        title="Distribucion por status",
        color="disposition",
        color_discrete_map=color_map,
        hole=0.55,
    )
    fig3.update_traces(textinfo="percent+label", textposition="outside")
    fig3.update_layout(height=400, margin=dict(t=50, b=20, l=20, r=20))
    st.plotly_chart(fig3, use_container_width=True)

with col_e:
    daily_rate = (
        df_calls[df_calls["direction"] == "OUTBOUND"]
        .assign(is_conn=lambda x: (x["disposition"] == "Conectado").astype(int))
        .groupby("date")
        .agg(total=("is_conn", "size"), connected=("is_conn", "sum"))
        .reset_index()
    )
    if not daily_rate.empty:
        daily_rate["rate"] = daily_rate["connected"] / daily_rate["total"] * 100
        fig4 = px.bar(
            daily_rate, x="date", y="rate",
            title="% Conexion por dia",
            color="rate",
            color_continuous_scale=[(0, "#f87171"), (0.5, "#fbbf24"), (1, "#34d399")],
            range_color=(0, 100),
        )
        fig4.update_layout(
            height=400,
            margin=dict(t=50, b=20, l=20, r=20),
            xaxis_title=None,
            yaxis_title="% Conexion",
            yaxis=dict(range=[0, 100], ticksuffix="%"),
            coloraxis_showscale=False,
        )
        fig4.update_traces(texttemplate="%{y:.0f}%", textposition="outside")
        st.plotly_chart(fig4, use_container_width=True)


# -----------------------------------------
#  Tabs: Detail tables
# -----------------------------------------
st.subheader("Detalle")

tab_calls, tab_summaries, tab_contacts = st.tabs([
    f"Llamadas ({total_calls})",
    f"Conectadas con notas ({len(connected)})",
    f"Contactos & Empresas",
])

with tab_calls:
    show = df_calls[[
        "timestamp", "title", "disposition", "direction",
        "duration_min", "status",
    ]].copy()
    show["timestamp"] = show["timestamp"].dt.tz_convert("America/Santiago").dt.strftime("%Y-%m-%d %H:%M")
    show["duration_min"] = show["duration_min"].round(1)
    show.columns = ["Fecha/Hora", "Titulo", "Disposicion", "Direccion", "Duracion (min)", "Status"]
    st.dataframe(show, use_container_width=True, hide_index=True, height=400)

with tab_summaries:
    if connected.empty:
        st.info("Sin llamadas conectadas en este periodo.")
    else:
        for _, c in connected.iterrows():
            with st.expander(f"📞 {c['title']} · {c['timestamp'].strftime('%d %b %Y %H:%M')} · {int(c['duration_min'])} min"):
                if c["summary"]:
                    st.markdown("**Resumen IA**")
                    st.markdown(c["summary"], unsafe_allow_html=True)
                if c["body"]:
                    st.markdown("**Notas internas**")
                    st.markdown(c["body"], unsafe_allow_html=True)
                if not c["summary"] and not c["body"]:
                    st.caption("Sin resumen ni notas registradas.")

with tab_contacts:
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown(f"**Contactos creados en el periodo:** {len(contacts)}")
        if contacts:
            df_contacts = pd.DataFrame(contacts)
            keep = [c for c in ["firstname", "lastname", "email", "lifecyclestage", "createdate"] if c in df_contacts.columns]
            st.dataframe(df_contacts[keep], use_container_width=True, hide_index=True, height=320)
        else:
            st.caption("Sin contactos en el rango.")
    with cc2:
        st.markdown(f"**Empresas creadas en el periodo:** {len(companies)}")
        if companies:
            df_comp = pd.DataFrame(companies)
            keep = [c for c in ["name", "domain", "createdate"] if c in df_comp.columns]
            st.dataframe(df_comp[keep], use_container_width=True, hide_index=True, height=320)
        else:
            st.caption("Sin empresas asignadas en el rango.")


# -----------------------------------------
#  Footer
# -----------------------------------------
st.divider()
st.caption(
    "Datos en vivo desde HubSpot · Bullseye (SOi Digital) · "
    "Cache 15 min · Filtra automaticamente llamadas 2FA."
)
