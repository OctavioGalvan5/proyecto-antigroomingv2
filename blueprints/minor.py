"""Portal del menor — /mi-monitoreo/<token>.

Diseño (ver docs/LEGAL_ETHICS.md y ADR-0002):
    - Al vincular una instancia se genera `ChildInstance.minor_access_token`.
    - El padre le comparte el link al menor. Con ese token el menor puede:
        * Ver qué se está monitoreando (metadatos, no contenido).
        * Ver el texto del consentimiento que aceptó.
        * REVOCAR el consentimiento en cualquier momento. La revocación:
            1. Marca ConsentRecord.revoked_at
            2. Deja child.is_monitoring_active = False (el webhook descarta mensajes)
            3. Queda registrada en AuditLog
    - NO se pide login del menor. El token es lo suficientemente largo (32 bytes urlsafe).

Nota: no expone contenido de mensajes ni alertas — sólo metadatos y controles.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from models import (
    ActorType,
    AuditLog,
    ChildInstance,
    ChildStatus,
    RiskEvent,
    db,
    utcnow,
)
from services import consent_service

bp = Blueprint("minor", __name__, url_prefix="/mi-monitoreo")


@bp.route("/<token>")
def portal(token: str):
    child = _get_child_by_token(token)

    total_alerts = RiskEvent.query.filter_by(child_instance_id=child.id).count()

    return render_template(
        "minor/portal.html",
        child=child,
        total_alerts=total_alerts,
        consent_text=consent_service.get_minor_consent_text(
            child.consent.consent_text_version if child.consent else None
        ),
    )


@bp.route("/<token>/revoke", methods=["POST"])
def revoke(token: str):
    child = _get_child_by_token(token)

    if not child.has_active_consent:
        flash("El consentimiento ya está revocado o nunca fue aceptado.", "warn")
        return redirect(url_for("minor.portal", token=token))

    reason = (request.form.get("reason") or "").strip() or "revoked_by_minor"
    consent_service.revoke_minor_consent(child, reason=reason)

    child.status = ChildStatus.REVOKED
    child.revoked_at = utcnow()

    db.session.add(AuditLog(
        actor_type=ActorType.MINOR,
        action="minor_revoked_consent",
        target_type="ChildInstance", target_id=child.id,
        ip=request.remote_addr, user_agent=request.user_agent.string[:500],
        audit_metadata={"reason": reason},
    ))
    db.session.commit()

    flash("Consentimiento revocado. El monitoreo quedó desactivado.", "ok")
    return redirect(url_for("minor.portal", token=token))


# --------------------------------------------------------------------------- #

def _get_child_by_token(token: str) -> ChildInstance:
    child = ChildInstance.query.filter_by(minor_access_token=token).first()
    if not child:
        abort(404)
    return child
