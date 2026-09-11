"""Punto de entrada de la app Flask antigrooming.

Uso local:
    python main.py

Producción:
    gunicorn 'main:create_app()' -b 0.0.0.0:5000

Ver docs/DEV_SETUP.md para más detalle.
"""
from __future__ import annotations

import logging
import sys

from flask import Flask, g, redirect, url_for

from config import Config
from models import db
from blueprints import auth as auth_bp
from blueprints import dashboard as dashboard_bp
from blueprints import linking as linking_bp
from blueprints import minor as minor_bp
from blueprints import webhook as webhook_bp
from services import background, consent_service


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    missing = Config.missing_required()
    if missing:
        logging.warning("Faltan variables de entorno: %s. Ver .env.example.", ", ".join(missing))
        # No abortamos para permitir levantar la UI mínima aún sin `.env` completo.

    app.config["SECRET_KEY"] = Config.SECRET_KEY or "dev-insecure-fallback"
    app.config["SQLALCHEMY_DATABASE_URI"] = Config.DATABASE_URL or "sqlite:///dev_fallback.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    db.init_app(app)

    with app.app_context():
        db.create_all()

    background.configure(app)

    _register_blueprints(app)
    _register_hooks(app)
    _register_error_handlers(app)
    _register_context_processors(app)
    _register_template_filters(app)

    return app


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp.bp)
    app.register_blueprint(dashboard_bp.bp)
    app.register_blueprint(linking_bp.bp)
    app.register_blueprint(minor_bp.bp)
    app.register_blueprint(webhook_bp.bp)

    @app.route("/")
    def _root():
        if getattr(g, "user", None):
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def _load_user():
        auth_bp.load_current_user()


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def _not_found(e):
        return {"error": "not_found"}, 404


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def _inject_texts():
        # Los templates necesitan mostrar los textos de términos/consentimiento.
        return {
            "parent_terms": consent_service.get_parent_terms_text(),
        }


def _register_template_filters(app: Flask) -> None:
    STATUS_LABELS = {
        "PENDING_QR": "Esperando QR",
        "PENDING_CONSENT": "Esperando consentimiento",
        "CONNECTED": "Conectado",
        "DISCONNECTED": "Desconectado",
        "REVOKED": "Revocado",
    }
    SEVERITY_LABELS = {
        "HIGH": "Alta",
        "MEDIUM": "Media",
        "LOW": "Baja",
        "NONE": "Ninguna",
    }
    TRUST_LABELS = {
        "UNKNOWN": "Desconocido",
        "TRUSTED": "Confiable",
        "FLAGGED": "Sospechoso",
    }
    CATEGORY_LABELS = {
        "aislamiento": "Aislamiento",
        "escalada_sexual": "Escalada sexual",
        "cambio_plataforma": "Cambio de plataforma",
        "encuentro_fisico": "Encuentro físico",
        "coercion": "Coerción / Chantaje",
        "adulacion_intensa": "Adulación intensa",
        "peticion_datos_personales": "Petición de datos personales",
        "otro": "Otro",
    }
    DIRECTION_LABELS = {
        "INBOUND": "Recibido (Contacto)",
        "OUTBOUND": "Enviado (Hijo/a)",
    }

    @app.template_filter("status_es")
    def _status_es(val):
        key = getattr(val, "value", str(val))
        return STATUS_LABELS.get(key, key)

    @app.template_filter("severity_es")
    def _severity_es(val):
        key = getattr(val, "value", str(val))
        return SEVERITY_LABELS.get(key, key)

    @app.template_filter("trust_es")
    def _trust_es(val):
        key = getattr(val, "value", str(val))
        return TRUST_LABELS.get(key, key)

    @app.template_filter("category_es")
    def _category_es(val):
        raw = getattr(val, "value", str(val)).lower()
        return CATEGORY_LABELS.get(raw, raw.replace("_", " ").capitalize())

    @app.template_filter("direction_es")
    def _direction_es(val):
        key = getattr(val, "value", str(val))
        return DIRECTION_LABELS.get(key, key)



# --------------------------------------------------------------------------- #

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    _configure_logging()
    app = create_app()
    app.run(host="0.0.0.0", port=Config.PORT, debug=(Config.FLASK_ENV == "development"))
