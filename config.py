"""Configuración central del sistema antigrooming.

Todas las variables se leen de `.env`. Si falta algo crítico, `Config.validate()`
lo reporta al arranque (ver `main.py`). No hay defaults con credenciales.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import ClassVar
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


class Config:
    # ---- Flask ----
    SECRET_KEY: ClassVar[str] = os.getenv("SECRET_KEY", "")
    FLASK_ENV: ClassVar[str] = os.getenv("FLASK_ENV", "development")
    PORT: ClassVar[int] = _int("PORT", 5000)
    PUBLIC_BASE_URL: ClassVar[str] = os.getenv("PUBLIC_BASE_URL", "")

    # ---- Base de datos ----
    DATABASE_URL: ClassVar[str] = os.getenv("DATABASE_URL", "")

    # ---- Evolution API ----
    EVOLUTION_API_URL: ClassVar[str] = (os.getenv("EVOLUTION_API_URL", "") or "").rstrip("/")
    EVOLUTION_API_KEY: ClassVar[str] = os.getenv("EVOLUTION_API_KEY", "")

    # ---- OpenAI ----
    OPENAI_API_KEY: ClassVar[str] = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL_MAIN: ClassVar[str] = os.getenv("OPENAI_MODEL_MAIN", "gpt-5-mini")
    OPENAI_MODEL_DEEP: ClassVar[str] = os.getenv("OPENAI_MODEL_DEEP", "gpt-5")

    # ---- SMTP ----
    SMTP_HOST: ClassVar[str] = os.getenv("SMTP_HOST", "")
    SMTP_PORT: ClassVar[int] = _int("SMTP_PORT", 587)
    SMTP_USER: ClassVar[str] = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: ClassVar[str] = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: ClassVar[str] = os.getenv("SMTP_FROM", "alertas@antigrooming.local")
    SMTP_USE_TLS: ClassVar[bool] = _bool("SMTP_USE_TLS", True)

    # ---- Operativo ----
    MESSAGE_RETENTION_DAYS: ClassVar[int] = _int("MESSAGE_RETENTION_DAYS", 30)
    ANALYZE_EVERY_N_MESSAGES: ClassVar[int] = _int("ANALYZE_EVERY_N_MESSAGES", 5)
    ANALYZE_MIN_INTERVAL_MINUTES: ClassVar[int] = _int("ANALYZE_MIN_INTERVAL_MINUTES", 10)

    # ---- Consentimiento ----
    # Versión del texto de consentimiento del menor. Cambiar acá cuando se edite el texto.
    CONSENT_TEXT_VERSION: ClassVar[str] = "v1-2026-09"
    TERMS_TEXT_VERSION: ClassVar[str] = "v1-2026-09"

    @classmethod
    def missing_required(cls) -> list[str]:
        """Devuelve la lista de variables requeridas que no están seteadas.

        Se usa al arrancar para fallar temprano en vez de romper en runtime.
        Las variables de OpenAI/SMTP no se validan acá porque son requeridas
        recién en v0.2.
        """
        required = {
            "SECRET_KEY": cls.SECRET_KEY,
            "DATABASE_URL": cls.DATABASE_URL,
            "EVOLUTION_API_URL": cls.EVOLUTION_API_URL,
            "EVOLUTION_API_KEY": cls.EVOLUTION_API_KEY,
            "PUBLIC_BASE_URL": cls.PUBLIC_BASE_URL,
        }
        return [name for name, value in required.items() if not value]

    @classmethod
    def webhook_url(cls) -> str:
        """URL absoluta que se registra en Evolution API por instancia."""
        return f"{cls.PUBLIC_BASE_URL.rstrip('/')}/webhook/evolution"
