import json
import traceback
from typing import Optional

from langchain_core.tools import tool

from services.tourism.graph_service import GraphService


@tool(return_direct=False, name_or_callable="tourism_graph_retrieve")
def tourism_graph_retrieve(
    event_id: Optional[str] = None,
    scenic_spot: Optional[str] = None,
    location: Optional[str] = None,
    hop: int = 1,
    limit: int = 50,
) -> str:
    """按 event_id、景区或地点查询桂林旅游舆情 Neo4j 图谱关系。"""
    try:
        service = GraphService()
        if event_id:
            result = service.query_event_relations(event_id, hop=hop, limit=limit)
        elif scenic_spot:
            result = service.query_by_scenic_spot(scenic_spot, hop=hop, limit=limit)
        elif location:
            result = service.query_by_location(location, hop=hop, limit=limit)
        else:
            result = {"nodes": [], "relationships": [], "paths": []}
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        traceback.print_exception(exc)
        return json.dumps({"error": "tourism_graph_retrieve_failed", "message": str(exc)}, ensure_ascii=False)
