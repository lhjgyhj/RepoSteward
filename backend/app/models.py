# ORM 模型定义：Installation、Repository、Event 三张首批表（报告 §8 核心数据模型概要）
# TODO(M1-T1): 定义首批三张表及其字段
# Installation：github_installation_id（唯一）、account、plan、daily_budget
# Repository：installation、github_repo_id、name、labels（缓存）、config
# Event：repo、delivery_id（唯一）、type、payload、received_at

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
