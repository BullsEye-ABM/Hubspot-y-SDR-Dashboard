"""
HubSpot API client for the Bullseye SDR dashboard.
Single-account. Caches results 15 minutes via Streamlit's st.cache_data.
"""

from __future__ import annotations

import requests
import streamlit as st
from typing import Any

API_BASE = "https://api.hubapi.com"
CACHE_TTL = 900  # 15 minutes

# Disposition UUID -> human label (from HubSpot Call outcome property)
DISPOSITION_LABELS = {
    "9d9162e7-6cf3-4944-bf63-4dff82258764": "Ocupado",
    "f240bbac-87c9-4f6e-bf70-924b57d47db7": "Conectado",
    "a4c4c377-d246-4b32-a13b-75a56a4cd0ff": "Dejo mensaje en directo",
    "b2cf5968-551e-4856-9783-52b3da59a7d0": "Dejo mensaje de voz",
    "73a0d17f-1163-4015-bdd5-ec830791da20": "Sin respuesta",
    "17b47fee-58de-441e-a44c-c6300d46f273": "Numero incorrecto",
}

# Numbers to filter out as 2FA / verification noise
KNOWN_2FA_NUMBERS = {"+14157234000"}


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _get_token() -> str:
    """Read token from Streamlit secrets."""
    try:
        return st.secrets["hubspot"]["private_app_token"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Token de HubSpot no configurado. "
            "Edita `.streamlit/secrets.toml` con `[hubspot]` -> `private_app_token`."
        )
        st.stop()


# -----------------------------------------
#  Owners
# -----------------------------------------

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def list_owners() -> list[dict[str, Any]]:
    """Return all active owners. Each: {id, name, email}."""
    token = _get_token()
    owners: list[dict] = []
    after: str | None = None

    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        r = requests.get(
            f"{API_BASE}/crm/v3/owners",
            headers=_headers(token),
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        for o in data.get("results", []):
            full_name = f"{o.get('firstName','').strip()} {o.get('lastName','').strip()}".strip()
            owners.append({
                "id": str(o["id"]),
                "name": full_name or o.get("email", f"Owner {o['id']}"),
                "email": o.get("email", ""),
            })
        paging = data.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break

    owners.sort(key=lambda x: x["name"].lower())
    return owners


# -----------------------------------------
#  Generic CRM search with date filter
# -----------------------------------------

def _search(
    object_type: str,
    properties: list[str],
    owner_id: str,
    date_property: str,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    """Paginated CRM v3 search with owner + date range filters."""
    token = _get_token()
    url = f"{API_BASE}/crm/v3/objects/{object_type}/search"
    results: list[dict] = []
    after = 0

    while True:
        body = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
                    {"propertyName": date_property, "operator": "GTE", "value": str(start_ms)},
                    {"propertyName": date_property, "operator": "LTE", "value": str(end_ms)},
                ]
            }],
            "properties": properties,
            "limit": 200,
            "after": after,
            "sorts": [{"propertyName": date_property, "direction": "DESCENDING"}],
        }
        r = requests.post(url, headers=_headers(token), json=body, timeout=60)
        if r.status_code != 200:
            st.warning(f"HubSpot {object_type} status {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        results.extend(data.get("results", []))
        paging = data.get("paging", {}).get("next", {})
        after_str = paging.get("after")
        if not after_str:
            break
        after = int(after_str)

    return results


# -----------------------------------------
#  Public fetchers (cached)
# -----------------------------------------

@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando llamadas...")
def get_calls(owner_id: str, start_ms: int, end_ms: int) -> list[dict]:
    """Return call objects with key properties."""
    props = [
        "hs_call_title", "hs_call_body", "hs_call_summary",
        "hs_call_disposition", "hs_call_duration", "hs_call_direction",
        "hs_call_status", "hs_timestamp", "hs_call_from_number",
        "hs_call_to_number", "hs_call_recording_url",
    ]
    raw = _search("calls", props, owner_id, "hs_timestamp", start_ms, end_ms)
    out = []
    for r in raw:
        p = r.get("properties", {})
        # Filter out 2FA / verification calls
        if p.get("hs_call_from_number") in KNOWN_2FA_NUMBERS:
            continue
        out.append({
            "id": r["id"],
            "title": p.get("hs_call_title") or "",
            "body": p.get("hs_call_body") or "",
            "summary": p.get("hs_call_summary") or "",
            "disposition": DISPOSITION_LABELS.get(p.get("hs_call_disposition") or "", "Sin disposicion"),
            "duration_ms": int(p.get("hs_call_duration") or 0),
            "direction": p.get("hs_call_direction") or "",
            "status": p.get("hs_call_status") or "",
            "timestamp": p.get("hs_timestamp") or "",
            "from_number": p.get("hs_call_from_number") or "",
            "to_number": p.get("hs_call_to_number") or "",
        })
    return out


@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando contactos...")
def get_contacts(owner_id: str, start_ms: int, end_ms: int) -> list[dict]:
    props = ["firstname", "lastname", "email", "createdate", "lifecyclestage"]
    raw = _search("contacts", props, owner_id, "createdate", start_ms, end_ms)
    return [{"id": r["id"], **r.get("properties", {})} for r in raw]


@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando empresas...")
def get_companies(owner_id: str, start_ms: int, end_ms: int) -> list[dict]:
    props = ["name", "domain", "createdate"]
    raw = _search("companies", props, owner_id, "createdate", start_ms, end_ms)
    return [{"id": r["id"], **r.get("properties", {})} for r in raw]


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def count_owned_total(object_type: str, owner_id: str) -> int:
    """Total objects owned by user (no date filter)."""
    token = _get_token()
    url = f"{API_BASE}/crm/v3/objects/{object_type}/search"
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id}
        ]}],
        "limit": 1,
    }
    r = requests.post(url, headers=_headers(token), json=body, timeout=30)
    if r.status_code != 200:
        return 0
    return r.json().get("total", 0)


# -----------------------------------------
#  Deals / Pipeline (Ventas)
# -----------------------------------------

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_pipelines() -> tuple[list[dict], str]:
    """
    Return (pipelines, error_message).
    error_message is "" on success, otherwise contains the API error detail.
    """
    token = _get_token()
    try:
        r = requests.get(
            f"{API_BASE}/crm/v3/pipelines/deals",
            headers=_headers(token),
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("results", []), ""
        return [], f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return [], str(e)


@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando negocios...")
def get_deals_by_pipeline(pipeline_id: str) -> list[dict]:
    """Return ALL deals from a specific pipeline (no date filter)."""
    token = _get_token()
    url = f"{API_BASE}/crm/v3/objects/deals/search"
    props = [
        "dealname", "dealstage", "pipeline", "hubspot_owner_id",
        "createdate", "closedate", "amount", "hs_lastmodifieddate",
        "hs_deal_stage_probability", "notes_last_contacted",
        "num_associated_contacts",
    ]
    results = []
    after = 0
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "EQ", "value": pipeline_id},
            ]}],
            "properties": props,
            "limit": 200,
            "after": after,
            "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "DESCENDING"}],
        }
        r = requests.post(url, headers=_headers(token), json=body, timeout=60)
        if r.status_code != 200:
            st.warning(f"HubSpot deals {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        results.extend(data.get("results", []))
        after_str = (data.get("paging") or {}).get("next", {}).get("after")
        if not after_str:
            break
        after = int(after_str)
    return results


@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando transcripciones DIIO...")
def get_deal_calls(deal_ids: tuple) -> dict[str, list[dict]]:
    """
    Return calls (with DIIO summaries) associated with deals.
    deal_ids must be a tuple for st.cache_data hashing.
    Returns: {deal_id: [call_dict, ...]}
    """
    token = _get_token()
    if not deal_ids:
        return {}

    batch_size = 100
    deal_to_call_ids: dict[str, list[str]] = {}

    # Step 1: Get call IDs associated with each deal
    for i in range(0, len(deal_ids), batch_size):
        batch = list(deal_ids[i:i + batch_size])
        try:
            r = requests.post(
                f"{API_BASE}/crm/v4/associations/deals/calls/batch/read",
                headers=_headers(token),
                json={"inputs": [{"id": did} for did in batch]},
                timeout=30,
            )
            if r.status_code == 200:
                for item in r.json().get("results", []):
                    did = str(item["from"]["id"])
                    cids = [str(a["toObjectId"]) for a in item.get("to", [])]
                    if cids:
                        deal_to_call_ids[did] = cids
        except Exception:
            pass

    # Step 1b: For deals with no direct call associations, look via contacts
    deals_without_calls = [did for did in deal_ids if did not in deal_to_call_ids]
    if deals_without_calls:
        deal_to_contact_ids: dict[str, list[str]] = {}
        for i in range(0, len(deals_without_calls), batch_size):
            batch = list(deals_without_calls[i:i + batch_size])
            try:
                r = requests.post(
                    f"{API_BASE}/crm/v4/associations/deals/contacts/batch/read",
                    headers=_headers(token),
                    json={"inputs": [{"id": did} for did in batch]},
                    timeout=30,
                )
                if r.status_code == 200:
                    for item in r.json().get("results", []):
                        did = str(item["from"]["id"])
                        cids = [str(a["toObjectId"]) for a in item.get("to", [])]
                        if cids:
                            deal_to_contact_ids[did] = cids
            except Exception:
                pass

        all_contact_ids = list({cid for cids in deal_to_contact_ids.values() for cid in cids})
        contact_to_call_ids: dict[str, list[str]] = {}
        for i in range(0, len(all_contact_ids), batch_size):
            batch = all_contact_ids[i:i + batch_size]
            try:
                r = requests.post(
                    f"{API_BASE}/crm/v4/associations/contacts/calls/batch/read",
                    headers=_headers(token),
                    json={"inputs": [{"id": cid} for cid in batch]},
                    timeout=30,
                )
                if r.status_code == 200:
                    for item in r.json().get("results", []):
                        cid = str(item["from"]["id"])
                        call_ids = [str(a["toObjectId"]) for a in item.get("to", [])]
                        if call_ids:
                            contact_to_call_ids[cid] = call_ids
            except Exception:
                pass

        for did, contact_ids in deal_to_contact_ids.items():
            extra_calls = [c for cid in contact_ids for c in contact_to_call_ids.get(cid, [])]
            if extra_calls:
                deal_to_call_ids.setdefault(did, [])
                deal_to_call_ids[did].extend(extra_calls)

    if not deal_to_call_ids:
        return {}

    # Step 2: Fetch call details in batches
    all_call_ids = list({cid for cids in deal_to_call_ids.values() for cid in cids})
    call_details: dict[str, dict] = {}

    for i in range(0, len(all_call_ids), batch_size):
        batch = all_call_ids[i:i + batch_size]
        try:
            r = requests.post(
                f"{API_BASE}/crm/v3/objects/calls/batch/read",
                headers=_headers(token),
                json={
                    "inputs": [{"id": cid} for cid in batch],
                    "properties": [
                        "hs_call_title", "hs_call_body", "hs_call_summary",
                        "hs_timestamp", "hs_call_disposition", "hs_call_duration",
                    ],
                },
                timeout=60,
            )
            if r.status_code == 200:
                for call in r.json().get("results", []):
                    call_details[str(call["id"])] = call.get("properties", {})
        except Exception:
            pass

    # Step 3: Build deal -> calls mapping (sorted newest first)
    result: dict[str, list[dict]] = {}
    for did, cids in deal_to_call_ids.items():
        calls = []
        for cid in cids:
            cd = call_details.get(cid)
            if not cd:
                continue
            summary = cd.get("hs_call_summary") or ""
            body = cd.get("hs_call_body") or ""
            if summary or body:
                calls.append({
                    "id": cid,
                    "title": cd.get("hs_call_title") or "Llamada",
                    "summary": summary,
                    "body": body,
                    "timestamp": cd.get("hs_timestamp") or "",
                    "disposition": DISPOSITION_LABELS.get(
                        cd.get("hs_call_disposition") or "", "Sin disposicion"
                    ),
                    "duration_ms": int(cd.get("hs_call_duration") or 0),
                })
        if calls:
            calls.sort(key=lambda x: x["timestamp"], reverse=True)
            result[did] = calls

    return result
