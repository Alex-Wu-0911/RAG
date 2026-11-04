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

默认执行 9 项错误处理测试。显式提供 DB_URL、DB_USER、DB_PASSWORD 后，另执行 7 项 PostgreSQL Repository/Service/Controller 测试，总计 16 项。

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

V4__create_documents.sql 已创建 biz.documents。本步尚未添加 Document 实体、文件存储或上传接口。

字段：id、knowledge_base_id、filename、storage_key、size_bytes、content_hash、status、created_at、updated_at。

- knowledge_base_id 外键指向知识库；不能上传到不存在的知识库。
- filename 是展示名，storage_key 是相对存储标识；后续 Java 根据存储根目录定位文件。
- content_hash 为文件内容 SHA-256；knowledge_base_id + content_hash 唯一，在同一知识库内去重，跨知识库允许相同文件。
- size_bytes 以字节记录文件大小；非空文件由数据库约束保证，20MB 上限由上传接口配置检查。
- status 初始 PENDING，处理时 PROCESSING，成功 READY，失败 FAILED。READY 表示后续 Python 已完成处理、可参与检索，不表示仅仅上传成功。
- 当前表不包含文档正文、分块、Embedding 或向量；这些由 Python 阶段处理。
- updated_at 的数据库默认值只在插入时生效，后续由应用维护。

已验证 V4 执行成功、9 个字段及外键与去重约束存在。后续结构修改继续新增迁移。
