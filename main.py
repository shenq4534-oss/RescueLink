import argparse
import json
from rescuelink.simulation.scenarios import level1, level2, showcase

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("scenario", choices=["level1","level2","showcase"], default="showcase", nargs="?")
    args=p.parse_args()
    print(json.dumps(globals()[args.scenario](), ensure_ascii=True, indent=2))
