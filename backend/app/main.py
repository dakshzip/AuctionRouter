"""FastAPI app exposing the AuctionRouter pipeline."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .config import TIER1_MODELS, TIER2_MODEL, VERIFIER_MODEL, settings  # noqa: E402
from .llm import close_client  # noqa: E402
from .pipeline import run_query  # noqa: E402
from .schemas import MetricsSummary, QueryRequest, RunResult  # noqa: E402
from .store import get_store  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(title="AuctionRouter", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "openrouter_key_set": bool(settings.openrouter_api_key),
        "store": "mongodb" if settings.mongodb_uri else "memory",
        "tier1_models": [m.openrouter_id for m in TIER1_MODELS.values()],
        "verifier": VERIFIER_MODEL.openrouter_id,
        "tier2_model": TIER2_MODEL.openrouter_id,
    }


@app.post("/api/query", response_model=RunResult)
async def query(req: QueryRequest):
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not set")
    return await run_query(req.query)


@app.get("/api/runs", response_model=list[RunResult])
async def runs(limit: int = 50):
    return await get_store().list_runs(min(limit, 200))


@app.get("/api/metrics", response_model=MetricsSummary)
async def metrics():
    return await get_store().metrics()


# In the Hugging Face Space image the Next.js static export is copied to
# ./static and served from the same origin as the API.
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
