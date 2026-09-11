"""Endpoint que recibe eventos de Evolution API.

Cada evento trae el campo `instance` (nombre de la instancia). Con ese pivote
resolvemos a qué `ChildInstance` de nuestra base pertenece.

Eventos que nos interesan (ver `services/evolution_client.py`):
    - MESSAGES_UPSERT     mensaje nuevo (entrante o saliente)
    - MESSAGES_UPDATE     cambio de estado (leído, entregado)
    - CONNECTION_UPDATE   estado de la sesión de WhatsApp
    - QRCODE_UPDATED      Evolution refrescó el QR

En v0.1 sólo persistimos mensajes entrantes y actualizamos estado.
El disparo del análisis se hace en v0.2 (ver docs/ANALYSIS_PIPELINE.md).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from config import Config
from models import (
    ChildInstance,
    ChildStatus,
    Contact,
    Conversation,
    MediaType,
    Message,
    MessageDirection,
    db,
    utcnow,
)

logger = logging.getLogger(__name__)
bp = Blueprint("webhook", __name__, url_prefix="/webhook")


# --------------------------------------------------------------------------- #

@bp.route("/evolution", methods=["POST"])
def evolution_event():
    """Punto único de entrada de eventos de Evolution API.

    Siempre respondemos 200 salvo errores duros. Nunca queremos que Evolution
    reintente por errores de datos.
    """
    payload = request.get_json(silent=True) or {}
    event_name = payload.get("event") or payload.get("eventType") or ""
    instance_name = _extract_instance_name(payload)

    if not instance_name:
        logger.warning("Webhook sin `instance` — descartado. Evento=%s", event_name)
        return jsonify({"ok": False, "reason": "no_instance"}), 200

    child = ChildInstance.query.filter_by(evolution_instance_name=instance_name).first()
    if not child:
        logger.warning("Webhook para instancia desconocida: %s", instance_name)
        return jsonify({"ok": False, "reason": "unknown_instance"}), 200

    normalized_event = event_name.lower().replace(".", "_")
    handler = _EVENT_HANDLERS.get(normalized_event)
    if not handler:
        logger.debug("Evento sin handler: %s", event_name)
        return jsonify({"ok": True, "handled": False}), 200

    try:
        handler(child, payload)
    except Exception:
        logger.exception("Error procesando evento %s de %s", event_name, instance_name)
        return jsonify({"ok": False, "reason": "handler_error"}), 200

    return jsonify({"ok": True}), 200


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #

def _on_messages_upsert(child: ChildInstance, payload: dict) -> None:
    """Persiste mensajes entrantes. Solo si el monitoreo está activo."""
    if not child.is_monitoring_active:
        logger.info("Descartando mensaje: monitoreo no activo (child_id=%s)", child.id)
        return

    for msg_data in _iter_messages(payload):
        _persist_incoming_message(child, msg_data)


def _on_messages_update(child: ChildInstance, payload: dict) -> None:
    # v0.1: no procesamos updates de status. Placeholder para v0.3.
    pass


def _on_connection_update(child: ChildInstance, payload: dict) -> None:
    """Actualiza el estado local según Evolution.

    Estados de Evolution: 'open' | 'connecting' | 'close'.
    """
    state = None
    data = payload.get("data") or {}
    if isinstance(data, dict):
        state = data.get("state") or data.get("connection")

    if state == "open":
        if child.has_active_consent:
            child.status = ChildStatus.CONNECTED
            child.connected_at = child.connected_at or utcnow()
        else:
            # WhatsApp conectó pero el consentimiento del menor no está registrado.
            # No activamos el monitoreo hasta que el consentimiento se acepte.
            child.status = ChildStatus.PENDING_CONSENT
        # Guardar el número que conectó, si vino
        phone = data.get("wuid") or data.get("phone") or data.get("number")
        if phone and not child.linked_phone:
            child.linked_phone = str(phone)
    elif state == "close":
        child.status = ChildStatus.DISCONNECTED

    db.session.commit()


def _on_qrcode_updated(child: ChildInstance, payload: dict) -> None:
    # v0.1: se lee bajo demanda por /link/<id>/qr; no cacheamos.
    pass


_EVENT_HANDLERS = {
    "messages_upsert": _on_messages_upsert,
    "messages_update": _on_messages_update,
    "connection_update": _on_connection_update,
    "qrcode_updated": _on_qrcode_updated,
}


# --------------------------------------------------------------------------- #
# Persistencia de mensajes
# --------------------------------------------------------------------------- #

def _persist_incoming_message(child: ChildInstance, msg: dict) -> None:
    key = msg.get("key") or {}
    from_me = bool(key.get("fromMe"))
    remote_jid = key.get("remoteJid") or ""
    wa_id = key.get("id") or ""

    if not remote_jid or not wa_id:
        return

    # v0.1: solo persistimos mensajes ENTRANTES al hijo.
    # Ver docs/ROADMAP.md — decisión de no monitorear salientes por privacidad.
    if from_me:
        return

    body, media_type, media_ref = _extract_content(msg.get("message") or {})
    if body is None and media_type is None:
        return  # tipo de mensaje que no sabemos parsear todavía

    ts_epoch = msg.get("messageTimestamp")
    try:
        ts = datetime.fromtimestamp(int(ts_epoch), tz=timezone.utc)
    except (TypeError, ValueError):
        ts = utcnow()

    contact = _get_or_create_contact(child, remote_jid, msg.get("pushName"))
    conversation = _get_or_create_conversation(child, contact)

    # Dedup por wa_message_id
    existing = Message.query.filter_by(
        conversation_id=conversation.id,
        wa_message_id=wa_id,
    ).first()
    if existing:
        return

    purge_at = utcnow() + timedelta(days=Config.MESSAGE_RETENTION_DAYS)

    message = Message(
        conversation_id=conversation.id,
        wa_message_id=wa_id,
        direction=MessageDirection.INBOUND,
        sender_jid=remote_jid,
        body=body,
        media_type=media_type,
        media_ref=media_ref,
        timestamp=ts,
        received_at=utcnow(),
        purge_at=purge_at,
    )
    db.session.add(message)

    conversation.message_count = (conversation.message_count or 0) + 1
    contact.last_message_at = ts
    db.session.commit()

    # v0.2: acá se dispara el pipeline de análisis (ver docs/ANALYSIS_PIPELINE.md)
    # from services.analysis_service import maybe_analyze_conversation
    # maybe_analyze_conversation(conversation.id)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _extract_instance_name(payload: dict) -> str | None:
    """Evolution manda el nombre en distintos lados según versión."""
    if not isinstance(payload, dict):
        return None
    for key in ("instance", "instanceName"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    # Algunas versiones lo anidan en `sender` o `data.instance`
    data = payload.get("data") or {}
    if isinstance(data, dict):
        return data.get("instance") or data.get("instanceName")
    return None


def _iter_messages(payload: dict):
    """Los eventos `messages.upsert` pueden traer una lista o un objeto solo."""
    data = payload.get("data") or {}
    if isinstance(data, dict) and "messages" in data:
        msgs = data.get("messages") or []
        if isinstance(msgs, list):
            yield from msgs
        elif isinstance(msgs, dict):
            yield msgs
    elif isinstance(data, dict) and data.get("key"):
        yield data  # el mensaje mismo


_MEDIA_TYPE_MAP = {
    "imageMessage": MediaType.IMAGE,
    "audioMessage": MediaType.AUDIO,
    "videoMessage": MediaType.VIDEO,
    "documentMessage": MediaType.DOC,
    "stickerMessage": MediaType.STICKER,
}


def _extract_content(message: dict) -> tuple[str | None, MediaType | None, str | None]:
    """Devuelve (body, media_type, media_ref) desde el payload de WhatsApp."""
    if not isinstance(message, dict):
        return None, None, None

    if "conversation" in message and message["conversation"]:
        return str(message["conversation"]), None, None

    if isinstance(message.get("extendedTextMessage"), dict):
        text = message["extendedTextMessage"].get("text")
        if text:
            return str(text), None, None

    for key, media_type in _MEDIA_TYPE_MAP.items():
        media = message.get(key)
        if isinstance(media, dict):
            caption = media.get("caption") or None
            ref = media.get("url") or media.get("directPath")
            return caption, media_type, str(ref) if ref else None

    return None, None, None


def _get_or_create_contact(child: ChildInstance, jid: str, push_name: str | None) -> Contact:
    is_group = jid.endswith("@g.us")
    contact = Contact.query.filter_by(child_instance_id=child.id, phone_jid=jid).first()
    if contact:
        if push_name and not contact.display_name:
            contact.display_name = push_name
        return contact
    contact = Contact(
        child_instance_id=child.id,
        phone_jid=jid,
        display_name=push_name,
        is_group=is_group,
    )
    db.session.add(contact)
    db.session.flush()
    return contact


def _get_or_create_conversation(child: ChildInstance, contact: Contact) -> Conversation:
    conv = Conversation.query.filter_by(contact_id=contact.id).first()
    if conv:
        return conv
    conv = Conversation(child_instance_id=child.id, contact_id=contact.id)
    db.session.add(conv)
    db.session.flush()
    return conv
