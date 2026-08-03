import argparse
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.load_env import load_env


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import the bundled Guilin tourism opinion sample data.")
    parser.add_argument(
        "--file",
        default="data/samples/tourism_opinion_seed.json",
        help="CSV, JSON, or JSONL source file.",
    )
    parser.add_argument(
        "--disable-llm-extraction",
        action="store_true",
        help="Use deterministic extraction rules for local smoke testing.",
    )
    args = parser.parse_args()

    if args.disable_llm_extraction:
        os.environ["TOURISM_EXTRACTION_LLM_ENABLED"] = "false"
    load_env()

    from services.tourism.pipeline_service import TourismPipelineService

    source = Path(args.file)
    if not source.exists():
        raise FileNotFoundError(source)
    file_data = SimpleNamespace(name=source.name, body=source.read_bytes())
    result = await TourismPipelineService().run_uploaded_file(
        file_data,
        source_type="sample_seed",
        created_by=1,
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
