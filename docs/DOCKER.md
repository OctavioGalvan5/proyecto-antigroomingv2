# Docker / Deployment

Documentación de cómo containerizar y deployar el sistema.

## Archivos involucrados

| Archivo | Cuándo se usa |
|---------|---------------|
| `Dockerfile` | Build de la imagen. Válido para dev y prod. |
| `.dockerignore` | Qué NO copiar al context de build (secretos, docs, .venv). |
| `docker-compose.yml` | Producción / Dokploy. Postgres externo (Supabase). |
| `docker-compose.dev.yml` | Dev local. Postgres embebido. |

## Build local

```bash
docker build -t antigrooming:latest .
```

## Correr en dev con Postgres embebido

```bash
docker compose -f docker-compose.dev.yml up --build
```

App en `http://localhost:5000`, Postgres en `localhost:5433`.

**Antes de correr**, exportar (o poner en `.env`) las variables:
- `EVOLUTION_API_URL`
- `EVOLUTION_API_KEY`
- `PUBLIC_BASE_URL` (por ejemplo el ngrok apuntando a localhost:5000)

## Correr en prod con Postgres externo (Supabase)

```bash
docker compose --env-file .env up -d --build
```

O usar Dokploy (ver sección abajo).

## Deploy en Dokploy

1. **Crear Application** → tipo *Docker Compose*.
2. **Source**: apuntá al repo Git donde vas a pushear este proyecto.
3. **Compose file**: `docker-compose.yml` (default).
4. **Environment**: pegá el contenido de tu `.env` (sin `PUBLIC_BASE_URL` — ese lo configuramos abajo).
5. **Domains**: asigná un dominio, ej. `antigrooming.tudominio.com`. Dokploy le pone SSL automático con Let's Encrypt.
6. Cuando esté deployado con dominio, **volvé a Environment** y seteá:
   ```
   PUBLIC_BASE_URL=https://antigrooming.tudominio.com
   ```
   Y redeploy. Esto es lo que Evolution API va a usar para postear el webhook.

## Verificaciones post-deploy

1. Abrir `https://antigrooming.tudominio.com/auth/signup` → debe cargar la pantalla de registro.
2. Crear cuenta de prueba.
3. Ir a `/link/new` → crear una vinculación → confirmar que aparece el QR.
4. Escanear con un WhatsApp de prueba.
5. Aceptar el consentimiento del menor.
6. Enviar un mensaje al número vinculado desde otro celular.
7. En logs de Dokploy: buscar `MESSAGES_UPSERT` y verificar que se guardó el mensaje.

## Rotar credenciales

Si comprometiste una key:
1. Revocar en el proveedor (Supabase / Evolution / OpenAI).
2. Actualizar variable en Dokploy → redeploy.

## Notas sobre imagen

- Base: `python:3.11-slim`.
- Usuario no-root (`appuser`) para runtime.
- `libpq-dev` y `gcc` se instalan sólo para compilar `psycopg2-binary`; después se limpian.
- Healthcheck HTTP contra `/` cada 30s.
- `gunicorn` con 2 workers × 4 threads. Ajustar cuando tengamos volumen real.
