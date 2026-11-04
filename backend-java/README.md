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

数据库表和 Flyway 迁移尚未实现，后续迁移文件放在 src/main/resources/db/migration。
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
- 当前没有业务迁移 SQL，Flyway 可能提示没有迁移，并创建 flyway_schema_history 元数据表；这不等于已经创建用户表。
- 本任务不创建 User 实体、Repository 或用户表，下一步才实现。
