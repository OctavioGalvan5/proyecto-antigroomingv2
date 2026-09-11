# Documentación — Sistema Antigrooming

Este directorio contiene toda la documentación viva del proyecto. Se actualiza junto con el código, no después.

## Índice

| Documento | Para qué sirve |
|-----------|----------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura de alto nivel, componentes, flujo de datos |
| [LEGAL_ETHICS.md](LEGAL_ETHICS.md) | Marco legal argentino, principios éticos, textos de consentimiento |
| [DATA_MODEL.md](DATA_MODEL.md) | Modelo de datos, entidades, relaciones, retención |
| [ROADMAP.md](ROADMAP.md) | Alcance por fase. Qué entra en v1, qué queda para después |
| [DECISIONS.md](DECISIONS.md) | Log de decisiones arquitectónicas (ADRs) |
| [DEV_SETUP.md](DEV_SETUP.md) | Cómo levantar el proyecto en local |
| [DOCKER.md](DOCKER.md) | Build, docker compose, deploy en Dokploy |
| [ANALYSIS_PIPELINE.md](ANALYSIS_PIPELINE.md) | Diseño del pipeline de detección de grooming |

## Principios rectores

1. **Consentimiento del menor es innegociable.** El sistema no se activa sin registro explícito de que el menor entendió qué se monitorea.
2. **Mínima exposición.** El padre ve señales de riesgo con contexto acotado, no la conversación completa.
3. **Severidad calibrada.** Solo severidad alta genera mail. Todo lo demás queda en el panel.
4. **Retención corta.** Los mensajes se retienen 30 días por default; después se resumen o eliminan.
5. **Transparencia.** El menor puede ver qué se está monitoreando y solicitar desvincular.
