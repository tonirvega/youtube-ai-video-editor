"""Prepare one daily GitHub release from Conventional Commits.

The GitHub workflow owns committing, tagging, and publishing. This script only
calculates the semantic version and writes the version and changelog artifacts.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
NOTES = ROOT / ".release-notes.md"
CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?:\s+(?P<description>.+)$")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True,
                          capture_output=True).stdout.strip()


def latest_tag() -> str | None:
    tags = git("tag", "--list", "v*", "--sort=-version:refname").splitlines()
    return tags[0] if tags else None


def release_already_created_today(tag: str | None) -> bool:
    if not tag:
        return False
    tag_date = git("for-each-ref", f"refs/tags/{tag}", "--format=%(creatordate:short)")
    return tag_date == datetime.now(UTC).date().isoformat()


def commits_since(tag: str | None) -> list[tuple[str, str]]:
    revision = f"{tag}..HEAD" if tag else "HEAD"
    output = git("log", revision, "--format=%s%x1f%b%x1e")
    commits: list[tuple[str, str]] = []
    for entry in output.split("\x1e"):
        if not entry.strip() or "\x1f" not in entry:
            continue
        subject, body = entry.split("\x1f", 1)
        commits.append((subject.strip(), body.strip()))
    return commits


def classify(commits: list[tuple[str, str]]) -> tuple[str | None, list[tuple[str, str]]]:
    level: str | None = None
    accepted: list[tuple[str, str]] = []
    priority = {"patch": 1, "minor": 2, "major": 3}
    for subject, body in commits:
        match = CONVENTIONAL.match(subject)
        if not match:
            continue
        commit_type = match.group("type")
        breaking = match.group("breaking") or "BREAKING CHANGE:" in body
        if breaking:
            bump = "major"
        elif commit_type == "feat":
            bump = "minor"
        elif commit_type in {"fix", "perf", "refactor", "revert"}:
            bump = "patch"
        else:
            continue
        if level is None or priority[bump] > priority[level]:
            level = bump
        accepted.append((commit_type, match.group("description")))
    return level, accepted


def current_version() -> tuple[int, int, int]:
    match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', VERSION_FILE.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find a semantic version in pyproject.toml.")
    return tuple(int(part) for part in match.groups())


def bump(version: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def prepare_release(dry_run: bool) -> tuple[bool, str | None]:
    tag = latest_tag()
    if release_already_created_today(tag):
        return False, None
    level, commits = classify(commits_since(tag))
    if level is None:
        return False, None

    version = ".".join(str(part) for part in bump(current_version(), level))
    notes = "\n".join(f"- **{kind}**: {description}" for kind, description in commits)
    if dry_run:
        return True, version

    content = VERSION_FILE.read_text(encoding="utf-8")
    VERSION_FILE.write_text(re.sub(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{version}"', content), encoding="utf-8")
    heading = f"## v{version} - {datetime.now(UTC).date().isoformat()}\n\n{notes}\n\n"
    previous = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Changelog\n\n"
    CHANGELOG.write_text(previous.replace("# Changelog\n\n", "# Changelog\n\n" + heading, 1), encoding="utf-8")
    NOTES.write_text(heading, encoding="utf-8")
    return True, version


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a daily Semantic Version release from Conventional Commits.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate the release without changing files")
    args = parser.parse_args()
    released, version = prepare_release(args.dry_run)
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"released={'true' if released else 'false'}\n")
            stream.write(f"version={version or ''}\n")
    print(f"released={released}; version={version or 'none'}")


if __name__ == "__main__":
    main()
