"""Servicio de notificación por email.

Regla de negocio (ADR-0007): sólo `RiskSeverity.HIGH` genera mail.

Diseño:
    - SMTP simple con STARTTLS.
    - Si SMTP no está configurado en `.env`, la función loguea y devuelve False
      (no rompe el pipeline). El RiskEvent igual queda persistido para el dashboard.
    - Cuerpo HTML mínimo pero legible, sin dependencias de templates.

Uso::

    from services import mail_service
    ok = mail_service.send_alert(user, risk_event)
    if ok:
        risk_event.notified_at = utcnow()
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from config import Config
from models import RiskEvent, User

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #

def is_configured() -> bool:
    return all([Config.SMTP_HOST, Config.SMTP_PORT, Config.SMTP_FROM])


def send_alert(user: User, event: RiskEvent) -> bool:
    """Envía mail al padre por alerta HIGH. Devuelve True si se envió."""
    if not is_configured():
        logger.warning(
            "SMTP no configurado; se omite mail para RiskEvent %s (severity=%s)",
            event.id, event.severity.value,
        )
        return False

    subject, text_body, html_body = _render_alert(event)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = Config.SMTP_FROM
    msg["To"] = user.email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        _send_via_smtp(msg)
    except Exception:
        logger.exception("Fallo enviando mail de alerta a %s", user.email)
        return False

    logger.info("Mail HIGH enviado a %s por RiskEvent %s", user.email, event.id)
    return True


# --------------------------------------------------------------------------- #

def _send_via_smtp(msg: EmailMessage) -> None:
    host = Config.SMTP_HOST
    port = Config.SMTP_PORT
    user = Config.SMTP_USER
    password = Config.SMTP_PASSWORD

    if Config.SMTP_USE_TLS:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    else:
        # SMTPS directo (465) o SMTP plano (dev)
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15,
                                  context=ssl.create_default_context()) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)


# --------------------------------------------------------------------------- #

def _render_alert(event: RiskEvent) -> tuple[str, str, str]:
    child = event.child_instance
    categories = event.categories or []
    excerpt = event.excerpt or []

    subject = f"[Antigrooming] Alerta ALTA — {child.child_alias}"

    dashboard_link = f"{Config.PUBLIC_BASE_URL.rstrip('/')}/alerts/{event.id}"

    plain_lines = [
        f"Se detectó una alerta de severidad ALTA para {child.child_alias}.",
        "",
        f"Categorías detectadas: {', '.join(categories) if categories else 'n/d'}",
        "",
        "Motivo:",
        event.reasons or "(sin descripción)",
        "",
        "Extracto de la conversación que disparó la alerta:",
    ]
    for m in excerpt:
        direction = m.get("direction", "?")
        who = m.get("sender_jid", "?")
        ts = m.get("timestamp", "")
        body = (m.get("body") or "").replace("\n", " ")
        plain_lines.append(f"- [{direction}] {who} {ts}: {body}")

    plain_lines += [
        "",
        f"Ver en el panel: {dashboard_link}",
        "",
        "Recordá: este sistema es preventivo. Ante hechos concretos, "
        "denunciá en fiscalía local o llamá a la Línea 137 (Argentina).",
    ]
    text_body = "\n".join(plain_lines)

    excerpt_html = "".join(
        f"<li><b>{escape(m.get('direction') or '?')}</b> "
        f"{escape(m.get('sender_jid') or '?')} "
        f"<small>{escape(m.get('timestamp') or '')}</small><br>"
        f"{escape((m.get('body') or '').replace(chr(10), ' '))}</li>"
        for m in excerpt
    )

    html_body = f"""\
<!doctype html>
<html><body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1b1b1f;">
  <h2 style="color:#b83232;">Alerta ALTA — {escape(child.child_alias)}</h2>
  <p><b>Categorías:</b> {escape(', '.join(categories)) if categories else 'n/d'}</p>
  <p><b>Motivo:</b><br>{escape(event.reasons or '(sin descripción)')}</p>
  <h3>Extracto de la conversación</h3>
  <ul>{excerpt_html or '<li>(sin extracto)</li>'}</ul>
  <p><a href="{escape(dashboard_link)}"
     style="display:inline-block;padding:10px 16px;background:#1f5fd4;color:#fff;text-decoration:none;border-radius:6px;">
     Ver alerta en el panel</a></p>
  <hr>
  <small>Este sistema es preventivo. Ante hechos concretos, denunciá en fiscalía local o llamá a la Línea 137 (Argentina).</small>
</body></html>
"""

    return subject, text_body, html_body
