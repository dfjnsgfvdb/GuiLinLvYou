import asyncio
import json
import logging
import os
import re
import traceback
import uuid
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agent.tourism.tourism_qa_prompt import (
    TOURISM_GENERAL_FALLBACK_SYSTEM_PROMPT,
    TOURISM_QA_SYSTEM_PROMPT,
    build_tourism_general_fallback_prompt,
    build_tourism_qa_user_prompt,
)
from constants.code_enum import DataTypeEnum, DiFyAppEnum
from services.tourism.conversation_memory import TourismConversationMemory
from services.tourism.event_service import TourismEventService
from services.tourism.retrieval_service import TourismRetrievalService
from services.user_service import add_user_record, decode_jwt_token

logger = logging.getLogger(__name__)


class TourismQaState(TypedDict, total=False):
    query: str
    evidence_package: Dict[str, Any]
    event_results: List[Dict[str, Any]]
    event_detail: Dict[str, Any]
    business_data: Dict[str, Any]
    conversation_context: str
    messages: List[Any]
    answer_policy: str


class TourismOpinionAgent:
    """Controlled LangGraph agent for Guilin tourism public-opinion QA."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME", "qwen-plus"),
            temperature=float(os.getenv("MODEL_TEMPERATURE", 0.2)),
            base_url=os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key=os.getenv("MODEL_API_KEY"),
            max_tokens=int(os.getenv("MAX_TOKENS", 4096)),
            top_p=float(os.getenv("TOP_P", 0.8)),
            frequency_penalty=float(os.getenv("FREQUENCY_PENALTY", 0.0)),
            presence_penalty=float(os.getenv("PRESENCE_PENALTY", 0.0)),
            timeout=float(os.getenv("REQUEST_TIMEOUT", 300.0)),
            max_retries=int(os.getenv("MAX_RETRIES", 3)),
            streaming=os.getenv("STREAMING", "True").lower() == "true",
            extra_body={},
            http_client=httpx.Client(trust_env=False),
            http_async_client=httpx.AsyncClient(trust_env=False),
        )
        self.llm_stream_timeout = float(os.getenv("TOURISM_LLM_TIMEOUT_SECONDS", "90"))
        self.running_tasks: Dict[str, Dict[str, Any]] = {}
        self.conversation_memory = TourismConversationMemory()
        self.workflow = self._build_workflow()

    @staticmethod
    def _create_response(
        content: str,
        message_type: str = "continue",
        data_type: str = DataTypeEnum.ANSWER.value[0],
    ) -> str:
        res = {"data": {"messageType": message_type, "content": content}, "dataType": data_type}
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    @staticmethod
    def _create_business_response(data: Dict[str, Any]) -> str:
        res = {"data": data, "dataType": DataTypeEnum.BUS_DATA.value[0]}
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    @staticmethod
    def _create_task_response(task_id: str) -> str:
        res = {"task_id": task_id, "data": {"messageType": "continue"}, "dataType": DataTypeEnum.TASK_ID.value[0]}
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    def _build_workflow(self):
        graph = StateGraph(TourismQaState)
        graph.add_node("retrieve_context", self._retrieve_context_node)
        graph.add_node("prepare_answer", self._prepare_answer_node)
        graph.add_edge(START, "retrieve_context")
        graph.add_edge("retrieve_context", "prepare_answer")
        graph.add_edge("prepare_answer", END)
        return graph.compile()

    def _retrieve_context_node(self, state: TourismQaState) -> TourismQaState:
        query = state["query"]
        retrieval_service = TourismRetrievalService()
        event_service = TourismEventService()

        evidence_package = retrieval_service.retrieve(query=query, mode="hybrid_graph", expand_graph=True)
        event_results = self._extract_events(
            evidence_package.get("retrieval", {}).get("candidates", []), [], {}
        )

        top_event_id = self._first_event_id(evidence_package, event_results)
        event_detail = event_service.get_event_detail(top_event_id, include_graph=True) if top_event_id else {}

        evidence_package = self._fuse_evidence(evidence_package, event_results, event_detail)
        answer_policy = self._decide_answer_policy(query, evidence_package)
        evidence_package.setdefault("metrics", {})["evidence_sufficient"] = answer_policy == "evidence_grounded"
        evidence_package["metrics"]["answer_generation_allowed"] = answer_policy in {
            "evidence_grounded",
            "general_fallback",
        }
        business_data = self._json_safe(
            self._build_business_data(evidence_package, event_results, event_detail, answer_policy)
        )
        return {
            **state,
            "evidence_package": evidence_package,
            "event_results": event_results,
            "event_detail": event_detail,
            "business_data": business_data,
            "answer_policy": answer_policy,
        }

    def _prepare_answer_node(self, state: TourismQaState) -> TourismQaState:
        answer_policy = state.get("answer_policy")
        if answer_policy == "general_fallback":
            return {
                **state,
                "messages": [
                    SystemMessage(content=TOURISM_GENERAL_FALLBACK_SYSTEM_PROMPT),
                    HumanMessage(
                        content=build_tourism_general_fallback_prompt(
                            state["query"],
                            state.get("conversation_context", "无"),
                        )
                    ),
                ],
            }
        if answer_policy != "evidence_grounded":
            return {**state, "messages": []}

        evidence_json = json.dumps(self._compact_evidence_for_prompt(state["business_data"]), ensure_ascii=False)
        if len(evidence_json) > 16000:
            evidence_json = evidence_json[:16000] + "\n...证据内容过长，已截断..."

        messages = [
            SystemMessage(content=TOURISM_QA_SYSTEM_PROMPT),
            HumanMessage(
                content=build_tourism_qa_user_prompt(
                    state["query"],
                    evidence_json,
                    state.get("conversation_context", "无"),
                ) + "\n每一条事实性陈述必须使用对应证据编号标注，例如 [E1]；不得引用不存在的编号。"
            ),
        ]
        return {**state, "messages": messages}

    async def run_agent(
        self,
        query: str,
        response,
        session_id: Optional[str] = None,
        uuid_str: str = None,
        user_token=None,
        file_list: dict = None,
    ):
        user_dict = await decode_jwt_token(user_token)
        user_id = str(user_dict["id"])
        task_id = str(uuid_str or uuid.uuid4())
        self.running_tasks[task_id] = {"cancelled": False, "user_id": user_id}
        answer_chunks: List[str] = []
        evidence_package: Dict[str, Any] = {}
        business_data: Dict[str, Any] = {}
        keepalive_task: Optional[asyncio.Task] = None
        memory_context = TourismConversationMemory.compact_for_prompt(
            self.conversation_memory.load(user_id, session_id)
        )

        try:
            await response.write(self._create_task_response(task_id))
            if hasattr(response, "flush"):
                await response.flush()
            keepalive_task = asyncio.create_task(self._write_keepalive(response, task_id))
            state = await self.workflow.ainvoke({"query": query, "conversation_context": memory_context})
            evidence_package = state.get("evidence_package", {})
            business_data = state.get("business_data", {})

            if self._is_cancelled(task_id):
                await self._stop_keepalive(keepalive_task)
                await self._write_cancelled(response)
                return

            answer_policy = state.get("answer_policy", "evidence_required")
            citation_validation: Dict[str, Any] = {
                "required": answer_policy == "evidence_grounded",
                "passed": answer_policy != "evidence_grounded",
                "valid_citations": [],
                "invalid_citations": [],
            }
            if answer_policy == "evidence_required":
                answer = self._insufficient_evidence_answer()
                answer_chunks.append(answer)
            else:
                messages = state["messages"]
                answer = await self._generate_llm_answer(response, task_id, messages)
                if answer is None:
                    await self._stop_keepalive(keepalive_task)
                    await self._write_cancelled(response)
                    return
                if answer_policy == "evidence_grounded":
                    answer, citation_validation = self._validate_answer_citations(
                        answer,
                        evidence_package.get("retrieval", {}).get("candidates", []),
                    )
                answer_chunks.append(answer)

            await self._stop_keepalive(keepalive_task)
            await self._write_answer_sse(response, answer_chunks[-1])
            evidence_package["citation_validation"] = citation_validation
            evidence_package.setdefault("metrics", {})["citation_validation"] = citation_validation
            business_data["citation_validation"] = citation_validation
            business_data["metrics"] = evidence_package.get("metrics", {})
            await response.write(self._create_business_response(business_data))

            qa_record_id = await add_user_record(
                uuid_str,
                session_id,
                query,
                answer_chunks,
                {"data": business_data, "dataType": DataTypeEnum.BUS_DATA.value[0]},
                DiFyAppEnum.TOURISM_QA.value[0],
                user_token,
                file_list,
            )
            self._save_qa_evidence(qa_record_id, session_id, uuid_str, query, evidence_package)
            self._save_retrieval_log(
                qa_record_id,
                session_id,
                uuid_str,
                query,
                evidence_package,
                answer_policy,
                citation_validation,
            )
            self.conversation_memory.append_turn(user_id, session_id, query, "".join(answer_chunks))

        except asyncio.CancelledError:
            await self._stop_keepalive(keepalive_task)
            if self._is_cancelled(task_id):
                await self._write_cancelled(response)
            else:
                logger.info("Tourism QA stream closed by client before completion, task_id=%s", task_id)
        except Exception as exc:
            await self._stop_keepalive(keepalive_task)
            logger.error("桂林旅游舆情 Agent 运行异常: %s", exc, exc_info=True)
            traceback.print_exception(exc)
            await response.write(self._create_response("[ERROR] 桂林旅游舆情问答运行异常", "error"))
        finally:
            await self._stop_keepalive(keepalive_task)
            self.running_tasks.pop(task_id, None)

    async def _write_cancelled(self, response) -> None:
        await response.write(self._create_response("\n> 这条消息已停止生成", "info"))

    async def _write_cancelled(self, response) -> None:
        await response.write(self._create_response("\n> \u8fd9\u6761\u6d88\u606f\u5df2\u505c\u6b62\u751f\u6210\u3002", "info"))
        if hasattr(response, "flush"):
            await response.flush()

    async def _write_keepalive(self, response, task_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(15)
                if self._is_cancelled(task_id):
                    return
                await response.write(": keep-alive\n\n")
                if hasattr(response, "flush"):
                    await response.flush()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.debug("Tourism QA keep-alive stopped, task_id=%s: %s", task_id, exc)

    @staticmethod
    async def _stop_keepalive(task: Optional[asyncio.Task]) -> None:
        if not task or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def cancel_task(self, task_id: str, user_id: str | int | None = None) -> bool:
        task_id = str(task_id)
        task = self.running_tasks.get(task_id)
        if task and (user_id is None or task.get("user_id") == str(user_id)):
            task["cancelled"] = True
            return True
        return False

    def _is_cancelled(self, task_id: str) -> bool:
        return bool(self.running_tasks.get(task_id, {}).get("cancelled"))

    def _build_business_data(
        self,
        evidence_package: Dict[str, Any],
        event_results: List[Dict[str, Any]],
        event_detail: Dict[str, Any],
        answer_policy: str,
    ) -> Dict[str, Any]:
        candidates = evidence_package.get("retrieval", {}).get("candidates", [])
        sources = self._extract_sources(candidates)
        events = self._extract_events(candidates, event_results, event_detail)
        graph = self._merge_graph_payloads(evidence_package.get("graph", {}), event_detail.get("graph", {}))

        return {
            "template_code": "TOURISM_EVIDENCE",
            "query_context": evidence_package.get("query_context", {}),
            "retrieval": evidence_package.get("retrieval", {}),
            "sources": sources,
            "events": events,
            "graph": graph,
            "metrics": evidence_package.get("metrics", {}),
            "answer_policy": answer_policy,
        }

    def _extract_sources(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        sources = []
        for item in candidates:
            document = item.get("document") or {}
            doc_id = document.get("doc_id") or item.get("doc_id")
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            sources.append(
                {
                    "doc_id": doc_id,
                    "title": document.get("title"),
                    "source_type": document.get("source_type"),
                    "source_name": document.get("source_name"),
                    "source_url": document.get("source_url"),
                    "publish_time": document.get("publish_time"),
                    "sentiment": document.get("sentiment"),
                    "score": item.get("score"),
                    "quote_text": item.get("quote_text"),
                }
            )
        return sources

    def _extract_events(
        self,
        candidates: List[Dict[str, Any]],
        event_results: List[Dict[str, Any]],
        event_detail: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        seen = set()
        events = []

        def append_event(event: Dict[str, Any]):
            event_id = event.get("event_id")
            if not event_id or event_id in seen:
                return
            seen.add(event_id)
            events.append(event)

        for candidate in candidates:
            for event in candidate.get("events", []) or []:
                append_event(event)
        for event in event_results or []:
            append_event(event)
        if event_detail.get("event"):
            append_event(event_detail["event"])
        return events

    def _merge_graph_payloads(self, *payloads: Dict[str, Any]) -> Dict[str, Any]:
        merged = {"nodes": [], "relationships": [], "paths": []}
        node_ids = set()
        rel_ids = set()
        for payload in payloads:
            for node in (payload or {}).get("nodes", []):
                node_id = node.get("id")
                if node_id not in node_ids:
                    node_ids.add(node_id)
                    merged["nodes"].append(node)
            for rel in (payload or {}).get("relationships", []):
                rel_id = rel.get("id")
                if rel_id not in rel_ids:
                    rel_ids.add(rel_id)
                    merged["relationships"].append(rel)
            merged["paths"].extend((payload or {}).get("paths", []))
        return merged

    def _compact_evidence_for_prompt(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "query_context": business_data.get("query_context", {}),
            "sources": business_data.get("sources", [])[:6],
            "events": business_data.get("events", [])[:6],
            "graph_relationships": business_data.get("graph", {}).get("relationships", [])[:20],
            "retrieval": {
                "mode": business_data.get("retrieval", {}).get("mode"),
                "latency_ms": business_data.get("retrieval", {}).get("latency_ms"),
                "candidates": business_data.get("retrieval", {}).get("candidates", []),
            },
        }

    def _first_event_id(self, evidence_package: Dict[str, Any], event_results: List[Dict[str, Any]]) -> Optional[str]:
        for candidate in evidence_package.get("retrieval", {}).get("candidates", []):
            if candidate.get("event_id"):
                return candidate["event_id"]
            for event in candidate.get("events", []) or []:
                if event.get("event_id"):
                    return event["event_id"]
        for event in event_results or []:
            if event.get("event_id"):
                return event["event_id"]
        return None

    def _fuse_evidence(
        self,
        evidence_package: Dict[str, Any],
        event_results: List[Dict[str, Any]],
        event_detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        evidence = evidence_package.setdefault("evidence", [])
        seen_events = {item.get("event_id") for item in evidence if item.get("event_id")}
        events = self._extract_events(
            evidence_package.get("retrieval", {}).get("candidates", []),
            event_results,
            event_detail,
        )
        for event in events:
            event_id = event.get("event_id")
            if not event_id or event_id in seen_events:
                continue
            seen_events.add(event_id)
            evidence.append(
                {
                    "evidence_type": "event",
                    "event_id": event_id,
                    "score": None,
                    "quote_text": event.get("event_summary") or event.get("event_name"),
                    "metadata": event,
                }
            )

        merged_graph = self._merge_graph_payloads(
            evidence_package.get("graph", {}),
            event_detail.get("graph", {}),
        )
        evidence_package["graph"] = merged_graph
        seen_relations = {item.get("graph_relation_id") for item in evidence if item.get("graph_relation_id")}
        for relation in merged_graph.get("relationships", []):
            relation_id = relation.get("id")
            if not relation_id or relation_id in seen_relations:
                continue
            seen_relations.add(relation_id)
            evidence.append(
                {
                    "evidence_type": "graph_relation",
                    "graph_relation_id": relation_id,
                    "score": None,
                    "quote_text": relation.get("type"),
                    "metadata": relation,
                }
            )

        metrics = evidence_package.setdefault("metrics", {})
        metrics["event_hit_count"] = len(events)
        metrics["graph_relation_count"] = len(merged_graph.get("relationships", []))
        return evidence_package

    @staticmethod
    def _has_enough_evidence(evidence_package: Dict[str, Any]) -> bool:
        retrieval = evidence_package.get("retrieval", {})
        candidates = retrieval.get("candidates", [])
        retrieval_sufficiency = retrieval.get("sufficiency", {})
        return bool(
            retrieval_sufficiency.get("passed")
            and any(item.get("quote_text") for item in candidates)
        )

    def _decide_answer_policy(self, query: str, evidence_package: Dict[str, Any]) -> str:
        # Vector similarity can return plausible but unrelated tourism chunks for
        # general-knowledge questions. Route clearly out-of-domain questions to
        # the general model before treating those chunks as grounded evidence.
        if self._can_use_general_fallback(query) and not self._is_tourism_domain_query(query):
            return "general_fallback"
        if self._has_enough_evidence(evidence_package):
            return "evidence_grounded"
        if self._can_use_general_fallback(query):
            return "general_fallback"
        return "evidence_required"

    @staticmethod
    def _is_tourism_domain_query(query: str) -> bool:
        normalized = (query or "").strip().lower()
        domain_keywords = [
            "桂林",
            "漓江",
            "阳朔",
            "象鼻山",
            "龙脊梯田",
            "两江四湖",
            "遇龙河",
            "芦笛岩",
            "靖江王城",
            "旅游",
            "游客",
            "景区",
            "景点",
            "游船",
            "竹筏",
            "码头",
            "酒店",
            "民宿",
            "导游",
            "旅行社",
            "门票",
            "客流",
            "排队",
            "投诉",
            "差评",
            "舆情",
            "热度",
            "风险",
            "预警",
            "事件",
            "行程",
        ]
        return any(keyword in normalized for keyword in domain_keywords)

    @staticmethod
    def _can_use_general_fallback(query: str) -> bool:
        normalized = (query or "").strip().lower()
        evidence_required_keywords = [
            "今天",
            "现在",
            "当前",
            "实时",
            "最近",
            "近期",
            "最新",
            "明天",
            "本周",
            "适合去",
            "值得去",
            "能去",
            "要不要去",
            "人多",
            "客流",
            "拥堵",
            "排队",
            "天气",
            "下雨",
            "开放",
            "门票",
            "价格",
            "公告",
            "投诉",
            "差评",
            "舆情",
            "负面",
            "热度",
            "风险",
            "预警",
            "事件",
            "事故",
            "纠纷",
            "宰客",
            "黑导游",
            "排行",
            "排名",
            "数量",
            "多少",
            "趋势",
        ]
        return bool(normalized) and not any(keyword in normalized for keyword in evidence_required_keywords)

    async def _generate_llm_answer(
        self,
        response,
        task_id: str,
        messages: List[Any],
    ) -> Optional[str]:
        generated_chunks: List[str] = []
        try:
            async with asyncio.timeout(self.llm_stream_timeout):
                async for message_chunk in self.llm.astream(messages):
                    if self._is_cancelled(task_id):
                        return None

                    content = self._chunk_to_text(message_chunk.content)
                    if content:
                        generated_chunks.append(content)
        except TimeoutError:
            logger.warning("旅游问答模型流式响应超时，task_id=%s", task_id)
            return "模型响应超时，请稍后重试。"
        except Exception as exc:
            logger.error("旅游问答模型调用失败，task_id=%s: %s", task_id, exc, exc_info=True)
            return "模型服务暂时不可用，请稍后重试。"
        return "".join(generated_chunks) or "模型未返回有效内容，请换一种方式提问。"

    async def _write_answer_sse(self, response, answer: str) -> None:
        chunk_size = 48
        for start in range(0, len(answer), chunk_size):
            await response.write(self._create_response(answer[start : start + chunk_size]))
            if hasattr(response, "flush"):
                await response.flush()
            await asyncio.sleep(0)

    @staticmethod
    def _validate_answer_citations(
        answer: str,
        candidates: List[Dict[str, Any]],
    ) -> tuple[str, Dict[str, Any]]:
        allowed = {
            str(item.get("evidence_id"))
            for item in candidates
            if item.get("evidence_id")
        }
        citation_groups = re.findall(r"\[([^\]]*E\d+[^\]]*)\]", answer or "")
        cited = {
            citation
            for group in citation_groups
            for citation in re.findall(r"E\d+", group)
        }
        valid = sorted(cited.intersection(allowed))
        invalid = sorted(cited.difference(allowed))
        validated_answer = answer
        for citation in invalid:
            validated_answer = re.sub(
                rf"(?<=\[)\s*{re.escape(citation)}\s*(?:[,，、]\s*)?|"
                rf"(?:[,，、]\s*)?{re.escape(citation)}\s*(?=\])",
                "",
                validated_answer,
            )
        validated_answer = re.sub(r"\[\s*\]", "", validated_answer)
        if allowed and not valid:
            fallback_citation = sorted(allowed, key=lambda item: int(item[1:]))[0]
            validated_answer = validated_answer.rstrip() + f"\n\n证据依据：[{fallback_citation}]"
            valid = [fallback_citation]
        return validated_answer, {
            "required": True,
            "passed": bool(valid) and not invalid,
            "valid_citations": valid,
            "invalid_citations": invalid,
            "available_citations": sorted(allowed, key=lambda item: int(item[1:])),
        }

    def _insufficient_evidence_answer(self) -> str:
        return (
            "### 事实\n"
            "- 当前证据不足：未从已构建的桂林旅游舆情索引中召回可支撑回答的文本片段、来源文档或事件关系。\n\n"
            "### 推断\n"
            "- 可能原因包括：相关数据尚未导入、索引尚未重建、查询条件过窄，或当前问题超出了已采集数据范围。\n\n"
            "### 建议\n"
            "- 先在“数据处理链路”中导入相关新闻、评论或平台文本，并重建 FAISS/BM25 索引和 Neo4j 图谱。\n"
            "- 如已导入数据，建议放宽时间、平台、景区或事件类型条件后重新查询。\n"
        )

    def _save_qa_evidence(
        self,
        qa_record_id: Optional[int],
        session_id: Optional[str],
        uuid_str: Optional[str],
        query: str,
        evidence_package: Dict[str, Any],
    ) -> None:
        if not evidence_package:
            return
        try:
            TourismRetrievalService().save_evidence_package(
                qa_record_id=qa_record_id,
                chat_id=session_id,
                uuid=uuid_str,
                qa_type=DiFyAppEnum.TOURISM_QA.value[0],
                question=query,
                evidence_package=evidence_package,
            )
        except Exception as exc:
            logger.warning("保存桂林旅游舆情问答证据失败: %s", exc, exc_info=True)

    def _save_retrieval_log(
        self,
        qa_record_id: Optional[int],
        session_id: Optional[str],
        uuid_str: Optional[str],
        query: str,
        evidence_package: Dict[str, Any],
        answer_policy: str,
        citation_validation: Dict[str, Any],
    ) -> None:
        try:
            TourismRetrievalService().save_retrieval_log(
                qa_record_id=qa_record_id,
                chat_id=session_id,
                uuid=uuid_str,
                question=query,
                evidence_package=evidence_package,
                answer_policy=answer_policy,
                citation_validation=citation_validation,
            )
        except Exception as exc:
            logger.warning("保存桂林旅游舆情检索评估日志失败: %s", exc, exc_info=True)

    def _chunk_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            return "".join(parts)
        return str(content) if content else ""

    def _json_safe(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {key: self._json_safe(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._json_safe(value) for value in payload]
        if isinstance(payload, (datetime, date)):
            return payload.isoformat()
        if isinstance(payload, Decimal):
            return float(payload)
        if hasattr(payload, "iso_format"):
            return payload.iso_format()
        if hasattr(payload, "isoformat"):
            return payload.isoformat()
        if payload is None or isinstance(payload, (str, int, float, bool)):
            return payload
        return str(payload)
