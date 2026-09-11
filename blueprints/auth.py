"""Blueprint de autenticación de padres/tutores.

Rutas:
    GET/POST /auth/signup   Registro. Requiere aceptar términos.
    GET/POST /auth/login    Login.
    POST     /auth/logout   Logout.
"""
from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import Config
from models import User, db, utcnow

bp = Blueprint("auth", __name__, url_prefix="/auth")


# --------------------------------------------------------------------------- #
# Helpers globales — se registran en main.py via app.before_request / context.
# --------------------------------------------------------------------------- #

def load_current_user() -> None:
    """Corre antes de cada request. Deja `g.user` seteado."""
    uid = session.get("user_id")
    g.user = User.query.get(uid) if uid else None


def login_required(view):
    """Decorador para rutas que requieren padre logueado."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #

@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip() or None
        accepted = request.form.get("accept_terms") == "on"

        error = _validate_signup(email, password, accepted)
        if error:
            flash(error, "error")
            return render_template("auth/signup.html", email=email, full_name=full_name)

        if User.query.filter_by(email=email).first():
            flash("Ya existe una cuenta con ese email.", "error")
            return render_template("auth/signup.html", email=email, full_name=full_name)

        user = User(
            email=email,
            full_name=full_name,
            accepted_terms_at=utcnow(),
            terms_version=Config.TERMS_TEXT_VERSION,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session.clear()
        session["user_id"] = user.id
        flash("Cuenta creada. Bienvenido/a.", "ok")
        return redirect(url_for("dashboard.index"))

    return render_template("auth/signup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Email o contraseña incorrectos.", "error")
            return render_template("auth/login.html", email=email)

        user.last_login_at = utcnow()
        db.session.commit()

        session.clear()
        session["user_id"] = user.id
        return redirect(request.args.get("next") or url_for("dashboard.index"))

    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------- #
# Validaciones
# --------------------------------------------------------------------------- #

def _validate_signup(email: str, password: str, accepted: bool) -> str | None:
    if not email or "@" not in email:
        return "Email inválido."
    if len(password) < 10:
        return "La contraseña debe tener al menos 10 caracteres."
    if not accepted:
        return "Debés aceptar los términos y la declaración sobre el menor."
    return None
