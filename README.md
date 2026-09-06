# 🤖 Athena AI Backend

> **JARVIS-style AI assistant by Qoretex** — Professional, capable, always at your service.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Athena is an advanced AI assistant backend designed to be proactive, personal, and deeply integrated into your life. Like JARVIS to Tony Stark — professional, composed, and always aware of your context.

---

## ✨ Features

### 🎯 Tier-1 JARVIS Features
- **Context-Aware Automation** — Rules that trigger based on time, location, app usage, or patterns
- **Relationship Intelligence** — Track contacts, interactions, sentiment, and get AI follow-up suggestions
- **Focus Mode** — Auto-detect focus sessions, hold notifications, analyze productivity
- **Quick Actions** — Preset shortcuts: morning briefing, focus mode, wind down, catch up
- **Learning System** — Remembers preferences, facts, skills with natural language queries

### 🧠 Core AI Capabilities
- **4-Tier LLM Fallback** — Claude → Groq → NVIDIA → Ollama (always available)
- **JARVIS Personality** — Addresses you as "Sir", short precise responses, proactive suggestions
- **Voice Chat** — Wake word detection, STT with Whisper, TTS with Piper
- **Image Generation** — DALL-E 3 integration
- **Vision Analysis** — Claude Vision for image understanding
- **Knowledge Base** — ChromaDB vector search for documents

### 📱 Smart Features
- **Push Notifications** — Expo push service integration
- **Calendar & Email** — Google Calendar & Gmail integration
- **Weather** — OpenWeatherMap integration
- **Web Search** — SearXNG for privacy-focused search
- **Smart Home** — Home Assistant integration
- **Pattern Learning** — Learns from your behavior and suggests optimizations

### 🛠️ Developer Features
- **70+ API Endpoints** — Full REST API with Swagger docs
- **WebSocket Support** — Real-time communication
- **Async/Await** — High-performance FastAPI backend
- **PostgreSQL** — Production-ready database with 24 tables
- **Comprehensive Documentation** — Frontend integration guide included

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL (or use Neon free tier)
- Groq API key (FREE)

### Installation

```bash
# Clone repository
git clone https://github.com/QORETEX/Athena-backend.git
cd Athena-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
# For local development (includes all features):
pip install -r requirements.txt

# For production/Render (cloud-compatible only):
# pip install -r requirements-production.txt

# Copy environment variables
cp .env.example .env

# Edit .env and add your keys:
# - DATABASE_URL (get free from neon.tech)
# - GROQ_API_KEY (get free from console.groq.com)

# Run server
uvicorn main:app --reload
```

Server runs at: **http://localhost:8000**

Swagger docs: **http://localhost:8000/docs**

---

## 📚 Documentation

- **[Frontend Integration Guide](FRONTEND_INTEGRATION_GUIDE.md)** — Complete API reference with examples
- **[Render Deployment Guide](RENDER_DEPLOYMENT.md)** — Deploy to production in 10 minutes
- **[Quick Start Reference](RENDER_QUICK_START.txt)** — Environment variables cheat sheet

---

## 🌐 Deploy to Production

### Render (Recommended — FREE)

1. Go to [dashboard.render.com](https://dashboard.render.com/)
2. Create new Web Service
3. Connect this GitHub repository
4. **Runtime:** Python 3 (auto-detected from `runtime.txt`)
5. **Build Command:** `pip install -r requirements-production.txt`
6. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Add environment variables from `.env.production`
8. Deploy!

**Cost: $0/month** (Render Free + Groq FREE + Neon FREE)

> **Note:** Production uses `requirements-production.txt` which excludes local-only features (Ollama, Whisper, ChromaDB, face recognition, etc.). All API-based features work perfectly.

See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) for detailed instructions.

---

## 🧪 Test the API

```bash
# Health check
curl http://localhost:8000/health

# Chat with Athena
curl -X POST http://localhost:8000/api/chat/text \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello Athena", "history": [], "tts": false}'

# Teach Athena something
curl -X POST http://localhost:8000/api/learning/teach \
  -H "Content-Type: application/json" \
  -d '{"category": "preference", "key": "coffee", "value": "black, no sugar", "source": "user"}'

# Query knowledge
curl -X POST http://localhost:8000/api/learning/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is my coffee preference?"}'
```

---

## 🏗️ Architecture

```
athena-backend/
├── app/
│   ├── routes/          # API endpoints (70+ endpoints)
│   ├── services/        # Business logic (automation, focus, learning, etc.)
│   ├── skills/          # AI skills (weather, calendar, smart home, etc.)
│   ├── llm_*.py         # LLM integrations (Claude, Groq, NVIDIA, Ollama)
│   ├── db.py            # Database models (24 tables)
│   └── config.py        # Configuration
├── main.py                      # FastAPI app entry point
├── requirements.txt             # Python dependencies (local dev)
├── requirements-production.txt  # Python dependencies (production)
└── .env.example                 # Environment variables template
```

---

## 🔧 Configuration

### Required Environment Variables

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
```

### Optional (Recommended)

```bash
NVIDIA_API_KEY=nvapi_...          # Backup LLM (FREE)
ANTHROPIC_API_KEY=sk-ant-...     # Best quality ($1-3/month)
OPENWEATHER_API_KEY=...           # Weather
EXPO_PUSH_TOKEN=ExponentPush...   # Mobile notifications
```

See `.env.example` for full configuration options.

---

## 📊 Database Schema

24 tables including:
- **Users & Auth** — Authentication, preferences, settings
- **AI Core** — Conversations, messages, tool calls
- **Features** — Notes, reminders, tasks, calendar, emails
- **JARVIS** — Automation rules, contacts, focus sessions, quick actions, knowledge
- **Analytics** — Context tracking, patterns, routines

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file

---

## 🙋 Support

- **Issues**: [GitHub Issues](https://github.com/QORETEX/Athena-backend/issues)
- **Docs**: See documentation files in repo
- **Email**: support@qoretex.com

---

## 🌟 About Qoretex

Athena was created by **Qoretex**, a technology company focused on intelligent AI systems that are proactive, personal, and deeply integrated into your life.

Visit: [qoretex.com](https://qoretex.com)

---

**Built with ❤️ by Qoretex**
