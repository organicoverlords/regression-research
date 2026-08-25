#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

BEGIN = "<!-- CHANGELOG-LANDING:BEGIN -->"
END = "<!-- CHANGELOG-LANDING:END -->"


def recent_entries(changelog: str) -> list[str]:
    lines = changelog.splitlines()
    try:
        start = lines.index("## [Unreleased]") + 1
    except ValueError:
        raise SystemExit("CHANGELOG_LANDING_FAIL: missing ## [Unreleased]")
    entries = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.startswith("- "):
            entries.append(line)
    return entries[:1]

def projection(changelog: str) -> str:
    entries = recent_entries(changelog)
    if not entries:
        entries = ["- No unreleased changes recorded."]
    return "\n".join([
        BEGIN,
        "## Recent changes",
        "",
        "Source: [CHANGELOG.md](CHANGELOG.md)",
        "",
        *entries,
        END,
    ])


def changed_files(base_ref: str, root: Path) -> set[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"], text=True, cwd=root
    )
    return {line.strip() for line in out.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    changelog_path = root / "CHANGELOG.md"
    readme_path = root / "README.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    readme = readme_path.read_text(encoding="utf-8")
    expected = projection(changelog)

    if BEGIN not in readme or END not in readme:
        raise SystemExit("CHANGELOG_LANDING_FAIL: README projection markers missing")
    before, tail = readme.split(BEGIN, 1)
    _, after = tail.split(END, 1)
    actual = BEGIN + tail.split(END, 1)[0] + END
    if args.write:
        readme_path.write_text(before + expected + after, encoding="utf-8")
        readme = readme_path.read_text(encoding="utf-8")
        actual = expected
    if actual != expected:
        raise SystemExit(
            "CHANGELOG_LANDING_FAIL: README recent-changes projection is stale; "
            "run .github/scripts/check_changelog_landing.py --write"
        )
    if args.base_ref:
        changed = changed_files(args.base_ref, root)
        non_changelog = changed - {"CHANGELOG.md"}
        if non_changelog and "CHANGELOG.md" not in changed:
            raise SystemExit(
                "CHANGELOG_LANDING_FAIL: repository changed without CHANGELOG.md update"
            )
    print("CHANGELOG_LANDING_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
