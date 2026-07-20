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

## Deployment (Vercel frontend + Hugging Face backend)

The frontend is a pure client-side SPA and the backend is a pure API, so they
deploy independently: **Vercel** serves the UI, a **Hugging Face Docker Space**
runs FastAPI. (The `Dockerfile` also bundles the UI, so the Space works
standalone as a fallback.)

### Security model

The API key is a server-side secret never sent to the browser — the threat is
*abuse of the endpoints that spend it*. Defense in depth, worst case bounded
by a number:

1. **Credit-capped OpenRouter key** — create a dedicated key with a hard
   credit limit (e.g. $20). Provider-enforced backstop; survives any app bug.
2. **Daily spend guard** — `DAILY_SPEND_LIMIT_USD`; query endpoints return 503
   once the day's total is exceeded (in-memory, resets on restart).
3. **Access code** — every `/api/*` route requires the `X-Access-Code` header
   (`ACCESS_CODE`); share the code with viewers. `/health` stays open.
4. **Per-IP rate limiting** — `RATE_LIMIT_PER_MIN` / `_PER_DAY` on the query
   endpoints (real IP read from `X-Forwarded-For`).
5. **CORS** — `ALLOWED_ORIGINS` allowlist (browsers only; not a security
   boundary — layers 1–4 are).

Locking the access code also closes the run-history / metrics endpoints, which
otherwise expose every visitor's queries and total spend.

### Backend → Hugging Face Docker Space

1. Create the credit-capped OpenRouter key.
2. Push this repo to a **Docker** Space:
   ```bash
   git remote add hf https://huggingface.co/spaces/<user>/AuctionRouter
   git push hf main:main
   ```
3. **Settings → Variables and secrets:**
   - `OPENROUTER_API_KEY` (secret, the credit-capped key)
   - `ACCESS_CODE` (secret, the shared demo code)
   - `ALLOWED_ORIGINS` (variable, your Vercel URL, comma-separated with any others)
   - `DAILY_SPEND_LIMIT_USD` (variable, e.g. `20`)
   - `MONGODB_URI` / `MONGODB_DB` (secret/variable, optional — Atlas M0; without
     it an in-memory store is used that resets on restart)
   - `FRONTIER_MODEL_ID` (variable, optional, default `openai/gpt-5`)
4. If using Atlas, allow `0.0.0.0/0` in its Network Access list (Space IPs
   aren't static).
5. Confirm `<space-url>/health` returns `openrouter_key_set: true`.

### Frontend → Vercel

1. Import `frontend/` as a Vercel project (auto-detected Next.js).
2. Set env `NEXT_PUBLIC_API_BASE` = the HF Space URL. (Do **not** put the
   access code here — it's entered at runtime.)
3. Deploy, then add the Vercel domain to the Space's `ALLOWED_ORIGINS` and
   redeploy the Space.
4. Open the Vercel URL → enter the access code → run a query.

Notes:
- HF free tier sleeps after ~48h idle → first query cold-starts ~30s. HF Pro
  or an always-on backend (Fly.io / Render, same Dockerfile) removes this.
- CPU Basic is sufficient — all inference happens on OpenRouter.

## Local development

```bash
# backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```
