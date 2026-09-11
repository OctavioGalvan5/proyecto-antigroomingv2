"""Modelos de datos del sistema antigrooming.

Ver `docs/DATA_MODEL.md` para el esquema completo y las decisiones de diseño.
Cambios de schema deben acompañarse de una migración en `migrations/`.
"""
from __future__ import annotations

import enum
import secrets
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_instance_name() -> str:
    """Nombre único para la instancia en Evolution API.

    Prefijo `child_` para separarlas visualmente de otras instancias que
    pudieran convivir en el mismo Evolution.
    """
    return f"child_{secrets.token_hex(6)}"


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class ChildStatus(enum.Enum):
    PENDING_QR = "PENDING_QR"
    PENDING_CONSENT = "PENDING_CONSENT"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    REVOKED = "REVOKED"


class MessageDirection(enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class MediaType(enum.Enum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    DOC = "DOC"
    STICKER = "STICKER"


class RiskSeverity(enum.Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TrustLevel(enum.Enum):
    UNKNOWN = "UNKNOWN"
    TRUSTED = "TRUSTED"
    FLAGGED = "FLAGGED"


class ActorType(enum.Enum):
    USER = "USER"
    MINOR = "MINOR"
    SYSTEM = "SYSTEM"


# --------------------------------------------------------------------------- #
# Usuarios (padres/tutores)
# --------------------------------------------------------------------------- #

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(Integer, primary_key=True)
    email = db.Column(String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(String(255), nullable=False)
    full_name = db.Column(String(255))
    created_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(DateTime(timezone=True))
    accepted_terms_at = db.Column(DateTime(timezone=True))
    terms_version = db.Column(String(32))

    children = relationship("ChildInstance", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


# --------------------------------------------------------------------------- #
# Vinculación de instancia (WhatsApp del hijo)
# --------------------------------------------------------------------------- #

class ChildInstance(db.Model):
    __tablename__ = "child_instances"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    child_alias = db.Column(String(120), nullable=False)
    child_age = db.Column(Integer)

    evolution_instance_name = db.Column(String(64), unique=True, nullable=False, default=generate_instance_name)
    status = db.Column(Enum(ChildStatus, name="child_status"), nullable=False, default=ChildStatus.PENDING_QR)
    linked_phone = db.Column(String(32))

    # Ver ADR-0008. Si True, se persisten también los mensajes que el hijo envía
    # (dirección OUTBOUND). El análisis los usa como contexto de patrón (grooming
    # es bidireccional). El padre sigue viendo solo extractos de alertas.
    monitor_outbound = db.Column(Boolean, default=True, nullable=False)

    # Token público que se le entrega al menor para acceder a /mi-monitoreo.
    # No expone datos hasta que exista ConsentRecord activo.
    minor_access_token = db.Column(String(64), unique=True, nullable=False,
                                   default=lambda: secrets.token_urlsafe(32))

    created_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
    connected_at = db.Column(DateTime(timezone=True))
    revoked_at = db.Column(DateTime(timezone=True))

    user = relationship("User", back_populates="children")
    consent = relationship("ConsentRecord", back_populates="child_instance",
                           uselist=False, cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="child_instance", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="child_instance", cascade="all, delete-orphan")
    risk_events = relationship("RiskEvent", back_populates="child_instance", cascade="all, delete-orphan")

    @property
    def has_active_consent(self) -> bool:
        return self.consent is not None and self.consent.revoked_at is None

    @property
    def is_monitoring_active(self) -> bool:
        return self.status == ChildStatus.CONNECTED and self.has_active_consent


# --------------------------------------------------------------------------- #
# Consentimiento del menor (bloqueante — ver ADR-0002)
# --------------------------------------------------------------------------- #

class ConsentRecord(db.Model):
    __tablename__ = "consent_records"

    id = db.Column(Integer, primary_key=True)
    child_instance_id = db.Column(Integer, ForeignKey("child_instances.id", ondelete="CASCADE"),
                                  nullable=False, unique=True)

    accepted_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
    accepted_from_ip = db.Column(String(64))
    user_agent = db.Column(String(500))
    consent_text_hash = db.Column(String(128), nullable=False)
    consent_text_version = db.Column(String(32), nullable=False)

    revoked_at = db.Column(DateTime(timezone=True))
    revoked_reason = db.Column(Text)

    child_instance = relationship("ChildInstance", back_populates="consent")


# --------------------------------------------------------------------------- #
# Contactos y conversaciones
# --------------------------------------------------------------------------- #

class Contact(db.Model):
    __tablename__ = "contacts"

    id = db.Column(Integer, primary_key=True)
    child_instance_id = db.Column(Integer, ForeignKey("child_instances.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    phone_jid = db.Column(String(64), nullable=False)
    display_name = db.Column(String(255))
    first_seen_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_message_at = db.Column(DateTime(timezone=True))
    is_group = db.Column(Boolean, default=False, nullable=False)
    trust_level = db.Column(Enum(TrustLevel, name="trust_level"), default=TrustLevel.UNKNOWN, nullable=False)

    child_instance = relationship("ChildInstance", back_populates="contacts")
    conversations = relationship("Conversation", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("child_instance_id", "phone_jid", name="uq_contact_child_jid"),
    )


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(Integer, primary_key=True)
    child_instance_id = db.Column(Integer, ForeignKey("child_instances.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    contact_id = db.Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"),
                           nullable=False, unique=True, index=True)

    last_analyzed_at = db.Column(DateTime(timezone=True))
    last_analyzed_message_id = db.Column(Integer, ForeignKey("messages.id", use_alter=True,
                                                             name="fk_conv_last_analyzed_msg"))
    message_count = db.Column(Integer, default=0, nullable=False)

    child_instance = relationship("ChildInstance", back_populates="conversations")
    contact = relationship("Contact", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation",
                            foreign_keys="Message.conversation_id",
                            cascade="all, delete-orphan",
                            order_by="Message.timestamp")


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(Integer, primary_key=True)
    conversation_id = db.Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    wa_message_id = db.Column(String(128), nullable=False)
    direction = db.Column(Enum(MessageDirection, name="message_direction"), nullable=False)
    sender_jid = db.Column(String(64), nullable=False)
    body = db.Column(Text)
    media_type = db.Column(Enum(MediaType, name="media_type"))
    media_ref = db.Column(String(500))

    timestamp = db.Column(DateTime(timezone=True), nullable=False)
    received_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
    purge_at = db.Column(DateTime(timezone=True), nullable=False, index=True)

    conversation = relationship("Conversation", back_populates="messages",
                                foreign_keys=[conversation_id])

    __table_args__ = (
        UniqueConstraint("conversation_id", "wa_message_id", name="uq_msg_conv_waid"),
        Index("ix_msg_conv_ts", "conversation_id", "timestamp"),
    )


# --------------------------------------------------------------------------- #
# Alertas
# --------------------------------------------------------------------------- #

class RiskEvent(db.Model):
    __tablename__ = "risk_events"

    id = db.Column(Integer, primary_key=True)
    child_instance_id = db.Column(Integer, ForeignKey("child_instances.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    conversation_id = db.Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    contact_id = db.Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)

    severity = db.Column(Enum(RiskSeverity, name="risk_severity"), nullable=False)
    categories = db.Column(JSONB)
    reasons = db.Column(Text, nullable=False)
    excerpt = db.Column(JSONB)
    model_used = db.Column(String(64))
    tokens_used = db.Column(Integer)

    created_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
    notified_at = db.Column(DateTime(timezone=True))
    reviewed_at = db.Column(DateTime(timezone=True))
    reviewer_note = db.Column(Text)

    child_instance = relationship("ChildInstance", back_populates="risk_events")
    contact = relationship("Contact")
    conversation = relationship("Conversation")

    __table_args__ = (
        Index("ix_risk_child_sev_created", "child_instance_id", "severity", "created_at"),
    )


# --------------------------------------------------------------------------- #
# Auditoría
# --------------------------------------------------------------------------- #

class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(Integer, primary_key=True)
    actor_type = db.Column(Enum(ActorType, name="actor_type"), nullable=False)
    actor_id = db.Column(Integer)
    action = db.Column(String(64), nullable=False)
    target_type = db.Column(String(64))
    target_id = db.Column(Integer)
    ip = db.Column(String(64))
    user_agent = db.Column(String(500))
    audit_metadata = db.Column("metadata", JSONB)
    created_at = db.Column(DateTime(timezone=True), default=utcnow, nullable=False)
