# Webhook 接收端点：POST /webhooks/github，验签、入库去重、快速过滤后返回 202（报告 §4.2 第 1~3 步、F2.1~F2.3）
import json

from fastapi import APIRouter, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Event, Repository
from app.security import verify_github_signature
from app.services.installations import handle_installation
from app.services.issue_triage import record_issue_triage

router = APIRouter()


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> Response:
    """接收 GitHub Webhook：验签通过后入库并尽快返回 202。

    签名无效必须拒绝，不能返回 202。
    同一 X-GitHub-Delivery 重复到达时仍返回 202，且不得插入第二行。
    没有对应仓库行时不要硬插 Event，避免伪造仓库。
    """
    payload = await request.body()
    if verify_github_signature(payload, x_hub_signature_256) is False:
        return Response(status_code=401)
    if not x_github_delivery or not x_github_event:
        return Response(status_code=400)

    # 请求体不是合法 JSON 就直接拒绝，不落半条数据
    try:
        payload_dict = json.loads(payload)
    except json.JSONDecodeError:
        return Response(status_code=400)

    async with SessionLocal() as session:
        if x_github_event == "installation":
            await handle_installation(session, payload_dict)

        # installation 事件可能只带 repositories 列表，此时没有 repository 键，跳过 Event
        event: Event | None = None
        github_repo_id = (payload_dict.get("repository") or {}).get("id")
        if github_repo_id is not None:
            result = await session.execute(
                select(Repository).where(Repository.github_repo_id == github_repo_id)
            )
            repo = result.scalar_one_or_none()
            if repo is not None:
                event = Event(
                    repo_id=repo.id,
                    delivery_id=x_github_delivery,
                    type=x_github_event,
                    payload=payload_dict
                )
                session.add(event)

        # delivery_id 唯一约束冲突视为重复投递：不 500、不插第二行，仍返回 202。
        # flush 放在 try 内，重复投递时在这里就撞唯一约束，不会带着半套数据进 commit
        try:
            if (
                event is not None
                and x_github_event == "issues"
                and payload_dict.get("action") == "opened"
            ):
                await record_issue_triage(session, event, payload_dict)
            await session.commit()
        except IntegrityError:
            await session.rollback()

    return Response(status_code=202)
