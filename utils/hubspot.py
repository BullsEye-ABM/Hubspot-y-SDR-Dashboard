"""
HubSpot API client for the Bullseye dashboard (Ventas / deals pipeline).
Single-account. Caches results 15 minutes via Streamlit's st.cache_data.
"""

from __future__ import annotations

import requests
import streamlit as st
from typing import Any

API_BASE = "https://api.hubapi.com"
CACHE_TTL = 900  # 15 minutes


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


@st.cache_data(ttl=CACHE_TTL, show_spinner="Cargando notas de reuniones DIIO...")
def get_deal_notes(deal_ids: tuple) -> dict[str, list[dict]]:
    """
    Fetch DIIO meeting notes from HubSpot for each deal.
    DIIO creates a NOTE engagement on the deal after each meeting,
    with body containing rich HTML summary (starts with 'Fuente: Reunión').
    Returns: {deal_id: [note_dict, ...]}
    """
    import re as _re
    token = _get_token()
    if not deal_ids:
        return {}

    result: dict[str, list[dict]] = {}

    for did in deal_ids:
        try:
            r = requests.get(
                f"{API_BASE}/engagements/v1/engagements/associated/deal/{did}/paged",
                headers=_headers(token),
                params={"limit": 100},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            notes = []
            for item in r.json().get("results", []):
                eng = item.get("engagement", {})
                if eng.get("type") != "NOTE":
                    continue
                body = item.get("metadata", {}).get("body", "") or ""
                # Strip HTML to check content quality
                plain = _re.sub(r"<[^>]+>", " ", body).strip()
                if len(plain) < 150:
                    continue
                # Skip LinkedIn/automation notes
                plain_lower = plain.lower()
                if any(s in plain_lower for s in ["linkedin", "campaign:", "lemlist"]):
                    continue
                notes.append({
                    "id": str(eng.get("id", "")),
                    "title": "Reunión DIIO",
                    "summary": body,
                    "body": body,
                    "timestamp": str(eng.get("createdAt", "") or ""),
                })
            if notes:
                notes.sort(key=lambda x: x["timestamp"], reverse=True)
                result[did] = notes
        except Exception:
            pass

    return result
