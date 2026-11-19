import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from rescuelink.simulation.scenarios import level2

if __name__ == "__main__":
    r=level2()
    print(json.dumps(r, ensure_ascii=True, indent=2))
    sys.exit(0 if r["delivered"] == 3 and not r["failed"] else 1)
