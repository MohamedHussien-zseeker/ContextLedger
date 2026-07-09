import os
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_VAULT = Path.home() / ".memory" / "vault"
CONFIG_DIR = Path.home() / ".memory"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# ── Service ───────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 9314
TOKEN_PATH = CONFIG_DIR / "token"

# ── Qdrant (optional) ────────────────────────────────────────────────
QDRANT_HOST = "127.0.0.1"
QDRANT_PORT = 6333
COLLECTION_NAME = "memories"

# ── Embeddings (optional) ────────────────────────────────────────────
OLLAMA_HOST = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

# ── Vault paths (stable contract) ────────────────────────────────────
RAW_DIR = "raw"
GENERATED_DIR = "wiki/generated"
HUB_DIR = "wiki/hubs"
