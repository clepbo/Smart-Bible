"""Entry point for the packaged Windows app (PyInstaller) and `python smartbible_app.py`.

`SmartBible.exe --self-test report.json` runs a few offline searches without
opening a window and writes the results to report.json (used by CI).
"""

import json
import sys


def self_test(report_path: str) -> int:
    from smartbible.engine import build_engine

    engine = build_engine()
    engine.warm_up()
    checks = {
        "john 3 16": "John 3:16",
        "the prodigal son": "Luke 15:11-32",
        "love is patient": "1 Corinthians 13:4-7",
        "God has good plans for my future": "Jeremiah 29:11",
    }
    report = {"semantic_ready": bool(engine.semantic and engine.semantic.ready), "queries": {}}
    ok = report["semantic_ready"]
    for query, expected in checks.items():
        top = [r.ref.display() for r in engine.search(query)[:5]]
        report["queries"][query] = top
        ok = ok and expected in top
    report["ok"] = ok
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        sys.exit(self_test(sys.argv[2]))
    from smartbible.ui import main

    sys.exit(main())
