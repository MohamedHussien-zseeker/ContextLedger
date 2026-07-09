# API Reference

Base URL: `http://127.0.0.1:9314`

## Authentication

All endpoints except `/v1/health` require a bearer token.

```bash
# Generate a token
openssl rand -hex 32 > ~/.memory/token

# Use it
curl -H "Authorization: Bearer $(cat ~/.memory/token)" http://127.0.0.1:9314/v1/stats
```

## Endpoints

### Health

```bash
GET /v1/health
```

Response:
```json
{"status": "ok", "memory_count": 42, "db_size_bytes": 65536}
```

### Create Memory

```bash
POST /v1/remember
Content-Type: application/json

{
    "type": "note",
    "title": "My Note",
    "content": "Some content...",
    "source": "manual",
    "importance": 3,
    "tags": ["ai", "memory"]
}
```

Response: `201 Created` with the full memory object.

### Get Memory

```bash
GET /v1/memories/{id}
```

### Update Memory

```bash
PUT /v1/memories/{id}
Content-Type: application/json

{
    "title": "Updated Title",
    "importance": 4
}
```

### Delete Memory

```bash
DELETE /v1/memories/{id}
```

Archives the memory (soft delete).

### Search

```bash
POST /v1/search
Content-Type: application/json

{
    "q": "RAG pipeline",
    "tags": ["ai"],
    "type": "note",
    "source": "obsidian",
    "limit": 10,
    "offset": 0
}
```

Response:
```json
{
    "memories": [
        {"id": "...", "title": "...", "score": null, ...}
    ],
    "total": 5
}
```

### Related Memories

```bash
GET /v1/related/{id}?limit=5
```

### Stats

```bash
GET /v1/stats
```

Response:
```json
{
    "total_memories": 42,
    "by_type": {"note": 30, "project": 5, "log": 7},
    "by_source": {"obsidian": 40, "manual": 2},
    "total_relationships": 85,
    "db_size_bytes": 65536,
    "health": "ok"
}
```

### Entities

```bash
GET /v1/entities/{id}
```

Returns extracted people, URLs, and topics from a memory.

### Capture

```bash
POST /v1/capture
Content-Type: application/json

{
    "scheme": "file",
    "target": "/path/to/file.md",
    "process": false
}
```

### Process

```bash
POST /v1/process
Content-Type: application/json

{
    "force": false,
    "dry_run": false,
    "limit": 0
}
```

### Index

```bash
POST /v1/index
Content-Type: application/json

{
    "apply": true,
    "dry_run": false
}
```
