# 🚀 Deploy Athena Backend to Render

## Quick Deployment Guide

### Prerequisites
✅ Render account (sign up at https://render.com)  
✅ Neon PostgreSQL database (you already have this)  
✅ Groq API key (you already have this)  
✅ NVIDIA API key (you already have this)  

---

## Step 1: Create Web Service on Render

1. Go to https://dashboard.render.com/
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository (or deploy from this directory)
4. Configure:
   - **Name:** `athena-backend` (or your preferred name)
   - **Region:** Choose closest to you (e.g., Oregon, Ohio)
   - **Branch:** `main`
   - **Root Directory:** Leave empty
   - **Runtime:** `Python 3` (auto-detected from runtime.txt → Python 3.11.9)
   - **Build Command:** `pip install -r requirements-production.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   
   > **Note:** We use Python 3.11.9 (specified in `runtime.txt`) because it has pre-built wheels for all packages. Python 3.14 is too new and requires building from source.

---

## Step 2: Environment Variables (CRITICAL!)

Add these in Render Dashboard → Environment → Environment Variables:

### ✅ REQUIRED (Must set these!)

```bash
# ═══════════════════════════════════════════════════════════════
# PYTHON VERSION (CRITICAL - Set this FIRST!)
# ═══════════════════════════════════════════════════════════════
PYTHON_VERSION=3.11.9

# ⚠️ IMPORTANT: Render defaults to Python 3.14 which is too new!
# SQLAlchemy and other packages don't support it yet.
# You MUST set PYTHON_VERSION to 3.11.9 manually in Render dashboard.
# runtime.txt does NOT work on Render (it's for Heroku only).

# ═══════════════════════════════════════════════════════════════
# DATABASE (REQUIRED)
# ═══════════════════════════════════════════════════════════════
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_QinvghC6l3mk@ep-long-sky-aes9llxp-pooler.c-2.us-east-2.aws.neon.tech/neondb

# ═══════════════════════════════════════════════════════════════
# LLM - At least ONE is required (Groq recommended - FREE)
# ═══════════════════════════════════════════════════════════════
GROQ_API_KEY=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
GROQ_MODEL=openai/gpt-oss-20b

# ═══════════════════════════════════════════════════════════════
# SERVER CONFIGURATION
# ═══════════════════════════════════════════════════════════════
HOST=0.0.0.0
PORT=10000
LOG_LEVEL=info
DEBUG=false
```

### ⚠️ OPTIONAL (Add if you have them)

```bash
# ───────────────────────────────────────────────────────────────
# Additional LLM Providers (for redundancy)
# ───────────────────────────────────────────────────────────────
NVIDIA_API_KEY=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
NVIDIA_MODEL=deepseek-v4-pro-0813

ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-3-5-haiku-20241022

# ───────────────────────────────────────────────────────────────
# Ollama (Local only - don't set on Render)
# ───────────────────────────────────────────────────────────────
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.2
```

### 📦 NOT NEEDED on Render (local/optional features)

```bash
# These features won't work on Render (require local setup):
# - ChromaDB (memory)
# - Whisper (STT)
# - Piper (TTS)
# - Torch (VAD)
# - Smart Home (Home Assistant)
# - SearXNG (Web Search)

# Don't add these to Render:
# CHROMA_PERSIST_DIR
# WHISPER_MODEL_SIZE
# PIPER_MODEL_PATH
# HASS_URL
# HASS_TOKEN
# SEARXNG_URL
```

---

## Step 3: Complete Environment Variables List for Copy-Paste

**⚠️ CRITICAL: Add PYTHON_VERSION first, then the rest!**

**Copy each line and add to Render → Environment → Add Environment Variable:**

```
PYTHON_VERSION=3.11.9
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_QinvghC6l3mk@ep-long-sky-aes9llxp-pooler.c-2.us-east-2.aws.neon.tech/neondb
GROQ_API_KEY=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
GROQ_MODEL=openai/gpt-oss-20b
NVIDIA_API_KEY=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
NVIDIA_MODEL=deepseek-v4-pro-0813
HOST=0.0.0.0
PORT=10000
LOG_LEVEL=info
DEBUG=false
CLAUDE_MODEL=claude-3-5-haiku-20241022
```

> **⚠️ IMPORTANT:** You must add each variable separately in Render dashboard using the "Add Environment Variable" button. Click the Key field, paste the key name, click the Value field, paste the value, then click "Add". Repeat for each variable.

---

## Step 4: Deploy!

1. Click **"Create Web Service"**
2. Render will automatically:
   - Install dependencies from `requirements.txt`
   - Run database migrations
   - Start the server
3. Wait 3-5 minutes for first deploy
4. You'll get a URL like: `https://athena-backend.onrender.com`

---

## Step 5: Test Your Deployment

Once deployed, test it:

```bash
# Replace with your Render URL
export API_URL=https://athena-backend.onrender.com

# Test health
curl $API_URL/health

# Test chat
curl -X POST $API_URL/api/chat/text \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello Athena", "history": [], "tts": false}'

# Test learning
curl -X POST $API_URL/api/learning/teach \
  -H "Content-Type: application/json" \
  -d '{"category": "test", "key": "deployment", "value": "success", "source": "user"}'

curl -X POST $API_URL/api/learning/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is deployment?"}'
```

---

## Render Configuration File (Optional)

Create `render.yaml` in your repo root for infrastructure-as-code:

```yaml
services:
  - type: web
    name: athena-backend
    runtime: python
    plan: free  # or 'starter' for $7/month
    buildCommand: pip install -r requirements-production.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false  # Set manually in dashboard
      - key: GROQ_API_KEY
        sync: false
      - key: GROQ_MODEL
        value: openai/gpt-oss-20b
      - key: HOST
        value: 0.0.0.0
      - key: LOG_LEVEL
        value: info
      - key: DEBUG
        value: false
```

---

## Environment Variables Reference

### By Priority

#### 🔴 CRITICAL (App won't work without these)
- `PYTHON_VERSION` - **MUST BE 3.11.9** (Render defaults to 3.14 which breaks!)
- `DATABASE_URL` - Neon PostgreSQL connection string
- `GROQ_API_KEY` - Groq LLM API key (FREE)

#### 🟡 IMPORTANT (Recommended for production)
- `HOST` - `0.0.0.0` (required for Render)
- `PORT` - `10000` (Render default)
- `LOG_LEVEL` - `info` or `debug`
- `DEBUG` - `false` for production

#### 🟢 OPTIONAL (For additional features)
- `NVIDIA_API_KEY` - Backup LLM (FREE)
- `ANTHROPIC_API_KEY` - Best quality LLM ($1-3/month)
- `CLAUDE_MODEL` - Model to use if using Claude

#### ⚪ NOT NEEDED (Local features only)
- Anything related to: Ollama, Whisper, Piper, ChromaDB, Home Assistant, SearXNG

---

## Cost Breakdown

### Free Tier (Render + Groq)
```
✅ Render Free Plan: $0/month
   - 750 hours/month
   - Spins down after 15 min inactivity
   - 512 MB RAM

✅ Neon PostgreSQL: $0/month (free tier)
   - 0.5 GB storage
   - 1 compute unit

✅ Groq API: $0/month
   - 14,400 requests/day FREE
   - Very fast inference

TOTAL: $0/month
```

### Paid Tier (Better performance)
```
✅ Render Starter: $7/month
   - Always on
   - 512 MB RAM
   - Custom domain

✅ Neon: $0-19/month
   - Free tier usually enough

✅ Groq: $0/month (still free)

TOTAL: $7-26/month
```

---

## Common Issues & Solutions

### Issue 1: "Application failed to respond"
**Solution:** Check logs in Render dashboard
- Look for port binding issues
- Ensure `HOST=0.0.0.0` is set
- Verify `PORT` is set (Render uses 10000)

### Issue 2: "Database connection failed"
**Solution:** Verify DATABASE_URL
- Must start with `postgresql+asyncpg://`
- Check Neon database is active
- No `?sslmode=require` needed (asyncpg handles SSL)

### Issue 3: "API key not configured"
**Solution:** Add LLM API key
- At minimum: `GROQ_API_KEY`
- Check spelling (no typos)
- No spaces around `=` in env vars

### Issue 4: "Module not found"
**Solution:** Check requirements.txt
- All dependencies listed
- Run locally first to test
- Check Render build logs

### Issue 5: "502 Bad Gateway"
**Solution:** Server taking too long to start
- Check logs for Python errors
- Verify all required env vars set
- Try restarting service

---

## Monitoring Your Deployment

### View Logs
```
Render Dashboard → Your Service → Logs
```

### Check Metrics
```
Render Dashboard → Your Service → Metrics
- Request count
- Response times
- Memory usage
- CPU usage
```

### Health Check Endpoint
```bash
curl https://your-app.onrender.com/health
```

Should return:
```json
{
  "status": "healthy",
  "timestamp": "2026-09-06T...",
  "database": "connected"
}
```

---

## Updating Your Deployment

### Automatic (Recommended)
1. Push code to GitHub
2. Render auto-deploys on every push to main branch
3. Check logs to confirm successful deployment

### Manual
1. Render Dashboard → Your Service
2. Click **"Manual Deploy"** → **"Deploy latest commit"**

### ⚠️ Important Note
The production build uses `requirements-production.txt` which excludes local-only features:
- ❌ Ollama (use Groq/Claude APIs instead)
- ❌ Whisper STT (local models)
- ❌ Piper TTS (local models)
- ❌ ChromaDB (local storage)
- ❌ Face recognition, YOLO, OpenCV
- ✅ All API-based features work (Groq, Claude, NVIDIA, Google APIs)

---

## Custom Domain (Optional)

1. Render Dashboard → Your Service → Settings
2. Scroll to **"Custom Domain"**
3. Add your domain: `api.yourdomain.com`
4. Add DNS record at your domain registrar:
   ```
   Type: CNAME
   Name: api
   Value: athena-backend.onrender.com
   ```
5. Wait for DNS propagation (5-30 minutes)

---

## Production Checklist

### Before Deploy
- [ ] All environment variables set
- [ ] Database connection string correct
- [ ] At least one LLM API key configured
- [ ] `DEBUG=false` in production
- [ ] `requirements.txt` up to date

### After Deploy
- [ ] Health check passes
- [ ] Chat endpoint works
- [ ] Learning system works
- [ ] Database queries work
- [ ] Check logs for errors
- [ ] Test from mobile app

### Ongoing
- [ ] Monitor logs daily
- [ ] Check error rates
- [ ] Monitor API usage (Groq dashboard)
- [ ] Database storage usage (Neon dashboard)

---

## Next Steps

1. **Deploy now:**
   - Copy environment variables
   - Create web service on Render
   - Wait 5 minutes
   - Test API

2. **Update mobile app:**
   ```javascript
   const API_URL = 'https://your-app.onrender.com';
   ```

3. **Monitor:**
   - Check Render logs
   - Test all features
   - Monitor performance

---

## 🎉 You're Ready!

Your Athena backend will be:
- ✅ Live 24/7 (or on Render free tier)
- ✅ Accessible from anywhere
- ✅ Using production database
- ✅ Fast AI responses (Groq)
- ✅ All features working

**Total setup time: 10 minutes**

**Questions?** Check Render logs or test with curl commands above.

---

## Quick Copy-Paste Checklist

**Environment Variables (minimum required):**
```
PYTHON_VERSION=3.11.9
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_QinvghC6l3mk@ep-long-sky-aes9llxp-pooler.c-2.us-east-2.aws.neon.tech/neondb
GROQ_API_KEY=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
GROQ_MODEL=openai/gpt-oss-20b
HOST=0.0.0.0
PORT=10000
LOG_LEVEL=info
DEBUG=false
```

> **⚠️ CRITICAL:** Set `PYTHON_VERSION=3.11.9` in Render dashboard BEFORE deploying! Render defaults to Python 3.14 which causes SQLAlchemy typing errors.

**Build Command:**
```
pip install -r requirements-production.txt
```

**Start Command:**
```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**That's it!** 🚀
