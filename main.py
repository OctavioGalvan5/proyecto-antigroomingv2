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
from blueprints import webhook as webhook_bp
from services import consent_service


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

    _register_blueprints(app)
    _register_hooks(app)
    _register_error_handlers(app)
    _register_context_processors(app)

    return app


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp.bp)
    app.register_blueprint(dashboard_bp.bp)
    app.register_blueprint(linking_bp.bp)
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
