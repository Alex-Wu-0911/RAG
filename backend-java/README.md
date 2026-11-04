# Knowledge Agent Java Backend

当前为 Maven / Spring Boot 工程骨架，尚未实现用户、知识库、文档、问答等业务功能。

## 开发环境

- JDK 21
- Maven 3.6.3 或更新版本（本机已安装 Maven，无需 Wrapper）
- IntelliJ IDEA：打开本目录的 pom.xml，设为 Maven 项目；Project SDK 和 Maven Runner JRE 均选择 JDK 21。

## 启动

在本目录执行 `mvn spring-boot:run`，或运行 `KnowledgeAgentApplication`。
默认 local 配置不连接数据库。访问 `http://localhost:8080/actuator/health` 检查服务状态。
当前仅开放健康检查，业务接口默认拒绝访问。Security 依赖不代表已实现登录或 JWT。

## 数据库模式

创建 PostgreSQL 数据库后，设置 DB_URL、DB_USER、DB_PASSWORD，运行：

`mvn spring-boot:run -Dspring-boot.run.profiles=db`

已有迁移 V1__create_users.sql，创建 biz.users；后续迁移文件放在 src/main/resources/db/migration。
不要同时启用 local 和 db：local 会禁用数据库自动配置。

## 模块分工

- auth：用户认证与授权
- knowledgebase：知识库及成员管理
- document：文档元数据与上传
- ingestion：入库任务、重试和幂等
- conversation：会话及消息
- agent：Agent 运行记录（编排逻辑由 Python 负责）
- client：调用内部 Python 服务
- common：统一响应与异常等公共组件
- config：Spring 配置

上述空目录为后续业务实现预留。LangChain、LangGraph 和向量检索在 Python 服务实现，Java 暂不引入 Spring AI。

## 验证

`mvn verify`

当前包含统一异常处理与请求 ID 的 9 项 MVC 测试；尚无数据库或业务功能测试。

## 任务 2：使用 db profile 连接数据库

前提：在 deploy 目录执行 `docker compose up -d --wait postgres` 成功，宿主机端口为 15432。

### IDEA 启动设置

在 Run → Edit Configurations 中选择 KnowledgeAgentApplication：

1. Program arguments 填入 `--spring.profiles.active=db`；若界面提供 Active profiles，也可在该字段填写 db，二者择一。
2. Environment variables 分别添加：
   - DB_URL：`jdbc:postgresql://localhost:15432/knowledge_agent`
   - DB_USER：`rag`，若修改过 deploy/.env，则以实际初始化账号为准。
   - DB_PASSWORD：复制本机 deploy/.env 中 POSTGRES_PASSWORD 的实际值，不带变量名。
3. 使用 JDK 21。若原来的服务仍占用 8080，先停止原运行实例再启动。

backend-java/.env.example 只是字段参考；Spring Boot 不会自动读取 .env，Docker Compose 的环境变量也不会自动传给 Java。
不要把本机密码写入 application-db.yml 或提交到 Git。IDEA 的运行配置不要保存为包含密码的共享项目文件。

### PowerShell 启动方式

在 backend-java 目录中执行以下命令，密码使用安全输入框读取：

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:DB_URL = 'jdbc:postgresql://localhost:15432/knowledge_agent'
$env:DB_USER = 'rag'
$databaseCredential = Get-Credential -UserName rag -Message '输入 deploy/.env 中的数据库密码'
$env:DB_PASSWORD = $databaseCredential.GetNetworkCredential().Password
try {
    mvn spring-boot:run '-Dspring-boot.run.profiles=db'
} finally {
    Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
    $databaseCredential = $null
}
```

### 验收

- 启动日志显示激活 db profile，而非回退到 local。
- Hikari 数据源成功建立 PostgreSQL 连接，Flyway 能读取数据库信息。
- 应用启动成功，`GET http://localhost:8080/actuator/health` 返回 `UP`。db profile 下 Actuator 会检查数据库连接，公开响应仍不展示连接详情。
- 从任务 3 开始已有 V1 迁移：首次执行会创建 biz.users；再次启动仅校验，不重复执行。迁移历史表仍为 public.flyway_schema_history。
- 任务 2 只验证连接；任务 3 创建用户表；User 实体和 Repository 留到任务 4。

## 任务 3：第一份数据库迁移

文件：src/main/resources/db/migration/V1__create_users.sql。

- V1：版本号；双下划线之后是迁移描述，后缀为 .sql。
- biz：业务 schema，可理解为数据库内的命名空间。
- users：用户表，包含 id、username、password_hash、created_at。
- PRIMARY KEY：用户唯一标识；UNIQUE：约束用户名不能重复；NOT NULL：字段必须有值。
- 用户名暂按大小写区分，不允许空用户名或首尾空格。长度上限 50，后续注册 DTO 与之保持一致。
- password_hash 只存哈希；数据库非空约束不能判断一个字符串是否真的经过哈希，后续业务层必须使用 PasswordEncoder。
- TIMESTAMPTZ 保存时间点，查询显示取决于会话时区。
- Flyway 成功执行 V1 后会记录版本和校验和，再次启动不会重新建表。

已执行的 V1 不再修改；以后变更结构应新增 V2、V3 等迁移，不用 IF NOT EXISTS 掩盖用户表已经存在等结构问题。

可在 IDEA 数据库控制台中查看（未连接数据库工具也不影响服务运行）：

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'biz' AND table_name = 'users'
ORDER BY ordinal_position;

SELECT version, description, success
FROM public.flyway_schema_history
ORDER BY installed_rank;
```

本次验证：V1 成功执行，用户表四个字段、主键和用户名唯一约束存在；再次启动日志显示 No migration necessary。

## 知识库阶段：V2 迁移

V2__create_knowledge_bases.sql 已创建 biz.knowledge_bases，包含 id、owner_id、name、description、created_at、updated_at。

- owner_id 外键指向 biz.users.id，创建知识库前必须有对应用户。开发用户的初始化留到接口阶段完成，不需要提前实现登录。
- 同一用户可以创建同名知识库；名称上限 100 字符、描述上限 1000 字符；名称禁止空值及首尾空格。
- owner_id、created_at DESC、id DESC 联合索引用于所有者的稳定分页。
- updated_at 默认值只负责插入，后续更新由 Java 维护。
- 本步没有增加知识库实体、Repository、接口或成员表，也没有修改 V1。
- 本地数据库已成功执行 V2，表字段、外键及分页索引检查通过。已执行的 V2 不再修改，后续结构变更新增迁移。
