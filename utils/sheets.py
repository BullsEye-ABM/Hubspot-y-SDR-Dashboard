"""
Google Sheets Reader — versión simple con API Key
No requiere Service Account. Solo necesitas:
  1. El sheet compartido como "Cualquiera con el link puede ver"
  2. Una Google API Key (sin service account)

Sheet: "Metas equipo BullsEye / reuniones / oportunidades"
Pestaña: "Gestión de reuniones"
"""

import requests
import pandas as pd
import streamlit as st


# ── Mapeo exacto de columnas del sheet ────────────────────────────────────────
# Formato: nombre_interno → nombre_exacto_en_el_sheet
COLUMN_MAP = {
    "cliente":             "Cliente",
    "origen":              "Origen",
    "sdr":                 "Responsable",
    "empresa":             "Empresa",
    "contacto":            "Contactos/Correo",
    "fecha_agendamiento":  "Fecha de agendamiento",
    "fecha_reunion":       "Fecha de la reunión reserva",
    "hora":                "Hora",
    "prospecto":           "Prospecto",
    "pais":                "País",
    "realizado":           "Realizado",
    "ejecutivo":           "Ejecutivo",
    "propuesta":           "Propuesta/Oportunidad",
    "piloto":              "Piloto",
    "mes_agenda":          "Mes agenda Reunion Fecha",
    "mes_reunion":         "Mes de la reunión",
    "cargo":               "CARGO",
    "telefono":            "TELEFONO",
    "asiste":              "Asiste a Reunión",
    "link_hubspot":        "Link de Hubspot",
    "kam":                 "KAM",
    "comentarios":         "Comentarios",
    "fuente":              "Fuente Campaña",
    "comentario":          "COMENTARIO",
    "comentario_ih":       "comentario IH",
    "flota":               "Flota informada",
}

# Diccionario invertido para renombrar columnas del sheet al nombre interno
_REVERSE_MAP = {v: k for k, v in COLUMN_MAP.items()}


@st.cache_data(ttl=1800, show_spinner=False)
def get_meetings_from_sheets(_secrets) -> pd.DataFrame:
    """
    Lee el Google Sheet de reuniones usando solo una API Key de Google.
    El sheet debe estar compartido como 'Cualquiera con el link puede ver'.
    El parámetro empieza con _ para que Streamlit no intente hashearlo.
    """
    try:
        sheet_id  = _secrets["google_sheets"]["sheet_id"]
        tab_name  = _secrets["google_sheets"].get("worksheet_name", "Gestión de reuniones")
        api_key   = _secrets["google_sheets"]["api_key"]
    except KeyError as e:
        st.error(f"Falta configuración en secrets.toml: {e}")
        return pd.DataFrame()

    # Usamos batchGet para pasar el nombre de la pestaña como parámetro query
    # (no en la URL), así requests maneja automáticamente tildes y espacios.
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchGet"
    resp = requests.get(
        url,
        params={"key": api_key, "ranges": tab_name},
        timeout=30,
    )

    if resp.status_code != 200:
        st.error(f"Error leyendo Google Sheet (código {resp.status_code}): {resp.text[:300]}")
        return pd.DataFrame()

    value_ranges = resp.json().get("valueRanges", [])
    values = value_ranges[0].get("values", []) if value_ranges else []
    if not values or len(values) < 2:
        st.warning("El Google Sheet está vacío o solo tiene encabezados.")
        return pd.DataFrame()

    # Construir DataFrame con encabezados de la primera fila
    headers = values[0]
    rows    = values[1:]
    # Rellenar filas más cortas que el encabezado
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]

    df = pd.DataFrame(rows, columns=headers)

    # Renombrar columnas al nombre interno
    df = df.rename(columns=_REVERSE_MAP)

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

    # Filtrar filas sin SDR válido
    if "sdr" in df.columns:
        df = df[df["sdr"].ne("") & df["sdr"].ne("nan")].copy()

    return df
