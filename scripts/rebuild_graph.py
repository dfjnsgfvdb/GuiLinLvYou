import json
import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.load_env import load_env
from services.tourism.graph_service import GraphService


def main():
    parser = argparse.ArgumentParser(description="Rebuild Guilin tourism opinion Neo4j graph")
    parser.add_argument("--clear", action="store_true", help="clear existing tourism graph nodes and relationships before rebuild")
    args = parser.parse_args()
    load_env()
    result = GraphService().rebuild_graph_from_mysql(clear_existing=args.clear)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
