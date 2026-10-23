"""Infrastructure smoke example. This is not a research experiment."""
import json
from pathlib import Path
from toy_evaluator import sum_of_squares

result = {"kind": "infrastructure_smoke", "n": 1000, "sum_of_squares": sum_of_squares(1000)}
Path("toy_metrics.json").write_text(json.dumps(result), encoding="utf-8")
print("Computed deterministic arithmetic; no scientific claim tested.")
