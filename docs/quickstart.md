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

### Termux (Android)

ContextLedger supports installation on Termux. The installer will detect Termux automatically and guide you through any missing prerequisites.

#### Quick install

```bash
pkg update
pkg install git python rust clang make pkg-config openssl libffi
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
./install.sh
export PATH="$HOME/.local/bin:$PATH"
memory --help
memory init ~/my-vault
```

#### Important notes for Termux

- Do **not** use `/tmp/my-vault` — Termux may have a read-only `/tmp`. Use `~/my-vault` or `$PREFIX/tmp/my-vault` instead.
- The first install may take several minutes while Rust compiles `pydantic-core`. This is normal.
- If you see errors about `ANDROID_API_LEVEL`, set it manually:
  ```bash
  export ANDROID_API_LEVEL=$(getprop ro.build.version.sdk)
  ```
- If `memory` is not found after install, add it to your PATH:
  ```bash
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
  ```

#### Slow compilation

`pydantic-core` requires Rust compilation on Termux, which can take 5-10 minutes depending on your device. If compilation fails:

1. Ensure you have enough free storage (`df -h`)
2. Try increasing swap if available
3. Verify build tools: `rustc --version && clang --version`

### Upgrading

Pull the latest changes and rerun the installer:

```bash
cd ContextLedger
git pull
./install.sh
```
