# Deploy Athena Backend to Render

## Quick Deployment Guide

### Prerequisites
- Render account (sign up at https://render.com)
- Neon PostgreSQL database
- At least one LLM API key (Groq recommended — free)

---

## Step 1: Create Web Service on Render

1. Go to https://dashboard.render.com/
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name:** `athena-backend`
   - **Region:** Choose closest to you
   - **Branch:** `main`
   - **Runtime:** Python 3 (auto-detected from `runtime.txt` → Python 3.11.9)
   - **Build Command:** `pip install -r requirements-production.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`

   > **XFF / rate-limit note:** `--proxy-headers` makes uvicorn rewrite `request.client.host`
   > from `X-Forwarded-For`, but it uses the **leftmost** entry — which clients can spoof.
   > Athena ignores that and reads the **rightmost** XFF entry directly when `TRUST_PROXY=true`.
   > Render always appends the real client IP as the rightmost entry.

   > **Python version:** We use Python 3.11.9 (`runtime.txt`) because it has pre-built wheels
   > for all packages. Set `PYTHON_VERSION=3.11.9` manually in Render dashboard as well —
   > Render can default to a newer version that requires building from source.

---

## Step 2: Environment Variables

**Single source of truth: [`.env.production.example`](.env.production.example)**

Open `.env.production.example` — it lists every variable with inline annotations marking
which are **REQUIRED** and which are **OPTIONAL** (leave empty to disable the feature).

Copy each variable into Render Dashboard → Environment → Add Environment Variable.

### Minimum required set

| Variable | Notes |
|---|---|
| `PYTHON_VERSION` | `3.11.9` — set this **first** |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | Neon PostgreSQL connection string (PostgreSQL only; SQLite rejected) |
| `JWT_SECRET` | 64-char hex — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `CORS_ORIGINS` | Comma-separated list of your frontend URLs (no `*`, no `localhost`) |
| At least one of: `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `NVIDIA_API_KEY` | LLM key |
| `TRUST_PROXY` | `true` — enables real-IP rate limiting |

The app validates all of the above at startup. If anything is missing it exits immediately
with an "Invalid configuration" list rather than silently misbehaving.

---

## Step 3: Deploy

1. Click **"Create Web Service"**
2. Render installs dependencies, runs DB migrations, and starts the server
3. Wait 3–5 minutes for first deploy
4. Your URL: `https://athena-backend.onrender.com`

---

## Step 4: Test Your Deployment

```bash
export API_URL=https://athena-backend.onrender.com

# Health check
curl $API_URL/health

# Chat
curl -X POST $API_URL/api/chat/text \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello Athena", "history": [], "tts": false}'
```

---

## Render Configuration File (Optional)

Create `render.yaml` for infrastructure-as-code:

```yaml
services:
  - type: web
    name: athena-backend
    runtime: python
    plan: free
    buildCommand: pip install -r requirements-production.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: DATABASE_URL
        sync: false
      - key: JWT_SECRET
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: GROQ_MODEL
        value: openai/gpt-oss-20b
      - key: CORS_ORIGINS
        sync: false
      - key: TRUST_PROXY
        value: "true"
      - key: LOG_LEVEL
        value: info
      - key: DEBUG
        value: "false"
```

---

## What runs on Render vs. what doesn't

### Works on Render (API-based)
- All LLM providers (Groq, Claude, NVIDIA NIM)
- Database (Neon PostgreSQL)
- SearXNG web search (if you have a reachable SearXNG instance)
- Home Assistant (if reachable via a public hostname)
- Gemini image generation

### Local-only (excluded from `requirements-production.txt`)
- Ollama (local models) — set `OLLAMA_BASE_URL` only if you have a non-localhost Ollama server
- Whisper STT, Piper TTS, Torch VAD — local hardware models
- ChromaDB — local vector store

---

## Common Issues

### "Application failed to respond"
Check Render logs. Ensure `HOST=0.0.0.0` is bound. First startup log line should read:
```
Config: env=production db=postgresql llm=[groq] integrations=[]
```
If it says `llm=[none]`, no LLM key is configured — the app won't start.

### "Invalid configuration" on startup
The app prints a list of every failing check, e.g.:
```
Invalid configuration:
  - JWT_SECRET must be set in production
  - DATABASE_URL must not be SQLite in production
```
Fix each item in Render environment variables and redeploy.

### "Database connection failed"
Verify `DATABASE_URL` starts with `postgresql+asyncpg://`.

### "502 Bad Gateway"
Server is taking too long. Check Render logs for Python errors or missing env vars.

---

## Verifying Real-IP Detection (one-time)

Rate limits key on the real client IP (rightmost `X-Forwarded-For` entry when `TRUST_PROXY=true`).
To verify this is correct for your Render region:

1. Set `DEBUG_CLIENT_IP=true` and redeploy.
2. From **two different networks** hit:
   ```
   curl https://your-app.onrender.com/api/_debug/client-ip
   ```
3. Confirm `get_client_ip` matches your real public IP each time.
4. Set `DEBUG_CLIENT_IP=false` and redeploy. The route returns 404 when false.

---

## Production Checklist

### Before Deploy
- [ ] `PYTHON_VERSION=3.11.9` set in Render dashboard
- [ ] All REQUIRED variables from `.env.production.example` filled in
- [ ] `DEBUG=false`
- [ ] `TRUST_PROXY=true`
- [ ] `CORS_ORIGINS` contains only your real frontend origins

### After Deploy
- [ ] Startup log shows correct `env=production db=postgresql llm=[...]`
- [ ] Health check passes: `curl .../health`
- [ ] Chat endpoint works
- [ ] Database queries work
- [ ] Verify real-IP detection (see above)

---

## Cost Breakdown

### Free Tier
```
Render Free:  $0/month  (750 hrs/month, spins down after 15 min)
Neon:         $0/month  (0.5 GB storage)
Groq API:     $0/month  (14,400 req/day)
TOTAL: $0/month
```

### Paid Tier
```
Render Starter: $7/month (always on, 512 MB RAM, custom domain)
TOTAL: ~$7/month
```
