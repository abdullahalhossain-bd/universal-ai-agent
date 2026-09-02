from pathlib import Path

for name in [
    "app/vision/vision_router.py",
    "app/vision/vision_cache.py",
    "app/query_engine/tools/image_analysis.py"
]:
    p = Path(name)
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)
    print(p.read_text(encoding="utf-8"))
