# Setup de desarrollo

## Requisitos
- Python 3.11+
- Postgres 14+ (local o Supabase / Neon / hosted)
- Instancia de Evolution API accesible (URL + API key)
- Cuenta SMTP para mails (Gmail App Password, SendGrid, Mailtrap para dev)
- Cuenta OpenAI

## Paso a paso

### 1. Clonar y crear venv
```bash
cd "Proyecto antigrooming"
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Bash (git bash)
source .venv/Scripts/activate

pip install -r requirements.txt
```

### 2. Copiar `.env.example` a `.env`
```bash
cp .env.example .env
```

Editar `.env` con las credenciales reales. **Nunca commitear `.env`**. Ver [.gitignore](../.gitignore).

Variables mínimas para correr:
- `DATABASE_URL` — Postgres URI.
- `SECRET_KEY` — clave Flask (`python -c "import secrets; print(secrets.token_hex(32))"`).
- `EVOLUTION_API_URL` y `EVOLUTION_API_KEY` — credenciales de tu Evolution API.
- `PUBLIC_BASE_URL` — URL pública donde Evolution puede llegar a nuestro webhook (usar ngrok o Cloudflare Tunnel en dev).
- `OPENAI_API_KEY` — para el análisis (v0.2 en adelante).
- `SMTP_*` — para mails (v0.2 en adelante).

### 3. Crear la base
El primer arranque ejecuta `db.create_all()`. Para producción usamos scripts de migración en `migrations/`.

### 4. Correr
```bash
python main.py
```

Servidor en `http://localhost:5000`.

### 5. Exponer para Evolution API (dev)
Evolution necesita poder POSTear a nuestro webhook. En dev:

```bash
# opción a: ngrok
ngrok http 5000
# opción b: cloudflared
cloudflared tunnel --url http://localhost:5000
```

Copiar la URL pública y setearla como `PUBLIC_BASE_URL`.

## Vinculación de un hijo (flujo manual de prueba)

1. Ir a `/signup`, crear cuenta de padre.
2. Aceptar términos.
3. Ir a `/link/new`, poner alias y edad del hijo.
4. Sistema crea instancia en Evolution y muestra QR + explicación.
5. Escanear con el WhatsApp del hijo.
6. Pantalla de consentimiento del menor aparece (en la misma pantalla que muestra el QR, con checkbox).
7. Al confirmar consentimiento y estado connected → dashboard.

## Diseño de tests (v0.3)
Ver [ROADMAP.md](ROADMAP.md).
