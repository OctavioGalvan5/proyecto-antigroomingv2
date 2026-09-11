"""Dashboard del padre.

Rutas:
    GET  /                          resumen de hijos + contadores de alertas
    GET  /alerts                    lista de RiskEvents (filtro por severidad)
    GET  /alerts/<id>               detalle de una alerta (con contexto acotado)
    POST /alerts/<id>/review        marcar como revisada
    GET  /children/<id>/contacts    contactos que le escriben al menor
    POST /children/<id>/toggle-outbound  activa/desactiva captura de outbound
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func

from blueprints.auth import login_required
from models import (
    ActorType,
    AuditLog,
    ChildInstance,
    Contact,
    RiskEvent,
    RiskSeverity,
    db,
    utcnow,
)

bp = Blueprint("dashboard", __name__, url_prefix="/")


# --------------------------------------------------------------------------- #

@bp.route("/")
@login_required
def index():
    children = (ChildInstance.query
                .filter_by(user_id=g.user.id)
                .order_by(ChildInstance.created_at.desc())
                .all())

    # Conteos de alertas por severidad por hijo (una sola query, agrupada).
    counts_rows = (db.session.query(
                        RiskEvent.child_instance_id,
                        RiskEvent.severity,
                        func.count(RiskEvent.id),
                    )
                   .filter(RiskEvent.child_instance_id.in_([c.id for c in children] or [0]))
                   .group_by(RiskEvent.child_instance_id, RiskEvent.severity)
                   .all())

    counts: dict[int, dict[str, int]] = {}
    for child_id, severity, cnt in counts_rows:
        counts.setdefault(child_id, {})[severity.value] = cnt

    return render_template("dashboard/index.html", children=children, counts=counts)


# ---------------------------------------------------------------- Alertas

@bp.route("/alerts")
@login_required
def alerts():
    severity_filter = request.args.get("severity")  # None | LOW | MEDIUM | HIGH
    child_id = request.args.get("child_id", type=int)

    q = (RiskEvent.query
         .join(ChildInstance, ChildInstance.id == RiskEvent.child_instance_id)
         .filter(ChildInstance.user_id == g.user.id))

    if severity_filter in RiskSeverity.__members__:
        q = q.filter(RiskEvent.severity == RiskSeverity[severity_filter])
    if child_id:
        q = q.filter(RiskEvent.child_instance_id == child_id)

    events = q.order_by(RiskEvent.created_at.desc()).limit(200).all()

    children = (ChildInstance.query
                .filter_by(user_id=g.user.id)
                .order_by(ChildInstance.child_alias)
                .all())

    return render_template(
        "dashboard/alerts.html",
        events=events,
        children=children,
        severity_filter=severity_filter,
        child_id_filter=child_id,
    )


@bp.route("/alerts/<int:event_id>")
@login_required
def alert_detail(event_id: int):
    event = _get_owned_alert(event_id)

    # Log de auditoría: el padre vio el detalle acotado (no la conversación completa).
    db.session.add(AuditLog(
        actor_type=ActorType.USER, actor_id=g.user.id,
        action="viewed_alert_detail",
        target_type="RiskEvent", target_id=event.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
    ))
    db.session.commit()

    return render_template("dashboard/alert_detail.html", event=event)


@bp.route("/alerts/<int:event_id>/review", methods=["POST"])
@login_required
def alert_review(event_id: int):
    event = _get_owned_alert(event_id)
    note = (request.form.get("note") or "").strip() or None

    event.reviewed_at = utcnow()
    event.reviewer_note = note

    db.session.add(AuditLog(
        actor_type=ActorType.USER, actor_id=g.user.id,
        action="reviewed_alert",
        target_type="RiskEvent", target_id=event.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
        audit_metadata={"had_note": bool(note)},
    ))
    db.session.commit()

    flash("Alerta marcada como revisada.", "ok")
    return redirect(url_for("dashboard.alert_detail", event_id=event.id))


# ---------------------------------------------------------------- Contactos

@bp.route("/children/<int:child_id>/contacts")
@login_required
def child_contacts(child_id: int):
    child = _get_owned_child(child_id)

    contacts = (Contact.query
                .filter_by(child_instance_id=child.id)
                .order_by(Contact.last_message_at.desc().nullslast())
                .all())

    return render_template("dashboard/contacts.html", child=child, contacts=contacts)


# ---------------------------------------------------------------- Toggle outbound

@bp.route("/children/<int:child_id>/toggle-outbound", methods=["POST"])
@login_required
def child_toggle_outbound(child_id: int):
    child = _get_owned_child(child_id)
    child.monitor_outbound = not child.monitor_outbound

    db.session.add(AuditLog(
        actor_type=ActorType.USER, actor_id=g.user.id,
        action="toggled_monitor_outbound",
        target_type="ChildInstance", target_id=child.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
        audit_metadata={"new_value": child.monitor_outbound},
    ))
    db.session.commit()

    flash(
        f"Captura de mensajes salientes: {'ACTIVADA' if child.monitor_outbound else 'DESACTIVADA'}",
        "ok",
    )
    return redirect(url_for("linking.qr", child_id=child.id))


# --------------------------------------------------------------------------- #

def _get_owned_child(child_id: int) -> ChildInstance:
    child = ChildInstance.query.get_or_404(child_id)
    if child.user_id != g.user.id:
        abort(404)
    return child


def _get_owned_alert(event_id: int) -> RiskEvent:
    event = RiskEvent.query.get_or_404(event_id)
    if event.child_instance.user_id != g.user.id:
        abort(404)
    return event
