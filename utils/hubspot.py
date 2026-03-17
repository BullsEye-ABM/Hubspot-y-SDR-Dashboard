"""
HubSpot API Client - Multi-cuenta con filtro de fechas en la API
Usa el endpoint de búsqueda (/search) para traer solo los registros
del período seleccionado, en vez de bajar todo el historial.
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


def _since_ms(days: int) -> int:
    """Retorna timestamp en milisegundos de hace N días."""
    return int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)


def _search(obj_type: str, token: str, properties: list,
            filter_property: str, days: int, limit: int = 100) -> list:
    """
    Usa el endpoint de búsqueda de HubSpot para traer solo registros
    más recientes que N días. Maneja paginación automáticamente.
    """
    url = f"https://api.hubapi.com/crm/v3/objects/{obj_type}/search"
    since = _since_ms(days)

    body = {
        "filterGroups": [{
            "filters": [{
                "propertyName": filter_property,
                "operator": "GTE",
                "value": str(since),
            }]
        }],
        "properties": properties,
        "limit": limit,
        "after": 0,
    }

    results = []
    while True:
        resp = requests.post(url, headers=_headers(token), json=body, timeout=30)
        if resp.status_code != 200:
            break
        data = resp.json()
        results.extend(data.get("results", []))
        paging = data.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break
        body["after"] = after

    return results


# ─────────────────────────────────────────
#  Owners (SDRs)
# ─────────────────────────────────────────

def get_owners(token: str) -> dict:
    """
    Devuelve dict {owner_id: nombre_completo}.
    Sin @st.cache_data porque se llama desde dentro de funciones ya cacheadas.
    """
    resp = requests.get(
        "https://api.hubapi.com/crm/v3/owners",
        headers=_headers(token),
        timeout=30,
    )
    owners = {}
    if resp.status_code == 200:
        for o in resp.json().get("results", []):
            full_name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
            name = full_name or o.get("email", "")
            # Guardar por id numérico (como string) y como string directo
            owners[str(o["id"])] = name
    return owners


# ─────────────────────────────────────────
#  Llamadas
# ─────────────────────────────────────────

CALL_PROPS = [
    "hs_call_title",
    "hs_call_duration",
    "hs_call_status",
    "hs_call_disposition",
    "hs_call_body",
    "hs_call_recording_url",
    "hs_call_direction",
    "hubspot_owner_id",
    "hs_timestamp",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_calls(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    raw = _search("calls", token, CALL_PROPS, "hs_timestamp", days)
    if not raw:
        return pd.DataFrame()

    owners = get_owners(token)
    rows = []
    for r in raw:
        p = r.get("properties", {})
        duration_ms = p.get("hs_call_duration")
        duration_sec = int(duration_ms) / 1000 if duration_ms else 0
        owner_id = str(p.get("hubspot_owner_id", ""))
        rows.append({
            "id":           r["id"],
            "account":      account_name,
            "fecha":        pd.to_datetime(p.get("hs_timestamp"), utc=True, errors="coerce"),
            "sdr":          owners.get(owner_id, owner_id),
            "estado":       p.get("hs_call_status", ""),
            "disposicion":  p.get("hs_call_disposition", ""),
            "duracion_seg": duration_sec,
            "duracion_min": round(duration_sec / 60, 1),
            "direccion":    p.get("hs_call_direction", ""),
            "titulo":       p.get("hs_call_title", ""),
            "notas":        p.get("hs_call_body", ""),
            "grabacion":    p.get("hs_call_recording_url", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["fecha_local"] = df["fecha"].dt.tz_convert("America/Santiago")
    df["dia"]    = df["fecha_local"].dt.date
    df["hora"]   = df["fecha_local"].dt.hour
    df["semana"] = df["fecha_local"].dt.isocalendar().week.astype(int)
    df["mes"]    = df["fecha_local"].dt.to_period("M").astype(str)
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
    raw = _search("contacts", token, CONTACT_PROPS, "createdate", days)
    if not raw:
        return pd.DataFrame()

    owners = get_owners(token)
    rows = []
    for r in raw:
        p = r.get("properties", {})
        owner_id = str(p.get("hubspot_owner_id", ""))
        rows.append({
            "id":             r["id"],
            "account":        account_name,
            "nombre":         f"{p.get('firstname', '')} {p.get('lastname', '')}".strip(),
            "email":          p.get("email", ""),
            "empresa":        p.get("company", ""),
            "cargo":          p.get("jobtitle", ""),
            "sdr":            owners.get(owner_id, owner_id),
            "fecha_creacion": pd.to_datetime(p.get("createdate"), utc=True, errors="coerce"),
            "estado_lead":    p.get("hs_lead_status", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_local"] = df["fecha_creacion"].dt.tz_convert("America/Santiago")
    df["mes"] = df["fecha_local"].dt.to_period("M").astype(str)
    return df


# ─────────────────────────────────────────
#  Empresas
# ─────────────────────────────────────────

COMPANY_PROPS = [
    "name", "domain", "industry", "city", "country",
    "hubspot_owner_id", "createdate", "numberofemployees",
    "cliente_bullseye_empresa",   # propiedad personalizada BullsEye
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_companies(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    raw = _search("companies", token, COMPANY_PROPS, "createdate", days)
    if not raw:
        return pd.DataFrame()

    owners = get_owners(token)
    rows = []
    for r in raw:
        p = r.get("properties", {})
        owner_id = str(p.get("hubspot_owner_id", ""))
        rows.append({
            "id":                     r["id"],
            "account":                account_name,
            "empresa":                p.get("name", ""),
            "industria":              p.get("industry", ""),
            "ciudad":                 p.get("city", ""),
            "sdr":                    owners.get(owner_id, owner_id),
            "cliente_bullseye":       p.get("cliente_bullseye_empresa", ""),
            "fecha_creacion":         pd.to_datetime(p.get("createdate"), utc=True, errors="coerce"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_local"] = df["fecha_creacion"].dt.tz_convert("America/Santiago")
    df["mes"] = df["fecha_local"].dt.to_period("M").astype(str)
    return df


# ─────────────────────────────────────────
#  Actividades (Calls + Meetings + Emails)
# ─────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_activities(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    owners = get_owners(token)
    frames = []

    type_config = {
        "calls":    ("Llamada",  "hs_timestamp",  ["hubspot_owner_id", "hs_timestamp", "hs_call_status"]),
        "meetings": ("Reunión",  "hs_timestamp",  ["hubspot_owner_id", "hs_timestamp", "hs_meeting_title"]),
        "emails":   ("Email",    "hs_timestamp",  ["hubspot_owner_id", "hs_timestamp"]),
    }

    for obj_type, (label, filter_prop, props) in type_config.items():
        raw = _search(obj_type, token, props, filter_prop, days)
        for r in raw:
            p = r.get("properties", {})
            owner_id = str(p.get("hubspot_owner_id", ""))
            frames.append({
                "id":      r["id"],
                "account": account_name,
                "tipo":    label,
                "sdr":     owners.get(owner_id, owner_id),
                "fecha":   pd.to_datetime(p.get("hs_timestamp"), utc=True, errors="coerce"),
            })

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames).dropna(subset=["fecha"])
    df["fecha_local"] = df["fecha"].dt.tz_convert("America/Santiago")
    df["dia"]    = df["fecha_local"].dt.date
    df["semana"] = df["fecha_local"].dt.isocalendar().week.astype(int)
    df["mes"]    = df["fecha_local"].dt.to_period("M").astype(str)
    return df


# ─────────────────────────────────────────
#  Carga multi-cuenta
# ─────────────────────────────────────────

def load_all_accounts(secrets: dict, days: int = 90):
    accounts = _parse_accounts(secrets)

    all_calls, all_contacts, all_companies, all_activities = [], [], [], []

    for acc in accounts:
        name, token = acc["name"], acc["token"]
        try:
            all_calls.append(get_calls(token, name, days))
            all_contacts.append(get_contacts(token, name, days))
            all_companies.append(get_companies(token, name, days))
            all_activities.append(get_activities(token, name, days))
        except Exception as e:
            st.warning(f"Error cargando cuenta '{name}': {e}")

    return {
        "calls":         pd.concat(all_calls,      ignore_index=True) if all_calls      else pd.DataFrame(),
        "contacts":      pd.concat(all_contacts,   ignore_index=True) if all_contacts   else pd.DataFrame(),
        "companies":     pd.concat(all_companies,  ignore_index=True) if all_companies  else pd.DataFrame(),
        "activities":    pd.concat(all_activities, ignore_index=True) if all_activities else pd.DataFrame(),
        "account_names": [a["name"] for a in accounts],
    }


def _parse_accounts(secrets) -> list:
    accounts = []
    i = 1
    while True:
        key = f"hubspot_account_{i}"
        if key not in secrets:
            break
        acc = secrets[key]
        accounts.append({
            "name":   acc["name"],
            "token":  acc["token"],
            "client": acc.get("client", acc["name"]),
        })
        i += 1
    return accounts
