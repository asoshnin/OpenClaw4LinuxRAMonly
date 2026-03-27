"""
test_validate_path.py — Airlock boundary enforcement tests.

Covers: correct paths, outside-boundary paths, sibling-prefix collision,
and symlink traversal attacks.
"""
import os
import pytest


def _get_validate(ws):
    """Return validate_path from the already-patched librarian_ctl module."""
    import librarian_ctl
    return librarian_ctl.validate_path


def test_valid_path_inside_workspace(isolated_workspace):
    """A path inside the workspace resolves and returns the real path."""
    validate_path = _get_validate(isolated_workspace)
    target = isolated_workspace / "factory.db"
    target.touch()
    result = validate_path(str(target))
    assert result == str(target.resolve())


def test_valid_workspace_root_itself(isolated_workspace):
    """The workspace root itself is a valid path (exact equality branch)."""
    validate_path = _get_validate(isolated_workspace)
    result = validate_path(str(isolated_workspace))
    assert result == str(isolated_workspace.resolve())


def test_outside_boundary_raises(isolated_workspace):
    """A path clearly outside the workspace raises PermissionError."""
    validate_path = _get_validate(isolated_workspace)
    with pytest.raises(PermissionError, match="Airlock Breach"):
        validate_path("/tmp/evil_file.txt")


def test_home_directory_raises(isolated_workspace):
    """User's home directory itself is outside the workspace boundary."""
    validate_path = _get_validate(isolated_workspace)
    home = os.path.expanduser("~")
    with pytest.raises(PermissionError, match="Airlock Breach"):
        validate_path(home)


def test_prefix_collision_sibling_rejected(isolated_workspace, tmp_path):
    """
    A sibling directory that shares the workspace name prefix must be rejected.

    e.g. if workspace = /tmp/pytest-xyz/workspace
         then /tmp/pytest-xyz/workspace_evil must NOT pass.

    This validates the os.sep suffix guard in validate_path().
    """
    validate_path = _get_validate(isolated_workspace)
    # Create a sibling directory with the same prefix + suffix
    sibling = isolated_workspace.parent / (isolated_workspace.name + "_evil")
    sibling.mkdir()
    evil_file = sibling / "payload.txt"
    evil_file.touch()
    with pytest.raises(PermissionError, match="Airlock Breach"):
        validate_path(str(evil_file))


def test_symlink_traversal_rejected(isolated_workspace):
    """
    A symlink inside the workspace that points outside must be rejected.
    os.path.realpath() resolves symlinks before the boundary check.
    """
    validate_path = _get_validate(isolated_workspace)
    # Create a symlink inside workspace pointing to /tmp
    link = isolated_workspace / "escape_link"
    link.symlink_to("/tmp")
    target_via_link = link / "some_file"
    with pytest.raises(PermissionError, match="Airlock Breach"):
        validate_path(str(target_via_link))
