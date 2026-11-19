import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from rescuelink.simulation.scenarios import level1

if __name__ == "__main__":
    results = [level1(d, n) for d in (b"", b"Hello", "应急通信".encode(), bytes(range(256)), "长消息分片".encode()*100) for n in (0,.25)]
    p = Path("outputs/level1")
    p.mkdir(parents=True, exist_ok=True)
    (p/"results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(dict(cases=len(results), passed=sum(r["success"] for r in results), max_fragments=max(r["fragments"] for r in results)),indent=2))
    if not all(r["success"] for r in results):
        sys.exit(1)
