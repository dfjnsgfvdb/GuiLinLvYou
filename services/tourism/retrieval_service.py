import json
import math
import os
import pickle
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from common.evidence_schema import EvidenceCandidate, EvidencePackage, EvidenceType, RetrievalMode
from common.minio_util import MinioUtils
from common.mysql_util import MysqlUtil
from services.tourism.graph_service import GraphService
from services.tourism.index_service import IndexService
from services.tourism.query_processor import TourismQueryProcessor
from services.tourism.rerank_service import EvidenceCompressor, RerankModelProvider, RuleLlmReranker


@dataclass
class TourismRetrievalFilters:
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    scenic_spot: Optional[str] = None
    location: Optional[str] = None
    event_type: Optional[str] = None


@dataclass
class RetrievalCandidate:
    chunk_id: str
    vector_score: float = 0.0
    bm25_score: float = 0.0
    graph_boost: float = 0.0
    fused_score: float = 0.0
    hit_sources: Optional[List[str]] = None


class TourismRetrievalService:
    """Hybrid retrieval service for tourism public-opinion QA.

    The service keeps Cypher out of LLM control: graph expansion delegates to
    GraphService, whose methods are fixed parameterized Cypher templates.
    """

    VECTOR_WEIGHT = 0.55
    BM25_WEIGHT = 0.35
    GRAPH_WEIGHT = 0.10

    def __init__(self, bucket_name: str = "filedata", rerank_provider: RerankModelProvider | None = None):
        self.bucket_name = bucket_name
        self.min_vector_score = float(os.getenv("TOURISM_MIN_VECTOR_SCORE", "0.45"))
        self.min_bm25_score = float(os.getenv("TOURISM_MIN_BM25_SCORE", "0.50"))
        self.final_context_top_k = max(1, int(os.getenv("FINAL_CONTEXT_TOP_K", "6")))
        self.vector_recall_top_k = max(
            self.final_context_top_k + 1, int(os.getenv("VECTOR_RECALL_TOP_K", "30"))
        )
        self.bm25_recall_top_k = max(
            self.final_context_top_k + 1, int(os.getenv("BM25_RECALL_TOP_K", "30"))
        )
        self.mysql_event_top_k = max(
            self.final_context_top_k + 1, int(os.getenv("MYSQL_EVENT_RECALL_TOP_K", "20"))
        )
        self.graph_expand_top_k = max(
            self.final_context_top_k + 1, int(os.getenv("GRAPH_EXPAND_TOP_K", "20"))
        )
        self.rerank_top_k = max(
            self.final_context_top_k, int(os.getenv("RERANK_TOP_K", "12"))
        )
        self.rerank_score_threshold = float(os.getenv("RERANK_SCORE_THRESHOLD", "0.35"))
        self.mysql = MysqlUtil()
        self.minio = MinioUtils()
        self.graph_service = GraphService()
        self.index_helper = IndexService()
        self.query_processor = TourismQueryProcessor()
        self.reranker = RuleLlmReranker(rerank_provider)
        self.compressor = EvidenceCompressor(int(os.getenv("EVIDENCE_COMPRESS_MAX_CHARS", "420")))

    def retrieve(
        self,
        query: str,
        filters: Optional[TourismRetrievalFilters] = None,
        top_k: int | None = None,
        mode: str = RetrievalMode.HYBRID_GRAPH.value,
        expand_graph: bool = True,
    ) -> Dict[str, Any]:
        """Execute the complete multi-route recall, rerank and context-selection pipeline."""

        started_at = time.time()
        filters = filters or TourismRetrievalFilters()
        normalized_mode = self._normalize_mode(mode)
        final_top_k = max(1, min(int(top_k or self.final_context_top_k), self.final_context_top_k))
        context = self.query_processor.process(query, filters)
        vector_version = self._load_active_index_version("faiss")
        bm25_version = self._load_active_index_version("bm25")
        pool: dict[str, EvidenceCandidate] = {}

        vector_hits = self._vector_search(
            context.rewritten_query, vector_version, self.vector_recall_top_k
        ) if normalized_mode in {
            RetrievalMode.VECTOR.value,
            RetrievalMode.VECTOR_BM25.value,
            RetrievalMode.HYBRID_GRAPH.value,
        } else []
        for chunk_id, score in vector_hits:
            self._merge_route_candidate(pool, self._chunk_candidate(chunk_id), "vector", score)

        expanded_query = " ".join(context.expanded_queries)
        bm25_hits = self._bm25_search(
            expanded_query, bm25_version, self.bm25_recall_top_k
        ) if normalized_mode in {RetrievalMode.VECTOR_BM25.value, RetrievalMode.HYBRID_GRAPH.value} else []
        for chunk_id, score in bm25_hits:
            self._merge_route_candidate(pool, self._chunk_candidate(chunk_id), "bm25", score)

        chunk_candidates = [item for item in pool.values() if item.chunk_id]
        metadata = self._load_candidate_metadata(chunk_candidates, filters)
        for candidate in list(chunk_candidates):
            item = metadata.get(candidate.chunk_id or "")
            if not item:
                pool.pop(candidate.candidate_id, None)
                continue
            candidate.text = item.get("content_preview") or ""
            candidate.doc_id = item.get("doc_id")
            candidate.event_id = item.get("event_id")
            candidate.metadata = item

        mysql_events = self._mysql_event_recall(context, self.mysql_event_top_k)
        for event in mysql_events:
            candidate = self._event_candidate(event)
            self._merge_route_candidate(pool, candidate, "mysql_event", float(event.pop("_route_score", 0)))

        graph_payload = {"nodes": [], "relationships": [], "paths": []}
        graph_candidates: list[EvidenceCandidate] = []
        if normalized_mode == RetrievalMode.HYBRID_GRAPH.value and expand_graph:
            graph_payload, graph_candidates = self._graph_recall(context, self.graph_expand_top_k)
            for rank, candidate in enumerate(graph_candidates, 1):
                graph_score = max(0.1, 1.0 - ((rank - 1) / max(self.graph_expand_top_k, 1)))
                self._merge_route_candidate(pool, candidate, "graph", graph_score)

        merged_candidates = self._deduplicate_candidates(list(pool.values()))
        self._normalize_route_scores(merged_candidates)
        self._coarse_fuse(merged_candidates)
        relevant_candidates = [item for item in merged_candidates if self._passes_enterprise_gate(item)]
        coarse_ranked = sorted(relevant_candidates, key=lambda item: item.fusion_score, reverse=True)
        rerank_input = coarse_ranked[: self.rerank_top_k]
        reranked = self.reranker.rerank(context, rerank_input)
        topk_truncated = [
            item for item in reranked[: self.rerank_top_k]
            if item.rerank_score >= self.rerank_score_threshold
        ]
        diversified = self._apply_diversity(topk_truncated, final_top_k)
        selected = self.compressor.compress(context, diversified)

        sufficiency = self._enterprise_sufficiency(selected, vector_version, bm25_version)
        evidence_items = self._build_final_evidence(selected)
        evidence_items.extend(self._build_graph_evidence(graph_payload))
        latency_ms = int((time.time() - started_at) * 1000)
        route_counts = {
            "faiss_vector": len(vector_hits),
            "bm25_keyword": len(bm25_hits),
            "mysql_event": len(mysql_events),
            "neo4j_graph": len(graph_candidates),
        }
        stage_counts = {
            "candidate_pool_merged": len(pool),
            "deduplicated": len(merged_candidates),
            "coarse_ranked": len(coarse_ranked),
            "rerank_input": len(rerank_input),
            "reranked": len(reranked),
            "topk_truncated": len(topk_truncated),
            "diversified": len(diversified),
            "compressed": len(selected),
        }
        config = self._retrieval_config(final_top_k)
        metrics = {
            "route_counts": route_counts,
            "stage_counts": stage_counts,
            "returned_count": len(selected),
            "graph_relation_count": len(graph_payload.get("relationships", [])),
            "latency_ms": latency_ms,
            "processing_stages": [
                "query_preprocess", "intent_detection", "parameter_extraction", "query_rewrite_expansion",
                "multi_route_recall", "candidate_pool_merge", "deduplication", "score_normalization",
                "coarse_fusion", "rerank", "topk_truncation", "diversity_control",
                "evidence_compression", "evidence_sufficiency_check",
            ],
            "evaluation_probe": {
                "retrieval_mode": normalized_mode,
                "ranked_candidate_ids": [item.candidate_id for item in selected],
                "ranked_chunk_ids": [item.chunk_id for item in selected if item.chunk_id],
                "ranked_doc_ids": [item.doc_id for item in selected if item.doc_id],
                "ranked_event_ids": [item.event_id for item in selected if item.event_id],
                "route_scores": {
                    item.candidate_id: {
                        "raw": item.raw_scores,
                        "normalized": item.normalized_scores,
                        "fusion": item.fusion_score,
                        "rule": item.rule_score,
                        "llm": item.llm_score,
                        "rerank": item.rerank_score,
                    }
                    for item in selected
                },
            },
        }
        package = EvidencePackage(
            query_context=context,
            retrieval_mode=normalized_mode,
            vector_version=self._version_name(vector_version),
            bm25_version=self._version_name(bm25_version),
            candidates=selected,
            graph=graph_payload,
            evidence=evidence_items,
            sufficiency=sufficiency,
            metrics=metrics,
            config=config,
        ).to_dict()
        package["retrieval"]["latency_ms"] = latency_ms
        return self._json_safe(package)

    @staticmethod
    def _chunk_candidate(chunk_id: str) -> EvidenceCandidate:
        return EvidenceCandidate(
            candidate_id=f"chunk:{chunk_id}",
            evidence_type=EvidenceType.CHUNK.value,
            text="",
            chunk_id=chunk_id,
        )

    @staticmethod
    def _event_candidate(event: Dict[str, Any]) -> EvidenceCandidate:
        event_id = str(event.get("event_id") or event.get("id") or "")
        text = " ".join(
            str(event.get(key) or "")
            for key in ["event_name", "event_summary", "topic", "main_scenic_spot", "main_location"]
        ).strip()
        return EvidenceCandidate(
            candidate_id=f"event:{event_id}",
            evidence_type=EvidenceType.EVENT.value,
            text=text,
            event_id=event_id or None,
            metadata={"event": event},
        )

    @staticmethod
    def _merge_route_candidate(
        pool: Dict[str, EvidenceCandidate],
        incoming: EvidenceCandidate,
        route: str,
        score: float,
    ) -> None:
        current = pool.get(incoming.candidate_id)
        if current is None:
            current = incoming
            pool[incoming.candidate_id] = current
        current.raw_scores[route] = max(current.raw_scores.get(route, 0.0), float(score))
        if route not in current.hit_sources:
            current.hit_sources.append(route)
        if incoming.text and not current.text:
            current.text = incoming.text
        if incoming.metadata:
            current.metadata.update(incoming.metadata)
        current.doc_id = current.doc_id or incoming.doc_id
        current.chunk_id = current.chunk_id or incoming.chunk_id
        current.event_id = current.event_id or incoming.event_id
        current.graph_relation_id = current.graph_relation_id or incoming.graph_relation_id

    @staticmethod
    def _deduplicate_candidates(candidates: List[EvidenceCandidate]) -> List[EvidenceCandidate]:
        deduplicated: Dict[str, EvidenceCandidate] = {}
        text_fingerprints: Dict[str, str] = {}
        for candidate in candidates:
            fingerprint = "".join(str(candidate.text or "").lower().split())[:500]
            identity = candidate.candidate_id
            if fingerprint and fingerprint in text_fingerprints:
                identity = text_fingerprints[fingerprint]
            else:
                text_fingerprints[fingerprint] = identity
            existing = deduplicated.get(identity)
            if existing is None:
                deduplicated[identity] = candidate
                continue
            for route, score in candidate.raw_scores.items():
                existing.raw_scores[route] = max(existing.raw_scores.get(route, 0.0), score)
            existing.hit_sources = list(dict.fromkeys([*existing.hit_sources, *candidate.hit_sources]))
        return list(deduplicated.values())

    @staticmethod
    def _normalize_route_scores(candidates: List[EvidenceCandidate]) -> None:
        routes = ["vector", "bm25", "mysql_event", "graph"]
        for route in routes:
            values = [item.raw_scores.get(route, 0.0) for item in candidates]
            nonzero = [value for value in values if value > 0]
            if not nonzero:
                continue
            minimum, maximum = min(nonzero), max(nonzero)
            for candidate in candidates:
                value = candidate.raw_scores.get(route, 0.0)
                if value <= 0:
                    candidate.normalized_scores[route] = 0.0
                elif maximum == minimum:
                    candidate.normalized_scores[route] = 1.0
                else:
                    candidate.normalized_scores[route] = (value - minimum) / (maximum - minimum)

    @staticmethod
    def _coarse_fuse(candidates: List[EvidenceCandidate]) -> None:
        weights = {"vector": 0.40, "bm25": 0.25, "mysql_event": 0.20, "graph": 0.15}
        for candidate in candidates:
            weighted = sum(
                weights[route] * candidate.normalized_scores.get(route, 0.0)
                for route in weights
            )
            route_bonus = min(max(len(candidate.hit_sources) - 1, 0) * 0.03, 0.09)
            candidate.fusion_score = min(weighted + route_bonus, 1.0)

    def _passes_enterprise_gate(self, candidate: EvidenceCandidate) -> bool:
        if not candidate.text:
            return False
        if candidate.raw_scores.get("mysql_event", 0) > 0 or candidate.raw_scores.get("graph", 0) > 0:
            return True
        return (
            candidate.raw_scores.get("vector", 0) >= self.min_vector_score
            or candidate.raw_scores.get("bm25", 0) >= self.min_bm25_score
        )

    @staticmethod
    def _apply_diversity(candidates: List[EvidenceCandidate], final_top_k: int) -> List[EvidenceCandidate]:
        selected: List[EvidenceCandidate] = []
        doc_counts: Dict[str, int] = {}
        event_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}
        for candidate in candidates:
            doc_key = candidate.doc_id or ""
            event_key = candidate.event_id or ""
            if doc_key and doc_counts.get(doc_key, 0) >= 2:
                continue
            if event_key and event_counts.get(event_key, 0) >= 2:
                continue
            if type_counts.get(candidate.evidence_type, 0) >= max(2, final_top_k - 1):
                continue
            selected.append(candidate)
            if doc_key:
                doc_counts[doc_key] = doc_counts.get(doc_key, 0) + 1
            if event_key:
                event_counts[event_key] = event_counts.get(event_key, 0) + 1
            type_counts[candidate.evidence_type] = type_counts.get(candidate.evidence_type, 0) + 1
            if len(selected) >= final_top_k:
                break
        return selected

    def _enterprise_sufficiency(
        self,
        candidates: List[EvidenceCandidate],
        vector_version: Optional[Dict[str, Any]],
        bm25_version: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        strong = [item for item in candidates if item.final_score >= self.rerank_score_threshold and item.compressed_text]
        route_coverage = len({route for item in strong for route in item.hit_sources})
        passed = bool(strong) and (route_coverage >= 2 or strong[0].final_score >= min(self.rerank_score_threshold + 0.2, 0.9))
        if passed:
            reason = "reranked_evidence_sufficient"
        elif not vector_version and not bm25_version and not candidates:
            reason = "no_active_index_or_structured_hits"
        elif candidates:
            reason = "insufficient_route_coverage_or_score"
        else:
            reason = "no_candidates_after_rerank"
        return {
            "passed": passed,
            "reason": reason,
            "strong_candidate_count": len(strong),
            "route_coverage": route_coverage,
            "rerank_score_threshold": self.rerank_score_threshold,
        }

    def _mysql_event_recall(self, context, top_n: int) -> List[Dict[str, Any]]:
        terms = list(dict.fromkeys([*context.keywords, *context.parameters.values()]))
        terms = [str(term).strip() for term in terms if len(str(term).strip()) >= 2][:10]
        if not terms:
            return []
        clauses = []
        params: List[Any] = []
        for term in terms:
            clauses.append(
                "CONCAT_WS(' ', event_name, event_summary, topic, main_scenic_spot, main_location) LIKE %s"
            )
            params.append(f"%{term}%")
        sql = f"""
            SELECT event_id, event_name, event_summary, topic, sentiment, risk_level,
                   heat_score, negative_ratio, growth_rate, first_seen_at, last_seen_at,
                   main_scenic_spot, main_location, source_count, document_count, status
            FROM t_tourism_event
            WHERE (status IS NULL OR status <> 'merged') AND ({' OR '.join(clauses)})
            ORDER BY heat_score DESC, last_seen_at DESC
            LIMIT %s
        """
        params.append(top_n)
        rows = self.mysql.query_mysql_dict_params(sql, tuple(params)) or []
        for row in rows:
            haystack = " ".join(str(value or "") for value in row.values()).lower()
            lexical = sum(1 for term in terms if term.lower() in haystack) / max(len(terms), 1)
            heat = min(float(row.get("heat_score") or 0) / 100.0, 1.0)
            row["_route_score"] = min(0.8 * lexical + 0.2 * heat, 1.0)
        return rows

    def _graph_recall(self, context, top_n: int) -> Tuple[Dict[str, Any], List[EvidenceCandidate]]:
        terms = list(dict.fromkeys([*context.keywords, *context.parameters.values()]))
        graph = self.graph_service.search_by_terms([str(item) for item in terms], top_n)
        candidates = []
        for node in graph.get("nodes", []):
            if "Event" not in (node.get("labels") or []):
                continue
            properties = node.get("properties") or {}
            event = {
                "event_id": properties.get("event_id"),
                "event_name": properties.get("name"),
                "event_summary": properties.get("summary"),
                "sentiment": properties.get("sentiment"),
                "risk_level": properties.get("risk_level"),
                "heat_score": properties.get("heat_score"),
            }
            if event["event_id"]:
                candidate = self._event_candidate(event)
                candidate.metadata["graph_node"] = node
                candidates.append(candidate)
        return graph, candidates[:top_n]

    def _build_final_evidence(self, candidates: List[EvidenceCandidate]) -> List[Dict[str, Any]]:
        evidence = []
        for rank, candidate in enumerate(candidates, 1):
            payload = candidate.to_dict(rank)
            evidence.append(
                {
                    "evidence_type": candidate.evidence_type,
                    "rank": rank,
                    "evidence_id": payload["evidence_id"],
                    "chunk_id": candidate.chunk_id,
                    "doc_id": candidate.doc_id,
                    "event_id": candidate.event_id,
                    "graph_relation_id": candidate.graph_relation_id,
                    "score": payload["score"],
                    "quote_text": payload["quote_text"],
                    "metadata": {
                        **candidate.metadata,
                        "hit_sources": candidate.hit_sources,
                        "raw_scores": candidate.raw_scores,
                        "normalized_scores": candidate.normalized_scores,
                        "fusion_score": candidate.fusion_score,
                        "rule_score": candidate.rule_score,
                        "llm_score": candidate.llm_score,
                        "rerank_score": candidate.rerank_score,
                    },
                }
            )
        return evidence

    def _retrieval_config(self, final_top_k: int) -> Dict[str, Any]:
        return {
            "VECTOR_RECALL_TOP_K": self.vector_recall_top_k,
            "BM25_RECALL_TOP_K": self.bm25_recall_top_k,
            "MYSQL_EVENT_RECALL_TOP_K": self.mysql_event_top_k,
            "GRAPH_EXPAND_TOP_K": self.graph_expand_top_k,
            "RERANK_TOP_K": self.rerank_top_k,
            "FINAL_CONTEXT_TOP_K": final_top_k,
            "RERANK_SCORE_THRESHOLD": self.rerank_score_threshold,
        }

    def save_evidence_package(
        self,
        qa_record_id: str,
        chat_id: str,
        uuid: str,
        qa_type: str,
        question: str,
        evidence_package: Dict[str, Any],
    ) -> int:
        """Persist evidence rows for answer traceability."""

        rows = []
        retrieval = evidence_package.get("retrieval", {})
        retrieval_mode = retrieval.get("mode", RetrievalMode.HYBRID_GRAPH.value)
        retrieval_version = self._join_versions(retrieval.get("vector_version"), retrieval.get("bm25_version"))
        for rank, item in enumerate(evidence_package.get("evidence", []), 1):
            metadata = item.get("metadata", {}) or {}
            document = metadata.get("document", {}) or {}
            rows.append(
                (
                    qa_record_id,
                    chat_id,
                    uuid,
                    qa_type,
                    question,
                    retrieval_version,
                    retrieval_mode,
                    item.get("evidence_type"),
                    item.get("doc_id"),
                    item.get("chunk_id"),
                    item.get("event_id"),
                    item.get("graph_relation_id"),
                    document.get("source_name"),
                    document.get("source_url"),
                    item.get("score"),
                    rank,
                    item.get("quote_text"),
                    json.dumps(self._json_safe(item.get("metadata", {})), ensure_ascii=False),
                )
            )

        if not rows:
            return 0

        sql = """
            INSERT INTO t_qa_evidence (
                qa_record_id, chat_id, uuid, qa_type, question, retrieval_version,
                retrieval_mode, evidence_type, doc_id, chunk_id, event_id,
                graph_relation_id, source_name, source_url, score, rank_no,
                quote_text, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        for row in rows:
            self.mysql.insert(sql, row)
        return len(rows)

    def save_retrieval_log(
        self,
        qa_record_id: int | None,
        chat_id: str | None,
        uuid: str | None,
        question: str,
        evidence_package: Dict[str, Any],
        answer_policy: str,
        citation_validation: Dict[str, Any] | None = None,
    ) -> int:
        context = evidence_package.get("query_context", {})
        retrieval = evidence_package.get("retrieval", {})
        metrics = evidence_package.get("metrics", {})
        return self.mysql.insert(
            """
            INSERT INTO t_tourism_retrieval_log
            (qa_record_id, chat_id, uuid, question, rewritten_query, intent,
             parameters_json, expansions_json, retrieval_config_json, route_counts_json,
             stage_counts_json, selected_candidates_json, latency_ms, answer_policy,
             citation_validation_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                qa_record_id,
                chat_id,
                uuid,
                question,
                context.get("rewritten_query"),
                context.get("intent"),
                json.dumps(self._json_safe(context.get("parameters", {})), ensure_ascii=False),
                json.dumps(self._json_safe(context.get("expanded_queries", [])), ensure_ascii=False),
                json.dumps(self._json_safe(retrieval.get("config", {})), ensure_ascii=False),
                json.dumps(self._json_safe(metrics.get("route_counts", {})), ensure_ascii=False),
                json.dumps(self._json_safe(metrics.get("stage_counts", {})), ensure_ascii=False),
                json.dumps(self._json_safe(retrieval.get("candidates", [])), ensure_ascii=False),
                int(metrics.get("latency_ms") or 0),
                answer_policy,
                json.dumps(self._json_safe(citation_validation or {}), ensure_ascii=False),
            ),
        )

    def _vector_search(self, query: str, version: Optional[Dict[str, Any]], top_n: int) -> List[Tuple[str, float]]:
        if not version:
            return []
        try:
            index_bytes = self._download_bytes(version.get("minio_index_key"))
            metadata = self._download_json(version.get("metadata_minio_key"))
            id_map = metadata.get("id_map", metadata)
            if not index_bytes or not id_map:
                return []

            query_vector = np.array([self.index_helper.embed_query(query)], dtype="float32")
            results: List[Tuple[str, float]] = []

            try:
                import faiss

                index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype=np.uint8))
                distances, indices = index.search(query_vector, min(top_n, len(id_map)))
                for distance, vector_id in zip(distances[0], indices[0]):
                    if vector_id < 0:
                        continue
                    chunk_id = self._mapped_chunk_id(id_map, int(vector_id))
                    if chunk_id:
                        results.append((chunk_id, float(distance)))
                return results
            except Exception:
                fallback = pickle.loads(index_bytes)
                vectors = np.array(fallback.get("vectors", []), dtype="float32")
                if vectors.size == 0:
                    return []
                scores = vectors @ query_vector[0]
                top_indices = np.argsort(scores)[::-1][:top_n]
                for vector_id in top_indices:
                    chunk_id = self._mapped_chunk_id(id_map, int(vector_id))
                    if chunk_id:
                        results.append((chunk_id, float(scores[int(vector_id)])))
                return results
        except Exception:
            return []

    def _bm25_search(self, query: str, version: Optional[Dict[str, Any]], top_n: int) -> List[Tuple[str, float]]:
        if not version:
            return []
        try:
            index_bytes = self._download_bytes(version.get("minio_index_key"))
            metadata = self._download_json(version.get("metadata_minio_key"))
            doc_map = metadata.get("doc_map", metadata)
            if not index_bytes or not doc_map:
                return []

            tokens = self.index_helper._tokenize(query)
            if not tokens:
                return []

            bm25 = pickle.loads(index_bytes)
            if hasattr(bm25, "get_scores"):
                scores = np.array(bm25.get_scores(tokens), dtype="float32")
            else:
                token_set = set(tokens)
                corpus_tokens = bm25.get("corpus", [])
                scores = np.array([len(token_set.intersection(set(doc_tokens))) for doc_tokens in corpus_tokens], dtype="float32")

            top_indices = np.argsort(scores)[::-1][:top_n]
            results = []
            for doc_index in top_indices:
                score = float(scores[int(doc_index)])
                if score <= 0:
                    continue
                chunk_id = self._mapped_chunk_id(doc_map, int(doc_index))
                if chunk_id:
                    results.append((chunk_id, score))
            return results
        except Exception:
            return []

    def _load_candidate_metadata(
        self,
        candidates: List[RetrievalCandidate],
        filters: TourismRetrievalFilters,
    ) -> Dict[str, Dict[str, Any]]:
        chunk_ids = [item.chunk_id for item in candidates]
        if not chunk_ids:
            return {}

        placeholders = ", ".join(["%s"] * len(chunk_ids))
        where_clauses = [f"c.chunk_id IN ({placeholders})"]
        params: List[Any] = list(chunk_ids)

        if filters.start_time:
            where_clauses.append("d.publish_time >= %s")
            params.append(filters.start_time)
        if filters.end_time:
            where_clauses.append("d.publish_time <= %s")
            params.append(filters.end_time)
        if filters.source_name:
            where_clauses.append("d.source_name = %s")
            params.append(filters.source_name)
        if filters.source_type:
            where_clauses.append("d.source_type = %s")
            params.append(filters.source_type)
        if filters.scenic_spot:
            where_clauses.append("e.main_scenic_spot = %s")
            params.append(filters.scenic_spot)
        if filters.location:
            where_clauses.append("e.main_location = %s")
            params.append(filters.location)
        if filters.event_type:
            where_clauses.append("(e.topic = %s OR e.event_name LIKE %s)")
            params.extend([filters.event_type, f"%{filters.event_type}%"])

        sql = f"""
            SELECT
                c.chunk_id, c.doc_id, c.content_preview, c.index_version,
                d.title, d.source_type, d.source_name, d.source_url, d.publish_time,
                d.sentiment AS document_sentiment, d.sentiment_score AS document_sentiment_score,
                e.event_id, e.event_name, e.event_summary, e.topic, e.risk_level,
                e.heat_score, e.main_scenic_spot, e.main_location
            FROM t_tourism_chunk c
            JOIN t_tourism_document d ON c.doc_id = d.doc_id
            LEFT JOIN t_tourism_event_document ed ON d.doc_id = ed.doc_id
            LEFT JOIN t_tourism_event e ON ed.event_id = e.event_id
            WHERE {" AND ".join(where_clauses)}
        """
        rows = self.mysql.query_mysql_dict_params(sql, tuple(params)) or []

        metadata: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            chunk_id = row.get("chunk_id")
            item = metadata.setdefault(
                chunk_id,
                {
                    "chunk_id": chunk_id,
                    "doc_id": row.get("doc_id"),
                    "content_preview": row.get("content_preview"),
                    "index_version": row.get("index_version"),
                    "document": {
                        "doc_id": row.get("doc_id"),
                        "title": row.get("title"),
                        "source_type": row.get("source_type"),
                        "source_name": row.get("source_name"),
                        "source_url": row.get("source_url"),
                        "publish_time": self._format_datetime(row.get("publish_time")),
                        "sentiment": row.get("document_sentiment"),
                        "sentiment_score": row.get("document_sentiment_score"),
                    },
                    "events": [],
                    "event_id": None,
                    "scenic_spot": None,
                    "location": None,
                },
            )
            if row.get("event_id"):
                event_payload = {
                    "event_id": row.get("event_id"),
                    "event_name": row.get("event_name"),
                    "event_summary": row.get("event_summary"),
                    "topic": row.get("topic"),
                    "risk_level": row.get("risk_level"),
                    "heat_score": row.get("heat_score"),
                    "main_scenic_spot": row.get("main_scenic_spot"),
                    "main_location": row.get("main_location"),
                }
                if event_payload not in item["events"]:
                    item["events"].append(event_payload)
                item["event_id"] = item["event_id"] or row.get("event_id")
                item["scenic_spot"] = item["scenic_spot"] or row.get("main_scenic_spot")
                item["location"] = item["location"] or row.get("main_location")
        return metadata

    def _expand_graph(
        self,
        metadata: Dict[str, Dict[str, Any]],
        candidates: List[RetrievalCandidate],
    ) -> Dict[str, Any]:
        merged = {"nodes": [], "relationships": [], "paths": []}
        seen_events = set()
        seen_spots = set()
        seen_locations = set()

        for candidate in candidates:
            item = metadata.get(candidate.chunk_id, {})
            event_id = item.get("event_id")
            scenic_spot = item.get("scenic_spot")
            location = item.get("location")
            if event_id and event_id not in seen_events:
                self._merge_graph_payload(merged, self.graph_service.query_event_relations(event_id, hop=2, limit=50))
                seen_events.add(event_id)
            if scenic_spot and scenic_spot not in seen_spots:
                self._merge_graph_payload(merged, self.graph_service.query_by_scenic_spot(scenic_spot, hop=1, limit=50))
                seen_spots.add(scenic_spot)
            if location and location not in seen_locations:
                self._merge_graph_payload(merged, self.graph_service.query_by_location(location, hop=1, limit=50))
                seen_locations.add(location)
        return merged

    def _normalize_and_fuse(self, candidates: List[RetrievalCandidate], use_graph: bool) -> None:
        max_vector = max([item.vector_score for item in candidates], default=0.0)
        max_bm25 = max([item.bm25_score for item in candidates], default=0.0)

        for item in candidates:
            vector_norm = item.vector_score / max_vector if max_vector > 0 else 0.0
            bm25_norm = item.bm25_score / max_bm25 if max_bm25 > 0 else 0.0
            graph_norm = item.graph_boost if use_graph else 0.0
            item.fused_score = (
                self.VECTOR_WEIGHT * vector_norm
                + self.BM25_WEIGHT * bm25_norm
                + self.GRAPH_WEIGHT * graph_norm
            )
            if item.fused_score == 0 and (item.vector_score > 0 or item.bm25_score > 0):
                item.fused_score = max(vector_norm, bm25_norm)

    def _passes_relevance_gate(self, candidate: RetrievalCandidate) -> bool:
        return (
            candidate.vector_score >= self.min_vector_score
            or candidate.bm25_score >= self.min_bm25_score
        )

    @staticmethod
    def _sufficiency_reason(
        selected: List[RetrievalCandidate],
        vector_version: Optional[Dict[str, Any]],
        bm25_version: Optional[Dict[str, Any]],
        raw_candidate_count: int,
    ) -> str:
        if selected:
            return "relevant_candidates_found"
        if not vector_version and not bm25_version:
            return "no_active_index"
        if raw_candidate_count:
            return "candidates_below_relevance_threshold"
        return "no_retrieval_hits"

    def _build_candidate_evidence(
        self,
        candidates: List[RetrievalCandidate],
        metadata: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        evidence = []
        for rank, candidate in enumerate(candidates, 1):
            meta = metadata.get(candidate.chunk_id, {})
            evidence.append(
                {
                    "evidence_type": EvidenceType.CHUNK.value,
                    "rank": rank,
                    "chunk_id": candidate.chunk_id,
                    "doc_id": meta.get("doc_id"),
                    "event_id": meta.get("event_id"),
                    "score": round(candidate.fused_score, 6),
                    "quote_text": meta.get("content_preview"),
                    "metadata": {
                        "document": meta.get("document"),
                        "events": meta.get("events", []),
                        "hit_sources": candidate.hit_sources or [],
                        "route_scores": {
                            "vector": candidate.vector_score,
                            "bm25": candidate.bm25_score,
                            "graph_boost": candidate.graph_boost,
                        },
                    },
                }
            )
            for event in meta.get("events", []):
                evidence.append(
                    {
                        "evidence_type": EvidenceType.EVENT.value,
                        "rank": rank,
                        "chunk_id": candidate.chunk_id,
                        "doc_id": meta.get("doc_id"),
                        "event_id": event.get("event_id"),
                        "score": round(candidate.fused_score, 6),
                        "quote_text": event.get("event_summary"),
                        "metadata": event,
                    }
                )
        return evidence

    def _build_graph_evidence(self, graph_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence = []
        for rank, rel in enumerate(graph_payload.get("relationships", []), 1):
            evidence.append(
                {
                    "evidence_type": EvidenceType.GRAPH_RELATION.value,
                    "rank": rank,
                    "graph_relation_id": rel.get("id"),
                    "score": 1.0,
                    "quote_text": rel.get("type"),
                    "metadata": rel,
                }
            )
        return evidence

    def _candidate_payload(
        self,
        candidate: RetrievalCandidate,
        metadata: Dict[str, Any],
        rank: int,
    ) -> Dict[str, Any]:
        return {
            "rank": rank,
            "chunk_id": candidate.chunk_id,
            "doc_id": metadata.get("doc_id"),
            "event_id": metadata.get("event_id"),
            "score": round(candidate.fused_score, 6),
            "scores": {
                "vector": candidate.vector_score,
                "bm25": candidate.bm25_score,
                "graph_boost": candidate.graph_boost,
            },
            "hit_sources": candidate.hit_sources or [],
            "quote_text": metadata.get("content_preview"),
            "document": metadata.get("document"),
            "events": metadata.get("events", []),
        }

    def _load_active_index_version(self, index_type: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT *
            FROM t_tourism_index_version
            WHERE index_type = %s AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """
        rows = self.mysql.query_mysql_dict_params(sql, (index_type,)) or []
        return rows[0] if rows else None

    def _download_bytes(self, key: Optional[str]) -> Optional[bytes]:
        if not key:
            return None
        response = None
        try:
            response = self.minio.client.get_object(self.bucket_name, key)
            return response.read()
        finally:
            if response:
                response.close()
                response.release_conn()

    def _download_json(self, key: Optional[str]) -> Dict[str, Any]:
        data = self._download_bytes(key)
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))

    def _merge_graph_payload(self, merged: Dict[str, Any], payload: Dict[str, Any]) -> None:
        node_ids = {node.get("id") for node in merged.get("nodes", [])}
        rel_ids = {rel.get("id") for rel in merged.get("relationships", [])}

        for node in payload.get("nodes", []):
            node_id = node.get("id")
            if node_id not in node_ids:
                merged["nodes"].append(node)
                node_ids.add(node_id)
        for rel in payload.get("relationships", []):
            rel_id = rel.get("id")
            if rel_id not in rel_ids:
                merged["relationships"].append(rel)
                rel_ids.add(rel_id)
        merged["paths"].extend(payload.get("paths", []))

    def _normalize_mode(self, mode: str) -> str:
        if mode in {RetrievalMode.VECTOR.value, RetrievalMode.VECTOR_BM25.value, RetrievalMode.HYBRID_GRAPH.value}:
            return mode
        return RetrievalMode.HYBRID_GRAPH.value

    def _version_name(self, version: Optional[Dict[str, Any]]) -> Optional[str]:
        return version.get("index_version") if version else None

    def _join_versions(self, vector_version: Optional[str], bm25_version: Optional[str]) -> Optional[str]:
        versions = [item for item in [vector_version, bm25_version] if item]
        return "+".join(versions) if versions else None

    def _append_source(self, sources: Optional[List[str]], source: str) -> List[str]:
        sources = list(sources or [])
        if source not in sources:
            sources.append(source)
        return sources

    def _mapped_chunk_id(self, id_map: Any, index: int) -> Optional[str]:
        if isinstance(id_map, dict):
            value = id_map.get(str(index)) or id_map.get(index)
        elif isinstance(id_map, list) and index < len(id_map):
            value = id_map[index]
        else:
            value = None
        if isinstance(value, dict):
            return value.get("chunk_id")
        return value

    def _format_datetime(self, value: Any) -> Optional[str]:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    def _json_safe(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {key: self._json_safe(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._json_safe(value) for value in payload]
        if isinstance(payload, (datetime, date)):
            return payload.isoformat()
        if isinstance(payload, Decimal):
            return float(payload)
        if isinstance(payload, float) and (math.isnan(payload) or math.isinf(payload)):
            return None
        if hasattr(payload, "iso_format"):
            return payload.iso_format()
        if hasattr(payload, "isoformat"):
            return payload.isoformat()
        if payload is None or isinstance(payload, (str, int, float, bool)):
            return payload
        return str(payload)
