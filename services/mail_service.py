"""Servicio de notificación por email.

Esqueleto — la implementación completa se hace junto con el pipeline (v0.2).
Contrato mínimo definido acá para que el resto del código pueda referenciarlo.

Regla de negocio (ADR-0007): sólo `RiskSeverity.HIGH` genera mail.
"""
from __future__ import annotations

import logging

from models import RiskEvent, User

logger = logging.getLogger(__name__)


def send_alert(user: User, risk_event: RiskEvent) -> bool:
    """v0.2 — envía mail al padre por alerta HIGH.

    Devuelve True si se envió correctamente.

    Diseño previsto:
      1. Renderizar template `email/alert_high.html` con el extracto acotado.
      2. Enviar via SMTP (Config.SMTP_*).
      3. Setear `risk_event.notified_at` (responsabilidad del caller).
    """
    logger.info("mail_service.send_alert — no implementado (user=%s, event=%s)",
                user.id, risk_event.id)
    return False
