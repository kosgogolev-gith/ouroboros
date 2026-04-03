#!/usr/bin/env python3
"""
Демон-наблюдатель за изменениями в git-репозитории.

Периодически проверяет состояние репозитория и запускает синхронизацию
при обнаружении неопубликованных коммитов или различий между
repo и runtime.

Альтернатива git hooks: более простая установка, не требует прав
на сервере. Запускается как фоновая задача Ouroboros или отдельный
systemd таймер.
"""

import json
import os
import sys
import time
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

from .sync import (
    REPO_DIR,
    RUNTIME_DIR,
    full_sync,
    check_version_consistency,
    log_sync,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("deploy.watcher")


def get_git_status() -> dict:
    """Вернуть статус git репозитория作为字典."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_DIR), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return {
            "clean": result.returncode == 0 and not result.stdout.strip(),
            "lines": result.stdout.strip().split("\n") if result.stdout.strip() else [],
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Git status failed: {e}")
        return {"clean": False, "lines": []}


def get_last_commit_sha() -> Optional[str]:
    """Получить SHA последнего коммита в текущей ветке."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def needs_sync() -> Tuple[bool, str]:
    """
    Проверить, требуется ли синхронизация.
    Возвращает (needed, reason).
    """
    # 1. Проверка на несохранённые изменения в рабочей директории
    status = get_git_status()
    if not status["clean"]:
        # Есть untracked/modified/staged файлы — нужно закоммитить? 
        # Для синхронизации мы скорее всего ждём, пока изменения войдут в историю.
        # Но если runtime отстаёт — всё равно синхронизируем.
        # Пока считаем, что синхронизация нужна, если runtime не совпадает с HEAD.
        reason = f"working directory not clean ({len(status['lines'])} changes)"
        return True, reason

    # 2. Проверка версионной консистентности
    ver_check = check_version_consistency()
    if not ver_check["consistent"]:
        return True, f"version inconsistency: {ver_check['versions']}"

    # 3. Проверка, что runtime соответствует repo HEAD
    repo_sha = get_last_commit_sha()
    runtime_sha_path = RUNTIME_DIR / ".git-head-sha"
    runtime_sha = None
    if runtime_sha_path.exists():
        runtime_sha = runtime_sha_path.read_text().strip()

    if repo_sha is None:
        return False, "cannot get repo SHA"

    if runtime_sha != repo_sha:
        return True, f"runtime outdated (runtime={runtime_sha[:8] if runtime_sha else 'none'}, repo={repo_sha[:8]})"

    # 4. Проверим хэши ключевых файлов (можно расширить)
    # Для экономии просто доверяем .git-head-sha
    return False, "up to date"


def write_runtime_sha(sha: str):
    """Записать SHA текущего репозитория в runtime-директорию."""
    (RUNTIME_DIR / ".git-head-sha").write_text(sha + "\n")


def run_sync_and_update_sha(dry_run: bool = False, restart: bool = False) -> dict:
    """Запустить синхронизацию и обновить метаданные."""
    logger.info("Starting deployment sync...")
    result = full_sync(dry_run=dry_run, restart=restart)

    # Обновляем метку SHA после успешной синхронизации
    if not dry_run and result["summary"]["errors"] == 0:
        current_sha = get_last_commit_sha()
        if current_sha:
            try:
                write_runtime_sha(current_sha)
                logger.info(f"Runtime SHA marker updated: {current_sha[:8]}")
            except Exception as e:
                logger.warning(f"Failed to write runtime SHA marker: {e}")

    logger.info(f"Sync completed: {result['summary']}")
    return result


def watch_loop(
    interval: int = 60,
    dry_run: bool = False,
    restart: bool = False,
    max_cycles: Optional[int] = None,
):
    """
    Бесконечный цикл наблюдения.
    
    Args:
        interval: интервал проверки в секундах
        dry_run: режим "сухого прогона"
        restart: перезапускать systemd после синхронизации
        max_cycles: остановиться после N циклов (для тестов)
    """
    logger.info(f"Deploy watcher started (interval={interval}s, dry_run={dry_run}, restart={restart})")
    cycle = 0

    try:
        while True:
            cycle += 1
            needs, reason = needs_sync()
            logger.debug(f"Cycle {cycle}: needs_sync={needs}, reason={reason}")

            if needs:
                logger.info(f"Sync needed: {reason}")
                result = run_sync_and_update_sha(dry_run=dry_run, restart=restart)
                # После синхронизации ждем чуть дольше, чтобы изменения устаканились
                time.sleep(5)
            else:
                logger.debug("No sync needed")

            time.sleep(interval)

            if max_cycles and cycle >= max_cycles:
                logger.info(f"Reached max_cycles={max_cycles}, exiting")
                break

    except KeyboardInterrupt:
        logger.info("Watcher interrupted by user")
    except Exception as e:
        logger.exception(f"Watcher crashed: {e}")
        raise


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deployment watcher daemon")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
    parser.add_argument("--dry-run", action="store_true", help="Do not actually copy or restart")
    parser.add_argument("--restart", action="store_true", help="Restart systemd service after sync")
    parser.add_argument("--once", action="store_true", help="Run one check and exit (no daemon loop)")
    parser.add_argument("--max-cycles", type=int, help="Stop after N cycles")
    args = parser.parse_args()

    if args.once:
        needs, reason = needs_sync()
        if needs:
            print(f"Sync needed: {reason}")
            result = run_sync_and_update_sha(dry_run=args.dry_run, restart=args.restart)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            sys.exit(0 if result["summary"]["errors"] == 0 else 1)
        else:
            print("Up to date.")
            sys.exit(0)
    else:
        watch_loop(
            interval=args.interval,
            dry_run=args.dry_run,
            restart=args.restart,
            max_cycles=args.max_cycles,
        )


if __name__ == "__main__":
    main()
