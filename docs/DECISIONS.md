# Decisiones arquitectónicas (ADRs)

Log append-only. Cada decisión describe contexto, opción elegida, alternativas y consecuencias. Si una decisión se revierte, se agrega una nueva entrada, no se edita la vieja.

---

## ADR-0001 — Blueprints en vez de monolito único

**Fecha**: 2026-09-11
**Contexto**: El CRM previo (`api de evolution api/app.py`) creció a 8000+ líneas en un solo archivo. Difícil de navegar, riesgo de merge conflicts, tests casi imposibles.
**Decisión**: Usar Flask Blueprints desde el día 1. Un blueprint por área funcional (`auth`, `linking`, `dashboard`, `webhook`). Servicios (Evolution, análisis, mail) en `services/`.
**Alternativas**:
- FastAPI: más moderno, pero rompe con lo que ya sabemos y agrega curva.
- Monolito en `app.py`: probado en el CRM, sabemos que escala mal.
**Consecuencias**:
- + Modularidad, testeo por unidad, onboarding más simple.
- − Un poco más de boilerplate al inicio.

---

## ADR-0002 — Consentimiento del menor como pre-requisito bloqueante

**Fecha**: 2026-09-11
**Contexto**: Ver [LEGAL_ETHICS.md](LEGAL_ETHICS.md). La legislación argentina (Ley 26.061, Ley 25.326, CCyC art. 26) exige informar al menor.
**Decisión**: `ChildInstance.status = CONNECTED` **exige** un `ConsentRecord` no revocado. Sin consentimiento, la conexión no se activa aunque el QR se haya escaneado. La UI del padre lo indica claramente.
**Consecuencias**:
- + Cumplimiento legal, defensibilidad.
- + Producto éticamente sostenible.
- − Fricción adicional en el onboarding. Aceptable.

---

## ADR-0003 — Padre ve solo alertas, no todas las conversaciones

**Fecha**: 2026-09-11
**Contexto**: Principio de mínima exposición. La legalidad del monitoreo se sostiene mejor cuando la exposición al monitor humano se limita a lo estrictamente necesario para proteger al menor.
**Decisión**: El padre nunca ve una lista de "todos los mensajes". Solo ve `RiskEvent` con extracto acotado. Puede solicitar contexto ampliado, pero eso queda auditado en `AuditLog`.
**Alternativas**:
- Timeline completo tipo Chatwoot: fue mi primer instinto. Descartado por privacidad del menor.
**Consecuencias**:
- + Defensibilidad legal.
- + Menor daño colateral en la relación padre-hijo.
- − Padres pueden querer más control. Se documenta esta decisión en el onboarding.

---

## ADR-0004 — Postgres + SQLAlchemy (no cambiamos el stack)

**Fecha**: 2026-09-11
**Contexto**: El CRM base usa Postgres/Supabase + SQLAlchemy 3.x. Funciona.
**Decisión**: Mismo stack. Base de datos separada del CRM. Credenciales separadas.
**Consecuencias**:
- + Cero curva.
- − Ninguna relevante.

---

## ADR-0005 — Nuevo Postgres, nuevo Evolution API, nuevas credenciales

**Fecha**: 2026-09-11
**Contexto**: El usuario pidió explícitamente no usar credenciales del CRM. El sistema antigrooming procesa datos de menores; mezclarlo con datos comerciales de otra app es un riesgo de compliance y de "blast radius" en caso de brecha.
**Decisión**: Base Postgres nueva, instancia Evolution API nueva (o al menos API key + BASE URL separadas si es la misma instalación auto-hospedada), MinIO/S3 nuevo si aplica, credenciales SMTP nuevas.
**Consecuencias**:
- + Aislamiento de blast radius.
- + Cumplimiento con separación de dominios.
- − Doble stack para operar. Aceptable dado el dominio sensible.

---

## ADR-0006 — Análisis por conversación, no por mensaje

**Fecha**: 2026-09-11
**Contexto**: El grooming es un patrón temporal (escalada, aislamiento, cambio de plataforma). Un mensaje aislado casi nunca lo revela.
**Decisión**: El pipeline procesa **conversaciones**. Trigger: cada N mensajes nuevos de un contacto o cada X minutos si hay mensajes sin analizar. El LLM recibe: conversación completa, perfil del contacto, edad estimada del hijo, historial de RiskEvents.
**Alternativas**:
- Análisis por mensaje: barato pero ciego al patrón.
- Análisis en tiempo real por cada mensaje entrante: no aporta valor y sube costo.
**Consecuencias**:
- + Precisión mucho mayor.
- − Latencia mayor entre mensaje sospechoso y alerta. Aceptable (grooming es de días/semanas, no de segundos).

---

## ADR-0008 — Monitoreo de mensajes salientes: toggleable, default ON

**Fecha**: 2026-09-11
**Contexto**: El pipeline de análisis originalmente proponía capturar solo mensajes ENTRANTES para minimizar la exposición del menor. Durante pruebas quedó claro que el grooming es una **dinámica bidireccional**: sin ver cómo responde el menor, se pierden señales clave (aislamiento activo, coerción efectiva, cambio de tono). Además el principio de "el padre solo ve extractos, no el chat" sigue cubriendo la exposición al monitor humano.
**Decisión**: Se agrega `ChildInstance.monitor_outbound` (bool, default `TRUE`). Cuando está en `TRUE`, los mensajes que el hijo envía se persisten con `direction=OUTBOUND` y el LLM los ve como contexto. El padre puede desactivarlo por instancia desde el panel. El texto de consentimiento (v2) lo declara explícitamente. El análisis se dispara **solo con mensajes INBOUND** (para no re-analizar en cada respuesta del hijo).
**Alternativas**:
- No capturar outbound (v1): analisis ciego al patrón, muchos falsos negativos.
- Capturar outbound sin opción de apagar: más invasivo que necesario.
**Consecuencias**:
- + Detección más precisa (patrón bidireccional).
- + Padre decide el nivel de intrusión.
- − Más datos del menor persistidos. Mitigado por: retención de 30 días, mínima exposición al padre, y consentimiento explícito v2.

---

## ADR-0007 — Mail solo en severidad HIGH

**Fecha**: 2026-09-11
**Contexto**: Padres desensibilizados dejan de leer alertas. El mail debe reservarse para lo urgente.
**Decisión**:
- `LOW`: solo aparece en el dashboard.
- `MEDIUM`: dashboard + push (cuando implementemos).
- `HIGH`: dashboard + push + mail.
**Consecuencias**:
- + Alertas mantienen valor.
- − Padres podrían perderse MEDIUM que escaló. Se compensa mostrando MEDIUM prominente en dashboard.
