"""
Google Sheets Reader — versión simple con API Key
No requiere Service Account. Solo necesitas:
  1. El sheet compartido como "Cualquiera con el link puede ver"
  2. Una Google API Key (sin service account)

Sheet: "Metas equipo BullsEye / reuniones / oportunidades"
Pestaña: "Gestión de reuniones"
"""

import unicodedata
import requests
import pandas as pd
import streamlit as st


# ── Mapeo de columnas: nombre_interno → posibles nombres en el sheet ──────────
# Cada clave interna puede tener MÚLTIPLES variantes posibles del encabezado.
COLUMN_MAP = {
    "cliente":            ["Cliente"],
    "origen":             ["Origen"],
    "sdr":                ["Responsable", "SDR", "Responsable SDR"],
    "empresa":            ["Empresa"],
    "contacto":           ["Contactos/Correo", "Contacto", "Correo"],
    "fecha_agendamiento": ["Fecha de agendamiento", "Fecha agendamiento", "Fecha Agendamiento"],
    "fecha_reunion":      ["Fecha de la reunión", "Fecha reunión", "Fecha de la reunion",
                           "Fecha de la reunión reserva", "Fecha Reunion"],
    "hora":               ["Hora"],
    "prospecto":          ["Prospecto"],
    "pais":               ["País", "Pais", "País "],
    "realizado":          ["Realizado", "Realizada"],
    "ejecutivo":          ["Ejecutivo"],
    "propuesta":          ["Propuesta/Oportunidad", "Propuesta", "Oportunidad"],
    "piloto":             ["Piloto"],
    "mes_agenda":         ["Mes agenda Reunion Fecha", "Mes Agenda"],
    "mes_reunion":        ["Mes de la reunión", "Mes de la reunion", "Mes reunión"],
    "cargo":              ["CARGO", "Cargo"],
    "telefono":           ["TELEFONO", "Teléfono", "Telefono"],
    "asiste":             ["Asiste a Reunión", "Asiste a Reunion", "Asiste"],
    "link_hubspot":       ["Link de Hubspot", "HubSpot", "Link Hubspot"],
    "kam":                ["KAM", "Kam"],
    "comentarios":        ["Comentarios", "COMENTARIOS"],
    "fuente":             ["Fuente Campaña", "Fuente Campana", "Fuente campaña"],
    "comentario":         ["COMENTARIO", "Comentario"],
    "comentario_ih":      ["comentario IH", "Comentario IH"],
    "flota":              ["Flota informada", "Flota"],
}


def _normalizar(texto: str) -> str:
    """Minúsculas + sin tildes para comparación flexible."""
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower().strip()


def _build_rename_map(sheet_cols: list[str]) -> dict[str, str]:
    """
    Construye el dict {columna_sheet: nombre_interno} probando:
    1. Coincidencia exacta con alguna de las variantes
    2. Coincidencia normalizada (sin tildes, minúsculas)
    """
    rename = {}
    for interno, variantes in COLUMN_MAP.items():
        variantes_norm = {_normalizar(v): v for v in variantes}
        for col in sheet_cols:
            if col in variantes:                   # exacto
                rename[col] = interno
                break
            if _normalizar(col) in variantes_norm:  # normalizado
                rename[col] = interno
                break
    return rename


@st.cache_data(ttl=1800, show_spinner=False)
def get_meetings_from_sheets(_secrets) -> pd.DataFrame:
    """
    Lee el Google Sheet de reuniones usando solo una API Key de Google.
    El sheet debe estar compartido como 'Cualquiera con el link puede ver'.
    El parámetro empieza con _ para que Streamlit no intente hashearlo.
    """
    try:
        sheet_id  = _secrets["google_sheets"]["sheet_id"]
        tab_name  = _secrets["google_sheets"].get("worksheet_name", "Gestión Reuniones")
        api_key   = _secrets["google_sheets"]["api_key"]
    except KeyError as e:
        st.error(f"Falta configuración en secrets.toml: {e}")
        return pd.DataFrame()

    import io

    # ── Paso 1: Obtener el ID numérico (gid) de la pestaña via metadatos ──────
    # Esto evita los problemas de encoding con tildes en el nombre.
    # La API de metadatos sí acepta la API key sin problemas.
    gid = 0  # gid 0 = primera pestaña (fallback)
    try:
        meta_resp = requests.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
            params={"key": api_key, "fields": "sheets.properties"},
            timeout=30,
        )
        if meta_resp.status_code == 200:
            for sheet in meta_resp.json().get("sheets", []):
                props = sheet.get("properties", {})
                if props.get("title", "").strip().lower() == tab_name.strip().lower():
                    gid = props.get("sheetId", 0)
                    break
    except Exception:
        pass  # usamos gid=0 como fallback

    # ── Paso 2: Exportar como CSV usando el gid numérico ──────────────────────
    # La URL de exportación lee TODOS los datos crudos, ignorando cualquier
    # filtro activo que el equipo tenga aplicado en la vista del sheet.
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
    resp = requests.get(
        export_url,
        params={"format": "csv", "gid": gid},
        timeout=30,
    )

    if resp.status_code != 200:
        st.error(f"Error exportando Google Sheet (código {resp.status_code})")
        return pd.DataFrame()

    if not resp.text.strip():
        st.warning("El Google Sheet está vacío.")
        return pd.DataFrame()

    # Leer CSV con pandas — todos los datos sin importar filtros activos
    df = pd.read_csv(io.StringIO(resp.text), dtype=str).fillna("")

    if df.empty:
        st.warning("El Google Sheet no tiene datos.")
        return pd.DataFrame()

    # Renombrar columnas al nombre interno (con matching flexible)
    _original_cols = df.columns.tolist()
    rename_map = _build_rename_map(_original_cols)
    df = df.rename(columns=rename_map)

    # Guardar info de debug en el df para que la página la muestre
    df.attrs["_debug_cols_original"] = _original_cols
    df.attrs["_debug_cols_mapped"] = sorted(rename_map.values())

    # Eliminar filas completamente vacías
    df = df.replace("", pd.NA).dropna(how="all").fillna("")

    # ── Parsear fechas ─────────────────────────────────────────────────────────
    for date_col in ["fecha_reunion", "fecha_agendamiento"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(
                df[date_col].astype(str),
                dayfirst=True,
                errors="coerce",
            )

    # Columna "fecha" principal = fecha de la reunión reservada
    if "fecha_reunion" in df.columns and df["fecha_reunion"].notna().any():
        df["fecha"] = df["fecha_reunion"]
    elif "fecha_agendamiento" in df.columns:
        df["fecha"] = df["fecha_agendamiento"]
    else:
        st.warning("No se encontró columna de fecha válida en el sheet.")
        return df

    df = df.dropna(subset=["fecha"])

    # Columnas derivadas de fecha
    df["dia"]        = df["fecha"].dt.date
    df["mes"]        = df["fecha"].dt.to_period("M").astype(str)
    df["semana"]     = df["fecha"].dt.isocalendar().week.astype(int)
    df["dia_semana"] = df["fecha"].dt.day_name()

    # ── Parsear hora ───────────────────────────────────────────────────────────
    if "hora" in df.columns and df["hora"].astype(str).str.strip().ne("").any():
        hora_parsed = pd.to_datetime(
            df["hora"].astype(str).str.strip(),
            format="%H:%M",
            errors="coerce",
        )
        df["hora_num"] = hora_parsed.dt.hour
    else:
        df["hora_num"] = pd.NA

    # ── Limpiar strings clave ──────────────────────────────────────────────────
    for col in ["sdr", "ejecutivo", "kam", "cliente", "empresa", "cargo", "pais"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Normalizar "realizado" → booleano
    if "realizado" in df.columns:
        df["reunión_realizada"] = df["realizado"].astype(str).str.lower().str.strip().isin(
            ["sí", "si", "yes", "y", "x", "✓", "true", "1", "realizada", "done"]
        )
    else:
        df["reunión_realizada"] = False

    # Normalizar "asiste" → booleano
    if "asiste" in df.columns:
        df["asiste_bool"] = df["asiste"].astype(str).str.lower().str.strip().isin(
            ["sí", "si", "yes", "y", "x", "✓", "true", "1"]
        )
    else:
        df["asiste_bool"] = False

    # Filas sin SDR → etiquetar como "Sin asignar" en vez de descartar
    if "sdr" in df.columns:
        df["sdr"] = df["sdr"].replace({"": "Sin asignar", "nan": "Sin asignar"})

    return df
