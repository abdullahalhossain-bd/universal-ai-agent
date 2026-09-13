from pathlib import Path

files = [
    "app/query_engine/executor.py",
    "app/query_engine/tools/base.py",
    "app/query_engine/tools/product_search.py",
    "app/query_engine/tools/stock_tool.py",
    "app/query_engine/tools/knowledge_search.py",
    "app/query_engine/intent.py",
    "app/query_engine/planner.py",
    "app/query_engine/composer.py"
]

for name in files:
    p = Path(name)
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)
    print(p.read_text(encoding="utf-8"))
