# 数据库连接层：异步引擎、会话工厂与 ORM 模型基类（报告 §8 核心数据模型的落库基础）
# TODO(M1-T1): 提供数据库连接、会话和模型基类

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
