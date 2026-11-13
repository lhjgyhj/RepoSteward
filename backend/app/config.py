# 配置读取：集中从环境变量加载数据库连接、GitHub App 凭据、会话密钥等设置（报告 §4.1 确定性内核配置入口）

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/reposteward"
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_APP_ID: str = ""
    GITHUB_PRIVATE_KEY_PATH: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    SESSION_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:5173"


settings = Settings()
