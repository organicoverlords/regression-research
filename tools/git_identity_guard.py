from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PLACEHOLDER_NAMES = {"", "your name"}
PLACEHOLDER_EMAILS = {"", "you@example.com", "you@example.invalid"}


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=check)


def local_identity(repo: Path) -> tuple[str, str]:
    name = _git(repo, "config", "--local", "--get", "user.name", check=False).stdout.strip()
    email = _git(repo, "config", "--local", "--get", "user.email", check=False).stdout.strip()
    return name, email


def identity_is_usable(name: str, email: str) -> bool:
    if name.strip().lower() in PLACEHOLDER_NAMES:
        return False
    normalized = email.strip().lower()
    if normalized in PLACEHOLDER_EMAILS or normalized.endswith(".invalid"):
        return False
    return "@" in normalized and "." in normalized.rsplit("@", 1)[-1]


def configure_local_identity(repo: Path, name: str, email: str) -> None:
    if not identity_is_usable(name, email):
        raise ValueError("refusing unusable git identity")
    _git(repo, "config", "--local", "user.name", name)
    _git(repo, "config", "--local", "user.email", email)


def github_noreply_identity() -> tuple[str, str]:
    login = subprocess.run(["gh", "api", "user", "--jq", ".login"], text=True, capture_output=True, check=True).stdout.strip()
    user_id = subprocess.run(["gh", "api", "user", "--jq", ".id"], text=True, capture_output=True, check=True).stdout.strip()
    if not login or not user_id.isdigit():
        raise RuntimeError("GitHub account identity unavailable")
    return login, f"{user_id}+{login}@users.noreply.github.com"


def audit(repo: Path) -> dict[str, object]:
    name, email = local_identity(repo)
    usable = identity_is_usable(name, email)
    return {
        "repo": str(repo.resolve()),
        "local_name": name,
        "local_email": email,
        "usable": usable,
        "scope": "repository-local only; global git config is neither read as authority nor modified",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Require a usable repository-local Git commit identity.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--fix-from-gh", action="store_true", help="set repo-local identity from the authenticated gh account")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.fix_from_gh:
        name, email = github_noreply_identity()
        configure_local_identity(repo, name, email)
    result = audit(repo)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["usable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
