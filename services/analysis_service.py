"""Pipeline de análisis de grooming.

Esqueleto documentado. La lógica se implementa en v0.2.
Ver `docs/ANALYSIS_PIPELINE.md` para el diseño completo.

Contrato público:

    maybe_analyze_conversation(conversation_id) -> None
        Función idempotente. Decide si vale la pena analizar según heurísticas
        (frecuencia, contacto nuevo, mensajes sin analizar). Si corresponde,
        invoca a `analyze_conversation`.

    analyze_conversation(conversation_id) -> RiskEvent | None
        Corre las 3 etapas del pipeline y persiste el resultado.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Etapa 1 — filtros baratos (heurística)
# --------------------------------------------------------------------------- #

# Keywords y frases asociadas a fases de grooming. Se calibra iterativamente.
# Se define acá para poder testear sin llamadas al LLM.
GROOMING_KEYWORDS = {
    "aislamiento": [
        "no le cuentes a tus papás", "no le digas a nadie", "que quede entre nosotros",
        "es nuestro secreto", "no me entienden como vos",
    ],
    "escalada_sexual": [
        "mandame una foto", "sin ropa", "en bombacha", "en calzoncillo",
        "estás sola", "mostrame",
    ],
    "cambio_plataforma": [
        "pasame tu telegram", "hablemos por signal", "descargate", "por snapchat",
        "por discord",
    ],
    "encuentro_fisico": [
        "vení a mi casa", "nos vemos hoy", "te paso a buscar", "salgamos",
    ],
    "coercion": [
        "te lo mando a tus papás", "voy a decir", "si no me mandas", "me la debes",
    ],
}


def maybe_analyze_conversation(conversation_id: int) -> None:
    """v0.2 — decide si disparar análisis basado en heurística.

    Reglas iniciales:
      - Si hay N mensajes nuevos desde `last_analyzed_message_id`, disparar.
      - Si el contacto es nuevo (<7 días) y `message_count >= 20`, forzar.
      - Respetar `ANALYZE_MIN_INTERVAL_MINUTES` para no re-analizar demasiado.
    """
    logger.debug("maybe_analyze_conversation(%s) — no implementado aún (v0.2)", conversation_id)


def analyze_conversation(conversation_id: int):
    """v0.2 — corre el pipeline completo. Ver ANALYSIS_PIPELINE.md."""
    raise NotImplementedError("Implementación de análisis se agrega en v0.2")
