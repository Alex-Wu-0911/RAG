# 本地 PostgreSQL

本步骤只运行 PostgreSQL，不创建业务表、不修改 Java 配置。

## 文件说明

- compose.yaml：数据库容器、端口、数据卷和健康检查。
- .env.example：可提交的环境变量示例。
- .env：本地实际配置，已加入当前目录的 .gitignore；首次创建时生成随机密码。

## 启动与检查

先启动 Docker Desktop，切换到本目录后运行：

```powershell
docker compose up -d --wait postgres
docker compose ps
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user;"'
```

连接地址为 localhost，默认宿主机端口 15432（容器内部仍为 5432），数据库 knowledge_agent，用户 rag，密码查看本机 .env。若端口已被使用，可修改 POSTGRES_PORT 后重试。

## 数据持久化

postgres_data 命名卷保存数据。docker compose stop 或 docker compose down 不删除命名卷，之后重新启动可继续使用。

不要使用 docker compose down -v，除非明确需要删除全部本地数据库数据。

POSTGRES_DB、POSTGRES_USER、POSTGRES_PASSWORD 用于空数据卷的首次初始化。修改 .env 不会自动修改已经创建的数据库账号或密码。

## 当前边界

采用 PostgreSQL 16 官方镜像。当前用户是镜像初始化的本地开发管理员；后续分离应用账号。pgvector 扩展和向量表留到 Python/RAG 阶段再安排，不假定当前镜像已包含扩展。

下一步才将 Spring Boot 的 db profile 连接到此数据库。Compose 的 .env 不会自动成为 Java 进程的环境变量。
