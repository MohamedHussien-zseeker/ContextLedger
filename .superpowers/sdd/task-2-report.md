### Task 2 Report: History Service Core

**Status:** DONE

**Files Created:**
- `memory/history.py` — HistoryService class with versioned tracking
- `tests/test_history.py` — Comprehensive unit tests (16 tests)

**Files Modified:**
- None

**Test Results:**
- All 16 tests pass (including concurrency test added in review)
- Full test suite (133 tests) passes with no regressions

**Implementation Details:**
- HistoryService class with atomic mutations (create, update, delete, rollback, change_status)
- Optimistic concurrency control via expected_version parameter
- Idempotency via change_id tracking
- Snapshot validation with required keys check
- Actor validation (human/agent/system)
- Status transition rules enforcement
- Field-level diff comparison between versions
- Thread-safe database operations using BEGIN IMMEDIATE

**Review Fix (2026-07-13):**
- Added `TestConcurrency.test_concurrent_updates` — verifies optimistic concurrency control: two concurrent updates with `expected_version=1` result in exactly one success and one `VersionConflictError`
- Fixed thread-safety issues in test: get db_path before spawning threads, set `row_factory=sqlite3.Row` on thread-local connections

**Concerns:**
- None identified. Implementation follows brief specifications exactly.

**Commits Made:**
- None (awaiting user request to commit)