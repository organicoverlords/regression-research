#!/usr/bin/env python3
import argparse
import re
import subprocess
from datetime import date
from pathlib import Path

BEGIN = "<!-- CHANGELOG-LANDING:BEGIN -->"
END = "<!-- CHANGELOG-LANDING:END -->"
DATED = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\] (.+\S)$")


def unreleased_lines(changelog: str) -> list[str]:
    if "`r`n" in changelog:
        raise SystemExit("CHANGELOG_LANDING_FAIL: CHANGELOG contains literal PowerShell `r`n escapes")
    lines = changelog.splitlines()
    try:
        start = lines.index("## [Unreleased]") + 1
    except ValueError:
        raise SystemExit("CHANGELOG_LANDING_FAIL: missing ## [Unreleased]")
    out = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        out.append(line)
    return out


def recent_entries(changelog: str) -> list[str]:
    entries = []
    for position, line in enumerate(unreleased_lines(changelog)):
        match = DATED.match(line)
        if not match:
            continue
        try:
            stamp = date.fromisoformat(match.group(1))
        except ValueError:
            raise SystemExit(f"CHANGELOG_LANDING_FAIL: invalid timeline date: {line}")
        entries.append((stamp, position, line))
    if not entries:
        raise SystemExit("CHANGELOG_LANDING_FAIL: no dated [YYYY-MM-DD] entries under [Unreleased]")
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [line for _, _, line in entries[:5]]


def projection(changelog: str) -> str:
    return "\n".join([
        BEGIN,
        "## Project timeline",
        "",
        "Canonical history: [CHANGELOG.md](CHANGELOG.md)",
        "",
        *recent_entries(changelog),
        END,
    ])


def without_projection(readme: str) -> str:
    if BEGIN not in readme and END not in readme:
        return readme
    if BEGIN not in readme or END not in readme:
        raise SystemExit("CHANGELOG_LANDING_FAIL: malformed README projection markers")
    before, tail = readme.split(BEGIN, 1)
    _, after = tail.split(END, 1)
    return (before.rstrip() + "\n" + after.lstrip("\r\n")).rstrip() + "\n"


def projected_readme(readme: str, changelog: str) -> str:
    clean = without_projection(readme)
    lines = clean.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise SystemExit("CHANGELOG_LANDING_FAIL: README must start with an H1")
    rest = "\n".join(lines[1:]).lstrip("\r\n")
    result = lines[0] + "\n\n" + projection(changelog) + "\n"
    if rest:
        result += "\n" + rest.rstrip() + "\n"
    return result


def changed_files(base_ref: str, root: Path) -> set[str]:
    out = subprocess.check_output(["git", "diff", "--name-only", f"{base_ref}...HEAD"], text=True, cwd=root)
    return {line.strip() for line in out.splitlines() if line.strip()}


def added_dated_entries(base_ref: str, root: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", "CHANGELOG.md"],
        text=True,
        cwd=root,
    )
    added = []
    for raw in out.splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:]
        match = DATED.match(line)
        if not match:
            continue
        try:
            date.fromisoformat(match.group(1))
        except ValueError:
            raise SystemExit(f"CHANGELOG_LANDING_FAIL: invalid added timeline date: {line}")
        added.append(line)
    return added


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
    expected = projected_readme(readme, changelog)
    if args.write:
        readme_path.write_text(expected, encoding="utf-8")
        readme = expected
    if readme != expected:
        raise SystemExit(
            "CHANGELOG_LANDING_FAIL: README Project timeline is stale or not immediately after H1; "
            "run .github/scripts/check_changelog_landing.py --write"
        )
    if args.base_ref:
        changed = changed_files(args.base_ref, root)
        if changed - {"CHANGELOG.md"}:
            if "CHANGELOG.md" not in changed:
                raise SystemExit("CHANGELOG_LANDING_FAIL: substantive PR changed without CHANGELOG.md")
            if not added_dated_entries(args.base_ref, root):
                raise SystemExit(
                    "CHANGELOG_LANDING_FAIL: substantive PR needs a newly added '- [YYYY-MM-DD] ...' timeline bullet"
                )
    print("CHANGELOG_LANDING_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
