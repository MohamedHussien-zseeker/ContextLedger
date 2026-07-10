# Quickstart

## Install

```bash
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
./install.sh
memory --help
```

## Initialize a vault

```bash
memory init
```

This creates `~/.memory/vault/` with the starter structure.

## Capture a source

```bash
memory capture file my-notes.md
```

## Process into knowledge notes

```bash
memory process
```

## Index into SQLite

```bash
memory index --apply
```

## Search

```bash
memory search "RAG"
```

## Check health

```bash
memory health
```

## Diagnose issues

```bash
memory doctor
```

## Start the API server

```bash
memory serve
```

## Full lifecycle (10-minute demo)

```bash
./install.sh
memory init
memory capture file example.md
memory process
memory index --apply
memory search "RAG"
memory health
```

## Troubleshooting

### Missing python3-venv

If `./install.sh` prints `ERROR: python3-venv is not installed`:

```bash
sudo apt update
sudo apt install -y python3-venv
```

Then rerun `./install.sh`.

### ~/.local/bin not on PATH

If `memory: command not found` after install, add `~/.local/bin` to your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Python version too old

ContextLedger requires Python 3.11+. If you have an older version:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv
```

Then rerun `./install.sh`.

### Upgrading

Pull the latest changes and rerun the installer:

```bash
cd ContextLedger
git pull
./install.sh
```
