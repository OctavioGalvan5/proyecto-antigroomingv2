# Roadmap

## v0.1 — Fundaciones (esta iteración)
- [x] Documentación fundacional
- [ ] Estructura de proyecto (Flask + Blueprints + SQLAlchemy)
- [ ] Modelos de DB
- [ ] Config con `.env` (sin credenciales del CRM)
- [ ] Cliente Evolution API multi-instancia (crear, conectar, QR, estado, eliminar)
- [ ] Auth: signup / login / logout del padre
- [ ] Términos y consentimiento del padre
- [ ] Vinculación de hijo: alias + edad → creación de instancia → QR
- [ ] Pantalla de consentimiento del menor (mostrar QR con explicación)
- [ ] Webhook receiver que rutea al `ChildInstance` correcto y persiste mensajes
- [ ] Esqueleto documentado del pipeline de análisis
- [ ] Esqueleto documentado del servicio de mail

## v0.2 — Análisis básico
- [x] Pipeline de análisis: filtro heurístico + LLM sobre conversación completa
- [x] Generación de `RiskEvent` con severidad
- [x] Dashboard de alertas para el padre (lista, filtros, detalle)
- [x] Mail de alerta severidad HIGH (con degradación si no hay SMTP)
- [x] Endpoint `/mi-monitoreo` para el menor (ver estado, revocar)
- [x] Toggle outbound por instancia (ADR-0008)

## v0.3 — Robustez
- [ ] Job de retención (30 días de mensajes)
- [ ] Reconexión automática si Evolution reporta desconexión
- [ ] Rate limiting en endpoints públicos
- [ ] Auditoría de acciones sensibles
- [ ] Tests de integración del pipeline

## v0.4 — Extensiones (candidatas)
- [ ] Análisis de imágenes (detectar imágenes explícitas enviadas al menor)
- [ ] Análisis de audios (transcripción → mismo pipeline)
- [ ] Bloqueo/silenciamiento de contactos flagged
- [ ] Multi-hijo por padre en misma UI
- [ ] App móvil PWA con push notifications (ya hay VAPID en el CRM base)

## Fuera de scope (explícito)

- **NO** vamos a permitir que el padre lea todas las conversaciones. Solo el contexto de alertas.
- **NO** vamos a monitorear mensajes salientes del hijo (privacidad; el grooming se detecta desde el que llega).
  - Excepción posible en v0.4: si la conversación disparó alerta HIGH, incluir respuestas del hijo en el análisis para confirmar patrón.
- **NO** vamos a integrar con otras plataformas (Instagram, Discord) en 2026. Sólo WhatsApp.
- **NO** vamos a hacer web scraping ni interceptar SSL. Todo pasa por la instancia Evolution que el hijo autorizó.

## Riesgos abiertos

| Riesgo | Mitigación |
|--------|-----------|
| Evolution API discontinuada o inestable | Documentar el cliente para que sea reemplazable. Baileys/WPPConnect son alternativas. |
| Falsos positivos ruidosos | Calibración iterativa. Padres pueden marcar RiskEvent como "no era nada" y eso alimenta prompt. |
| WhatsApp bloquea la cuenta del hijo por uso multi-dispositivo intenso | Documentar en onboarding. No usar la instancia para enviar, solo leer. |
| Menor pierde acceso o cambia celular | Flujo de re-vinculación con nuevo consentimiento. |
| Padre malicioso (control abusivo, no protección) | Requerir DNI del padre en signup + validación básica (fase futura). |
