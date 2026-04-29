# KnowledgeRAG-GZHU 分享说明

这是一份源码分享包说明。压缩包保留了项目源码、配置模板、Docker 配置、启动脚本和文档；不包含本机依赖、缓存、数据库数据、日志、上传文件、向量库和私密 `.env`。

## 项目结构

- `RagBackend/`：FastAPI 后端，主要入口是 `main.py`，依赖见 `requirements.txt`。
- `RagFrontend/`：Vue 3 + Vite 前端，依赖见 `package.json` / `package-lock.json`。
- `RagMobile/`：React Native / Expo 移动端。
- `kb_smart_rag_v1/`：独立的轻量 Flask RAG 子项目，作为可选参考模块。
- `docs/`、`apifox/`、`assets/`：文档、接口集合和静态资源。
- `docker-compose.yml`：完整容器编排，包含前端、后端、MySQL、Redis、Ollama 等服务。
- `docker-compose.lite.yml`：轻量容器编排，适合接入公网 LLM API。
- `dev.ps1`：Windows 本地开发一键启动脚本。
- `mysql/init/01-init.sql`、`RagBackend/docs/init.sql`：本地数据库初始化 SQL 脚本。

## 环境要求

- Python 3.10+
- Node.js 18+
- Docker Desktop（推荐，用于 MySQL / Redis / 完整部署）
- Ollama（如果使用本地模型）

推荐本地模型：

```powershell
ollama pull qwen2:0.5b
```

## 本地开发启动

1. 配置后端环境变量：

```powershell
Copy-Item RagBackend\.env.example RagBackend\.env
notepad RagBackend\.env
```

至少修改：

- `DB_PASSWORD`
- `JWT_SECRET`
- `MODEL`（可保留 `qwen2:0.5b`）

2. 配置前端可选环境变量：

```powershell
Copy-Item RagFrontend\.env.example RagFrontend\.env
notepad RagFrontend\.env
```

如果需要 Lens 学术搜索功能，填写 `VITE_LENS_API_KEY`。

3. 安装依赖：

```powershell
cd RagBackend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

cd ..\RagFrontend
npm install
```

4. 启动项目：

```powershell
cd ..
powershell -ExecutionPolicy Bypass -File .\dev.ps1
```

访问地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## Docker 启动

完整版本：

```powershell
docker compose up -d
```

轻量版本：

```powershell
docker compose -f docker-compose.lite.yml up -d
```

访问地址：

- 前端：`http://localhost:8089`
- API 文档：`http://localhost:8000/docs`

## 分享包未包含的内容

以下内容是本机生成或可能包含隐私/凭据的数据，已经从分享包排除：

- `.env`、`.env.local`
- `node_modules/`、`.venv/`
- `dist/`、`build/`
- `__pycache__/`、`.pytest_cache/`
- `.idea/`、`.vscode/`
- `.local-mysql/`
- `local-KLB-files/`、`knowledge_base/`、`metadata/`、`user_avatars/`
- `logs/`、`*.log`
- `kb_smart_rag_v1/chroma_db/`、`kb_smart_rag_v1/storages/`

如果你确实需要迁移旧数据，需要单独导出数据库和向量库，并确认其中不含隐私信息后再分享。

## SQL 文件

分享包包含项目自己的 SQL 脚本：

- `mysql/init/01-init.sql`
- `RagBackend/docs/init.sql`

依赖目录 `.venv/` 内部的第三方迁移 SQL 不会打包。
