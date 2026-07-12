-- Helium Brain v1: Add review workflow and provenance fields
-- Version: v1_add_helium_fields

ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'approved';
ALTER TABLE memories ADD COLUMN content_hash TEXT;
ALTER TABLE memories ADD COLUMN source_type TEXT DEFAULT 'manual';
ALTER TABLE memories ADD COLUMN captured_at TEXT;
ALTER TABLE memories ADD COLUMN confidentiality TEXT DEFAULT 'confidential';

CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
