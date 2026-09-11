# Pipeline de análisis de grooming

## Objetivo
Detectar patrones de grooming en conversaciones que le llegan a un menor. **No** clasificar mensajes sueltos.

## Definición operativa de grooming
El grooming es un proceso de manipulación con estas fases clásicas (útiles como señales):

1. **Selección y aproximación**: contacto nuevo, aparente empatía, intereses en común.
2. **Formación de vínculo**: elogios sostenidos, disponibilidad emocional, "confidente".
3. **Aislamiento**: "esto queda entre nosotros", "no le cuentes a tus papás", "no me entienden como vos".
4. **Desensibilización**: introducción gradual de temas sexuales, chistes, contenido subido de tono.
5. **Escalada sexual**: pedidos de fotos, envío de material, sexting.
6. **Mantenimiento / coerción**: amenazas, chantaje si el menor se resiste.
7. **Intento de encuentro físico o cambio de plataforma**: propuestas de verse, cambio a Telegram/Signal/plataformas efímeras.

Fuentes de referencia: guías de UNICEF, ECPAT, Grooming Argentina.

## Estrategia en tres etapas

```
   Mensaje entrante ────┐
                        ▼
              ┌──────────────────┐
              │  Ingesta y stage │  siempre
              │  (persistencia)  │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Etapa 1: filtros │
              │ baratos (regex + │  ~ms
              │ señales contexto)│
              └────────┬─────────┘
                       │ activa?
                       ▼
              ┌──────────────────┐
              │ Etapa 2: LLM     │
              │ análisis         │  segundos
              │ conversacional   │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Etapa 3:         │
              │ RiskEvent +      │
              │ notificación     │
              └──────────────────┘
```

### Etapa 1 — Filtros baratos
Sin llamadas a LLM. Se ejecuta en el mismo request del webhook.

Activadores (basta con uno):
- **Contacto nuevo con actividad intensa**: `Contact.first_seen_at < 7 días` y `Conversation.message_count >= 20`.
- **Keywords de riesgo**: lista curada (multi-idioma / argot) — palabras y frases asociadas a fases 3–7. Ver `services/analysis_service.py`.
- **Horario nocturno recurrente**: mensajes entre 00:00 y 06:00 en varios días.
- **Enlaces a otras plataformas**: menciones de Telegram, Signal, Discord, Snapchat, TikTok DMs, junto con verbos de acción ("mandame", "vení", "cambiémonos").
- **Frecuencia**: cambio abrupto de baseline (contacto que pasa de 2 mensajes/día a 50/día).
- **Alerta previa** en el mismo contacto (accelera re-análisis).

Si no activa → no se corre LLM. Nada se marca. Se sigue.

### Etapa 2 — Análisis conversacional con LLM

Input al modelo:
- Datos de contexto: edad estimada del menor, alias del hijo, número de mensajes de la conversación, since first_seen del contacto, si es grupo o 1-a-1.
- **La conversación completa** (últimos ~200 mensajes o desde `last_analyzed_message_id`).
- Historial resumido de RiskEvents previos con este contacto.

Output esperado (JSON estructurado):
```json
{
  "severity": "LOW" | "MEDIUM" | "HIGH" | "NONE",
  "categories": ["escalada_sexual", "aislamiento", "cambio_plataforma", ...],
  "reasons": "Explicación en 2-4 oraciones citando fases del grooming detectadas.",
  "excerpt_message_ids": [123, 145, 178],
  "confidence": 0.0-1.0,
  "recommend_action": "monitor" | "confront" | "denounce"
}
```

**Regla de severidad** (guía para el prompt, no lógica de negocio del backend):
- `NONE`: conversación normal.
- `LOW`: alguna señal aislada, probablemente falso positivo.
- `MEDIUM`: múltiples señales, escalada leve.
- `HIGH`: escalada sexual explícita, pedido de fotos, propuesta de encuentro, aislamiento activo, o coerción.

### Etapa 3 — Persistencia y notificación
- Se crea `RiskEvent` con severity, categories, reasons, `excerpt` (los mensajes referenciados).
- Se actualiza `Conversation.last_analyzed_at` y `last_analyzed_message_id`.
- Si `severity == HIGH`:
  - `mail_service.send_alert(user, risk_event)`.
  - `RiskEvent.notified_at = now()`.

## Modelo por default
- v0.2: `gpt-5-mini` o equivalente para volumen. Fallback a `gpt-5` cuando severity previa es HIGH (revisión más fina).
- Uso de function calling / structured outputs para forzar el schema JSON.
- Sin costo como restricción en v1, pero telemetría de tokens siempre se guarda en `RiskEvent.tokens_used`.

## Falsos positivos y feedback
El padre puede marcar un `RiskEvent` como "no era nada". Eso:
1. Registra en `AuditLog`.
2. En el futuro alimenta un prompt de calibración (o fine-tune).

## Anti-abuso del modelo
- El prompt del sistema instruye no revelar sus reglas.
- El prompt del sistema **NO** se muestra al padre. Se muestra solo `reasons` y `categories`.
- Los mensajes se pasan sanitizados (sin instrucciones que puedan hacer prompt injection en la conversación misma).

## Métricas a trackear (v0.3)
- Recall (alertas detectadas / alertas reales) — via revisión manual de dataset.
- Precisión (alertas correctas / alertas emitidas) — via feedback del padre.
- Latencia (recepción → RiskEvent).
- Costo por hijo-día.
