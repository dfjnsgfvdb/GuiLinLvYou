from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TourismDocument:
    doc_id: str
    title: str
    content: str
    source_type: str = "manual"
    source_name: str = "unknown"
    source_url: str = ""
    author_name: str = ""
    publish_time: datetime | None = None
    raw_minio_key: str = ""
    clean_minio_key: str = ""
    content_hash: str = ""
    sentiment: str = "neutral"
    sentiment_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TourismChunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    char_count: int
    content_preview: str


@dataclass(slots=True)
class ExtractedOpinion:
    doc_id: str
    event_type: str
    summary: str
    sentiment: str
    sentiment_score: float
    topic: str
    scenic_spots: list[str]
    locations: list[str]
    keywords: list[str]


@dataclass(slots=True)
class TourismEvent:
    event_id: str
    event_name: str
    event_summary: str
    event_type: str
    topic: str
    sentiment: str
    risk_level: str
    heat_score: float
    negative_ratio: float
    growth_rate: float
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    main_scenic_spot: str
    main_location: str
    source_count: int
    document_count: int
    doc_ids: list[str]
    scenic_spots: list[str]
    locations: list[str]
