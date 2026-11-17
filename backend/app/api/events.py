# 事件只读接口：GET /api/events 返回当前登录用户有维护权限的仓库的原始 Webhook 事件（报告 §4.2、F1.2）

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Event, Repository

router = APIRouter()


@router.get("/api/events")
async def list_events(request: Request) -> list[dict]:
    """返回已入库的原始 Webhook 事件，新的在前；未登录 401，没有可见仓库返回空列表。

    只列 Repository.github_repo_id 落在当前用户 repo_ids 里的事件，
    避免任何调用方读到别人的仓库数据。
    """
    # 登录态由 SessionMiddleware 写进 request.session，未登录直接 401
    github_user = request.session.get("github_user")
    if not github_user:
        raise HTTPException(status_code=401, detail="未登录")

    # 会话里没带可见仓库就是没有可看的事件，直接空列表，不查库、不 500
    repo_ids = github_user.get("repo_ids") or []
    if not repo_ids:
        return []

    # 步骤 1：用 app.db.SessionLocal 开异步会话
    async with SessionLocal() as session:
        # 步骤 2：Event 与 Repository 按外键关联，按 github_repo_id 过滤，received_at 降序
        result = await session.execute(
            select(Event)
            .join(Repository, Event.repo_id == Repository.id)
            .where(Repository.github_repo_id.in_(repo_ids))
            .order_by(Event.received_at.desc())
        )
        rows = result.scalars().all()

    # 步骤 3：每一行收成 dict，键为 id、type、delivery_id、received_at；时间转 isoformat 才能 JSON 序列化
    items = []
    for event in rows:
        items.append({
            "id": event.id,
            "type": event.type,
            "delivery_id": event.delivery_id,
            "received_at": event.received_at.isoformat(),
        })

    # 步骤 4：没有行就是空列表，不是错误
    return items
