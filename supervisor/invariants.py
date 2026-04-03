"""
Supervisor — invariant verification before critical operations.

Provides pre-restart checks to prevent P7 (Versioning) violations and other
state inconsistencies. These checks are called by safe_restart before any
code restart.
"""

from __future__ import annotations

import logging
import pathlib
import re
import subprocess
from typing import Dict, List, Tuple

from supervisor.git_ops import REPO_DIR, git_capture
from supervisor.state import load_state, DRIVE_ROOT

log = logging.getLogger(__name__)


def get_version_from_file() -> str:
    """Read VERSION file from repo."""
    version_path = REPO_DIR / "VERSION"
    if not version_path.exists():
        raise FileNotFoundError(f"VERSION file not found in {REPO_DIR}")
    return version_path.read_text().strip()


def get_latest_git_tag() -> str:
    """Get the most recent annotated or lightweight tag matching vX.Y.Z."""
    rc, out, err = git_capture(["git", "tag", "--list", "v*", "--sort=-creatordate"])
    if rc != 0:
        raise RuntimeError(f"git tag failed: {err}")
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("No git tags found (expected at least one vX.Y.Z tag)")
    # Return first (latest) tag
    return lines[0]


def extract_version_from_changelog(readme_path: pathlib.Path) -> str:
    """Parse README.md changelog to find the latest version entry."""
    content = readme_path.read_text(encoding="utf-8")
    # Look for "## [X.Y.Z]" - typical markdown heading for a version
    # Or "### X.Y.Z" etc. We'll match lines like "## [1.2.3]" or "## 1.2.3"
    pattern = re.compile(r"^#{2,}\s*\[?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
    match = pattern.search(content)
    if match:
        return match.group(1)
    # Fallback: look for "Version X.Y.Z" heading
    pattern2 = re.compile(r"^#+\s*Version\s+(\d+\.\d+\.\d+)", re.MULTILINE | re.IGNORECASE)
    match2 = pattern2.search(content)
    if match2:
        return match2.group(1)
    raise RuntimeError("Could not parse version from README.md changelog")


def check_version_invariants() -> List[str]:
    """
    Check all version-related invariants.

    Returns a list of error strings. Empty list = all OK.
    Invariants:
    1. VERSION file exists and contains a valid semver.
    2. Latest git tag matches VERSION.
    3. README changelog top entry matches VERSION.
    4. Runtime state (Drive) refers to the same VERSION (optional, depends on state file).
    """
    errors: List[str] = []

    try:
        version_file = get_version_from_file()
    except Exception as e:
        errors.append(f"VERSION file error: {e}")
        return errors  # Cannot continue without VERSION

    # Check latest git tag
    try:
        latest_tag = get_latest_git_tag()
        if latest_tag != f"v{version_file}":
            errors.append(
                f"VERSION/tag mismatch: VERSION={version_file}, latest git tag={latest_tag}"
            )
    except Exception as e:
        errors.append(f"Git tag check failed: {e}")

    # Check README
    readme_path = REPO_DIR / "README.md"
    if readme_path.exists():
        try:
            readme_version = extract_version_from_changelog(readme_path)
            if readme_version != version_file:
                errors.append(
                    f"VERSION/README mismatch: VERSION={version_file}, README changelog={readme_version}"
                )
        except Exception as e:
            errors.append(f"README version parse failed: {e}")
    else:
        errors.append("README.md not found")

    # Optional: check that runtime state version matches repo VERSION
    # This is best-effort; if state file missing or corrupted, ignore
    try:
        state = load_state()
        state_version = state.get("version") or state.get("VERSION")
        if state_version and state_version != version_file:
            errors.append(
                f"VERSION/state mismatch: VERSION={version_file}, state.version={state_version}"
            )
    except Exception:
        # State may be missing or corrupted; that's not a version invariant failure
        pass

    return errors


def check_deployment_sync() -> List[str]:
    """
    Check deployment sync invariant: runtime dir vs repo dir consistency.
    Returns list of warnings/errors.
    """
    warnings: List[str] = []

    # Determine runtime working directory from environment or fallback
    # The service's WorkingDirectory is /home/goga/ouroboros
    runtime_dir = pathlib.Path("/home/goga/ouroboros")
    if not runtime_dir.exists():
        warnings.append("Runtime directory does not exist")
        return warnings

    # Check if runtime dir is different from REPO_DIR
    if runtime_dir.resolve() != REPO_DIR.resolve():
        warnings.append(
            f"Deployment two-copy problem: runtime dir={runtime_dir} != repo dir={REPO_DIR}. "
            "Systemd runs from a different location than the git repo. "
            "Consider switching service ExecStart to use the repo directly."
        )

    return warnings


def run_all_pre_restart_checks() -> Tuple[bool, str]:
    """
    Run all pre-restart invariant checks.

    Returns (ok, message):
    - ok=True, message="All invariants passed"
    - ok=False, message="Failed: <comma-separated errors>"
    """
    all_errors: List[str] = []

    # Version invariants (critical)
    version_errors = check_version_invariants()
    all_errors.extend(version_errors)

    # Deployment sync (warning-level, but can be escalated)
    sync_warnings = check_deployment_sync()
    if sync_warnings:
        # For now, treat warnings as non-fatal but log them prominently
        log.warning("Deployment sync warnings: %s", "; ".join(sync_warnings))
        # Could be made fatal via config; currently not blocking restart
        # all_errors.extend(sync_warnings)

    if all_errors:
        return False, "Failed: " + "; ".join(all_errors)
    return True, "All invariants passed"
