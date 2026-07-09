### Task 1: Project Scaffolding

**Files:**
- Create: `ai-memory-os/pyproject.toml`
- Create: `ai-memory-os/README.md`
- Create: `ai-memory-os/install.sh`
- Create: `ai-memory-os/memory/__init__.py`
- Create: `ai-memory-os/.gitignore`
- Create: `ai-memory-os/tests/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: installable package skeleton at `ai-memory-os/`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p ai-memory-os/{memory/{providers,api,mcp},vault,tests,docs}
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "ai-memory-os"
version = "0.1.0"
description = "Local-first, human-editable memory for any AI agent"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "httpx>=0.27.0",
]
optional-dependencies = {
    "qdrant" = ["qdrant-client>=1.9.0"],
    "dev" = ["pytest>=8.0", "pytest-cov>=5.0"],
}

[project.scripts]
memory = "memory.cli:main"

[tool.setuptools.packages.find]
include = ["memory*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
```

- [ ] **Step 3: Write README.md**

```markdown
# AI Memory OS

Local-first, human-editable memory for any AI agent.

```bash
./install.sh
memory init
memory capture file example.md
memory process
memory index
memory search "RAG"
memory health
```

See `docs/quickstart.md` for details.
```

- [ ] **Step 4: Write install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --upgrade pip
python3 -m pip install -e .
echo "AI Memory OS installed. Run 'memory init' to get started."
```

- [ ] **Step 5: Write .gitignore**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.env
data/
*.db
*.db-shm
*.db-wal
```

- [ ] **Step 6: Write `memory/__init__.py`**

```python
"""AI Memory OS — local-first, human-editable memory for any AI agent."""
```

- [ ] **Step 7: Write `tests/__init__.py`** (empty file)

- [ ] **Step 8: Verify package installs**

```bash
cd ai-memory-os && pip install -e . 2>&1 | tail -3
```
Expected: `Successfully installed ai-memory-os-0.1.0`

---

