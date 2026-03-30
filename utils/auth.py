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
    Verifica que haya sesión activa con cuenta @bullseye-abm.com.
    - Si auth no está configurada en secrets (dev local), pasa sin bloquear.
    - Si no está autenticado, muestra pantalla de login.
    - Si el dominio no coincide, muestra error y botón para cerrar sesión.
    """
    # Si no hay config de auth (dev local / Streamlit sin soporte), no bloquear
    if not hasattr(st, "user") or not hasattr(st, "login"):
        return
    try:
        logged_in = st.user.is_logged_in
    except AttributeError:
        return

    # ── Sin sesión activa → pantalla de login ──
    if not logged_in:
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
            # st.login() debe llamarse en el flujo directo del script,
            # nunca dentro de un callback (on_click / if button).
            # Llamado así, renderiza el botón de login de Google internamente.
            st.login("google")

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
            # st.logout() también debe ir en el flujo directo
            st.button("🚪 Cerrar sesión", use_container_width=True,
                      key="_logout_btn", on_click=st.logout)
        st.stop()
