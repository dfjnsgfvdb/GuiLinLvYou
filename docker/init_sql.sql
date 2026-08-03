CREATE DATABASE IF NOT EXISTS chat_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE chat_db;

DROP TABLE IF EXISTS t_tourism_retrieval_log;
DROP TABLE IF EXISTS t_qa_evidence;
DROP TABLE IF EXISTS t_tourism_alert;
DROP TABLE IF EXISTS t_tourism_index_version;
DROP TABLE IF EXISTS t_tourism_event_document;
DROP TABLE IF EXISTS t_tourism_event;
DROP TABLE IF EXISTS t_tourism_chunk;
DROP TABLE IF EXISTS t_tourism_document;
DROP TABLE IF EXISTS t_tourism_ingest_task;
DROP TABLE IF EXISTS t_user_qa_record;
DROP TABLE IF EXISTS t_user;

CREATE TABLE t_user (
  id INT NOT NULL AUTO_INCREMENT,
  userName VARCHAR(200) DEFAULT NULL,
  password VARCHAR(300) DEFAULT NULL,
  mobile VARCHAR(100) DEFAULT NULL,
  createTime DATETIME DEFAULT NULL,
  updateTime DATETIME DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (userName)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO t_user (id, userName, password, createTime, updateTime)
VALUES (1, 'admin', '123456', NOW(), NOW());

CREATE TABLE t_user_qa_record (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id INT DEFAULT NULL,
  uuid VARCHAR(200) DEFAULT NULL,
  conversation_id VARCHAR(100) DEFAULT NULL,
  message_id VARCHAR(100) DEFAULT NULL,
  task_id VARCHAR(100) DEFAULT NULL,
  chat_id VARCHAR(100) DEFAULT NULL,
  question TEXT,
  to2_answer LONGTEXT,
  to4_answer LONGTEXT,
  qa_type VARCHAR(100) DEFAULT NULL,
  file_key TEXT,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_user_id (user_id),
  KEY idx_chat_id (chat_id),
  KEY idx_qa_type (qa_type),
  KEY idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_ingest_task (
  id BIGINT NOT NULL AUTO_INCREMENT,
  task_no VARCHAR(64) NOT NULL,
  task_type VARCHAR(32) DEFAULT NULL,
  source_type VARCHAR(32) DEFAULT NULL,
  file_name VARCHAR(255) DEFAULT NULL,
  minio_raw_key VARCHAR(500) DEFAULT NULL,
  minio_clean_key VARCHAR(500) DEFAULT NULL,
  status VARCHAR(32) DEFAULT NULL,
  total_count INT DEFAULT 0,
  success_count INT DEFAULT 0,
  failed_count INT DEFAULT 0,
  error_message TEXT,
  step_status JSON DEFAULT NULL,
  duration_ms BIGINT DEFAULT 0,
  created_by BIGINT DEFAULT NULL,
  started_at DATETIME DEFAULT NULL,
  finished_at DATETIME DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  update_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_task_no (task_no),
  KEY idx_status (status),
  KEY idx_task_type (task_type),
  KEY idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_document (
  id BIGINT NOT NULL AUTO_INCREMENT,
  doc_id VARCHAR(64) NOT NULL,
  task_id BIGINT DEFAULT NULL,
  title VARCHAR(500) DEFAULT NULL,
  content_hash VARCHAR(64) DEFAULT NULL,
  source_type VARCHAR(32) DEFAULT NULL,
  source_name VARCHAR(100) DEFAULT NULL,
  source_url VARCHAR(1000) DEFAULT NULL,
  author_name VARCHAR(100) DEFAULT NULL,
  publish_time DATETIME DEFAULT NULL,
  raw_minio_key VARCHAR(500) DEFAULT NULL,
  clean_minio_key VARCHAR(500) DEFAULT NULL,
  language VARCHAR(20) DEFAULT NULL,
  sentiment VARCHAR(20) DEFAULT NULL,
  sentiment_score DECIMAL(6,4) DEFAULT NULL,
  extract_status VARCHAR(32) DEFAULT NULL,
  graph_status VARCHAR(32) DEFAULT NULL,
  index_status VARCHAR(32) DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  update_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_doc_id (doc_id),
  UNIQUE KEY uk_content_hash (content_hash),
  KEY idx_task_id (task_id),
  KEY idx_source (source_type, source_name),
  KEY idx_publish_time (publish_time),
  KEY idx_sentiment (sentiment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_chunk (
  id BIGINT NOT NULL AUTO_INCREMENT,
  chunk_id VARCHAR(64) NOT NULL,
  doc_id VARCHAR(64) NOT NULL,
  chunk_index INT NOT NULL,
  content_hash VARCHAR(64) DEFAULT NULL,
  content_preview VARCHAR(1000) DEFAULT NULL,
  token_count INT DEFAULT NULL,
  char_count INT DEFAULT NULL,
  embedding_model VARCHAR(100) DEFAULT NULL,
  index_version VARCHAR(64) DEFAULT NULL,
  faiss_vector_id BIGINT DEFAULT NULL,
  bm25_doc_id VARCHAR(64) DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_chunk_id (chunk_id),
  UNIQUE KEY uk_doc_chunk (doc_id, chunk_index),
  KEY idx_doc_id (doc_id),
  KEY idx_index_version (index_version),
  KEY idx_faiss_vector_id (faiss_vector_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_event (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  event_name VARCHAR(300) DEFAULT NULL,
  event_summary TEXT,
  topic VARCHAR(100) DEFAULT NULL,
  sentiment VARCHAR(20) DEFAULT NULL,
  risk_level VARCHAR(20) DEFAULT NULL,
  heat_score DECIMAL(10,4) DEFAULT NULL,
  negative_ratio DECIMAL(6,4) DEFAULT NULL,
  growth_rate DECIMAL(10,4) DEFAULT NULL,
  first_seen_at DATETIME DEFAULT NULL,
  last_seen_at DATETIME DEFAULT NULL,
  main_scenic_spot VARCHAR(100) DEFAULT NULL,
  main_location VARCHAR(100) DEFAULT NULL,
  source_count INT DEFAULT 0,
  document_count INT DEFAULT 0,
  status VARCHAR(32) DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  update_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_event_id (event_id),
  KEY idx_topic (topic),
  KEY idx_sentiment (sentiment),
  KEY idx_risk_level (risk_level),
  KEY idx_heat_score (heat_score),
  KEY idx_last_seen_at (last_seen_at),
  KEY idx_scenic_location (main_scenic_spot, main_location)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_event_document (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_id VARCHAR(64) NOT NULL,
  doc_id VARCHAR(64) NOT NULL,
  match_score DECIMAL(10,4) DEFAULT NULL,
  match_reason VARCHAR(500) DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_event_doc (event_id, doc_id),
  KEY idx_doc_id (doc_id),
  KEY idx_event_id (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_index_version (
  id BIGINT NOT NULL AUTO_INCREMENT,
  index_version VARCHAR(64) NOT NULL,
  index_type VARCHAR(20) NOT NULL,
  embedding_model VARCHAR(100) DEFAULT NULL,
  chunk_count INT DEFAULT 0,
  document_count INT DEFAULT 0,
  event_count INT DEFAULT 0,
  minio_index_key VARCHAR(500) DEFAULT NULL,
  metadata_minio_key VARCHAR(500) DEFAULT NULL,
  status VARCHAR(32) DEFAULT NULL,
  build_params JSON DEFAULT NULL,
  build_started_at DATETIME DEFAULT NULL,
  build_finished_at DATETIME DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_index_version_type (index_version, index_type),
  KEY idx_status (status),
  KEY idx_index_type (index_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_alert (
  id BIGINT NOT NULL AUTO_INCREMENT,
  alert_id VARCHAR(64) NOT NULL,
  event_id VARCHAR(64) DEFAULT NULL,
  alert_level VARCHAR(20) DEFAULT NULL,
  rule_code VARCHAR(64) DEFAULT NULL,
  rule_name VARCHAR(100) DEFAULT NULL,
  metric_name VARCHAR(100) DEFAULT NULL,
  metric_value DECIMAL(12,4) DEFAULT NULL,
  threshold_value DECIMAL(12,4) DEFAULT NULL,
  evidence_doc_ids JSON DEFAULT NULL,
  status VARCHAR(32) DEFAULT NULL,
  handler_user_id BIGINT DEFAULT NULL,
  handled_at DATETIME DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  update_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_alert_id (alert_id),
  KEY idx_event_id (event_id),
  KEY idx_alert_level (alert_level),
  KEY idx_status (status),
  KEY idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_qa_evidence (
  id BIGINT NOT NULL AUTO_INCREMENT,
  qa_record_id BIGINT DEFAULT NULL,
  chat_id VARCHAR(100) DEFAULT NULL,
  uuid VARCHAR(200) DEFAULT NULL,
  qa_type VARCHAR(100) DEFAULT NULL,
  question TEXT,
  retrieval_version VARCHAR(64) DEFAULT NULL,
  retrieval_mode VARCHAR(50) DEFAULT NULL,
  evidence_type VARCHAR(32) DEFAULT NULL,
  doc_id VARCHAR(64) DEFAULT NULL,
  chunk_id VARCHAR(64) DEFAULT NULL,
  event_id VARCHAR(64) DEFAULT NULL,
  graph_relation_id VARCHAR(128) DEFAULT NULL,
  source_name VARCHAR(100) DEFAULT NULL,
  source_url VARCHAR(1000) DEFAULT NULL,
  score DECIMAL(10,6) DEFAULT NULL,
  rank_no INT DEFAULT NULL,
  quote_text VARCHAR(2000) DEFAULT NULL,
  metadata_json JSON DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_qa_record_id (qa_record_id),
  KEY idx_chat_uuid (chat_id, uuid),
  KEY idx_doc_chunk (doc_id, chunk_id),
  KEY idx_event_id (event_id),
  KEY idx_retrieval_version (retrieval_version),
  KEY idx_rank (rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE t_tourism_retrieval_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  qa_record_id BIGINT DEFAULT NULL,
  chat_id VARCHAR(100) DEFAULT NULL,
  uuid VARCHAR(200) DEFAULT NULL,
  question TEXT,
  rewritten_query TEXT,
  intent VARCHAR(64) DEFAULT NULL,
  parameters_json JSON DEFAULT NULL,
  expansions_json JSON DEFAULT NULL,
  retrieval_config_json JSON DEFAULT NULL,
  route_counts_json JSON DEFAULT NULL,
  stage_counts_json JSON DEFAULT NULL,
  selected_candidates_json JSON DEFAULT NULL,
  latency_ms BIGINT DEFAULT 0,
  answer_policy VARCHAR(32) DEFAULT NULL,
  citation_validation_json JSON DEFAULT NULL,
  create_time TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_retrieval_qa_record (qa_record_id),
  KEY idx_retrieval_chat_uuid (chat_id, uuid),
  KEY idx_retrieval_intent (intent),
  KEY idx_retrieval_policy (answer_policy),
  KEY idx_retrieval_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
