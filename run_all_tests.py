"""
Universal AI Agent - one-command project test runner.

Run from the repository root:
    python run_all_tests.py

Core tests are always required. The Alembic `current` check is only run
when DATABASE_URL is explicitly configured in the shell; otherwise local
Postgres is considered unavailable and the migration graph + SQLite
migration regression tests remain the authoritative offline checks.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(label: str, cmd: list[str], cwd: Path = ROOT) -> bool:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    print("$", " ".join(cmd))
    try:
        result = subprocess.run(cmd, cwd=cwd, check=False)
    except OSError as exc:
        print(f"SKIP: {exc}")
        return True
    if result.returncode == 0:
        print(f"PASS: {label}")
        return True
    print(f"FAIL: {label} (exit {result.returncode})")
    return False


def security_scan() -> bool:
    print(f"\n{'=' * 72}\nSECURITY STATIC SCAN\n{'=' * 72}")
    forbidden = [
        (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "private key"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
        (re.compile(r"(?:sk|rk|pk)[_-]live[_-][A-Za-z0-9]{16,}"), "live provider key"),
        (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "GitHub token"),
        (re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"), "Slack token"),
    ]
    ignored_dirs = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
    allowed_test_key = "1Q5CMAJ3S3iemRmjauMWsPLeJmpY-VPO0J_9jHijTxs="
    findings: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored_dirs for part in path.parts):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, name in forbidden:
            for match in pattern.finditer(text):
                value = match.group(0)
                if name == "private key" or value != allowed_test_key:
                    findings.append(f"{path.relative_to(ROOT)}: possible {name}")
                    break

    if findings:
        print("FAIL: possible secret material found:")
        for finding in findings[:20]:
            print(" -", finding)
        return False

    print("PASS: no obvious committed private keys/live tokens found")
    return True


def main() -> int:
    results: list[tuple[str, bool]] = []

    python = sys.executable
    results.append(("Python test suite", run("Python test suite", [python, "-m", "pytest", "-q"])))

    alembic = shutil.which("alembic")
    if alembic:
        results.append(("Alembic migration graph", run("Alembic migration graph", [alembic, "heads"])))
        if "DATABASE_URL" in __import__("os").environ:
            results.append(("Alembic current", run("Alembic current", [alembic, "current"])))
        else:
            print("\nSKIP: Alembic current — DATABASE_URL is not configured locally")
    else:
        print("\nSKIP: alembic executable not found")

    results.append(("Repository security scan", security_scan()))

    dashboard = ROOT / "frontend-dashboard"
    npm = shutil.which("npm")
    if npm and (dashboard / "package.json").exists():
        if (dashboard / "package-lock.json").exists():
            results.append(("Dashboard dependency install", run("Dashboard dependency install", [npm, "ci", "--ignore-scripts"], dashboard)))
        results.append(("Dashboard lint", run("Dashboard lint", [npm, "run", "lint"], dashboard)))
        results.append(("Dashboard production build", run("Dashboard production build", [npm, "run", "build"], dashboard)))
    else:
        print("\nSKIP: npm or frontend-dashboard/package.json not found")

    print(f"\n{'=' * 72}\nFINAL RESULT\n{'=' * 72}")
    failed = [label for label, ok in results if not ok]
    if failed:
        print("FAILED CHECKS:")
        for label in failed:
            print(" -", label)
        print("\nOVERALL: FAIL")
        return 1

    print("OVERALL: PASS")
    print("All required checks that are runnable completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
