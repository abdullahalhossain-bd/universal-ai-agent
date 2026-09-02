# -*- coding: utf-8 -*-

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXCLUDE = {
    ".venv",
    "__pycache__",
    ".git",
    "node_modules",
}

print("=" * 80)
print("UNIVERSAL AI AGENT - FULL PROJECT AUDIT")
print("=" * 80)


# ============================================================
# FILES
# ============================================================

files = []

for p in ROOT.rglob("*"):

    if not p.is_file():
        continue

    if any(part in EXCLUDE for part in p.parts):
        continue

    files.append(p)

py_files = [
    p for p in files
    if p.suffix.lower() == ".py"
]

print("\n[1] PROJECT FILES")
print("-" * 80)

print("Total files :", len(files))
print("Python files:", len(py_files))

for p in sorted(py_files):
    print(" ", p.relative_to(ROOT))


# ============================================================
# API ROUTES
# ============================================================

print("\n[2] FASTAPI ROUTES")
print("-" * 80)

routes = []

for p in py_files:

    try:
        source = p.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        tree = ast.parse(source)

    except Exception:
        continue

    for node in ast.walk(tree):

        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Attribute):
            continue

        method = node.func.attr.lower()

        if method not in {
            "get",
            "post",
            "put",
            "patch",
            "delete",
        }:
            continue

        if not node.args:
            continue

        arg = node.args[0]

        if isinstance(arg, ast.Constant):

            routes.append(
                (
                    method.upper(),
                    str(arg.value),
                    str(p.relative_to(ROOT)),
                )
            )

for method, route, file in sorted(routes):

    print(
        f"{method:7} {route:50} {file}"
    )

print("\nRoutes found:", len(routes))


# ============================================================
# CLASSES
# ============================================================

print("\n[3] CLASSES")
print("-" * 80)

classes = []

for p in py_files:

    try:
        tree = ast.parse(
            p.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        )

    except Exception:
        continue

    for node in ast.walk(tree):

        if isinstance(node, ast.ClassDef):

            classes.append(
                (
                    node.name,
                    str(p.relative_to(ROOT)),
                )
            )

for name, file in sorted(classes):

    print(
        f"{name:45} {file}"
    )

print("\nClasses found:", len(classes))


# ============================================================
# FUNCTIONS
# ============================================================

print("\n[4] FUNCTIONS")
print("-" * 80)

functions = []

for p in py_files:

    try:
        tree = ast.parse(
            p.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        )

    except Exception:
        continue

    for node in ast.walk(tree):

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):

            functions.append(
                (
                    node.name,
                    str(p.relative_to(ROOT)),
                    isinstance(
                        node,
                        ast.AsyncFunctionDef,
                    ),
                )
            )

for name, file, is_async in sorted(functions):

    prefix = "async " if is_async else ""

    print(
        f"{prefix}{name:40} {file}"
    )

print("\nFunctions found:", len(functions))


# ============================================================
# TODO / FIXME / PLACEHOLDER
# ============================================================

print("\n[5] TODO / FIXME / PLACEHOLDER")
print("-" * 80)

patterns = [
    "TODO",
    "FIXME",
    "NOT IMPLEMENTED",
    "NotImplementedError",
    "placeholder",
    "coming soon",
]

hits = []

for p in py_files:

    try:
        lines = p.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()

    except Exception:
        continue

    for number, line in enumerate(lines, 1):

        for pattern in patterns:

            if pattern.lower() in line.lower():

                hits.append(
                    (
                        str(p.relative_to(ROOT)),
                        number,
                        line.strip(),
                    )
                )

                break

for file, line, content in hits:

    print(
        f"{file}:{line} -> {content}"
    )

print(
    "\nPotential incomplete areas:",
    len(hits),
)


# ============================================================
# EXCEPTION HANDLING
# ============================================================

print("\n[6] EXCEPTION HANDLING")
print("-" * 80)

exception_hits = []

for p in py_files:

    try:
        lines = p.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()

    except Exception:
        continue

    for number, line in enumerate(lines, 1):

        stripped = line.strip()

        if (
            stripped.startswith("except")
            or "except Exception" in stripped
        ):

            exception_hits.append(
                (
                    str(p.relative_to(ROOT)),
                    number,
                    stripped,
                )
            )

for file, line, content in exception_hits:

    print(
        f"{file}:{line} -> {content}"
    )

print(
    "\nException handlers:",
    len(exception_hits),
)


# ============================================================
# DATABASE / MODEL FILES
# ============================================================

print("\n[7] DATABASE / MODEL FILES")
print("-" * 80)

model_files = []

for p in py_files:

    try:
        source = p.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    except Exception:
        continue

    if any(
        x in source
        for x in [
            "sqlalchemy",
            "DeclarativeBase",
            "declarative_base",
            "Column(",
            "mapped_column(",
        ]
    ):

        model_files.append(
            str(p.relative_to(ROOT))
        )

for f in sorted(set(model_files)):
    print(f)

print(
    "\nPotential model files:",
    len(set(model_files)),
)


# ============================================================
# DATASOURCE / CONNECTOR / SYNC
# ============================================================

print("\n[8] DATASOURCE / CONNECTOR / SYNC")
print("-" * 80)

keywords = [
    "datasource",
    "connector",
    "sync",
    "mapping",
    "schema",
    "scheduler",
    "worker",
    "queue",
    "redis",
]

matched = []

for p in py_files:

    name = str(
        p.relative_to(ROOT)
    ).lower()

    if any(
        keyword in name
        for keyword in keywords
    ):

        matched.append(name)

for f in sorted(matched):
    print(f)

print(
    "\nRelevant files:",
    len(matched),
)


# ============================================================
# KNOWLEDGE / RAG
# ============================================================

print("\n[9] KNOWLEDGE / RAG")
print("-" * 80)

knowledge_keywords = [
    "knowledge",
    "embedding",
    "vector",
    "hybrid",
    "search",
    "chunk",
    "ingest",
]

knowledge_files = []

for p in py_files:

    name = str(
        p.relative_to(ROOT)
    ).lower()

    if any(
        keyword in name
        for keyword in knowledge_keywords
    ):

        knowledge_files.append(name)

for f in sorted(knowledge_files):
    print(f)

print(
    "\nKnowledge files:",
    len(knowledge_files),
)


# ============================================================
# TESTS
# ============================================================

print("\n[10] TESTS")
print("-" * 80)

test_files = []

for p in py_files:

    name = p.name.lower()

    if (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in p.parts
    ):

        test_files.append(
            str(p.relative_to(ROOT))
        )

for f in sorted(test_files):
    print(f)

print(
    "\nTest files:",
    len(test_files),
)


# ============================================================
# ENVIRONMENT
# ============================================================

print("\n[11] ENVIRONMENT CONFIG")
print("-" * 80)

env_file = ROOT / ".env"

if env_file.exists():

    names = []

    for line in env_file.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():

        line = line.strip()

        if (
            line
            and not line.startswith("#")
            and "=" in line
        ):

            names.append(
                line.split("=", 1)[0].strip()
            )

    for name in sorted(names):
        print(name)

    print(
        "\n.env variables:",
        len(names),
    )

else:

    print(".env NOT FOUND")


# ============================================================
# GIT STATUS
# ============================================================

print("\n[12] GIT STATUS")
print("-" * 80)

if (ROOT / ".git").exists():

    try:

        result = subprocess.run(
            [
                "git",
                "status",
                "--short",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        if result.stdout.strip():

            print(result.stdout)

        else:

            print("Working tree clean.")

    except Exception as exc:

        print(
            "Git error:",
            repr(exc),
        )

else:

    print("Not a Git repository.")


# ============================================================
# DATABASE
# ============================================================

print("\n[13] DATABASE SNAPSHOT")
print("-" * 80)

try:

    from app.core.config import settings
    from sqlalchemy import create_engine, text

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    with engine.connect() as conn:

        row = conn.execute(
            text(
                """
                SELECT
                    current_database(),
                    current_user
                """
            )
        ).fetchone()

        print(
            "Database:",
            row[0],
        )

        print(
            "User:",
            row[1],
        )

        tables = conn.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
        ).scalars().all()

        for table in tables:

            try:

                count = conn.execute(
                    text(
                        f'SELECT COUNT(*) FROM "{table}"'
                    )
                ).scalar()

                print(
                    f"{table:40} rows={count}"
                )

            except Exception as exc:

                print(
                    f"{table:40} ERROR={exc}"
                )

        print("\nExtensions:")

        extensions = conn.execute(
            text(
                """
                SELECT extname
                FROM pg_extension
                ORDER BY extname
                """
            )
        ).scalars().all()

        for ext in extensions:
            print(" ", ext)

except Exception as exc:

    print(
        "Database audit failed:",
        repr(exc),
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)

print(
    "\nSend the COMPLETE output to me."
)

print(
    "I will classify every major system component as:"
)

print("  COMPLETE")
print("  PARTIAL")
print("  MISSING")
print("  PRODUCTION BLOCKER")
print("  SECURITY RISK")
print("  TEST GAP")

print("=" * 80)

