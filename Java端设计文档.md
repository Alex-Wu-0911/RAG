# 研发知识库 Agent 服务——Java 端设计文档

## 1. 设计原则

Java 端为 Agent/RAG 提供业务接口与数据管理。采用单个 Spring Boot 应用，代码尽量简单、易读，按实际需求逐步实现。

移除用户模型、认证、权限、成员管理和开发用户配置。知识库不区分所有者，后续接口直接操作知识库资源。

## 2. 技术与职责

| 组件 | 用途 |
| --- | --- |
| Java 21、Maven | 开发与构建 |
| Spring Boot 3.5.16、Spring MVC | REST、SSE |
| Validation | 接口参数校验 |
| Spring Data JPA | 实体持久化和查询 |
| PostgreSQL 16、Flyway | 业务数据及结构迁移 |
| Actuator | 健康检查 |
| RestClient | 后续调用 Python HTTP 服务 |

Java 管理知识库、原始文件、文档元数据、入库任务、会话和运行记录。Python 处理解析、分块、Embedding、检索、rerank 与 Agent 编排，不在 Java 中重复实现模型流程。

## 3. 包结构

```text
knowledgeagent/
├── KnowledgeAgentApplication
├── common/          错误响应、分页、requestId
├── knowledgebase/   知识库实体、查询、业务逻辑与接口
├── document/        后续文档管理
├── ingestion/       后续入库任务
├── conversation/    后续会话和消息
├── agent/           后续问答运行记录
└── client/          后续 Python 客户端
```

每个业务模块按需要使用 entity、repository、service、dto、controller；不为每个类额外生成接口和实现类。

Controller 接收请求，Service 实现用例与事务，Repository 读写数据库。Entity 不直接作为 HTTP 响应返回。

## 4. 知识库数据模型

表：biz.knowledge_bases。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID | 主键 |
| name | VARCHAR(100) | 必填、非空，允许同名 |
| description | VARCHAR(1000) | 无描述时为空字符串 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 修改时间 |

索引为 created_at DESC、id DESC，支持稳定分页。数据库没有 owner_id，也不需要用户表。

KnowledgeBase 使用 @Entity/@Table 映射表，@GeneratedValue 生成 UUID，@PrePersist 设置时间，@PreUpdate 更新 updatedAt。直接执行 SQL 不触发实体回调。

## 5. Repository 与 Service

KnowledgeBaseRepository 继承 JpaRepository：

- save：保存知识库。
- findById：按 ID 查询。
- findAllByOrderByCreatedAtDescIdDesc：分页返回全部知识库。

KnowledgeBaseService：

- create(name, description)：创建并返回 KnowledgeBaseResponse。
- list(page, size)：按固定顺序分页，size 为 1～100。
- getById(id)：返回详情，不存在抛 RESOURCE_NOT_FOUND。

Service 默认只读事务，create 使用写事务。分页返回 items、page、size、total。移除了 CurrentUserProvider 和所有者过滤。

## 6. 目标 HTTP 接口

知识库创建、列表、详情，文档上传、列表、详情和健康检查已实现；其他接口尚待开发。

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| POST | /api/knowledge-bases | 创建，返回 201 |
| GET | /api/knowledge-bases | 分页列表 |
| GET | /api/knowledge-bases/{id} | 详情 |
| PATCH | /api/knowledge-bases/{id} | 修改名称、描述 |
| POST | /api/knowledge-bases/{id}/documents | 上传文档 |
| GET | /api/knowledge-bases/{id}/documents | 文档列表 |
| GET / DELETE | /api/documents/{id} | 文档详情、删除 |
| GET | /api/ingestion-tasks/{id} | 查询任务状态 |
| POST | /api/ingestion-tasks/{id}/retry | 重试任务 |
| POST | /api/conversations | 创建会话 |
| POST | /api/conversations/{id}/messages | 问答入口，后续 SSE |
| GET | /api/conversations/{id}/messages | 历史消息 |
| GET | /api/agent-runs/{id} | 运行记录 |
| POST | /api/agent-runs/{id}/cancel | 取消运行 |
| GET | /actuator/health | 健康检查，已可用 |

不需要 Session、JWT、CSRF Token 或当前用户参数。请求 DTO 保留必要的非空和长度校验。

## 7. 后续表结构规划

| 表 | 主要数据 |
| --- | --- |
| documents | 知识库 ID、文件名、存储标识、哈希、大小、状态、有效索引版本 |
| ingestion_tasks | 文档 ID、状态、阶段、尝试次数、错误、下次执行时间 |
| conversations | 知识库 ID、标题、创建时间 |
| messages | 会话 ID、角色、正文、状态、创建时间 |
| agent_runs | 会话 ID、运行状态、耗时、错误与工具次数 |
| message_citations | 消息 ID、文档和片段标识 |
| agent_tool_calls | 运行 ID、工具名称、序号、状态与结果摘要 |

这些表按阶段增加，不提前生成完整代码。所有表都不包含用户归属或成员授权字段。

## 8. 文档与任务流程

1. 接收 Markdown 或文本型 PDF，检查格式和大小。
2. 保存文件并计算 SHA-256，同一知识库内按内容去重。
3. 创建文档及任务记录，返回标识。
4. Python 领取任务，读取文档，解析分块并写向量。
5. Python 回传结果，Java 更新任务及文档状态。
6. 失败任务支持重试，未完成索引不参与问答。

原始文件使用 Docker MinIO 对象存储，bucket 为 rag-documents；storage_key 保存服务生成的对象 Key。Java 不直接写本地文件目录。初期无需消息队列，先同步打通，再实现数据库任务轮询。心跳、租约、超时恢复在任务阶段按需补充。

## 9. Python 通信与问答

Java 使用 HTTP 调用 FastAPI，将问题、知识库 ID、运行 ID、历史消息和运行限制交给 Python。后续 Python 返回答案片段、引用、工具摘要与完成状态。

Java 不负责选择检索工具或编排 Agent。模型调用期间不保持数据库事务。跨服务设置连接和读取超时，保留 requestId 关联日志。

初期先返回普通 JSON，跑通后再接 SSE、取消与运行状态。文件删除后停止参与检索，历史引用标记失效。

## 10. 异常处理

ErrorResponse 包含 code、message、requestId、fieldErrors。BusinessException 表达预期业务错误；GlobalExceptionHandler 处理 MVC 异常，RequestIdFilter 关联请求与日志。

保留 400 参数错误、404 资源不存在、409 状态冲突、413 文件过大、415 类型错误、500 服务异常等必要状态。已删除用户认证错误码。

## 11. 迁移与配置

- V1/V2 已执行，保留原文件以保持 Flyway 校验和。
- V3 删除历史用户表、owner_id、关联外键及所有者索引，新增知识库全量分页索引。
- V3 保留已有知识库，新建数据库执行全部迁移后的结构也一致。
- local profile 用于无数据库的骨架验证；db profile 启用完整数据库功能，不需要 dev profile。
- DB_URL 默认 jdbc:postgresql://localhost:15432/knowledge_agent；账号与密码通过环境变量传入。
- Flyway 负责建表改表，Hibernate ddl-auto=validate 检查实体映射。

## 12. 验证与后续顺序

现有测试包括统一错误处理，以及真实 PostgreSQL 的知识库保存、修改、全量分页、Service 创建和详情查询。数据库测试中的业务数据通过事务回滚；结构迁移实际生效。

下一步按顺序实现：文档上传 → 入库任务 → Python 通信 → 会话问答 → SSE 与 Agent 记录。只增加关键路径需要的测试与配置。
