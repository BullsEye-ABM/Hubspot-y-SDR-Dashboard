"""
HubSpot API Client - Multi-cuenta optimizado
Mejoras de performance:
  - Carga de cuentas en paralelo (ThreadPoolExecutor)
  - get_owners cacheado para no repetir la llamada
  - get_activities no repite fetch de llamadas (usa solo meetings + emails)
  - Paginación de 200 registros por página (antes era 100)
"""

import re
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
# Cache manual de owners: solo guarda resultados no vacíos y reintenta si falló
_owners_cache: dict = {}
# Cache de nombre interno de propiedad "SDR Asignado - [Cliente]"
_prop_name_cache: dict = {}


def _normalize_phone(phone) -> str:
    """Normaliza número de teléfono: solo dígitos, sin espacios ni símbolos."""
    if not phone:
        return ""
    return re.sub(r"\D", "", str(phone))


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

def get_owners(token: str) -> dict:
    """
    Devuelve dict {owner_id_str: nombre_completo}.
    Cache manual: solo guarda si la respuesta tiene datos (evita cachear errores).
    Pagina correctamente para cuentas con muchos owners.
    """
    # Devolver desde cache solo si tiene datos
    if token in _owners_cache and _owners_cache[token]:
        return _owners_cache[token]

    owners = {}
    try:
        after = None
        while True:
            params = {"limit": 100, "includeDeactivated": "true"}
            if after:
                params["after"] = after
            resp = requests.get(
                "https://api.hubapi.com/crm/v3/owners",
                headers=_headers(token),
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            for o in data.get("results", []):
                full_name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
                owners[str(o["id"])] = full_name or o.get("email", str(o["id"]))
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
    except Exception:
        pass

    # Solo cachear si obtuvimos resultados
    if owners:
        _owners_cache[token] = owners

    return owners


def _owner_name(owners: dict, owner_id) -> str:
    oid = str(owner_id) if owner_id else ""
    return owners.get(oid, oid) if oid else ""


# ─────────────────────────────────────────
#  SDR por propiedad de contacto
# ─────────────────────────────────────────

def _get_all_sdr_properties(token: str) -> list:
    """
    Devuelve los nombres internos de TODAS las propiedades de contacto
    cuya etiqueta contenga 'SDR Asignado' (ej: SDR Asignado - Lemu,
    SDR Asignado - Sovos, SDR Asignado - BullsEye, etc.).
    """
    cache_key = f"{token}:__all_sdr_props__"
    if cache_key in _prop_name_cache:
        return _prop_name_cache[cache_key]

    props = []
    try:
        resp = requests.get(
            "https://api.hubapi.com/crm/v3/properties/contacts",
            headers=_headers(token),
            timeout=30,
        )
        if resp.status_code == 200:
            for prop in resp.json().get("results", []):
                if "SDR Asignado" in prop.get("label", ""):
                    props.append(prop["name"])
    except Exception:
        pass

    _prop_name_cache[cache_key] = props
    return props


def _sdr_from_contact_props(props_dict: dict, sdr_prop_names: list) -> str:
    """Devuelve el primer valor no vacío entre las propiedades SDR del contacto."""
    for p in sdr_prop_names:
        val = (props_dict.get(p) or "").strip()
        if val:
            return val
    return ""


def _enrich_calls_with_sdr(token: str, df: pd.DataFrame, client_name: str) -> pd.DataFrame:
    """
    Enriquece las llamadas con el nombre real del SDR usando dos estrategias:

    1. Asociaciones call → contacto en HubSpot.
    2. Fallback por número de teléfono: busca contactos que tengan
       CUALQUIER propiedad 'SDR Asignado - *' rellena y empareja por teléfono.
    """
    if df.empty:
        return df

    sdr_props = _get_all_sdr_properties(token)
    if not sdr_props:
        return df

    df = df.copy()
    batch_size = 100

    # ── Estrategia 1: Asociaciones call → contacto ────────────────────────────
    call_ids = df["id"].astype(str).tolist()
    call_to_contact: dict = {}

    for i in range(0, len(call_ids), batch_size):
        batch = call_ids[i:i + batch_size]
        try:
            resp = requests.post(
                "https://api.hubapi.com/crm/v4/associations/calls/contacts/batch/read",
                headers=_headers(token),
                json={"inputs": [{"id": cid} for cid in batch]},
                timeout=30,
            )
            if resp.status_code == 200:
                for item in resp.json().get("results", []):
                    from_id = str(item["from"]["id"])
                    to_list = item.get("to", [])
                    if to_list:
                        call_to_contact[from_id] = str(to_list[0]["toObjectId"])
        except Exception:
            pass

    if call_to_contact:
        contact_ids = list(set(call_to_contact.values()))
        contact_to_sdr: dict = {}
        for i in range(0, len(contact_ids), batch_size):
            batch = contact_ids[i:i + batch_size]
            try:
                resp = requests.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/batch/read",
                    headers=_headers(token),
                    json={"inputs": [{"id": cid} for cid in batch],
                          "properties": sdr_props},
                    timeout=30,
                )
                if resp.status_code == 200:
                    for c in resp.json().get("results", []):
                        sdr = _sdr_from_contact_props(c.get("properties", {}), sdr_props)
                        if sdr:
                            contact_to_sdr[str(c["id"])] = sdr
            except Exception:
                pass

        sdr_map = {cid: contact_to_sdr[cid2]
                   for cid, cid2 in call_to_contact.items()
                   if cid2 in contact_to_sdr}
        enriched = df["id"].astype(str).map(sdr_map)
        df["sdr"] = enriched.where(enriched.notna() & (enriched != ""), df["sdr"])

    # ── Estrategia 2: Fallback por número de teléfono ─────────────────────────
    # Solo para llamadas que aún tienen un valor que parece ID numérico
    unresolved = df["sdr"].str.match(r"^\d+$", na=False) | df["sdr"].str.strip().eq("")
    if not unresolved.any():
        return df

    # Buscar contactos con CUALQUIER propiedad SDR rellena (OR entre filter groups)
    # HubSpot permite hasta 10 filter groups por request; partimos en lotes si hay más
    phone_to_sdr: dict = {}
    HUBSPOT_MAX_FG = 10
    prop_batches = [sdr_props[i:i+HUBSPOT_MAX_FG]
                    for i in range(0, len(sdr_props), HUBSPOT_MAX_FG)]

    for prop_batch in prop_batches:
        after = ""
        while True:
            try:
                body: dict = {
                    "filterGroups": [
                        {"filters": [{"propertyName": p, "operator": "HAS_PROPERTY"}]}
                        for p in prop_batch
                    ],
                    "properties": ["phone", "mobilephone"] + prop_batch,
                    "limit": 100,
                }
                if after:
                    body["after"] = after
                resp = requests.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/search",
                    headers=_headers(token),
                    json=body,
                    timeout=30,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                for c in data.get("results", []):
                    sdr = _sdr_from_contact_props(c.get("properties", {}), prop_batch)
                    if not sdr:
                        continue
                    for field in ("phone", "mobilephone"):
                        norm = _normalize_phone(c.get("properties", {}).get(field))
                        if norm and norm not in phone_to_sdr:
                            phone_to_sdr[norm] = sdr
                after = (data.get("paging", {}).get("next", {}) or {}).get("after", "")
                if not after or not data.get("results"):
                    break
            except Exception:
                break

    if phone_to_sdr:
        def _resolve(row):
            if not unresolved.loc[row.name]:
                return row["sdr"]
            norm = _normalize_phone(row.get("telefono_raw", ""))
            return phone_to_sdr.get(norm, row["sdr"])
        df["sdr"] = df.apply(_resolve, axis=1)

    return df


# ─────────────────────────────────────────
#  Llamadas
# ─────────────────────────────────────────

CALL_PROPS = [
    "hs_call_title", "hs_call_duration", "hs_call_status",
    "hs_call_disposition", "hs_call_body", "hs_call_recording_url",
    "hs_call_direction", "hubspot_owner_id", "hs_timestamp",
    "hs_call_to_number",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_calls(token: str, account_name: str, client_name: str = "", days: int = 90) -> pd.DataFrame:
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
            "sdr":          "",   # se rellena desde propiedades del contacto
            "estado":       p.get("hs_call_status", ""),
            "disposicion":  p.get("hs_call_disposition", ""),
            "duracion_seg": duration_sec,
            "duracion_min": round(duration_sec / 60, 1),
            "direccion":    p.get("hs_call_direction", ""),
            "titulo":       p.get("hs_call_title", ""),
            "notas":        p.get("hs_call_body", ""),
            "grabacion":    p.get("hs_call_recording_url", ""),
            "telefono_raw": p.get("hs_call_to_number", ""),
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

    # Enriquecer con SDR real desde propiedades de contacto (todas las 'SDR Asignado - *')
    df = _enrich_calls_with_sdr(token, df, client_name)
    # Limpiar sdr: si sigue siendo un ID numérico, dejarlo vacío
    df["sdr"] = df["sdr"].apply(lambda x: "" if str(x).strip().isdigit() else x)
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
    client = acc.get("client", name)
    try:
        return {
            "name":       name,
            "calls":      get_calls(token, name, client, days),
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
