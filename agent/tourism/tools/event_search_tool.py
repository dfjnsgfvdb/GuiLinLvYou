import json
import traceback
from typing import Optional

from langchain_core.tools import tool

from services.tourism.event_service import TourismEventService


@tool(return_direct=False, name_or_callable="tourism_event_search")
def tourism_event_search(
    keyword: Optional[str] = None,
    scenic_spot: Optional[str] = None,
    location: Optional[str] = None,
    event_type: Optional[str] = None,
    sentiment: Optional[str] = None,
    risk_level: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 10,
) -> str:
    """查询聚合后的桂林旅游舆情事件列表。"""
    try:
        events = TourismEventService().search_events(
            keyword=keyword,
            scenic_spot=scenic_spot,
            location=location,
            event_type=event_type,
            sentiment=sentiment,
            risk_level=risk_level,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        return json.dumps({"events": events}, ensure_ascii=False, default=str)
    except Exception as exc:
        traceback.print_exception(exc)
        return json.dumps({"error": "tourism_event_search_failed", "message": str(exc)}, ensure_ascii=False)
