from typing import Any, Dict, List, Optional

from common.mysql_util import MysqlUtil
from services.tourism.graph_service import GraphService


class TourismEventService:
    def __init__(self):
        self.mysql = MysqlUtil()
        self.graph_service = GraphService()

    def search_events(
        self,
        keyword: Optional[str] = None,
        scenic_spot: Optional[str] = None,
        location: Optional[str] = None,
        event_type: Optional[str] = None,
        sentiment: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 10), 50))
        clauses = ["(status IS NULL OR status <> 'merged')"]
        params: List[Any] = []

        if keyword:
            clauses.append(
                "(event_name LIKE %s ESCAPE '\\\\' OR event_summary LIKE %s ESCAPE '\\\\' "
                "OR topic LIKE %s ESCAPE '\\\\')"
            )
            escaped_keyword = str(keyword).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like_value = f"%{escaped_keyword}%"
            params.extend([like_value, like_value, like_value])
        if scenic_spot:
            clauses.append("main_scenic_spot = %s")
            params.append(scenic_spot)
        if location:
            clauses.append("main_location = %s")
            params.append(location)
        if event_type:
            clauses.append("(topic = %s OR event_name LIKE %s)")
            params.extend([event_type, f"%{event_type}%"])
        if sentiment:
            clauses.append("sentiment = %s")
            params.append(sentiment)
        if risk_level:
            clauses.append("risk_level = %s")
            params.append(risk_level)
        if start_time:
            clauses.append("last_seen_at >= %s")
            params.append(start_time)
        if end_time:
            clauses.append("first_seen_at <= %s")
            params.append(end_time)

        sql = f"""
            SELECT event_id, event_name, event_summary, topic, sentiment, risk_level,
                   heat_score, negative_ratio, growth_rate, first_seen_at, last_seen_at,
                   main_scenic_spot, main_location, source_count, document_count, status
            FROM t_tourism_event
            WHERE {" AND ".join(clauses)}
            ORDER BY heat_score DESC, last_seen_at DESC
            LIMIT %s
        """
        params.append(limit)
        return self.mysql.query_mysql_dict_params(sql, tuple(params)) or []

    def get_event_detail(self, event_id: str, include_graph: bool = True) -> Dict[str, Any]:
        event_rows = self.mysql.query_mysql_dict_params(
            """
            SELECT event_id, event_name, event_summary, topic, sentiment, risk_level,
                   heat_score, negative_ratio, growth_rate, first_seen_at, last_seen_at,
                   main_scenic_spot, main_location, source_count, document_count, status
            FROM t_tourism_event
            WHERE event_id = %s
            LIMIT 1
            """,
            (event_id,),
        )
        if not event_rows:
            return {"event": None, "documents": [], "graph": {"nodes": [], "relationships": [], "paths": []}}

        documents = self.mysql.query_mysql_dict_params(
            """
            SELECT d.doc_id, d.title, d.source_type, d.source_name, d.source_url,
                   d.publish_time, d.sentiment, d.sentiment_score, ed.match_score, ed.match_reason
            FROM t_tourism_event_document ed
            JOIN t_tourism_document d ON ed.doc_id = d.doc_id
            WHERE ed.event_id = %s
            ORDER BY d.publish_time DESC, d.id DESC
            LIMIT 50
            """,
            (event_id,),
        ) or []
        graph = self.graph_service.query_event_relations(event_id, hop=2, limit=80) if include_graph else {
            "nodes": [],
            "relationships": [],
            "paths": [],
        }
        return {"event": event_rows[0], "documents": documents, "graph": graph}
