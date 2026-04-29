import os
from pathlib import Path

# 项目根目录的路径
class Config:
    BASE_DIR = Path(__file__).parent.parent
    # 直接使用默认密钥
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # 应用配置
    # 应用监听的主机地址
    APP_HOST = "0.0.0.0"
    # 服务器监听的端口号
    APP_PORT = 5000
    # 是否启动调用模式
    APP_DEBUG = False
    # 上传的文件的最大文件大小
    MAX_FILE_SIZE = 104857600  # 100M
    # 允许上传的文件
    ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}
    # 允许上传的图片的扩展名
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
    # 允许上传的图片的最大大小，默认为5M
    MAX_IMAGE_SIZE = 5242880

    # 日志配置
    # 日志存放目录
    LOG_DIR = "./logs"
    # 日志文件
    LOG_FILE = "rag_lite.log"
    # 日志级别
    LOG_LEVEL = "INFO"
    # 是否启用文件日志
    LOG_ENABLE_FILE = True
    # 是否启用控制台
    LOG_ENABLE_CONSOLE = True

    # 数据库配置
    DB_HOST = "localhost"
    DB_PORT = 3306
    DB_USER = "root"
    DB_PASSWORD = os.getenv("DB_PASSWORD", "change_me")
    DB_NAME = "rag"
    DB_CHARSET = "utf8mb4"

    # 存储的类型
    STORAGE_TYPE = "local"  # local / minio
    # 本地文件的存储目录
    STORAGE_DIR = "./storages"

    # MinIO 配置（当 STORAGE_TYPE='minio' 时使用）
    MINIO_ENDPOINT = ""
    MINIO_ACCESS_KEY = ""
    MINIO_SECRET_KEY = ""
    MINIO_BUCKET_NAME = "rag-lite"
    MINIO_SECURE = False
    MINIO_REGION = None

    # --- 模型配置 ---
    
    # 核心模型切换开关 (如果你的代码逻辑使用 LLM_TYPE 来判断)
    LLM_TYPE = "ollama" 

    DEEPSEEK_CHAT_MODEL = "deepseek-chat"
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    OPENAI_CHAT_MODEL = "deepseek-chat"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = "https://api.deepseek.com"

    # Ollama 配置修改：指向本地 11434 端口，并使用本地已下载的模型
    OLLAMA_CHAT_MODEL = "qwen2.5" # 建议使用 qwen2.5，请确保已执行 ollama pull qwen2.5
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
    OLLAMA_BASE_URL = "http://localhost:11434"

    # 指定向量数据库的类型
    VECTOR_DB_TYPE = "chroma"  # chroma 或 milvus
    # 指定 chroma 向量数据库的本地存储目录
    CHROMA_PERSIST_DIRECTORY = "./chroma_db"

    MILVUS_HOST = "localhost"
    MILVUS_PORT = "19530"
    
    # Neo4j 配置
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "change_me")
    
    # 检索配置
    TOP_K = 5
    VECTOR_THRESHOLD = 0.1
    KEYWORD_THRESHOLD = 0.1
    VECTOR_WEIGHT = 0.3
    KEYWORD_WEIGHT = 0.3
    KG_WEIGHT = 0.4
    RRF_K = 60
