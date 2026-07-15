---
title: AuctionRouter
emoji: 🎯
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Cost-aware multi-agent LLM router with auction + verification
---

# AuctionRouter

Cost-aware multi-agent LLM orchestrator: cheap models bid on each query, an
auction picks a winner to draft the answer, a verifier scores it, and only
failures escalate to a frontier model (GPT-5 / Claude Sonnet) via OpenRouter.

## Hosting (Hugging Face Spaces)

This repo is a single Docker Space: the multi-stage `Dockerfile` builds the
Next.js frontend as a static export and FastAPI serves it alongside the API on
port 7860.

### Deploy

1. Create a **Docker** Space and push this repo to it:
   ```bash
   git remote add hf https://huggingface.co/spaces/<your-username>/AuctionRouter
   git push hf master:main
   ```
2. In **Settings → Variables and secrets**, add:
   - `OPENROUTER_API_KEY` (secret, required)
   - `MONGODB_URI` (secret, optional — MongoDB Atlas M0; without it the app
     uses an in-memory store that resets on restart)
   - `MONGODB_DB` (variable, optional, default `auctionrouter`)
   - `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` (optional, LangSmith)
3. If using Atlas, allow `0.0.0.0/0` in its Network Access list — Space IPs
   are not static.

Notes:
- Spaces restart on every push and wipe local disk; persistent history needs
  the Mongo URI.
- CPU Basic hardware is sufficient (all inference happens on OpenRouter).
  Pro-tier upgraded hardware avoids the ~48h inactivity sleep.

## Local development

```bash
# backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```
