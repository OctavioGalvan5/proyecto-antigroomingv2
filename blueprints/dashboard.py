"""Dashboard del padre.

En v0.1 sólo muestra los hijos vinculados y su estado. Las alertas se
implementan en v0.2 (ver docs/ROADMAP.md).
"""
from __future__ import annotations

from flask import Blueprint, g, render_template

from blueprints.auth import login_required
from models import ChildInstance

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
@login_required
def index():
    children = ChildInstance.query.filter_by(user_id=g.user.id).order_by(ChildInstance.created_at.desc()).all()
    return render_template("dashboard/index.html", children=children)
