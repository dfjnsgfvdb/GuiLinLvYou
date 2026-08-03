import json
import logging
import os
import re
from typing import Protocol

import httpx

from common.evidence_schema import EvidenceCandidate, QueryContext

logger = logging.getLogger(__name__)


class RerankModelProvider(Protocol):
    """Adapter reserved for a dedicated cross-encoder or hosted rerank model."""

    def score(self, query: str, candidates: list[EvidenceCandidate]) -> dict[str, float]: ...


class RuleLlmReranker:
    def __init__(self, model_provider: RerankModelProvider | None = None):
        self.model_provider = model_provider
        self.llm_enabled = os.getenv("RERANK_LLM_ENABLED", "true").lower() == "true"

    def rerank(self, context: QueryContext, candidates: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
        for candidate in candidates:
            candidate.rule_score = self._rule_score(context, candidate)

        model_scores = self._model_scores(context, candidates)
        llm_scores = {} if model_scores else self._llm_judge(context, candidates)
        for candidate in candidates:
            judged_score = model_scores.get(candidate.candidate_id)
            if judged_score is None:
                judged_score = llm_scores.get(candidate.candidate_id)
            candidate.llm_score = judged_score
            if judged_score is None:
                candidate.rerank_score = 0.65 * candidate.fusion_score + 0.35 * candidate.rule_score
            else:
                candidate.rerank_score = (
                    0.45 * candidate.fusion_score + 0.30 * candidate.rule_score + 0.25 * judged_score
                )
            candidate.final_score = candidate.rerank_score
        return sorted(candidates, key=lambda item: item.rerank_score, reverse=True)

    def _model_scores(self, context: QueryContext, candidates: list[EvidenceCandidate]) -> dict[str, float]:
        if not self.model_provider:
            return {}
        try:
            return self._bounded_scores(self.model_provider.score(context.rewritten_query, candidates))
        except Exception as exc:
            logger.warning("Dedicated rerank provider failed; using rule/LLM fallback: %s", exc)
            return {}

    def _llm_judge(self, context: QueryContext, candidates: list[EvidenceCandidate]) -> dict[str, float]:
        api_key = os.getenv("MODEL_API_KEY")
        if not self.llm_enabled or not api_key or not candidates:
            return {}
        try:
            from openai import OpenAI

            with httpx.Client(trust_env=False) as http_client:
                client = OpenAI(
                    api_key=api_key,
                    base_url=os.getenv("MODEL_BASE_URL"),
                    timeout=float(os.getenv("RERANK_LLM_TIMEOUT_SECONDS", "20")),
                    http_client=http_client,
                )
                items = [
                    {"id": item.candidate_id, "text": item.text[:500], "type": item.evidence_type}
                    for item in candidates
                ]
                response = client.chat.completions.create(
                    model=os.getenv("RERANK_LLM_MODEL_NAME") or os.getenv("MODEL_NAME", "qwen-plus"),
                    temperature=0,
                    max_tokens=1000,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a relevance judge. Return JSON only as "
                                "{\"scores\":[{\"id\":\"...\",\"score\":0.0}]}. "
                                "Score how directly each evidence item supports the user query from 0 to 1."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"query": context.original_query, "intent": context.intent, "candidates": items},
                                ensure_ascii=False,
                            ),
                        },
                    ],
                )
            payload = self._parse_json(response.choices[0].message.content or "")
            return self._bounded_scores(
                {str(item.get("id")): float(item.get("score", 0)) for item in payload.get("scores", [])}
            )
        except Exception as exc:
            logger.warning("LLM relevance judge unavailable; using deterministic rerank: %s", exc)
            return {}

    @staticmethod
    def _rule_score(context: QueryContext, candidate: EvidenceCandidate) -> float:
        query_terms = set(context.keywords)
        text = f"{candidate.text} {json.dumps(candidate.metadata, ensure_ascii=False, default=str)}".lower()
        matched = sum(1 for term in query_terms if term in text)
        lexical = matched / max(len(query_terms), 1)
        route_coverage = min(len(candidate.hit_sources) / 4, 1.0)
        entity_match = 0.0
        for key in ["scenic_spot", "location", "sentiment", "risk_level"]:
            value = context.parameters.get(key)
            if value and str(value).lower() in text:
                entity_match += 0.25
        return min(0.65 * lexical + 0.20 * route_coverage + 0.15 * min(entity_match, 1.0), 1.0)

    @staticmethod
    def _parse_json(text: str) -> dict:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        return json.loads(match.group(0) if match else text)

    @staticmethod
    def _bounded_scores(scores: dict[str, float]) -> dict[str, float]:
        return {key: max(0.0, min(float(value), 1.0)) for key, value in scores.items()}


class EvidenceCompressor:
    def __init__(self, max_chars: int = 420):
        self.max_chars = max(120, int(max_chars))

    def compress(self, context: QueryContext, candidates: list[EvidenceCandidate]) -> list[EvidenceCandidate]:
        seen_sentences: set[str] = set()
        for candidate in candidates:
            sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", candidate.text) if item.strip()]
            ranked = sorted(
                sentences or [candidate.text],
                key=lambda sentence: sum(1 for keyword in context.keywords if keyword in sentence),
                reverse=True,
            )
            selected = []
            char_count = 0
            for sentence in ranked:
                fingerprint = re.sub(r"\s+", "", sentence)
                if fingerprint in seen_sentences:
                    continue
                if selected and char_count + len(sentence) > self.max_chars:
                    continue
                selected.append(sentence)
                seen_sentences.add(fingerprint)
                char_count += len(sentence)
                if char_count >= self.max_chars:
                    break
            candidate.compressed_text = "".join(selected)[: self.max_chars] or candidate.text[: self.max_chars]
            candidate.metadata["compression"] = {
                "original_chars": len(candidate.text),
                "compressed_chars": len(candidate.compressed_text),
            }
        return candidates
