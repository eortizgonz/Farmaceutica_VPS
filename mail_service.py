import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app, url_for


def send_password_reset_email(user):
    username = current_app.config["MAIL_USERNAME"]
    password = current_app.config["MAIL_PASSWORD"]
    sender = current_app.config["MAIL_DEFAULT_SENDER"] or username
    if not username or not password or not sender:
        raise RuntimeError("La configuración SMTP está incompleta.")

    token = user.get_reset_token()
    path = url_for("reset_password", token=token)
    base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
    reset_url = f"{base_url}{path}" if base_url else url_for(
        "reset_password", token=token, _external=True
    )

    message = EmailMessage()
    message["Subject"] = "Recuperación de contraseña · Pharma & MedDev AI Copilot"
    message["From"] = sender
    message["To"] = user.email
    message.set_content(
        f"""Hola {user.name},

Recibimos una solicitud para restablecer tu contraseña.

Abre este enlace dentro de los próximos 60 minutos:
{reset_url}

Si no solicitaste el cambio, ignora este mensaje. Tu contraseña actual seguirá funcionando.

Pharma & MedDev AI Copilot
"""
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(
        current_app.config["MAIL_SERVER"], current_app.config["MAIL_PORT"], timeout=15
    ) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)
