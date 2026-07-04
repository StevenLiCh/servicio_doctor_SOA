# ============================================================
# auth/email_config.py
# Ubicación: ServicioDoctor/auth/email_config.py
# Propósito: Enviar correos electrónicos con el código 2FA
#            usando Gmail SMTP con contraseña de aplicación
# ============================================================

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# ── Cargar variables de entorno ───────────────────────────────────────────────
load_dotenv()

EMAIL_REMITENTE   = os.getenv("EMAIL_REMITENTE")
EMAIL_PASSWORD    = os.getenv("EMAIL_PASSWORD_APP")
EMAIL_NOMBRE      = os.getenv("EMAIL_NOMBRE", "EcoSalud - Panel Doctor")

# ── FUNCIÓN: Enviar código 2FA por correo ─────────────────────────────────────
def enviar_codigo_2fa(email_destino: str, nombre_doctor: str, codigo: str) -> bool:
    """
    Envía el código de verificación 2FA al correo del doctor.

    Parámetros:
        email_destino: correo del doctor (de la tabla doctores.doctores)
        nombre_doctor: nombre completo para personalizar el mensaje
        codigo: código de 6 dígitos generado aleatoriamente

    Retorna:
        True si el correo se envió correctamente
        False si ocurrió algún error (sin lanzar excepción)
    """
    try:
        # ── Construir el mensaje ───────────────────────────────────────────────
        mensaje = MIMEMultipart("alternative")
        mensaje["Subject"] = f"🔐 Tu código de verificación EcoSalud: {codigo}"
        mensaje["From"]    = f"{EMAIL_NOMBRE} <{EMAIL_REMITENTE}>"
        mensaje["To"]      = email_destino

        # ── Versión texto plano (para clientes de email sin HTML) ──────────────
        texto_plano = f"""
Hola {nombre_doctor},

Tu código de verificación para EcoSalud es:

    {codigo}

Este código es válido por 5 minutos.
Si no intentaste iniciar sesión, ignora este mensaje.

— EcoSalud, Ecosistema de Salud Conectado
        """.strip()

        # ── Versión HTML (para clientes modernos) ─────────────────────────────
        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; background: #f1f6f5; margin: 0; padding: 24px; }}
    .card {{ background: #ffffff; border-radius: 12px; padding: 40px; max-width: 480px; margin: 0 auto; }}
    .brand {{ color: #0f766e; font-size: 22px; font-weight: bold; margin-bottom: 8px; }}
    .subtitulo {{ color: #5f7c83; font-size: 14px; margin-bottom: 32px; }}
    .saludo {{ color: #13313a; font-size: 16px; margin-bottom: 16px; }}
    .codigo-box {{
      background: #d6f3ef; border-radius: 10px;
      padding: 24px; text-align: center; margin: 24px 0;
    }}
    .codigo {{
      font-size: 42px; font-weight: bold; letter-spacing: 14px;
      color: #0b5852; font-family: 'Courier New', monospace;
    }}
    .expira {{ color: #5f7c83; font-size: 13px; margin-top: 8px; }}
    .aviso {{ color: #dc2626; font-size: 13px; margin-top: 24px; }}
    .footer {{ color: #999; font-size: 12px; margin-top: 32px; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">🏥 EcoSalud</div>
    <div class="subtitulo">Ecosistema de Salud Conectado</div>
    <div class="saludo">Hola, <strong>{nombre_doctor}</strong></div>
    <p style="color:#13313a; font-size:15px;">
      Ingresa el siguiente código para completar tu inicio de sesión:
    </p>
    <div class="codigo-box">
      <div class="codigo">{codigo}</div>
      <div class="expira">⏱ Válido por <strong>5 minutos</strong></div>
    </div>
    <div class="aviso">
      ⚠️ Si no intentaste iniciar sesión en EcoSalud, ignora este correo.
      Tus credenciales no han sido comprometidas.
    </div>
    <div class="footer">
      EcoSalud · Panel del Doctor · Universidad Tecnológica del Perú 2026
    </div>
  </div>
</body>
</html>
        """.strip()

        # Adjuntar ambas versiones (el cliente de email elige cuál usar)
        mensaje.attach(MIMEText(texto_plano, "plain", "utf-8"))
        mensaje.attach(MIMEText(html, "html", "utf-8"))

        # ── Enviar por Gmail SMTP ──────────────────────────────────────────────
        # Puerto 587 con STARTTLS es el estándar seguro de Gmail
        with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
            servidor.ehlo()
            servidor.starttls()                              # Cifrado TLS
            servidor.login(EMAIL_REMITENTE, EMAIL_PASSWORD) # Contraseña de aplicación
            servidor.sendmail(
                EMAIL_REMITENTE,
                email_destino,
                mensaje.as_bytes()
            )

        print(f"[2FA] CÓDIGO_ENVIADO → {email_destino}")
        return True

    except Exception as e:
        # Logueamos el error pero no lo propagamos al endpoint
        # (el endpoint decide qué hacer si falla el envío)
        print(f"[2FA] ERROR_ENVIO → {email_destino} | {type(e).__name__}: {e}")
        return False