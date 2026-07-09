"""FastAPI REST server for ContextLedger."""
import json
import logging
import logging.handlers
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from memory import config
from memory.vault import default_vault_path
from memory.database import init_db
from memory.crud import create, get, update, archive, get_stats
from memory.search import search, related
from memory.models import MemoryCreate, MemoryUpdate, MemoryResponse, StatsResponse
from memory.entity import extract_entities
from memory.providers import get as get_provider, list_providers
from memory.processor import process_source, process_all
from memory.indexer import index_vault

VAULT_PATH = Path(os.environ.get("MEMORY_VAULT", default_vault_path()))
_request_count = 0
_error_count = 0
_request_durations: list[int] = []
MAX_DURATIONS = 100
_log_initialized = False


def get_logger():
    global _log_initialized
    logger = logging.getLogger("memory-api")
    if _log_initialized:
        return logger
    _log_initialized = True
    logger.setLevel(logging.INFO)
    log_dir = Path("/var/log")

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": "memory-api",
                "level": record.levelname,
                "message": record.getMessage(),
                "request_id": getattr(record, "request_id", ""),
                "duration_ms": getattr(record, "duration_ms", 0),
            })

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "memory-api.jsonl", maxBytes=100*1024*1024, backupCount=3
        )
    except PermissionError:
        handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger


_log = get_logger()


def verify_token(authorization: str = Header(None)) -> str:
    token_path = config.TOKEN_PATH
    if not token_path.exists():
        return "no-token-configured"
    expected = token_path.read_text().strip()
    if authorization is None:
        raise HTTPException(401, "Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != expected:
        raise HTTPException(401, "Invalid token")
    return token


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(VAULT_PATH)
    _log.info("memory_api_start")
    yield
    _log.info("memory_api_stop")


app = FastAPI(title="ContextLedger API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    global _request_count, _error_count, _request_durations
    request_id = uuid.uuid4().hex[:12]
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    _request_count += 1
    if response.status_code >= 400:
        _error_count += 1
    _request_durations.append(duration_ms)
    if len(_request_durations) > MAX_DURATIONS:
        _request_durations = _request_durations[-MAX_DURATIONS:]
    extra = {"request_id": request_id, "duration_ms": duration_ms}
    _log.info(f"{request.method} {request.url.path} {response.status_code}", extra=extra)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/v1/health")
def health():
    s = get_stats(VAULT_PATH)
    return {"status": "ok", "memory_count": s["total_memories"], "db_size_bytes": s["db_size_bytes"]}


@app.post("/v1/remember", response_model=MemoryResponse)
def remember(m: MemoryCreate, _=Depends(verify_token)):
    return create(VAULT_PATH, m)


@app.get("/v1/memories/{mid}", response_model=MemoryResponse)
def get_memory(mid: str, _=Depends(verify_token)):
    mem = get(VAULT_PATH, mid)
    if not mem:
        raise HTTPException(404, "Memory not found")
    return mem


@app.put("/v1/memories/{mid}", response_model=MemoryResponse)
def update_memory(mid: str, m: MemoryUpdate, _=Depends(verify_token)):
    mem = update(VAULT_PATH, mid, m)
    if not mem:
        raise HTTPException(404, "Memory not found")
    return mem


@app.delete("/v1/memories/{mid}")
def delete_memory(mid: str, _=Depends(verify_token)):
    if not archive(VAULT_PATH, mid):
        raise HTTPException(404, "Memory not found")
    return {"status": "archived", "id": mid}


class SearchQuery(BaseModel):
    q: str = ""
    tags: list[str] = []
    type: str = ""
    source: str = ""
    limit: int = 10
    offset: int = 0


@app.post("/v1/search")
def search_endpoint(body: SearchQuery, _=Depends(verify_token)):
    memories, total = search(
        VAULT_PATH, q=body.q, tags=body.tags or None,
        type_filter=body.type or None, source=body.source or None,
        limit=body.limit, offset=body.offset,
    )
    return {"memories": [m.model_dump() for m in memories], "total": total}


@app.get("/v1/related/{mid}")
def get_related(mid: str, limit: int = 5, _=Depends(verify_token)):
    return {"memories": [m.model_dump() for m in related(VAULT_PATH, mid, limit)]}


@app.get("/v1/stats", response_model=StatsResponse)
def stats(_=Depends(verify_token)):
    s = get_stats(VAULT_PATH)
    return StatsResponse(**s)


@app.get("/v1/entities/{mid}")
def get_entities(mid: str, _=Depends(verify_token)):
    mem = get(VAULT_PATH, mid)
    if not mem:
        raise HTTPException(404, "Memory not found")
    entities = extract_entities(mem.title + "\n" + mem.content)
    entities["memory_id"] = mid
    return entities


class CaptureRequest(BaseModel):
    scheme: str
    target: str
    process: bool = False


class CaptureResponse(BaseModel):
    source: str
    title: str
    processed: bool = False
    process_result: dict | None = None


@app.post("/v1/capture", response_model=CaptureResponse)
def capture(body: CaptureRequest, _=Depends(verify_token)):
    provider = get_provider(body.scheme)
    if not provider:
        available = ", ".join(list_providers())
        raise HTTPException(400, f"Unknown provider '{body.scheme}'. Available: {available}")

    raw_dir = VAULT_PATH / config.RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_source = provider.capture(body.target)
    source_slug = raw_source.title.lower().replace(" ", "-")
    source_path = raw_dir / f"{source_slug}.md"
    fm = {
        "captured": raw_source.captured_at,
        "source_type": raw_source.source_type,
        "source_uri": raw_source.source_uri,
        "title": raw_source.title,
        "status": "captured",
    }
    with open(source_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        for k, v in fm.items():
            f.write(f"{k}: {v}\n")
        f.write("---\n\n")
        f.write(raw_source.content)

    result = None
    if body.process:
        result = process_source(VAULT_PATH, source_path)

    return CaptureResponse(
        source=str(source_path.relative_to(VAULT_PATH)),
        title=raw_source.title,
        processed=body.process,
        process_result=result,
    )


class ProcessRequest(BaseModel):
    force: bool = False
    dry_run: bool = False
    limit: int = 0


class IndexRequest(BaseModel):
    apply: bool = False
    dry_run: bool = False


@app.post("/v1/process")
def process(body: ProcessRequest, _=Depends(verify_token)):
    results = process_all(VAULT_PATH, force=body.force, dry_run=body.dry_run, limit=body.limit)
    return {"results": results, "count": len(results)}


@app.post("/v1/index")
def index(body: IndexRequest, _=Depends(verify_token)):
    stats = index_vault(VAULT_PATH, apply=body.apply)
    return stats
