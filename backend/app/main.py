"""FastAPI app exposing the AuctionRouter pipeline."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import json  # noqa: E402

from fastapi.responses import StreamingResponse  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from .config import TIER1_MODELS, TIER2_MODEL, VERIFIER_MODEL, settings  # noqa: E402
from .llm import close_client  # noqa: E402
from .pipeline import run_query, run_query_stream  # noqa: E402
from .schemas import MetricsSummary, QueryRequest, RunResult  # noqa: E402
from .security import RATE_LIMITS, limiter, require_access, spend_guard  # noqa: E402
from .store import get_store  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(title="AuctionRouter", version="0.1.0", lifespan=lifespan)

# Per-IP rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Browser-origin allowlist. NOT a security boundary (curl ignores CORS) —
# the access code + rate limits + spend guard are. Just lets the deployed
# frontend call the API from its own origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    # Open (no access code): HF Spaces healthcheck. Returns no secrets.
    return {
        "status": "ok",
        "openrouter_key_set": bool(settings.openrouter_api_key),
        "access_required": bool(settings.access_code),
        "store": "mongodb" if settings.mongodb_uri else "memory",
        "tier1_models": [m.openrouter_id for m in TIER1_MODELS.values()],
        "verifier": VERIFIER_MODEL.openrouter_id,
        "tier2_model": TIER2_MODEL.openrouter_id,
    }


@app.post("/api/query", response_model=RunResult,
          dependencies=[Depends(require_access)])
@limiter.limit(RATE_LIMITS)
async def query(request: Request, req: QueryRequest):
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not set")
    spend_guard.check()
    return await run_query(req.query, [t.model_dump() for t in req.history],
                           req.hint)


@app.post("/api/query/stream", dependencies=[Depends(require_access)])
@limiter.limit(RATE_LIMITS)
async def query_stream(request: Request, req: QueryRequest):
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not set")
    spend_guard.check()

    history = [t.model_dump() for t in req.history]

    async def gen():
        try:
            async for event in run_query_stream(req.query, history, req.hint):
                yield json.dumps(event) + "\n"
        except Exception as e:  # surface pipeline crashes to the client
            yield json.dumps({"type": "error", "message": str(e)[:300]}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/runs", response_model=list[RunResult],
         dependencies=[Depends(require_access)])
async def runs(limit: int = 50):
    return await get_store().list_runs(min(limit, 200))


@app.get("/api/metrics", response_model=MetricsSummary,
         dependencies=[Depends(require_access)])
async def metrics():
    return await get_store().metrics()


# In the Hugging Face Space image the Next.js static export is copied to
# ./static and served from the same origin as the API.
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
