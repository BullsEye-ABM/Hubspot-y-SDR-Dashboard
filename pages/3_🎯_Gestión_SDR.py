"""
Gestion SDR · Actividad de Llamadas
Bullseye (SOi Digital) · HubSpot API · Cache 15 min
Diseno pro: dark theme, categorias IA, scorecard de coaching, reproductor inline.
"""

from __future__ import annotations

import re
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime

from utils.auth import require_login
from utils.hubspot import (
    list_owners, get_calls, get_contacts, get_companies, count_owned_total,
)
from utils.periods import PERIOD_OPTIONS, get_period_dates, to_ms, to_ms_end


# PORTAL_ID de Bullseye: visible en la URL de HubSpot (ej. app.hubspot.com/contacts/XXXXXXX)
# Para portales EU, el endpoint de grabaciones usa api-eu1 en vez de api-na1.
PORTAL_ID = "25153925"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_recording_bytes(call_id: str):
    """Download audio recording from HubSpot via authenticated proxy.
    Returns (bytes, content_type) or (None, error_msg)."""
    if not call_id:
        return None, "Sin call_id"
    if not PORTAL_ID:
        return None, "PORTAL_ID no configurado en el archivo"
    try:
        token = st.secrets["hubspot"]["private_app_token"]
    except (KeyError, FileNotFoundError):
        return None, "Token no configurado"
    # Portales EU: reemplazar api-na1 por api-eu1 si no funciona
    url = (
        f"https://api-na1.hubspot.com/recording/auth/provider/hublets/v1/"
        f"external-url-retriever/getAuthRecording/portal/{PORTAL_ID}/engagement/{call_id}"
    )
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=45,
            allow_redirects=True,
        )
        if r.status_code == 200 and r.content:
            ct = r.headers.get("Content-Type", "audio/mpeg")
            return r.content, ct
        return None, f"HTTP {r.status_code}"
    except Exception as e:
        return None, str(e)[:120]


# ─────────────────────────────────────────
#  Page config & CSS
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Bullseye · Gestion SDR",
    page_icon="🎯",
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
.cat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 900px) { .cat-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .cat-grid { grid-template-columns: 1fr; } }
.cat-card {
  border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
  background: linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0));
}
.cat-badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: 700; margin-bottom: 8px; }
.cat-name { font-size: 13px; color: var(--text-dim); margin-bottom: 4px; }
.cat-num  { font-size: 26px; font-weight: 700; line-height: 1; }
.cat-ex   { font-size: 11px; color: var(--text-dim); margin-top: 8px; line-height: 1.5; }
.b-win        { background: rgba(52,211,153,.15);  color: var(--green); }
.b-handoff    { background: rgba(76,201,240,.15);  color: #4cc9f0; }
.b-discovery  { background: rgba(167,139,250,.15); color: var(--purple); }
.b-gatekeeper { background: rgba(248,113,113,.15); color: var(--red); }
.b-recovery   { background: rgba(230,57,70,.15);   color: var(--accent); }
.b-objection  { background: rgba(251,191,36,.15);  color: var(--amber); }
.tag {
  display: inline-block; padding: 2px 10px; border-radius: 6px;
  font-size: 11px; font-weight: 600;
}
.tag-win        { background: rgba(52,211,153,.15);  color: var(--green); }
.tag-handoff    { background: rgba(76,201,240,.15);  color: #4cc9f0; }
.tag-discovery  { background: rgba(167,139,250,.15); color: var(--purple); }
.tag-gatekeeper { background: rgba(248,113,113,.15); color: var(--red); }
.tag-recovery   { background: rgba(230,57,70,.15);   color: var(--accent); }
.tag-objection  { background: rgba(251,191,36,.15);  color: var(--amber); }
.scorecard-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.scorecard-table th, .scorecard-table td {
  padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border);
}
.scorecard-table th { color: var(--text-dim); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
.score-bar {
  display: flex; align-items: center; gap: 10px; min-width: 130px;
}
.score-bar .bar {
  height: 6px; border-radius: 4px; background: rgba(255,255,255,.08);
  flex: 1; overflow: hidden; position: relative;
}
.score-bar .bar i {
  position: absolute; top: 0; left: 0; bottom: 0; border-radius: 4px;
}
.score-bar .num { font-weight: 700; min-width: 32px; }
.s9 i { background: var(--green); }
.s7 i { background: #6c8cff; }
.s6 i { background: var(--amber); }
.s5 i { background: var(--red); }
.insight {
  border-left: 3px solid var(--accent); padding: 12px 16px; margin: 10px 0;
  background: rgba(230,57,70,.06); border-radius: 6px;
  font-size: 13.5px; line-height: 1.6; color: var(--text);
}
.insight.warn { border-color: var(--amber); background: rgba(251,191,36,.06); }
.insight.win  { border-color: var(--green); background: rgba(52,211,153,.06); }
.insight strong { color: var(--text); }
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
.dt-wrap { max-height: 420px; overflow-y: auto; border-radius: 12px; }
.listen-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 32px; border-radius: 8px;
  background: rgba(230,57,70,.12); color: var(--accent) !important;
  text-decoration: none !important; transition: all .15s ease;
  font-size: 14px; border: 1px solid rgba(230,57,70,.25);
}
.listen-btn:hover {
  background: var(--accent); color: #fff !important;
  transform: scale(1.08); border-color: var(--accent);
}
[data-testid="stMain"] [data-baseweb="select"] > div,
section.main [data-baseweb="select"] > div {
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
}
[data-testid="stMain"] [data-baseweb="select"] svg,
section.main [data-baseweb="select"] svg { fill: var(--text-dim) !important; }
[data-baseweb="popover"],
[data-baseweb="popover"] *,
[data-baseweb="menu"],
[data-baseweb="menu"] *,
[role="listbox"],
[role="listbox"] * {
  background-color: var(--card) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}
[data-baseweb="popover"] {
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  box-shadow: 0 10px 30px rgba(0,0,0,.5) !important;
}
[data-baseweb="popover"] li:hover,
[data-baseweb="menu"] li:hover,
[role="option"]:hover,
[role="option"][aria-selected="true"] {
  background-color: rgba(230,57,70,.20) !important;
  color: var(--text) !important;
}
[data-testid="stAudio"] audio,
audio {
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
[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
  color: var(--text) !important;
}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
  color: var(--text-dim);
}
.player-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px; margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)


def _data_table(df, columns):
    """Render a DataFrame as a dark-styled HTML table."""
    if df is None or df.empty:
        return '<div class="card"><em style="color:var(--text-dim)">Sin datos.</em></div>'
    headers = "".join(f"<th>{c}</th>" for c in columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{row.get(c, '') if hasattr(row, 'get') else (row[c] if c in row else '')}</td>" for c in columns)
        rows.append(f"<tr>{cells}</tr>")
    return (
        f'<div class="dt-wrap"><table class="dt">'
        f'<thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table></div>'
    )


# ─────────────────────────────────────────
#  Helpers: categorization, scoring
# ─────────────────────────────────────────

CATEGORY_DEFS = [
    # (key, label, badge_class, tag_class, keywords)
    ("cierre", "Cierre", "b-win", "tag-win",
     ["outsourcing oficial", "free trial", "agendamos onboarding", "va a comenzar a externalizar",
      "se cerro", "convirtio", "agendar reunion", "agendo reunion", "compromiso", "cliente oficial"]),
    ("handoff", "Handoff / Reasignacion", "b-handoff", "tag-handoff",
     ["reemplaz", "maternidad", "nueva persona de contacto", "reasignacion", "nuevo contacto"]),
    ("recovery", "Recovery / Follow-up", "b-recovery", "tag-recovery",
     ["no recibio", "no llego", "reenvi", "correo no llego", "reenviar", "verificar"]),
    ("gatekeeper", "Gatekeeper", "b-gatekeeper", "tag-gatekeeper",
     ["secretaria", "recepcionista", "no esta disponible", "no se encuentra disponible",
      "le va a transmitir", "le voy a avisar"]),
    ("objection", "Objecion", "b-objection", "tag-objection",
     ["tiempos de entrega", "rush", "objecion", "queja", "precio", "demasiado caro", "competidor"]),
    ("discovery", "Discovery", "b-discovery", "tag-discovery",
     ["info por correo", "envia info", "mandar email", "informacion", "cotizacion",
      "tarifas", "precios", "mas informacion"]),
]


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).lower()


def categorize(call: dict) -> dict:
    """Return {key, label, badge, tag} for a connected call."""
    text = _strip_html(call.get("summary", "")) + " " + _strip_html(call.get("body", ""))
    for key, label, badge, tag, keywords in CATEGORY_DEFS:
        for kw in keywords:
            if kw in text:
                return {"key": key, "label": label, "badge": badge, "tag": tag}
    return {"key": "discovery", "label": "Discovery", "badge": "b-discovery", "tag": "tag-discovery"}


def score_call(category_key: str, duration_min: float) -> tuple[float, str]:
    """Heuristic score + improvement focus."""
    if category_key == "cierre":
        if duration_min > 3: return 9.0, "Documentar alcance del compromiso por escrito"
        return 8.0, "Cerrar pricing y forecast en la misma llamada"
    if category_key == "handoff":
        if duration_min > 4: return 7.5, "Cuantificar volumen e identificar competidor primario"
        if duration_min > 1.5: return 7.0, "Profundizar en satisfaccion y necesidades nuevas"
        return 5.5, "Llamada corta: explorar mas oportunidades antes de cortar"
    if category_key == "recovery":
        return 6.5, "Validar recepcion multicanal dentro de 24h"
    if category_key == "discovery":
        if duration_min > 5: return 7.5, "Confirmar recepcion multicanal, no solo email"
        if duration_min > 2: return 6.5, "Dar precios completos en llamada, no derivar todo a email"
        return 4.5, "Aplicar 3 preguntas SPIN antes de aceptar 'mandame info'"
    if category_key == "objection":
        return 6.5, "Proponer caso piloto, no solo reenviar PDF/aranceles"
    if category_key == "gatekeeper":
        return 5.5, "Pedir nombre y canal directo del decisor"
    return 6.0, "Profundizar discovery y agendar siguiente paso"


def score_class(s: float) -> str:
    if s >= 8: return "s9"
    if s >= 7: return "s7"
    if s >= 6: return "s6"
    return "s5"


def fmt_duration(mins: float) -> str:
    if not mins: return "–"
    m = int(mins); s = int((mins - m) * 60)
    return f"{m}:{s:02d}"


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

    owners = list_owners()
    if not owners:
        st.error("No se encontraron usuarios en HubSpot.")
        st.stop()

    owner_labels = [f"{o['name']} · ID {o['id']}" for o in owners]
    owner_choice = st.selectbox("Usuario (SDR)", owner_labels, index=0)
    owner = owners[owner_labels.index(owner_choice)]

    st.divider()
    if st.button("🔄 Forzar actualizacion", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("⏱️ Cache: 15 min · Datos en vivo")
    st.caption(f"🕐 Ultima carga: {datetime.now().strftime('%H:%M:%S')}")


# ─────────────────────────────────────────
#  Header
# ─────────────────────────────────────────
st.markdown(f'<div class="brand-header"><div class="brand-left"><div class="brand-logo">BE</div><div><div class="brand-title">Gestion SDR · Actividad de Llamadas</div><div class="brand-sub">{owner["name"]} · Bullseye (SOi Digital)</div></div></div><div class="brand-right"><strong>Dashboard de Coaching</strong><span>Datos al {datetime.now().strftime("%d %b %Y")}</span><br><span>Periodo: {start_date.strftime("%d %b %Y")} → {end_date.strftime("%d %b %Y")}</span><div class="pill">Owner ID {owner["id"]} · Bullseye</div></div></div>', unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Fetch data
# ─────────────────────────────────────────
start_ms = to_ms(start_date)
end_ms = to_ms_end(end_date)

calls = get_calls(owner["id"], start_ms, end_ms)
contacts = get_contacts(owner["id"], start_ms, end_ms)
companies = get_companies(owner["id"], start_ms, end_ms)
total_contacts = count_owned_total("contacts", owner["id"])
total_companies = count_owned_total("companies", owner["id"])

df = pd.DataFrame(calls)
if not df.empty:
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    df["date"] = df["timestamp"].dt.tz_convert("America/Santiago").dt.date
    df["duration_min"] = df["duration_ms"] / 60000

connected = df[df["disposition"] == "Conectado"] if not df.empty else pd.DataFrame()
outbound = df[df["direction"] == "OUTBOUND"] if not df.empty else pd.DataFrame()

# Categorize connected calls
cat_results = []
score_results = []
for _, c in connected.iterrows():
    cat = categorize(c.to_dict())
    s, focus = score_call(cat["key"], c["duration_min"])
    cat_results.append(cat)
    score_results.append({"score": s, "focus": focus})

avg_score = round(sum(s["score"] for s in score_results) / len(score_results), 1) if score_results else 0


# ─────────────────────────────────────────
#  KPIs
# ─────────────────────────────────────────
total_calls = len(df)
total_connected = len(connected)
conn_rate = (total_connected / len(outbound) * 100) if len(outbound) > 0 else 0
avg_duration = connected["duration_min"].mean() if not connected.empty else 0
inbound_count = len(df) - len(outbound) if not df.empty else 0

st.markdown('<div class="section-title">Indicadores clave</div>', unsafe_allow_html=True)
st.markdown(f'<div class="kpi-row"><div class="kpi accent"><div class="kpi-label">Llamadas (filtradas)</div><div class="kpi-value">{total_calls}</div><div class="kpi-sub">Outbound: {len(outbound)} · Inbound real: {inbound_count}</div></div><div class="kpi green"><div class="kpi-label">Conectadas</div><div class="kpi-value">{total_connected}</div><div class="kpi-sub">Hubo conversacion efectiva</div></div><div class="kpi amber"><div class="kpi-label">Tasa de conexion</div><div class="kpi-value">{conn_rate:.1f}%</div><div class="kpi-sub">Conectadas / Outbound</div></div><div class="kpi purple"><div class="kpi-label">Duracion promedio</div><div class="kpi-value">{fmt_duration(avg_duration)}</div><div class="kpi-sub">Llamadas conectadas</div></div><div class="kpi"><div class="kpi-label">Contactos asignados</div><div class="kpi-value">{len(contacts)}</div><div class="kpi-sub">Total historico: {total_contacts}{" · ⚠️ Empresas: 0" if total_companies == 0 else f" · Empresas: {total_companies}"}</div></div><div class="kpi green"><div class="kpi-label">Score promedio</div><div class="kpi-value">{avg_score if avg_score else "–"}<span style="font-size:14px;color:var(--text-dim)">/10</span></div><div class="kpi-sub">Coaching consultivo</div></div></div>', unsafe_allow_html=True)

if df.empty:
    st.info("📭 No hay llamadas en este periodo para el usuario seleccionado.")
    st.stop()


# ─────────────────────────────────────────
#  Charts: temporal
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Actividad temporal</div>', unsafe_allow_html=True)
col_a, col_b = st.columns([2, 1])

PLOT_TEMPLATE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#93a0c2", family="Inter, sans-serif"),
    margin=dict(t=50, b=20, l=20, r=20),
)

with col_a:
    daily = (
        df.assign(
            connected=lambda x: (x["disposition"] == "Conectado").astype(int),
            no_answer=lambda x: (x["disposition"] == "Sin respuesta").astype(int),
            other=lambda x: (~x["disposition"].isin(["Conectado", "Sin respuesta"])).astype(int),
        )
        .groupby("date")[["connected", "no_answer", "other"]].sum().reset_index()
        .sort_values("date")
    )
    fig = go.Figure()
    fig.add_bar(x=daily["date"], y=daily["connected"], name="Conectadas", marker_color="#34d399")
    fig.add_bar(x=daily["date"], y=daily["no_answer"], name="Sin respuesta", marker_color="#fbbf24")
    fig.add_bar(x=daily["date"], y=daily["other"], name="Otros/Failed", marker_color="#f87171")
    fig.update_layout(
        title=dict(text="Llamadas por dia", font=dict(color="#e6eaf2", size=15)),
        barmode="stack", height=380,
        legend=dict(orientation="h", y=-0.2),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        **PLOT_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    weekly = (
        df.assign(week=df["timestamp"].dt.tz_convert("America/Santiago").dt.strftime("W%V"))
        .groupby("week").size().reset_index(name="calls").sort_values("week")
    )
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=weekly["week"], y=weekly["calls"], mode="lines+markers+text",
        line=dict(color="#e63946", width=3), fill="tozeroy",
        fillcolor="rgba(230,57,70,0.18)",
        marker=dict(size=10, color="#e63946", line=dict(color="#fff", width=2)),
        text=weekly["calls"], textposition="top center",
        textfont=dict(color="#e6eaf2", size=12),
    ))
    fig2.update_layout(
        title=dict(text="Por semana ISO", font=dict(color="#e6eaf2", size=15)),
        height=380, showlegend=False,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        **PLOT_TEMPLATE,
    )
    st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────
#  Charts: outcomes
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Resultados de las llamadas</div>', unsafe_allow_html=True)
col_d, col_e = st.columns(2)

with col_d:
    disp = df["disposition"].value_counts().reset_index()
    disp.columns = ["disposition", "count"]
    color_map = {
        "Conectado": "#34d399", "Sin respuesta": "#fbbf24",
        "Sin disposicion": "#f87171", "Ocupado": "#a78bfa",
        "Dejo mensaje en directo": "#4cc9f0", "Dejo mensaje de voz": "#4cc9f0",
        "Numero incorrecto": "#93a0c2",
    }
    fig3 = px.pie(
        disp, names="disposition", values="count",
        color="disposition", color_discrete_map=color_map, hole=0.55,
    )
    fig3.update_traces(textinfo="percent+label", textposition="outside",
                       marker=dict(line=dict(color="#161e3d", width=3)))
    fig3.update_layout(
        title=dict(text="Distribucion por status", font=dict(color="#e6eaf2", size=15)),
        height=400, **PLOT_TEMPLATE,
    )
    st.plotly_chart(fig3, use_container_width=True)

with col_e:
    daily_rate = (
        df[df["direction"] == "OUTBOUND"]
        .assign(is_conn=lambda x: (x["disposition"] == "Conectado").astype(int))
        .groupby("date").agg(total=("is_conn", "size"), connected=("is_conn", "sum")).reset_index()
    )
    if not daily_rate.empty:
        daily_rate["rate"] = daily_rate["connected"] / daily_rate["total"] * 100

        def color_for(v):
            if v >= 60: return "#34d399"
            if v >= 30: return "#6c8cff"
            if v >= 15: return "#fbbf24"
            return "#f87171"

        fig4 = go.Figure()
        fig4.add_bar(
            x=daily_rate["date"], y=daily_rate["rate"],
            marker_color=[color_for(v) for v in daily_rate["rate"]],
            text=[f"{v:.0f}%" for v in daily_rate["rate"]], textposition="outside",
            textfont=dict(color="#e6eaf2"),
        )
        fig4.update_layout(
            title=dict(text="% Conexion por dia", font=dict(color="#e6eaf2", size=15)),
            height=400,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", range=[0, 110], ticksuffix="%"),
            **PLOT_TEMPLATE,
        )
        st.plotly_chart(fig4, use_container_width=True)


# ─────────────────────────────────────────
#  Categories of prospect response
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Categorias de respuesta del prospecto</div>', unsafe_allow_html=True)
st.caption(f"Analisis automatico sobre las {len(connected)} conversaciones efectivas, segun transcripciones IA.")

if connected.empty:
    st.info("Sin conversaciones conectadas en este periodo.")
else:
    cat_buckets: dict[str, dict] = {}
    for (_, c), cat in zip(connected.iterrows(), cat_results):
        bucket = cat_buckets.setdefault(cat["key"], {"label": cat["label"], "badge": cat["badge"], "calls": []})
        title = c.get("title", "").replace("Llamada con ", "")
        bucket["calls"].append(title or "Sin titulo")

    parts = ['<div class="cat-grid">']
    for key, label, badge, tag, _ in CATEGORY_DEFS:
        bucket = cat_buckets.get(key)
        if not bucket:
            continue
        examples = " · ".join(bucket["calls"][:3])
        if len(bucket["calls"]) > 3:
            examples += f" · +{len(bucket['calls']) - 3}"
        parts.append(f'<div class="cat-card"><span class="cat-badge {badge}">{label.split(" /")[0].upper()}</span><div class="cat-name">{label}</div><div class="cat-num">{len(bucket["calls"])}</div><div class="cat-ex">{examples}</div></div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Coaching scorecard
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Scorecard de coaching · Venta consultiva</div>', unsafe_allow_html=True)

if connected.empty:
    st.info("Sin llamadas para evaluar en este periodo.")
else:
    rows_parts = []
    pairs = sorted(
        zip(connected.to_dict("records"), cat_results, score_results),
        key=lambda x: x[2]["score"], reverse=True,
    )
    for c, cat, s in pairs:
        ts = c["timestamp"]
        date_str = ts.tz_convert("America/Santiago").strftime("%d-%b") if hasattr(ts, "tz_convert") else "—"
        title = (c.get("title") or "").replace("Llamada con ", "") or "Sin titulo"
        dur = fmt_duration(c.get("duration_min", 0))
        s_cls = score_class(s["score"])
        bar_pct = int(s["score"] * 10)
        call_id = c.get("id", "")
        audio_btn = (f'<a href="https://app.hubspot.com/calls/{PORTAL_ID}/review/{call_id}" target="_blank" rel="noopener" class="listen-btn" title="Escuchar grabacion en HubSpot">🎧</a>') if call_id and PORTAL_ID else ""
        rows_parts.append(f'<tr><td>{date_str}</td><td>{title}</td><td><span class="tag {cat["tag"]}">{cat["label"].split(" /")[0]}</span></td><td>{dur}</td><td><div class="score-bar {s_cls}"><div class="bar"><i style="width:{bar_pct}%"></i></div><span class="num">{s["score"]}</span></div></td><td>{s["focus"]}</td><td style="text-align:center">{audio_btn}</td></tr>')
    table_html = (
        '<div class="card">'
        '<div style="font-size:15px;font-weight:600;margin-bottom:4px;">Evaluacion llamada por llamada</div>'
        f'<div style="font-size:12px;color:var(--text-dim);margin-bottom:14px;">Escala 1–10 sobre {len(connected)} conexiones efectivas. Heuristica por duracion + categoria detectada.</div>'
        '<table class="scorecard-table">'
        '<thead><tr><th>Fecha</th><th>Cliente</th><th>Tipo</th><th>Duracion</th><th>Score</th><th>Foco de mejora</th><th style="text-align:center">HubSpot</th></tr></thead>'
        f'<tbody>{"".join(rows_parts)}</tbody>'
        '</table>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # ─────────────────────────────────────────
    #  Inline audio player
    # ─────────────────────────────────────────
    st.markdown('<div class="section-title">🎧 Reproductor de grabaciones</div>', unsafe_allow_html=True)

    player_options = []
    player_lookup = {}
    for c, cat, s in pairs:
        title = (c.get("title") or "Sin titulo").replace("Llamada con ", "")
        ts = c["timestamp"]
        date_str = ts.tz_convert("America/Santiago").strftime("%d %b %H:%M") if hasattr(ts, "tz_convert") else "—"
        dur_str = fmt_duration(c.get("duration_min", 0))
        opt = f"{title} · {date_str} · {dur_str} · score {s['score']}/10"
        player_options.append(opt)
        player_lookup[opt] = c

    if player_options:
        with st.container():
            st.markdown('<div class="player-card"><div style="font-size:15px;font-weight:600;margin-bottom:4px;">Selecciona una llamada</div><div style="font-size:12px;color:var(--text-dim);margin-bottom:14px;">Reproduce la grabacion + transcripcion sin salir del dashboard.</div>', unsafe_allow_html=True)
            selected_call = st.selectbox(
                "Llamada a reproducir",
                player_options,
                key="audio_player_select",
                label_visibility="collapsed",
            )
            if selected_call:
                call = player_lookup[selected_call]
                call_id = call.get("id", "")
                with st.spinner("Cargando grabacion…"):
                    audio_data, info = fetch_recording_bytes(call_id)

                if audio_data:
                    st.audio(audio_data, format=info if "audio" in info else "audio/mpeg")
                    col_a2, col_b2 = st.columns([1, 1])
                    with col_a2:
                        if call.get("summary"):
                            with st.expander("📝 Resumen IA"):
                                st.markdown(call["summary"], unsafe_allow_html=True)
                    with col_b2:
                        if call.get("body"):
                            with st.expander("✏️ Notas internas"):
                                st.markdown(call["body"], unsafe_allow_html=True)
                else:
                    st.warning(
                        f"⚠️ No se pudo cargar el audio ({info}). "
                        f"Asegurate de configurar PORTAL_ID en el archivo y que el token "
                        f"tenga el scope `crm.objects.calls.recording.read`. "
                        f"Click 🎧 en la fila para abrir en HubSpot."
                    )
            st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Insights & alertas
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Insights y alertas</div>', unsafe_allow_html=True)

insights = []

if score_results:
    best_idx = max(range(len(score_results)), key=lambda i: score_results[i]["score"])
    best_call = connected.iloc[best_idx]
    if score_results[best_idx]["score"] >= 8:
        insights.append(("win",
            f"🏆 <strong>Mejor llamada del periodo:</strong> "
            f"{best_call['title'].replace('Llamada con ', '')} "
            f"({score_results[best_idx]['score']}/10). Categoria: {cat_results[best_idx]['label']}."))

discovery_count = sum(1 for c in cat_results if c["key"] == "discovery")
if discovery_count >= 2 and len(connected) > 0:
    pct = discovery_count / len(connected) * 100
    if pct >= 30:
        insights.append(("warn",
            f"⚠️ <strong>Email-dependence:</strong> {discovery_count} de {len(connected)} conversaciones "
            f"({pct:.0f}%) terminaron derivando a correo. Aplicar SPIN antes de aceptar 'mandame info'."))

no_answer = df[df["disposition"] == "Sin respuesta"]
if len(no_answer) >= 3:
    by_title = no_answer["title"].value_counts()
    repeats = by_title[by_title >= 3]
    if not repeats.empty:
        names = ", ".join(repeats.index[:3].tolist())
        insights.append(("warn",
            f"⚠️ <strong>Marcado repetitivo sin respuesta:</strong> {names}. "
            f"Variar canal: voz → WhatsApp → email personalizado → reintento en otro horario."))

failed = df[df["disposition"] == "Sin disposicion"]
if len(failed) >= 4:
    insights.append(("warn",
        f"🔧 <strong>Alerta tecnica:</strong> {len(failed)} llamadas sin disposicion/failed en el periodo. "
        f"Revisar problemas de marcado o integracion SIP con TI."))

if conn_rate >= 35:
    insights.append(("win",
        f"📈 <strong>Excelente tasa de conexion:</strong> {conn_rate:.1f}% (benchmark 25-30%)."))
elif conn_rate < 20 and len(outbound) >= 5:
    insights.append(("warn",
        f"📉 <strong>Tasa de conexion baja:</strong> {conn_rate:.1f}%. "
        f"Revisar horarios, calidad de listas o canal preferido del prospecto."))

if total_companies == 0 and total_contacts > 0:
    insights.append(("",
        f"📋 <strong>Asignacion de empresas:</strong> {total_contacts} contactos asignados pero 0 empresas. "
        f"Verificar workflow de propiedad para sincronizar contacto → empresa."))

if not insights:
    st.caption("Sin alertas relevantes para este periodo.")
else:
    for kind, html in insights:
        cls = f"insight {kind}".strip()
        st.markdown(f'<div class="{cls}">{html}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Detail tabs
# ─────────────────────────────────────────
st.markdown('<div class="section-title">Detalle</div>', unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs([
    f"📞 Llamadas ({total_calls})",
    f"📝 Conectadas con notas ({len(connected)})",
    "👥 Contactos & Empresas",
])

with tab1:
    show = df[["timestamp", "title", "disposition", "direction", "duration_min", "status"]].copy()
    show["timestamp"] = show["timestamp"].dt.tz_convert("America/Santiago").dt.strftime("%Y-%m-%d %H:%M")
    show["duration_min"] = show["duration_min"].round(1)
    show.columns = ["Fecha/Hora", "Titulo", "Disposicion", "Direccion", "Duracion (min)", "Status"]
    st.markdown(_data_table(show, show.columns.tolist()), unsafe_allow_html=True)

with tab2:
    if connected.empty:
        st.info("Sin llamadas conectadas en este periodo.")
    else:
        for _, c in connected.iterrows():
            with st.expander(
                f"📞 {c['title']} · "
                f"{c['timestamp'].tz_convert('America/Santiago').strftime('%d %b %Y %H:%M')} · "
                f"{int(c['duration_min'])} min"
            ):
                if c["summary"]:
                    st.markdown("**Resumen IA**")
                    st.markdown(c["summary"], unsafe_allow_html=True)
                if c["body"]:
                    st.markdown("**Notas internas**")
                    st.markdown(c["body"], unsafe_allow_html=True)
                if not c["summary"] and not c["body"]:
                    st.caption("Sin resumen ni notas registradas.")

with tab3:
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown(f"**Contactos creados en el periodo:** {len(contacts)}")
        if contacts:
            df_c = pd.DataFrame(contacts)
            keep = [k for k in ["firstname", "lastname", "email", "lifecyclestage", "createdate"] if k in df_c.columns]
            st.markdown(_data_table(df_c[keep], keep), unsafe_allow_html=True)
        else:
            st.caption("Sin contactos en el rango.")
    with cc2:
        st.markdown(f"**Empresas creadas en el periodo:** {len(companies)}")
        if companies:
            df_co = pd.DataFrame(companies)
            keep = [k for k in ["name", "domain", "createdate"] if k in df_co.columns]
            st.markdown(_data_table(df_co[keep], keep), unsafe_allow_html=True)
        else:
            st.caption("Sin empresas asignadas en el rango.")


# Footer
st.divider()
st.caption(
    "🔐 Datos en vivo desde HubSpot · Bullseye (SOi Digital) · "
    "Cache 15 min · Filtra automaticamente llamadas 2FA · "
    "Categorias y scorecard generados por heuristica sobre transcripciones."
)
