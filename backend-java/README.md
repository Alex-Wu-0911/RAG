# Knowledge Agent Java Backend

项目重点为 Agent 和 RAG。Java 负责知识库、文档、入库任务、会话和 Python 服务调用，目前采用无用户模型，不需要登录或开发用户配置。

## 开发环境

- JDK 21、Maven 3.6.3 或更新版本。
- PostgreSQL 16：使用 deploy/compose.yaml 启动，宿主机端口 15432。
- IDEA 打开 pom.xml，Project SDK 与 Maven Runner JRE 选择 JDK 21。

## 启动

默认 local profile 仅验证工程骨架，不连接数据库，也不注册依赖数据库的业务 Service。

运行知识库业务时，设置以下环境变量，使用 db profile：

- DB_URL：jdbc:postgresql://localhost:15432/knowledge_agent
- DB_USER：rag
- DB_PASSWORD：本机 deploy/.env 中实际初始化的 POSTGRES_PASSWORD。

```powershell
mvn spring-boot:run '-Dspring-boot.run.profiles=db'
```

IDEA 中设置 Active profiles 为 db，Environment variables 填写上述变量；不再需要 dev profile。Spring Boot 不会自动读取 .env，.env.example 只作为字段参考。

默认端口 8080，健康检查 http://localhost:8080/actuator/health。数据库账号密码仅用于数据库连接，与已移除的应用用户体系无关。

## 代码结构

- knowledgebase/entity：知识库实体，映射 biz.knowledge_bases。
- knowledgebase/repository：保存、按 ID 查询、全量分页列表。
- knowledgebase/service：创建、列表、详情。
- knowledgebase/dto：返回 DTO。
- common/error：业务异常、错误码与统一错误响应。
- common/web：请求 ID、分页返回结构。
- document、ingestion、conversation、agent、client：后续实现。

已实现知识库创建、分页列表、详情 Controller；Security 依赖、配置和用户身份代码已移除。

## 数据库迁移

- V1、V2 是已执行的历史迁移，保持原样以维护校验和。
- V3__remove_users_and_ownership.sql 移除 owner_id、所有者外键、旧索引及 biz.users，保留已有知识库数据。
- 新建数据库会顺序执行 V1 → V2 → V3，最终也不包含用户表和所有者字段。
- 后续表结构变更新增迁移文件，不修改已执行版本。
- Hibernate ddl-auto=validate，Flyway 负责实际表结构变化。

## 知识库

字段：id、name、description、created_at、updated_at。

- 名称上限 100 字符、描述上限 1000 字符，名称允许重复。
- 使用 UUID 主键；创建及更新时间由 JPA 生命周期回调维护。
- 列表按 created_at DESC、id DESC 稳定分页，返回全部知识库。
- 详情按 ID 查询，不存在时返回 RESOURCE_NOT_FOUND。

## 测试

```powershell
mvn test
```

默认执行 9 项错误处理测试。显式提供 DB_URL、DB_USER、DB_PASSWORD 后，另执行 10 项 PostgreSQL Repository/Service/Controller 测试，总计 19 项。

数据库测试中的知识库数据自动回滚，但 Flyway 迁移会实际生效，请连接本地或专用测试数据库。

下一步：文档上传与元数据。

## 知识库接口

启用 db profile 后可用，无需登录。

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| POST | /api/knowledge-bases | 接收 name、description，返回 201、Location 和创建结果 |
| GET | /api/knowledge-bases?page=0&size=20 | 返回 items、page、size、total |
| GET | /api/knowledge-bases/{id} | 返回详情；不存在返回 404 |

创建请求示例：

```json
{
  "name": "研发知识库",
  "description": "存放部署手册与接口文档"
}
```

name 必填，最多 100 字符；description 可省略，最多 1000 字符。@Valid 触发参数校验，错误由 GlobalExceptionHandler 统一转换。

IDEA 请求示例见 requests/knowledge-bases.http：先创建，再把返回 id 填入 knowledgeBaseId 后查询详情。

Controller 测试通过真实 Service 和 PostgreSQL 验证创建、列表、详情与错误响应；测试写入的数据自动回滚。

## 文档阶段：V4 元数据表

V4__create_documents.sql 已创建 biz.documents。现已有 Document 实体、DocumentStatus、DocumentRepository 和对象存储上传接口。

字段：id、knowledge_base_id、filename、storage_key、size_bytes、content_hash、status、created_at、updated_at。

- knowledge_base_id 外键指向知识库；不能上传到不存在的知识库。
- filename 是展示名，storage_key 是 MinIO bucket 中的对象 Key；后续 Java 通过 MinIO 客户端访问文件。
- content_hash 为文件内容 SHA-256；knowledge_base_id + content_hash 唯一，在同一知识库内去重，跨知识库允许相同文件。
- size_bytes 以字节记录文件大小；非空文件由数据库约束保证，20MB 上限由上传接口配置检查。
- status 初始 PENDING，处理时 PROCESSING，成功 READY，失败 FAILED。READY 表示后续 Python 已完成处理、可参与检索，不表示仅仅上传成功。
- 当前表不包含文档正文、分块、Embedding 或向量；这些由 Python 阶段处理。
- updated_at 的数据库默认值只在插入时生效，后续由应用维护。

已验证 V4 执行成功、9 个字段及外键与去重约束存在。后续结构修改继续新增迁移。

## 文档阶段：实体与 Repository

- Document 映射 V4 的 9 个字段，构造时状态为 PENDING。
- DocumentStatus 使用 @Enumerated(EnumType.STRING) 持久化为状态名，不保存枚举序号。
- changeStatus 修改状态，@PreUpdate 在更新时维护 updatedAt；暂不引入状态机。
- knowledgeBaseId 直接保存 UUID，不引入 KnowledgeBase 实体关联。
- findByKnowledgeBaseIdAndContentHash 用于同库内容去重。
- findByKnowledgeBaseIdOrderByCreatedAtDescIdDesc 用于文档分页列表。

新增 3 项真实 PostgreSQL 测试：元数据保存读取与状态更新、同库查询及跨库重复内容、同库重复内容约束。全部 19 项测试通过，测试数据回滚。

已在 deploy/compose.yaml 配置 Docker MinIO；MinIO 客户端、上传 Service 和上传接口已实现，启动与使用方式见下文。

## 对象存储上传接口

### 启动配置

启用 `db,storage`，保留之前的 DB_URL、DB_USER、DB_PASSWORD，另外配置：

| Java 环境变量 | 填写内容 |
| --- | --- |
| MINIO_ENDPOINT | http://localhost:19000 |
| MINIO_ACCESS_KEY | deploy/.env 中 MINIO_ROOT_USER 的值 |
| MINIO_SECRET_KEY | deploy/.env 中 MINIO_ROOT_PASSWORD 的值 |
| MINIO_BUCKET | rag-documents |

.env.example 只提供模板，Java 不会自动加载 deploy/.env。IDEA 在 Run Configuration 的 Active profiles 填入 db,storage，并设置这些环境变量。

命令行在设置上述环境变量后运行：

```powershell
mvn spring-boot:run '-Dspring-boot.run.profiles=db,storage'
```

只启用 db 时知识库接口仍可用，但上传接口不注册，不要求提供对象存储配置。

### 请求

POST /api/knowledge-bases/{knowledgeBaseId}/documents，类型 multipart/form-data，字段名 file。

Postman 的 Body 选择 form-data，添加 file 并将其类型改成 File，选择 .md 或 .pdf 文件。不要自行填写 multipart boundary，交由客户端生成。

IDEA 可使用 requests/documents.http 和其中引用的 sample.md。先在 knowledge-bases.http 创建知识库，再填写实际 knowledgeBaseId。

- 新上传返回 201 和 DocumentResponse。
- 同知识库重复内容返回 200 和已有记录，即使文件名不同也不会新增对象。
- 新记录状态 PENDING，本步不解析、不调用 Python、不生成向量。
- 当前按扩展名接受 .md/.pdf，不进行完整文件格式解析；解析错误由后续 Python 处理。
- 文件上限 20MB；整个 multipart 请求上限 21MB，为表单头预留空间。
- Multipart 文件在 20MB 内保持内存缓冲，不由 Java 持久保存到本地 storage 文件夹；持久文件由 MinIO/Silo 管理。

对象 Key 为 知识库UUID/随机UUID.md（或 .pdf），原始文件名仅用于展示。数据库写入失败时尝试移除刚上传的对象。普通重复请求会复用记录；数据库唯一约束仍负责阻止并发重复写入。

### 阅读顺序

1. MinioConfiguration：创建 SDK 客户端。
2. DocumentController：接收 MultipartFile，调用 Service 并选择 201/200。
3. DocumentService：检查知识库和文件，计算 SHA-256、查重、上传、保存记录。
4. DocumentResponse：返回文档元数据，不暴露内部对象 Key。

MinIO SDK 8.6.0 使用 OkHttp 5，pom.xml 显式引入 okhttp-jvm 5.1.0，提供 Maven 下的 JVM 实现。

### 验证

新增 2 项真实 PostgreSQL + 对象存储的上传测试，显式设置 MINIO_ACCESS_KEY 及相关配置后启用。它们验证上传、读回原内容、去重和错误参数；测试数据库写入回滚，对象存储中的测试文件在结束时清理。全部 21 项测试已通过。
