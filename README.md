# 🎯 Bullseye Dashboard

Dashboard interno de reportería de SDR que conecta ALLO (telefonía), HubSpot (pipeline de ventas) y Google Sheets en un solo lugar.

---

## Métricas disponibles

| Página | Qué muestra |
|--------|-------------|
| 🏠 Inicio | KPIs globales de reuniones, resumen por SDR |
| 📅 Reuniones | Reuniones del Google Sheet, heatmap día/hora |
| 📞 ALLO | Actividad de llamadas (ALLO): tasa de conexión sin voicemail, reuniones agendadas, etiquetas, ranking por SDR y por número/cliente |
| 💼 Ventas | Pipeline de negocios y transcripciones DIIO (HubSpot) |

---

## Pasos para instalar y publicar (sin programar)

### PASO 1 — Crear cuenta en GitHub (repositorio de código)

1. Ve a **github.com** → Crea una cuenta gratuita
2. Crea un repositorio nuevo:
   - Haz clic en el botón verde **"New"**
   - Nombre: `bullseye-dashboard`
   - Selecciona **"Private"** (privado)
   - Haz clic en **"Create repository"**

### PASO 2 — Subir el código a GitHub

En tu computador, abre la **Terminal** (buscala en Spotlight con Cmd+Space) y ejecuta:

```bash
# Ir a la carpeta del proyecto
cd ~/Desktop/bullseye-dashboard

# Inicializar git
git init
git add .
git commit -m "primer commit"

# Conectar con GitHub (reemplaza TU_USUARIO con tu usuario de GitHub)
git remote add origin https://github.com/TU_USUARIO/bullseye-dashboard.git
git branch -M main
git push -u origin main
```

> ⚠️ El archivo `.gitignore` ya está configurado para que el archivo `secrets.toml` (con tus tokens) NUNCA se suba a GitHub.

---

### PASO 3 — Obtener el token de HubSpot (solo para la página Ventas)

1. Entra al portal HubSpot
2. Ve a **Configuración** → **Integraciones** → **Private Apps**
3. Clic en **"Create a private app"**
4. Dale un nombre: `Bullseye Dashboard`
5. En la pestaña **Scopes**, activa:
   - `crm.objects.deals.read`
   - `crm.schemas.deals.read`
   - `crm.owners.read`
6. Clic en **"Create app"** → Copia el token (`pat-na1-xxxx`)

---

### PASO 3B — Obtener la API key de ALLO (para la página ALLO)

1. Entra a la plataforma ALLO → **Configuración** → **API / Integraciones**
2. Genera (o copia) tu API key
3. Pégala en `secrets.toml` como se indica en el Paso 5 (`[allo]` → `api_key`)

La página ALLO usa esta key para leer llamadas, SMS, usuarios, números y etiquetas del equipo — no requiere scopes adicionales, la API key ya trae los permisos habilitados para tu cuenta.

---

### PASO 4 — Crear credencial de Google Sheets

Para leer el Google Sheet de reuniones:

1. Ve a **console.cloud.google.com**
2. Crea un proyecto nuevo (o usa uno existente)
3. Busca y activa las APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Ve a **IAM y administración** → **Cuentas de servicio**
5. Crea una cuenta de servicio:
   - Nombre: `bullseye-sheets`
   - Clic en **"Crear y continuar"** → **"Listo"**
6. Haz clic en la cuenta de servicio creada → **"Claves"** → **"Agregar clave"** → **JSON**
7. Se descargará un archivo `.json` — guárdalo bien, contiene las credenciales

**Compartir el Google Sheet con la cuenta de servicio:**
1. Abre el JSON descargado, copia el valor de `client_email`
2. Abre tu Google Sheet de reuniones
3. Haz clic en **"Compartir"** y pega el email de la cuenta de servicio
4. Dale permiso de **"Lector"**

---

### PASO 5 — Configurar los secrets (credenciales secretas)

1. Copia `bullseye-dashboard/.streamlit/secrets.toml.example` a `bullseye-dashboard/.streamlit/secrets.toml`
2. Rellena todos los valores con tus tokens y credenciales reales (ALLO, HubSpot, Google)
3. Para las credenciales de Google, copia los valores del archivo JSON descargado

El archivo de ejemplo ya tiene comentarios explicativos en cada campo.

---

### PASO 6 — Publicar en Streamlit Cloud (gratis)

1. Ve a **share.streamlit.io**
2. Inicia sesión con tu cuenta de GitHub
3. Haz clic en **"New app"**
4. Selecciona tu repositorio `bullseye-dashboard`
5. Main file path: `app.py`
6. Haz clic en **"Advanced settings"** → **"Secrets"**
7. Copia y pega el contenido de tu archivo `secrets.toml` aquí
8. Haz clic en **"Deploy!"**

¡Listo! En 2-3 minutos tendrás tu dashboard en una URL pública (solo accesible para quienes tú invites).

---

### PASO 7 — Dar acceso a tu equipo

1. En tu app en Streamlit Cloud, ve a **"Settings"** → **"Sharing"**
2. Agrega los emails de tu equipo
3. Solo quienes tengan cuenta Streamlit con esos emails podrán entrar

---

## Estructura del Google Sheet de Reuniones

El sheet debe tener estas columnas (los nombres son flexibles, el sistema los detecta automáticamente):

| Columna | Descripción | Ejemplo |
|---------|-------------|---------|
| Fecha | Fecha de la reunión | 15/03/2026 |
| Hora | Hora agendada | 10:30 |
| SDR | Nombre del SDR | Juan Pérez |
| Cliente | Cliente de Bullseye | Cliente A |
| Contacto | Nombre del prospecto | María González |
| Empresa | Empresa del prospecto | Empresa XYZ |
| Cargo | Cargo del prospecto | Gerente de Marketing |
| Estado | Confirmada / No Show / Reagendada | Confirmada |
| Notas | Observaciones del SDR | Muy interesado en... |

---

## Soporte

Si algo no funciona, revisa:
1. Que los tokens de HubSpot tengan los scopes correctos
2. Que el Google Sheet esté compartido con el email de la cuenta de servicio
3. Que el `sheet_id` en secrets.toml sea el correcto (está en la URL del sheet)
