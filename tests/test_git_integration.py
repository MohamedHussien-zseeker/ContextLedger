"""Tests for Git integration with history."""

import subprocess
import tempfile
import os
import pytest
from pathlib import Path
from memory.review import git_commit_with_history


@pytest.fixture
def git_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

        # Create initial commit
        (repo_path / "README.md").write_text("Initial")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        yield repo_path


def test_commit_with_history_success(git_repo):
    """Test successful commit with history."""
    # Create a file
    test_file = git_repo / "test.md"
    test_file.write_text("Test content")

    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[test_file],
        change_id="test-change-id",
        memory_id="mem-1",
        change_type="create",
        memory_title="Test Memory",
    )

    assert sha is not None
    assert len(sha) == 40  # Valid SHA

    # Verify commit message
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert "create: Test Memory" in result.stdout
    assert "Memory-Id: mem-1" in result.stdout
    assert "Memory-Change-Id: test-change-id" in result.stdout


def test_commit_preserves_staged(git_repo):
    """Test that existing staged changes are preserved."""
    # Stage an unrelated change
    unrelated_file = git_repo / "unrelated.txt"
    unrelated_file.write_text("Unrelated")
    subprocess.run(["git", "add", str(unrelated_file)], cwd=git_repo, check=True)

    # Now commit a different file
    test_file = git_repo / "test.md"
    test_file.write_text("Test content")

    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[test_file],
        change_id="test-change-id-2",
        memory_id="mem-2",
        change_type="update",
        memory_title="Test Memory 2",
    )

    # Verify unrelated file is still staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert "unrelated.txt" in result.stdout


def test_commit_no_changes(git_repo):
    """Test skip when no changes in affected paths."""
    test_file = git_repo / "test.md"
    test_file.write_text("No changes")

    # Commit it
    subprocess.run(["git", "add", str(test_file)], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=git_repo, check=True)

    # Try to commit again with no changes
    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[test_file],
        change_id="test-change-id-3",
        memory_id="mem-3",
        change_type="update",
        memory_title="Test Memory 3",
    )

    assert sha is None


def test_commit_failure_returns_none(git_repo):
    """Test that git failure returns None, not exception."""
    # Try to commit to non-existent path
    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[Path("nonexistent.md")],
        change_id="test-change-id-4",
        memory_id="mem-4",
        change_type="create",
        memory_title="Test Memory 4",
    )

    # Should return None, not raise
    assert sha is None
