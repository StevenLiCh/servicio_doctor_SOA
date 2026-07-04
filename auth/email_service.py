# ============================================================
# auth/email_service.py
# Ubicación: ServicioDoctor/auth/email_service.py
# Propósito: Enviar el código de verificación (2FA) por correo
#            usando una cuenta de Gmail + Contraseña de aplicación.
#
# NOTA: No requiere instalar ninguna librería nueva.
#       smtplib y email vienen incluidas en Python (librería estándar).
# ============================================================

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

load_dotenv()

EMAIL_REMITENTE     = os.getenv("EMAIL_REMITENTE")
EMAIL_PASSWORD_APP  = os.getenv("EMAIL_PASSWORD_APP")
EMAIL_NOMBRE        = os.getenv("EMAIL_NOMBRE", "EcoSalud - Panel Doctor")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587  # Puerto TLS (STARTTLS)


def enviar_codigo_verificacion(destinatario: str, nombre_doctor: str, codigo: str, minutos_expira: int = 5) -> bool:
    """
    Envía el código de verificación de 6 dígitos al correo del doctor.
    """
    if not EMAIL_REMITENTE or not EMAIL_PASSWORD_APP:
        print("[EMAIL] ERROR: Faltan EMAIL_REMITENTE / EMAIL_PASSWORD_APP en el .env")
        return False

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = "Tu código de verificación - EcoSalud"
    mensaje["From"]    = f"{EMAIL_NOMBRE} <{EMAIL_REMITENTE}>"
    mensaje["To"]      = destinatario

    texto_plano = (
        f"Hola {nombre_doctor},\n\n"
        f"Tu código de verificación es: {codigo}\n"
        f"Este código vence en {minutos_expira} minutos.\n\n"
        f"Si no intentaste iniciar sesión, ignora este mensaje."
    )

    texto_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Verificación en dos pasos</h2>
        <p>Hola <b>{nombre_doctor}</b>,</p>
        <p>Tu código de verificación es:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #2563eb;">
          {codigo}
        </p>
        <p>Este código vence en <b>{minutos_expira} minutos</b>.</p>
        <p style="color: #888; font-size: 12px;">
          Si no intentaste iniciar sesión, ignora este mensaje.
        </p>
      </body>
    </html>
    """

    mensaje.attach(MIMEText(texto_plano, "plain"))
    mensaje.attach(MIMEText(texto_html, "html"))

    try:
        contexto = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as servidor:
            servidor.starttls(context=contexto)
            servidor.login(EMAIL_REMITENTE, EMAIL_PASSWORD_APP)
            servidor.sendmail(EMAIL_REMITENTE, destinatario, mensaje.as_string())

        print(f"[EMAIL] Código enviado correctamente a {destinatario}")
        return True

    except Exception as e:
        print(f"[EMAIL] ERROR al enviar el correo: {e}")
        return False