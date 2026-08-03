# 漓观：桂林旅游舆情智能分析平台

漓观是一个面向桂林旅游场景的开源舆情分析与证据研判系统。项目将新闻、游客评论、投诉和社交平台文本处理为结构化旅游事件，并通过 FAISS、BM25、MySQL 与 Neo4j 为大模型提供可追溯证据。

系统不是通用聊天模板。当前产品界面和后端链路均围绕桂林旅游舆情构建，包括舆情总览、智能研判、事件监测、知识图谱、数据管道和系统状态。

## 核心能力

- 多源数据导入：支持 CSV、JSON、JSONL 新闻、评论、投诉和社交文本。
- 文本处理链路：清洗、去重、切分、要素抽取、实体标准化和事件聚合。
- 混合检索：FAISS 语义召回与 BM25 关键词召回融合。
- 图谱分析：在 Neo4j 中关联事件、景区、地点、来源、文档和主题。
- 事件查询：按景区、地点、情感、风险、时间和关键词筛选。
- 证据问答：回答同时返回来源证据、事件证据和图谱关系。
- 充分性控制：舆情事实在证据不足时不允许模型编造。
- 通识兜底：非实时通识问题在本地零召回时可由大模型回答，并明确标注无本地证据。
- 全链路留痕：保存问答记录、检索版本、证据片段和关联事件。

## 处理链路

```text
原始新闻 / 评论 / 平台舆情
  -> 数据导入
  -> MinIO 保存 raw
  -> MySQL 创建 document
  -> 文本清洗并由 MinIO 保存 clean
  -> content_hash 去重
  -> 文本切分 chunk
  -> 要素抽取与实体标准化
  -> 事件聚合并由 MySQL 保存 event/chunk/task
  -> Neo4j 构建事件图谱
  -> Embedding
  -> FAISS 索引与 BM25 索引
  -> index_version 记录
  -> 用户问题预处理、意图识别与参数抽取
  -> Query Rewrite / Expansion
  -> FAISS top 30 / BM25 top 30 / MySQL 事件 top 20 / Neo4j 图谱 top 20
  -> 候选池合并、去重、分数归一化与粗排融合
  -> 规则 + LLM relevance judge Rerank
  -> TopK 截断、多样性控制与证据压缩
  -> 证据充分性检查与 Prompt 组装
  -> 大模型生成与答案引用校验
  -> SSE 回答 + 来源 + 事件 + 图谱证据
  -> QA、t_qa_evidence 与检索评估日志持久化
```

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Naive UI、ECharts、UnoCSS |
| API | Sanic、PyMySQL、SQLAlchemy |
| Agent | LangGraph、LangChain、OpenAI Compatible API |
| 检索 | FAISS、BM25、Jieba、Embedding API |
| 数据 | MySQL 8、MinIO、Redis、Neo4j 5 |
| 部署 | Docker Compose、uv、pnpm |

## 项目结构

```text
agent/tourism/               桂林旅游舆情 Agent、提示词和工具
common/                      数据库、对象存储、鉴权和证据协议
controllers/                 Sanic HTTP / SSE 接口
data/samples/                可重复导入的旅游舆情样例数据
docker/                      中间件编排与数据库初始化脚本
model/                       MySQL 业务模型
scripts/                     数据种子、图谱重建和检索评估脚本
services/tourism/            清洗、抽取、聚合、图谱、索引与检索服务
web/                         桂林旅游舆情分析控制台
serv.py                      Sanic 服务入口
```

## 本地启动

### 1. 环境要求

- Python 3.11
- Node.js 18 或更高版本
- pnpm 9 或更高版本
- Docker Desktop 或 Docker Engine + Compose
- 可用的 OpenAI Compatible 对话模型与 Embedding 模型

### 2. 启动中间件

```bash
cp docker/.env.template docker/.env
docker compose -f docker/docker-compose.yaml --env-file docker/.env up -d
```

默认端口：

| 服务 | 地址 |
| --- | --- |
| MySQL | `127.0.0.1:13006` |
| Redis | `127.0.0.1:16379` |
| MinIO API | `http://127.0.0.1:19000` |
| MinIO Console | `http://127.0.0.1:19001` |
| Neo4j Browser | `http://127.0.0.1:7474` |
| Neo4j Bolt | `bolt://127.0.0.1:7687` |

首次创建 MySQL 数据卷时，Compose 会自动执行 `docker/init_sql.sql`。

### 3. 配置后端

```bash
cp .env.example .env.local
```

编辑 `.env.local`，至少配置：

- `MODEL_NAME`、`MODEL_BASE_URL`、`MODEL_API_KEY`
- `EMBEDDING_MODEL_NAME`、`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`
- MySQL、MinIO、Redis、Neo4j 的本地连接信息
- 一个随机且足够长的 `JWT_SECRET_KEY`

`.env.local` 已被 Git 忽略，不要提交真实密钥。

### 4. 安装后端依赖

```bash
uv sync
```

初始化或升级已有数据库：

```bash
uv run python common/initialize_mysql.py
```

启动 API：

```bash
uv run python serv.py
```

后端默认地址：`http://127.0.0.1:8088`。

### 5. 安装并启动前端

```bash
cd web
pnpm install
pnpm dev
```

前端默认地址：`http://127.0.0.1:2048`。

开发环境初始账号：

```text
用户名：admin
密码：123456
```

公开部署前必须修改默认账号密码，并对密码进行哈希存储。

## 导入样例数据

仓库提供 12 条桂林旅游舆情测试记录：

```bash
uv run python scripts/seed_tourism_data.py --disable-llm-extraction
```

该命令会执行正式 `TourismPipelineService` 链路，并构建 MySQL 业务数据、Neo4j 图谱、FAISS 索引和 BM25 索引。移除 `--disable-llm-extraction` 后会启用配置的大模型抽取服务。

## 常用运维命令

```bash
# 重建图谱
uv run python scripts/rebuild_graph.py

# 清空旅游图谱后完整重建
uv run python scripts/rebuild_graph.py --clear

# 执行检索评估
uv run python scripts/evaluate_retrieval.py

# 构建前端生产包
cd web && pnpm build
```

## 回答策略

系统将问题分为三种回答策略：

| 策略 | 行为 |
| --- | --- |
| `evidence_grounded` | 检索到充分证据，模型只能依据来源、事件和图谱证据回答 |
| `evidence_required` | 舆情事实问题没有充分证据，不调用模型编造事实 |
| `general_fallback` | 非实时通识问题零召回，调用通用模型并明确提示无本地证据 |

召回和上下文预算通过 `VECTOR_RECALL_TOP_K`、`BM25_RECALL_TOP_K`、
`GRAPH_EXPAND_TOP_K`、`RERANK_TOP_K`、`FINAL_CONTEXT_TOP_K` 和
`RERANK_SCORE_THRESHOLD` 调整。召回 TopK 必须大于最终上下文 TopK。

## 数据边界

- MySQL 保存业务实体、任务、事件、索引版本、问答和证据记录。
- MinIO 保存原始文件、清洗文本与 FAISS/BM25 索引对象。
- Neo4j 只保存实体和关系，不保存完整原文。
- Redis 保存短期会话记忆，不作为长期证据来源。
- 测试数据中的来源 URL 使用 `example.test`，避免被误认为真实公开报道。

## 安全说明

- 不要提交 `.env.local`、API Key、生产数据库密码或 JWT 密钥。
- 当前默认账号仅供本地开发；生产环境应接入密码哈希、账号锁定和权限控制。
- 图谱查询使用固定参数化 Cypher 模板，不允许模型直接生成并执行任意 Cypher。
- SQL 查询和数据导入应继续遵守最小权限、文件大小和内容类型限制。

## 开源协议

本项目使用 [MIT License](LICENSE)。第三方依赖遵循各自许可证。
