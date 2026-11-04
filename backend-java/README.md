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

目前没有业务 Controller；Security 依赖、配置和用户身份代码已移除。

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

默认执行 9 项错误处理测试。显式提供 DB_URL、DB_USER、DB_PASSWORD 后，另执行 5 项 PostgreSQL Repository/Service 测试。

数据库测试中的知识库数据自动回滚，但 Flyway 迁移会实际生效，请连接本地或专用测试数据库。

下一步：请求 DTO 和创建、列表、详情 Controller。
