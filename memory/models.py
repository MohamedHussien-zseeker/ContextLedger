import uuid
from datetime import datetime, timezone
from typing import Any, Optional

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
    tags: list[str] = Field(default_factory=list)
    vault_path: Optional[str] = None
    content_hash: Optional[str] = None
    status: str = "approved"
    source_type: str = "manual"
    source_uri: Optional[str] = None
    captured_at: Optional[str] = None
    confidentiality: str = "confidential"


class MemoryUpdate(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    importance: Optional[int] = Field(None, ge=1, le=5)
    tags: Optional[list[str]] = None
    vault_path: Optional[str] = None
    status: str = "approved"
    content_hash: Optional[str] = None
    source_type: str = "manual"
    source_uri: Optional[str] = None
    captured_at: Optional[str] = None
    confidentiality: str = "confidential"


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
    deleted_at: Optional[str] = None
    status: Optional[str] = None
    content_hash: Optional[str] = None
    source_type: Optional[str] = None
    source_uri: Optional[str] = None
    captured_at: Optional[str] = None
    confidentiality: Optional[str] = None


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


class HistoryEntryResponse(BaseModel):
    id: str
    memory_id: str
    version: int
    change_id: str
    actor_type: str
    initiated_by: Optional[str] = None
    executed_by: str
    change_type: str
    reason: Optional[str] = None
    snapshot: dict
    rolled_back_from_history_id: Optional[str] = None
    created_at: str


class FieldDiffResponse(BaseModel):
    field: str
    old_value: Any
    new_value: Any


class HistoryListResponse(BaseModel):
    entries: list[HistoryEntryResponse]
    total: int
    limit: int
    offset: int


class RollbackRequest(BaseModel):
    target_version: int
    expected_version: int
    actor_type: str
    executed_by: str
    initiated_by: Optional[str] = None
    reason: Optional[str] = None
    change_id: Optional[str] = None


class MutationResponse(BaseModel):
    changed: bool
    entry: HistoryEntryResponse
    git_commit_sha: Optional[str] = None
    git_warning: Optional[str] = None
