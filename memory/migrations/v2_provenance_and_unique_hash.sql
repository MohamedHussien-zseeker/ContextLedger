ALTER TABLE memories ADD COLUMN source_uri TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_active_content_hash
ON memories(content_hash)
WHERE archived=0 AND content_hash IS NOT NULL AND content_hash != '';
