#!/usr/bin/env python3
"""ContextLedger CLI."""

import argparse
import getpass
import json
import sys
from pathlib import Path

from memory import config
from memory.database import get_db
from memory.doctor import check as doctor_check
from memory.graph import health as graph_health
from memory.history import HistoryService, MemoryNotFoundError, VersionConflictError
from memory.indexer import index_vault
from memory.processor import process_all, process_source
from memory.providers import get as get_provider
from memory.providers import list_providers
from memory.review import git_commit_with_history
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


def cmd_history(args):
    vault_path = args.vault or default_vault_path()
    db = get_db(vault_path)
    service = HistoryService(db)

    if args.history_cmd == "list":
        return _cmd_history_list(args, service)
    elif args.history_cmd == "diff":
        return _cmd_history_diff(args, service)
    elif args.history_cmd == "rollback":
        return _cmd_history_rollback(args, service, vault_path)
    else:
        print("error: history command required (list, diff, rollback)", file=sys.stderr)
        return 1


def _cmd_history_list(args, service):
    entries = service.get_log(
        memory_id=args.memory_id,
        limit=args.limit,
        offset=args.offset,
    )

    if args.json:
        output = {
            "entries": [
                {
                    "id": e.id,
                    "memory_id": e.memory_id,
                    "version": e.version,
                    "change_id": e.change_id,
                    "actor_type": e.actor_type,
                    "initiated_by": e.initiated_by,
                    "executed_by": e.executed_by,
                    "change_type": e.change_type,
                    "reason": e.reason,
                    "snapshot": e.snapshot,
                    "rolled_back_from_history_id": e.rolled_back_from_history_id,
                    "created_at": e.created_at,
                }
                for e in entries
            ],
            "total": len(entries),
            "limit": args.limit,
            "offset": args.offset,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"{'Version':<8} {'Author':<20} {'Type':<15} {'Reason':<25} {'Date':<20}")
        print("-" * 90)
        for e in entries:
            author = e.executed_by or "unknown"
            reason = (e.reason or "")[:24]
            date = e.created_at[:19]
            print(f"{e.version:<8} {author:<20} {e.change_type:<15} {reason:<25} {date:<20}")

    return 0


def _cmd_history_diff(args, service):
    try:
        diffs = service.diff_versions(args.memory_id, args.version_a, args.version_b)
    except MemoryNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.json:
        output = [
            {"field": d.field, "old_value": d.old_value, "new_value": d.new_value}
            for d in diffs
        ]
        print(json.dumps(output, indent=2))
    else:
        if not diffs:
            print("No differences found.")
            return 0

        print(f"{'Field':<15} {'Old':<30} {'New':<30}")
        print("-" * 75)
        for d in diffs:
            old = str(d.old_value)[:29]
            new = str(d.new_value)[:29]
            print(f"{d.field:<15} {old:<30} {new:<30}")

    return 0


def _cmd_history_rollback(args, service, vault_path):
    if args.expected_version is None:
        entries = service.get_log(memory_id=args.memory_id, limit=1)
        if entries:
            args.expected_version = entries[0].version
        else:
            print("error: no history found for memory", file=sys.stderr)
            return 1

    if not args.yes:
        diffs = service.diff_versions(args.memory_id, args.expected_version, args.target_version)

        print("Proposed rollback:")
        print(f"  Memory: {args.memory_id}")
        print(f"  From version: {args.expected_version}")
        print(f"  To version: {args.target_version}")

        if diffs:
            print("\nChanges:")
            for d in diffs:
                print(f"  {d.field}: {d.old_value} -> {d.new_value}")

        response = input("\nProceed? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            return 0

    executed_by = args.executed_by or getpass.getuser()
    initiated_by = getpass.getuser() if args.actor_type == "human" else None

    try:
        result = service.rollback(
            memory_id=args.memory_id,
            target_version=args.target_version,
            expected_version=args.expected_version,
            actor_type=args.actor_type,
            executed_by=executed_by,
            initiated_by=initiated_by,
            reason=args.reason,
        )
    except (MemoryNotFoundError, VersionConflictError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2 if isinstance(e, VersionConflictError) else 1

    git_sha = None
    git_warning = None

    if result.changed and result.entry.snapshot.get("vault_path"):
        vault_file = Path(vault_path) / result.entry.snapshot["vault_path"]
        if vault_file.exists():
            git_sha = git_commit_with_history(
                vault_path=Path(vault_path),
                affected_paths=[vault_file],
                change_id=result.entry.change_id,
                memory_id=args.memory_id,
                change_type="rollback",
                memory_title=result.entry.snapshot["title"],
            )
            if git_sha is None:
                git_warning = "git commit failed, database change preserved"

    if args.json:
        output = {
            "changed": result.changed,
            "entry": {
                "id": result.entry.id,
                "memory_id": result.entry.memory_id,
                "version": result.entry.version,
                "change_id": result.entry.change_id,
                "change_type": result.entry.change_type,
            },
            "git_commit_sha": git_sha,
            "git_warning": git_warning,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Rollback complete: version {result.entry.version}")
        if git_sha:
            print(f"Git commit: {git_sha}")
        if git_warning:
            print(f"warning: {git_warning}", file=sys.stderr)

    return 0


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

    # history subcommands
    p_history = sub.add_parser("history", help="Memory history operations")
    history_sub = p_history.add_subparsers(dest="history_cmd")

    history_list = history_sub.add_parser("list", help="List history for a memory")
    history_list.add_argument("memory_id", help="Memory ID")
    history_list.add_argument("--limit", type=int, default=50)
    history_list.add_argument("--offset", type=int, default=0)
    history_list.add_argument("--json", action="store_true")

    history_diff = history_sub.add_parser("diff", help="Compare two versions")
    history_diff.add_argument("memory_id", help="Memory ID")
    history_diff.add_argument("version_a", type=int, help="First version")
    history_diff.add_argument("version_b", type=int, help="Second version")
    history_diff.add_argument("--json", action="store_true")

    history_rollback = history_sub.add_parser("rollback", help="Rollback to a version")
    history_rollback.add_argument("memory_id", help="Memory ID")
    history_rollback.add_argument("target_version", type=int, help="Version to restore")
    history_rollback.add_argument("--expected-version", type=int, help="Expected current version")
    history_rollback.add_argument("--actor-type", default="human", choices=["human", "agent", "system"])
    history_rollback.add_argument("--executed-by", help="Executor identity")
    history_rollback.add_argument("--reason", help="Reason for rollback")
    history_rollback.add_argument("--yes", action="store_true", help="Skip confirmation")

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
        "history": cmd_history,
    }
    cmd = cmd_map.get(args.command)
    if cmd:
        cmd(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
