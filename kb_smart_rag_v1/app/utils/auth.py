from flask import g
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 获取当前登录的用户
def get_current_user():
    if not hasattr(g, "current_user"):
        # 移除用户认证，始终返回默认值
        g.current_user = 'admin'
    return g.current_user


def login_required(f):
    # 移除登录认证，直接返回原函数
    return f


# 定义 API 登录认证装饰器
def api_login_required(f):
    """
    API 登录装饰器
    用于 API 端点，现在移除了认证逻辑
    """
    # 移除登录认证，直接返回原函数
    return f
