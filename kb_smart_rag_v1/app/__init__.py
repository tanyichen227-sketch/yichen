from flask import Flask
import os
from app.config import Config
from app.utils.logger import get_logger

# 导入初始化数据库的函数
from app.utils.db import init_db


def create_app(config_class=Config):
    # 获取名为当前的模块名的日志记录器
    logger = get_logger(__name__)
    try:
        logger.info("初始化数据库...")
        init_db()
        logger.info("初始化数据库成功")
    except Exception as e:
        logger.warning(f"数据库初始化失败")
    # 获取当前文件所在的目录的绝对路径
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app = Flask(
        __name__,
        # 指定模板文件的路径
        template_folder=os.path.join(base_dir, "templates"),
        # 静态文件目录
        static_folder=os.path.join(base_dir, "static"),
    )

    # 注册上下文管理器，在所有的模板里可用
    @app.context_processor
    def inject_user():
        return dict(current_user=None)

    from app.blueprints import auth, knowledgebase, settings, document, chat
    from app.blueprints.knowledge_graph import knowledge_graph_bp

    app.register_blueprint(auth.bp)
    app.register_blueprint(knowledgebase.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(document.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(knowledge_graph_bp)
    # 从给定的配置类中加载配置信息到应用
    app.config.from_object(config_class)

    return app
