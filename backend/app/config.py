# 配置读取：集中从环境变量加载数据库连接、GitHub App 凭据、会话密钥等设置（报告 §4.1 确定性内核配置入口）
# TODO(M1-T1): 读取下列环境变量，供各模块统一取用配置
# 需要读取的变量：DATABASE_URL、GITHUB_WEBHOOK_SECRET、GITHUB_APP_ID、GITHUB_PRIVATE_KEY_PATH、
# GITHUB_CLIENT_ID、GITHUB_CLIENT_SECRET、SESSION_SECRET、FRONTEND_URL。

from pydantic_settings import BaseSettings, SettingsConfigDict
