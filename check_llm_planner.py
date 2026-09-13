from pathlib import Path

files = [
    "app/ai/router.py",
    "app/ai/provider_router.py",
    "app/ai/llm_planner.py",
    "app/planner/llm_planner.py",
    "app/planner/rule_planner.py",
    "app/planner/simple_planner.py",
    "app/llm/router.py"
]

for name in files:
    p = Path(name)
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)
    print(p.read_text(encoding="utf-8"))
