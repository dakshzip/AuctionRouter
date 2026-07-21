---
title: GAVL
emoji: 🔨
colorFrom: indigo
colorTo: orange
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Cost-aware multi-agent LLM router with a live auction
---

<div align="center">

# 🔨 GAVL

### Ask more · Know faster · Pay less

**A cost-aware, multi-agent LLM router.** Cheap models bid on every question,
an auction picks a winner, a verifier checks the answer, and only the
genuinely hard queries ever reach an expensive frontier model.

Frontier-quality answers — without paying frontier prices on the easy 90%.

![Docker](https://img.shields.io/badge/deploy-docker-2496ED?logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/frontend-Next.js-000000?logo=nextdotjs&logoColor=white)
![OpenRouter](https://img.shields.io/badge/models-OpenRouter-6467F2)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

---

## The idea

Most chat apps send **every** question to one big, expensive model — even
"what's the capital of France." That's slow and wasteful: the easy majority of
queries don't need a frontier model at all.

GAVL treats routing as an **auction**. Three cheap, fast specialist models bid
to answer each query based on how well they think they'd do. The best bid wins
and drafts the answer, an independent verifier grades it, and *only* when a
genuinely hard query fails does GAVL summon the expensive frontier model — the
"boss fight." Easy questions never escalate.

The payoff (see [evals](#-eval-results)): **~0.95 answer quality at ~68% lower
cost and ~15× faster median latency** than sending everything to the frontier.

## 🧠 How it works

```mermaid
flowchart LR
    Q([Your query]) --> B{Parallel bids}
    B --> G[Generalist]
    B --> C[Coder]
    B --> M[Logic / Math]
    G & C & M --> A[Auction<br/>score bids]
    A -->|winner drafts| V{Verifier}
    V -->|passes| ✅([Answer])
    V -->|hard + fails| BOSS[🔨 Frontier<br/>boss fight]
    BOSS --> ✅
    A -.needs fresh info.-> W[🔍 Web search]
    W --> V
```

1. **Bidding** — all three tier-1 models bid in parallel. Each returns a
   *confidence*, a *difficulty* estimate, and a flag for whether the query
   needs **live web data**. A confident bidder also drafts its answer on the
   spot, so if it wins there's no extra round-trip.
2. **Auction** — bids are scored on
   `0.7·confidence + 0.2·historical-accuracy − 0.1·cost`. A **topic toggle**
   (general / coding / logic-math) lets you steer routing. The accuracy term is
   *learned* — a model that overbids and fails is trusted less next time.
3. **Verification** — an independent verifier grades the winning draft on
   correctness, completeness, and commitment. Creative writing skips this
   (no single right answer to check).
4. **Escalation** — only a **hard** query that fails verification escalates to
   the frontier model, with reasoning effort and token budget scaled to the
   difficulty. Easy queries never escalate; a weak answer just ships, clearly
   marked *unverified*.
5. **Web search** — if a bidder flags the query as needing current information
   (news, latest releases, "who won X", a specific recent item), the winner
   runs a live web search and **cites its sources**.

## ✨ Features

- **Auction-based routing** with a learned per-model accuracy prior.
- **Speculative drafting** — confident bidders answer inside their bid, so the
  winning answer often needs zero extra calls.
- **Streaming-first UI** — you see text in ~3s; the verifier judges in parallel.
- **Difficulty-gated escalation** — the frontier model is reserved for the
  small fraction of queries that truly need it.
- **Live web search** with citations, gated on a per-query freshness flag.
- **Topic toggles** to hint the router (general / coding / logic-math).
- **Retro arcade UI** — a live "bidding bots" animation, a boss-fight ticker
  for escalations, per-code-block copy, and a `/explain` command that walks
  through the whole pipeline in-app.
- **Cost & routing telemetry** — every answer shows who won, what it cost, and
  the verifier's score; a metrics dashboard tracks savings over time.

## 📊 Eval results

38 bucketed queries (easy factual, subjective, typos, ambiguous, coding,
medium reasoning, PhD-level STEM) run through the full pipeline vs. sending
every query straight to the frontier model. Answers scored 0–1 by an
independent LLM judge against reference notes. Frontier stand-in for the eval:
DeepSeek R1; identical queries, models, and judge across both modes.

| mode | judge score | tier-1 rate | p50 latency | total cost |
|---|---|---|---|---|
| **GAVL** | **0.95** | 89% | **3.6 s** | **$0.067** |
| frontier-only | 1.00 | 0% | 52.8 s | $0.212 |

**68% cheaper and ~15× faster at the median**, giving up 0.05 judge points —
half of which is a single eval-artifact failure (the frontier stand-in
exhausted its token budget on one physics derivation), not a routing miss. At
production frontier pricing the gap widens sharply, projecting to ~85–90%
savings.

<details>
<summary>Per-bucket breakdown</summary>

| bucket | n | judge | tier-1 | p50 | cost |
|---|---|---|---|---|---|
| easy_factual | 8 | 1.00 | 100% | 1.7 s | $0.002 |
| subjective | 5 | 1.00 | 100% | 2.6 s | $0.002 |
| typo | 4 | 1.00 | 100% | 3.3 s | $0.002 |
| ambiguous | 5 | 0.82 | 100% | 2.8 s | $0.003 |
| coding | 5 | 1.00 | 100% | 6.8 s | $0.005 |
| reasoning | 5 | 1.00 | 100% | 9.9 s | $0.005 |
| stem_hard | 6 | 0.83 | 33% | 112.6 s | $0.048 |

Notably, 2 of 6 hard-STEM items were answered *correctly at tier 1*
(judge 1.0, verifier-passed) — the cheap models legitimately solved them, so
the "low" routing accuracy there is savings, not error.
</details>

Reproduce:

```bash
cd backend
FRONTIER_MODEL_ID=deepseek/deepseek-r1 uv run python -m evals.run_evals
FRONTIER_MODEL_ID=deepseek/deepseek-r1 uv run python -m evals.run_evals --mode frontier
```

## 🧩 Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · LangGraph pipeline · async `httpx` |
| Models | Routed through **OpenRouter** (swappable per slot via config) |
| Frontend | Next.js (static export) · Tailwind · streaming NDJSON |
| Store | MongoDB (optional) or in-memory |
| Deploy | Single Docker image (Hugging Face Space) or split Vercel + HF |

All model choices, auction weights, and thresholds live in
`backend/app/config.py` — swap any bidder, the verifier, or the frontier model
without touching pipeline code.

## 🚀 Deployment

The frontend is a pure client-side SPA and the backend is a pure API, so they
can deploy independently: **Vercel** serves the UI, a **Hugging Face Docker
Space** runs FastAPI. (The `Dockerfile` also bundles the UI, so the Space works
standalone.)

### 🔐 Security model

The API key is a server-side secret never sent to the browser — the real threat
is *abuse of the endpoints that spend it*. Defense in depth, worst case bounded
by a number:

1. **Credit-capped OpenRouter key** — a dedicated key with a hard credit limit.
   Provider-enforced; survives any app bug.
2. **Daily spend guard** — `DAILY_SPEND_LIMIT_USD`; query endpoints 503 once
   the day's total is exceeded.
3. **Access code** — every `/api/*` route requires the `X-Access-Code` header
   (`ACCESS_CODE`); `/health` stays open. Locking it also closes the
   run-history and metrics endpoints.
4. **Per-IP rate limiting** — `RATE_LIMIT_PER_MIN` / `_PER_DAY`.
5. **CORS** — `ALLOWED_ORIGINS` allowlist (browsers only; layers 1–4 are the
   real boundary).

### Backend → Hugging Face Docker Space

1. Create the credit-capped OpenRouter key.
2. Push this repo to a **Docker** Space:
   ```bash
   git remote add hf https://huggingface.co/spaces/<user>/GAVL
   git push hf main:main
   ```
3. **Settings → Variables and secrets:**
   - `OPENROUTER_API_KEY` *(secret)* — the credit-capped key
   - `ACCESS_CODE` *(secret)* — the shared demo code
   - `ALLOWED_ORIGINS` *(variable)* — your Vercel URL (comma-separated)
   - `DAILY_SPEND_LIMIT_USD` *(variable)* — e.g. `20`
   - `MONGODB_URI` / `MONGODB_DB` *(optional)* — Atlas M0; else in-memory
   - `FRONTIER_MODEL_ID` *(optional)*
4. If using Atlas, allow `0.0.0.0/0` in its Network Access list.
5. Confirm `<space-url>/health` returns `openrouter_key_set: true`.

### Frontend → Vercel

1. Import `frontend/` as a Vercel project (auto-detected Next.js).
2. Set `NEXT_PUBLIC_API_BASE` = the HF Space URL. (The access code is entered
   at runtime, never baked into the bundle.)
3. Deploy, add the Vercel domain to the Space's `ALLOWED_ORIGINS`, redeploy.

> HF free tier sleeps after ~48h idle → first query cold-starts ~30s. HF Pro or
> an always-on backend (Fly.io / Render, same Dockerfile) removes this. CPU
> Basic is sufficient — all inference happens on OpenRouter.

## 💻 Local development

```bash
# backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```

Then open <http://localhost:3000>. With no `ACCESS_CODE` set the gate is
skipped automatically; set one in `backend/.env` to preview the splash screen.

---

<div align="center">
<sub>Built with FastAPI, LangGraph, Next.js, and OpenRouter · MIT licensed</sub>
</div>
