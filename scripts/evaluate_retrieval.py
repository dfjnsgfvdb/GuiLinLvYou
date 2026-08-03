import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MODE_ALIASES = {
    "vector_only": "vector",
    "vector": "vector",
    "vector_bm25": "vector_bm25",
    "vector_bm25_graph": "hybrid_graph",
    "hybrid_graph": "hybrid_graph",
}


@dataclass
class QueryMetric:
    question: str
    mode: str
    recall_at_5: float
    recall_at_10: float
    mrr: float
    latency_ms: int
    hit_at_5: bool
    hit_at_10: bool
    ranked_chunk_ids: list[str]
    ranked_document_ids: list[str]
    ranked_event_ids: list[str]


def load_testset(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"评估集不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("评估集格式错误：根节点必须是数组")
    if not data:
        raise ValueError(f"评估集为空: {path}。请先补充真实 question 和 gold_*_ids，不能伪造结果。")
    for index, item in enumerate(data, 1):
        required_keys = ["question", "gold_document_ids", "gold_chunk_ids", "gold_event_ids"]
        missing_keys = [key for key in required_keys if key not in item]
        if missing_keys:
            raise ValueError(f"第 {index} 条缺少字段: {', '.join(missing_keys)}")
        if not item.get("question"):
            raise ValueError(f"第 {index} 条缺少 question")
        for key in ["gold_document_ids", "gold_chunk_ids", "gold_event_ids"]:
            if not isinstance(item.get(key), list):
                raise ValueError(f"第 {index} 条 {key} 必须是数组")
        if not any(item.get(key) for key in ["gold_document_ids", "gold_chunk_ids", "gold_event_ids"]):
            raise ValueError(f"第 {index} 条至少需要一个 gold_document_ids/gold_chunk_ids/gold_event_ids")
    return data


def normalize_modes(raw_modes: list[str]) -> list[tuple[str, str]]:
    modes = []
    for raw_mode in raw_modes:
        if raw_mode not in MODE_ALIASES:
            supported = ", ".join(MODE_ALIASES)
            raise ValueError(f"不支持的检索模式: {raw_mode}。可选: {supported}")
        modes.append((raw_mode, MODE_ALIASES[raw_mode]))
    return modes


def assert_indexes_available(service: Any, modes: list[tuple[str, str]]) -> None:
    needs_faiss = any(mode in {"vector", "vector_bm25", "hybrid_graph"} for _, mode in modes)
    needs_bm25 = any(mode in {"vector_bm25", "hybrid_graph"} for _, mode in modes)
    if needs_faiss and not service._load_active_index_version("faiss"):
        raise RuntimeError("缺少 active FAISS 索引版本，请先在“数据处理链路”中重建索引。")
    if needs_bm25 and not service._load_active_index_version("bm25"):
        raise RuntimeError("缺少 active BM25 索引版本，请先在“数据处理链路”中重建索引。")


def as_str_set(values: Any) -> set[str]:
    if not values:
        return set()
    if not isinstance(values, list):
        values = [values]
    return {str(value) for value in values if value is not None and str(value)}


def ranked_probe_ids(package: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    probe = package.get("metrics", {}).get("evaluation_probe", {})
    chunk_ids = [str(item) for item in probe.get("ranked_chunk_ids", []) if item]
    doc_ids = [str(item) for item in probe.get("ranked_doc_ids", []) if item]
    event_ids = [str(item) for item in probe.get("ranked_event_ids", []) if item]
    return chunk_ids, doc_ids, event_ids


def hit_count_at_k(test_item: dict[str, Any], chunk_ids: list[str], doc_ids: list[str], event_ids: list[str], k: int) -> tuple[int, int]:
    gold_chunks = as_str_set(test_item.get("gold_chunk_ids"))
    gold_docs = as_str_set(test_item.get("gold_document_ids"))
    gold_events = as_str_set(test_item.get("gold_event_ids"))
    total = len(gold_chunks) + len(gold_docs) + len(gold_events)
    hits = 0
    hits += len(gold_chunks.intersection(chunk_ids[:k]))
    hits += len(gold_docs.intersection(doc_ids[:k]))
    hits += len(gold_events.intersection(event_ids[:k]))
    return hits, total


def first_hit_rank(test_item: dict[str, Any], chunk_ids: list[str], doc_ids: list[str], event_ids: list[str]) -> int | None:
    gold_chunks = as_str_set(test_item.get("gold_chunk_ids"))
    gold_docs = as_str_set(test_item.get("gold_document_ids"))
    gold_events = as_str_set(test_item.get("gold_event_ids"))
    max_rank = max(len(chunk_ids), len(doc_ids), len(event_ids))
    for rank in range(1, max_rank + 1):
        chunk_hit = rank <= len(chunk_ids) and chunk_ids[rank - 1] in gold_chunks
        doc_hit = rank <= len(doc_ids) and doc_ids[rank - 1] in gold_docs
        event_hit = rank <= len(event_ids) and event_ids[rank - 1] in gold_events
        if chunk_hit or doc_hit or event_hit:
            return rank
    return None


def evaluate_query(service: Any, test_item: dict[str, Any], display_mode: str, service_mode: str, top_k: int) -> QueryMetric:
    started = time.perf_counter()
    package = service.retrieve(query=test_item["question"], top_k=top_k, mode=service_mode, expand_graph=service_mode == "hybrid_graph")
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    latency_ms = int(package.get("metrics", {}).get("latency_ms") or elapsed_ms)
    chunk_ids, doc_ids, event_ids = ranked_probe_ids(package)

    hits5, total = hit_count_at_k(test_item, chunk_ids, doc_ids, event_ids, 5)
    hits10, _ = hit_count_at_k(test_item, chunk_ids, doc_ids, event_ids, 10)
    rank = first_hit_rank(test_item, chunk_ids, doc_ids, event_ids)
    return QueryMetric(
        question=test_item["question"],
        mode=display_mode,
        recall_at_5=hits5 / total if total else 0.0,
        recall_at_10=hits10 / total if total else 0.0,
        mrr=1.0 / rank if rank else 0.0,
        latency_ms=latency_ms,
        hit_at_5=hits5 > 0,
        hit_at_10=hits10 > 0,
        ranked_chunk_ids=chunk_ids,
        ranked_document_ids=doc_ids,
        ranked_event_ids=event_ids,
    )


def summarize(metrics: list[QueryMetric]) -> dict[str, dict[str, float]]:
    modes = sorted({item.mode for item in metrics})
    summary = {}
    for mode in modes:
        rows = [item for item in metrics if item.mode == mode]
        summary[mode] = {
            "question_count": float(len(rows)),
            "recall@5": mean(item.recall_at_5 for item in rows),
            "recall@10": mean(item.recall_at_10 for item in rows),
            "hit_rate@5": mean(1.0 if item.hit_at_5 else 0.0 for item in rows),
            "hit_rate@10": mean(1.0 if item.hit_at_10 else 0.0 for item in rows),
            "mrr": mean(item.mrr for item in rows),
            "avg_latency_ms": mean(item.latency_ms for item in rows),
        }
    return summary


def lift_percent(base: float, candidate: float) -> str:
    if base <= 0:
        return "N/A"
    return f"{((candidate - base) / base) * 100:.2f}%"


def add_lift_metrics(summary: dict[str, dict[str, float]]) -> dict[str, dict[str, float | str]]:
    enriched: dict[str, dict[str, float | str]] = {mode: dict(values) for mode, values in summary.items()}
    base = summary.get("vector_only") or summary.get("vector")
    if not base:
        return enriched
    for mode, values in enriched.items():
        if mode in {"vector_only", "vector"}:
            values["recall@5_lift_vs_vector_only"] = "-"
            values["recall@10_lift_vs_vector_only"] = "-"
            values["mrr_lift_vs_vector_only"] = "-"
        else:
            values["recall@5_lift_vs_vector_only"] = lift_percent(float(base["recall@5"]), float(values["recall@5"]))
            values["recall@10_lift_vs_vector_only"] = lift_percent(float(base["recall@10"]), float(values["recall@10"]))
            values["mrr_lift_vs_vector_only"] = lift_percent(float(base["mrr"]), float(values["mrr"]))
    return enriched


def write_csv(path: Path, metrics: list[QueryMetric]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "mode",
            "question",
            "recall@5",
            "recall@10",
            "hit@5",
            "hit@10",
            "mrr",
            "latency_ms",
            "ranked_chunk_ids",
            "ranked_document_ids",
            "ranked_event_ids",
        ])
        for item in metrics:
            writer.writerow([
                item.mode,
                item.question,
                f"{item.recall_at_5:.6f}",
                f"{item.recall_at_10:.6f}",
                int(item.hit_at_5),
                int(item.hit_at_10),
                f"{item.mrr:.6f}",
                item.latency_ms,
                "|".join(item.ranked_chunk_ids),
                "|".join(item.ranked_document_ids),
                "|".join(item.ranked_event_ids),
            ])


def write_markdown(path: Path, summary: dict[str, dict[str, float | str]], modes: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 桂林旅游舆情问答检索评估报告",
        "",
        "本报告由真实评估集和当前索引运行生成；脚本不会填充或伪造 gold id。",
        "",
        "| mode | questions | Recall@5 | Recall@10 | Hit@5 | Hit@10 | MRR | Avg Latency(ms) | Recall@5 Lift | Recall@10 Lift | MRR Lift |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in modes:
        item = summary[mode]
        lines.append(
            f"| {mode} | {int(float(item['question_count']))} | {float(item['recall@5']):.4f} | {float(item['recall@10']):.4f} | "
            f"{float(item['hit_rate@5']):.4f} | {float(item['hit_rate@10']):.4f} | {float(item['mrr']):.4f} | "
            f"{float(item['avg_latency_ms']):.2f} | {item.get('recall@5_lift_vs_vector_only', '-')} | "
            f"{item.get('recall@10_lift_vs_vector_only', '-')} | {item.get('mrr_lift_vs_vector_only', '-')} |"
        )
    lines.extend(
        [
            "",
            "## 指标说明",
            "",
            "- `Recall@5/10`：按 gold_document_ids、gold_chunk_ids、gold_event_ids 的命中比例计算，再对问题取均值。",
            "- `Hit@5/10`：该问题在 TopK 内是否至少命中一个 gold id。",
            "- `MRR`：第一个 gold id 命中的倒数排名。",
            "- `Lift`：相对 `vector_only` 的提升百分比，用于支撑“混合检索较纯向量检索提升”的量化表述；只有真实测试集和索引存在时才有意义。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate tourism QA retrieval modes.")
    parser.add_argument("--testset", default=str(ROOT_DIR / "data" / "evaluation" / "tourism_qa_test.json"))
    parser.add_argument("--out-dir", default=str(ROOT_DIR / "data" / "evaluation" / "reports"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--modes", nargs="+", default=["vector_only", "vector_bm25", "vector_bm25_graph"])
    args = parser.parse_args()

    tests = load_testset(Path(args.testset))
    modes = normalize_modes(args.modes)
    top_k = max(args.top_k, 10)

    from config.load_env import load_env
    from services.tourism.retrieval_service import TourismRetrievalService

    load_env()
    service = TourismRetrievalService()
    assert_indexes_available(service, modes)

    metrics: list[QueryMetric] = []
    for display_mode, service_mode in modes:
        for test_item in tests:
            metrics.append(evaluate_query(service, test_item, display_mode, service_mode, top_k))

    summary = add_lift_metrics(summarize(metrics))
    out_dir = Path(args.out_dir)
    write_csv(out_dir / "retrieval_eval_detail.csv", metrics)
    write_markdown(out_dir / "retrieval_eval_report.md", summary, [mode for mode, _ in modes])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"报告已生成: {out_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
