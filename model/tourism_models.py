import datetime
import decimal
from typing import Optional

from sqlalchemy import BigInteger, DECIMAL, DateTime, Index, Integer, String, TIMESTAMP, Text, text
from sqlalchemy.dialects.mysql import JSON, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from model.db_connection_pool import Base


class TTourismIngestTask(Base):
    __tablename__ = "t_tourism_ingest_task"
    __table_args__ = (
        Index("uk_task_no", "task_no", unique=True),
        Index("idx_status", "status"),
        Index("idx_task_type", "task_type"),
        Index("idx_create_time", "create_time"),
        {"comment": "桂林旅游舆情数据处理任务表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="任务编号")
    task_type: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="import/clean/extract/index/graph")
    source_type: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="news/comment/csv/json/manual")
    file_name: Mapped[Optional[str]] = mapped_column(VARCHAR(255), comment="上传文件名")
    minio_raw_key: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="原始文件MinIO key")
    minio_clean_key: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="清洗结果MinIO key")
    status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="pending/running/success/failed")
    total_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="总记录数")
    success_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="成功数")
    failed_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="失败数")
    error_message: Mapped[Optional[str]] = mapped_column(Text, comment="错误信息")
    step_status: Mapped[Optional[dict]] = mapped_column(JSON, comment="各处理步骤状态")
    duration_ms: Mapped[Optional[int]] = mapped_column(BigInteger, server_default=text("'0'"), comment="总耗时毫秒")
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, comment="创建用户id")
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="开始时间")
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="完成时间")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    update_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TTourismDocument(Base):
    __tablename__ = "t_tourism_document"
    __table_args__ = (
        Index("uk_doc_id", "doc_id", unique=True),
        Index("uk_content_hash", "content_hash", unique=True),
        Index("idx_task_id", "task_id"),
        Index("idx_source", "source_type", "source_name"),
        Index("idx_publish_time", "publish_time"),
        Index("idx_sentiment", "sentiment"),
        {"comment": "桂林旅游舆情文档元数据表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="文档业务id")
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="关联导入任务id")
    title: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="标题")
    content_hash: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="清洗后正文hash")
    source_type: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="news/comment/complaint/social")
    source_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="来源平台")
    source_url: Mapped[Optional[str]] = mapped_column(VARCHAR(1000), comment="原文链接")
    author_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="作者或账号")
    publish_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="发布时间")
    raw_minio_key: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="原始文件key")
    clean_minio_key: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="清洗文本key")
    language: Mapped[Optional[str]] = mapped_column(VARCHAR(20), comment="语言")
    sentiment: Mapped[Optional[str]] = mapped_column(VARCHAR(20), comment="positive/neutral/negative")
    sentiment_score: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(6, 4), comment="情感分")
    extract_status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="抽取状态")
    graph_status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="图谱状态")
    index_status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="索引状态")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    update_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TTourismChunk(Base):
    __tablename__ = "t_tourism_chunk"
    __table_args__ = (
        Index("uk_chunk_id", "chunk_id", unique=True),
        Index("uk_doc_chunk", "doc_id", "chunk_index", unique=True),
        Index("idx_doc_id", "doc_id"),
        Index("idx_index_version", "index_version"),
        Index("idx_faiss_vector_id", "faiss_vector_id"),
        {"comment": "桂林旅游舆情文本切片表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="切片业务id")
    doc_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="文档业务id")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="文档内切片序号")
    content_hash: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="切片文本hash")
    content_preview: Mapped[Optional[str]] = mapped_column(VARCHAR(1000), comment="片段预览")
    token_count: Mapped[Optional[int]] = mapped_column(Integer, comment="token数")
    char_count: Mapped[Optional[int]] = mapped_column(Integer, comment="字符数")
    embedding_model: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="向量模型")
    index_version: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="索引版本")
    faiss_vector_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="FAISS内部向量id")
    bm25_doc_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="BM25文档id")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TTourismEvent(Base):
    __tablename__ = "t_tourism_event"
    __table_args__ = (
        Index("uk_event_id", "event_id", unique=True),
        Index("idx_topic", "topic"),
        Index("idx_sentiment", "sentiment"),
        Index("idx_risk_level", "risk_level"),
        Index("idx_heat_score", "heat_score"),
        Index("idx_last_seen_at", "last_seen_at"),
        Index("idx_scenic_location", "main_scenic_spot", "main_location"),
        {"comment": "桂林旅游舆情聚合事件表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="事件业务id")
    event_name: Mapped[Optional[str]] = mapped_column(VARCHAR(300), comment="事件名称")
    event_summary: Mapped[Optional[str]] = mapped_column(Text, comment="事件摘要")
    topic: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="主题")
    sentiment: Mapped[Optional[str]] = mapped_column(VARCHAR(20), comment="情感倾向")
    risk_level: Mapped[Optional[str]] = mapped_column(VARCHAR(20), comment="风险等级")
    heat_score: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment="热度分")
    negative_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(6, 4), comment="负面比例")
    growth_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment="增长率")
    first_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="首次出现时间")
    last_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="最近出现时间")
    main_scenic_spot: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="主景区")
    main_location: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="主地点")
    source_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="来源数量")
    document_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="文档数量")
    status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="active/merged/closed")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    update_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TTourismEventDocument(Base):
    __tablename__ = "t_tourism_event_document"
    __table_args__ = (
        Index("uk_event_doc", "event_id", "doc_id", unique=True),
        Index("idx_doc_id", "doc_id"),
        Index("idx_event_id", "event_id"),
        {"comment": "桂林旅游舆情事件文档关联表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="事件业务id")
    doc_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="文档业务id")
    match_score: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment="聚合匹配分")
    match_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="聚合原因")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TTourismIndexVersion(Base):
    __tablename__ = "t_tourism_index_version"
    __table_args__ = (
        Index("uk_index_version_type", "index_version", "index_type", unique=True),
        Index("idx_status", "status"),
        Index("idx_index_type", "index_type"),
        {"comment": "桂林旅游舆情索引版本表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    index_version: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="索引版本")
    index_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False, comment="faiss/bm25/graph")
    embedding_model: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="向量模型")
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="切片数")
    document_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="文档数")
    event_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("'0'"), comment="事件数")
    minio_index_key: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="索引文件MinIO key")
    metadata_minio_key: Mapped[Optional[str]] = mapped_column(VARCHAR(500), comment="索引元数据MinIO key")
    status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="building/active/inactive/failed")
    build_params: Mapped[Optional[dict]] = mapped_column(JSON, comment="构建参数")
    build_started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="构建开始时间")
    build_finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="构建完成时间")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TTourismAlert(Base):
    __tablename__ = "t_tourism_alert"
    __table_args__ = (
        Index("uk_alert_id", "alert_id", unique=True),
        Index("idx_event_id", "event_id"),
        Index("idx_alert_level", "alert_level"),
        Index("idx_status", "status"),
        Index("idx_create_time", "create_time"),
        {"comment": "桂林旅游舆情热点预警表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment="预警业务id")
    event_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="事件业务id")
    alert_level: Mapped[Optional[str]] = mapped_column(VARCHAR(20), comment="low/medium/high/critical")
    rule_code: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="规则编码")
    rule_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="规则名称")
    metric_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="指标名")
    metric_value: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(12, 4), comment="指标值")
    threshold_value: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(12, 4), comment="阈值")
    evidence_doc_ids: Mapped[Optional[dict]] = mapped_column(JSON, comment="触发证据文档")
    status: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="pending/confirmed/closed/false_positive")
    handler_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="处理人")
    handled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment="处理时间")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )
    update_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"
    )


class TQaEvidence(Base):
    __tablename__ = "t_qa_evidence"
    __table_args__ = (
        Index("idx_qa_record_id", "qa_record_id"),
        Index("idx_chat_uuid", "chat_id", "uuid"),
        Index("idx_doc_chunk", "doc_id", "chunk_id"),
        Index("idx_event_id", "event_id"),
        Index("idx_retrieval_version", "retrieval_version"),
        Index("idx_rank", "rank_no"),
        {"comment": "问答证据记录表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    qa_record_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="关联t_user_qa_record.id")
    chat_id: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="对话id")
    uuid: Mapped[Optional[str]] = mapped_column(VARCHAR(200), comment="单轮问答uuid")
    qa_type: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="问答类型")
    question: Mapped[Optional[str]] = mapped_column(Text, comment="用户问题")
    retrieval_version: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="检索版本")
    retrieval_mode: Mapped[Optional[str]] = mapped_column(VARCHAR(50), comment="vector/vector_bm25/hybrid_graph")
    evidence_type: Mapped[Optional[str]] = mapped_column(VARCHAR(32), comment="chunk/document/event/graph_relation")
    doc_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="文档业务id")
    chunk_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="切片业务id")
    event_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment="事件业务id")
    graph_relation_id: Mapped[Optional[str]] = mapped_column(VARCHAR(128), comment="图谱关系标识")
    source_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100), comment="来源")
    source_url: Mapped[Optional[str]] = mapped_column(VARCHAR(1000), comment="原文链接")
    score: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 6), comment="检索分")
    rank_no: Mapped[Optional[int]] = mapped_column(Integer, comment="排名")
    quote_text: Mapped[Optional[str]] = mapped_column(VARCHAR(2000), comment="引用片段")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, comment="额外元数据")
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间"
    )


class TTourismRetrievalLog(Base):
    __tablename__ = "t_tourism_retrieval_log"
    __table_args__ = (
        Index("idx_retrieval_qa_record", "qa_record_id"),
        Index("idx_retrieval_chat_uuid", "chat_id", "uuid"),
        Index("idx_retrieval_intent", "intent"),
        Index("idx_retrieval_policy", "answer_policy"),
        Index("idx_retrieval_create_time", "create_time"),
        {"comment": "企业级RAG检索评估日志"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    qa_record_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    chat_id: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    uuid: Mapped[Optional[str]] = mapped_column(VARCHAR(200))
    question: Mapped[Optional[str]] = mapped_column(Text)
    rewritten_query: Mapped[Optional[str]] = mapped_column(Text)
    intent: Mapped[Optional[str]] = mapped_column(VARCHAR(64))
    parameters_json: Mapped[Optional[dict]] = mapped_column(JSON)
    expansions_json: Mapped[Optional[dict]] = mapped_column(JSON)
    retrieval_config_json: Mapped[Optional[dict]] = mapped_column(JSON)
    route_counts_json: Mapped[Optional[dict]] = mapped_column(JSON)
    stage_counts_json: Mapped[Optional[dict]] = mapped_column(JSON)
    selected_candidates_json: Mapped[Optional[dict]] = mapped_column(JSON)
    latency_ms: Mapped[Optional[int]] = mapped_column(BigInteger, server_default=text("'0'"))
    answer_policy: Mapped[Optional[str]] = mapped_column(VARCHAR(32))
    citation_validation_json: Mapped[Optional[dict]] = mapped_column(JSON)
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
