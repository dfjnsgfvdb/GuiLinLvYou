import json
import traceback

from langchain_core.tools import tool

from services.tourism.event_service import TourismEventService


@tool(return_direct=False, name_or_callable="tourism_event_detail")
def tourism_event_detail(event_id: str, include_graph: bool = True) -> str:
    """查询单个桂林旅游舆情事件详情、来源文档和图谱关系。"""
    try:
        detail = TourismEventService().get_event_detail(event_id, include_graph=include_graph)
        return json.dumps(detail, ensure_ascii=False, default=str)
    except Exception as exc:
        traceback.print_exception(exc)
        return json.dumps({"error": "tourism_event_detail_failed", "message": str(exc)}, ensure_ascii=False)
