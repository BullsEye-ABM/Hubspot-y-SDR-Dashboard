"""
Ventas - Directorio Comercial & Funnel de Negocios
Pipeline ABM y Consultorias - HubSpot CRM + analisis de transcripciones DIIO
"""

from __future__ import annotations

import re
from datetime import datetime, date, timezone, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from utils.auth import require_login
from utils.hubspot import get_pipelines, get_deals_by_pipeline, get_deal_calls, list_owners
from utils.periods import PERIOD_OPTIONS, get_period_dates

# ─────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Bullseye · Ventas",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_login()

st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
hr { margin: 1rem 0; }
.kpi-card {
  border-radius:12px; padding:18px 20px; height:100%;
}
.stage-badge {
  display:inline-block; padding:2px 10px; border-radius:12px;
  font-size:11px; font-weight:700; letter-spacing:.04em;
}
.score-hot  { color:#15803d; font-weight:800; }
.score-warm { color:#b45309; font-weight:800; }
.score-cold { color:#b91c1c; font-weight:800; }
.signal-pos { background:rgba(52,211,153,.12); color:#15803d;
              padding:1px 7px; border-radius:8px; font-size:11px; margin:1px; display:inline-block; }
.signal-neg { background:rgba(248,113,113,.12); color:#b91c1c;
              padding:1px 7px; border-radius:8px; font-size:11px; margin:1px; display:inline-block; }
.signal-urg { background:rgba(251,191,36,.14); color:#b45309;
              padding:1px 7px; border-radius:8px; font-size:11px; margin:1px; display:inline-block; }

.kpi-html-card {
  cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease;
}
.kpi-html-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.12);
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Scoring: analisis de transcripciones
# ─────────────────────────────────────────

POSITIVE_KW = [
    "firmar", "contrato", "aprobado", "confirmado", "acordamos",
    "siguiente paso", "avanzar", "propuesta aceptada", "cuando empezamos",
    "kick off", "kickoff", "listo para", "muy interesado",
    "comprometidos", "cerramos", "procedemos", "les interesa",
    "quieren avanzar", "orden de compra", "purchase order",
    "carta de intencion", "propuesta aprobada", "aprobaron",
    "interesado", "le interesa", "quiere proceder", "gustó",
    "le gustó", "le gusto", "avanzamos", "seguimos",
]

NEGATIVE_KW = [
    "no está listo", "no estan listos", "están evaluando",
    "sin presupuesto", "no tienen presupuesto", "no respondio",
    "postergamos", "cancelar", "cancelaron", "otro proveedor",
    "competencia", "lo están pensando", "falta de recursos",
    "no hay presupuesto", "congelado", "en pausa", "pausado",
    "no tiene claridad", "no por ahora", "no es el momento",
    "no recibio", "no recibió", "no le llego", "no llego",
]

URGENCY_KW = [
    "urgente", "fines de mes", "fin de mes", "necesitamos para",
    "deadline", "fecha limite", "antes de", "lo antes posible",
    "para esta semana", "para este mes", "cuanto antes",
    "hoy mismo", "inmediatamente", "para mañana",
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").lower()


def _analyze_signals(calls: list[dict]) -> dict:
    full_text = " ".join(
        _strip_html(c.get("summary", "")) + " " + _strip_html(c.get("body", ""))
        for c in calls
    )
    return {
        "positive": [kw for kw in POSITIVE_KW if kw in full_text],
        "negative": [kw for kw in NEGATIVE_KW if kw in full_text],
        "urgency":  [kw for kw in URGENCY_KW  if kw in full_text],
        "has_text": bool(full_text.strip()),
        "call_count": len(calls),
    }


def _score_deal(stage_prob: float, signals: dict,
                days_since_activity: int, days_to_close: int | None) -> dict:
    """Score a deal 0-100 based on stage, signals, recency and close date."""

    # Stage contribution: 0-35 pts
    stage_pts = stage_prob * 35

    # Transcript signals: -25 to +30 pts
    pos_pts  = min(len(signals["positive"]) * 7, 25)
    neg_pts  = min(len(signals["negative"]) * 9, 25)
    urg_pts  = min(len(signals["urgency"])  * 5, 10)
    # Small bonus for having any call data
    data_bonus = 5 if signals["has_text"] else 0
    trans_pts = pos_pts - neg_pts + urg_pts + data_bonus

    # Recency: 0-20 pts
    if days_since_activity <= 2:
        rec_pts = 20
    elif days_since_activity <= 7:
        rec_pts = 14
    elif days_since_activity <= 14:
        rec_pts = 7
    elif days_since_activity <= 30:
        rec_pts = 3
    else:
        rec_pts = 0

    # Close date: -10 to +15 pts
    close_pts = 0
    if days_to_close is not None:
        if 0 <= days_to_close <= 7:
            close_pts = 15
        elif days_to_close <= 14:
            close_pts = 10
        elif days_to_close <= 30:
            close_pts = 5
        elif days_to_close < 0:
            close_pts = -10  # vencido

    score = stage_pts + trans_pts + rec_pts + close_pts
    score = max(0, min(100, round(score)))

    level = "hot" if score >= 65 else "warm" if score >= 35 else "cold"
    return {"score": score, "level": level}


# ─────────────────────────────────────────
#  Fetch pipelines + sidebar
# ─────────────────────────────────────────
pipelines, pipelines_error = get_pipelines()

with st.sidebar:
    st.markdown("### Filtros")

    if pipelines_error:
        # Token sin scope de deals — permitir ingresar pipeline ID manualmente
        st.warning(
            "El token de HubSpot no tiene permisos para leer pipelines.\n\n"
            "**Scopes necesarios:**\n"
            "- `crm.objects.deals.read`\n"
            "- `crm.schemas.deals.read`\n\n"
            "Mientras tanto, ingresá el Pipeline ID manualmente:",
            icon="⚠️",
        )
        manual_pipeline_id = st.text_input(
            "Pipeline ID",
            value="637168513",
            help="Encontralo en HubSpot → CRM → Deals → Acciones → Editar pipeline → URL",
        )
        pipeline_id        = manual_pipeline_id.strip()
        pipeline_label     = f"Pipeline {pipeline_id}"
        stages_raw         = []
        stage_id_to_label  = {}
        stage_id_to_prob   = {}
        stage_id_to_order  = {}
        CLOSED_STAGE_IDS   = set()
    else:
        pipeline_labels = [p.get("label", p["id"]) for p in pipelines]
        pipeline_map    = {p.get("label", p["id"]): p for p in pipelines}

        default_pipe = next(
            (lbl for lbl in pipeline_labels
             if any(kw in lbl.lower() for kw in ["abm", "consultor", "bullseye"])),
            pipeline_labels[0],
        )
        pipeline_label = st.selectbox("Pipeline", pipeline_labels,
                                      index=pipeline_labels.index(default_pipe))
        pipeline       = pipeline_map[pipeline_label]
        pipeline_id    = pipeline["id"]
        stages_raw     = sorted(pipeline.get("stages", []), key=lambda s: s.get("displayOrder", 0))
        stage_id_to_label = {s["id"]: s["label"] for s in stages_raw}
        stage_id_to_prob  = {s["id"]: float(s.get("metadata", {}).get("probability", 0)) for s in stages_raw}
        stage_id_to_order = {s["id"]: i for i, s in enumerate(stages_raw)}

        CLOSED_STAGE_IDS = {
            s["id"] for s in stages_raw
            if float(s.get("metadata", {}).get("probability", 0)) >= 1.0
            or any(kw in s.get("label", "").lower()
                   for kw in ["cerrado", "ganado", "perdido", "won", "lost", "closed"])
        }

    show_closed = st.checkbox("Mostrar negocios cerrados", value=False)

    st.divider()

    # Periodo (filtro por fecha creacion)
    period = st.selectbox("Periodo (creacion)", ["Todos"] + PERIOD_OPTIONS, index=0)
    if period != "Todos":
        p_start, p_end = get_period_dates(period)
    else:
        p_start, p_end = None, None

    # Owner filter
    owners_list  = list_owners()
    owner_name_to_id = {o["name"]: o["id"] for o in owners_list}
    owner_options    = ["Todos"] + [o["name"] for o in owners_list]
    selected_owner   = st.selectbox("Owner / SDR", owner_options, index=0)


# ─────────────────────────────────────────
#  Fetch & process deals
# ─────────────────────────────────────────
deals_raw = get_deals_by_pipeline(pipeline_id)
now_utc   = datetime.now(timezone.utc)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


rows = []
for d in deals_raw:
    p          = d.get("properties", {})
    stage_id   = p.get("dealstage", "")
    stage_lbl  = stage_id_to_label.get(stage_id, stage_id)
    stage_prob = (stage_id_to_prob.get(stage_id)
                  if stage_id_to_prob
                  else float(p.get("hs_deal_stage_probability") or 0))
    stage_ord  = stage_id_to_order.get(stage_id, 0)

    create_dt  = _parse_dt(p.get("createdate"))
    close_dt   = _parse_dt(p.get("closedate"))
    last_dt    = _parse_dt(p.get("notes_last_contacted") or p.get("hs_lastmodifieddate"))

    days_created  = (now_utc - create_dt).days if create_dt else 999
    days_activity = (now_utc - last_dt).days   if last_dt   else 999
    days_to_close = (close_dt - now_utc).days  if close_dt  else None

    amount = 0.0
    try:
        amount = float(p.get("amount") or 0)
    except Exception:
        pass

    owner_id   = p.get("hubspot_owner_id") or ""
    owner_name = next((o["name"] for o in owners_list if o["id"] == owner_id), owner_id or "Sin asignar")

    rows.append({
        "id":            d["id"],
        "deal_name":     p.get("dealname") or "Sin nombre",
        "stage_id":      stage_id,
        "stage":         stage_lbl,
        "stage_prob":    stage_prob,
        "stage_order":   stage_ord,
        "is_closed":     stage_id in CLOSED_STAGE_IDS,
        "amount":        amount,
        "weighted":      round(amount * stage_prob, 2),
        "owner_id":      owner_id,
        "owner":         owner_name,
        "create_date":   create_dt.date() if create_dt else None,
        "close_date":    close_dt.date()  if close_dt  else None,
        "last_activity": last_dt.date()   if last_dt   else None,
        "days_created":  days_created,
        "days_activity": days_activity,
        "days_to_close": days_to_close,
        "n_contacts":    int(p.get("num_associated_contacts") or 0),
        # scoring placeholders
        "score":         0,
        "level":         "warm",
        "signals":       {"positive": [], "negative": [], "urgency": [], "has_text": False, "call_count": 0},
    })

_COLS = [
    "id","deal_name","stage_id","stage","stage_prob","stage_order","is_closed",
    "amount","weighted","owner_id","owner","create_date","close_date",
    "last_activity","days_created","days_activity","days_to_close",
    "n_contacts","score","level","signals",
]
df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=_COLS)

# ── Filters ────────────────────────────────────────────────────────────────
# Always remove Churn stages from the funnel
if not df.empty:
    df = df[~df["stage"].str.lower().str.contains("churn", na=False)]

if not show_closed and not df.empty:
    df = df[~df["is_closed"]]

if p_start and p_end and not df.empty:
    df = df[
        df["create_date"].apply(
            lambda x: x is not None and p_start <= x <= p_end
        )
    ]

if selected_owner != "Todos" and not df.empty:
    df = df[df["owner"] == selected_owner]

# ── Stage filter sidebar (built after df is ready) ─────────────────────────
with st.sidebar:
    st.divider()
    stage_opts = (
        df.sort_values("stage_order")["stage"].unique().tolist()
        if not df.empty else []
    )
    selected_stages = st.multiselect(
        "Etapas del funnel",
        options=stage_opts,
        default=stage_opts,
        key="stage_filter",
    )

if selected_stages and not df.empty:
    df = df[df["stage"].isin(selected_stages)]

# ── Transcripts + refresh sidebar ─────────────────────────────────────────
with st.sidebar:
    st.divider()
    load_transcripts = st.checkbox(
        "Cargar transcripciones DIIO",
        value=True,
        help="Carga y analiza resúmenes de llamadas asociadas a cada negocio.",
    )
    if st.button("Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache: 15 min · Datos en vivo desde HubSpot.")


# ── Load transcripts & score ───────────────────────────────────────────────
deal_calls: dict[str, list[dict]] = {}
if load_transcripts and not df.empty:
    deal_calls = get_deal_calls(tuple(df["id"].astype(str).tolist()))
    n_with_calls = len(deal_calls)
    if n_with_calls == 0:
        st.warning(
            f"⚠️ No se encontraron transcripciones DIIO para ninguno de los {len(df)} negocios. "
            "Esto puede significar que: (1) las llamadas DIIO no están asociadas a estos deals ni a sus contactos en HubSpot, "
            "o (2) el token no tiene el scope `crm.objects.calls.read`. "
            "Hacé clic en **Actualizar datos** en el sidebar para limpiar caché e intentar de nuevo.",
            icon="⚠️",
        )
    else:
        st.success(f"✅ Transcripciones DIIO encontradas en {n_with_calls} de {len(df)} negocios.", icon="📞")

if not df.empty:
    for idx in df.index:
        did      = str(df.at[idx, "id"])
        calls    = deal_calls.get(did, [])
        signals  = _analyze_signals(calls)
        scored   = _score_deal(
            df.at[idx, "stage_prob"],
            signals,
            int(df.at[idx, "days_activity"]),
            df.at[idx, "days_to_close"],
        )
        df.at[idx, "score"]   = scored["score"]
        df.at[idx, "level"]   = scored["level"]
        df.at[idx, "signals"] = signals


# ─────────────────────────────────────────
#  Header
# ─────────────────────────────────────────
st.markdown(f"""
<div style="display:flex;align-items:center;gap:14px;
            border-bottom:2px solid #e5e7eb;padding-bottom:14px;margin-bottom:18px;">
  <div style="width:46px;height:46px;border-radius:12px;flex-shrink:0;
              background:linear-gradient(135deg,#e63946,#f4a261);
              display:flex;align-items:center;justify-content:center;
              font-weight:900;color:#fff;font-size:20px;">$</div>
  <div>
    <h1 style="margin:0;font-size:22px;font-weight:800;color:#111827">
      Directorio Comercial · {pipeline_label}
    </h1>
    <p style="margin:0;color:#6b7280;font-size:13px">
      {len(df):,} negocios · Bullseye (SOi Digital) ·
      {"Transcripciones DIIO activadas" if load_transcripts else "Transcripciones: desactivadas (activar en sidebar)"}
    </p>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
#  KPI helpers + dialog
# ─────────────────────────────────────────
today = date.today()

total_deals    = len(df)
total_value    = df["amount"].sum() if not df.empty else 0.0
weighted_value = df["weighted"].sum() if not df.empty else 0.0
df_hot_kpi     = df[df["score"] >= 65] if not df.empty else df
hot_deals      = len(df_hot_kpi)
df_closing     = df[df["close_date"].apply(
    lambda x: x is not None and x.year == today.year and x.month == today.month
)] if not df.empty else df
closing_month  = len(df_closing)
avg_score      = round(df["score"].mean()) if not df.empty else 0


def _explain_score(row: pd.Series) -> str:
    """Generate a human-readable reason for the score."""
    sig = row.get("signals", {})
    if not isinstance(sig, dict):
        sig = {}
    stage_pct = int(row.get("stage_prob", 0) * 100)
    if not sig.get("has_text"):
        days_act = int(row.get("days_activity", 999))
        days_cl  = row.get("days_to_close")
        parts = [f"Sin transcripciones · etapa {stage_pct}%"]
        if days_act > 30:
            parts.append(f"sin actividad {days_act}d")
        if days_cl is not None and days_cl < 0:
            parts.append("fecha cierre vencida")
        elif days_cl is not None and days_cl <= 14:
            parts.append(f"cierra en {days_cl}d")
        return " · ".join(parts)
    parts = []
    for kw in sig.get("positive", [])[:3]:
        parts.append(f"✓ {kw}")
    for kw in sig.get("urgency", [])[:2]:
        parts.append(f"⚡ {kw}")
    for kw in sig.get("negative", [])[:2]:
        parts.append(f"✗ {kw}")
    if not parts:
        return f"Etapa {stage_pct}% · {sig.get('call_count', 0)} llamada(s) sin señales clave"
    return " · ".join(parts)


@st.dialog("Detalle de negocios", width="large")
def _kpi_detail(title: str, sub_df: pd.DataFrame) -> None:
    st.markdown(f"**{title}** — {len(sub_df)} negocio(s)")
    if sub_df.empty:
        st.info("Sin negocios en esta categoría.")
        return
    disp = sub_df[["deal_name", "stage", "amount", "owner", "close_date", "score"]].copy()
    disp["razon"] = sub_df.apply(_explain_score, axis=1)
    disp["amount"] = disp["amount"].apply(lambda v: f"${v:,.0f}" if v > 0 else "–")
    disp["close_date"] = disp["close_date"].apply(
        lambda d: d.strftime("%d/%m/%Y") if d is not None else "–"
    )
    disp["score"] = disp["score"].apply(lambda s: f"{int(s)}%")
    disp.columns = ["Negocio", "Etapa", "Valor", "Owner", "Cierre estimado", "Score", "Razón del score"]
    st.dataframe(disp, use_container_width=True, hide_index=True)


def _kcard(icon, label, value, sub, tc, bg, bc):
    return f"""<div class="kpi-html-card" style="background:{bg};border:1px solid {bc};border-radius:12px;padding:16px 18px">
      <div style="font-size:.65rem;font-weight:700;color:{tc};text-transform:uppercase;
                  letter-spacing:.08em;margin-bottom:4px">{icon} {label}</div>
      <div style="font-size:1.9rem;font-weight:800;color:#111827;line-height:1.15">{value}</div>
      <div style="font-size:.7rem;color:#9ca3af;margin-top:3px">{sub}</div>
    </div>"""


# ─────────────────────────────────────────
#  KPI Cards (HTML card + invisible overlay button)
# ─────────────────────────────────────────
st.markdown('<div class="kpi-row-marker" style="display:none"></div>', unsafe_allow_html=True)
k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.markdown(_kcard("🏢","Activos",f"{total_deals:,}","en pipeline",
        "#6366f1","linear-gradient(135deg,#f8faff,#eef2ff)","#c7d2fe"), unsafe_allow_html=True)
    if st.button(" ", key="kbtn1", use_container_width=True):
        _kpi_detail("Todos los negocios activos", df.sort_values("score", ascending=False))

with k2:
    st.markdown(_kcard("💰","Valor total",f"${total_value:,.0f}","suma de deals",
        "#0ea5e9","linear-gradient(135deg,#f0f9ff,#e0f2fe)","#7dd3fc"), unsafe_allow_html=True)
    if st.button(" ", key="kbtn2", use_container_width=True):
        _kpi_detail("Negocios por valor", df.sort_values("amount", ascending=False))

with k3:
    st.markdown(_kcard("⚖️","Valor ponderado",f"${weighted_value:,.0f}","ajustado por probabilidad",
        "#8b5cf6","linear-gradient(135deg,#faf5ff,#ede9fe)","#c4b5fd"), unsafe_allow_html=True)
    if st.button(" ", key="kbtn3", use_container_width=True):
        _kpi_detail("Negocios por valor ponderado", df.sort_values("weighted", ascending=False))

with k4:
    tc4 = "#15803d" if hot_deals > 0 else "#6b7280"
    bg4 = "linear-gradient(135deg,#f0fdf4,#dcfce7)" if hot_deals > 0 else "linear-gradient(135deg,#f9fafb,#f3f4f6)"
    bc4 = "#86efac" if hot_deals > 0 else "#e5e7eb"
    st.markdown(_kcard("🔥","En cierre (≥65)",f"{hot_deals:,}","score alto",
        tc4, bg4, bc4), unsafe_allow_html=True)
    if st.button(" ", key="kbtn4", use_container_width=True):
        _kpi_detail("Negocios en cierre (score ≥ 65%)", df_hot_kpi.sort_values("score", ascending=False))

with k5:
    tc5 = "#b45309" if closing_month > 0 else "#6b7280"
    st.markdown(_kcard("📅","Cierran este mes",f"{closing_month:,}","por close date",
        tc5,"linear-gradient(135deg,#fffbeb,#fef3c7)","#fcd34d"), unsafe_allow_html=True)
    if st.button(" ", key="kbtn5", use_container_width=True):
        _kpi_detail("Negocios que cierran este mes", df_closing.sort_values("close_date"))

with k6:
    tc6 = "#15803d" if avg_score >= 55 else "#b45309" if avg_score >= 35 else "#b91c1c"
    st.markdown(_kcard("📊","Score prom.",f"{avg_score}%","basado en señales",
        tc6,"linear-gradient(135deg,#fff7f7,#fde8e8)","#fca5a5"), unsafe_allow_html=True)
    if st.button(" ", key="kbtn6", use_container_width=True):
        _kpi_detail("Todos los negocios por score", df.sort_values("score", ascending=False))

components.html("""
<script>
(function() {
  var doc = window.parent.document;
  function setup() {
    var cards = doc.querySelectorAll('.kpi-html-card:not([data-wired])');
    if (!cards.length) return 0;
    var done = 0;
    cards.forEach(function(card) {
      var col = card.closest('[data-testid="column"]');
      if (!col) return;
      var btn = col.querySelector('[data-testid="stButton"] button');
      if (!btn) return;
      var wrap = btn.parentElement && btn.parentElement.parentElement;
      if (wrap) wrap.style.cssText = 'height:0!important;overflow:hidden!important;padding:0!important;margin:0!important;';
      card.setAttribute('data-wired','1');
      card.addEventListener('click', (function(b, w) {
        return function() {
          if (w) w.style.cssText = '';
          b.click();
          if (w) setTimeout(function(){ w.style.cssText='height:0!important;overflow:hidden!important;padding:0!important;margin:0!important;'; }, 80);
        };
      })(btn, wrap));
      done++;
    });
    return done;
  }
  var tries = 0;
  function attempt() {
    if (setup() >= 1) return;
    if (++tries < 40) setTimeout(attempt, 250);
  }
  attempt();
})();
</script>
""", height=0)

st.markdown("<br>", unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Charts
# ─────────────────────────────────────────
if not df.empty:
    chart_l, chart_r = st.columns([3, 2])

    with chart_l:
        stage_agg = (
            df.groupby("stage", sort=False)
            .agg(Deals=("id","count"), Valor=("amount","sum"), Ponderado=("weighted","sum"))
            .reset_index()
        )
        # Sort by stage order
        stage_order_list = [stage_id_to_label.get(s["id"], s["id"]) for s in stages_raw]
        stage_agg["_ord"] = stage_agg["stage"].map(
            {lbl: i for i, lbl in enumerate(stage_order_list)}
        ).fillna(99)
        stage_agg = stage_agg.sort_values("_ord")

        fig_funnel = go.Figure()
        fig_funnel.add_bar(
            y=stage_agg["stage"], x=stage_agg["Deals"],
            orientation="h", name="Deals",
            marker_color="#6366f1", text=stage_agg["Deals"],
            textposition="inside",
        )
        fig_funnel.update_layout(
            title="Negocios por etapa",
            height=320, margin=dict(t=45,b=20,l=10,r=20),
            xaxis_title=None, yaxis_title=None,
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

    with chart_r:
        fig_val = px.bar(
            stage_agg, x="stage", y="Valor",
            title="Valor por etapa ($)",
            color="Valor",
            color_continuous_scale=[(0,"#e0f2fe"),(0.5,"#6366f1"),(1,"#e63946")],
            text_auto=".2s",
        )
        fig_val.update_layout(
            height=320, margin=dict(t=45,b=60,l=10,r=20),
            xaxis_title=None, coloraxis_showscale=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig_val.update_traces(textposition="outside")
        st.plotly_chart(fig_val, use_container_width=True)

st.divider()


# ─────────────────────────────────────────
#  Tabs: Directorio / Hot / Transcripciones / En riesgo
# ─────────────────────────────────────────
tab_dir, tab_hot, tab_trans, tab_risk = st.tabs([
    f"📋 Directorio ({len(df)})",
    f"🔥 Oportunidades calientes ({len(df[df['level']=='hot']) if not df.empty else 0})",
    f"📝 Transcripciones DIIO",
    f"⚠️ En riesgo",
])


# ── helpers ──────────────────────────────────────────────────────────────────
STAGE_COLORS = [
    "#e0f2fe","#bfdbfe","#c7d2fe","#ddd6fe","#f5d0fe",
    "#fed7aa","#fde68a","#bbf7d0","#6ee7b7",
]

def _stage_badge(stage: str, order: int) -> str:
    col = STAGE_COLORS[order % len(STAGE_COLORS)]
    return f'<span class="stage-badge" style="background:{col};color:#374151">{stage}</span>'

def _score_badge(score: int, level: str) -> str:
    cls = f"score-{level}"
    icon = "🔥" if level == "hot" else "🌡" if level == "warm" else "❄️"
    return f'<span class="{cls}">{icon} {score}%</span>'

def _close_date_html(d: date | None, days: int | None) -> str:
    if d is None:
        return '<span style="color:#9ca3af">–</span>'
    s = d.strftime("%d/%m/%Y")
    if days is not None:
        if days < 0:
            return f'<span style="color:#b91c1c;font-weight:600">{s} ⚠️ vencido</span>'
        elif days <= 7:
            return f'<span style="color:#b45309;font-weight:600">{s} ({days}d)</span>'
        elif days <= 30:
            return f'<span style="color:#0ea5e9">{s} ({days}d)</span>'
    return f'<span style="color:#6b7280">{s}</span>'


# ── TAB 1: DIRECTORIO ─────────────────────────────────────────────────────────
with tab_dir:
    if df.empty:
        st.info("Sin negocios con los filtros actuales.")
    else:
        # Sort options
        col_s, col_s2, _ = st.columns([2, 2, 6])
        with col_s:
            sort_by = st.selectbox("Ordenar por",
                ["Score ↓", "Valor ↓", "Cierre próximo", "Actividad reciente", "Etapa", "Creación ↓"],
                key="dir_sort", label_visibility="collapsed")
        with col_s2:
            st.caption(f"**{len(df)}** negocios · valor total **${total_value:,.0f}**")

        sort_map = {
            "Score ↓":          ("score",         False),
            "Valor ↓":          ("amount",         False),
            "Cierre próximo":   ("days_to_close",  True),
            "Actividad reciente":("days_activity",  True),
            "Etapa":            ("stage_order",     True),
            "Creación ↓":       ("days_created",    True),
        }
        sk, sa = sort_map[sort_by]
        df_sorted = df.sort_values(sk, ascending=sa, na_position="last")

        # Build display table
        rows_html = []
        for _, row in df_sorted.iterrows():
            badge    = _stage_badge(row["stage"], int(row["stage_order"]))
            sc_badge = _score_badge(int(row["score"]), str(row["level"]))
            cd_html  = _close_date_html(row["close_date"], row["days_to_close"])
            amt      = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
            act_days = f"{int(row['days_activity'])}d" if row["days_activity"] < 999 else "–"
            create   = row["create_date"].strftime("%d/%m/%y") if row["create_date"] else "–"
            razon    = _explain_score(row)

            rows_html.append(
                f"<tr>"
                f"<td style='padding:8px 10px;font-weight:600;max-width:200px'>{row['deal_name']}</td>"
                f"<td style='padding:8px 10px'>{badge}</td>"
                f"<td style='padding:8px 10px;text-align:right;font-weight:600'>{amt}</td>"
                f"<td style='padding:8px 10px'>{row['owner']}</td>"
                f"<td style='padding:8px 10px;text-align:center;color:#6b7280'>{create}</td>"
                f"<td style='padding:8px 10px;text-align:center;color:#6b7280'>{act_days}</td>"
                f"<td style='padding:8px 10px'>{cd_html}</td>"
                f"<td style='padding:8px 10px;text-align:center'>{sc_badge}</td>"
                f"<td style='padding:8px 10px;color:#6b7280;font-size:11px;max-width:220px'>{razon}</td>"
                f"</tr>"
            )

        body_rows = "".join(
            f'<tr style="border-bottom:1px solid #f3f4f6;{"background:#fafafa" if i%2==0 else ""}">'
            + r.split("<tr>")[1].split("</tr>")[0]
            + "</tr>"
            for i, r in enumerate(rows_html)
        )
        clean_table = f"""
        <div style="overflow-x:auto;border-radius:10px;border:1px solid #e5e7eb;margin-top:8px">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb">
              <th style="padding:10px;text-align:left;color:#374151;font-weight:700">Negocio</th>
              <th style="padding:10px;text-align:left;color:#374151;font-weight:700">Etapa</th>
              <th style="padding:10px;text-align:right;color:#374151;font-weight:700">Valor</th>
              <th style="padding:10px;text-align:left;color:#374151;font-weight:700">Owner</th>
              <th style="padding:10px;text-align:center;color:#374151;font-weight:700">Creado</th>
              <th style="padding:10px;text-align:center;color:#374151;font-weight:700">Ult. actividad</th>
              <th style="padding:10px;text-align:left;color:#374151;font-weight:700">Cierre est.</th>
              <th style="padding:10px;text-align:center;color:#374151;font-weight:700">Score cierre</th>
              <th style="padding:10px;text-align:left;color:#374151;font-weight:700">Razón del score</th>
            </tr>
          </thead>
          <tbody>{body_rows}</tbody>
        </table></div>"""
        st.markdown(clean_table, unsafe_allow_html=True)


# ── TAB 2: HOT DEALS ─────────────────────────────────────────────────────────
with tab_hot:
    if df.empty:
        st.info("Sin datos.")
    else:
        df_hot = df[df["level"] == "hot"].sort_values("score", ascending=False)
        df_warm = df[df["level"] == "warm"].sort_values("score", ascending=False).head(10)

        if df_hot.empty and df_warm.empty:
            if not load_transcripts:
                st.info("Activa 'Cargar transcripciones DIIO' en el sidebar para ver el análisis de señales. "
                        "Sin transcripciones el score se basa solo en etapa y fechas.")
            else:
                st.info("Sin deals calientes en este pipeline con los filtros actuales.")
        else:
            if not df_hot.empty:
                st.markdown("### 🔥 Cierre muy probable")
                for _, row in df_hot.iterrows():
                    sig = row["signals"]
                    amt = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
                    cd  = row["close_date"].strftime("%d/%m/%Y") if row["close_date"] else "–"
                    pos_tags = " ".join(f'<span class="signal-pos">✓ {s}</span>' for s in sig["positive"][:5])
                    neg_tags = " ".join(f'<span class="signal-neg">✗ {s}</span>' for s in sig["negative"][:3])
                    urg_tags = " ".join(f'<span class="signal-urg">⚡ {s}</span>' for s in sig["urgency"][:3])
                    calls_in = deal_calls.get(str(row["id"]), [])
                    n_calls  = len(calls_in)
                    st.markdown(f"""
<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:1px solid #86efac;
            border-radius:12px;padding:16px 20px;margin-bottom:10px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <span style="font-size:17px;font-weight:800;color:#111827">{row['deal_name']}</span>
      <span style="margin-left:10px;font-size:11px;color:#6b7280">
        {_stage_badge(row['stage'], int(row['stage_order']))}
      </span>
    </div>
    <div style="text-align:right">
      <div style="font-size:2rem;font-weight:900;color:#15803d;line-height:1">{row['score']}%</div>
      <div style="font-size:11px;color:#15803d">score de cierre</div>
    </div>
  </div>
  <div style="margin-top:8px;font-size:12px;color:#374151">
    💰 <b>{amt}</b> &nbsp;|&nbsp; 👤 {row['owner']} &nbsp;|&nbsp;
    📅 Cierre: <b>{cd}</b>
    {f"&nbsp;|&nbsp; 📞 {n_calls} llamada(s)" if n_calls else ""}
  </div>
  <div style="margin-top:8px">{pos_tags}{neg_tags}{urg_tags}</div>
</div>""", unsafe_allow_html=True)

            if not df_warm.empty:
                st.markdown("### 🌡 En seguimiento (potencial)")
                cols_w = st.columns(2)
                for i, (_, row) in enumerate(df_warm.iterrows()):
                    amt = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
                    cd  = row["close_date"].strftime("%d/%m/%Y") if row["close_date"] else "–"
                    with cols_w[i % 2]:
                        st.markdown(f"""
<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);border:1px solid #fcd34d;
            border-radius:10px;padding:14px 16px;margin-bottom:8px">
  <div style="font-weight:700;font-size:14px;color:#111827">{row['deal_name']}</div>
  <div style="font-size:11px;color:#6b7280;margin-top:4px">
    {_stage_badge(row['stage'], int(row['stage_order']))} &nbsp; {amt} &nbsp;|&nbsp; Cierre: {cd}
  </div>
  <div style="font-size:13px;font-weight:800;color:#b45309;margin-top:6px">Score: {row['score']}%</div>
</div>""", unsafe_allow_html=True)


# ── TAB 3: TRANSCRIPCIONES DIIO ──────────────────────────────────────────────
with tab_trans:
    if not load_transcripts:
        st.info("Activa **'Cargar transcripciones DIIO'** en el sidebar para ver los resúmenes de llamadas "
                "generados automáticamente por DIIO.")
    elif not deal_calls:
        st.info("No se encontraron transcripciones de llamadas para los negocios en este pipeline.")
    else:
        deals_with_calls = [row for _, row in df.iterrows() if str(row["id"]) in deal_calls]
        deals_with_calls = sorted(deals_with_calls, key=lambda r: r["score"], reverse=True)

        st.markdown(f"**{len(deals_with_calls)}** negocios con transcripciones DIIO")
        st.divider()

        for row in deals_with_calls:
            calls_list = deal_calls.get(str(row["id"]), [])
            sig   = row["signals"]
            score = int(row["score"])
            level = str(row["level"])
            amt   = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
            sc_icon = "🔥" if level == "hot" else "🌡" if level == "warm" else "❄️"

            pos_tags = " ".join(f'<span class="signal-pos">✓ {s}</span>' for s in sig["positive"][:6])
            neg_tags = " ".join(f'<span class="signal-neg">✗ {s}</span>' for s in sig["negative"][:4])
            urg_tags = " ".join(f'<span class="signal-urg">⚡ {s}</span>' for s in sig["urgency"][:3])

            with st.expander(
                f"{sc_icon} {row['deal_name']}  —  "
                f"{row['stage']}  ·  {amt}  ·  Score: {score}%  ·  {len(calls_list)} llamada(s)"
            ):
                # Signals summary
                if pos_tags or neg_tags or urg_tags:
                    st.markdown("**Señales detectadas en transcripciones:**")
                    st.markdown(
                        f"{pos_tags} {neg_tags} {urg_tags}",
                        unsafe_allow_html=True
                    )
                    st.markdown("---")

                # Individual calls
                for call in calls_list:
                    ts = ""
                    try:
                        ts = datetime.fromisoformat(call["timestamp"].replace("Z", "+00:00")) \
                                     .strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        pass
                    dur_min = call["duration_ms"] // 60000
                    dur_sec = (call["duration_ms"] % 60000) // 1000

                    st.markdown(
                        f"**📞 {call['title']}** &nbsp;·&nbsp; {ts}"
                        f" &nbsp;·&nbsp; {call['disposition']}"
                        f"{f' &nbsp;·&nbsp; {dur_min}:{dur_sec:02d} min' if dur_min else ''}",
                        unsafe_allow_html=True,
                    )
                    if call.get("summary"):
                        st.markdown("*Resumen DIIO:*")
                        st.markdown(call["summary"], unsafe_allow_html=True)
                    if call.get("body"):
                        st.markdown("*Notas del SDR:*")
                        st.markdown(call["body"], unsafe_allow_html=True)
                    st.markdown("---")


# ── TAB 4: EN RIESGO ─────────────────────────────────────────────────────────
with tab_risk:
    if df.empty:
        st.info("Sin datos.")
    else:
        today_dt = date.today()

        # 1. Sin actividad hace +14 días (excluir recién creados)
        stalled = df[
            (df["days_activity"] > 14) &
            (df["days_created"] > 7) &
            (~df["is_closed"])
        ].sort_values("days_activity", ascending=False)

        # 2. Close date vencida y aún activos
        overdue = df[
            df["days_to_close"].apply(lambda x: x is not None and x < 0) &
            (~df["is_closed"])
        ].sort_values("days_to_close", ascending=True)

        # 3. Señales negativas dominantes (solo si hay transcripciones)
        cold_deals = df[df["level"] == "cold"].sort_values("score", ascending=True)

        # Sidebar summary
        st.markdown(
            f"**{len(stalled)}** sin actividad (+14d) &nbsp;·&nbsp; "
            f"**{len(overdue)}** con fecha de cierre vencida &nbsp;·&nbsp; "
            f"**{len(cold_deals)}** con score bajo"
        )
        st.divider()

        r1, r2 = st.columns(2)

        with r1:
            st.markdown("#### 💤 Sin actividad reciente (+14 días)")
            if stalled.empty:
                st.caption("Todos los negocios tienen actividad reciente.")
            else:
                for _, row in stalled.head(15).iterrows():
                    amt = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
                    last = row["last_activity"].strftime("%d/%m/%Y") if row["last_activity"] else "–"
                    color = "#b91c1c" if row["days_activity"] > 30 else "#b45309"
                    st.markdown(f"""
<div style="border-left:3px solid {color};padding:8px 12px;
            margin-bottom:6px;border-radius:0 8px 8px 0;background:#fafafa">
  <div style="font-weight:700;font-size:13px">{row['deal_name']}</div>
  <div style="font-size:11px;color:#6b7280">
    {_stage_badge(row['stage'], int(row['stage_order']))} &nbsp;
    {amt} &nbsp;·&nbsp; {row['owner']}
  </div>
  <div style="font-size:11px;color:{color};margin-top:3px;font-weight:600">
    Última actividad: {last} ({int(row['days_activity'])} días)
  </div>
</div>""", unsafe_allow_html=True)

        with r2:
            st.markdown("#### 📅 Fecha de cierre vencida")
            if overdue.empty:
                st.caption("No hay negocios con cierre vencido.")
            else:
                for _, row in overdue.head(15).iterrows():
                    amt = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
                    cd  = row["close_date"].strftime("%d/%m/%Y") if row["close_date"] else "–"
                    late = abs(int(row["days_to_close"]))
                    st.markdown(f"""
<div style="border-left:3px solid #b91c1c;padding:8px 12px;
            margin-bottom:6px;border-radius:0 8px 8px 0;background:#fef2f2">
  <div style="font-weight:700;font-size:13px">{row['deal_name']}</div>
  <div style="font-size:11px;color:#6b7280">
    {_stage_badge(row['stage'], int(row['stage_order']))} &nbsp;
    {amt} &nbsp;·&nbsp; {row['owner']}
  </div>
  <div style="font-size:11px;color:#b91c1c;margin-top:3px;font-weight:600">
    Vencido hace {late} días (cierre: {cd})
  </div>
</div>""", unsafe_allow_html=True)

        if not cold_deals.empty and load_transcripts:
            st.markdown("#### ❄️ Señales negativas dominantes")
            for _, row in cold_deals.head(8).iterrows():
                sig = row["signals"]
                neg_tags = " ".join(f'<span class="signal-neg">✗ {s}</span>' for s in sig["negative"][:4])
                amt = f"${row['amount']:,.0f}" if row["amount"] > 0 else "–"
                st.markdown(f"""
<div style="border-left:3px solid #6b7280;padding:8px 12px;
            margin-bottom:6px;border-radius:0 8px 8px 0;background:#fafafa">
  <div style="font-weight:700;font-size:13px">{row['deal_name']} · Score: {row['score']}%</div>
  <div style="font-size:11px;color:#6b7280">{_stage_badge(row['stage'], int(row['stage_order']))} · {amt} · {row['owner']}</div>
  <div style="margin-top:4px">{neg_tags}</div>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────
#  Footer
# ─────────────────────────────────────────
st.divider()
st.caption(
    f"💼 Directorio Comercial · {pipeline_label} · Bullseye (SOi Digital) · "
    f"Score basado en etapa, señales de transcripciones DIIO, recencia y fecha de cierre · Cache 15 min"
)
