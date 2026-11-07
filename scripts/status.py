#!/usr/bin/env python3
"""Compute status.json (the auto-maintained half of the profile).

    observedGeneration  number of commits that touched cwhash.yaml
    lastUpdated         date of the latest of those commits (YYYY-MM-DD)
    publicRepos         public repo count from the GitHub API (via `gh api`)

status.json is only rewritten when a value actually changes.
Needs full git history (actions/checkout with fetch-depth: 0) and an authenticated
`gh` (GH_TOKEN in CI).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "status.json"
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "cwhash")


def run(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    if run("git", "rev-parse", "--is-shallow-repository") == "true":
        print("error: shallow clone; use actions/checkout with fetch-depth: 0", file=sys.stderr)
        return 1

    commits = run("git", "log", "--follow", "--format=%cs", "--", "cwhash.yaml").splitlines()
    public_repos = int(run("gh", "api", f"users/{OWNER}", "--jq", ".public_repos"))

    status = {
        "phase": "Running",
        "observedGeneration": len(commits),
        "lastUpdated": commits[0] if commits else None,
        "publicRepos": public_repos,
    }

    old = json.loads(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else None
    if old == status:
        print("status.json unchanged")
        return 0
    STATUS_FILE.write_bytes((json.dumps(status, indent=2) + "\n").encode("utf-8"))
    print(f"status.json updated: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
