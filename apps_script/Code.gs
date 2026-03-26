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

// ── GET: retorna los datos de los desplegables o reuniones por SDR ─────────
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || "";
    if (action === "getMeetings") {
      const sdr     = (e.parameter && e.parameter.sdr)     || "";
      const cliente = (e.parameter && e.parameter.cliente) || "";
      return getMeetingsForSDR(sdr, cliente);
    }
    if (action === "getClientsForSDR") {
      const sdr = (e.parameter && e.parameter.sdr) || "";
      return getClientsForSDR(sdr);
    }
    const data = getMaestraData();
    return jsonResponse({ status: "ok", data: data });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// ── POST: guarda nueva reunión o actualiza una existente ──────────────────
function doPost(e) {
  try {
    const params = e.parameter;
    if (params.action === "update") {
      updateReunion(params);
    } else {
      saveReunion(params);
    }
    return jsonResponse({ status: "ok", message: "OK" });
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

// ── Obtener clientes únicos con reuniones pendientes para un SDR ──────────
function getClientsForSDR(sdrName) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(OUTPUT_TAB);
  if (!sheet) return jsonResponse({ status: "ok", clientes: [] });

  const all = sheet.getDataRange().getValues();
  if (all.length < 2) return jsonResponse({ status: "ok", clientes: [] });

  const headers = all[0].map(h => h.toString().trim().toLowerCase());
  const col = (kw1, kw2, exclude) => headers.findIndex(h =>
    h.includes(kw1) && (!kw2 || h.includes(kw2)) && (!exclude || !h.includes(exclude))
  );

  const colResponsable = col("responsable");
  const colRealizado   = col("realizado");
  const colCliente     = col("cliente");

  const pendingValues = ["pendiente", "no", "reagendar", ""];
  const seen = new Set();
  const clientes = [];

  for (let i = 1; i < all.length; i++) {
    const r           = all[i];
    const responsable = colResponsable >= 0 ? r[colResponsable]?.toString().trim()          : "";
    const realizado   = colRealizado   >= 0 ? r[colRealizado]?.toString().trim().toLowerCase() : "";
    const cliente     = colCliente     >= 0 ? r[colCliente]?.toString().trim()              : "";

    if (responsable !== sdrName) continue;
    if (!pendingValues.includes(realizado)) continue;
    if (cliente && !seen.has(cliente)) {
      clientes.push(cliente);
      seen.add(cliente);
    }
  }

  clientes.sort();
  return jsonResponse({ status: "ok", clientes: clientes });
}

// ── Obtener reuniones pendientes para un SDR ──────────────────────────────
function getMeetingsForSDR(sdrName, clienteFilter) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(OUTPUT_TAB);
  if (!sheet) return jsonResponse({ status: "ok", meetings: [] });

  const all     = sheet.getDataRange().getValues();
  if (all.length < 2) return jsonResponse({ status: "ok", meetings: [] });

  const headers = all[0].map(h => h.toString().trim().toLowerCase());

  // Matching flexible: busca por palabras clave, no nombre exacto
  const col = (kw1, kw2, exclude) => headers.findIndex(h => {
    return h.includes(kw1) &&
           (!kw2    || h.includes(kw2)) &&
           (!exclude || !h.includes(exclude));
  });

  const colResponsable = col("responsable");
  const colRealizado   = col("realizado");
  const colEmpresa     = col("empresa");
  const colContacto    = col("contacto");
  const colCargo       = col("cargo");
  const colPais        = headers.findIndex(h => /pa[íi]s/.test(h));
  const colFecha       = col("fecha", "reuni");   // "fecha de la reunión"
  const colHora        = col("hora");
  const colCliente     = col("cliente");

  const pendingValues = ["pendiente", "no", "reagendar", ""];

  const meetings = [];
  for (let i = 1; i < all.length; i++) {
    const r           = all[i];
    const responsable = colResponsable >= 0 ? r[colResponsable]?.toString().trim() : "";
    const realizado   = colRealizado   >= 0 ? r[colRealizado]?.toString().trim()   : "";

    if (responsable !== sdrName) continue;
    if (!pendingValues.includes(realizado.toLowerCase())) continue;
    if (clienteFilter) {
      const c = colCliente >= 0 ? r[colCliente]?.toString().trim() : "";
      if (c !== clienteFilter) continue;
    }

    meetings.push({
      row:      i + 1,  // 1-indexed, row 1 = headers
      empresa:  colEmpresa  >= 0 ? r[colEmpresa]?.toString().trim()  : "",
      contacto: colContacto >= 0 ? r[colContacto]?.toString().trim() : "",
      cargo:    colCargo    >= 0 ? r[colCargo]?.toString().trim()    : "",
      pais:     colPais     >= 0 ? r[colPais]?.toString().trim()     : "",
      fecha:    colFecha    >= 0 ? r[colFecha]?.toString().trim()    : "",
      hora:     colHora     >= 0 ? r[colHora]?.toString().trim()     : "",
      estado:   realizado,
      cliente:  colCliente  >= 0 ? r[colCliente]?.toString().trim()  : "",
    });
  }

  return jsonResponse({ status: "ok", meetings: meetings });
}

// ── Actualizar fecha y estado de una reunión existente ────────────────────
function updateReunion(p) {
  const ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(OUTPUT_TAB);
  if (!sheet) throw new Error("No se encontró la pestaña '" + OUTPUT_TAB + "'");

  const rowNum = parseInt(p.row, 10);
  if (isNaN(rowNum) || rowNum < 2) throw new Error("Número de fila inválido: " + p.row);

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const colIndex = (name) => headers.findIndex(h => h.toString().trim() === name);

  const colFecha     = colIndex("Fecha de la reunión");
  const colRealizado = colIndex("Realizado");
  const colComentario = colIndex("Comentario de la reunión");

  if (colFecha >= 0 && p.fecha_reunion !== undefined) {
    sheet.getRange(rowNum, colFecha + 1).setValue(p.fecha_reunion);
  }
  if (colRealizado >= 0 && p.realizado !== undefined) {
    sheet.getRange(rowNum, colRealizado + 1).setValue(p.realizado);
  }
  if (colComentario >= 0 && p.comentario !== undefined && p.comentario !== "") {
    sheet.getRange(rowNum, colComentario + 1).setValue(p.comentario);
  }
}

// ── Helper: respuesta JSON ─────────────────────────────────────────────────
function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
