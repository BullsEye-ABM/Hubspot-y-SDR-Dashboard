"""
HubSpot API Client - Multi-cuenta
Obtiene datos de múltiples portales HubSpot usando sus tokens individuales.
"""

import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta


# ─────────────────────────────────────────
#  Helpers internos
# ─────────────────────────────────────────

def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _paginate(url: str, token: str, properties: list, limit: int = 100, extra_params: dict = None) -> list:
    """Recorre todas las páginas de un endpoint CRM v3 y devuelve todos los registros."""
    results = []
    params = {
        "limit": limit,
        "properties": ",".join(properties),
    }
    if extra_params:
        params.update(extra_params)

    while True:
        resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
        if resp.status_code != 200:
            break
        data = resp.json()
        results.extend(data.get("results", []))
        paging = data.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break
        params["after"] = after

    return results


# ─────────────────────────────────────────
#  Owners (SDRs)
# ─────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_owners(token: str) -> dict:
    """Devuelve dict {owner_id: nombre_completo}"""
    resp = requests.get(
        "https://api.hubapi.com/crm/v3/owners",
        headers=_headers(token),
        timeout=30
    )
    owners = {}
    if resp.status_code == 200:
        for o in resp.json().get("results", []):
            full_name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
            owners[str(o["id"])] = full_name or o.get("email", str(o["id"]))
    return owners


# ─────────────────────────────────────────
#  Llamadas (Calls)
# ─────────────────────────────────────────

CALL_PROPS = [
    "hs_call_title",
    "hs_call_duration",      # milisegundos
    "hs_call_status",        # COMPLETED, BUSY, NO_ANSWER, etc.
    "hs_call_disposition",
    "hs_call_body",          # notas / transcripción
    "hs_call_recording_url",
    "hs_call_direction",     # INBOUND / OUTBOUND
    "hubspot_owner_id",
    "hs_timestamp",
    "hs_activity_type",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_calls(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    """Devuelve DataFrame con todas las llamadas de los últimos N días."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw = _paginate(
        "https://api.hubapi.com/crm/v3/objects/calls",
        token,
        CALL_PROPS,
        extra_params={"filterGroups": None},  # filtraremos en pandas
    )

    if not raw:
        return pd.DataFrame()

    rows = []
    owners = get_owners(token)
    for r in raw:
        p = r.get("properties", {})
        ts = p.get("hs_timestamp", "")
        try:
            dt = pd.to_datetime(ts, utc=True)
        except Exception:
            dt = None

        duration_ms = p.get("hs_call_duration")
        duration_sec = int(duration_ms) / 1000 if duration_ms else 0

        owner_id = str(p.get("hubspot_owner_id", ""))
        rows.append({
            "id": r["id"],
            "account": account_name,
            "fecha": dt,
            "sdr": owners.get(owner_id, owner_id),
            "estado": p.get("hs_call_status", ""),
            "disposicion": p.get("hs_call_disposition", ""),
            "duracion_seg": duration_sec,
            "duracion_min": round(duration_sec / 60, 1),
            "direccion": p.get("hs_call_direction", ""),
            "titulo": p.get("hs_call_title", ""),
            "notas": p.get("hs_call_body", ""),
            "grabacion": p.get("hs_call_recording_url", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["fecha"] = pd.to_datetime(df["fecha"], utc=True)
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    df = df[df["fecha"] >= cutoff].copy()
    df["fecha_local"] = df["fecha"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.hour
    df["semana"] = df["fecha_local"].dt.isocalendar().week.astype(int)
    df["mes"] = df["fecha_local"].dt.to_period("M").astype(str)
    # Llamada "conectada" si el estado es COMPLETED
    df["conectada"] = df["estado"].str.upper() == "COMPLETED"
    return df


# ─────────────────────────────────────────
#  Contactos
# ─────────────────────────────────────────

CONTACT_PROPS = [
    "firstname", "lastname", "email", "company",
    "jobtitle", "phone", "hubspot_owner_id",
    "createdate", "hs_lead_status",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_contacts(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    raw = _paginate(
        "https://api.hubapi.com/crm/v3/objects/contacts",
        token,
        CONTACT_PROPS,
    )

    if not raw:
        return pd.DataFrame()

    owners = get_owners(token)
    rows = []
    for r in raw:
        p = r.get("properties", {})
        owner_id = str(p.get("hubspot_owner_id", ""))
        rows.append({
            "id": r["id"],
            "account": account_name,
            "nombre": f"{p.get('firstname', '')} {p.get('lastname', '')}".strip(),
            "email": p.get("email", ""),
            "empresa": p.get("company", ""),
            "cargo": p.get("jobtitle", ""),
            "sdr": owners.get(owner_id, owner_id),
            "fecha_creacion": pd.to_datetime(p.get("createdate"), utc=True, errors="coerce"),
            "estado_lead": p.get("hs_lead_status", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_local"] = df["fecha_creacion"].dt.tz_convert("America/Santiago")
    df["mes"] = df["fecha_local"].dt.to_period("M").astype(str)
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    df = df[df["fecha_creacion"] >= cutoff].copy()
    return df


# ─────────────────────────────────────────
#  Empresas
# ─────────────────────────────────────────

COMPANY_PROPS = [
    "name", "domain", "industry", "city", "country",
    "hubspot_owner_id", "createdate", "numberofemployees",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_companies(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    raw = _paginate(
        "https://api.hubapi.com/crm/v3/objects/companies",
        token,
        COMPANY_PROPS,
    )

    if not raw:
        return pd.DataFrame()

    owners = get_owners(token)
    rows = []
    for r in raw:
        p = r.get("properties", {})
        owner_id = str(p.get("hubspot_owner_id", ""))
        rows.append({
            "id": r["id"],
            "account": account_name,
            "empresa": p.get("name", ""),
            "industria": p.get("industry", ""),
            "ciudad": p.get("city", ""),
            "sdr": owners.get(owner_id, owner_id),
            "fecha_creacion": pd.to_datetime(p.get("createdate"), utc=True, errors="coerce"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_local"] = df["fecha_creacion"].dt.tz_convert("America/Santiago")
    df["mes"] = df["fecha_local"].dt.to_period("M").astype(str)
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    df = df[df["fecha_creacion"] >= cutoff].copy()
    return df


# ─────────────────────────────────────────
#  Actividades (Engagements)
# ─────────────────────────────────────────

ACTIVITY_PROPS = [
    "hs_activity_type", "hubspot_owner_id",
    "hs_timestamp", "hs_body_preview",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_activities(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    """
    Combina calls + meetings + emails en un solo DataFrame de actividades.
    """
    owners = get_owners(token)
    frames = []

    for obj_type, type_label in [("calls", "Llamada"), ("meetings", "Reunión"), ("emails", "Email")]:
        props = ["hubspot_owner_id", "hs_timestamp"]
        if obj_type == "calls":
            props += ["hs_call_status", "hs_call_duration"]
        elif obj_type == "meetings":
            props += ["hs_meeting_title"]

        raw = _paginate(
            f"https://api.hubapi.com/crm/v3/objects/{obj_type}",
            token,
            props,
        )
        for r in raw:
            p = r.get("properties", {})
            owner_id = str(p.get("hubspot_owner_id", ""))
            frames.append({
                "id": r["id"],
                "account": account_name,
                "tipo": type_label,
                "sdr": owners.get(owner_id, owner_id),
                "fecha": pd.to_datetime(p.get("hs_timestamp"), utc=True, errors="coerce"),
            })

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df["fecha_local"] = df["fecha"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["semana"] = df["fecha_local"].dt.isocalendar().week.astype(int)
    df["mes"] = df["fecha_local"].dt.to_period("M").astype(str)
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    df = df[df["fecha"] >= cutoff].copy()
    return df


# ─────────────────────────────────────────
#  Carga multi-cuenta
# ─────────────────────────────────────────

def load_all_accounts(secrets: dict, days: int = 90):
    """
    Recorre todas las cuentas configuradas y devuelve dicts con DataFrames consolidados.
    secrets debe ser el objeto st.secrets
    """
    accounts = _parse_accounts(secrets)

    all_calls = []
    all_contacts = []
    all_companies = []
    all_activities = []

    for acc in accounts:
        name = acc["name"]
        token = acc["token"]
        try:
            all_calls.append(get_calls(token, name, days))
            all_contacts.append(get_contacts(token, name, days))
            all_companies.append(get_companies(token, name, days))
            all_activities.append(get_activities(token, name, days))
        except Exception as e:
            st.warning(f"Error cargando cuenta '{name}': {e}")

    return {
        "calls": pd.concat(all_calls, ignore_index=True) if all_calls else pd.DataFrame(),
        "contacts": pd.concat(all_contacts, ignore_index=True) if all_contacts else pd.DataFrame(),
        "companies": pd.concat(all_companies, ignore_index=True) if all_companies else pd.DataFrame(),
        "activities": pd.concat(all_activities, ignore_index=True) if all_activities else pd.DataFrame(),
        "account_names": [a["name"] for a in accounts],
    }


def _parse_accounts(secrets) -> list:
    """Lee las cuentas desde st.secrets."""
    accounts = []
    i = 1
    while True:
        key = f"hubspot_account_{i}"
        if key not in secrets:
            break
        acc = secrets[key]
        accounts.append({
            "name": acc["name"],
            "token": acc["token"],
            "client": acc.get("client", acc["name"]),
        })
        i += 1
    return accounts
