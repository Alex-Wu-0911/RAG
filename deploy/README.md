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

采用 pgvector/pgvector:0.8.7-pg16-bookworm 镜像，在 PostgreSQL 16 上增加 pgvector 扩展。继续使用 postgres_data 数据卷。镜像包含扩展文件，但每个数据库还需要执行 CREATE EXTENSION 才能启用；具体操作见下文。

下一步才将 Spring Boot 的 db profile 连接到此数据库。Compose 的 .env 不会自动成为 Java 进程的环境变量。

## MinIO 对象存储

Java 后续通过 S3 API 上传原始文件到 MinIO，数据库 storage_key 保存对象 Key。暂不写 Java 本地 storage 文件夹。

### 启动

在 deploy 目录执行：

```powershell
docker compose up -d minio
docker compose run --rm minio-init
docker compose ps
```

minio-init 是一次性 bucket 初始化工具，成功创建后退出；再次执行不会重复创建 bucket。

### 地址与登录

- S3 API：http://localhost:19000，供电脑上运行的 Java/Python 使用。
- 控制台：http://localhost:19001，供浏览器登录查看文件。
- Docker 网络中的服务使用 http://minio:9000，不使用 localhost:19000。
- 用户名、密码分别为本机 .env 的 MINIO_ROOT_USER、MINIO_ROOT_PASSWORD。
- bucket 默认为 rag-documents，可理解为存放文档对象的容器。
- Java 的 MinIO 客户端尚未实现，Compose 环境变量也不会自动进入 Java 进程。

### 持久化

minio_data 命名卷挂载到 /data，容器重建后对象仍保留。数据仍占用本机 Docker 磁盘，由 MinIO 管理，不是云端存储。

不要执行 docker compose down -v，除非明确需要删除 PostgreSQL 和 MinIO 的全部本地数据。

本地开发使用 Silo（PGSTY 维护的 MinIO 社区分支），采用已验证可公开访问的 Docker Hub 版本并固定镜像摘要。保留 minio 服务名、MINIO_* 变量及 S3 接口。初始化工具使用同一镜像内置的 mcli，不再依赖官方 Quay 镜像。原数据库配置与数据卷保留不变。

### 验证

```powershell
Invoke-WebRequest http://localhost:19000/minio/health/live
docker compose run --rm --entrypoint /bin/sh minio-init -c 'mcli alias set storage http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mcli ls storage'
```

健康接口应返回 HTTP 200，对象列表中应出现 rag-documents。也可直接在控制台查看 bucket。

### 镜像拉取 401 的处理

原来的 quay.io/minio/minio 与 quay.io/minio/mc 已无法公开拉取，配置现改用 docker.io/pgsty/silo；不是要求用户登录 Quay。

在项目根目录也可以用下面的命令启动，避免找不到 Compose 文件：

```powershell
docker compose -f deploy/compose.yaml pull minio minio-init
docker compose -f deploy/compose.yaml up -d minio
docker compose -f deploy/compose.yaml run --rm minio-init
```

在 deploy 目录执行时省略 -f deploy/compose.yaml 即可。凭证、端口、bucket 和数据卷不变，无需删除现有卷。

镜像资料：https://github.com/pgsty/silo

## 启用 pgvector

在项目根目录的 PowerShell 执行：

```powershell
docker compose -f deploy/compose.yaml pull postgres
docker compose -f deploy/compose.yaml up -d --wait postgres
docker compose -f deploy/compose.yaml exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/rag/enable-pgvector.sql'
```

第二条命令会重建 PostgreSQL 容器，期间数据库短暂断开；原数据卷、业务表和连接端口继续使用，不要删除数据卷。

最后一条执行本目录的 enable-pgvector.sql，应该返回扩展版本 0.8.7 和 dimensions = 3。脚本可以重复执行，适用于已经存在的数据库；不依赖只在空数据卷上运行的初始化脚本。

当前只准备向量存储能力，还没有创建文本块表或写入 Embedding。后续再由 Python 保存文本块和对应向量。

资料：https://github.com/pgvector/pgvector#docker