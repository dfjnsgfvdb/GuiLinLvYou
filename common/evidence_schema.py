from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RetrievalMode(str, Enum):
    VECTOR = "vector"
    VECTOR_BM25 = "vector_bm25"
    HYBRID_GRAPH = "hybrid_graph"


class EvidenceType(str, Enum):
    CHUNK = "chunk"
    DOCUMENT = "document"
    EVENT = "event"
    GRAPH_RELATION = "graph_relation"


@dataclass(slots=True)
class QueryContext:
    original_query: str
    normalized_query: str
    rewritten_query: str
    intent: str
    parameters: dict[str, Any] = field(default_factory=dict)
    expanded_queries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceCandidate:
    """A route-agnostic candidate carried through the enterprise RAG pipeline."""

    candidate_id: str
    evidence_type: str
    text: str
    doc_id: str | None = None
    chunk_id: str | None = None
    event_id: str | None = None
    graph_relation_id: str | None = None
    raw_scores: dict[str, float] = field(default_factory=dict)
    normalized_scores: dict[str, float] = field(default_factory=dict)
    hit_sources: list[str] = field(default_factory=list)
    fusion_score: float = 0.0
    rule_score: float = 0.0
    llm_score: float | None = None
    rerank_score: float = 0.0
    final_score: float = 0.0
    compressed_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, rank: int | None = None) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.final_score or self.rerank_score or self.fusion_score, 6)
        payload["quote_text"] = self.compressed_text or self.text
        payload["document"] = self.metadata.get("document")
        payload["events"] = self.metadata.get("events", [])
        if self.metadata.get("event") and not payload["events"]:
            payload["events"] = [self.metadata["event"]]
        if rank is not None:
            payload["rank"] = rank
            payload["evidence_id"] = f"E{rank}"
        return payload


@dataclass(slots=True)
class EvidencePackage:
    query_context: QueryContext
    retrieval_mode: str
    vector_version: str | None
    bm25_version: str | None
    candidates: list[EvidenceCandidate]
    graph: dict[str, Any]
    evidence: list[dict[str, Any]]
    sufficiency: dict[str, Any]
    metrics: dict[str, Any]
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        candidate_payloads = [item.to_dict(rank) for rank, item in enumerate(self.candidates, 1)]
        return {
            "query": self.query_context.original_query,
            "query_context": asdict(self.query_context),
            "retrieval": {
                "mode": self.retrieval_mode,
                "top_k": len(candidate_payloads),
                "vector_version": self.vector_version,
                "bm25_version": self.bm25_version,
                "sufficiency": self.sufficiency,
                "config": self.config,
                "candidates": candidate_payloads,
            },
            "graph": self.graph,
            "evidence": self.evidence,
            "metrics": self.metrics,
        }


class TourismMinioPrefix(str, Enum):
    RAW = "tourism/raw"
    CLEAN = "tourism/clean"
    FAILED = "tourism/failed"
    INDEX = "tourism/index"
    EXPORT = "tourism/export"


NEO4J_TOURISM_CONSTRAINTS = [
    "CREATE CONSTRAINT tourism_event_id IF NOT EXISTS FOR (n:Event) REQUIRE n.event_id IS UNIQUE",
    "CREATE CONSTRAINT tourism_spot_id IF NOT EXISTS FOR (n:ScenicSpot) REQUIRE n.spot_id IS UNIQUE",
    "CREATE CONSTRAINT tourism_location_id IF NOT EXISTS FOR (n:Location) REQUIRE n.location_id IS UNIQUE",
    "CREATE CONSTRAINT tourism_doc_id IF NOT EXISTS FOR (n:Document) REQUIRE n.doc_id IS UNIQUE",
    "CREATE CONSTRAINT tourism_source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE",
    "CREATE CONSTRAINT tourism_topic_id IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_id IS UNIQUE",
]


NEO4J_TOURISM_RELATIONSHIPS = [
    "REPORTS",
    "INVOLVES_SCENIC_SPOT",
    "OCCURRED_AT",
    "FROM_SOURCE",
    "BELONGS_TO_TOPIC",
    "RELATED_TO",
]


@dataclass(slots=True)
class QaEvidencePayload:
    chat_id: str
    uuid: str
    qa_type: str
    question: str
    retrieval_version: str
    retrieval_mode: RetrievalMode
    evidence_type: EvidenceType
    rank_no: int
    score: float | None = None
    qa_record_id: int | None = None
    doc_id: str | None = None
    chunk_id: str | None = None
    event_id: str | None = None
    graph_relation_id: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    quote_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def build_tourism_minio_key(prefix: TourismMinioPrefix, *parts: str) -> str:
    clean_parts = [str(part).strip("/") for part in parts if part]
    return "/".join([prefix.value, *clean_parts])
