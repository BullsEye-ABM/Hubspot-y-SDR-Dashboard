/**
 * BullsEye — Formulario de Reuniones
 * Google Apps Script Backend
 *
 * Funciones:
 *   doGet()  → retorna los desplegables desde "Maestra IA"
 *   doPost() → guarda la nueva reunión en "API Reuniones - IA"
 *
 * Deployment: Publicar como aplicación web
 *   - Ejecutar como: Yo (tu cuenta Google)
 *   - Acceso: Cualquier persona (incluso anónima)
 */

const SPREADSHEET_ID  = "11vYlkzNlRwmEpGbeDNWpceDlhh36-B9gIgXU_emuRRk";
const MAESTRA_TAB     = "Maestra IA";
const OUTPUT_TAB      = "API Reuniones - IA";

// Columnas del sheet de salida
const OUTPUT_HEADERS = [
  "Cliente",
  "Origen",
  "Responsable",
  "Empresa",
  "Contactos/Correo",
  "Fecha de agendamiento",
  "Fecha de la reunión",
  "Hora",
  "País",
  "Realizado",
  "Sales Manager",
  "Cargo",
  "Correo",
  "Teléfono",
  "Industria",
  "Comentario de la reunión",
  "Fecha de registro"
];

// ── GET: retorna los datos de los desplegables ─────────────────────────────
function doGet(e) {
  try {
    const data = getMaestraData();
    return jsonResponse({ status: "ok", data: data });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// ── POST: guarda la nueva reunión ─────────────────────────────────────────
function doPost(e) {
  try {
    const params = e.parameter;
    saveReunion(params);
    return jsonResponse({ status: "ok", message: "Reunión registrada exitosamente" });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// ── Leer opciones de la Maestra IA ────────────────────────────────────────
function getMaestraData() {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(MAESTRA_TAB);
  if (!sheet) throw new Error("No se encontró la pestaña 'Maestra IA'");

  const values  = sheet.getDataRange().getValues();
  const headers = values[0].map(h => h.toString().trim());

  // Encontrar índices por nombre de columna
  const idx = (keyword, exclude) => headers.findIndex(h => {
    const hl = h.toLowerCase();
    return hl.includes(keyword) && (!exclude || !hl.includes(exclude));
  });

  const colCliente      = idx("cliente",       "status");
  const colStCliente    = idx("status",         "responsable");
  const colResponsable  = idx("responsable",    "status");
  const colStResponsable= headers.findIndex((h,i) => h.toLowerCase().includes("status") && i > colResponsable);
  const colOrigen       = idx("origen");
  const colPais         = headers.findIndex(h => /pa[íi]s/i.test(h));
  const colIndustria    = idx("industria");

  const result = { clientes:[], sdrs:[], origenes:[], paises:[], industrias:[] };
  const seen   = { clientes: new Set(), sdrs: new Set(), origenes: new Set(), paises: new Set(), industrias: new Set() };

  for (let i = 1; i < values.length; i++) {
    const r   = values[i];
    const val = (col) => col >= 0 ? r[col]?.toString().trim() : "";

    const cliente     = val(colCliente);
    const stCliente   = val(colStCliente).toLowerCase();
    if (cliente && stCliente === "activo" && !seen.clientes.has(cliente)) {
      result.clientes.push(cliente); seen.clientes.add(cliente);
    }

    const sdr         = val(colResponsable);
    const stSdr       = val(colStResponsable).toLowerCase();
    if (sdr && stSdr === "activo" && !seen.sdrs.has(sdr)) {
      result.sdrs.push(sdr); seen.sdrs.add(sdr);
    }

    const origen = val(colOrigen);
    if (origen && !seen.origenes.has(origen)) {
      result.origenes.push(origen); seen.origenes.add(origen);
    }

    const pais = val(colPais);
    if (pais && !seen.paises.has(pais)) {
      result.paises.push(pais); seen.paises.add(pais);
    }

    const industria = val(colIndustria);
    if (industria && !seen.industrias.has(industria)) {
      result.industrias.push(industria); seen.industrias.add(industria);
    }
  }

  result.clientes.sort();
  result.sdrs.sort();
  result.origenes.sort();
  result.paises.sort();
  result.industrias.sort();

  return result;
}

// ── Guardar fila en "API Reuniones - IA" ──────────────────────────────────
function saveReunion(p) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = ss.getSheetByName(OUTPUT_TAB);

  // Crear pestaña con encabezados si no existe
  if (!sheet) {
    sheet = ss.insertSheet(OUTPUT_TAB);
    const headerRange = sheet.getRange(1, 1, 1, OUTPUT_HEADERS.length);
    headerRange.setValues([OUTPUT_HEADERS]);
    headerRange.setBackground("#1a1b4d");
    headerRange.setFontColor("#ffffff");
    headerRange.setFontWeight("bold");
    sheet.setFrozenRows(1);
  }

  const now = Utilities.formatDate(
    new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm:ss"
  );

  // Mapa de valores por nombre de columna
  const values = {
    "Cliente":                p.cliente            || "",
    "Origen":                 p.origen             || "",
    "Responsable":            p.responsable        || "",
    "Empresa":                p.empresa            || "",
    "Contactos/Correo":       p.contactos          || "",
    "Fecha de agendamiento":  p.fecha_agendamiento || "",
    "Fecha de la reunión":    p.fecha_reunion       || "",
    "Hora":                   p.hora               || "",
    "País":                   p.pais               || "",
    "Realizado":              p.realizado          || "",
    "Sales Manager":          p.sales_manager      || "",
    "Cargo":                  p.cargo              || "",
    "Correo":                 p.correo             || "",
    "Teléfono":               p.telefono           || "",
    "Industria":              p.industria          || "",
    "Comentario de la reunión": p.comentario       || "",
    "Fecha de registro":      now
  };

  // Leer headers actuales del sheet y construir la fila en el orden correcto
  const sheetHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const row = sheetHeaders.map(h => values[h.toString().trim()] ?? "");

  sheet.appendRow(row);
}

// ── Helper: respuesta JSON ─────────────────────────────────────────────────
function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
