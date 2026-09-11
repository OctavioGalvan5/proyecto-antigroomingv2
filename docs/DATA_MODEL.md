# Modelo de datos

## Entidades

### User (padre/tutor)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| email | str unique | login |
| password_hash | str | werkzeug hash |
| full_name | str | opcional |
| created_at | datetime UTC | |
| last_login_at | datetime UTC | |
| accepted_terms_at | datetime UTC | acepta términos del servicio |
| terms_version | str | versión del texto aceptado |

### ChildInstance (WhatsApp del hijo vinculado)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| user_id | FK User | dueño |
| child_alias | str | "Juan", "hija menor", como quiera el padre |
| child_age | int nullable | opcional, mejora análisis |
| evolution_instance_name | str unique | ej. `child_a1b2c3d4` |
| status | enum | `PENDING_QR`, `CONNECTED`, `DISCONNECTED`, `REVOKED` |
| linked_phone | str nullable | número que conecta, se llena al escanear |
| created_at | datetime UTC | |
| connected_at | datetime UTC nullable | primera conexión efectiva |
| revoked_at | datetime UTC nullable | si se desvinculó |

### ConsentRecord (consentimiento del menor)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| child_instance_id | FK ChildInstance | |
| accepted_at | datetime UTC | |
| accepted_from_ip | str | |
| user_agent | str | |
| consent_text_hash | str | hash SHA-256 del texto exacto que aceptó |
| consent_text_version | str | ej. `v1` |
| revoked_at | datetime UTC nullable | si el menor revocó |
| revoked_reason | str nullable | texto libre |

### Contact (contacto del hijo)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| child_instance_id | FK ChildInstance | |
| phone_jid | str | `54911...@s.whatsapp.net` |
| display_name | str nullable | push_name del contacto |
| first_seen_at | datetime UTC | |
| last_message_at | datetime UTC | |
| is_group | bool | si es grupo |
| trust_level | enum | `UNKNOWN`, `TRUSTED`, `FLAGGED` — set manual por padre |

Unique: `(child_instance_id, phone_jid)`.

### Conversation (hilo con un contacto)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| child_instance_id | FK ChildInstance | |
| contact_id | FK Contact | |
| last_analyzed_at | datetime UTC nullable | último análisis |
| last_analyzed_message_id | FK Message nullable | hasta dónde analizamos |
| message_count | int | contador rápido para heurísticas |

### Message
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| conversation_id | FK Conversation | |
| wa_message_id | str | id de WhatsApp para dedup |
| direction | enum | `INBOUND`, `OUTBOUND` |
| sender_jid | str | quién lo mandó |
| body | text nullable | texto plano |
| media_type | enum nullable | `IMAGE`, `AUDIO`, `VIDEO`, `DOC`, `STICKER` (fuera de v1) |
| media_ref | str nullable | id local o url del media (v2+) |
| timestamp | datetime UTC | ts real de WhatsApp |
| received_at | datetime UTC | cuándo llegó a nuestro webhook |
| purge_at | datetime UTC | cuándo se elimina el body por retención |

Índices: `(conversation_id, timestamp DESC)`, `(purge_at)` para job de retención.

### RiskEvent (alerta generada por la IA)
| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| child_instance_id | FK ChildInstance | |
| conversation_id | FK Conversation | |
| contact_id | FK Contact | denormalizado para queries rápidas |
| severity | enum | `LOW`, `MEDIUM`, `HIGH` |
| categories | jsonb | ej. `["escalada_sexual","aislamiento"]` |
| reasons | text | narrativa de la IA |
| excerpt | jsonb | lista de mensajes que dispararon la alerta |
| model_used | str | ej. `gpt-5-mini` |
| tokens_used | int | telemetría |
| created_at | datetime UTC | |
| notified_at | datetime UTC nullable | cuándo se mandó mail |
| reviewed_at | datetime UTC nullable | padre marcó como revisado |
| reviewer_note | text nullable | anotación del padre |

Índice: `(child_instance_id, severity, created_at DESC)`.

### AuditLog
Trazabilidad de acciones sensibles (padre viendo contexto ampliado, revocaciones, cambios de config).

| Campo | Tipo | Notas |
|-------|------|-------|
| id | int PK | |
| actor_type | enum | `USER`, `MINOR`, `SYSTEM` |
| actor_id | int nullable | |
| action | str | ej. `viewed_full_context`, `revoked_consent` |
| target_type | str nullable | |
| target_id | int nullable | |
| ip | str nullable | |
| user_agent | str nullable | |
| metadata | jsonb | |
| created_at | datetime UTC | |

## Relaciones (resumen)

```
User 1 ─── N ChildInstance 1 ─── 1 ConsentRecord
                     │
                     ├── N Contact
                     ├── N Conversation ── N Message
                     └── N RiskEvent
```

## Retención

Job diario:
- `Message` con `purge_at < now()`: se hace `body = NULL` y `media_ref = NULL`, se mantiene el resto para estadística/auditoría.
- `RiskEvent` viejos (>1 año): se eliminan.
- `ConsentRecord`: nunca se borra mientras el `User` exista + 5 años tras cierre de cuenta.
- `AuditLog`: 2 años.
