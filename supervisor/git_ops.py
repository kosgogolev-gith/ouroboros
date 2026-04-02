         return False, msg

    subprocess.run(["git", "checkout", branch], cwd=str(REPO_DIR), check=True)
    subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=str(REPO_DIR), check=True)
    # Clean __pycache__ to prevent stale bytecode (git checkout may not update mtime)
    for p in REPO_DIR.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    st = load_state()
    st["current_branch"] = branch
    st["current_sha"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_DIR),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    save_state(st)
    return True, "ok"


# ---------------------------------------------------------------------------
# Safe restart orchestration
# ---------------------------------------------------------------------------

def safe_restart(
    reason: str,
    unsynced_policy: str = "rescue_and_reset",
) -> Tuple[bool, str]:
    """
    Attempt to checkout dev branch, sync deps, and verify imports.
    Falls back to stable branch if dev fails.

    Before any restart, pre-restart invariant checks are run automatically.
    If invariants fail (e.g., VERSION mismatch), restart is blocked with a clear error.

    Args:
        reason: Human-readable reason for the restart (logged to supervisor.jsonl)
        unsynced_policy: Policy for handling unsynced state (default: "rescue_and_reset")

    Returns:
        Tuple of (ok: bool, message: str)
        - If successful: (True, "OK: <branch>")
        - If failed: (False, "<error description>")
    """
    # ---- PRE-RESTART INVARIANT CHECKS (P7 protection) ----
    try:
        from supervisor.invariants import run_all_pre_restart_checks
        ok_inv, msg_inv = run_all_pre_restart_checks()
        if not ok_inv:
            log.error("Pre-restart invariant checks failed: %s", msg_inv)
            append_jsonl(
                DRIVE_ROOT / "logs" / "supervisor.jsonl",
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "type": "pre_restart_invariants_failed",
                    "reason": reason,
                    "invariant_error": msg_inv,
                },
            )
            return False, f"Invariant check failed: {msg_inv}"
    except Exception as e:
        # If invariants module itself fails, log but allow restart (we don't want to brick the system)
        log.exception("Invariant check module failed (allowing restart): %s", e)
        append_jsonl(
            DRIVE_ROOT / "logs" / "supervisor.jsonl",
            {
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "type": "pre_restart_invariants_error",
                "reason": reason,
                "error": repr(e),
            },
        )

    # Try dev branch
    ok, err = checkout_and_reset(BRANCH_DEV, reason, unsynced_policy)
    if ok:
        ok, err = sync_runtime_dependencies(reason)
        if ok:
            imp = import_test()
            if imp["ok"]:
                return True, f"OK: {BRANCH_DEV}"
            log.warning("Import test failed on %s: %s", BRANCH_DEV, imp["stderr"])
            log.warning("Falling back to stable branch")
        else:
            log.warning("Dependency sync failed on %s: %s", BRANCH_DEV, err)
            log.warning("Falling back to stable branch")
    # Fallback to stable
    ok2, err2 = checkout_and_reset(BRANCH_STABLE, reason + " (stable fallback)", unsynced_policy)
    if not ok2:
        return False, f"dev failed: {err}; stable failed: {err2}"
    ok3, err3 = sync_runtime_dependencies(reason + " (stable)")
    if not ok3:
        return False, f"dev failed: {err}; stable deps failed: {err3}"
    imp2 = import_test()
    if not imp2["ok"]:
        return False, f"dev failed: {err}; stable import failed: {imp2['stderr']}"
    return True, f"OK: {BRANCH_STABLE} (fallback from {BRANCH_DEV})"
