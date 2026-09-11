"""Blueprint del flujo de vinculación de un hijo.

Flujo (ver docs/ARCHITECTURE.md y docs/LEGAL_ETHICS.md):

    1. GET  /link/new             padre completa alias + edad, ve advertencia
    2. POST /link/new             se crea ChildInstance + instancia Evolution
    3. GET  /link/<id>/qr         padre muestra QR al menor, con explicación
    4. POST /link/<id>/consent    el menor acepta consentimiento (mismo browser)
    5. GET  /link/<id>/status     polling del estado (JSON)
    6. POST /link/<id>/revoke     revocar y eliminar instancia
"""
from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from blueprints.auth import login_required
from config import Config
from models import (
    AuditLog,
    ActorType,
    ChildInstance,
    ChildStatus,
    db,
    utcnow,
)
from services import consent_service
from services.evolution_client import EvolutionAPIError, EvolutionClient

logger = logging.getLogger(__name__)
bp = Blueprint("linking", __name__, url_prefix="/link")


# --------------------------------------------------------------------------- #

@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        alias = (request.form.get("child_alias") or "").strip()
        age_raw = (request.form.get("child_age") or "").strip()

        if not alias:
            flash("Ingresá un alias para identificar al hijo/a.", "error")
            return render_template("link/new.html")

        child_age = None
        if age_raw:
            try:
                child_age = int(age_raw)
                if child_age < 6 or child_age > 21:
                    raise ValueError()
            except ValueError:
                flash("La edad debe ser un número entre 6 y 21.", "error")
                return render_template("link/new.html", child_alias=alias, child_age=age_raw)

        child = ChildInstance(
            user_id=g.user.id,
            child_alias=alias,
            child_age=child_age,
            status=ChildStatus.PENDING_QR,
        )
        db.session.add(child)
        db.session.flush()  # necesitamos el id

        try:
            client = EvolutionClient()
            result = client.create_instance(
                child.evolution_instance_name,
                webhook_url=Config.webhook_url(),
            )
        except EvolutionAPIError as exc:
            db.session.rollback()
            logger.exception("No se pudo crear la instancia en Evolution")
            flash(f"Error al crear la instancia: {exc}", "error")
            return render_template("link/new.html", child_alias=alias, child_age=age_raw)

        db.session.add(AuditLog(
            actor_type=ActorType.USER, actor_id=g.user.id,
            action="child_instance_created",
            target_type="ChildInstance", target_id=child.id,
            ip=request.remote_addr, user_agent=request.user_agent.string[:500],
            audit_metadata={"instance": child.evolution_instance_name},
        ))
        db.session.commit()

        return redirect(url_for("linking.qr", child_id=child.id))

    return render_template("link/new.html")


@bp.route("/<int:child_id>/qr")
@login_required
def qr(child_id: int):
    child = _get_owned_child(child_id)

    qr_base64 = None
    try:
        qr_base64 = EvolutionClient().get_qr(child.evolution_instance_name)
    except EvolutionAPIError:
        logger.exception("No se pudo obtener el QR de %s", child.evolution_instance_name)

    return render_template(
        "link/qr.html",
        child=child,
        qr_base64=qr_base64,
        minor_consent_text=consent_service.get_minor_consent_text(),
    )


@bp.route("/<int:child_id>/consent", methods=["POST"])
@login_required
def consent(child_id: int):
    """El menor acepta el consentimiento en el mismo dispositivo/sesión.

    Se identifica por el `minor_access_token` posteado en el form.
    Se acepta también desde la sesión del padre (misma pantalla que muestra el QR),
    porque el flujo asume que ambos están juntos al escanear.
    """
    child = _get_owned_child(child_id)

    if not request.form.get("accept_consent") == "on":
        flash("El menor debe tildar la aceptación.", "error")
        return redirect(url_for("linking.qr", child_id=child.id))

    consent_service.register_minor_consent(
        child,
        ip=request.remote_addr,
        user_agent=request.user_agent.string,
    )

    # El estado del monitoreo depende de consentimiento + conexión de WhatsApp.
    # Si Evolution ya reporta conectado, saltamos a CONNECTED; si no,
    # queda PENDING_QR hasta que el webhook nos avise.
    if child.status == ChildStatus.PENDING_CONSENT:
        child.status = ChildStatus.CONNECTED
        child.connected_at = child.connected_at or utcnow()

    db.session.add(AuditLog(
        actor_type=ActorType.MINOR,
        action="minor_consent_accepted",
        target_type="ChildInstance", target_id=child.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
        audit_metadata={"version": Config.CONSENT_TEXT_VERSION},
    ))
    db.session.commit()

    flash("Consentimiento registrado. El monitoreo se activa cuando el QR esté escaneado.", "ok")
    return redirect(url_for("linking.qr", child_id=child.id))


@bp.route("/<int:child_id>/status")
@login_required
def status(child_id: int):
    """Polling JSON para actualizar el UI mientras el padre espera el escaneo."""
    child = _get_owned_child(child_id)

    evolution_state = "unknown"
    try:
        evolution_state = EvolutionClient().connection_state(child.evolution_instance_name)
    except EvolutionAPIError:
        pass

    return jsonify({
        "child_status": child.status.value,
        "evolution_state": evolution_state,
        "has_consent": child.has_active_consent,
        "monitoring_active": child.is_monitoring_active,
    })


@bp.route("/<int:child_id>/revoke", methods=["POST"])
@login_required
def revoke(child_id: int):
    child = _get_owned_child(child_id)

    try:
        EvolutionClient().delete_instance(child.evolution_instance_name)
    except EvolutionAPIError:
        logger.exception("Fallo eliminando instancia; se marca como REVOKED igual")

    consent_service.revoke_minor_consent(child, reason="revoked_by_parent")
    child.status = ChildStatus.REVOKED
    child.revoked_at = utcnow()

    db.session.add(AuditLog(
        actor_type=ActorType.USER, actor_id=g.user.id,
        action="child_instance_revoked",
        target_type="ChildInstance", target_id=child.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
    ))
    db.session.commit()

    flash("Vinculación revocada.", "ok")
    return redirect(url_for("dashboard.index"))


@bp.route("/<int:child_id>/disconnect", methods=["POST"])
@login_required
def disconnect(child_id: int):
    """Cierra la sesión de WhatsApp en Evolution API manteniendo los registros."""
    child = _get_owned_child(child_id)

    try:
        EvolutionClient().logout(child.evolution_instance_name)
        child.status = ChildStatus.DISCONNECTED
        db.session.commit()
        flash(f"Se ha cerrado la sesión de WhatsApp de {child.child_alias}.", "ok")
    except EvolutionAPIError as exc:
        if exc.status_code == 404:
            child.status = ChildStatus.DISCONNECTED
            db.session.commit()
            flash(f"La sesión de WhatsApp de {child.child_alias} ya no estaba activa en el servidor.", "ok")
        else:
            logger.exception("Error al cerrar sesión en Evolution")
            flash(f"No se pudo desconectar: {exc}", "error")

    return redirect(url_for("linking.qr", child_id=child.id))


@bp.route("/<int:child_id>/delete", methods=["POST"])
@login_required
def delete(child_id: int):
    """Elimina definitivamente la instancia en Evolution API y borra la vinculación de la base de datos."""
    child = _get_owned_child(child_id)
    alias = child.child_alias

    try:
        EvolutionClient().delete_instance(child.evolution_instance_name)
    except EvolutionAPIError:
        logger.exception("Fallo al eliminar instancia en Evolution; se procede a eliminar en base de datos")

    db.session.add(AuditLog(
        actor_type=ActorType.USER, actor_id=g.user.id,
        action="child_instance_deleted",
        target_type="ChildInstance", target_id=child.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
        audit_metadata={"alias": alias, "instance": child.evolution_instance_name},
    ))

    db.session.delete(child)
    db.session.commit()

    flash(f"La conexión con {alias} y todos sus datos asociados fueron eliminados.", "ok")
    return redirect(url_for("dashboard.index"))



# --------------------------------------------------------------------------- #

def _get_owned_child(child_id: int) -> ChildInstance:
    child = ChildInstance.query.get_or_404(child_id)
    if child.user_id != g.user.id:
        abort(404)
    return child
