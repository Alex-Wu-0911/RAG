# RAG AI Service

当前包含健康检查和问题回显接口，不接数据库、对象存储、LangChain 或模型。

## 目录

- main.py：应用及健康检查接口。
- requirements.txt：项目直接依赖。
- requirements.lock.txt：首次安装后的完整固定版本，便于复现。
- .venv：本项目的 Python 虚拟环境，不提交 Git。

## 启动

在 ai-service 目录运行，无需激活虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

- main：main.py 模块名。
- app：main.py 中的 FastAPI 实例变量。
- uvicorn：接收 HTTP 请求、运行 FastAPI 应用的 ASGI 服务程序。
- --reload：修改 Python 文件后自动重启，适用于本地开发。
- Ctrl+C：停止服务。

IDE 中选择 ai-service/.venv/Scripts/python.exe 作为解释器，避免依赖装在一个 Python 中、运行时却使用另一个。

## 第一个接口

打开 http://localhost:8000/health，返回：

```json
{"status":"UP"}
```

阅读 main.py：

1. from fastapi import FastAPI：导入框架。
2. app = FastAPI(...)：创建应用。
3. @app.get('/health')：把 GET /health 映射到下面的函数，类似 Spring 的 @GetMapping。
4. def health()：请求到达时调用函数；现在使用普通 def，后续需要异步 I/O 时再学 async def。
5. return 字典：FastAPI 自动转成 JSON 响应。
6. -> dict[str, str]：Python 返回类型提示，表示键和值都是字符串。

## 自动接口文档

- http://localhost:8000/docs：Swagger UI，展开 GET /health，点击 Try it out，再点击 Execute。
- http://localhost:8000/openapi.json：框架生成的接口描述，包含路径、参数与响应结构。

框架会读取路由和类型信息生成文档，不需要自己写 HTML。

## 重新安装环境

本机已创建 .venv 并安装依赖。换一台电脑时：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

健康检查与问题回显均可在 /docs 调用。本阶段学习 FastAPI 基础，不提前实现完整 RAG。

## 第二步：POST 请求体与 Pydantic

main.py 中 ChatRequest 继承 BaseModel，相当于 Java 的请求 DTO。

- knowledge_base_id: UUID：JSON 中是 UUID 字符串，解析后变成 Python UUID 对象。
- question: str：必填字符串。
- Field(min_length=1, max_length=4000)：问题长度为 1～4000，类似 @Size。
- @app.post('/chat')：定义 POST 接口。
- request: ChatRequest：FastAPI 从 JSON 请求体创建这个模型对象，并进行校验。
- -> ChatRequest：返回类型声明，FastAPI 据此生成响应文档和序列化结果。
- return request：回显收到的数据，没有检索或模型回答。

在 /docs 中展开 POST /chat，点击 Try it out，提交：

```json
{
  "knowledge_base_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "服务如何部署？"
}
```

成功返回 200 和相同内容。UUID 只验证格式，不查询知识库是否存在，因此练习时可以使用上面的示例 ID。

把 UUID 改成 abc，或者把 question 改成空字符串，再执行：FastAPI 返回 422，detail 列出错误字段。这是请求校验，没有调用 Java 的异常处理器。

空格组成的问题目前不会被自动去除；本步只学习类型和长度校验。
