"""
Autenticación Google para Bullseye Dashboard.
Solo permite acceso a cuentas @bullseye-abm.com.

Requiere en Streamlit Cloud secrets.toml:
  [auth]
  redirect_uri   = "https://<tu-app>.streamlit.app/oauth2callback"
  cookie_secret  = "<string aleatorio>"

  [auth.google]
  client_id             = "<client_id>.apps.googleusercontent.com"
  client_secret         = "<client_secret>"
  server_metadata_url   = "https://accounts.google.com/.well-known/openid-configuration"
"""

import streamlit as st

ALLOWED_DOMAIN = "bullseye-abm.com"


def require_login():
    """
    Auth deshabilitada temporalmente.
    Para reactivar: descomentar el bloque de abajo y configurar [auth] en secrets.
    """
    return

    # ── BLOQUE DESHABILITADO ── descomenta para reactivar auth Google ──────────
    # Si Streamlit no soporta auth, no bloquear (dev local)
    if not hasattr(st, "user") or not hasattr(st, "login"):  # noqa: unreachable
        return
    # Si [auth] no está configurado en secrets, no bloquear
    try:
        if not st.secrets.get("auth"):
            return
    except (FileNotFoundError, AttributeError):
        return
    try:
        logged_in = st.user.is_logged_in
    except AttributeError:
        return

    # ── Sin sesión activa → pantalla de login ──
    if not logged_in:
        # Si el usuario ya hizo clic en "Ingresar", ahora sí llamamos st.login()
        # (la sesión WebSocket ya está establecida en este punto)
        if st.session_state.get("_do_login"):
            del st.session_state["_do_login"]
            st.login("google")
            st.stop()

        # Primera carga: mostrar pantalla con botón
        st.markdown("""
        <style>
        [data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none; }
        </style>
        """, unsafe_allow_html=True)

        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown(
                "<h1 style='text-align:center;font-size:2.5rem;'>🎯 Bullseye Dashboard</h1>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<p style='text-align:center;color:#888;'>Plataforma de reportería SDR</p>",
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
            st.info(
                f"Inicia sesión con tu cuenta corporativa **@{ALLOWED_DOMAIN}** para continuar.",
                icon="🔐",
            )
            st.markdown("<br>", unsafe_allow_html=True)

            # Botón custom: al hacer clic setea flag y hace rerun,
            # en el siguiente rerun st.login() se llama con sesión activa
            if st.button(
                "🔑  Ingresar con Google",
                use_container_width=True,
                type="primary",
                key="_login_btn",
            ):
                st.session_state["_do_login"] = True
                st.rerun()

        st.stop()

    # ── Sesión activa y dominio correcto → mostrar usuario en sidebar ──
    email = (getattr(st.user, "email", "") or "").lower().strip()
    name  = getattr(st.user, "name", "") or email
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"👤 **{name}**  \n`{email}`")
        st.button("🚪 Cerrar sesión", use_container_width=True,
                  key="_logout_sidebar", on_click=st.logout)

    # ── Sesión activa pero dominio incorrecto ──
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        st.markdown("""
        <style>
        [data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none; }
        </style>
        """, unsafe_allow_html=True)

        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.error(
                f"⛔ **Acceso denegado.**\n\n"
                f"Solo cuentas `@{ALLOWED_DOMAIN}` tienen acceso a este sistema.\n\n"
                f"Cuenta actual: `{email}`",
            )
            st.button("🚪 Cerrar sesión", use_container_width=True,
                      key="_logout_btn", on_click=st.logout)
        st.stop()
