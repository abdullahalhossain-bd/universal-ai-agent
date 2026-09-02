from pathlib import Path

p = Path("app/connectors/postgresql.py")
print("=" * 70)
print(p)
print("=" * 70)
print(p.read_text(encoding="utf-8"))
