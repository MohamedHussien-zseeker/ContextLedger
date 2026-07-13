-- v3: Add history table and soft-delete support

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

-- Backfill all memories as version 1
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
