import io
import json
import pickle
from datetime import datetime

import numpy as np

from common.embedding_service import EmbeddingService
from common.evidence_schema import TourismMinioPrefix, build_tourism_minio_key
from common.minio_util import MinioUtils
from common.mysql_util import MysqlUtil
from services.tourism.schemas import TourismChunk, TourismDocument, TourismEvent


class IndexService:
    def __init__(self, vector_dim: int | None = None):
        self.embedding_service = EmbeddingService()
        self.vector_dim = vector_dim or self.embedding_service.fallback_dim
        self.minio = MinioUtils()
        self.mysql = MysqlUtil()

    @staticmethod
    def new_index_version() -> str:
        return f"idx_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def build_indexes(
        self,
        chunks: list[TourismChunk],
        documents: list[TourismDocument],
        events: list[TourismEvent],
        task_no: str,
        bucket_name: str = "filedata",
    ) -> str:
        index_version = self.new_index_version()
        faiss_key, id_map_key, vector_dim = self._build_faiss(chunks, index_version, task_no, bucket_name)
        bm25_key, doc_map_key = self._build_bm25(chunks, index_version, task_no, bucket_name)
        self._save_index_version(index_version, "faiss", faiss_key, id_map_key, len(chunks), len(documents), len(events), vector_dim)
        self._save_index_version(index_version, "bm25", bm25_key, doc_map_key, len(chunks), len(documents), len(events), vector_dim)
        self._update_chunk_index_mapping(chunks, index_version)
        for doc in documents:
            self.mysql.update_params(
                "UPDATE t_tourism_document SET index_status=%s, update_time=NOW() WHERE doc_id=%s",
                ("success", doc.doc_id),
            )
        return index_version

    def rebuild_indexes_from_mysql(self, task_no: str = "manual_rebuild", bucket_name: str = "filedata") -> dict:
        chunk_rows = self.mysql.query_mysql_dict(
            """
            SELECT chunk_id, doc_id, chunk_index, content_hash, content_preview, token_count, char_count
            FROM t_tourism_chunk
            ORDER BY id ASC
            """
        )
        document_rows = self.mysql.query_mysql_dict(
            """
            SELECT doc_id, title, source_type, source_name, source_url, publish_time,
                   raw_minio_key, clean_minio_key, content_hash, sentiment, sentiment_score
            FROM t_tourism_document
            ORDER BY id ASC
            """
        )
        event_rows = self.mysql.query_mysql_dict(
            """
            SELECT event_id, event_name, event_summary, topic, sentiment, risk_level, heat_score,
                   negative_ratio, growth_rate, first_seen_at, last_seen_at, main_scenic_spot,
                   main_location, source_count, document_count
            FROM t_tourism_event
            WHERE status IS NULL OR status <> 'merged'
            ORDER BY id ASC
            """
        )

        chunks = [
            TourismChunk(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                chunk_index=int(row.get("chunk_index") or 0),
                content=row.get("content_preview") or "",
                content_hash=row.get("content_hash") or "",
                token_count=int(row.get("token_count") or 0),
                char_count=int(row.get("char_count") or len(row.get("content_preview") or "")),
                content_preview=row.get("content_preview") or "",
            )
            for row in chunk_rows
        ]
        documents = [
            TourismDocument(
                doc_id=row["doc_id"],
                title=row.get("title") or "",
                content=row.get("title") or "",
                source_type=row.get("source_type") or "manual",
                source_name=row.get("source_name") or "unknown",
                source_url=row.get("source_url") or "",
                publish_time=row.get("publish_time"),
                raw_minio_key=row.get("raw_minio_key") or "",
                clean_minio_key=row.get("clean_minio_key") or "",
                content_hash=row.get("content_hash") or "",
                sentiment=row.get("sentiment") or "neutral",
                sentiment_score=float(row.get("sentiment_score") or 0),
            )
            for row in document_rows
        ]
        events = [
            TourismEvent(
                event_id=row["event_id"],
                event_name=row.get("event_name") or "",
                event_summary=row.get("event_summary") or "",
                event_type=row.get("topic") or "",
                topic=row.get("topic") or "",
                sentiment=row.get("sentiment") or "neutral",
                risk_level=row.get("risk_level") or "low",
                heat_score=float(row.get("heat_score") or 0),
                negative_ratio=float(row.get("negative_ratio") or 0),
                growth_rate=float(row.get("growth_rate") or 0),
                first_seen_at=row.get("first_seen_at"),
                last_seen_at=row.get("last_seen_at"),
                main_scenic_spot=row.get("main_scenic_spot") or "",
                main_location=row.get("main_location") or "",
                source_count=int(row.get("source_count") or 0),
                document_count=int(row.get("document_count") or 0),
                doc_ids=[],
                scenic_spots=[row.get("main_scenic_spot")] if row.get("main_scenic_spot") else [],
                locations=[row.get("main_location")] if row.get("main_location") else [],
            )
            for row in event_rows
        ]
        index_version = self.build_indexes(chunks, documents, events, task_no, bucket_name)
        return {
            "status": "success",
            "index_version": index_version,
            "chunk_count": len(chunks),
            "document_count": len(documents),
            "event_count": len(events),
        }

    def _build_faiss(
        self,
        chunks: list[TourismChunk],
        index_version: str,
        task_no: str,
        bucket_name: str,
    ) -> tuple[str, str, int]:
        vectors = self.embedding_service.embed_documents([item.content for item in chunks])
        vector_dim = int(vectors.shape[1]) if vectors.ndim == 2 and vectors.shape[0] > 0 else self.vector_dim
        id_map = {str(index): item.chunk_id for index, item in enumerate(chunks)}
        faiss_key = build_tourism_minio_key(TourismMinioPrefix.INDEX, index_version, "faiss", "index.faiss")
        id_map_key = build_tourism_minio_key(TourismMinioPrefix.INDEX, index_version, "faiss", "id_map.json")

        try:
            import faiss

            index = faiss.IndexFlatIP(vector_dim)
            if len(vectors) > 0:
                index.add(vectors)
            buffer = faiss.serialize_index(index).tobytes()
        except Exception:
            buffer = pickle.dumps({"vectors": vectors, "fallback": "numpy"})

        self.minio.upload_to_minio_form_stream(io.BytesIO(buffer), bucket_name, faiss_key)
        self.minio.upload_to_minio_form_stream(
            io.BytesIO(json.dumps(id_map, ensure_ascii=False).encode("utf-8")),
            bucket_name,
            id_map_key,
        )
        return faiss_key, id_map_key, vector_dim

    def _build_bm25(
        self,
        chunks: list[TourismChunk],
        index_version: str,
        task_no: str,
        bucket_name: str,
    ) -> tuple[str, str]:
        corpus = [self._tokenize(item.content) for item in chunks]
        doc_map = {str(index): item.chunk_id for index, item in enumerate(chunks)}
        bm25_key = build_tourism_minio_key(TourismMinioPrefix.INDEX, index_version, "bm25", "index.pkl")
        doc_map_key = build_tourism_minio_key(TourismMinioPrefix.INDEX, index_version, "bm25", "doc_map.json")
        try:
            from rank_bm25 import BM25Okapi

            bm25 = BM25Okapi(corpus)
            payload = pickle.dumps(bm25)
        except Exception:
            payload = pickle.dumps({"corpus": corpus, "fallback": "token_corpus"})

        self.minio.upload_to_minio_form_stream(io.BytesIO(payload), bucket_name, bm25_key)
        self.minio.upload_to_minio_form_stream(
            io.BytesIO(json.dumps(doc_map, ensure_ascii=False).encode("utf-8")),
            bucket_name,
            doc_map_key,
        )
        return bm25_key, doc_map_key

    def _save_index_version(
        self,
        index_version: str,
        index_type: str,
        index_key: str,
        metadata_key: str,
        chunk_count: int,
        document_count: int,
        event_count: int,
        vector_dim: int,
    ):
        self.mysql.insert(
            """
            INSERT INTO t_tourism_index_version
            (index_version, index_type, embedding_model, chunk_count, document_count, event_count,
             minio_index_key, metadata_minio_key, status, build_params, build_started_at, build_finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
              minio_index_key=VALUES(minio_index_key),
              metadata_minio_key=VALUES(metadata_minio_key),
              status=VALUES(status),
              build_finished_at=NOW()
            """,
            (
                index_version,
                index_type,
                self.embedding_service.model_name,
                chunk_count,
                document_count,
                event_count,
                index_key,
                metadata_key,
                "active",
                json.dumps(
                    {
                        "vector_dim": vector_dim,
                        "embedding_model": self.embedding_service.model_name,
                        "embedding_base_url": self.embedding_service.base_url,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        self.mysql.update_params(
            """
            UPDATE t_tourism_index_version
            SET status='inactive'
            WHERE index_type=%s AND index_version<>%s AND status='active'
            """,
            (index_type, index_version),
        )

    def _update_chunk_index_mapping(self, chunks: list[TourismChunk], index_version: str):
        sql = """
            UPDATE t_tourism_chunk
            SET index_version=%s, faiss_vector_id=%s, bm25_doc_id=%s
            WHERE chunk_id=%s
        """
        for index, chunk in enumerate(chunks):
            self.mysql.update_params(sql, (index_version, index, str(index), chunk.chunk_id))

    def embed_query(self, text: str) -> np.ndarray:
        return self.embedding_service.embed_query(text).astype("float32")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        try:
            import jieba

            return [item for item in jieba.lcut(text) if item.strip()]
        except Exception:
            return [char for char in text if char.strip()]
