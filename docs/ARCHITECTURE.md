# Arquitectura

## Vista de 10.000 metros

```
┌─────────────┐        ┌────────────────────────────────────┐
│   Padre     │        │        App Antigrooming            │
│  (Browser)  │◄──────►│  Flask + SQLAlchemy + Postgres     │
└─────────────┘        │                                    │
                       │  ┌──────────────────────────────┐  │
                       │  │  Blueprints                  │  │
                       │  │  - auth                      │  │
                       │  │  - linking (QR + consent)    │  │
                       │  │  - dashboard                 │  │
                       │  │  - webhook (Evolution → app) │  │
                       │  └──────────────────────────────┘  │
                       │  ┌──────────────────────────────┐  │
                       │  │  Services                    │  │
                       │  │  - evolution_client          │  │
                       │  │  - analysis_service (IA)     │  │
                       │  │  - mail_service              │  │
                       │  │  - consent_service           │  │
                       │  └──────────────────────────────┘  │
                       └────┬───────────────────┬───────────┘
                            │                   │
                     webhook│                   │REST (crear
                            │                   │instance, QR,
                            │                   │enviar, etc.)
                            ▼                   ▼
                       ┌────────────────────────────────┐
                       │        Evolution API           │
                       │  (una instancia por hijo)      │
                       └────────────────┬───────────────┘
                                        │ WhatsApp Web protocol
                                        ▼
                                ┌───────────────┐
                                │ WhatsApp del  │
                                │     hijo      │
                                └───────────────┘
```

## Componentes

### Web app (Flask)
Monolito modularizado con Blueprints. La razón por la que **no** replicamos el patrón "todo en `app.py`" del CRM (que llegó a 8000+ líneas) está registrada en [DECISIONS.md ADR-0001](DECISIONS.md).

### Base de datos
Postgres (Supabase u otro). SQLAlchemy como ORM. Ver [DATA_MODEL.md](DATA_MODEL.md).

### Evolution API
Servicio externo que expone WhatsApp Web como REST. Cada hijo vinculado = una `instance` en Evolution.

- **Crear instancia**: `POST /instance/create` con `instanceName` único.
- **Conectar (obtener QR)**: `GET /instance/connect/{instanceName}`.
- **Estado**: `GET /instance/connectionState/{instanceName}`.
- **Webhook por instancia**: se configura al crear, apunta a `/webhook/evolution` de nuestra app.
- **Eliminar**: `DELETE /instance/delete/{instanceName}`.

### IA de análisis
Servicio interno que analiza **conversaciones enteras**, no mensajes sueltos. Ver [ANALYSIS_PIPELINE.md](ANALYSIS_PIPELINE.md).

### Mail
Servicio con SMTP genérico. Solo se dispara en severidad `HIGH`. En v1 usamos SMTP simple (Gmail/SendGrid).

## Flujo de datos: mensaje entrante → alerta

```
1. WhatsApp del hijo recibe un mensaje.
2. Evolution API detecta el evento y POSTea a /webhook/evolution.
3. Webhook receiver:
   a. Extrae `instance` del payload.
   b. Busca ChildInstance por instance_name → obtiene user_id (padre).
   c. Persiste el mensaje en la conversación correspondiente.
4. Un job (mismo request o async) verifica si esta conversación debe analizarse
   (heurística: cada N mensajes nuevos o cada X minutos).
5. Si corresponde: analysis_service.analyze_conversation(conversation_id).
   - Aplica filtros baratos (heurística, keywords, señales de contacto).
   - Si pasa el filtro, invoca al modelo con el contexto completo.
   - Produce un RiskEvent con severity (LOW/MEDIUM/HIGH), reasons, excerpt.
6. Si severity == HIGH: mail_service.send_alert(user, risk_event).
7. En cualquier caso, el RiskEvent aparece en el dashboard.
```

## Multi-tenancy

- Un `User` (padre) puede tener múltiples `ChildInstance` (varios hijos).
- Cada `ChildInstance` mapea 1-a-1 con una `instance_name` en Evolution.
- El webhook usa `instance` del payload como pivote para resolver el tenant.
- Toda query que expone datos al padre debe filtrar por `user_id` explícito.

## Zona horaria

El sistema opera en UTC internamente y presenta al usuario en `America/Argentina/Buenos_Aires`. Reutilizamos el patrón de filtros Jinja del CRM.
