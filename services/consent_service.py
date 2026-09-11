"""Servicio de consentimiento.

Concentra:
    - El texto exacto que el menor tiene que aceptar (versionado).
    - El texto de advertencia que el padre acepta.
    - La creación y revocación de `ConsentRecord`.

Cambiar el texto exige subir la versión (`Config.CONSENT_TEXT_VERSION`).
Esto es intencional: el hash del texto se guarda con el consentimiento;
si cambiamos el texto sin subir versión, perdemos trazabilidad.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from models import ChildInstance, ConsentRecord, db, utcnow
from config import Config


# --------------------------------------------------------------------------- #
# Textos versionados
# --------------------------------------------------------------------------- #

MINOR_CONSENT_TEXT_V1 = """\
Hola. Tus papás o tutores activaron una herramienta que va a leer los mensajes de \
WhatsApp que te lleguen. La herramienta no lee tus mensajes uno por uno para pasarlos, \
sino que busca SEÑALES DE PELIGRO: gente que quiera hacerte daño, pedirte fotos, \
convencerte de guardar secretos o de encontrarse con vos.

- Qué se lee: mensajes que TE LLEGAN a WhatsApp (texto). Por ahora no audios ni imágenes.
- Qué ven tus papás: solo alertas si el sistema detecta algo raro. NO ven todas tus conversaciones.
- Cuánto se guarda: los mensajes se borran a los 30 días.
- Podés pedir que se apague en cualquier momento entrando al link que te dieron.

Si algo no te queda claro, pedile a tus papás que te expliquen ANTES de aceptar.
"""

PARENT_TERMS_TEXT_V1 = """\
Al usar este servicio declaro que:

1. Soy responsable legal (padre, madre o tutor) del menor cuya cuenta voy a vincular.
2. Le expliqué al menor qué hace esta herramienta y le voy a mostrar la pantalla \
   de consentimiento en su dispositivo.
3. Entiendo que este sistema NO reemplaza el diálogo con mi hijo/a ni la denuncia \
   policial ante hechos concretos.
4. Entiendo que la detección por IA tiene falsos positivos y falsos negativos: \
   una alerta no prueba un delito, y la ausencia de alerta no garantiza seguridad.
5. Entiendo que solo veré señales de riesgo (alertas), no la conversación completa \
   del menor. Es una decisión deliberada para respetar su privacidad.
6. Los datos del menor se tratan bajo la Ley 25.326 y solo se conservan mientras \
   sean necesarios.
"""


def get_minor_consent_text(version: str | None = None) -> str:
    version = version or Config.CONSENT_TEXT_VERSION
    if version == "v1-2026-09":
        return MINOR_CONSENT_TEXT_V1
    raise ValueError(f"Versión de consentimiento desconocida: {version}")


def get_parent_terms_text(version: str | None = None) -> str:
    version = version or Config.TERMS_TEXT_VERSION
    if version == "v1-2026-09":
        return PARENT_TERMS_TEXT_V1
    raise ValueError(f"Versión de términos desconocida: {version}")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #

def register_minor_consent(
    child_instance: ChildInstance,
    *,
    ip: str | None,
    user_agent: str | None,
) -> ConsentRecord:
    """Crea el `ConsentRecord` para el menor.

    Guarda hash del texto y versión: si en el futuro cambia, sabemos qué aceptó.
    Idempotente: si ya existe un consentimiento no revocado, lo devuelve.
    """
    if child_instance.consent and child_instance.consent.revoked_at is None:
        return child_instance.consent

    version = Config.CONSENT_TEXT_VERSION
    text = get_minor_consent_text(version)

    record = ConsentRecord(
        child_instance_id=child_instance.id,
        accepted_at=utcnow(),
        accepted_from_ip=ip,
        user_agent=(user_agent or "")[:500],
        consent_text_hash=_hash_text(text),
        consent_text_version=version,
    )
    db.session.add(record)
    db.session.commit()
    return record


def revoke_minor_consent(child_instance: ChildInstance, reason: str | None = None) -> None:
    """Marca el consentimiento como revocado. No borra el registro histórico."""
    if not child_instance.consent:
        return
    if child_instance.consent.revoked_at:
        return
    child_instance.consent.revoked_at = utcnow()
    child_instance.consent.revoked_reason = reason
    db.session.commit()
