# Quickstart

## Install

```bash
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
./install.sh
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
