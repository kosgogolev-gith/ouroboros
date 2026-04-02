#!/usr/bin/env python3
"""
Децентрализованная синхронизация развертывания Ouroboros.

Source of truth: /home/goga/ouroboros_repo/
Runtime: /home/goga/ouroboros/

Гарантии:
- Консистентность VERSION (файл, pyproject.toml, README.md)
- Синхронизация критически важных файлов
- Проверка целостности (размер, mtime)
- Журналирование операций
- Возможность принудительной перезагрузки systemd
"""

import os
import sys
import hashlib
import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# Конфигурация путей
REPO_DIR = Path("/home/goga/ouroboros_repo")
RUNTIME_DIR = Path("/home/goga/ouroboros")
STATE_DIR = Path("/home/goga/ouroboros_data/state")
SYNC_LOG = STATE_DIR / "deploy_sync.jsonl"

# Критические файлы для синхронизации (относительно repo/)
CRITICAL_FILES = [
    "VERSION",
    "pyproject.toml",
    "requirements.txt",
    "colab_launcher.py",
    "README.md",
    "BIBLE.md",
    "prompts/SYSTEM.md",
]

# Директории для полной копии (рекурсивно)
SYNC_DIRS = [
    "ouroboros/",
    "supervisor/",
    "prompts/",
    "docs/",
    "tests/",
    "integrations/",
]


def log_sync(event: Dict):
    """Запись события синхронизации в журнал."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYNC_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def file_hash(path: Path) -> str:
    """Вычислить SHA256 файла."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def compare_files(repo_path: Path, runtime_path: Path) -> Tuple[bool, Optional[str]]:
    """Сравнить файлы. Возвращает (identical, reason)."""
    if not runtime_path.exists():
        return False, "runtime missing"
    if not repo_path.exists():
        return False, "repo missing"
    if repo_path.stat().st_size != runtime_path.stat().st_size:
        return False, "size mismatch"
    try:
        if file_hash(repo_path) != file_hash(runtime_path):
            return False, "content mismatch"
    except Exception as e:
        return False, f"hash error: {e}"
    return True, None


def get_version_from_file() -> str:
    """Прочитать VERSION из репозитория."""
    return (REPO_DIR / "VERSION").read_text().strip()


def get_version_from_pyproject() -> str:
    """Извлечь version из pyproject.toml."""
    import tomllib
    content = (REPO_DIR / "pyproject.toml").read_text()
    data = tomllib.loads(content)
    return data["project"]["version"]


def get_version_from_readme() -> Optional[str]:
    """Попытаться извлечь версию из README (changelog)."""
    readme = (REPO_DIR / "README.md").read_text()
    # Ищем строку вида "## v6.4.1" или "### 6.4.1"
    import re
    match = re.search(r'(?:##|###)\s+v?(\d+\.\d+\.\d+)', readme)
    if match:
        return match.group(1)
    return None


def check_version_consistency() -> Dict:
    """
    Проверить, что VERSION согласован между файлами.
    Возвращает словарь с результатами и рекомендациями.
    """
    versions = {
        "VERSION": get_version_from_file(),
        "pyproject.toml": get_version_from_pyproject(),
        "README.md": get_version_from_readme(),
    }

    unique = set(versions.values())
    consistent = len(unique) == 1

    result = {
        "consistent": consistent,
        "versions": versions,
        "master_version": versions["VERSION"],
    }

    if not consistent:
        result["fixes_needed"] = []
        for src, ver in versions.items():
            if ver != versions["VERSION"]:
                result["fixes_needed"].append({
                    "file": src,
                    "current": ver,
                    "expected": versions["VERSION"],
                })

    return result


def sync_critical_files(dry_run: bool = False) -> Dict:
    """
    Синхронизировать критические одиночные файлы.
    Возвращает статистику.
    """
    stats = {"copied": [], "up_to_date": [], "errors": []}

    for rel_path in CRITICAL_FILES:
        repo_file = REPO_DIR / rel_path
        runtime_file = RUNTIME_DIR / rel_path

        if not repo_file.exists():
            stats["errors"].append(f"repo missing: {rel_path}")
            continue

        identical, reason = compare_files(repo_file, runtime_file) if runtime_file.exists() else (False, "runtime missing")

        if identical:
            stats["up_to_date"].append(rel_path)
            continue

        if dry_run:
            stats["copied"].append(f"{rel_path} (dry-run, would copy: {reason})")
        else:
            try:
                runtime_file.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(repo_file, runtime_file)
                stats["copied"].append(f"{rel_path} ({reason})")
            except Exception as e:
                stats["errors"].append(f"{rel_path}: {e}")

    return stats


def sync_directories(dry_run: bool = False) -> Dict:
    """
    Рекурсивно синхронизировать директории.
    Использует простую стратегию: копирует всё из repo в runtime,
    но только если файл изменился.
    """
    stats = {"copied": [], "up_to_date": [], "errors": []}

    for dir_rel in SYNC_DIRS:
        repo_dir = REPO_DIR / dir_rel
        runtime_dir = RUNTIME_DIR / dir_rel

        if not repo_dir.exists():
            stats["errors"].append(f"repo dir missing: {dir_rel}")
            continue

        for root, dirs, files in os.walk(repo_dir):
            rel_root = Path(root).relative_to(repo_dir)
            runtime_root = runtime_dir / rel_root

            for d in dirs:
                runtime_dir_path = runtime_root / d
                if not runtime_dir_path.exists():
                    if dry_run:
                        stats["copied"].append(f"mkdir: {dir_rel}/{rel_root}/{d}")
                    else:
                        runtime_dir_path.mkdir(parents=True, exist_ok=True)
                        stats["copied"].append(f"mkdir: {dir_rel}/{rel_root}/{d}")

            for f in files:
                repo_file = Path(root) / f
                runtime_file = runtime_root / f

                identical, reason = compare_files(repo_file, runtime_file) if runtime_file.exists() else (False, "runtime missing")

                if identical:
                    stats["up_to_date"].append(f"{dir_rel}/{rel_root}/{f}")
                    continue

                if dry_run:
                    stats["copied"].append(f"{dir_rel}/{rel_root}/{f} (dry-run, would copy: {reason})")
                else:
                    try:
                        runtime_root.mkdir(parents=True, exist_ok=True)
                        import shutil
                        shutil.copy2(repo_file, runtime_file)
                        stats["copied"].append(f"{dir_rel}/{rel_root}/{f} ({reason})")
                    except Exception as e:
                        stats["errors"].append(f"{dir_rel}/{rel_root}/{f}: {e}")

    return stats


def restart_service() -> bool:
    """Перезапустить systemd сервис ouroboros."""
    try:
        subprocess.run(["systemctl", "restart", "ouroboros"], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка перезапуска сервиса: {e.stderr}", file=sys.stderr)
        return False


def fix_version_mismatch(dry_run: bool = False) -> Dict:
    """
    Исправить рассогласование VERSION.
    Правило: мастер-версия берётся из VERSION файла.
    pyproject.toml и README должны следовать за ним.
    """
    result = check_version_consistency()
    if result["consistent"]:
        return {"action": "none", "reason": "already consistent"}

    master_version = result["master_version"]
    fixes = []

    for fix in result.get("fixes_needed", []):
        file_path = REPO_DIR / fix["file"]
        if dry_run:
            fixes.append(f"Would update {fix['file']}: {fix['current']} -> {master_version}")
            continue

        try:
            content = file_path.read_text()
            if fix["file"] == "pyproject.toml":
                import tomllib
                from tomli_w import dumps
                data = tomllib.loads(content)
                data["project"]["version"] = master_version
                new_content = dumps(data)
            elif fix["file"] == "README.md":
                # В README ищем строку с версией в changelog и заменяем
                import re
                pattern = rf'(?##|###)\s+v?(\d+\.\d+\.\d+)'
                new_content = re.sub(pattern, rf'\1 v{master_version}', content, count=1)
            else:
                # Для VERSION — просто перезаписываем
                new_content = master_version + "\n"

            file_path.write_text(new_content)
            fixes.append(f"Updated {fix['file']}: {fix['current']} -> {master_version}")
        except Exception as e:
            fixes.append(f"Failed to update {fix['file']}: {e}")

    # После исправления делаем commit
    if fixes and not dry_run:
        try:
            subprocess.run(["git", "-C", str(REPO_DIR), "add", "VERSION", "pyproject.toml", "README.md"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(REPO_DIR), "commit", "-m", f"chore: sync VERSION to {master_version}"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(REPO_DIR), "push"], check=True, capture_output=True)
            fixes.append("Committed and pushed version fixes")
        except subprocess.CalledProcessError as e:
            fixes.append(f"Git commit failed: {e.stderr}")

    return {"action": "fixed", "fixes": fixes}


def full_sync(dry_run: bool = False, restart: bool = False) -> Dict:
    """
    Полная синхронизация: версии + файлы + опционально рестарт.
    Возвращает полную статистику.
    """
    log_sync({"event": "sync_start", "dry_run": dry_run, "restart": restart})

    result = {
        "started": "now",
        "dry_run": dry_run,
        "restart": restart,
        "version_check": check_version_consistency(),
    }

    # Исправляем рассогласование версий
    fix_result = fix_version_mismatch(dry_run=dry_run)
    result["version_fix"] = fix_result

    # Синхронизируем файлы
    result["critical_files"] = sync_critical_files(dry_run=dry_run)
    result["directories"] = sync_directories(dry_run=dry_run)

    # Статистика по количеству файлов
    total_copied = len(result["critical_files"]["copied"]) + len(result["directories"]["copied"])
    total_errors = len(result["critical_files"]["errors"]) + len(result["directories"]["errors"])

    result["summary"] = {
        "files_copied": total_copied,
        "errors": total_errors,
        "would_restart": restart and not dry_run and total_errors == 0,
    }

    # Перезапуск сервиса (только если нет ошибок)
    if restart and not dry_run and total_errors == 0:
        if restart_service():
            result["restart_result"] = "success"
            log_sync({"event": "service_restart", "status": "success"})
        else:
            result["restart_result"] = "failed"
            log_sync({"event": "service_restart", "status": "failed"})

    log_sync({"event": "sync_complete", **result["summary"]})
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Синхронизация развертывания Ouroboros")
    parser.add_argument("--dry-run", action="store_true", help="Показать, что будет сделано, без изменений")
    parser.add_argument("--restart", action="store_true", help="Перезапустить systemd сервис после синхронизации")
    parser.add_argument("--check-versions", action="store_true", help="Только проверить согласованность версий")
    args = parser.parse_args()

    if args.check_versions:
        result = check_version_consistency()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["consistent"] else 1)

    result = full_sync(dry_run=args.dry_run, restart=args.restart)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Возвращаем код ошибки, если были проблемы
    if result["summary"]["errors"] > 0:
        sys.exit(1)
    if not result["version_check"]["consistent"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
