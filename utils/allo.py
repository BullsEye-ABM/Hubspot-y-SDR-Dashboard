"""
ALLO API client for the Bullseye dashboard.
ALLO is the telephony platform used by SDRs (one phone number per client/country,
each SDR dials from their assigned number so reporting stays unified).

Caches raw fetches 15 minutes via Streamlit's st.cache_data; all filtering by
SDR, phone number, tag, etc. happens client-side on the cached DataFrame so
switching a filter doesn't re-hit the API.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import requests
import streamlit as st

API_BASE = "https://api.withallo.com"
CACHE_TTL = 900  # 15 minutes

# Safety cap on how many conversation items a single fetch will page through.
# ~450 calls/month today; this comfortably covers a full year before truncating.
MAX_ITEMS = 6000
PAGE_SIZE = 100

# Call results that count as a real human connection (excludes VOICEMAIL).
CONNECTED_RESULTS = {"ANSWERED", "TRANSFERRED"}

MEETING_TAG = "meeting_booked"


def _get_token() -> str:
    """Read the ALLO API key from Streamlit secrets."""
    try:
        return st.secrets["allo"]["api_key"]
    except (KeyError, FileNotFoundError):
        st.error(
            "API key de ALLO no configurada. "
            "Edita `.streamlit/secrets.toml` con `[allo]` -> `api_key` "
            "(ver `.streamlit/secrets.toml.example`)."
        )
        st.stop()


def _headers() -> dict:
    return {
        "Authorization": f"Api-Key {_get_token()}",
        "Content-Type": "application/json",
    }


def _raise_with_body(r: "requests.Response") -> None:
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        sent_body = r.request.body if r.request is not None else None
        sent_headers = dict(r.request.headers) if r.request is not None else {}
        sent_headers.pop("Authorization", None)
        raise requests.HTTPError(
            f"{e} — response body: {r.text[:800]} — sent body: {sent_body!r} — sent headers: {sent_headers}",
            response=r,
        ) from e


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{API_BASE}{path}", headers=_headers(), params=params, timeout=30)
    _raise_with_body(r)
    return r.json()


def _post(path: str, body: dict) -> dict:
    r = requests.post(f"{API_BASE}{path}", headers=_headers(), json=body, timeout=30)
    _raise_with_body(r)
    return r.json()


# -----------------------------------------
#  Reference data (numbers, users, tags)
# -----------------------------------------

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def list_numbers() -> list[dict[str, Any]]:
    """Return ALLO phone numbers/lines. Each: {number, name, country, users}."""
    data = _get("/v2/api/numbers").get("data", [])
    return [n for n in data if n.get("number")]


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def list_users() -> list[dict[str, Any]]:
    """Return active team members. Each: {id, name, email, role}."""
    return _get("/v2/api/users", params={"status": "ACTIVE"}).get("data", [])


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def list_tags() -> list[dict[str, Any]]:
    """Return configured call/SMS tags. Each: {id, name, color}."""
    return _get("/v2/api/tags").get("data", [])


# -----------------------------------------
#  Conversation items (calls + SMS)
# -----------------------------------------

@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando actividad de ALLO...")
def fetch_conversation_items(date_from: date, date_to: date, item_type: str = "ALL") -> tuple[list[dict], bool]:
    """
    Page through /conversations/items/search for the given date range.
    Returns (items, truncated) where truncated=True if MAX_ITEMS was hit.
    No SDR/number/tag filtering here — that happens client-side so switching
    those filters doesn't trigger a new fetch.
    """
    items: list[dict] = []
    page = 1
    truncated = False

    while True:
        body = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "type": item_type,
            "sort": "DATE",
            "page": page,
            "size": PAGE_SIZE,
        }
        data = _post("/v2/api/conversations/items/search", body)
        batch = data.get("data", [])
        items.extend(batch)
        pagination = data.get("pagination", {})
        if len(items) >= MAX_ITEMS:
            truncated = bool(pagination.get("has_more"))
            break
        if not pagination.get("has_more"):
            break
        page += 1

    return items, truncated


def items_to_dataframe(items: list[dict]):
    """Convert raw ALLO conversation items into a flat pandas DataFrame."""
    import pandas as pd

    rows = []
    for it in items:
        user = it.get("user") or {}
        rows.append({
            "id": it.get("id", ""),
            "type": it.get("type", ""),
            "direction": it.get("direction", ""),
            "allo_number": it.get("allo_number", ""),
            "contact_number": it.get("contact_number", ""),
            "user_id": user.get("id", ""),
            "user_name": user.get("name", "Sin asignar"),
            "date": it.get("date", ""),
            "duration": it.get("duration", 0) or 0,
            "result": it.get("result", ""),
            "recording_url": it.get("recording_url", ""),
            "summary": it.get("summary", "") or "",
            "tags": it.get("tags", []) or [],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df = df.dropna(subset=["date"])
    df["duration_min"] = df["duration"] / 60
    return df


# -----------------------------------------
#  Official ALLO analytics (source of truth — matches ALLO's own dashboard)
# -----------------------------------------
#
# ALLO's own API rejects combining user_ids + allo_numbers in one call
# (FILTER_CONFLICT — their own UI has the same "By User / By Phone" mutually
# exclusive toggle). So these are only usable when at most one of the two
# dimensions (SDR, numero/cliente) is restricted at a time. When both are
# restricted simultaneously, the page falls back to the raw item-level
# helpers above (connection_rate_excl_voicemail / breakdown_by).

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_outbound_funnel(
    date_from: date, date_to: date,
    user_ids: tuple[str, ...] | None = None,
    allo_numbers: tuple[str, ...] | None = None,
    meeting_tag: str = MEETING_TAG,
) -> dict[str, Any]:
    """
    Official outbound funnel from ALLO's own analytics engine — the exact
    numbers shown in ALLO's dashboard (Outbound > Conversion funnel).
    Do not pass both user_ids and allo_numbers (ALLO rejects it).
    """
    body: dict[str, Any] = {
        "date": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "tags": [meeting_tag],
    }
    if user_ids:
        body["user_ids"] = list(user_ids)
    if allo_numbers:
        body["allo_numbers"] = list(allo_numbers)

    data = _post("/v2/api/analytics/outbound", body).get("data", {})
    funnel = data.get("funnel", {})
    ts = data.get("time_series", {})
    time_spent = data.get("time_spent", {})

    return {
        "dials": funnel.get("dials", {}).get("count", {}).get("value", 0),
        "connected": funnel.get("connected", {}).get("count", {}).get("value", 0),
        "connected_rate": (funnel.get("connected", {}).get("rate") or 0) * 100,
        "meetings": funnel.get("conversions", {}).get("count", {}).get("value", 0),
        "avg_conversation_seconds": time_spent.get("avg_conversation_time_seconds", {}).get("value", 0) or 0,
        "time_series": {
            "dials": ts.get("dials", []),
            "connected": ts.get("connected", []),
            "connection_rate": ts.get("connection_rate", []),
        },
    }


def get_outbound_funnel_per_user(date_from: date, date_to: date, user_ids: list[str]) -> list[dict]:
    """One official funnel call per SDR (cached individually)."""
    return [
        {"user_id": uid, **get_outbound_funnel(date_from, date_to, user_ids=(uid,))}
        for uid in user_ids
    ]


def get_outbound_funnel_per_number(date_from: date, date_to: date, allo_numbers: list[str]) -> list[dict]:
    """One official funnel call per ALLO number (cached individually)."""
    return [
        {"allo_number": num, **get_outbound_funnel(date_from, date_to, allo_numbers=(num,))}
        for num in allo_numbers
    ]


# -----------------------------------------
#  Derived metrics (fallback for combined SDR + numero filters, and for
#  metrics ALLO's analytics API doesn't expose: activities incl. SMS,
#  voicemail count, tag breakdown, raw detail feed)
# -----------------------------------------

def connection_rate_excl_voicemail(df) -> tuple[float, int, int, int]:
    """
    Tasa de conexion sin contar voicemail, sobre llamadas salientes:
        conectadas (ANSWERED + TRANSFERRED) / (total_outbound - voicemail)
    Voicemail se excluye del numerador Y del denominador: no cuenta ni como
    intento ni como conexion.
    Returns (rate_pct, connected_count, voicemail_count, denominator).
    """
    if df.empty:
        return 0.0, 0, 0, 0
    calls = df[(df["type"] == "CALL") & (df["direction"] == "OUTBOUND")]
    if calls.empty:
        return 0.0, 0, 0, 0
    voicemail = int((calls["result"] == "VOICEMAIL").sum())
    connected = int(calls["result"].isin(CONNECTED_RESULTS).sum())
    denominator = len(calls) - voicemail
    rate = (connected / denominator * 100) if denominator > 0 else 0.0
    return rate, connected, voicemail, denominator


def meetings_booked_count(df) -> int:
    """Count of calls tagged as meeting_booked."""
    if df.empty:
        return 0
    return int(df["tags"].apply(lambda t: MEETING_TAG in t).sum())


def tag_breakdown(df, tag_catalog: list[dict]):
    """Return a DataFrame [tag_id, tag_name, color, count] over calls in df."""
    import pandas as pd

    if df.empty:
        return pd.DataFrame(columns=["tag_id", "tag_name", "color", "count"])
    exploded = df.explode("tags").dropna(subset=["tags"])
    counts = exploded["tags"].value_counts()
    name_map = {t["id"]: t["name"] for t in tag_catalog}
    color_map = {t["id"]: t["color"] for t in tag_catalog}
    out = pd.DataFrame({
        "tag_id": counts.index,
        "count": counts.values,
    })
    out["tag_name"] = out["tag_id"].map(name_map).fillna(out["tag_id"])
    out["color"] = out["tag_id"].map(color_map).fillna("#93a0c2")
    return out.sort_values("count", ascending=False)


def breakdown_by(df, group_col: str):
    """
    Breakdown by an arbitrary column (e.g. 'user_name' for SDR, or a
    'client_name' column joined in by the caller for per-number reporting):
    calls, connected, connection rate (excl. voicemail), meetings booked,
    avg duration of connected calls.
    """
    import pandas as pd

    if df.empty or group_col not in df.columns:
        return pd.DataFrame()

    rows = []
    for key, sub in df.groupby(group_col):
        rate, connected, voicemail, denom = connection_rate_excl_voicemail(sub)
        connected_calls = sub[sub["result"].isin(CONNECTED_RESULTS)]
        avg_dur = connected_calls["duration_min"].mean() if not connected_calls.empty else 0
        rows.append({
            group_col: key,
            "actividades": len(sub),
            "conectadas": connected,
            "voicemail": voicemail,
            "tasa_conexion": round(rate, 1),
            "reuniones_agendadas": meetings_booked_count(sub),
            "duracion_prom_min": round(avg_dur or 0, 1),
        })
    return pd.DataFrame(rows).sort_values("actividades", ascending=False)
