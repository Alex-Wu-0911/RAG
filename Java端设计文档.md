# 研发知识库 Agent 服务——Java 端设计文档

## 1. 文档定位

本文依据根目录《需求设计文档.md》，描述 Spring Boot 业务后端的目标设计。项目规模定位为校招项目，采用单个 Java 应用按业务模块组织，不拆分多个 Java 微服务。

本文不代表功能已实现。当前仅有 Maven 工程、启动类、基础配置和 Security 配置；业务接口、数据库迁移与 Python 客户端均待开发。

## 2. 技术选型与职责

| 项目 | 方案 | 说明 |
| --- | --- | --- |
| 语言与构建 | Java 21、Maven | 与当前 pom.xml 一致 |
| 服务框架 | Spring Boot 3.5.16、Spring MVC | REST 接口与 SSE |
| 参数校验 | Jakarta Validation | 校验 DTO，不直接接收实体对象 |
| 认证授权 | Spring Security | 后续采用服务器端 Session，第一版不引入 JWT/Redis |
| 持久化 | Spring Data JPA、PostgreSQL | 普通业务 CRUD；任务领取等并发操作使用原生 SQL |
| 数据库迁移 | Flyway | Java 工程统一维护迁移版本 |
| Python 通信 | Spring RestClient；流式调用采用有界后台执行器 | HTTP 调用不占用数据库事务 |
| 文件存储 | 本地持久卷 | 生成随机存储标识，不使用用户文件名拼接路径 |
| 测试 | JUnit、Spring Boot Test、Spring Security Test | 已有依赖；数据库并发测试后续使用真实 PostgreSQL |

Java 负责用户、知识库权限、文件元数据、入库任务、会话、运行记录和对外接口。Python 负责解析、分块、Embedding、检索、rerank、Agent 编排与模型调用。Java 不重复实现 LangChain 或向量检索，不引入 Spring AI。

Session 保存于应用进程内，适用于第一版单实例部署；Java 重启后用户重新登录。水平扩容及共享 Session 不在当前范围。

## 3. 系统结构

```text
Postman / curl
      │ REST / SSE + Session
      ▼
Spring Boot :8080
      ├── PostgreSQL biz schema：业务数据
      ├── 文件持久卷：原始文档
      └── FastAPI :8000：模型问答与流式事件
                    ├── PostgreSQL ai schema：分块与向量
                    └── 模型 / Embedding 服务

Python worker ──内部 HTTP──► Java：领取任务、读取文件、心跳、提交结果
```

数据库使用一个 PostgreSQL 实例，按 biz、ai 两个 schema 划分写入职责。Java 拥有 biz 的写权限；Python 写 ai，读取检索所需的有效文档元数据。迁移文件统一由 Flyway 管理，Python 不在启动时自动建表。实际数据库账号授权在部署阶段落实。

原始文件通过 Java 内部下载接口交给 worker，Python 不接受外部传入的任意本地路径或下载 URL。

## 4. 包结构与分层

根包：`com.example.knowledgeagent`。

```text
knowledgeagent/
├── KnowledgeAgentApplication
├── config/          Security、HTTP 客户端、执行器配置
├── common/          异常、错误响应、分页、请求关联标识
├── auth/            登录、注册、当前用户
├── knowledgebase/   知识库、成员与权限策略
├── document/        上传、元数据、原始文件存储、删除
├── ingestion/       任务领取、租约、重试与结果提交
├── conversation/    会话、消息、流式输出
├── agent/           问答运行状态、工具执行摘要
└── client/          Python 服务客户端与通信 DTO
```

业务模块内部按需要使用 controller、service、repository、entity、dto 子包；不为每个类机械增加接口和实现类。

- Controller：处理 HTTP、当前用户、DTO 校验与状态码，不直接操作 Repository。
- Service：实现用例、权限检查和事务边界。
- Repository：数据库访问，不决定业务权限。
- Entity：持久化模型，不作为接口响应返回。
- DTO：区分创建请求、修改请求、列表摘要和详情响应。
- Client：只处理跨服务协议，不直接修改业务实体。

跨模块通过 Service 调用；授权统一由 KnowledgeBaseAccessService 提供，避免每个 Controller 各写一套判断。

## 5. 认证与授权

### 5.1 Session 方案

- 注册使用 PasswordEncoder 哈希密码，用户名具有数据库唯一约束。
- 登录成功后轮换 Session ID，响应不包含密码哈希。
- 认证过滤器从 Session 建立当前用户，接口不信任请求体中的 userId。
- Cookie 配置 HttpOnly、SameSite；HTTPS 部署时启用 Secure。
- 保留 CSRF 防护；提供获取 CSRF Token 的接口，修改操作需携带 Token。
- 未登录返回 JSON 401，权限不足返回 JSON 403，不跳转 HTML 登录页。
- API 工具需保存 Cookie，并将 CSRF Token 放入后续写请求。

认证实现阶段配置 JSON 登录过滤器、成功/失败处理器与登出，不将当前骨架的 denyAll 直接改成 permitAll。

### 5.2 资源访问规则

- OWNER：可管理知识库、成员、文档；不可将自己作为只读成员移除。
- READER：只读知识库与文档信息，可创建自己的会话并提问。
- 会话、消息与运行记录必须同时满足“属于当前用户”和“当前具有知识库权限”。
- 每个会话固定绑定一个知识库，第一版不支持跨知识库会话。
- 对无法查看的资源可统一返回 404，避免通过 ID 枚举资源。
- 来源读取额外检查文档未删除、已完成入库且版本有效。

内部 `/internal/**` 使用独立 SecurityFilterChain 和服务凭证，与浏览器 Session 分离。凭证从环境变量读取、日志脱敏，内部接口仅在受控网络开放。

## 6. 数据模型

业务 ID 统一使用 UUID；时间使用 UTC 时间戳，接口以 ISO 8601 返回。以下为逻辑设计，字段长度与 SQL 在迁移阶段确定。

| 表（biz） | 主要字段 | 约束与用途 |
| --- | --- | --- |
| users | id、username、password_hash、created_at | username 唯一 |
| knowledge_bases | id、owner_id、name、description、created_at、updated_at | owner_id 关联 users |
| knowledge_base_members | knowledge_base_id、user_id、created_at | 联合唯一；表内成员均为 READER，OWNER 由知识库字段表示 |
| documents | id、knowledge_base_id、filename、content_hash、storage_key、size_bytes、status、active_generation、deleted_at | 同库未删除文档的 content_hash 唯一 |
| ingestion_tasks | id、document_id、status、stage、attempt_count、cycle_attempt_count、available_at、lease_token、lease_until、last_error_code、last_error_message、version | 每个文档一条可复用任务；document_id 唯一 |
| conversations | id、user_id、knowledge_base_id、title、created_at | user_id 和创建时间索引用于分页 |
| messages | id、conversation_id、role、content、status、created_at | 保存问题及回答；响应脱离实体 |
| agent_runs | id、conversation_id、user_message_id、assistant_message_id、status、idempotency_key、request_hash、started_at、finished_at、error_code、tool_count | 同会话幂等键唯一；一个会话最多一项活跃运行 |
| message_citations | id、message_id、document_id、generation、chunk_id、page_number | 记录来源标识，原文摘录按权限动态读取 |
| agent_tool_calls | id、run_id、sequence、tool_name、status、duration_ms、result_summary | run_id + sequence 唯一；摘要避免保存大量原文 |

Python 侧 ai schema 的 chunks 包含 document_id、generation、chunk_index、content、page_number、embedding；唯一键为 document_id + generation + chunk_index。

Embedding 维度随模型确定，第一版固定一个模型。更换模型须重新建索引，不混用不同维度或模型的向量。该细节由 Python 端设计进一步明确。

### 6.1 索引与迁移

- documents：按 knowledge_base_id、status 查询；使用部分唯一索引约束未删除文件的内容哈希。
- ingestion_tasks：按 status、available_at、lease_until 查待执行及超时任务。
- messages：按 conversation_id、created_at、id 稳定分页。
- agent_runs：按 conversation_id、created_at 查询；对活跃状态建立每会话唯一的部分索引。
- 外键字段建立与查询模式对应的索引，避免无目的地给所有字段加索引。
- Flyway 分批创建身份权限、文档任务、会话运行、AI 索引相关表；已执行迁移不原地修改。
- Hibernate 使用 ddl-auto=validate，禁止自动更新数据库结构。

## 7. 对外接口设计

以下为目标接口，当前均未实现；除公开认证接口和健康检查外，需要 Session，写接口另需 CSRF Token。

| 方法 | 路径 | 功能与限制 |
| --- | --- | --- |
| GET | /api/auth/csrf | 获取 CSRF Token |
| POST | /api/auth/register | 注册，返回 201 |
| POST | /api/auth/login | 登录并建立 Session |
| POST | /api/auth/logout | 登出并使 Session 失效 |
| GET | /api/auth/me | 当前用户摘要 |
| POST | /api/knowledge-bases | 创建知识库，返回 201 |
| GET | /api/knowledge-bases | 分页查询有权访问的知识库 |
| GET / PATCH | /api/knowledge-bases/{id} | 查看 / 修改名称描述，修改限 OWNER |
| GET / POST | /api/knowledge-bases/{id}/members | 查看成员 / 添加 READER，限 OWNER |
| DELETE | /api/knowledge-bases/{id}/members/{userId} | 移除成员，限 OWNER |
| POST | /api/knowledge-bases/{id}/documents | multipart 上传，限 OWNER；新任务返回 202，重复文件返回 200 |
| GET | /api/knowledge-bases/{id}/documents | 分页查询文档摘要 |
| GET / DELETE | /api/documents/{id} | 查看 / 逻辑删除，删除限 OWNER |
| GET | /api/ingestion-tasks/{id} | 查询状态；失败详情仅 OWNER 可见 |
| POST | /api/ingestion-tasks/{id}/retry | 手动重试最终失败任务，限 OWNER，返回 202 |
| POST | /api/conversations | 为指定知识库创建当前用户的会话 |
| GET | /api/conversations | 分页查询当前用户可访问的会话 |
| GET | /api/conversations/{id}/messages | 查询历史消息，重新校验资料有效性 |
| POST | /api/conversations/{id}/messages | 提交问题并返回 SSE；请求头携带 Idempotency-Key |
| GET | /api/agent-runs/{id} | 查询执行状态与最终结果，限会话所属用户 |
| POST | /api/agent-runs/{id}/cancel | 取消运行，重复取消幂等 |
| GET | /api/agent-runs/{id}/tool-calls | 查询脱敏后的工具执行轨迹 |
| GET | /api/messages/{id}/citations | 按当前权限返回有效引用 |
| GET | /actuator/health | 健康检查 |

第一版 SSE 使用 POST 请求流，curl/Postman 可直接读取，不承诺原生 EventSource 或事件重放支持。连接中断后，客户端通过运行查询接口获取最终状态，不自动重发问题。

### 7.1 响应、校验与分页

普通成功响应直接返回业务 DTO；分页响应统一包含 items、page、size、total。page 从 0 开始，size 默认 20、最大 100。

错误响应统一包含 code、message、requestId、fieldErrors。分别使用 400 参数错误、401 未登录、403 无权限、404 不可见资源、409 状态或幂等冲突、413 上传过大、415 不支持文件类型、429 容量限制、502 下游异常、504 下游超时。

错误 code 为稳定业务标识，例如 KB_ACCESS_DENIED、DOCUMENT_PARSE_FAILED、RUN_IN_PROGRESS、AI_SERVICE_TIMEOUT。接口不返回堆栈、数据库错误详情或内部文件路径。

问题长度、知识库名称、描述等在 DTO 中设置明确上限，实施时统一放入配置或常量。运行初始建议限制问题为 4000 字符，工具最多调用 4 次；这些是设计初值，需要评测后调整。

## 8. 文档上传与入库

### 8.1 上传流程

1. 校验 OWNER、20MB 限制、扩展名和文件内容特征；不只信任 Content-Type。
2. 将内容流写入临时文件，同时计算 SHA-256；原始文件名仅作展示。
3. 查询同库未删除文档的内容哈希，命中则清理临时文件并返回已有文档及任务。
4. 将文件原子移动到随机 storage_key 对应位置。
5. 在短事务中创建 document 与 ingestion_task；任务初始为 PENDING。
6. 若并发上传触发唯一约束，回滚当前事务后在新事务读取已有记录，清理本次多余文件。
7. 数据库写入失败时清理文件；定期扫描没有数据库引用的过期临时文件及孤立文件。

文件系统与数据库不具备共同事务，依靠顺序写入、补偿及清理任务恢复；不宣称跨存储强事务。

### 8.2 无消息队列的任务调度

Python worker 轮询 Java 内部领取接口。Java 在短事务中通过 FOR UPDATE SKIP LOCKED 选取已到执行时间的 PENDING 任务，修改为 PROCESSING，生成新的 lease_token 并设置 lease_until 后提交。

初始建议：轮询间隔 2 秒、租约 120 秒、心跳间隔 20 秒、每轮最多自动尝试 3 次；全部可配置，后续依据文档规模调整。

```text
PENDING → PROCESSING → SUCCEEDED
             │
             ├──可重试且未超限──► PENDING（延迟后再次执行）
             └──不可重试或超限──► FAILED
FAILED ──所有者手动重试──► PENDING
```

- attempt_count 记录累计领取次数，cycle_attempt_count 用于当前重试周期；手动重试只重置后者。
- 网络错误、限流等可重试；不支持格式、无可提取文本等直接失败。
- 心跳、阶段更新及完成提交必须携带 taskId 和 lease_token，以条件更新验证当前执行权。
- Java 定时恢复租约到期任务；旧 worker 的迟到心跳与完成提交被拒绝。
- Python 按 generation=lease_token 写入独立分块集合，单次尝试重复写入使用唯一约束保证幂等。
- Python 完成索引写入并提交事务后，再向 Java 提交完成结果。
- Java 校验租约、任务状态及文档未删除后，原子更新 active_generation 和任务成功状态。
- 检索仅使用 READY 文档的 active_generation；失败尝试和旧 generation 后台清理。
- 完成回调丢失时允许相同 lease_token 重复提交，成功状态返回一致结果；已经失效的 token 不得覆盖新结果。

### 8.3 删除文档

删除时短事务标记 deleted_at、撤销 active_generation，并使仍在执行的任务租约失效。检索必须同时过滤未删除、READY 和当前 generation；物理文件与旧向量异步清理。

删除后新请求不得返回资料；已经发送给客户端的字节无法追回。对于仍在生成的运行，标记为待取消并终止后续输出，历史回答按第 10 节重新检查。

## 9. Java 与 Python 的通信约定

### 9.1 Java 调用 Python

| 方法 | Python 路径 | 用途 |
| --- | --- | --- |
| GET | /health | 服务存活检查 |
| POST | /internal/chat/stream | 接收已验证的运行上下文，返回 SSE |
| POST | /internal/runs/{runId}/cancel | 幂等取消运行 |

问答请求包含 runId、requestId、userId、knowledgeBaseId、问题、经过权限检查的历史消息，以及工具次数与执行时限。用户不能自行覆盖内部授权字段。

初始连接超时采用已有配置 3 秒；流式读取无数据超时 60 秒，另外设置整个运行的总时限（建议初始 120 秒）。配置值是候选值，不代表已测性能。

普通短请求使用 RestClient；流式请求通过有界执行器读取响应，逐事件转交 Java 的 SseEmitter。不使用无上限线程池或缓存全部模型输出再一次性返回。队列已满时拒绝新增运行并返回容量错误。

### 9.2 Python 调用 Java

| 方法 | Java 内部路径 | 用途 |
| --- | --- | --- |
| POST | /internal/ingestion-tasks/claim | 原子领取任务，可返回无任务 |
| POST | /internal/ingestion-tasks/{id}/heartbeat | 续租及阶段更新 |
| GET | /internal/ingestion-tasks/{id}/content | 校验当前租约后读取原文件 |
| POST | /internal/ingestion-tasks/{id}/complete | 提交索引 generation 与结果 |
| POST | /internal/ingestion-tasks/{id}/fail | 提交结构化错误，由 Java 决定重试 |
| GET | /internal/agent-runs/{id}/access | 每次检索工具执行前确认当前用户权限与运行状态 |

内部服务凭证与执行租约分别验证：前者验证调用方，后者验证当前任务执行权。不得将内部凭证发给外部客户端。

Python 每次工具调用都检查知识库当前访问权，再通过数据库查询过滤文档有效状态和 generation。读取相邻片段同样校验归属，不能只凭 chunkId 读取。

## 10. 会话、SSE 与权限变更

### 10.1 提问流程

1. 验证会话归属、知识库权限、问题长度与并发限制。
2. 在短事务中写入用户消息、占位回答与 PENDING 运行，记录幂等键和请求哈希。
3. 同一会话的相同幂等键且请求一致，返回已有 runId，不重复生成；请求不同返回 409。
4. 提交事务后进入有界执行器，运行更新为 RUNNING，再调用 Python。
5. 建立 SSE 后先发送 run 事件，再发送 delta、citation、tool、done 或 error 事件，所有事件带 runId。
6. 结构化引用须由 Java 验证文档归属和有效性，再对外返回；模型自行拼出的来源不作为可信引用。
7. 收到完成事件后，在短事务中保存最终回答、引用、工具摘要和成功状态，再发送 done。
8. 提交执行器失败或下游异常时，将已创建运行更新为 FAILED，避免永久停在 PENDING。

工具事件只展示工具名称、状态及摘要，不输出模型内部推理。SSE 开始前可返回正常 HTTP 错误；开始后使用 error 事件表示失败，不能再修改已经发出的 HTTP 状态码。

### 10.2 取消、超时与断连

运行内部状态为 PENDING、RUNNING、CANCELLING、SUCCEEDED、FAILED、CANCELLED。客户端断连按第一版策略触发取消；显式取消与断连走同一逻辑。

- 使用条件更新处理取消与完成竞争；成功等终态不得被迟到回调覆盖。
- 若取消先落库，后续完成事件不能将运行改为成功；若成功先落库，取消接口返回已完成状态。
- Java 关闭下游读取资源并调用 Python 取消接口；下游取消失败也不允许继续向该客户端输出。
- 部分文本可保留为失败或取消记录，不能作为成功答案使用。
- Java 重启时将遗留活跃运行标记失败并尽力取消 Python 运行；第一版不恢复模型流。

### 10.3 权限撤销与历史数据

成员移除或文档删除提交后，Java 取消受影响的活跃运行；每次对外输出前再次检查访问状态和已知来源的有效性。并发撤权之前已发出的内容无法收回，不承诺撤回在途字节。

历史消息不仅过滤引用：如果回答依赖的任一来源已经删除、失效或无权访问，整个助手消息内容隐藏并返回不可用原因，防止答案正文继续泄露原文。第一版采取保守策略：会话引用的文档发生删除后，该会话既有助手回答不再用于后续模型上下文，必要时提示创建新会话。

读取运行结果、工具轨迹和引用时执行同样校验，不能通过另一接口绕过限制。Python 不持久化独立的、绕过 Java 权限过滤的会话记忆。

## 11. 事务与异常处理

- @Transactional 放在业务 Service 的数据库操作边界，文件上传、模型调用和长时间 SSE 不包在数据库事务内。
- 并发约束由数据库唯一索引与条件更新保证，不能只做“先查再写”。
- 外部 HTTP 超时、文件错误与数据库冲突映射为稳定业务异常，由全局异常处理器返回错误 DTO。
- 任务失败回调、取消与完成请求必须支持幂等，普通聊天请求不自动重试。
- 请求关联使用 X-Request-Id；外部输入限制长度和字符，缺失或无效时由 Java 生成，再传给 Python。
- 日志记录 requestId、taskId、runId、错误码和耗时，默认不记录文档正文、问题全文、凭证及密码。

## 12. 配置与运行方式

当前 application.yml 定义 8080 端口、20MB 上传上限、健康检查和 Python 服务地址；这些客户端配置尚未绑定实现。

- local 为默认 profile，禁用数据库和 Flyway 自动配置，仅用于骨架启动验证。
- db profile 启用 PostgreSQL、JPA validate 与 Flyway，要求 DB_PASSWORD 环境变量。
- local 与 db 不同时启用，避免数据库被 local 配置禁用。
- 后续增加 FILE_STORAGE_ROOT、INTERNAL_SERVICE_TOKEN、任务租约、执行器容量和运行时限配置，并通过配置类进行合法性校验。
- Java、Python 及数据库使用同一 Docker Compose 网络；数据库和原始文件使用持久卷。
- 目前没有 Compose 文件、数据库迁移或实际业务配置实现，不将部署设计表述为已可一键启动。

## 13. 测试与验收

| 测试层级 | 重点场景 |
| --- | --- |
| Service 单元测试 | 角色权限、状态转换、重试次数、错误映射 |
| MVC 与 Security 测试 | 未登录、CSRF、越权、字段校验、分页限制、错误响应 |
| PostgreSQL 集成测试 | 并发文件去重、SKIP LOCKED 领取、租约失效、部分唯一索引、事务回滚 |
| HTTP 客户端集成测试 | Python 超时、非正常状态、SSE 格式错误、取消及连接中断 |
| 端到端测试 | 上传到可检索、重试后无重复数据、带引用回答与撤权后内容隐藏 |

数据库集成测试使用 PostgreSQL，不用 H2 代替验证 PostgreSQL 特有锁与索引行为。Testcontainers 等依赖在实际实现该层测试时加入，当前 pom.xml 尚未包含。

并发验收至少覆盖：两个 worker 争抢任务、旧 worker 迟到提交、并发上传同一文件、删除与入库完成竞争、取消与回答完成竞争、成员撤权与流式输出竞争。

验收以可复现的请求及数据库结果为依据，不预先宣称 QPS、准确率提升或生产级可靠性。

## 14. 实施顺序

1. 公共错误响应、requestId、Python 客户端与最小服务联通。
2. 使用开发测试数据打通同步入库及基础问答，不向公网开放未鉴权接口。
3. 数据库迁移、Session 认证、知识库和统一权限检查。
4. 文档上传、去重、异步任务、租约与失败恢复。
5. 会话、SSE、取消、运行记录与历史资料权限过滤。
6. 配合 Python 加入有限轮 Agent、混合检索与 rerank，完善评测。
7. Docker Compose、接口说明及演示请求，完成关键异常与并发测试。

JWT、Redis、消息队列、对象存储、跨知识库问答和分布式 Java 部署均留待明确需求出现后再评估。
