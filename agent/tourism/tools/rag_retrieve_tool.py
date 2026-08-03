import json
import traceback
from typing import Optional

from langchain_core.tools import tool

from common.evidence_schema import RetrievalMode
from services.tourism.retrieval_service import TourismRetrievalFilters, TourismRetrievalService


@tool(return_direct=False, name_or_callable="tourism_rag_retrieve")
def tourism_rag_retrieve(
    query: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    source_name: Optional[str] = None,
    source_type: Optional[str] = None,
    scenic_spot: Optional[str] = None,
    location: Optional[str] = None,
    event_type: Optional[str] = None,
    top_k: int = 5,
    mode: str = RetrievalMode.HYBRID_GRAPH.value,
) -> str:
    """
    检索桂林旅游舆情知识库，返回文本片段、来源文档、关联事件和 Neo4j 图谱关系证据。

    当问题涉及具体舆情事实、景区投诉、地点事件、来源追溯、事件关联分析时必须优先调用本工具。
    时间参数格式建议使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS。
    """
    try:
        filters = TourismRetrievalFilters(
            start_time=start_time,
            end_time=end_time,
            source_name=source_name,
            source_type=source_type,
            scenic_spot=scenic_spot,
            location=location,
            event_type=event_type,
        )
        package = TourismRetrievalService().retrieve(
            query=query,
            filters=filters,
            top_k=top_k,
            mode=mode,
            expand_graph=mode == RetrievalMode.HYBRID_GRAPH.value,
        )
        return json.dumps(package, ensure_ascii=False, default=str)
    except Exception as exc:
        traceback.print_exception(exc)
        return json.dumps(
            {
                "error": "tourism_hybrid_retrieve_failed",
                "message": str(exc),
                "query": query,
            },
            ensure_ascii=False,
        )


tourism_hybrid_retrieve = tourism_rag_retrieve
