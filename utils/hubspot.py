"""
HubSpot API Client - Multi-cuenta optimizado
Mejoras de performance:
  - Carga de cuentas en paralelo (ThreadPoolExecutor)
  - get_owners cacheado para no repetir la llamada
  - get_activities no repite fetch de llamadas (usa solo meetings + emails)
  - Paginación de 200 registros por página (antes era 100)
"""

import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache


# ─────────────────────────────────────────
#  Helpers internos
# ─────────────────────────────────────────

def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _since_ms(days: int) -> int:
    return int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)


def _search(obj_type: str, token: str, properties: list,
            filter_property: str, days: int, limit: int = 200) -> list:
    """
    Búsqueda con filtro de fecha en la API.
    Limit = 200 (máximo de HubSpot) → menos peticiones de paginación.
    """
    url   = f"https://api.hubapi.com/crm/v3/objects/{obj_type}/search"
    since = _since_ms(days)

    body = {
        "filterGroups": [{
            "filters": [{
                "propertyName": filter_property,
                "operator":     "GTE",
                "value":        str(since),
            }]
        }],
        "properties": properties,
        "limit":      limit,
        "after":      0,
    }

    results = []
    while True:
        try:
            resp = requests.post(url, headers=_headers(token), json=body, timeout=30)
        except Exception:
            break
        if resp.status_code != 200:
            break
        data = resp.json()
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        body["after"] = after

    return results


# ─────────────────────────────────────────
#  Owners (SDRs) — cacheado para no repetir
# ─────────────────────────────────────────

@lru_cache(maxsize=32)
def get_owners(token: str) -> dict:
    """
    Devuelve dict {owner_id_str: nombre_completo}.
    Usa lru_cache (Python puro) en vez de @st.cache_data para que funcione
    correctamente cuando se llama desde dentro de otras funciones cacheadas.
    """
    try:
        resp = requests.get(
            "https://api.hubapi.com/crm/v3/owners",
            headers=_headers(token),
            timeout=30,
        )
        owners = {}
        if resp.status_code == 200:
            for o in resp.json().get("results", []):
                full_name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
                owners[str(o["id"])] = full_name or o.get("email", str(o["id"]))
        return owners
    except Exception:
        return {}


def _owner_name(owners: dict, owner_id) -> str:
    oid = str(owner_id) if owner_id else ""
    return owners.get(oid, oid) if oid else ""


# ─────────────────────────────────────────
#  Llamadas
# ─────────────────────────────────────────

CALL_PROPS = [
    "hs_call_title", "hs_call_duration", "hs_call_status",
    "hs_call_disposition", "hs_call_body", "hs_call_recording_url",
    "hs_call_direction", "hubspot_owner_id", "hs_timestamp",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_calls(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    raw    = _search("calls", token, CALL_PROPS, "hs_timestamp", days)
    owners = get_owners(token)
    if not raw:
        return pd.DataFrame()

    rows = []
    for r in raw:
        p            = r.get("properties", {})
        duration_ms  = p.get("hs_call_duration")
        duration_sec = int(duration_ms) / 1000 if duration_ms else 0
        rows.append({
            "id":           r["id"],
            "account":      account_name,
            "fecha":        pd.to_datetime(p.get("hs_timestamp"), utc=True, errors="coerce"),
            "sdr":          _owner_name(owners, p.get("hubspot_owner_id")),
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
    df["dia"]         = df["fecha_local"].dt.date
    df["hora"]        = df["fecha_local"].dt.hour
    df["semana"]      = df["fecha_local"].dt.isocalendar().week.astype(int)
    df["mes"]         = df["fecha_local"].dt.to_period("M").astype(str)
    df["conectada"]   = df["estado"].str.upper() == "COMPLETED"
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
    raw    = _search("contacts", token, CONTACT_PROPS, "createdate", days)
    owners = get_owners(token)
    if not raw:
        return pd.DataFrame()

    rows = []
    for r in raw:
        p = r.get("properties", {})
        rows.append({
            "id":             r["id"],
            "account":        account_name,
            "nombre":         f"{p.get('firstname', '')} {p.get('lastname', '')}".strip(),
            "email":          p.get("email", ""),
            "empresa":        p.get("company", ""),
            "cargo":          p.get("jobtitle", ""),
            "sdr":            _owner_name(owners, p.get("hubspot_owner_id")),
            "fecha_creacion": pd.to_datetime(p.get("createdate"), utc=True, errors="coerce"),
            "estado_lead":    p.get("hs_lead_status", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_local"] = df["fecha_creacion"].dt.tz_convert("America/Santiago")
    df["mes"]         = df["fecha_local"].dt.to_period("M").astype(str)
    return df


# ─────────────────────────────────────────
#  Empresas
# ─────────────────────────────────────────

COMPANY_PROPS = [
    "name", "domain", "industry", "city", "country",
    "hubspot_owner_id", "createdate", "numberofemployees",
    "cliente_bullseye_empresa",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_companies(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    raw    = _search("companies", token, COMPANY_PROPS, "createdate", days)
    owners = get_owners(token)
    if not raw:
        return pd.DataFrame()

    rows = []
    for r in raw:
        p = r.get("properties", {})
        rows.append({
            "id":               r["id"],
            "account":          account_name,
            "empresa":          p.get("name", ""),
            "industria":        p.get("industry", ""),
            "ciudad":           p.get("city", ""),
            "sdr":              _owner_name(owners, p.get("hubspot_owner_id")),
            "cliente_bullseye": p.get("cliente_bullseye_empresa", ""),
            "fecha_creacion":   pd.to_datetime(p.get("createdate"), utc=True, errors="coerce"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha_local"] = df["fecha_creacion"].dt.tz_convert("America/Santiago")
    df["mes"]         = df["fecha_local"].dt.to_period("M").astype(str)
    return df


# ─────────────────────────────────────────
#  Actividades (solo Meetings + Emails, no Calls porque ya se cargan)
# ─────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_activities(token: str, account_name: str, days: int = 90) -> pd.DataFrame:
    """
    Carga meetings y emails de HubSpot.
    Las llamadas NO se incluyen aquí (ya vienen de get_calls) para evitar
    duplicar la descarga. En la página de Actividades se unen ambos.
    """
    owners = get_owners(token)
    frames = []

    type_config = {
        "meetings": ("Reunión HubSpot", "hs_timestamp", ["hubspot_owner_id", "hs_timestamp", "hs_meeting_title"]),
        "emails":   ("Email",           "hs_timestamp", ["hubspot_owner_id", "hs_timestamp"]),
    }

    for obj_type, (label, filter_prop, props) in type_config.items():
        raw = _search(obj_type, token, props, filter_prop, days)
        for r in raw:
            p = r.get("properties", {})
            frames.append({
                "id":      r["id"],
                "account": account_name,
                "tipo":    label,
                "sdr":     _owner_name(owners, p.get("hubspot_owner_id")),
                "fecha":   pd.to_datetime(p.get("hs_timestamp"), utc=True, errors="coerce"),
            })

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames).dropna(subset=["fecha"])
    df["fecha_local"] = df["fecha"].dt.tz_convert("America/Santiago")
    df["dia"]         = df["fecha_local"].dt.date
    df["semana"]      = df["fecha_local"].dt.isocalendar().week.astype(int)
    df["mes"]         = df["fecha_local"].dt.to_period("M").astype(str)
    return df


# ─────────────────────────────────────────
#  Carga multi-cuenta EN PARALELO
# ─────────────────────────────────────────

def _load_single_account(acc: dict, days: int) -> dict:
    """Carga los 4 datasets de una sola cuenta."""
    name, token = acc["name"], acc["token"]
    try:
        return {
            "name":       name,
            "calls":      get_calls(token, name, days),
            "contacts":   get_contacts(token, name, days),
            "companies":  get_companies(token, name, days),
            "activities": get_activities(token, name, days),
        }
    except Exception as e:
        return {
            "name":       name,
            "calls":      pd.DataFrame(),
            "contacts":   pd.DataFrame(),
            "companies":  pd.DataFrame(),
            "activities": pd.DataFrame(),
            "error":      str(e),
        }


def load_all_accounts(secrets, days: int = 90) -> dict:
    """
    Carga todas las cuentas HubSpot EN PARALELO.
    Cada cuenta se carga en su propio thread, reduciendo el tiempo total
    de N×T a ~T (donde T es el tiempo de la cuenta más lenta).
    """
    accounts = _parse_accounts(secrets)

    all_calls, all_contacts, all_companies, all_activities = [], [], [], []

    # Carga paralela — un thread por cuenta
    with ThreadPoolExecutor(max_workers=min(len(accounts), 6)) as executor:
        future_to_acc = {
            executor.submit(_load_single_account, acc, days): acc
            for acc in accounts
        }
        for future in as_completed(future_to_acc):
            result = future.result()
            if "error" in result:
                st.warning(f"Error cargando cuenta '{result['name']}': {result['error']}")
            all_calls.append(result["calls"])
            all_contacts.append(result["contacts"])
            all_companies.append(result["companies"])
            all_activities.append(result["activities"])

    def safe_concat(frames):
        valid = [f for f in frames if not f.empty]
        return pd.concat(valid, ignore_index=True) if valid else pd.DataFrame()

    return {
        "calls":         safe_concat(all_calls),
        "contacts":      safe_concat(all_contacts),
        "companies":     safe_concat(all_companies),
        "activities":    safe_concat(all_activities),
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
