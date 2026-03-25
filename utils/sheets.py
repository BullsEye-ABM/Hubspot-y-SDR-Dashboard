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
    "fecha_reunion":      ["Fecha Mes de la reunión", "Fecha mes de la reunión",
                           "Fecha Mes de la Reunión", "Fecha mes de la reunion",
                           "Fecha de la reunión", "Fecha reunión", "Fecha de la reunion",
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


@st.cache_data(ttl=1800, show_spinner=False)
def get_maestra_activos(_secrets) -> dict:
    """
    Lee la pestaña 'Maestra IA' y retorna clientes y SDRs activos.
    Retorna: {"clientes": [...], "sdrs": [...]}
    """
    try:
        sheet_id = _secrets["google_sheets"]["sheet_id"]
        api_key  = _secrets["google_sheets"]["api_key"]
    except KeyError:
        return {"clientes": [], "sdrs": []}

    tab_name   = "Maestra IA"
    range_name = requests.utils.quote(tab_name)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
        f"/values/{range_name}"
    )

    try:
        resp = requests.get(
            url,
            params={"key": api_key, "valueRenderOption": "FORMATTED_VALUE"},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"clientes": [], "sdrs": []}
        rows = resp.json().get("values", [])
    except Exception:
        return {"clientes": [], "sdrs": []}

    if len(rows) < 2:
        return {"clientes": [], "sdrs": []}

    headers = [h.strip() for h in rows[0]]

    def find_col(keyword, exclude=None, after=-1):
        for i, h in enumerate(headers):
            hl = h.lower()
            if i <= after:
                continue
            if keyword.lower() in hl and (not exclude or exclude.lower() not in hl):
                return i
        return -1

    col_cliente       = find_col("cliente",     exclude="status")
    col_st_cliente    = find_col("status",      exclude="responsable")
    col_responsable   = find_col("responsable", exclude="status")
    col_st_responsable = find_col("status",     after=col_responsable)

    def cell(row, col):
        if col < 0 or col >= len(row):
            return ""
        return str(row[col]).strip()

    clientes, sdrs = [], []
    seen_c, seen_s = set(), set()

    for row in rows[1:]:
        c  = cell(row, col_cliente)
        sc = cell(row, col_st_cliente).lower()
        if c and sc == "activo" and c not in seen_c:
            clientes.append(c)
            seen_c.add(c)

        s  = cell(row, col_responsable)
        ss = cell(row, col_st_responsable).lower()
        if s and ss == "activo" and s not in seen_s:
            sdrs.append(s)
            seen_s.add(s)

    return {"clientes": sorted(clientes), "sdrs": sorted(sdrs)}


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

    # ── Leer datos ignorando 100% los filtros activos del equipo ─────────────
    # MÉTODO 1: Sheets API v4 → values.get siempre devuelve TODAS las filas
    #           sin importar qué filtros tenga el equipo aplicados en la vista.
    # MÉTODO 2 (fallback): gviz/tq con tq=select * (fuerza lectura completa).
    df = None

    _method_used = "desconocido"
    _v4_error    = None

    # — Método 1: Sheets API v4 values.get (ignora filtros activos) ───────────
    try:
        # La API v4 espera solo el nombre de la pestaña URL-encoded, SIN comillas simples
        range_name = requests.utils.quote(tab_name)
        v4_url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
            f"/values/{range_name}"
        )
        v4_resp = requests.get(
            v4_url,
            params={"key": api_key, "valueRenderOption": "FORMATTED_VALUE"},
            timeout=30,
        )
        if v4_resp.status_code == 200:
            payload = v4_resp.json()
            rows = payload.get("values", [])
            if len(rows) >= 2:
                headers = rows[0]
                data_rows = [
                    r + [""] * (len(headers) - len(r)) for r in rows[1:]
                ]
                df = pd.DataFrame(data_rows, columns=headers).fillna("")
                _method_used = "Sheets API v4 ✅ (ignora filtros del equipo)"
        else:
            _v4_error = f"HTTP {v4_resp.status_code}: {v4_resp.text[:200]}"
    except Exception as exc:
        _v4_error = str(exc)

    # — Método 2 (fallback): gviz/tq — SÍ respeta filtros activos ────────────
    if df is None or df.empty:
        _method_used = "gviz/tq fallback ⚠️ (puede respetar filtros del equipo)"
        tq_url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/gviz/tq?tqx=out:csv"
            f"&tq={requests.utils.quote('select *')}"
            f"&sheet={requests.utils.quote(tab_name)}"
        )
        tq_resp = requests.get(tq_url, timeout=30)
        if tq_resp.status_code != 200:
            st.error(f"Error exportando Google Sheet (código {tq_resp.status_code})")
            return pd.DataFrame()
        if not tq_resp.text.strip():
            st.warning("El Google Sheet está vacío.")
            return pd.DataFrame()
        df = pd.read_csv(io.StringIO(tq_resp.text), dtype=str).fillna("")

    if df is None or df.empty:
        st.warning("El Google Sheet no tiene datos.")
        return pd.DataFrame()

    # Guardar estado del método para el diagnóstico
    df.attrs["_fetch_method"] = _method_used
    df.attrs["_v4_error"]     = _v4_error
    df.attrs["_row_count_raw"] = len(df)

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
    # Si una fila no tiene fecha_reunion (col O vacía), cae a fecha_agendamiento
    # para no perder esas filas en el dropna.
    if "fecha_reunion" in df.columns and "fecha_agendamiento" in df.columns:
        df["fecha"] = df["fecha_reunion"].fillna(df["fecha_agendamiento"])
    elif "fecha_reunion" in df.columns:
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
