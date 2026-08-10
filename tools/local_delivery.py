from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable

DEFAULT_REMOTE = "https://github.com/persfinancier-blip/region-price-monitor.git"
DEFAULT_BRANCH = "work/g01-implementation"


class DeliveryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _run(
    args: list[str],
    cwd: Path | None = None,
    *,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )
    if check and cp.returncode != 0:
        command = args[0] + (f" {args[1]}" if len(args) > 1 else "")
        raise DeliveryError("LOCAL_GIT_COMMAND_FAILED", f"Команда завершилась ошибкой: {command}")
    return cp


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], repo, check=check, capture=True)


def _normalize_remote(value: str) -> str:
    value = value.strip()
    low = value.lower()
    if low.startswith("https://") or low.startswith("http://"):
        normalized = value.rstrip("/")
        if normalized.lower().endswith(".git"):
            normalized = normalized[:-4]
        return normalized.lower()
    if low.startswith("file://"):
        return str(Path(value[7:]).resolve())
    return str(Path(value).expanduser().resolve())


def _ensure_git_available() -> None:
    if shutil.which("git") is None:
        raise DeliveryError(
            "GIT_NOT_FOUND",
            "Git не найден. Установите Git for Windows и снова запустите START_PARSER.bat.",
        )


def ensure_checkout(repo: Path, remote: str, branch: str) -> bool:
    """Создать checkout, если его ещё нет. True означает, что был выполнен clone."""
    _ensure_git_available()
    repo = repo.resolve()
    if repo.exists():
        if not (repo / ".git").is_dir():
            raise DeliveryError(
                "LOCAL_CHECKOUT_WRONG_DIRECTORY",
                "Папка локального приложения уже существует, но это не Git checkout. Скрипт ничего не удалял.",
            )
        return False

    repo.parent.mkdir(parents=True, exist_ok=True)
    cp = _run(
        ["git", "clone", "--branch", branch, "--single-branch", remote, str(repo)],
        check=False,
        capture=True,
    )
    if cp.returncode != 0:
        raise DeliveryError(
            "GIT_CLONE_FAILED",
            "Не удалось скачать репозиторий. Проверьте интернет и Git-авторизацию (Git Credential Manager, если доступ станет приватным).",
        )
    return True


def recover_stale_index_lock(repo: Path) -> bool:
    """Удалить только stale .git/index.lock; активный Git никогда не прерывается."""
    lock = repo / ".git" / "index.lock"
    if not lock.exists():
        return False

    if os.name != "nt":
        raise DeliveryError(
            "LOCAL_GIT_INDEX_LOCK",
            "Обнаружен .git/index.lock. Автоматическое удаление разрешено только Windows launcher после проверки процессов.",
        )

    tasklist = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq git.exe", "/NH"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if "git.exe" in tasklist.stdout.lower():
        raise DeliveryError(
            "LOCAL_GIT_INDEX_LOCK_ACTIVE",
            "Обнаружен .git/index.lock и активный git.exe. Закройте Git-операции и повторите запуск; lock не удалён.",
        )

    try:
        lock.unlink()
    except OSError as exc:
        raise DeliveryError(
            "LOCAL_GIT_INDEX_LOCK_CLEANUP_FAILED",
            f"Stale .git/index.lock не удалось удалить: {exc}",
        ) from exc
    return True


def validate_checkout(repo: Path, remote: str) -> None:
    if not (repo / ".git").is_dir():
        raise DeliveryError("LOCAL_CHECKOUT_INVALID", "В локальной папке отсутствует .git.")

    actual_remote = _git(repo, "remote", "get-url", "origin", check=False)
    if actual_remote.returncode != 0:
        raise DeliveryError("LOCAL_CHECKOUT_WRONG_REMOTE", "Git remote 'origin' отсутствует.")
    if _normalize_remote(actual_remote.stdout.strip()) != _normalize_remote(remote):
        raise DeliveryError(
            "LOCAL_CHECKOUT_WRONG_REMOTE",
            "Локальная папка смотрит на другой origin. Обновление остановлено без изменений файлов.",
        )


def assert_clean_tracked(repo: Path) -> None:
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=no")
    if status.stdout.strip():
        raise DeliveryError(
            "LOCAL_CHECKOUT_DIRTY",
            "Есть локальные изменения tracked-файлов. Они НЕ перезаписаны. Сначала явно commit/stash/revert эти изменения.",
        )


def _fetch_target_branch(repo: Path, branch: str) -> str:
    remote_ref = f"origin/{branch}"
    refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
    fetch = _git(repo, "fetch", "--prune", "origin", refspec, check=False)
    if fetch.returncode != 0:
        raise DeliveryError(
            "GIT_FETCH_FAILED",
            "Не удалось получить обновления. Проверьте интернет/Git-авторизацию. Локальные файлы не изменены.",
        )
    remote_head_cp = _git(repo, "rev-parse", remote_ref, check=False)
    if remote_head_cp.returncode != 0:
        raise DeliveryError("REMOTE_BRANCH_NOT_FOUND", f"Удалённая ветка '{branch}' не найдена.")
    return remote_ref


def ensure_target_branch(repo: Path, branch: str, remote_ref: str) -> bool:
    """Безопасно переключиться на явно заданную implementation branch. Старые ветки/commits не удаляются."""
    current = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    current_branch = current.stdout.strip() if current.returncode == 0 else ""
    if current_branch == branch:
        return False

    assert_clean_tracked(repo)
    local_target = _git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    if local_target.returncode == 0:
        switch = _git(repo, "switch", branch, check=False)
    else:
        switch = _git(repo, "switch", "--track", "-c", branch, remote_ref, check=False)
    if switch.returncode != 0:
        raise DeliveryError(
            "LOCAL_CHECKOUT_BRANCH_SWITCH_FAILED",
            f"Не удалось безопасно переключиться на '{branch}'. Никакой reset/clean не выполнялся.",
        )

    switched = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if switched.returncode != 0 or switched.stdout.strip() != branch:
        raise DeliveryError(
            "LOCAL_CHECKOUT_BRANCH_SWITCH_FAILED",
            f"После переключения активная ветка не равна '{branch}'.",
        )
    return True


def sync_checkout(repo: Path, remote: str, branch: str) -> bool:
    """Безопасно перейти на configured branch и fast-forward обновить до origin/branch."""
    recover_stale_index_lock(repo)
    validate_checkout(repo, remote)
    assert_clean_tracked(repo)
    remote_ref = _fetch_target_branch(repo, branch)
    switched = ensure_target_branch(repo, branch, remote_ref)
    assert_clean_tracked(repo)

    local_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    remote_head = _git(repo, "rev-parse", remote_ref).stdout.strip()
    if local_head == remote_head:
        return switched

    ancestor = _git(repo, "merge-base", "--is-ancestor", "HEAD", remote_ref, check=False)
    if ancestor.returncode != 0:
        raise DeliveryError(
            "LOCAL_CHECKOUT_DIVERGED",
            "Implementation branch содержит собственные commits или разошлась с облачной. Деструктивный reset запрещён.",
        )

    merge = _git(repo, "merge", "--ff-only", remote_ref, check=False)
    if merge.returncode != 0:
        raise DeliveryError(
            "LOCAL_FAST_FORWARD_FAILED",
            "Fast-forward обновление не удалось. reset/clean не выполнялись.",
        )
    return True


def _fingerprint(paths: Iterable[Path]) -> str:
    h = hashlib.sha256()
    for path in paths:
        h.update(path.name.encode("utf-8"))
        if path.exists():
            h.update(path.read_bytes())
        else:
            h.update(b"<missing>")
    return h.hexdigest()


def prepare_local_runtime(repo: Path) -> dict[str, str]:
    """Подготовить ignored runtime-state и изолировать изменяемый products.json от Git tree."""
    core = repo / "parser" / "core"
    local_dir = core / "local"
    local_dir.mkdir(parents=True, exist_ok=True)

    local_products = local_dir / "products.json"
    tracked_products = core / "products.json"
    if not local_products.exists():
        if tracked_products.exists():
            shutil.copyfile(tracked_products, local_products)
        else:
            local_products.write_text('{"wb": [], "ozon": []}\n', encoding="utf-8")

    env = os.environ.copy()
    env["RPM_PRODUCTS"] = str(local_products)
    return env


def ensure_runtime(repo: Path, env: dict[str, str], *, skip_setup: bool = False) -> bool:
    """Запустить существующий install.bat только если runtime отсутствует или installer/dependencies изменились."""
    core = repo / "parser" / "core"
    state_dir = core / "local"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / ".runtime_fingerprint"
    current = _fingerprint([repo / "install.bat", core / "requirements.txt"])
    venv_python = core / "venv" / "Scripts" / "python.exe"

    previous = state_file.read_text(encoding="utf-8").strip() if state_file.exists() else ""
    needs_setup = previous != current or (os.name == "nt" and not venv_python.exists())
    if not needs_setup:
        return False
    if skip_setup:
        return True
    if os.name != "nt":
        raise DeliveryError("WINDOWS_SETUP_REQUIRED", "Локальный installer рассчитан на Windows.")

    install = repo / "install.bat"
    if not install.exists():
        raise DeliveryError("INSTALLER_NOT_FOUND", "В checkout отсутствует install.bat.")

    setup_env = env.copy()
    setup_env["RPM_INSTALL_NONINTERACTIVE"] = "1"
    cp = subprocess.run(["cmd", "/c", str(install)], cwd=str(repo), env=setup_env)
    if cp.returncode != 0:
        raise DeliveryError("LOCAL_RUNTIME_SETUP_FAILED", "Установка/обновление Python runtime завершилась ошибкой.")
    state_file.write_text(current + "\n", encoding="utf-8")
    return True


def launch_parser(repo: Path, env: dict[str, str]) -> int:
    if os.name != "nt":
        raise DeliveryError("WINDOWS_LAUNCH_REQUIRED", "Локальный launcher рассчитан на Windows.")
    launcher = repo / "parser" / "run_parser.bat"
    if not launcher.exists():
        raise DeliveryError("PARSER_LAUNCHER_NOT_FOUND", "В checkout отсутствует parser/run_parser.bat.")
    cp = subprocess.run(["cmd", "/c", str(launcher)], cwd=str(repo), env=env)
    return cp.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--skip-setup", action="store_true")
    ns = parser.parse_args(argv)

    repo = Path(ns.repo)
    try:
        cloned = ensure_checkout(repo, ns.remote, ns.branch)
        changed = sync_checkout(repo, ns.remote, ns.branch)
        env = prepare_local_runtime(repo)
        setup = ensure_runtime(repo, env, skip_setup=ns.skip_setup)
        print(
            f"[OK] checkout={'cloned' if cloned else 'existing'} "
            f"update={'yes' if changed else 'no'} setup={'needed' if setup else 'current'}"
        )
        if ns.launch:
            return launch_parser(repo, env)
        return 0
    except DeliveryError as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
