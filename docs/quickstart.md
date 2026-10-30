# Quickstart

This guide takes you from a fresh clone to a searchable local memory vault.

## Install

ContextLedger requires Python 3.11+.

```bash
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
./install.sh
memory --help
```

The installer creates an isolated environment and places the `memory` command in `~/.local/bin`. If the command is not found, follow [the PATH troubleshooting step](#-localbin-not-on-path).

## Create a vault

Choose a directory for your project memory:

```bash
memory init ~/my-vault
```

Use the same vault for every command by putting the global `--vault` option before the subcommand.

## Capture a file

Create a small Markdown file to capture:

```bash
cat > my-notes.md <<'EOF'
# Project notes

We decided to use SQLite FTS5 for local full-text search.
The memory store should remain human-editable Markdown.
EOF
```

Capture it into your vault:

```bash
memory --vault ~/my-vault capture file my-notes.md
```

The file path is resolved from your current working directory. The capture command copies its contents into the vault's raw-source area.

## Process into knowledge notes

```bash
memory --vault ~/my-vault process
```

## Index into SQLite

```bash
memory --vault ~/my-vault index --apply
```

## Search

```bash
memory --vault ~/my-vault search "SQLite"
```

## Check graph health

```bash
memory --vault ~/my-vault health
```

## Diagnose issues

```bash
memory --vault ~/my-vault doctor
```

## Start the API server

By default, the API listens on localhost at port 9314:

```bash
memory --vault ~/my-vault serve
```

## Full lifecycle demo

After installing, run this complete example:

```bash
mkdir -p ~/my-vault
cat > example.md <<'EOF'
# Example project

The project uses local-first memory and SQLite full-text search.
EOF

memory init ~/my-vault
memory --vault ~/my-vault capture file example.md
memory --vault ~/my-vault process
memory --vault ~/my-vault index --apply
memory --vault ~/my-vault search "local-first"
memory --vault ~/my-vault health
memory --vault ~/my-vault doctor
```

## Troubleshooting

### Missing python3-venv

If `./install.sh` prints `ERROR: python3-venv is not installed`:

```bash
sudo apt update
sudo apt install -y python3-venv
```

Then rerun `./install.sh`.

### `~/.local/bin` not on PATH

If `memory: command not found` after installation, add `~/.local/bin` to your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

If you use a different shell, add the same export to that shell's startup file.

### Python version too old

ContextLedger requires Python 3.11+. Check your version:

```bash
python3 --version
```

On Ubuntu/Debian, if Python 3.11 is available in your configured package sources:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv
```

Then rerun `./install.sh`.

### Termux (Android)

ContextLedger supports installation on Termux. Install the build prerequisites first:

```bash
pkg update
pkg install git python rust clang make pkg-config openssl libffi
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
./install.sh
export PATH="$HOME/.local/bin:$PATH"
memory --help
```

Create a vault:

```bash
memory init ~/my-vault
```

#### Context bridge for AI apps

Use ContextLedger with a mobile AI app via clipboard:

```bash
mkdir -p ~/.memory
openssl rand -hex 32 > ~/.memory/token
MEMORY_VAULT=~/my-vault memory serve --host 127.0.0.1 --port 9314 &

cl-context "what did we decide about the project?"
```

Paste the copied context into your AI app and ask it to use that project context when answering.

For automatic clipboard access, install Termux:API:

```bash
pkg install termux-api
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

`pydantic-core` requires Rust compilation on Termux, which can take 5–10 minutes depending on your device. If compilation fails:

1. Ensure you have enough free storage (`df -h`)
2. Try increasing swap if available
3. Verify build tools: `rustc --version && clang --version`

## Upgrading

Pull the latest changes and rerun the installer:

```bash
cd ContextLedger
git pull
./install.sh
```
