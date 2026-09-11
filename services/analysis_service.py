"""Pipeline de análisis de grooming.

Referencia de diseño: `docs/ANALYSIS_PIPELINE.md`.

Contrato público:
    maybe_analyze_conversation(conversation_id): decide si vale la pena analizar
        según heurísticas de trigger. Se llama desde el webhook, en background.
    analyze_conversation(conversation_id): fuerza el análisis. Corre las 3
        etapas y devuelve el RiskEvent creado (o None si severity=NONE).

Diseño:
    1. Etapa cheap: heurísticas (keywords, contacto nuevo, horarios).
       Si NO activa nada, saltamos LLM y NO creamos RiskEvent.
    2. Etapa LLM: modelo con structured output. Recibe conversación completa
       (hasta N mensajes recientes), edad del hijo, metadata del contacto, y
       resumen de risk events previos.
    3. Persistencia: crea RiskEvent, marca last_analyzed_message_id, y — si
       severity=HIGH — enviamos mail (ADR-0007) en background.

Robustez:
    - Cualquier falla del LLM se loguea y no rompe el webhook.
    - Rate-limit por conversación via `ANALYZE_MIN_INTERVAL_MINUTES`.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any

from openai import OpenAI

from config import Config
from models import (
    Contact,
    Conversation,
    Message,
    MessageDirection,
    RiskEvent,
    RiskSeverity,
    db,
    utcnow,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Etapa 1 — heurística
# --------------------------------------------------------------------------- #

GROOMING_KEYWORDS = {
    "aislamiento": [
        r"no le cuentes a tus? pap[aá]s?",
        r"no le digas a nadie",
        r"que quede entre nosotros",
        r"es nuestro secreto",
        r"no me entienden como vos",
        r"si (te )?enter(a|an) tus? pap[aá]s?",
    ],
    "escalada_sexual": [
        r"mandame (una )?foto",
        r"sin ropa",
        r"en bombacha",
        r"en calzoncillo",
        r"estás? sol[ao]\?",
        r"mostrame",
        r"pack",
        r"sex(t|ting)",
    ],
    "cambio_plataforma": [
        r"pasame tu telegram",
        r"hablemos por (signal|telegram|snapchat|discord)",
        r"por (snap|snapchat)",
        r"por discord",
    ],
    "encuentro_fisico": [
        r"ven[ií] a mi casa",
        r"nos vemos hoy",
        r"te paso a buscar",
        r"salgamos",
        r"encontr[eé]monos",
    ],
    "coercion": [
        r"te lo mando a tus? pap[aá]s?",
        r"voy a decir",
        r"si no me mand[aá]s",
        r"me la deb[eé]s",
        r"te vas? a arrepentir",
    ],
    "adulacion_intensa": [
        r"sos (la más|la mas|el más|el mas) (linda|lindo|bonit[ao])",
        r"nadie te (entiende|quiere) como yo",
        r"sos especial",
    ],
}


def _compile_patterns() -> dict[str, list[re.Pattern]]:
    return {cat: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cat, patterns in GROOMING_KEYWORDS.items()}


_COMPILED_PATTERNS = _compile_patterns()


def _heuristic_signals(conv: Conversation, contact: Contact,
                       recent_messages: list[Message]) -> dict[str, Any]:
    """Devuelve un diccionario con las señales heurísticas detectadas."""
    signals: dict[str, Any] = {"categories": [], "flags": []}

    inbound_bodies = [m.body for m in recent_messages
                      if m.direction == MessageDirection.INBOUND and m.body]
    joined = "\n".join(inbound_bodies).lower()

    for category, patterns in _COMPILED_PATTERNS.items():
        for p in patterns:
            if p.search(joined):
                signals["categories"].append(category)
                break

    # Contacto nuevo con actividad alta
    if contact.first_seen_at and (utcnow() - contact.first_seen_at) < timedelta(days=7):
        if (conv.message_count or 0) >= 20:
            signals["flags"].append("nuevo_contacto_alta_actividad")

    # Horario nocturno recurrente
    night_msgs = sum(
        1 for m in recent_messages
        if m.direction == MessageDirection.INBOUND and m.timestamp
        and (m.timestamp.hour < 6 or m.timestamp.hour >= 0 and m.timestamp.hour < 5)
    )
    if night_msgs >= 5:
        signals["flags"].append("actividad_nocturna")

    signals["categories"] = sorted(set(signals["categories"]))
    return signals


# --------------------------------------------------------------------------- #
# Etapa 2 — LLM
# --------------------------------------------------------------------------- #

_ANALYSIS_JSON_SCHEMA = {
    "name": "grooming_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["severity", "categories", "reasons",
                     "excerpt_wa_ids", "confidence", "recommend_action"],
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["NONE", "LOW", "MEDIUM", "HIGH"],
            },
            "categories": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "aislamiento", "escalada_sexual", "cambio_plataforma",
                        "encuentro_fisico", "coercion", "adulacion_intensa",
                        "peticion_datos_personales", "otro",
                    ],
                },
            },
            "reasons": {
                "type": "string",
                "description": "Explicación de 2-4 oraciones citando fases del grooming detectadas.",
            },
            "excerpt_wa_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "wa_message_id de los mensajes que disparan la alerta (los citados).",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "recommend_action": {
                "type": "string",
                "enum": ["ignore", "monitor", "confront", "denounce"],
            },
        },
    },
}


_SYSTEM_PROMPT = """\
Sos un analizador especializado en detectar patrones de GROOMING infantil en \
conversaciones de WhatsApp entre menores y sus contactos. Trabajás para un \
sistema de alerta preventiva usado por padres/tutores.

Tarea: analizar la conversación provista y devolver, en el schema JSON \
indicado, una evaluación de riesgo.

Fases clásicas del grooming (usalas para razonar):
1. Selección y aproximación.
2. Formación de vínculo (elogios sostenidos, disponibilidad emocional).
3. Aislamiento ("no le cuentes a tus papás", "es nuestro secreto").
4. Desensibilización (introducción gradual de temas sexuales).
5. Escalada sexual (pedido de fotos, sexting, envío de material).
6. Coerción/chantaje.
7. Intento de encuentro físico o cambio de plataforma (Telegram, Signal, Snapchat).

Reglas de severidad:
- NONE: conversación normal, sin señales.
- LOW: alguna señal aislada, probablemente falso positivo.
- MEDIUM: múltiples señales, escalada leve pero sin cruzar límites explícitos.
- HIGH: escalada sexual explícita, pedido de fotos íntimas, propuesta de \
  encuentro, aislamiento activo, o coerción.

Reglas duras:
- No inventes contexto. Basate ESTRICTAMENTE en los mensajes provistos.
- Diferenciá bromas entre pares adolescentes de conducta predatoria adulta.
- Si el contacto es un GRUPO, tené en cuenta que múltiples personas escriben.
- En `excerpt_wa_ids` incluí SOLO los ids de mensajes que motivan tu \
  clasificación. Máximo 6 mensajes.
- `reasons` en 2-4 oraciones. Citá fase(s). Sin palabras sensacionalistas.
- Si severity=NONE, `excerpt_wa_ids` puede quedar vacío y `categories` también.
"""


def _build_llm_input(conv: Conversation, contact: Contact, child_age: int | None,
                    messages: list[Message], prior_events: list[RiskEvent],
                    heuristic: dict[str, Any]) -> str:
    """Serializa la conversación y el contexto a un único mensaje de usuario."""
    context_lines = [
        "## Contexto",
        f"- Edad del menor: {child_age if child_age else 'no informada'}",
        f"- Tipo de chat: {'GRUPO' if contact.is_group else '1-a-1'}",
        f"- JID del chat: {contact.phone_jid}",
        f"- Contacto primer visto: {contact.first_seen_at.isoformat() if contact.first_seen_at else 'n/d'}",
        f"- Mensajes totales en la conversación: {conv.message_count or 0}",
        f"- Señales heurísticas previas: categories={heuristic['categories']} flags={heuristic['flags']}",
    ]

    if prior_events:
        context_lines.append("- Risk events previos en esta conversación:")
        for ev in prior_events[:5]:
            context_lines.append(
                f"  * {ev.created_at.isoformat()} severity={ev.severity.value} "
                f"categories={ev.categories}"
            )

    context_lines.append("")
    context_lines.append("## Conversación (más viejo primero)")
    context_lines.append(
        "Formato: [wa_message_id] direction sender_jid ts | body"
    )

    for m in messages:
        body = (m.body or "").replace("\n", " ")
        if len(body) > 500:
            body = body[:500] + "…"
        context_lines.append(
            f"[{m.wa_message_id}] {m.direction.value} {m.sender_jid} "
            f"{m.timestamp.isoformat() if m.timestamp else ''} | {body}"
        )

    context_lines.append("")
    context_lines.append("Devolvé el análisis en el schema JSON provisto.")
    return "\n".join(context_lines)


def _call_llm(prompt: str, *, deep: bool = False) -> dict[str, Any] | None:
    if not Config.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY no configurada; se omite análisis LLM")
        return None

    client = OpenAI(api_key=Config.OPENAI_API_KEY)
    model = Config.OPENAI_MODEL_DEEP if deep else Config.OPENAI_MODEL_MAIN

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_schema", "json_schema": _ANALYSIS_JSON_SCHEMA},
        )
    except Exception:
        logger.exception("LLM: fallo llamando al modelo %s", model)
        return None

    try:
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
    except Exception:
        logger.exception("LLM: respuesta no parseable")
        return None

    tokens = getattr(resp, "usage", None)
    if tokens is not None:
        data["_tokens_used"] = getattr(tokens, "total_tokens", None)
    data["_model_used"] = model
    return data


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #

_RECENT_WINDOW = 200  # mensajes que se pasan al LLM


def maybe_analyze_conversation(conversation_id: int) -> None:
    """Decide si es momento de correr análisis y, si sí, lo corre.

    No lanza excepciones al caller: cualquier error se loguea.
    """
    try:
        conv = Conversation.query.get(conversation_id)
        if not conv:
            return

        # Rate-limit por conversación
        min_interval = timedelta(minutes=Config.ANALYZE_MIN_INTERVAL_MINUTES)
        if conv.last_analyzed_at and (utcnow() - conv.last_analyzed_at) < min_interval:
            logger.debug("Skip análisis conv=%s: dentro del rate-limit", conversation_id)
            return

        # Trigger por acumulación de mensajes nuevos INBOUND desde el último análisis.
        q = Message.query.filter(
            Message.conversation_id == conv.id,
            Message.direction == MessageDirection.INBOUND,
        )
        if conv.last_analyzed_message_id:
            q = q.filter(Message.id > conv.last_analyzed_message_id)
        new_inbound_count = q.count()

        if new_inbound_count < Config.ANALYZE_EVERY_N_MESSAGES:
            logger.debug("Skip análisis conv=%s: %d mensajes nuevos < umbral",
                         conversation_id, new_inbound_count)
            return

        analyze_conversation(conversation_id)
    except Exception:
        logger.exception("maybe_analyze_conversation crasheó")


def analyze_conversation(conversation_id: int) -> RiskEvent | None:
    """Corre el pipeline sobre la conversación. Devuelve el RiskEvent o None."""
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return None

    contact = conv.contact
    child = conv.child_instance

    recent = (Message.query
              .filter_by(conversation_id=conv.id)
              .order_by(Message.timestamp.asc())
              .limit(_RECENT_WINDOW)
              .all())
    if not recent:
        return None

    heuristic = _heuristic_signals(conv, contact, recent)

    # Si la heurística no encontró NADA y no hay historial, salteamos LLM.
    prior_events = (RiskEvent.query
                    .filter_by(conversation_id=conv.id)
                    .order_by(RiskEvent.created_at.desc())
                    .limit(5).all())
    if not heuristic["categories"] and not heuristic["flags"] and not prior_events:
        # Marcamos como analizado para no reanalizar en cada mensaje.
        conv.last_analyzed_at = utcnow()
        conv.last_analyzed_message_id = recent[-1].id
        db.session.commit()
        logger.debug("Conv %s sin señales heurísticas: no llamamos LLM", conv.id)
        return None

    prompt = _build_llm_input(conv, contact, child.child_age, recent, prior_events, heuristic)
    # Si ya hubo un HIGH previo, usamos el modelo grande para revisión más fina.
    use_deep = any(e.severity == RiskSeverity.HIGH for e in prior_events)
    result = _call_llm(prompt, deep=use_deep)

    conv.last_analyzed_at = utcnow()
    conv.last_analyzed_message_id = recent[-1].id

    if result is None:
        db.session.commit()
        return None

    severity_str = result.get("severity", "NONE")
    try:
        severity = RiskSeverity[severity_str]
    except KeyError:
        severity = RiskSeverity.NONE

    if severity == RiskSeverity.NONE:
        db.session.commit()
        logger.info("Conv %s analizada, severity=NONE", conv.id)
        return None

    # Convertimos los wa_message_ids del LLM en snapshots {id, wa_message_id, sender_jid, body, timestamp}.
    excerpt_ids = result.get("excerpt_wa_ids") or []
    excerpt_msgs = [m for m in recent if m.wa_message_id in excerpt_ids]
    excerpt = [
        {
            "id": m.id,
            "wa_message_id": m.wa_message_id,
            "direction": m.direction.value,
            "sender_jid": m.sender_jid,
            "body": m.body,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        }
        for m in excerpt_msgs
    ]

    event = RiskEvent(
        child_instance_id=child.id,
        conversation_id=conv.id,
        contact_id=contact.id,
        severity=severity,
        categories=result.get("categories") or [],
        reasons=result.get("reasons") or "",
        excerpt=excerpt,
        model_used=result.get("_model_used"),
        tokens_used=result.get("_tokens_used"),
    )
    db.session.add(event)
    db.session.commit()

    logger.info("Conv %s → RiskEvent %s severity=%s", conv.id, event.id, severity.value)

    if severity == RiskSeverity.HIGH:
        _dispatch_high_severity_alert(event)

    return event


def _dispatch_high_severity_alert(event: RiskEvent) -> None:
    """Manda el mail al padre y marca notified_at si tuvo éxito.

    Import local para evitar ciclo con el mail_service.
    """
    from services import mail_service
    child = event.child_instance
    user = child.user
    ok = mail_service.send_alert(user, event)
    if ok:
        event.notified_at = utcnow()
        db.session.commit()
