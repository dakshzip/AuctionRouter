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

## Eval results

38 bucketed queries (easy factual, subjective, typos, ambiguous, coding,
medium reasoning, PhD-level STEM) run through the full pipeline vs. sending
every query straight to the frontier model. Answers scored 0–1 by an
independent LLM judge (GPT-OSS-120B) against reference notes. Frontier
stand-in for the eval: DeepSeek R1 (production uses GPT-5); identical
queries, models, and judge across both modes.

| mode | judge score | tier-1 rate | p50 latency | total cost |
|---|---|---|---|---|
| **AuctionRouter** | **0.95** | 89% | **3.6 s** | **$0.067** |
| frontier-only | 1.00 | 0% | 52.8 s | $0.212 |

**68% cheaper and ~15× faster at the median**, giving up 0.05 judge points —
half of which is a single eval-artifact failure (R1's reasoning exhausted the
token budget on one physics derivation), not a routing miss. At production
GPT-5 output pricing (~4.7× R1's), the frontier-only baseline scales to
roughly $1 for the same set while the auction's tier-1 majority is
frontier-price-independent, projecting to ~85–90% savings.

Per-bucket (AuctionRouter mode):

| bucket | n | judge | tier-1 | p50 | cost |
|---|---|---|---|---|---|
| easy_factual | 8 | 1.00 | 100% | 1.7 s | $0.002 |
| subjective | 5 | 1.00 | 100% | 2.6 s | $0.002 |
| typo | 4 | 1.00 | 100% | 3.3 s | $0.002 |
| ambiguous | 5 | 0.82 | 100% | 2.8 s | $0.003 |
| coding | 5 | 1.00 | 100% | 6.8 s | $0.005 |
| reasoning | 5 | 1.00 | 100% | 9.9 s | $0.005 |
| stem_hard | 6 | 0.83 | 33% | 112.6 s | $0.048 |

Notably, 2 of 6 hard-STEM items were answered *correctly at tier 1* (judge
1.0, verifier-passed) — the cheap models legitimately solved them, so the
"low" tier-1 routing accuracy there is savings, not error.

Reproduce:

```bash
cd backend
FRONTIER_MODEL_ID=deepseek/deepseek-r1 uv run python -m evals.run_evals
FRONTIER_MODEL_ID=deepseek/deepseek-r1 uv run python -m evals.run_evals --mode frontier
```

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
