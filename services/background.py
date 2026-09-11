"""Runner de tareas en background.

Encapsula un ThreadPoolExecutor global para lanzar trabajos fuera del ciclo
request/response de Flask (típicamente: análisis de conversación, envío de mail).

Reglas:
    - Nunca bloquear el webhook con tareas caras (llamadas a LLM, SMTP).
    - Cada tarea debe abrir su propio `app.app_context()` porque el executor
      corre en un thread distinto al del request.
    - Si la app no está inicializada aún, se ejecuta inline (útil para tests).

Uso típico::

    from services.background import run_in_background
    run_in_background(analysis_service.analyze_conversation, conv_id)

La app se registra con `configure(app)` al arranque (ver `main.py`).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from flask import Flask

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_app: Flask | None = None
_lock = threading.Lock()


def configure(app: Flask, *, max_workers: int = 4) -> None:
    """Registra la app y crea el executor. Idempotente."""
    global _executor, _app
    with _lock:
        _app = app
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bg")


def run_in_background(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Encola `fn(*args, **kwargs)` en el executor con app_context activo.

    Si el executor no fue configurado (edge case en tests), se ejecuta inline
    con manejo de excepciones para no romper el caller.
    """
    if _executor is None or _app is None:
        logger.debug("Executor no configurado; ejecutando inline: %s", fn.__name__)
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Fallo en ejecución inline de %s", fn.__name__)
        return

    app = _app

    def _wrapper():
        with app.app_context():
            try:
                fn(*args, **kwargs)
            except Exception:
                logger.exception("Fallo en tarea background %s", fn.__name__)

    _executor.submit(_wrapper)


def shutdown(wait: bool = True) -> None:
    """Cierra el executor de forma limpia. Llamar al shutdown de la app."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=wait)
        _executor = None
