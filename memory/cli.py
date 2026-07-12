#!/usr/bin/env python3
"""ContextLedger CLI."""

import argparse
import sys
from pathlib import Path

from memory import config
from memory.doctor import check as doctor_check
from memory.graph import health as graph_health
from memory.indexer import index_vault
from memory.processor import process_all, process_source
from memory.providers import get as get_provider
from memory.providers import list_providers
from memory.search import search
from memory.vault import default_vault_path, init_vault


def cmd_init(args):
    try:
        vault_path = Path(args.path) if args.path else default_vault_path()
        result = init_vault(vault_path)
        print(f"Vault initialized at {result}")
    except FileExistsError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def cmd_capture(args):
    from memory.crud import find_by_content_hash
    from memory.database import init_db
    from memory.indexer import index_file

    provider = get_provider(args.scheme)
    if not provider:
        available = ", ".join(list_providers())
        print(f"ERROR: no provider for '{args.scheme}'. Available: {available}")
        sys.exit(1)
    vault_path = args.vault or default_vault_path()
    init_db(vault_path)
    raw_dir = vault_path / config.RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_source = provider.capture(args.target)

    # Idempotent capture: check for duplicates by content hash
    existing = find_by_content_hash(vault_path, raw_source.content_hash)
    if existing:
        print(f"Duplicate skipped: {existing['title']} (hash: {raw_source.content_hash[:12]}...)")
        return

    source_slug = raw_source.title.lower().replace(" ", "-")
    source_path = raw_dir / f"{source_slug}.md"
    fm = {
        "captured": raw_source.captured_at,
        "source_type": raw_source.source_type,
        "source_uri": raw_source.source_uri,
        "title": raw_source.title,
        "status": "captured",
        "content_hash": raw_source.content_hash,
        "confidentiality": raw_source.confidentiality,
    }
    with open(source_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        for k, v in fm.items():
            f.write(f"{k}: {v}\n")
        f.write("---\n\n")
        f.write(raw_source.content)
    index_file(vault_path, str(source_path.relative_to(vault_path)), apply=True)
    print(f"Captured to {source_path.relative_to(vault_path)}")
    if args.process:
        result = process_source(vault_path, source_path, dry_run=args.dry_run)
        print(f"Processed: {result['action']} -> {result.get('note', 'N/A')}")


def cmd_process(args):
    vault_path = args.vault or default_vault_path()
    results = process_all(vault_path, force=args.force, dry_run=args.dry_run, limit=args.limit or 0)
    if not results:
        print("No raw sources to process.")
        return
    for r in results:
        if r["action"] == "skip":
            print(f"  skip  {r['source']}")
        else:
            print(
                f"  {r['action']:<6} {r['source']} -> {r.get('note', '')} [{', '.join(r.get('hubs', []))}]"
            )
    print(f"Processed: {len(results)}")


def cmd_index(args):
    vault_path = args.vault or default_vault_path()
    apply = args.apply or args.dry_run is False
    stats = index_vault(vault_path, apply=apply)
    print(f"Files: {stats['files']}")
    if apply:
        print(f"Total memories: {stats.get('total_memories', 'N/A')}")
        print(f"Relationships rebuilt: {stats.get('relationships', 0)}")
        print(f"Archived stale paths: {stats.get('archived', 0)}")
    else:
        new = sum(1 for r in stats["results"] if not r["existing"])
        print(f"Not in DB: {new}/{stats['files']}")


def cmd_search(args):
    vault_path = args.vault or default_vault_path()
    results, total = search(vault_path, q=args.query, limit=args.limit)
    print(f"Found {total} results:")
    for mem in results:
        print(f"  [{mem.type}] {mem.title} (score: {getattr(mem, 'score', 'N/A')})")


def cmd_pending(args):
    from memory.review import list_pending

    vault_path = args.vault or default_vault_path()
    pending = list_pending(vault_path)
    if not pending:
        print("No drafts pending.")
        return
    for item in pending:
        print(f"  {item['id']}: {item['title']}")


def cmd_review(args):
    from memory.review import list_pending, read_draft

    vault_path = args.vault or default_vault_path()
    if args.id:
        print(read_draft(vault_path, args.id))
        return
    for item in list_pending(vault_path):
        print(f"\n[{item['id']}] {item['title']}\n{item['preview']}")


def _transition(args, target):
    from memory.review import git_commit, transition

    vault_path = args.vault or default_vault_path()
    destination = transition(vault_path, args.id, target, getattr(args, "replacement", None))
    prefix = {"approved": "approve", "rejected": "reject", "superseded": "supersede"}[target]
    git_commit(vault_path, prefix, args.id)
    print(f"{target.title()}: {destination.relative_to(vault_path)}")


def cmd_approve(args):
    _transition(args, "approved")


def cmd_reject(args):
    _transition(args, "rejected")


def cmd_supersede(args):
    from memory.review import git_commit, transition

    vault_path = args.vault or default_vault_path()
    transition(vault_path, args.replacement, "approved")
    destination = transition(vault_path, args.id, "superseded", args.replacement)
    git_commit(vault_path, "supersede", f"{args.id}-by-{args.replacement}")
    print(f"Superseded: {destination.relative_to(vault_path)} -> {args.replacement}")


def cmd_brief(args):
    from memory.brief import save_brief

    vault_path = args.vault or default_vault_path()
    path = save_brief(vault_path, args.project, args.type)
    print(f"Brief written to {path.relative_to(vault_path)}")


def cmd_health(args):
    vault_path = args.vault or default_vault_path()
    result = graph_health(vault_path)
    print(f"Notes: {result['total_notes']}")
    print(f"Connected: {result['connected']} ({result['connected_pct']}%)")
    print(f"Isolated: {result['isolated']} ({result['isolated_pct']}%)")
    print(f"Components: {result['components']}")
    print(f"Largest component: {result['largest_component']} ({result['largest_component_pct']}%)")
    print(f"Generated isolated: {result['generated_isolated']}")
    for f in result["generated_isolated_files"][:5]:
        print(f"  {f}")


def cmd_doctor(args):
    vault_path = args.vault or default_vault_path()
    result = doctor_check(vault_path)
    for key, val in result["checks"].items():
        status = "OK" if val else "FAIL"
        if isinstance(val, bool):
            print(f"  {key}: {status}")
        else:
            print(f"  {key}: {val}")
    if result["issues"]:
        print(f"\nIssues found ({len(result['issues'])}):")
        for issue in result["issues"]:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("\nNo issues found.")


def cmd_serve(args):
    try:
        import uvicorn

        from memory.api.server import app

        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except ImportError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def cmd_mcp(args):
    try:
        from memory.mcp.server import main as mcp_main

        mcp_main()
    except ImportError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="ContextLedger")
    parser.add_argument("--vault", "-v", help="Path to vault (default: ~/.memory/vault)")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Create a new vault")
    p_init.add_argument("path", nargs="?", help="Vault path")

    p_capture = sub.add_parser("capture", help="Capture a source")
    p_capture.add_argument("scheme", help="Provider scheme (file, youtube, etc.)")
    p_capture.add_argument("target", help="Source URI or path")
    p_capture.add_argument(
        "--process", action="store_true", help="Process immediately after capture"
    )
    p_capture.add_argument("--dry-run", action="store_true")

    p_process = sub.add_parser("process", help="Process raw sources into knowledge notes")
    p_process.add_argument(
        "--force", action="store_true", help="Regenerate already processed sources"
    )
    p_process.add_argument("--dry-run", action="store_true")
    p_process.add_argument("--limit", type=int, default=0)

    p_index = sub.add_parser("index", help="Index vault into SQLite")
    p_index.add_argument("--apply", action="store_true", help="Write changes")
    p_index.add_argument("--dry-run", action="store_true")

    p_search = sub.add_parser("search", help="Search memories")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=10)

    sub.add_parser("pending", help="List drafts pending review")
    p_review = sub.add_parser("review", help="Review pending drafts")
    p_review.add_argument("id", nargs="?")
    p_approve = sub.add_parser("approve", help="Approve a draft")
    p_approve.add_argument("id")
    p_reject = sub.add_parser("reject", help="Reject a draft")
    p_reject.add_argument("id")
    p_supersede = sub.add_parser("supersede", help="Supersede an approved record")
    p_supersede.add_argument("id")
    p_supersede.add_argument("replacement")
    p_brief = sub.add_parser("brief", help="Generate a project brief")
    p_brief.add_argument("project")
    p_brief.add_argument("--type", default="landing-page")

    _p_health = sub.add_parser("health", help="Graph health report")

    _p_doctor = sub.add_parser("doctor", help="Diagnose vault issues")

    p_serve = sub.add_parser("serve", help="Start REST API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=9314)

    _p_mcp = sub.add_parser("mcp", help="Start MCP server")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.vault:
        args.vault = Path(args.vault)
    cmd_map = {
        "init": cmd_init,
        "capture": cmd_capture,
        "process": cmd_process,
        "index": cmd_index,
        "search": cmd_search,
        "pending": cmd_pending,
        "review": cmd_review,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "supersede": cmd_supersede,
        "brief": cmd_brief,
        "health": cmd_health,
        "doctor": cmd_doctor,
        "serve": cmd_serve,
        "mcp": cmd_mcp,
    }
    cmd = cmd_map.get(args.command)
    if cmd:
        cmd(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
