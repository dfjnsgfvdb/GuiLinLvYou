from decimal import Decimal
from typing import Any

from common.minio_util import MinioUtils
from common.mysql_util import MysqlUtil
from services.tourism.event_service import TourismEventService
from services.tourism.graph_service import GraphService


class TourismDashboardService:
    """Read-only operational views for the tourism opinion console."""

    GRAPH_LABELS = ["Event", "ScenicSpot", "Location", "Document", "Source", "Topic"]

    def __init__(self):
        self.mysql = MysqlUtil()
        self.minio = MinioUtils()
        self.events = TourismEventService()
        self.graph = GraphService()

    def overview(self) -> dict[str, Any]:
        metrics = {
            "document_count": self._count("t_tourism_document"),
            "event_count": self._count("t_tourism_event", "status IS NULL OR status <> 'merged'"),
            "negative_event_count": self._count(
                "t_tourism_event",
                "(status IS NULL OR status <> 'merged') AND sentiment='negative'",
            ),
            "high_risk_event_count": self._count(
                "t_tourism_event",
                "(status IS NULL OR status <> 'merged') AND risk_level IN ('high', 'critical')",
            ),
            "qa_count": self._count("t_user_qa_record", "qa_type='TOURISM_QA'"),
        }
        source_distribution = self.mysql.query_mysql_dict(
            """
            SELECT COALESCE(NULLIF(source_name, ''), '未知来源') AS name, COUNT(*) AS value
            FROM t_tourism_document
            GROUP BY COALESCE(NULLIF(source_name, ''), '未知来源')
            ORDER BY value DESC
            LIMIT 8
            """
        )
        scenic_distribution = self.mysql.query_mysql_dict(
            """
            SELECT COALESCE(NULLIF(main_scenic_spot, ''), '其他') AS name, COUNT(*) AS value
            FROM t_tourism_event
            WHERE status IS NULL OR status <> 'merged'
            GROUP BY COALESCE(NULLIF(main_scenic_spot, ''), '其他')
            ORDER BY value DESC
            LIMIT 8
            """
        )
        sentiment_distribution = self.mysql.query_mysql_dict(
            """
            SELECT COALESCE(NULLIF(sentiment, ''), 'neutral') AS name, COUNT(*) AS value
            FROM t_tourism_event
            WHERE status IS NULL OR status <> 'merged'
            GROUP BY COALESCE(NULLIF(sentiment, ''), 'neutral')
            ORDER BY value DESC
            """
        )
        trend = self.mysql.query_mysql_dict(
            """
            SELECT DATE(day_value) AS day, COUNT(*) AS value
            FROM (
                SELECT COALESCE(publish_time, create_time) AS day_value
                FROM t_tourism_document
            ) AS documents
            GROUP BY day
            ORDER BY day ASC
            LIMIT 30
            """
        )
        recent_events = self.events.search_events(limit=6)
        latest_task = self._one(
            """
            SELECT task_no, status, total_count, success_count, failed_count, duration_ms,
                   started_at, finished_at
            FROM t_tourism_ingest_task
            ORDER BY id DESC
            LIMIT 1
            """
        )
        active_indexes = self.mysql.query_mysql_dict(
            """
            SELECT index_version, index_type, embedding_model, chunk_count, document_count,
                   event_count, status, build_finished_at
            FROM t_tourism_index_version
            WHERE status='active'
            ORDER BY index_type
            """
        )
        return self._json_safe(
            {
                "metrics": metrics,
                "source_distribution": source_distribution,
                "scenic_distribution": scenic_distribution,
                "sentiment_distribution": sentiment_distribution,
                "trend": trend,
                "recent_events": recent_events,
                "latest_task": latest_task,
                "active_indexes": active_indexes,
            }
        )

    def search_events(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        allowed = {
            "keyword",
            "scenic_spot",
            "location",
            "event_type",
            "sentiment",
            "risk_level",
            "start_time",
            "end_time",
            "limit",
        }
        params = {key: value for key, value in filters.items() if key in allowed and value not in (None, "")}
        return self._json_safe(self.events.search_events(**params))

    def event_detail(self, event_id: str) -> dict[str, Any]:
        return self._json_safe(self.events.get_event_detail(event_id, include_graph=True))

    def graph_overview(self, limit: int = 80) -> dict[str, Any]:
        limit = max(10, min(int(limit or 80), 120))
        if not self.graph.neo4j.available():
            return {"nodes": [], "relationships": [], "paths": [], "available": False}
        cursor = self.graph.neo4j.run(
            """
            MATCH p=(a)-[r]->(b)
            WHERE any(label IN labels(a) WHERE label IN $labels)
              AND any(label IN labels(b) WHERE label IN $labels)
            RETURN collect(DISTINCT p)[0..$limit] AS paths
            """,
            labels=self.GRAPH_LABELS,
            limit=limit,
        )
        payload = self.graph._cursor_to_graph_payload(cursor)
        payload["available"] = True
        return self._json_safe(payload)

    def system_status(self) -> dict[str, Any]:
        latest_task = self._one(
            """
            SELECT task_no, status, success_count, failed_count, duration_ms, finished_at
            FROM t_tourism_ingest_task
            ORDER BY id DESC
            LIMIT 1
            """
        )
        indexes = self.mysql.query_mysql_dict(
            """
            SELECT index_version, index_type, embedding_model, chunk_count, document_count,
                   event_count, status, build_finished_at
            FROM t_tourism_index_version
            ORDER BY id DESC
            LIMIT 12
            """
        )
        try:
            minio_available = self.minio.client.bucket_exists("filedata")
        except Exception:
            minio_available = False
        return self._json_safe(
            {
                "services": [
                    {"name": "MySQL", "role": "业务数据与问答记录", "available": True},
                    {"name": "MinIO", "role": "原始文件与索引对象", "available": minio_available},
                    {"name": "Neo4j", "role": "旅游事件知识图谱", "available": self.graph.neo4j.available()},
                    {
                        "name": "FAISS / BM25",
                        "role": "语义与关键词混合召回",
                        "available": any(item.get("status") == "active" for item in indexes),
                    },
                ],
                "latest_task": latest_task,
                "indexes": indexes,
            }
        )

    def _count(self, table: str, where: str = "") -> int:
        suffix = f" WHERE {where}" if where else ""
        return int(self.mysql.query_mysql_dict(f"SELECT COUNT(*) AS value FROM {table}{suffix}")[0]["value"])

    def _one(self, sql: str) -> dict[str, Any] | None:
        rows = self.mysql.query_mysql_dict(sql)
        return rows[0] if rows else None

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        if hasattr(value, "iso_format"):
            return value.iso_format()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
