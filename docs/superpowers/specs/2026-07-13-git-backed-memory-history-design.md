# Git-Backed Memory History (ContextLedger v0.2)

**Date:** 2026-07-13
**Status:** Approved
**Author:** Helium Brain Team

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    CLI / MCP / REST                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              History Service (shared)                │
│  - create_memory()                                  │
│  - update_memory()                                  │
│  - change_status()                                  │
│  - delete_memory()                                  │
│  - rollback()                                       │
│  - get_log()                                        │
│  - diff_versions()                                  │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐   ┌──────────┐   ┌─────────┐
   │memories │   │ history  │   │  Git    │
   │  table  │   │  table   │   │ commit  │
   └─────────┘   └──────────┘   └─────────┘
        │              │              │
        └──────────────┴──────────────┘
                       │
              change_id correlates
```

**Key principles:**
- History is append-only (immutable during normal operation)
- Every meaningful change creates exactly one history row
- Rollback creates a new row (preserves full history)
- Git commits are supplementary, not authoritative
- History Service owns complete mutation transaction
- Database-only changes do not require Git commits
- Git-only operational file changes do not create memory history

**Authority boundaries:**
- SQLite history is the authoritative audit trail for every meaningful memory change
- Git records resulting vault-file changes for review, blame, recovery, and synchronization
- If Git fails, retain valid database change and report recoverable synchronization error
- Explicit future pruning command is the only permitted deletion path

## 2. History Record Schema

```sql
CREATE TABLE memory_history (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,  -- no FK to memories (avoids cascade on delete)
  version INTEGER NOT NULL,
  change_id TEXT NOT NULL,
  
  -- Actor model
  actor_type TEXT NOT NULL CHECK(actor_type IN ('human', 'agent', 'system')),
  initiated_by TEXT,
  executed_by TEXT NOT NULL CHECK(trim(executed_by) <> ''),
  
  -- Change metadata
  change_type TEXT NOT NULL CHECK(change_type IN (
    'create', 'update', 'status_change', 'rollback', 'delete'
  )),
  reason TEXT,
  
  -- Post-change snapshot
  snapshot JSON NOT NULL CHECK(json_valid(snapshot)),
  
  -- Rollback tracking
  rolled_back_from_history_id TEXT,
  FOREIGN KEY (rolled_back_from_history_id) REFERENCES memory_history(id),
  
  -- Timestamps
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  
  -- Constraints
  UNIQUE(memory_id, version),
  UNIQUE(change_id, memory_id),
  
  -- Actor validation
  CHECK (
    (actor_type = 'human' AND initiated_by IS NOT NULL AND trim(initiated_by) <> '')
    OR (actor_type = 'agent')
    OR (actor_type = 'system' AND initiated_by IS NULL)
  )
);

CREATE INDEX idx_history_created_at ON memory_history(created_at);
CREATE INDEX idx_history_executed_by ON memory_history(executed_by);
```

**Snapshot format:**
```json
{
  "schema_version": 1,
  "title": "TasteSkill",
  "content": "# TasteSkill\n\nQuality rules...",
  "status": "approved",
  "tags": ["quality", "ai-prevention"],
  "importance": 4,
  "vault_path": "approved/tasteskill.md",
  "deleted": false
}
```

**Actor validation rules:**
- `actor_type = 'human'` → `initiated_by` required
- `actor_type = 'agent'` → `executed_by` = agent name, `initiated_by` optional (human who triggered)
- `actor_type = 'system'` → `executed_by` = process name, `initiated_by` null

**Status transition rules:**
```
draft → approved | rejected
approved → superseded | rejected
rejected → draft  (rework)
superseded → (terminal)
```

## 3. History Service Layer

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class HistoryEntry:
    id: str
    memory_id: str
    version: int
    change_id: str
    actor_type: str
    initiated_by: str | None
    executed_by: str
    change_type: str
    reason: str | None
    snapshot: dict
    rolled_back_from_history_id: str | None
    created_at: str

@dataclass(frozen=True)
class FieldDiff:
    field: str
    old_value: Any
    new_value: Any

@dataclass(frozen=True)
class MutationResult:
    entry: HistoryEntry
    changed: bool

class HistoryService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
    
    def create_memory(
        self,
        memory_id: str,
        snapshot: dict,
        actor_type: str,
        executed_by: str,
        initiated_by: str = None,
        change_id: str = None,
        reason: str = None
    ) -> MutationResult:
        """Reject if active memory_id exists. Create + initial history."""
        
    def update_memory(
        self,
        memory_id: str,
        snapshot: dict,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str = None,
        change_id: str = None,
        reason: str = None
    ) -> MutationResult:
        """Update fields. Returns MutationResult with changed=False if no-op."""
        
    def change_status(
        self,
        memory_id: str,
        new_status: str,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str = None,
        change_id: str = None,
        reason: str = None
    ) -> MutationResult:
        """Validate transition rules, then update."""
        
    def delete_memory(
        self,
        memory_id: str,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str = None,
        change_id: str = None,
        reason: str = None
    ) -> MutationResult:
        """Soft-delete: set deleted_at, append tombstone snapshot."""
        
    def rollback(
        self,
        memory_id: str,
        target_version: int,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str = None,
        change_id: str = None,
        reason: str = None
    ) -> MutationResult:
        """Restore from target. Non-deleted → restore. Tombstone → soft-delete."""
        
    def get_log(
        self,
        memory_id: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[HistoryEntry]:
        """Query history."""
        
    def diff_versions(
        self,
        memory_id: str,
        version_a: int,
        version_b: int
    ) -> list[FieldDiff]:
        """Compare two snapshots."""
        
    def _execute_atomic(
        self,
        memory_id: str,
        change_id: str,
        change_type: str,
        snapshot: dict,
        actor_type: str,
        executed_by: str,
        expected_version: int = None,
        initiated_by: str = None,
        reason: str = None,
        rolled_back_from_history_id: str = None
    ) -> MutationResult:
        """Internal: BEGIN IMMEDIATE, idempotency check, version allocation,
           field comparison, memory update, history insert, COMMIT.
           Rolls back on any exception."""
```

**Concurrency model:**
- `BEGIN IMMEDIATE` starts write transaction
- Allocate `version = MAX(version) + 1` within transaction
- Check `(change_id, memory_id)` exists → return existing HistoryEntry (idempotent)
- Compare fields → skip if no meaningful change
- Update memories + insert memory_history
- COMMIT

**Rollback rules:**
- Reject if `target_version` not found
- Load target snapshot (immutable historical record)
- Apply as new current state (with current timestamp)
- Set `rolled_back_from_history_id = target_history.id`
- Append new version
- Rollback to non-deleted restores memory; rollback to tombstone soft-deletes

**Mutation result:**
- `MutationResult(entry, changed=True)` for meaningful new mutations
- `MutationResult(entry, changed=False)` for idempotent retries or no-ops
- Updates, status changes, and deletes reject already-deleted memories
- Only rollback can restore deleted memories

## 4. CLI Commands

```bash
# List history for a memory
cl-context history list <memory_id> [--limit N] [--offset N] [--json]

# Compare two versions
cl-context history diff <memory_id> <version_a> <version_b> [--json]

# Rollback to a specific version
cl-context history rollback <memory_id> <target_version> \
  [--expected-version N] \
  [--actor-type human] \
  [--executed-by zserverai] \
  [--reason "..."] \
  [--yes]
```

**Behavior:**
- `--json` outputs stable machine-readable format
- `rollback` reads latest version if `--expected-version` omitted, still enforces optimistic concurrency
- Default attribution: `actor_type=human`, `initiated_by=<OS user>`, `executed_by=<OS user>`
- Confirmation prompt with proposed diff unless `--yes`
- Unified line diff for content, table for metadata

**Exit codes:**
```
0  success
1  memory not found
2  version conflict (stale expected_version)
3  invalid status transition
4  validation failure (snapshot, actor, etc.)
5  deleted memory (cannot update)
```

## 5. MCP Tools

```python
# Tool names (verb-first)
"list_memory_history": {
    "memory_id": {"type": "string"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
    "offset": {"type": "integer", "minimum": 0, "default": 0}
}

"diff_memory_history": {
    "memory_id": {"type": "string"},
    "version_a": {"type": "integer", "minimum": 1},
    "version_b": {"type": "integer", "minimum": 1}
}

"rollback_memory": {  # omitted from tools/list when MEMORY_READ_ONLY=1
    "memory_id": {"type": "string"},
    "target_version": {"type": "integer", "minimum": 1},
    "expected_version": {"type": "integer", "minimum": 1},
    "actor_type": {"type": "string", "enum": ["human", "agent", "system"]},
    "executed_by": {"type": "string", "minLength": 1},
    "initiated_by": {"type": "string"},
    "reason": {"type": "string"},  # required when actor_type=agent
    "change_id": {"type": ["string", "null"]}
}
```

**Read-only mode:**
- `rollback_memory` omitted from `tools/list` when `MEMORY_READ_ONLY=1`
- Direct calls also rejected as defense in depth

**Error response format:**
```json
{
  "error": {
    "code": "version_conflict",
    "message": "Expected version 5, current version is 7",
    "details": {"current_version": 7}
  }
}
```

## 6. REST API Endpoints

```
GET    /v1/memories/{memory_id}/history
GET    /v1/memories/{memory_id}/history/diff?a=3&b=5
POST   /v1/memories/{memory_id}/history/rollback
```

**Headers:**
- `Authorization: Bearer <token>` (existing)
- `Idempotency-Key: <uuid>` (optional, used as change_id)

**Request/response examples:**

```bash
# List
GET /v1/memories/abc123/history?limit=10
→ {
    "entries": [...],
    "total": 12,
    "limit": 10,
    "offset": 0
  }

# Diff
GET /v1/memories/abc123/history/diff?a=3&b=5
→ [
    {"field": "content", "old_value": "...", "new_value": "..."},
    {"field": "importance", "old_value": 3, "new_value": 4}
  ]

# Rollback
POST /v1/memories/abc123/history/rollback
{
  "target_version": 3,
  "expected_version": 5,
  "actor_type": "human",
  "executed_by": "zserverai",
  "reason": "Restore original"
}
→ {
    "changed": true,
    "entry": {"version": 6, "change_id": "...", ...}
  }
```

**HTTP status codes:**
- `200` success
- `404` memory/version not found
- `409` version conflict, deleted memory, invalid transition
- `422` invalid actor, snapshot, or input
- `403` mutation blocked (read-only mode)

## 7. Git Integration

**Change correlation:**
```python
def git_commit_with_history(
    vault_path: Path,
    affected_paths: list[Path],
    change_id: str,
    memory_id: str,
    change_type: str,
    memory_title: str,
) -> str | None:
    """Commit only affected vault paths; return commit SHA or None."""
```

**File write flow:**
```
1. Write to vault_path / {memory_id}.tmp
2. os.replace(tmp_path, final_path)  # atomic
3. For moves: stage both old_path and new_path
4. For deletes: stage removal
5. git add affected_paths (explicit, not --all)
6. git diff --cached -- affected_paths
7. If diff: commit, else skip
```

**Commit message format:**
```
rollback: TasteSkill

Memory-Id: abc123
Memory-Change-Id: abc123-def456
```

**Failure handling:**
- DB is authoritative; Git failure is warning
- CLI: `warning: git commit failed, database change preserved` to stderr
- REST/MCP: `{"git_warning": "...", "git_commit_sha": null}`
- Reconciliation command can compare snapshots with vault files and repair drift (deferred to future work)

## 8. Migration Plan

**v3 migration (`v3_history_table.sql`):**
```sql
-- Add soft-delete column
ALTER TABLE memories ADD COLUMN deleted_at TEXT DEFAULT NULL;

-- Create history table
CREATE TABLE memory_history (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  change_id TEXT NOT NULL,
  actor_type TEXT NOT NULL CHECK(actor_type IN ('human', 'agent', 'system')),
  initiated_by TEXT,
  executed_by TEXT NOT NULL CHECK(trim(executed_by) <> ''),
  change_type TEXT NOT NULL CHECK(change_type IN ('create', 'update', 'status_change', 'rollback', 'delete')),
  reason TEXT,
  snapshot JSON NOT NULL CHECK(json_valid(snapshot)),
  rolled_back_from_history_id TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(memory_id, version),
  UNIQUE(change_id, memory_id),
  FOREIGN KEY (rolled_back_from_history_id) REFERENCES memory_history(id),
  CHECK (
    (actor_type = 'human' AND initiated_by IS NOT NULL AND trim(initiated_by) <> '')
    OR (actor_type = 'agent')
    OR (actor_type = 'system' AND initiated_by IS NULL)
  )
);

CREATE INDEX idx_history_created_at ON memory_history(created_at);
CREATE INDEX idx_history_executed_by ON memory_history(executed_by);

-- Set deleted_at for archived rows
UPDATE memories SET deleted_at = updated_at WHERE archived = 1 AND deleted_at IS NULL;

-- Backfill all memories
INSERT INTO memory_history (id, memory_id, version, change_id, actor_type, initiated_by, executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at)
SELECT
  lower(hex(randomblob(16))),
  id,
  1,
  lower(hex(randomblob(16))),
  'system',
  NULL,
  'history-v2-migration',
  CASE WHEN archived = 1 THEN 'delete' ELSE 'create' END,
  'Baseline created during v2 history migration',
  json_object(
    'schema_version', 1,
    'title', title,
    'content', content,
    'status', status,
    'tags', json(CASE WHEN json_valid(tags) THEN tags ELSE '[]' END),
    'importance', importance,
    'vault_path', vault_path,
    'deleted', json(CASE WHEN archived = 1 THEN 'true' ELSE 'false' END)
  ),
  NULL,
  strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM memories;
```

**Migration runner fix:**
```python
def run_migrations(db_path: str):
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys = ON")
    
    for migration_file in sorted(glob("v*.sql")):
        version = extract_version(migration_file)
        if already_applied(db, version):
            continue
        
        sql = read(migration_file)
        version_sql = version.replace("'", "''")
        script = f"""
        BEGIN IMMEDIATE;
        {sql}
        INSERT INTO schema_migrations (version)
        VALUES ('{version_sql}');
        COMMIT;
        """
        
        try:
            db.executescript(script)
        except Exception:
            db.rollback()
            raise
```

## 9. Testing Strategy

**Unit tests (per component):**
- HistoryService: create, update, delete, rollback, idempotency, concurrency
- Snapshot validation: required keys, schema_version, json_valid
- Actor validation: human requires initiated_by, system requires null
- Status transition rules: valid/invalid transitions
- Field comparison: canonicalized tags (sorted), no false diffs

**Field comparison rules:**
- Tags: sort alphabetically, compare as JSON arrays
- Strings: compare as-is (no normalization)
- Numbers: compare as numeric values
- Booleans: compare as true/false (not 0/1)
- None/null: treated as distinct values

**Integration tests:**
- CLI commands: list, diff, rollback with confirmation
- MCP tools: list, diff, rollback with read-only blocking
- REST endpoints: auth, pagination, error codes
- Git correlation: change_id in commit messages

**Migration tests:**
- Fresh database
- Upgrade with active and archived memories
- JSON tags remain arrays
- Archived rows become tombstones
- Repeated initialization is idempotent
- Forced migration failure leaves neither schema changes nor an applied marker

**Concurrency tests:**
- Concurrent updates from two independent connections: exactly one succeeds, other gets version conflict
- Repeated change_id: returns original history entry without another mutation
- No-op update: creates no version

**Rollback tests:**
- Rollback to active version restores archived=0 and clears deleted_at
- Rollback to tombstone restores archived=1
- FTS results exclude deleted memories and include restored memories correctly

**Git tests:**
- Git failure leaves DB history intact and returns a warning
- Git commit excludes unrelated staged and unstaged files
- Atomic rendering leaves no partial final file on failure

**API tests:**
- REST/MCP return stable serialized shapes and structured errors
- CLI --yes, declined confirmation, JSON output, and noninteractive input behavior

**E2E workflow:**
- Full workflow: capture → update → status transition → soft deletion → diff → rollback → verify Git

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Actor model | initiated_by + executed_by + actor_type | Complete provenance for human, agent, and system |
| Tracked fields | title, content, status, tags, importance, vault_path | All meaningful fields, no operational noise |
| Storage | Same SQLite database | Atomic writes, single backup |
| Retention | Forever by default, explicit pruning later | Complete audit trail |
| Display | CLI + MCP + REST API | Full access through shared service |
| Git relationship | Complement (not replace) | SQLite authoritative, Git for file changes |
| History format | Full snapshot (post-change) | Simple rollback, one row = one version |
| Concurrency | Optimistic with expected_version | Reject stale writes |
| Version allocation | BEGIN IMMEDIATE | Prevent competing writers |
| Idempotency | (change_id, memory_id) unique | Retry safety |
| No-op detection | Compare fields before writing | Avoid noise in history |
| Soft delete | deleted_at column + archived sync | Tombstone in both DB and history |
| Rollback | Create new version, never delete | Preserve full history |
| Migration | Atomic transaction with marker | Crash-safe schema changes |
