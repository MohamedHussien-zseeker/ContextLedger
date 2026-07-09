from datetime import datetime, timezone
from typing import Optional
import uuid

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


class MemoryCreate(BaseModel):
    type: str = "note"
    title: str
    content: str = ""
    source: str = "manual"
    importance: int = Field(default=1, ge=1, le=5)
    tags: list[str] = []
    vault_path: Optional[str] = None


class MemoryUpdate(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    importance: Optional[int] = Field(None, ge=1, le=5)
    tags: Optional[list[str]] = None
    vault_path: Optional[str] = None


class MemoryResponse(BaseModel):
    id: str
    type: str
    title: str
    content: str
    source: str
    importance: int
    tags: list[str]
    created_at: str
    updated_at: str
    accessed_at: Optional[str] = None
    access_count: int
    archived: bool
    vault_path: Optional[str] = None
    score: Optional[float] = None


class SearchResult(BaseModel):
    memories: list[MemoryResponse]
    total: int


class StatsResponse(BaseModel):
    total_memories: int
    by_type: dict[str, int]
    by_source: dict[str, int]
    total_relationships: int
    db_size_bytes: int
    health: str
